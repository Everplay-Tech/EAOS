#![no_main]
use ihp::*;
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if data.len() < 24 {
        return;
    }
    let client_nonce = ClientNonce::from_slice(&data[..24]).unwrap_or(ClientNonce::new([0u8; 24]));
    let payload = BoundedPayload::new(data[24..].to_vec(), IhpConfig::default().max_plaintext_len);
    if payload.is_err() {
        return;
    }
    let config = IhpConfig::default();
    let env_hash = ServerEnvHash([0u8; 32]);
    let network_context = IhpNetworkContext { rtt_bucket: 1, path_hint: 1 };
    let k = SecretKey::from_array(KeyOrigin::Session(ServerProfileId(0), 1), [1u8; 32]);
    let _ = encrypt_capsule(
        &config,
        1,
        client_nonce,
        ServerProfileId(0),
        network_context,
        env_hash,
        &k,
        &payload.unwrap(),
        CapsuleTimestamp::new(1_700_000_000).unwrap(),
    );
});
