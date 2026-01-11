use anyhow::{anyhow, bail, Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use crc32fast::Hasher;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, HashSet};
use std::io::{Read, Write};

use chacha20poly1305::aead::{Aead, KeyInit, Payload};
use chacha20poly1305::ChaCha20Poly1305;
use getrandom::getrandom;
use pbkdf2::pbkdf2_hmac;
use sha2::Sha256;

const WRAPPER_MAGIC: &[u8; 4] = b"QYN1";
const PAYLOAD_MAGIC: &[u8; 4] = b"MCS\0";
const PBKDF_ROUNDS: u32 = 200_000;

const FEATURE_BITS: [(&str, u32); 4] = [
    ("compression:optimisation", 0),
    ("compression:extras", 1),
    ("payload:source-map", 2),
    ("compression:fse", 3),
];

#[derive(Debug, Deserialize)]
struct CanonicalVersions {
    wrapper_version: String,
    payload_version: String,
    dictionary_version: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(default)]
pub struct Descriptor {
    pub wrapper_version: String,
    pub payload_version: String,
    pub payload_features: Vec<String>,
    pub metadata: Value,
    pub salt: Option<String>,
    pub nonce: Option<String>,
    pub sections: Sections,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(default)]
pub struct Sections {
    pub stream_header: StreamHeader,
    pub compression: Compression,
    pub tokens: String,
    pub string_table: String,
    pub payloads: Value,
    pub payload_channels: PayloadChannels,
    pub source_map: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(default)]
pub struct PayloadChannels {
    pub identifiers: Option<Value>,
    pub strings: Option<Value>,
    pub integers: Option<Value>,
    pub counts: Option<Value>,
    pub flags: Option<Value>,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(default)]
pub struct StreamHeader {
    pub dictionary_version: String,
    pub encoder_version: String,
    pub source_language: String,
    pub source_language_version: String,
    pub symbol_count: u32,
    pub source_hash: String,
    pub has_source_map: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(default)]
pub struct Compression {
    pub backend: String,
    pub symbol_count: u32,
    pub model: Value,
    pub extras: Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Version {
    major: u8,
    minor: u8,
    patch: u16,
}

impl Version {
    fn parse(text: &str) -> Result<Self> {
        let mut parts = text.split('.').collect::<Vec<_>>();
        if parts.len() == 2 {
            parts.push("0");
        }
        if parts.len() != 3 {
            bail!("invalid version '{}'", text);
        }
        Ok(Self {
            major: parts[0].parse()?,
            minor: parts[1].parse()?,
            patch: parts[2].parse()?,
        })
    }

