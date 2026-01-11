#![cfg_attr(not(feature = "std"), no_std)]

use blake3::Hasher;
use chacha20poly1305::aead::{AeadInPlace, KeyInit};
use chacha20poly1305::{ChaCha20Poly1305, Nonce, Tag};

pub const BLOB_LEN: usize = 8256;
pub const HEADER_LEN: usize = 24;
pub const NONCE_LEN: usize = 24;
pub const AEAD_NONCE_LEN: usize = 12;
pub const TAG_LEN: usize = 16;
pub const PAYLOAD_LEN: usize = 8192;
pub const MANIFEST_LEN: usize = 256;

pub const MAGIC_HEADER: [u8; 4] = *b"EaM6";
pub const MAGIC_MANIFEST: [u8; 4] = *b"EaMM";

pub const ARCH_AARCH64: u8 = 1;
pub const ARCH_X86_64: u8 = 2;
pub const ARCH_WASM32: u8 = 3;

pub const FLAG_DETERMINISTIC_NONCE: u8 = 0b0000_0001;
pub const FLAG_HAS_LLM_PROFILE: u8 = 0b0000_0010;
pub const FLAG_HAS_ORGANELLE_MAP: u8 = 0b0000_0100;

pub mod capabilities {
    pub const LATTICE_READ: u32 = 1 << 0;
    pub const LATTICE_WRITE: u32 = 1 << 1;
    pub const CLOCK_READ: u32 = 1 << 2;
    pub const STORAGE_READ: u32 = 1 << 3;
    pub const STORAGE_WRITE: u32 = 1 << 4;
    pub const NET_CLIENT: u32 = 1 << 5;
    pub const NET_SERVER: u32 = 1 << 6;
    pub const SPAWN_SUCCESSOR: u32 = 1 << 7;
    pub const USE_ACCELERATOR: u32 = 1 << 8;
}

const KEY_CONTEXT: &[u8] = b"EaM6 key";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EaM6Header {
    pub magic: [u8; 4],
    pub version: u8,
    pub header_len: u8,
    pub flags: u8,
    pub arch: u8,
    pub cap_bitmap: u32,
    pub payload_len: u16,
    pub manifest_len: u16,
    pub reserved: [u8; 8],
}

impl EaM6Header {
    pub fn new(arch: u8, cap_bitmap: u32, flags: u8) -> Self {
        Self {
            magic: MAGIC_HEADER,
            version: 0x06,
            header_len: HEADER_LEN as u8,
            flags,
            arch,
            cap_bitmap,
            payload_len: PAYLOAD_LEN as u16,
            manifest_len: MANIFEST_LEN as u16,
            reserved: [0u8; 8],
        }
    }

    pub fn to_bytes(&self) -> [u8; HEADER_LEN] {
        let mut out = [0u8; HEADER_LEN];
        out[0..4].copy_from_slice(&self.magic);
        out[4] = self.version;
        out[5] = self.header_len;
        out[6] = self.flags;
        out[7] = self.arch;
        write_u32(&mut out, 8, self.cap_bitmap);
        write_u16(&mut out, 12, self.payload_len);
        write_u16(&mut out, 14, self.manifest_len);
        out[16..24].copy_from_slice(&self.reserved);
        out
    }

    pub fn from_bytes(bytes: &[u8]) -> Result<Self, ContractError> {
        if bytes.len() != HEADER_LEN {
            return Err(ContractError::InvalidLength);
        }
        let mut reserved = [0u8; 8];
        reserved.copy_from_slice(&bytes[16..24]);
        let header = Self {
            magic: bytes[0..4].try_into().unwrap(),
            version: bytes[4],
            header_len: bytes[5],
            flags: bytes[6],
            arch: bytes[7],
            cap_bitmap: read_u32(bytes, 8),
            payload_len: read_u16(bytes, 12),
            manifest_len: read_u16(bytes, 14),
            reserved,
        };
        header.validate()?;
        Ok(header)
    }

