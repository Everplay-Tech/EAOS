// muscle-compiler/src/blob.rs
// Eä Muscle Blob Format v5.0 — Compatible with Crypto Engine v5.0

use blake3::Hasher;
use crate::crypto::{MuscleSalt, MuscleVersion};

/// Final .muscle blob format
/// Structure: [header][sealed_payload]
/// Header: magic(4) + version(1) + arch(1) + name_len(1) + reserved(1) + name(name_len)
/// Sealed: output from crypto::seal()
pub fn forge(
    muscle_name: &str,
    target_arch: &str,
    sealed_payload: &[u8],
) -> Vec<u8> {
    let name_bytes = muscle_name.as_bytes();
    if name_bytes.len() > 32 {
        panic!("Muscle name too long: {}", muscle_name);
    }

    let mut blob = Vec::with_capacity(64 + sealed_payload.len());

    // Header
    blob.extend_from_slice(b"EaM5");           // Magic
    blob.push(5u8);                           // Format version
    blob.push(arch_to_code(target_arch));     // Target architecture
    blob.push(name_bytes.len() as u8);        // Name length
    blob.push(0u8);                           // Reserved
    blob.extend_from_slice(name_bytes);       // Muscle name
    blob.resize(40, 0);                       // Pad header to 40 bytes

    // Sealed payload (from crypto engine)
    blob.extend_from_slice(sealed_payload);

    // Add integrity check for the header
    let mut hasher = Hasher::new();
    hasher.update(&blob);
    let integrity_hash = hasher.finalize();
    blob.extend_from_slice(&integrity_hash.as_bytes()[..8]);

    blob
}

/// Extract components from .muscle blob
pub fn parse(blob: &[u8]) -> Result<(String, String, &[u8]), &'static str> {
    if blob.len() < 48 {
        return Err("blob too small");
    }

    // Verify magic
    if &blob[0..4] != b"EaM5" {
        return Err("invalid magic");
    }

    let format_version = blob[4];
    if format_version != 5 {
        return Err("unsupported format version");
    }

    let arch_code = blob[5];
    let name_len = blob[6] as usize;
    let _reserved = blob[7];

    if blob.len() < 40 + name_len {
        return Err("invalid name length");
    }

    let name = String::from_utf8(blob[8..8 + name_len].to_vec())
        .map_err(|_| "invalid muscle name")?;

    let arch = code_to_arch(arch_code).ok_or("unknown architecture")?;

    // Payload starts after 40-byte header
    let payload = &blob[40..blob.len() - 8];

    // Verify integrity
    let mut hasher = Hasher::new();
    hasher.update(&blob[..blob.len() - 8]);
    let computed_hash = hasher.finalize();
    let stored_hash = &blob[blob.len() - 8..];

    if computed_hash.as_bytes()[..8] != stored_hash {
        return Err("integrity check failed");
    }

    Ok((name, arch.to_string(), payload))
}

fn arch_to_code(arch: &str) -> u8 {
    match arch {
        "aarch64" => 1,
        "x86_64" => 2,
        _ => 0,
    }
}

fn code_to_arch(code: u8) -> Option<&'static str> {
    match code {
        1 => Some("aarch64"),
        2 => Some("x86_64"),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_forge_parse() {
        let name = "test_muscle";
        let arch = "aarch64";
        let payload = b"test payload";

        let blob = forge(name, arch, payload);
        let (parsed_name, parsed_arch, parsed_payload) = parse(&blob).unwrap();

        assert_eq!(name, parsed_name);
        assert_eq!(arch, parsed_arch);
        assert_eq!(payload, parsed_payload);
    }

    #[test]
    fn rejects_tampered_blob() {
        let name = "test";
        let arch = "x86_64";
        let payload = b"data";

        let mut blob = forge(name, arch, payload);
        
        // Tamper with the name length
        blob[6] = 50; // Invalid name length
        
        assert!(parse(&blob).is_err());
    }
}
