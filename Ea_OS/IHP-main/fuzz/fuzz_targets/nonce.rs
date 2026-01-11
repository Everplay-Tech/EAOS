#![no_main]
use ihp::*;
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if data.len() < 24 {
        return;
    }
    let mut bytes = [0u8; 24];
    bytes.copy_from_slice(&data[..24]);
    let nonce = ClientNonce::new(bytes);
    let network_context = IhpNetworkContext { rtt_bucket: 1, path_hint: 1 };
    let suite = CryptoSuite::default();
    let provider = InMemoryKeyProvider::new([0x11u8; 32]);
    let env_hash = ServerEnvHash([0u8; 32]);
    if let Ok(k_profile) = provider.profile_key(ServerProfileId(0), &env_hash, &suite) {
        let _ = provider.session_key(
            &k_profile,
            data,
            &nonce,
            &network_context,
            ServerProfileId(0),
            &suite,
        );
    }
});
