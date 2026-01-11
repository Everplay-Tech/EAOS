#![no_main]

use ihp::{
    decrypt_capsule, CapsuleTimestamp, IhpConfig, IhpCapsule, ServerEnvHash, SessionKey, KEY_BYTES,
    GOLDEN_CAPSULE_V1,
};
use libfuzzer_sys::fuzz_target;
use serde_json::from_str;

const STATIC_SESSION_KEY: [u8; KEY_BYTES] = [
    207, 224, 74, 76, 26, 88, 246, 237, 203, 113, 51, 160, 235, 87, 96, 212, 162, 31, 107, 191,
    51, 38, 53, 3, 172, 88, 243, 108, 120, 29, 181, 252,
];
const STATIC_ENV_HASH: ServerEnvHash = ServerEnvHash([0x42u8; 32]);

fuzz_target!(|data: &[u8]| {
    let mut capsule: IhpCapsule = match from_str(GOLDEN_CAPSULE_V1) {
        Ok(c) => c,
        Err(_) => return,
    };
    if data.is_empty() {
        return;
    }
    for (idx, byte) in capsule.payload.iter_mut().enumerate() {
        *byte ^= data.get(idx % data.len()).copied().unwrap_or(0);
    }
    for (idx, byte) in capsule.client_nonce.iter_mut().enumerate() {
        *byte ^= data.get(idx % data.len()).copied().unwrap_or(0);
    }
    let session = SessionKey::from_bytes(STATIC_SESSION_KEY);
    let _ = decrypt_capsule(
        &capsule,
        &STATIC_ENV_HASH,
        &session,
        CapsuleTimestamp::new(1_700_000_123).unwrap(),
        &IhpConfig::default(),
    );
});
