#![no_std]

extern crate muscle_contract;
use muscle_contract::sentry::{SentryOp, SentryRequest, SentryResult};
use ed25519_dalek::{SigningKey, Signer};

/// The guarded key (Static Mutable - Not Thread Safe, but Nucleus is single threaded)
static mut KEY: Option<SigningKey> = None;

/// The Sentry Gate
pub fn guard(req: SentryRequest) -> SentryResult {
    match req.op {
        SentryOp::Initialize => {
            unsafe {
                if KEY.is_none() {
                    // Load the key once
                    KEY = Some(SigningKey::from_bytes(&req.payload));
                    // Wipe payload from memory? (Rust moves copy, caller must wipe)
                    SentryResult { signature: [0; 64], status: 0 }
                } else {
                    SentryResult { signature: [0; 64], status: 1 } // Already initialized
                }
            }
        },
        SentryOp::SignHash => {
            unsafe {
                if let Some(key) = &KEY {
                    // In a real Sentry, we would check Capabilities here
                    // e.g. "Is this hash a valid DirectorRequest?"
                    let sig = key.sign(&req.payload);
                    SentryResult {
                        signature: sig.to_bytes(),
                        status: 0,
                    }
                } else {
                    SentryResult { signature: [0; 64], status: 2 } // Locked
                }
            }
        },
        _ => SentryResult { signature: [0; 64], status: 0 },
    }
}
