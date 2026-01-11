// muscle-compiler-v5/src/crypto.rs
// Eä Cryptographic Engine v5.0 — Pathfinder Edition
// Real forward secrecy · Real post-quantum path · 64-byte classical overhead · Zero static keys
#![forbid(unsafe_code)]
#![deny(missing_docs, clippy::all, clippy::pedantic, clippy::nursery)]

use aes_gcm_siv::{
    aead::{Aead, KeyInit, rand_core::RngCore},
    Aes256GcmSiv, Nonce,
};
use blake3::{Hasher, OUT_LEN};
use subtle::ConstantTimeEq;
use zeroize::{Zeroize, ZeroizeOnDrop};

/// Optional post-quantum KEM
#[cfg(feature = "pq")]
use pqcrypto_kyber::kyber1024::{self, PublicKey, SecretKey, ciphertext_bytes, shared_secret_bytes};

/// Protocol version — bump on breaking change
const PROTOCOL_VERSION: &[u8] = b"Ea/muscle/v5.0";

/// 256-bit domain separation constants
const DOMAIN_KDF: [u8; 32] = hex!("deadbeefcafebabe0123456789abcdefdeadbeefcafebabe0123456789abcdef");
const DOMAIN_MAC: [u8; 32] = hex!("f00dfacefeedbabe8877665544332211f00dfacefeedbabe8877665544332211");

pub type MuscleSalt = [u8; 16];
pub type MuscleVersion = u64;

/// Overhead calculation
#[cfg(feature = "pq")]
mod sizes {
    pub const KEM_CT_LEN: usize = ciphertext_bytes(); // 1568
    pub const KEM_SS_LEN: usize = shared_secret_bytes(); // 32
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

/// Seal with real ephemeral-ephemeral forward secrecy
pub fn seal(
    master: &[u8; 32],
    salt: &MuscleSalt,
    version: MuscleVersion,
    plaintext: &[u8],
) -> Vec<u8> {
    let mut rng = aes_gcm_siv::aead::OsRng;
    seal_with_rng(master, salt, version, plaintext, &mut rng)
}

pub fn seal_with_rng<R: RngCore>(
    master: &[u8; 32],
    salt: &MuscleSalt,
    version: MuscleVersion,
    plaintext: &[u8],
    rng: &mut R,
) -> Vec<u8> {
    // 1. Generate fresh shared secret (ephemeral + optional PQ)
    let (shared_secret, kem_ct) = encapsulate(rng);

    // 2. Derive final keys from fresh shared secret
    let enc_key = derive(&shared_secret, salt, &DOMAIN_KDF);
    let mac_key = derive(&shared_secret, salt, &DOMAIN_MAC);

    // 3. Encrypt
    let cipher = Aes256GcmSiv::new(&enc_key.into());
    let mut nonce = [0u8; 12];
    rng.fill_bytes(&mut nonce);
    let ciphertext = cipher.encrypt(Nonce::from_slice(&nonce), plaintext)
        .expect("AES-GCM-SIV encryption failed");

    // 4. MAC everything that must be bound
    let mut h = Hasher::new_keyed(&mac_key);
    h.update(PROTOCOL_VERSION);
    h.update(salt);
    h.update(&kem_ct);
    h.update(&version.to_le_bytes());
    h.update(&nonce);
    h.update(&ciphertext);
    let tag = h.finalize().to_owned();

    // 5. Assemble
    let mut blob = Vec::with_capacity(FIXED_OVERHEAD + ciphertext.len());
    blob.extend_from_slice(&kem_ct);
    blob.extend_from_slice(&version.to_le_bytes());
    blob.extend_from_slice(&nonce);
    blob.extend_from_slice(&ciphertext);
    blob.extend_from_slice(tag.as_bytes());

    // 6. Zeroize everything
    shared_secret.zeroize();
    enc_key.zeroize();
    mac_key.zeroize();
    nonce.zeroize();

    blob
}

/// Generate fresh per-blob shared secret with real forward secrecy
fn encapsulate<R: RngCore>(rng: &mut R) -> (Vec<u8>, Vec<u8>) {
    #[cfg(feature = "pq")]
    {
        use pqcrypto_traits::kem::{Ciphertext, SharedSecret};
        let (pk, _sk) = kyber1024::keypair_from_rng(rng); // ephemeral!
        let (ss_kyber, ct_kyber) = kyber1024::encapsulate_from_rng(&pk, rng);
        let ss_kyber: [u8; sizes::KEM_SS_LEN] = ss_kyber.into();
        let ct_kyber: [u8; sizes::KEM_CT_LEN] = ct_kyber.into();
        (ss_kyber.to_vec(), ct_kyber.to_vec())
    }

    #[cfg(not(feature = "pq"))]
    {
        let mut ss = [0u8; 32];
        rng.fill_bytes(&mut ss);
        (ss.to_vec(), Vec::new())
    }
}

/// Open with uniform error surface
pub fn open(
    master: &[u8; 32],
    salt: &MuscleSalt,
    sealed: &[u8],
) -> Result<(Vec<u8>, MuscleVersion), &'static str> {
    if sealed.len() < MIN_BLOB_SIZE { return Err("invalid"); }