    fn text(&self) -> String {
        format!("{}.{}.{}", self.major, self.minor, self.patch)
    }
}

#[derive(Debug, Clone)]
struct FrameHeader {
    version: Version,
    features: Vec<String>,
}

#[derive(Debug, Clone)]
struct Section {
    id: u16,
    flags: u16,
    payload: Vec<u8>,
}

fn canonical_versions() -> CanonicalVersions {
    serde_json::from_str(include_str!("../../canonical_versions.json"))
        .expect("canonical version map must be valid json")
}

pub fn decode_descriptor(data: &[u8], passphrase: &str) -> Result<Descriptor> {
    let (wrapper_header, wrapper_body, remainder) = read_frame(data, WRAPPER_MAGIC)?;
    if !remainder.is_empty() {
        bail!("unexpected trailing data after wrapper frame");
    }
    let wrapper: Value = serde_json::from_slice(&wrapper_body)?;
    let wrapper_obj = wrapper
        .as_object()
        .ok_or_else(|| anyhow!("wrapper JSON must be an object"))?;
    let advertised = wrapper_obj
        .get("payload_features")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if !advertised.is_empty() && !feature_sets_match(&advertised, &wrapper_header.features) {
        bail!("wrapper feature bitset mismatch");
    }

    let metadata = wrapper_obj.get("metadata").cloned().unwrap_or(Value::Null);
    let aad = metadata_aad(&metadata);

    let salt = decode_base64_field(wrapper_obj, "salt")?;
    let nonce = decode_base64_field(wrapper_obj, "nonce")?;
    let ciphertext = decode_base64_field(wrapper_obj, "ciphertext")?;
    let tag = decode_base64_field(wrapper_obj, "tag")?;

    let payload_frame_bytes = decrypt_payload(passphrase, &salt, &nonce, &ciphertext, &tag, &aad)?;
    let (payload_header, payload_body, payload_remainder) =
        read_frame(&payload_frame_bytes, PAYLOAD_MAGIC)?;
    if !payload_remainder.is_empty() {
        bail!("unexpected trailing data after payload frame");
    }
    if !feature_sets_match(&payload_header.features, &wrapper_header.features) {
        bail!("payload feature set mismatch with wrapper");
    }

    let sections = decode_sections(&payload_body)?;
    let mut section_map = sections
        .into_iter()
        .map(|s| (s.id, s))
        .collect::<std::collections::HashMap<_, _>>();

    let stream = section_map
        .remove(&0x0001)
        .context("missing stream header")?;
    let mut cursor = std::io::Cursor::new(&stream.payload);
    let dictionary_version = read_utf8(&mut cursor)?;
    let encoder_version = read_utf8(&mut cursor)?;
    let source_language = read_utf8(&mut cursor)?;
    let source_language_version = read_utf8(&mut cursor)?;
    let symbol_count = read_u32(&mut cursor)?;
    let _hash_type = read_u8(&mut cursor)?;
    let mut hash_bytes = [0u8; 32];
    cursor.read_exact(&mut hash_bytes)?;
    let source_hash = if hash_bytes.iter().all(|b| *b == 0) {
        String::new()
    } else {
        hex::encode(hash_bytes)
    };

    let compression = section_map
        .remove(&0x0002)
        .context("missing compression section")?;
    let mut comp_cursor = std::io::Cursor::new(&compression.payload);
    let backend = read_utf8(&mut comp_cursor)?;
    let comp_symbol_count = read_u32(&mut comp_cursor)?;
    let model_blob = read_length_prefixed(&mut comp_cursor)?;
    let extras_blob = read_length_prefixed(&mut comp_cursor)?;
    let model: Value = serde_json::from_slice(&model_blob).unwrap_or(Value::Object(Map::new()));
    let extras: Value = if extras_blob.is_empty() {
        Value::Object(Map::new())
    } else {
        serde_json::from_slice(&extras_blob)?
    };

    let tokens_section = section_map
        .remove(&0x0003)
        .context("missing tokens section")?;
    let tokens = read_length_prefixed(&mut std::io::Cursor::new(&tokens_section.payload))?;

    let string_section = section_map
        .remove(&0x0004)
        .context("missing string table section")?;
    let string_table = read_length_prefixed(&mut std::io::Cursor::new(&string_section.payload))?;

    let payload_section = section_map
        .remove(&0x0005)
        .context("missing payload section")?;
    let payloads: Value = serde_json::from_slice(&read_length_prefixed(
        &mut std::io::Cursor::new(&payload_section.payload),
    ))?;

    let mut payload_channels = PayloadChannels::default();
    for (sid, target) in [
        (0x0101, &mut payload_channels.identifiers),
        (0x0102, &mut payload_channels.strings),
        (0x0103, &mut payload_channels.integers),
        (0x0104, &mut payload_channels.counts),
        (0x0105, &mut payload_channels.flags),
    ] {
        if let Some(section) = section_map.remove(&sid) {
            let value: Value = serde_json::from_slice(&read_length_prefixed(
                &mut std::io::Cursor::new(&section.payload),
            ))?;
            *target = Some(value);
        }
    }

    let source_map = if let Some(sec) = section_map.remove(&0x0006) {
        let blob = read_length_prefixed(&mut std::io::Cursor::new(&sec.payload))?;
        Some(STANDARD.encode(blob))
    } else {
        None
    };

    let metadata_section = section_map
        .remove(&0x0007)
        .context("missing metadata section")?;
    let metadata_inner: Value = serde_json::from_slice(&read_length_prefixed(
        &mut std::io::Cursor::new(&metadata_section.payload),
    ))?;

    let desc = Descriptor {
        wrapper_version: wrapper_header.version.text(),
        payload_version: payload_header.version.text(),
        payload_features: payload_header.features,
        metadata: metadata_inner,
        salt: Some(STANDARD.encode(salt)),
        nonce: Some(STANDARD.encode(nonce)),
        sections: Sections {
            stream_header: StreamHeader {
                dictionary_version,
                encoder_version,
                source_language,
                source_language_version,
                symbol_count,
                source_hash,
                has_source_map: stream.flags & 0x0001 != 0,
            },
            compression: Compression {
                backend,
                symbol_count: comp_symbol_count,
                model,
                extras,
            },
            tokens: STANDARD.encode(tokens),
            string_table: STANDARD.encode(string_table),
            payloads,
            payload_channels,
            source_map,
        },
    };
    Ok(desc)
}

pub fn encode_descriptor(desc: Descriptor, passphrase: &str) -> Result<Vec<u8>> {
    let canonical = canonical_versions();
    let wrapper_version_text = if desc.wrapper_version.is_empty() {
        canonical.wrapper_version.clone()
    } else {
        desc.wrapper_version.clone()
    };
    let payload_version_text = if desc.payload_version.is_empty() {
        canonical.payload_version.clone()
    } else {
        desc.payload_version.clone()
    };
    let wrapper_version = Version::parse(&wrapper_version_text)?;
    let payload_version = Version::parse(&payload_version_text)?;

    let dictionary_version = if desc.sections.stream_header.dictionary_version.is_empty() {
        canonical.dictionary_version.clone()
    } else {
        desc.sections.stream_header.dictionary_version.clone()
    };

    let mut stream_payload = Vec::new();
    stream_payload.extend(write_utf8(&dictionary_version));
    stream_payload.extend(write_utf8(&desc.sections.stream_header.encoder_version));
    stream_payload.extend(write_utf8(&desc.sections.stream_header.source_language));
    stream_payload.extend(write_utf8(
        &desc.sections.stream_header.source_language_version,
    ));
    stream_payload.extend(&desc.sections.stream_header.symbol_count.to_le_bytes());
    stream_payload.push(0);
    if desc.sections.stream_header.source_hash.is_empty() {
        stream_payload.extend([0u8; 32]);
    } else {
        let hash = hex::decode(&desc.sections.stream_header.source_hash)
            .context("invalid source hash hex")?;
        if hash.len() != 32 {
            bail!("source hash must be 32 bytes");
        }
        stream_payload.extend(hash);
    }
    let stream_section = write_section(
        0x0001,
        if desc.sections.stream_header.has_source_map {
            0x0001
        } else {
            0
        },
        &stream_payload,
    );

    let mut comp_payload = Vec::new();
    comp_payload.extend(write_utf8(&desc.sections.compression.backend));
    comp_payload.extend(&desc.sections.compression.symbol_count.to_le_bytes());
    comp_payload.extend(write_length_prefixed(canonical_json_bytes(
        &desc.sections.compression.model,
    )));
    comp_payload.extend(write_length_prefixed(canonical_json_bytes(
        &desc.sections.compression.extras,
    )));
    let compression_section = write_section(0x0002, 0, &comp_payload);

    let tokens = STANDARD
        .decode(desc.sections.tokens.as_bytes())
        .context("invalid tokens base64")?;
    let tokens_section = write_section(0x0003, 0, &write_length_prefixed(&tokens));

    let string_table = STANDARD
        .decode(desc.sections.string_table.as_bytes())
        .context("invalid string table base64")?;
    let string_section = write_section(0x0004, 0, &write_length_prefixed(&string_table));

    let payloads_section = write_section(
        0x0005,
        0,
        &write_length_prefixed(&canonical_json_bytes(&desc.sections.payloads)),
    );

    let mut channel_sections = Vec::new();
    for (sid, value) in [
        (0x0101, &desc.sections.payload_channels.identifiers),
        (0x0102, &desc.sections.payload_channels.strings),
        (0x0103, &desc.sections.payload_channels.integers),
        (0x0104, &desc.sections.payload_channels.counts),
        (0x0105, &desc.sections.payload_channels.flags),
    ] {
        if let Some(payload) = value {
            channel_sections.push(write_section(
                sid,
                0,
                &write_length_prefixed(&canonical_json_bytes(payload)),
            ));
        }
    }

    let source_map_section = if let Some(ref sm) = desc.sections.source_map {
        let blob = STANDARD
            .decode(sm.as_bytes())
            .context("invalid source map base64")?;
        write_section(0x0006, 0, &write_length_prefixed(&blob))
    } else {
        Vec::new()
    };

    let metadata_bytes = canonical_json_bytes(&desc.metadata);
    let metadata_section = write_section(0x0007, 0, &write_length_prefixed(&metadata_bytes));

    let mut payload_body = Vec::new();
    payload_body.extend(stream_section);
    payload_body.extend(compression_section);
    payload_body.extend(tokens_section);
    payload_body.extend(string_section);
    payload_body.extend(payloads_section);
    for section in channel_sections {
        payload_body.extend(section);
    }
    payload_body.extend(source_map_section);
    payload_body.extend(metadata_section);

    let mut features = if desc.payload_features.is_empty() {
        Vec::new()
    } else {
        desc.payload_features.clone()
    };
    if features.is_empty() {
        if let Some(obj) = desc.sections.compression.extras.as_object() {
            if !obj.is_empty() {
                features.push("compression:extras".to_string());
                if obj.contains_key("optimisation") {
                    features.push("compression:optimisation".to_string());
                }
            }
        }
        if desc.sections.compression.backend == "fse" {
            features.push("compression:fse".to_string());
        }
        if desc.sections.source_map.is_some() {
            features.push("payload:source-map".to_string());
        }
    }

    let payload_frame = write_frame(PAYLOAD_MAGIC, &payload_version, &features, &payload_body)?;

    let salt = if let Some(ref salt_b64) = desc.salt {
        STANDARD
            .decode(salt_b64.as_bytes())
            .context("invalid salt base64")?
    } else {
        let mut buf = [0u8; 16];
        getrandom(&mut buf)?;
        buf.to_vec()
    };
    let nonce = if let Some(ref nonce_b64) = desc.nonce {
        STANDARD
            .decode(nonce_b64.as_bytes())
            .context("invalid nonce base64")?
    } else {
        let mut buf = [0u8; 12];
        getrandom(&mut buf)?;
        buf.to_vec()
    };
    let key = derive_key(passphrase, &salt)?;
    let cipher = ChaCha20Poly1305::new_from_slice(&key)?;
    let aad = metadata_aad(&desc.metadata);
    let ciphertext = cipher.encrypt(
        nonce.as_slice().into(),
        Payload {
            msg: &payload_frame,
            aad: &aad,
        },
    )?;
    let (ciphertext_only, tag) = ciphertext.split_at(payload_frame.len());

    let wrapper = json!({
        "version": wrapper_version.text(),
        "payload_version": payload_version.text(),
        "payload_features": features,
        "metadata": desc.metadata,
        "salt": STANDARD.encode(&salt),
        "nonce": STANDARD.encode(&nonce),
        "ciphertext": STANDARD.encode(ciphertext_only),
        "tag": STANDARD.encode(tag),
    });
    let wrapper_bytes = canonical_json_bytes(&wrapper);
    let wrapper_frame = write_frame(WRAPPER_MAGIC, &wrapper_version, &features, &wrapper_bytes)?;
    Ok(wrapper_frame)
}

fn metadata_aad(metadata: &Value) -> Vec<u8> {
    let mut aad = b"QYN1-METADATA-v1:".to_vec();
    aad.extend(canonical_json_bytes(metadata));
    aad
}

fn derive_key(passphrase: &str, salt: &[u8]) -> Result<[u8; 32]> {
    let mut key = [0u8; 32];
    pbkdf2_hmac::<Sha256>(passphrase.as_bytes(), salt, PBKDF_ROUNDS, &mut key);
    Ok(key)
}

fn decode_base64_field(map: &Map<String, Value>, name: &str) -> Result<Vec<u8>> {
    let value = map
        .get(name)
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow!("{} missing from wrapper", name))?;
    Ok(STANDARD.decode(value.as_bytes())?)
}

