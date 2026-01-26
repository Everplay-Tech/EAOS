use ihp::*;

const MASTER_KEY: [u8; 32] = *b"master key material for ihp pro!";
const TLS_EXPORTER_KEY: &[u8] = b"tls exporter key material";
const CLIENT_NONCE: [u8; NONCE_LEN] = [7u8; NONCE_LEN];
const PAYLOAD: &[u8] = b"fixture payload";
const TIMESTAMP: i64 = 1_700_000_000;
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
    let labels = CryptoDomainLabels::default();
    let client_nonce = ClientNonce::new(CLIENT_NONCE);
    let k_profile = derive_profile_key(&provider, SERVER_PROFILE_ID, &env_hash, &labels)?;
    let k_session = derive_session_key(
        &k_profile,
        TLS_EXPORTER_KEY,
        &client_nonce,
        &network_context,
        SERVER_PROFILE_ID,
        &labels,
    )?;
    let password_material = PasswordMaterial::new(PAYLOAD.to_vec())?;
    let timestamp = CapsuleTimestamp::new(TIMESTAMP)?;
    let capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        &config,
        99,
        client_nonce,
        SERVER_PROFILE_ID,
        network_context,
        &env_hash,
        &k_session,
        &password_material,
        timestamp,
    )?;

    let bytes = bincode::serialize(&capsule).map_err(|_| IhpError::SerializationFailed)?;
    Ok(bytes.iter().map(|b| format!("{:02x}", b)).collect())
}
