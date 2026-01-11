use ihp::*;

const MASTER_KEY: [u8; 32] = *b"master key material for ihp proto*";
const TLS_EXPORTER_KEY: &[u8] = b"tls exporter key material";
const CLIENT_NONCE: [u8; NONCE_LEN] = [7u8; NONCE_LEN];
const PAYLOAD: &[u8] = b"fixture payload";
const TIMESTAMP: u64 = 1_700_000_000;
const SERVER_PROFILE_ID: ServerProfileId = ServerProfileId(42);

pub fn generate_fixture_capsule_hex() -> Result<String, IhpError> {
    let config = IhpConfig::default();
    let sep = ServerEnvironmentProfile {
        cpu_fingerprint: "cpu:fixture".into(),
        nic_fingerprint: "nic:fixture".into(),
        os_fingerprint: "os:fixture".into(),
        app_build_fingerprint: "build:fixture".into(),
        tpm_quote: None,
    };
    let env_hash = compute_server_env_hash(&sep);
    let provider = InMemoryKeyProvider::new(MASTER_KEY);
    let network_context = IhpNetworkContext {
        rtt_bucket: 7,
        path_hint: 120,
    };
    let client_nonce = ClientNonce::new(CLIENT_NONCE);
    let k_profile = provider.profile_key(SERVER_PROFILE_ID, &env_hash, &CryptoSuite::default())?;
    let k_session = provider.session_key(
        &k_profile,
        TLS_EXPORTER_KEY,
        &client_nonce,
        &network_context,
        SERVER_PROFILE_ID,
        &CryptoSuite::default(),
    )?;
    let capsule = encrypt_capsule(
        &config,
        99,
        client_nonce,
        SERVER_PROFILE_ID,
        network_context,
        env_hash,
        &k_session,
        &BoundedPayload::new(PAYLOAD.to_vec(), config.max_plaintext_len)?,
        CapsuleTimestamp::new(TIMESTAMP)?,
    )?;

    let bytes = serialize_capsule(&capsule)?;
    Ok(bytes.iter().map(|b| format!("{:02x}", b)).collect())
}