fn decrypt_payload(
    passphrase: &str,
    salt: &[u8],
    nonce: &[u8],
    ciphertext: &[u8],
    tag: &[u8],
    aad: &[u8],
) -> Result<Vec<u8>> {
    let key = derive_key(passphrase, salt)?;
    let cipher = ChaCha20Poly1305::new_from_slice(&key)?;
    let mut combined = Vec::with_capacity(ciphertext.len() + tag.len());
    combined.extend_from_slice(ciphertext);
    combined.extend_from_slice(tag);
    let plaintext = cipher.decrypt(
        nonce.into(),
        Payload {
            msg: &combined,
            aad,
        },
    )?;
    Ok(plaintext)
}

fn write_frame(
    magic: &[u8; 4],
    version: &Version,
    features: &[String],
    body: &[u8],
) -> Result<Vec<u8>> {
    let mut header = Vec::with_capacity(16);
    header.extend_from_slice(magic);
    header.push(version.major);
    header.push(version.minor);
    header.extend_from_slice(&version.patch.to_be_bytes());
    header.extend_from_slice(&encode_feature_bits(features)?.to_be_bytes());
    header.extend_from_slice(&(body.len() as u32).to_be_bytes());
    let mut hasher = Hasher::new();
    hasher.update(body);
    let crc = hasher.finalize().to_be_bytes();
    let mut frame = Vec::with_capacity(header.len() + body.len() + 4);
    frame.extend_from_slice(&header);
    frame.extend_from_slice(body);
    frame.extend_from_slice(&crc);
    Ok(frame)
}

