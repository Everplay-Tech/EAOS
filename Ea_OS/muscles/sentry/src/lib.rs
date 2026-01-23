#![no_std]

extern crate muscle_contract;
use muscle_contract::sentry::{SentryOp, SentryRequest, SentryResult};
use ed25519_dalek::{SigningKey, Signer};
use spin::Mutex;

/// The guarded key (Thread Safe Mutex)
static KEY: Mutex<Option<SigningKey>> = Mutex::new(None);

/// The Sentry Gate
pub fn guard(req: SentryRequest) -> SentryResult {
    match req.op {
        SentryOp::Initialize => {
            let mut key_guard = KEY.lock();
            if key_guard.is_none() {
                // Load the key once
                *key_guard = Some(SigningKey::from_bytes(&req.payload));
                SentryResult { signature: [0; 64], status: 0 }
            } else {
                SentryResult { signature: [0; 64], status: 1 } // Already initialized
            }
        },
        SentryOp::SignHash => {
            let key_guard = KEY.lock();
            if let Some(key) = &*key_guard {
                // In a real Sentry, we would check Capabilities here
                let sig = key.sign(&req.payload);
                SentryResult {
                    signature: sig.to_bytes(),
                    status: 0,
                }
            } else {
                SentryResult { signature: [0; 64], status: 2 } // Locked
            }
        },
        _ => SentryResult { signature: [0; 64], status: 0 },
    }
}