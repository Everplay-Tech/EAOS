//! Biological primitives and types for the Eä ecosystem
//!
//! Defines the fundamental biological structures that make up
//! the cellular architecture of Eä muscles.

use core::fmt;
use zeroize::Zeroize;

/// Salt for muscle derivation - ensures unique encryption per muscle
#[derive(Clone, PartialEq, Eq, Hash, Zeroize)]
#[zeroize(drop)]
pub struct MuscleSalt([u8; 16]);

impl MuscleSalt {
    /// Create a new muscle salt from bytes
    pub fn new(bytes: [u8; 16]) -> Self {
        Self(bytes)
    }

    /// Generate a random muscle salt
    pub fn random<R: rand_core::RngCore + rand_core::CryptoRng>(rng: &mut R) -> Self {
        let mut bytes = [0u8; 16];
        rng.fill_bytes(&mut bytes);
        Self(bytes)
    }

    /// Get the salt as bytes
    pub fn as_bytes(&self) -> &[u8; 16] {
        &self.0
    }
}

impl AsRef<[u8]> for MuscleSalt {
    fn as_ref(&self) -> &[u8] {
        &self.0
    }
}

impl fmt::Debug for MuscleSalt {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "MuscleSalt({})", hex::encode(self.0))
    }
}

/// Sealed blob containing an encrypted muscle
#[derive(Clone, Zeroize)]
#[zeroize(drop)]
pub struct SealedBlob {
    /// The encrypted payload
    pub payload: alloc::vec::Vec<u8>,
    /// The salt used for this specific muscle
    pub salt: MuscleSalt,
    /// Version information
    pub version: u32,
}

impl SealedBlob {
    /// Create a new sealed blob
    pub fn new(payload: alloc::vec::Vec<u8>, salt: MuscleSalt, version: u32) -> Self {
        Self {
            payload,
            salt,
            version,
        }
    }

    /// Get the salt for this blob
    pub fn salt(&self) -> &MuscleSalt {
        &self.salt
    }

    /// Get the version
    pub fn version(&self) -> u32 {
        self.version
    }
}

impl fmt::Debug for SealedBlob {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "SealedBlob {{ version: {}, salt: {}, payload: {} bytes }}",
            self.version,
            hex::encode(self.salt.0),
            self.payload.len()
        )
    }
}

/// Key for deriving successor muscles
#[derive(Clone, PartialEq, Eq, Zeroize)]
#[zeroize(drop)]
pub struct SuccessorKey([u8; 32]);

impl SuccessorKey {
    /// Create a new successor key from bytes
    pub fn new(bytes: [u8; 32]) -> Self {
        Self(bytes)
    }

    /// Generate a random successor key
    pub fn random<R: rand_core::RngCore + rand_core::CryptoRng>(rng: &mut R) -> Self {
        let mut bytes = [0u8; 32];
        rng.fill_bytes(&mut bytes);
        Self(bytes)
    }

    /// Get the key as bytes
    pub fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }
}

impl AsRef<[u8]> for SuccessorKey {
    fn as_ref(&self) -> &[u8] {
        &self.0
    }
}

impl fmt::Debug for SuccessorKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "SuccessorKey({}...)", hex::encode(&self.0[..8]))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand_core::{CryptoRng, RngCore};

    struct TestRng(u64);

    impl TestRng {
        fn next_state(&mut self) -> u64 {
            let mut x = self.0;
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            self.0 = x;
            x
        }
    }

    impl RngCore for TestRng {
        fn next_u32(&mut self) -> u32 {
            self.next_state() as u32
        }

        fn next_u64(&mut self) -> u64 {
            self.next_state()
        }

        fn fill_bytes(&mut self, dest: &mut [u8]) {
            let mut offset = 0;
            while offset < dest.len() {
                let chunk = self.next_u64().to_le_bytes();
                let take = core::cmp::min(8, dest.len() - offset);
                dest[offset..offset + take].copy_from_slice(&chunk[..take]);
                offset += take;
            }
        }

        fn try_fill_bytes(&mut self, dest: &mut [u8]) -> Result<(), rand_core::Error> {
            self.fill_bytes(dest);
            Ok(())
        }
    }

    impl CryptoRng for TestRng {}

    #[test]
    fn test_muscle_salt_operations() {
        let mut rng = TestRng(0xA11CE5EED);
        let salt1 = MuscleSalt::random(&mut rng);
        let salt2 = MuscleSalt::random(&mut rng);

        assert_ne!(salt1.as_bytes(), salt2.as_bytes());
        assert_eq!(salt1.as_bytes().len(), 16);
    }

    #[test]
    fn test_successor_key_operations() {
        let mut rng = TestRng(0x5EED5EED);
        let key1 = SuccessorKey::random(&mut rng);
        let key2 = SuccessorKey::random(&mut rng);

        assert_ne!(key1.as_bytes(), key2.as_bytes());
        assert_eq!(key1.as_bytes().len(), 32);
    }

    #[test]
    fn test_sealed_blob_creation() {
        let mut rng = TestRng(0xC0FFEE);
        let salt = MuscleSalt::random(&mut rng);
        let payload = alloc::vec![1, 2, 3, 4, 5];
        let blob = SealedBlob::new(payload.clone(), salt.clone(), 1);

        assert_eq!(blob.version(), 1);
        assert_eq!(blob.salt(), &salt);
        assert_eq!(blob.payload, payload);
    }
}