fn read_frame(data: &[u8], expected_magic: &[u8; 4]) -> Result<(FrameHeader, Vec<u8>, &[u8])> {
    if data.len() < 20 {
        bail!("frame too small");
    }
    if &data[0..4] != expected_magic {
        bail!("unexpected frame magic");
    }
    let version = Version {
        major: data[4],
        minor: data[5],
        patch: u16::from_be_bytes([data[6], data[7]]),
    };
    let feature_bits = u32::from_be_bytes([data[8], data[9], data[10], data[11]]);
    let length = u32::from_be_bytes([data[12], data[13], data[14], data[15]]);
    let body_start = 16usize;
    let body_end = body_start + length as usize;
    let crc_end = body_end + 4;
    if crc_end > data.len() {
        bail!("frame truncated");
    }
    let body = &data[body_start..body_end];
    let mut hasher = Hasher::new();
    hasher.update(body);
    if hasher.finalize() != u32::from_be_bytes(data[body_end..crc_end].try_into().unwrap()) {
        bail!("frame CRC mismatch");
    }
    let features = decode_feature_bits(feature_bits)?;
    Ok((
        FrameHeader { version, features },
        body.to_vec(),
        &data[crc_end..],
    ))
}

fn encode_feature_bits(features: &[String]) -> Result<u32> {
    let mut bits = 0u32;
    for feature in features {
        let (_, idx) = FEATURE_BITS
            .iter()
            .find(|(name, _)| name == feature)
            .ok_or_else(|| anyhow!("unknown feature '{}'", feature))?;
        bits |= 1 << idx;
    }
    Ok(bits)
}

