#![no_main]

use arbitrary::Arbitrary;
use ihp::{
    encrypt_capsule, CapsuleTimestamp, ClientNonce, IhpConfig, IhpNetworkContext, PasswordMaterial,
    ProtocolVersion, ServerEnvHash, ServerProfileId, SessionKey, NONCE_LEN, KEY_BYTES,
};
use libfuzzer_sys::fuzz_target;

#[derive(Arbitrary, Debug)]
struct CapsuleInput {
    payload: Vec<u8>,
    header_id: u64,
    nonce: [u8; NONCE_LEN],
    path_hint: u16,
    rtt_bucket: u8,
}

fuzz_target!(|input: CapsuleInput| {
    let Ok(password) = PasswordMaterial::new(&input.payload) else {
        return;
    };
    let config = IhpConfig::default();
    let client_nonce = ClientNonce::new(input.nonce);
    let session_key = SessionKey::from_bytes([0x11u8; KEY_BYTES]);
    let network_context = IhpNetworkContext {
        rtt_bucket: input.rtt_bucket % 100,
        path_hint: input.path_hint.max(1),
    };
    let capsule = match encrypt_capsule(
        ProtocolVersion::V1,
        &config,
        input.header_id,
        client_nonce,
        ServerProfileId(1),
        network_context,
        &ServerEnvHash([0u8; 32]),
        &session_key,
        &password,
        CapsuleTimestamp::new(1_700_000_000).unwrap(),
    ) {
        Ok(c) => c,
        Err(_) => return,
    };
    let _ = ihp::decrypt_capsule(
        &capsule,
        &ServerEnvHash([0u8; 32]),
        &session_key,
        CapsuleTimestamp::new(1_700_000_000).unwrap(),
        &config,
    );
});
