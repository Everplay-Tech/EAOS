use std::collections::{HashMap, HashSet};
use std::sync::Mutex;

use thiserror::Error;

#[derive(Debug, Error)]
pub enum EntropyError {
    #[error("nonce has been used previously for key {0}")]
    NonceReuse(String),
    #[error("salt has been used previously for key {0}")]
    SaltReuse(String),
}

pub trait NonceManager: Send + Sync {
    fn vouch_unique(&self, key_id: &str, nonce: &[u8]) -> bool;
}

#[derive(Debug, Clone)]
pub struct EntropyMaterial {
    pub salt: Vec<u8>,
    pub nonce: Vec<u8>,
    pub deterministic: bool,
}

#[derive(Debug, Clone)]
pub enum EntropyRequest {
    Random {
        salt_len: usize,
        nonce_len: usize,
    },
    Provided {
        salt: Vec<u8>,
        nonce: Vec<u8>,
        manager: Option<std::sync::Arc<dyn NonceManager>>,
    },
}

impl EntropyRequest {
    pub fn random() -> Self {
        Self::Random {
            salt_len: 32,
            nonce_len: 12,
        }
    }
}

#[derive(Default)]
pub struct EntropyStrategy {
    used_nonces: Mutex<HashMap<String, HashSet<Vec<u8>>>>,
    used_salts: Mutex<HashMap<String, HashSet<Vec<u8>>>>,
}

impl EntropyStrategy {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn material_for(
        &self,
        key_id: &str,
        request: EntropyRequest,
    ) -> Result<EntropyMaterial, EntropyError> {
        match request {
            EntropyRequest::Random {
                salt_len,
                nonce_len,
            } => {
                let salt = random_bytes(salt_len);
                let nonce = random_bytes(nonce_len);
                self.record(key_id, &salt, &nonce);
                Ok(EntropyMaterial {
                    salt,
                    nonce,
                    deterministic: false,
                })
            }
            EntropyRequest::Provided {
                salt,
                nonce,
                manager,
            } => {
                let mut nonce_guard = self.used_nonces.lock().unwrap();
                let mut salt_guard = self.used_salts.lock().unwrap();

                let nonce_set = nonce_guard.entry(key_id.to_string()).or_default();
                let salt_set = salt_guard.entry(key_id.to_string()).or_default();

                let nonce_seen = nonce_set.contains(&nonce);
                let salt_seen = salt_set.contains(&salt);

                let approved = manager
                    .as_ref()
                    .map(|m| m.vouch_unique(key_id, &nonce))
                    .unwrap_or(false);

                if nonce_seen && !approved {
                    return Err(EntropyError::NonceReuse(key_id.to_string()));
                }

                if salt_seen && !approved {
                    return Err(EntropyError::SaltReuse(key_id.to_string()));
                }

                nonce_set.insert(nonce.clone());
                salt_set.insert(salt.clone());

                Ok(EntropyMaterial {
                    salt,
                    nonce,
                    deterministic: true,
                })
            }
        }
    }

    fn record(&self, key_id: &str, salt: &[u8], nonce: &[u8]) {
        let mut nonce_guard = self.used_nonces.lock().unwrap();
        let mut salt_guard = self.used_salts.lock().unwrap();
        nonce_guard
            .entry(key_id.to_string())
            .or_default()
            .insert(nonce.to_vec());
        salt_guard
            .entry(key_id.to_string())
            .or_default()
            .insert(salt.to_vec());
    }
}

fn random_bytes(len: usize) -> Vec<u8> {
    let mut buf = vec![0u8; len];
    getrandom::getrandom(&mut buf).expect("randomness failure");
    buf
}