fn decode_feature_bits(bits: u32) -> Result<Vec<String>> {
    let mut features = Vec::new();
    for (name, idx) in FEATURE_BITS {
        if bits & (1 << idx) != 0 {
            features.push(name.to_string());
        }
    }
    features.sort();
    let known_bits = encode_feature_bits(&features)?;
    let unknown = bits & !known_bits;
    if unknown != 0 {
        bail!("frame advertises unknown feature bits 0x{unknown:08x}");
    }
    Ok(features)
}

fn decode_sections(buffer: &[u8]) -> Result<Vec<Section>> {
    let mut offset = 0usize;
    let mut sections = Vec::new();
    while offset < buffer.len() {
        if offset + 8 > buffer.len() {
            bail!("truncated section header");
        }
        let id = u16::from_le_bytes([buffer[offset], buffer[offset + 1]]);
        let flags = u16::from_le_bytes([buffer[offset + 2], buffer[offset + 3]]);
        let length = u32::from_le_bytes([
            buffer[offset + 4],
            buffer[offset + 5],
            buffer[offset + 6],
            buffer[offset + 7],
        ]);
        offset += 8;
        let end = offset + length as usize;
        if end > buffer.len() {
            bail!("truncated section payload");
        }
        sections.push(Section {
            id,
            flags,
            payload: buffer[offset..end].to_vec(),
        });
        offset = end;
    }
    Ok(sections)
}

