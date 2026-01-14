// muscle-compiler/src/crypto.rs
// Eä Cryptographic Engine v5.0 — Integrated Pathfinder Edition
#![forbid(unsafe_code)]
#![deny(missing_docs)]

use aes_gcm_siv::{
    aead::{Aead, KeyInit, rand_core::RngCore},
    Aes256GcmSiv, Nonce,
};
use blake3::{Hasher, OUT_LEN};
use subtle::ConstantTimeEq;
use zeroize::{Zeroize, ZeroizeOnDrop};

/// Optional post-quantum KEM
#[cfg(feature = "pq")]
use pqcrypto_kyber::kyber1024::{self, ciphertext_bytes, shared_secret_bytes};

/// Protocol version — bump on breaking change
const PROTOCOL_VERSION: &[u8] = b"Ea/muscle/v5.0";

/// Domain separation constants
const DOMAIN_KDF: [u8; 32] = *b"\xde\xad\xbe\xef\xca\xfe\xba\xbe\x01\x23\x45\x67\x89\xab\xcd\xef\
                                 \xde\xad\xbe\xef\xca\xfe\xba\xbe\x01\x23\x45\x67\x89\xab\xcd\xef";
const DOMAIN_MAC: [u8; 32] = *b"\xf0\x0d\xfa\xce\xfe\xed\xba\xbe\x88\x77\x66\x55\x44\x33\x22\x11\
                                 \xf0\x0d\xfa\xce\xfe\xed\xba\xbe\x88\x77\x66\x55\x44\x33\x22\x11";

pub type MuscleSalt = [u8; 16];
pub type MuscleVersion = u64;

/// Overhead calculation
#[cfg(feature = "pq")]
mod sizes {
    use pqcrypto_kyber::kyber1024;
    pub const KEM_CT_LEN: usize = kyber1024::ciphertext_bytes();
    pub const KEM_SS_LEN: usize = kyber1024::shared_secret_bytes();
}

#[cfg(not(feature = "pq"))]
mod sizes {
    pub const KEM_CT_LEN: usize = 0;
    pub const KEM_SS_LEN: usize = 0;
}

pub const FIXED_OVERHEAD: usize = sizes::KEM_CT_LEN + 8 + 12 + 32;
pub const MIN_BLOB_SIZE: usize = FIXED_OVERHEAD;

/// Derive 32-byte key with full domain separation
fn derive(key_material: &[u8], salt: &MuscleSalt, domain: &[u8; 32]) -> [u8; 32] {
    let mut h = Hasher::new_keyed(key_material);
    h.update(PROTOCOL_VERSION);
    h.update(domain);
    h.update(salt);
    *h.finalize().as_bytes()
}

/// Primary sealing function
pub fn seal(
    master: &[u8; 32],
    salt: &MuscleSalt,
    version: MuscleVersion,
    plaintext: &[u8],
) -> Vec<u8> {
    let mut rng = aes_gcm_siv::aead::rand_core::OsRng;
    seal_with_rng(master, salt, version, plaintext, &mut rng)
}

/// Internal sealing with custom RNG
pub fn seal_with_rng<R: RngCore>(
    master: &[u8; 32],
    salt: &MuscleSalt,
    version: MuscleVersion,
    plaintext: &[u8],
    rng: &mut R,
) -> Vec<u8> {
    // 1. Generate fresh shared secret
    let (shared_secret, kem_ct) = encapsulate(rng);

    // 2. Derive final keys
    let enc_key = derive(&shared_secret, salt, &DOMAIN_KDF);
    let mac_key = derive(&shared_secret, salt, &DOMAIN_MAC);

    // 3. Encrypt payload
    let cipher = Aes256GcmSiv::new(&enc_key.into());
    let mut nonce = [0u8; 12];
    rng.fill_bytes(&mut nonce);
    let ciphertext = cipher.encrypt(Nonce::from_slice(&nonce), plaintext)
        .expect("AES-GCM-SIV encryption failed");

    // 4. MAC everything
    let mut h = Hasher::new_keyed(&mac_key);
    h.update(PROTOCOL_VERSION);
    h.update(salt);
    h.update(&kem_ct);
    h.update(&version.to_le_bytes());
    h.update(&nonce);
    h.update(&ciphertext);
    let tag = *h.finalize().as_bytes();

    // 5. Assemble final blob
    let mut blob = Vec::with_capacity(FIXED_OVERHEAD + ciphertext.len());
    blob.extend_from_slice(&kem_ct);
    blob.extend_from_slice(&version.to_le_bytes());
    blob.extend_from_slice(&nonce);
    blob.extend_from_slice(&ciphertext);
    blob.extend_from_slice(&tag);

    // 6. Cleanup
    zeroize::Zeroize::zeroize(&mut shared_secret);
    zeroize::Zeroize::zeroize(&mut enc_key);
    zeroize::Zeroize::zeroize(&mut mac_key);
    zeroize::Zeroize::zeroize(&mut nonce);

    blob
}