    pub fn validate(&self) -> Result<(), ContractError> {
        if self.magic != MAGIC_HEADER {
            return Err(ContractError::InvalidMagic);
        }
        if self.version != 0x06 {
            return Err(ContractError::InvalidVersion);
        }
        if self.header_len as usize != HEADER_LEN {
            return Err(ContractError::InvalidLength);
        }
        if self.payload_len as usize != PAYLOAD_LEN {
            return Err(ContractError::InvalidLength);
        }
        if self.manifest_len as usize != MANIFEST_LEN {
            return Err(ContractError::InvalidLength);
        }
        if self.reserved != [0u8; 8] {
            return Err(ContractError::ReservedFieldNonZero);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MuscleManifestV1 {
    pub magic: [u8; 4],
    pub version: u8,
    pub flags: u8,
    pub arch: u8,
    pub abi: u8,
    pub code_offset: u16,
    pub code_size: u16,
    pub entrypoint: u32,
    pub memory_pages: u16,
    pub stack_pages: u8,
    pub heap_pages: u8,
    pub update_budget: u16,
    pub io_budget: u16,
    pub capability_bitmap: u32,
    pub muscle_id: [u8; 32],
    pub muscle_version: u64,
    pub code_hash: [u8; 32],
    pub llm_profile_off: u16,
    pub llm_profile_len: u16,
    pub organelle_off: u16,
    pub organelle_len: u16,
    pub reserved: [u8; 148],
}

impl MuscleManifestV1 {
    pub fn new(
        arch: u8,
        abi: u8,
        code_size: u16,
        entrypoint: u32,
        memory_pages: u16,
        stack_pages: u8,
        heap_pages: u8,
        update_budget: u16,
        io_budget: u16,
        capability_bitmap: u32,
        muscle_id: [u8; 32],
        muscle_version: u64,
    ) -> Self {
        Self {
            magic: MAGIC_MANIFEST,
            version: 0x01,
            flags: 0,
            arch,
            abi,
            code_offset: MANIFEST_LEN as u16,
            code_size,
            entrypoint,
            memory_pages,
            stack_pages,
            heap_pages,
            update_budget,
            io_budget,
            capability_bitmap,
            muscle_id,
            muscle_version,
            code_hash: [0u8; 32],
            llm_profile_off: 0,
            llm_profile_len: 0,
            organelle_off: 0,
            organelle_len: 0,
            reserved: [0u8; 148],
        }
    }

    pub fn with_code_hash(mut self, code: &[u8]) -> Self {
        let hash = blake3::hash(code);
        self.code_hash.copy_from_slice(hash.as_bytes());
        self
    }

    pub fn to_bytes(&self) -> [u8; MANIFEST_LEN] {
        let mut out = [0u8; MANIFEST_LEN];
        out[0..4].copy_from_slice(&self.magic);
        out[4] = self.version;
        out[5] = self.flags;
        out[6] = self.arch;
        out[7] = self.abi;
        write_u16(&mut out, 8, self.code_offset);
        write_u16(&mut out, 10, self.code_size);
        write_u32(&mut out, 12, self.entrypoint);
        write_u16(&mut out, 16, self.memory_pages);
        out[18] = self.stack_pages;
        out[19] = self.heap_pages;
        write_u16(&mut out, 20, self.update_budget);
        write_u16(&mut out, 22, self.io_budget);
        write_u32(&mut out, 24, self.capability_bitmap);
        out[28..60].copy_from_slice(&self.muscle_id);
        write_u64(&mut out, 60, self.muscle_version);
        out[68..100].copy_from_slice(&self.code_hash);
        write_u16(&mut out, 100, self.llm_profile_off);
        write_u16(&mut out, 102, self.llm_profile_len);
        write_u16(&mut out, 104, self.organelle_off);
        write_u16(&mut out, 106, self.organelle_len);
        out[108..256].copy_from_slice(&self.reserved);
        out
    }

    pub fn from_bytes(bytes: &[u8]) -> Result<Self, ContractError> {
        if bytes.len() != MANIFEST_LEN {
            return Err(ContractError::InvalidLength);
        }
        let mut muscle_id = [0u8; 32];
        muscle_id.copy_from_slice(&bytes[28..60]);
        let mut code_hash = [0u8; 32];
        code_hash.copy_from_slice(&bytes[68..100]);
        let mut reserved = [0u8; 148];
        reserved.copy_from_slice(&bytes[108..256]);
        let manifest = Self {
            magic: bytes[0..4].try_into().unwrap(),
            version: bytes[4],
            flags: bytes[5],
            arch: bytes[6],
            abi: bytes[7],
            code_offset: read_u16(bytes, 8),
            code_size: read_u16(bytes, 10),
            entrypoint: read_u32(bytes, 12),
            memory_pages: read_u16(bytes, 16),
            stack_pages: bytes[18],
            heap_pages: bytes[19],
            update_budget: read_u16(bytes, 20),
            io_budget: read_u16(bytes, 22),
            capability_bitmap: read_u32(bytes, 24),
            muscle_id,
            muscle_version: read_u64(bytes, 60),
            code_hash,
            llm_profile_off: read_u16(bytes, 100),
            llm_profile_len: read_u16(bytes, 102),
            organelle_off: read_u16(bytes, 104),
            organelle_len: read_u16(bytes, 106),
            reserved,
        };
        manifest.validate()?;
        Ok(manifest)
    }

    pub fn validate(&self) -> Result<(), ContractError> {
        if self.magic != MAGIC_MANIFEST {
            return Err(ContractError::InvalidMagic);
        }
        if self.version != 0x01 {
            return Err(ContractError::InvalidVersion);
        }
        if self.code_offset as usize != MANIFEST_LEN {
            return Err(ContractError::InvalidLength);
        }
        if self.code_size as usize > PAYLOAD_LEN - MANIFEST_LEN {
            return Err(ContractError::InvalidLength);
        }
        if self.entrypoint as usize >= self.code_size as usize {
            return Err(ContractError::InvalidEntryPoint);
        }
        if self.reserved != [0u8; 148] {
            return Err(ContractError::ReservedFieldNonZero);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContractError {
    InvalidLength,
    InvalidMagic,
    InvalidVersion,
    InvalidEntryPoint,
    ReservedFieldNonZero,
    CryptoError,
    ManifestMismatch,
}

pub fn build_payload(
    manifest: &MuscleManifestV1,
    code: &[u8],
) -> Result<[u8; PAYLOAD_LEN], ContractError> {
    if code.len() > PAYLOAD_LEN - MANIFEST_LEN {
        return Err(ContractError::InvalidLength);
    }
    if manifest.code_size as usize != code.len() {
        return Err(ContractError::InvalidLength);
    }

    let manifest = manifest.with_code_hash(code);
    let mut payload = [0u8; PAYLOAD_LEN];
    payload[0..MANIFEST_LEN].copy_from_slice(&manifest.to_bytes());
    payload[MANIFEST_LEN..MANIFEST_LEN + code.len()].copy_from_slice(code);
    Ok(payload)
}

pub fn parse_manifest(payload: &[u8; PAYLOAD_LEN]) -> Result<MuscleManifestV1, ContractError> {
    MuscleManifestV1::from_bytes(&payload[0..MANIFEST_LEN])
}

pub fn verify_code_hash(
    manifest: &MuscleManifestV1,
    payload: &[u8; PAYLOAD_LEN],
) -> Result<(), ContractError> {
    let start = MANIFEST_LEN;
    let end = MANIFEST_LEN + manifest.code_size as usize;
    let hash = blake3::hash(&payload[start..end]);
    if hash.as_bytes() != &manifest.code_hash {
        return Err(ContractError::ManifestMismatch);
    }
    Ok(())
}

pub fn seal_with_nonce(
    master_key: &[u8; 32],
    header: &EaM6Header,
    nonce: &[u8; NONCE_LEN],
    payload: &[u8; PAYLOAD_LEN],
) -> Result<[u8; BLOB_LEN], ContractError> {
    header.validate()?;

    let header_bytes = header.to_bytes();
    let key = derive_key(master_key, &header_bytes, nonce);
    let cipher = ChaCha20Poly1305::new((&key).into());

    let mut ciphertext = [0u8; PAYLOAD_LEN];
    ciphertext.copy_from_slice(payload);
    let tag = cipher
        .encrypt_in_place_detached(
            Nonce::from_slice(&nonce[..AEAD_NONCE_LEN]),
            &header_bytes,
            &mut ciphertext,
        )
        .map_err(|_| ContractError::CryptoError)?;

    let mut blob = [0u8; BLOB_LEN];
    blob[0..HEADER_LEN].copy_from_slice(&header_bytes);
    blob[HEADER_LEN..HEADER_LEN + NONCE_LEN].copy_from_slice(nonce);
    blob[HEADER_LEN + NONCE_LEN..HEADER_LEN + NONCE_LEN + PAYLOAD_LEN]
        .copy_from_slice(&ciphertext);
    blob[HEADER_LEN + NONCE_LEN + PAYLOAD_LEN..]
        .copy_from_slice(tag.as_slice());
    Ok(blob)
}

pub fn open(
    master_key: &[u8; 32],
    blob: &[u8; BLOB_LEN],
) -> Result<(EaM6Header, [u8; PAYLOAD_LEN]), ContractError> {
    let header = EaM6Header::from_bytes(&blob[0..HEADER_LEN])?;
    let nonce = &blob[HEADER_LEN..HEADER_LEN + NONCE_LEN];
    let ciphertext = &blob[HEADER_LEN + NONCE_LEN..HEADER_LEN + NONCE_LEN + PAYLOAD_LEN];
    let tag = Tag::from_slice(&blob[HEADER_LEN + NONCE_LEN + PAYLOAD_LEN..]);

    let header_bytes = header.to_bytes();
    let key = derive_key(master_key, &header_bytes, nonce);
    let cipher = ChaCha20Poly1305::new((&key).into());

    let mut payload_out = [0u8; PAYLOAD_LEN];
    payload_out.copy_from_slice(ciphertext);
    cipher
        .decrypt_in_place_detached(
            Nonce::from_slice(&nonce[..AEAD_NONCE_LEN]),
            &header_bytes,
            &mut payload_out,
            tag,
        )
        .map_err(|_| ContractError::CryptoError)?;

    Ok((header, payload_out))
}

fn derive_key(master_key: &[u8; 32], header: &[u8; HEADER_LEN], nonce: &[u8]) -> [u8; 32] {
    let mut hasher = Hasher::new_keyed(master_key);
    hasher.update(KEY_CONTEXT);
    hasher.update(header);
    hasher.update(nonce);
    *hasher.finalize().as_bytes()
}

fn write_u16(buf: &mut [u8], offset: usize, value: u16) {
    buf[offset..offset + 2].copy_from_slice(&value.to_le_bytes());
}

fn write_u32(buf: &mut [u8], offset: usize, value: u32) {
    buf[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
}

fn write_u64(buf: &mut [u8], offset: usize, value: u64) {
    buf[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
}

fn read_u16(buf: &[u8], offset: usize) -> u16 {
    u16::from_le_bytes(buf[offset..offset + 2].try_into().unwrap())
}

fn read_u32(buf: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(buf[offset..offset + 4].try_into().unwrap())
}

fn read_u64(buf: &[u8], offset: usize) -> u64 {
    u64::from_le_bytes(buf[offset..offset + 8].try_into().unwrap())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn header_roundtrip() {
        let header = EaM6Header::new(1, 0xAABBCCDD, 0);
        let bytes = header.to_bytes();
        let parsed = EaM6Header::from_bytes(&bytes).unwrap();
        assert_eq!(header, parsed);
    }

    #[test]
    fn manifest_roundtrip() {
        let manifest = MuscleManifestV1::new(
            1,
            0,
            32,
            0,
            2,
            1,
            1,
            8,
            16,
            0x01,
            [0x11; 32],
            1,
        );
        let bytes = manifest.to_bytes();
        let parsed = MuscleManifestV1::from_bytes(&bytes).unwrap();
        assert_eq!(manifest, parsed);
    }

    #[test]
    fn seal_open_roundtrip() {
        let master_key = [0x42; 32];
        let header = EaM6Header::new(1, 0x01, FLAG_DETERMINISTIC_NONCE);
        let mut code = [0u8; 64];
        for (i, byte) in code.iter_mut().enumerate() {
            *byte = i as u8;
        }
        let manifest = MuscleManifestV1::new(
            1,
            0,
            code.len() as u16,
            0,
            2,
            1,
            1,
            8,
            16,
            0x01,
            [0x22; 32],
            7,
        );
        let payload = build_payload(&manifest, &code).unwrap();
        let nonce = [0xAA; NONCE_LEN];
        let blob = seal_with_nonce(&master_key, &header, &nonce, &payload).unwrap();
        let (parsed_header, opened_payload) = open(&master_key, &blob).unwrap();
        assert_eq!(parsed_header, header);
        assert_eq!(opened_payload, payload);
        let parsed_manifest = parse_manifest(&opened_payload).unwrap();
        verify_code_hash(&parsed_manifest, &opened_payload).unwrap();
    }
}