fn write_section(id: u16, flags: u16, payload: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(8 + payload.len());
    out.extend_from_slice(&id.to_le_bytes());
    out.extend_from_slice(&flags.to_le_bytes());
    out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    out.extend_from_slice(payload);
    out
}

fn write_utf8(text: &str) -> Vec<u8> {
    let mut out = Vec::with_capacity(2 + text.len());
    out.extend_from_slice(&(text.len() as u16).to_le_bytes());
    out.extend_from_slice(text.as_bytes());
    out
}

fn read_utf8<R: Read>(reader: &mut R) -> Result<String> {
    let mut len_bytes = [0u8; 2];
    reader.read_exact(&mut len_bytes)?;
    let length = u16::from_le_bytes(len_bytes) as usize;
    let mut buf = vec![0u8; length];
    reader.read_exact(&mut buf)?;
    Ok(String::from_utf8(buf)?)
}

fn read_u32<R: Read>(reader: &mut R) -> Result<u32> {
    let mut buf = [0u8; 4];
    reader.read_exact(&mut buf)?;
    Ok(u32::from_le_bytes(buf))
}

fn read_u8<R: Read>(reader: &mut R) -> Result<u8> {
    let mut buf = [0u8; 1];
    reader.read_exact(&mut buf)?;
    Ok(buf[0])
}

fn write_length_prefixed(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(4 + data.len());
    out.extend_from_slice(&(data.len() as u32).to_le_bytes());
    out.extend_from_slice(data);
    out
}

fn read_length_prefixed<R: Read>(reader: &mut R) -> Result<Vec<u8>> {
    let mut len_buf = [0u8; 4];
    reader.read_exact(&mut len_buf)?;
    let length = u32::from_le_bytes(len_buf) as usize;
    let mut buf = vec![0u8; length];
    reader.read_exact(&mut buf)?;
    Ok(buf)
}

fn canonical_json_bytes(value: &Value) -> Vec<u8> {
    canonical_json_value(value).to_string().into_bytes()
}

fn canonical_json_value(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut ordered = BTreeMap::new();
            for (k, v) in map {
                ordered.insert(k.clone(), canonical_json_value(v));
            }
            Value::Object(ordered.into_iter().collect())
        }
        Value::Array(arr) => Value::Array(arr.iter().map(canonical_json_value).collect()),
        _ => value.clone(),
    }
}

fn feature_sets_match(a: &[String], b: &[String]) -> bool {
    if a.is_empty() {
        return true;
    }
    let set_a: HashSet<_> = a.iter().collect();
    let set_b: HashSet<_> = b.iter().collect();
    set_a == set_b
}