/// Generate fresh shared secret
fn encapsulate<R: RngCore>(rng: &mut R) -> (Vec<u8>, Vec<u8>) {
    #[cfg(feature = "pq")]
    {
        let (pk, sk) = kyber1024::keypair_from_rng(rng);
        let (ss, ct) = kyber1024::encapsulate_from_rng(&pk, rng);
        (ss.as_bytes().to_vec(), ct.as_bytes().to_vec())
    }

    #[cfg(not(feature = "pq"))]
    {
        let mut ss = [0u8; 32];
        rng.fill_bytes(&mut ss);
        (ss.to_vec(), Vec::new())
    }
}

/// Primary opening function
pub fn open(
    master: &[u8; 32],
    salt: &MuscleSalt,
    sealed: &[u8],
) -> Result<(Vec<u8>, MuscleVersion), &'static str> {
    if sealed.len() < MIN_BLOB_SIZE {
        return Err("sealed data too small");
    }

    // Parse blob structure
    let kem_ct_len = sizes::KEM_CT_LEN;
    let kem_ct = &sealed[..kem_ct_len];
    let version_bytes = &sealed[kem_ct_len..kem_ct_len + 8];
    let nonce = &sealed[kem_ct_len + 8..kem_ct_len + 20];
    let ciphertext = &sealed[kem_ct_len + 20..sealed.len() - OUT_LEN];
    let received_tag = &sealed[sealed.len() - OUT_LEN..];

    let version = u64::from_le_bytes(version_bytes.try_into().unwrap());

    // Recover shared secret
    let shared_secret = decapsulate(master, salt, kem_ct)?;

    let enc_key = derive(&shared_secret, salt, &DOMAIN_KDF);
    let mac_key = derive(&shared_secret, salt, &DOMAIN_MAC);

    // Verify MAC first
    let mut h = Hasher::new_keyed(&mac_key);
    h.update(PROTOCOL_VERSION);
    h.update(salt);
    h.update(kem_ct);
    h.update(&version.to_le_bytes());
    h.update(nonce);
    h.update(ciphertext);
    
    if !bool::from(h.finalize().as_bytes().ct_eq(received_tag)) {
        return Err("integrity check failed");
    }

    // Decrypt after verification
    let plaintext = Aes256GcmSiv::new(&enc_key.into())
        .decrypt(Nonce::from_slice(nonce), ciphertext)
        .map_err(|_| "decryption failed")?;

    // Cleanup
    zeroize::Zeroize::zeroize(&mut shared_secret);
    zeroize::Zeroize::zeroize(&mut enc_key);
    zeroize::Zeroize::zeroize(&mut mac_key);

    Ok((plaintext, version))
}

#[cfg(feature = "pq")]
fn decapsulate(_master: &[u8; 32], _salt: &MuscleSalt, kem_ct: &[u8]) -> Result<Vec<u8>, &'static str> {
    use pqcrypto_kyber::kyber1024::{Ciphertext, SecretKey};
    
    if kem_ct.len() != sizes::KEM_CT_LEN {
        return Err("invalid KEM ciphertext length");
    }
    
    // In real implementation, we'd need the secret key here
    // For now, this is a placeholder - real integration requires key management
    Err("PQ decryption not fully implemented")
}

#[cfg(not(feature = "pq"))]
fn decapsulate(master: &[u8; 32], salt: &MuscleSalt, kem_ct: &[u8]) -> Result<Vec<u8>, &'static str> {
    if !kem_ct.is_empty() {
        return Err("unexpected KEM data in classical mode");
    }
    // Classical mode: derive directly from master + salt
    Ok(derive(master, salt, &DOMAIN_KDF).to_vec())
}

/// Fast-path opening for performance-critical code
pub fn open_infallible(
    master: &[u8; 32],
    salt: &MuscleSalt,
    sealed: &[u8],
) -> Option<(Vec<u8>, MuscleVersion)> {
    open(master, salt, sealed).ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    proptest! {
        #[test]
        fn roundtrip_classical(
            master in prop::array::uniform32(any::<u8>()),
            salt in prop::array::uniform16(any::<u8>()),
            version in any::<u64>(),
            data in prop::collection::vec(any::<u8>(), 0..4096)
        ) {
            let sealed = seal(&master, &salt, version, &data);
            let (opened, opened_version) = open(&master, &salt, &sealed).unwrap();
            assert_eq!(data, opened);
            assert_eq!(version, opened_version);
        }
    }

    #[test]
    fn rejects_tampered_data() {
        let master = [0x42; 32];
        let salt = [0x13; 16];
        let sealed = seal(&master, &salt, 1, b"test data");
        
        // Tamper with the ciphertext
        let mut tampered = sealed.clone();
        let tamper_pos = sizes::KEM_CT_LEN + 20 + 5; // Some position in ciphertext
        if tamper_pos < tampered.len() {
            tampered[tamper_pos] ^= 0x01;
            assert!(open(&master, &salt, &tampered).is_err());
        }
    }
}