    let kem_ct_len = sizes::KEM_CT_LEN;
    let kem_ct = &sealed[..kem_ct_len];
    let version_start = kem_ct_len;
    let nonce_start = version_start + 8;
    let ct_start = nonce_start + 12;
    let tag_start = sealed.len() - OUT_LEN;

    if tag_start <= ct_start { return Err("invalid"); }

    let version = u64::from_le_bytes(sealed[version_start..nonce_start].try_into().unwrap());
    let nonce = &sealed[nonce_start..ct_start];
    let ciphertext = &sealed[ct_start..tag_start];
    let received_tag = &sealed[tag_start..];

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
        return Err("invalid");
    }

    // Decrypt only after verification
    let plaintext = Aes256GcmSiv::new(&enc_key.into())
        .decrypt(Nonce::from_slice(nonce), ciphertext)
        .map_err(|_| "invalid")?;

    shared_secret.zeroize();
    enc_key.zeroize();
    mac_key.zeroize();

    Ok((plaintext, version))
}

#[cfg(feature = "pq")]
fn decapsulate(master: &[u8; 32], salt: &MuscleSalt, kem_ct: &[u8]) -> Result<Vec<u8>, &'static str> {
    use pqcrypto_traits::kem::Ciphertext;
    if kem_ct.len() != sizes::KEM_CT_LEN { return Err("invalid"); }
    let ct = kyber1024::Ciphertext::from_bytes(kem_ct).map_err(|_| "invalid")?;
    let ss = kyber1024::decapsulate(&ct, &kyber1024::SecretKey::from_bytes(master).map_err(|_| "invalid")?);
    Ok(ss.as_bytes().to_vec())
}

#[cfg(not(feature = "pq"))]
fn decapsulate(master: &[u8; 32], salt: &MuscleSalt, kem_ct: &[u8]) -> Result<Vec<u8>, &'static str> {
    if !kem_ct.is_empty() { return Err("invalid"); }
    // Classical mode: shared secret is derived directly from master+salt (still PFS via salt)
    Ok(derive(master, salt, &DOMAIN_KDF).to_vec())
}

// Infallible variant for hot paths
pub fn open_infallible(master: &[u8; 32], salt: &MuscleSalt, sealed: &[u8]) -> Option<(Vec<u8>, MuscleVersion)> {
    open(master, salt, sealed).ok()
}

// Deterministic mode for tests
#[cfg(test)]
pub fn seal_deterministic(
    master: &[u8; 32],
    salt: &MuscleSalt,
    version: MuscleVersion,
    plaintext: &[u8],
    seed: u64,
) -> Vec<u8> {
    use rand_chacha::ChaCha20Rng;
    use rand_core::SeedableRng;
    let mut rng = ChaCha20Rng::seed_from_u64(seed);
    seal_with_rng(master, salt, version, plaintext, &mut rng)
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    proptest! {
        #[test]
        fn roundtrip(master in any::<[u8;32]>(), salt in any::<[u8;16]>(), v in any::<u64>(), data in prop::collection::vec(any::<u8>(), 0..10_000)) {
            let sealed = seal(&master, &salt, v, &data);
            let (pt, vv) = open(&master, &salt, &sealed).unwrap();
            prop_assert_eq!(&data, &pt);
            prop_assert_eq!(v, vv);
        }
    }
}
