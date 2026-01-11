use anyhow::{anyhow, Result};
use crc32fast::Hasher;

pub const WRAPPER_MAGIC: &[u8; 4] = b"QYN1";
pub const PAYLOAD_MAGIC: &[u8; 4] = b"MCSF";

pub const WRAPPER_FLAG_ENCRYPTED: u32 = 0x0001;
pub const WRAPPER_FLAG_METADATA_AUTHENTICATED: u32 = 0x0002;
pub const PAYLOAD_FLAG_CANONICAL_SECTIONS: u32 = 0x0001;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Version(pub u8, pub u8, pub u16);

impl Version {
    pub fn parse(text: &str) -> Result<Self> {
        let parts: Vec<_> = text.split('.').collect();
        let (major, minor, patch) = match parts.len() {
            2 => (parts[0], parts[1], "0"),
            3 => (parts[0], parts[1], parts[2]),
            _ => return Err(anyhow!("invalid version")),
        };
        Ok(Version(major.parse()?, minor.parse()?, patch.parse()?))
    }

    pub fn text(&self) -> String {
        format!("{}.{}.{}", self.0, self.1, self.2)
    }
}

#[derive(Clone, Copy)]
pub struct PayloadDescriptor {
    pub version: Version,
    pub features: u32,
}

pub const SUPPORTED_PAYLOADS: &[PayloadDescriptor] = &[
    PayloadDescriptor {
        version: Version(1, 0, 0),
        features: 0,
    },
    PayloadDescriptor {
        version: Version(1, 1, 0),
        features: PAYLOAD_FLAG_CANONICAL_SECTIONS,
    },
    PayloadDescriptor {
        version: Version(1, 2, 0),
        features: PAYLOAD_FLAG_CANONICAL_SECTIONS,
    },
];

pub fn negotiate_payload(requested: &Version) -> Option<&'static PayloadDescriptor> {
    SUPPORTED_PAYLOADS
        .iter()
        .rev()
        .find(|desc| desc.version.0 == requested.0 && desc.version <= *requested)
}

#[derive(Clone, Copy, Debug)]
pub struct FrameHeader {
    pub magic: [u8; 4],
    pub version: Version,
    pub flags: u32,
    pub length: u32,
    pub checksum: u32,
}

pub fn encode_frame(magic: &[u8; 4], version: Version, flags: u32, payload: &[u8]) -> Vec<u8> {
    let mut hasher = Hasher::new();
    hasher.update(payload);
    let checksum = hasher.finalize();
    let mut out = Vec::with_capacity(20 + payload.len());
    out.extend_from_slice(magic);
    out.push(version.0);
    out.push(version.1);
    out.extend_from_slice(&version.2.to_be_bytes());
    out.extend_from_slice(&flags.to_be_bytes());
    out.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    out.extend_from_slice(&checksum.to_be_bytes());
    out.extend_from_slice(payload);
    out
}

pub fn decode_frame<'a>(
    data: &'a [u8],
    expected_magic: Option<&[u8; 4]>,
) -> Result<(FrameHeader, Vec<u8>, &'a [u8])> {
    if data.len() < 20 {
        return Err(anyhow!("frame too small"));
    }
    let magic = [data[0], data[1], data[2], data[3]];
    if let Some(expected) = expected_magic {
        if &magic != expected {
            return Err(anyhow!("unexpected frame magic"));
        }
    }
    let version = Version(data[4], data[5], u16::from_be_bytes([data[6], data[7]]));
    let flags = u32::from_be_bytes([data[8], data[9], data[10], data[11]]);
    let length = u32::from_be_bytes([data[12], data[13], data[14], data[15]]);
    let checksum = u32::from_be_bytes([data[16], data[17], data[18], data[19]]);
    let start = 20usize;
    let end = start + length as usize;
    if end > data.len() {
        return Err(anyhow!("frame payload truncated"));
    }
    let payload = data[start..end].to_vec();
    let mut hasher = Hasher::new();
    hasher.update(&payload);
    if hasher.finalize() != checksum {
        return Err(anyhow!("frame checksum mismatch"));
    }
    let remainder = &data[end..];
    let header = FrameHeader {
        magic,
        version,
        flags,
        length,
        checksum,
    };
    Ok((header, payload, remainder))
}

#[derive(Clone, Copy, Debug)]
pub struct SectionHeader {
    pub id: u16,
    pub flags: u16,
    pub length: u32,
    pub checksum: u32,
}

pub fn encode_section(id: u16, flags: u16, payload: &[u8]) -> Vec<u8> {
    let mut hasher = Hasher::new();
    hasher.update(payload);
    let checksum = hasher.finalize();
    let mut out = Vec::with_capacity(12 + payload.len());
    out.extend_from_slice(&id.to_le_bytes());
    out.extend_from_slice(&flags.to_le_bytes());
    out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    out.extend_from_slice(&checksum.to_le_bytes());
    out.extend_from_slice(payload);
    out
}

pub fn decode_sections(buffer: &[u8]) -> Result<Vec<(SectionHeader, Vec<u8>)>> {
    let mut offset = 0usize;
    let mut sections = Vec::new();
    while offset < buffer.len() {
        if offset + 12 > buffer.len() {
            return Err(anyhow!("truncated section header"));
        }
        let id = u16::from_le_bytes([buffer[offset], buffer[offset + 1]]);
        let flags = u16::from_le_bytes([buffer[offset + 2], buffer[offset + 3]]);
        let length = u32::from_le_bytes([
            buffer[offset + 4],
            buffer[offset + 5],
            buffer[offset + 6],
            buffer[offset + 7],
        ]);
        let checksum = u32::from_le_bytes([
            buffer[offset + 8],
            buffer[offset + 9],
            buffer[offset + 10],
            buffer[offset + 11],
        ]);
        offset += 12;
        let end = offset + length as usize;
        if end > buffer.len() {
            return Err(anyhow!("truncated section payload"));
        }
        let payload = buffer[offset..end].to_vec();
        offset = end;
        let mut hasher = Hasher::new();
        hasher.update(&payload);
        if hasher.finalize() != checksum {
            return Err(anyhow!("section checksum mismatch"));
        }
        sections.push((SectionHeader { id, flags, length, checksum }, payload));
    }
    Ok(sections)
}
