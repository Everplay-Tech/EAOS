mod fixture_inputs {
    #![allow(dead_code)]
    include!("../tests/fixture_inputs.rs");
}

use ihp::{
    CapsuleTimestamp, ClientNonce, CryptoDomainLabels, DEFAULT_PROTOCOL_VERSION, IhpConfig,
    IhpNetworkContext, InMemoryKeyProvider, NONCE_LEN, PasswordMaterial, ServerEnvironmentProfile,
    ServerProfileId, compute_server_env_hash, derive_profile_key, derive_session_key,
    encrypt_capsule,
};

fn main() -> Result<(), ihp::IhpError> {
    let config = IhpConfig::default();
    let sep = ServerEnvironmentProfile {
        cpu_fingerprint: "cpu:fixture".into(),
        nic_fingerprint: "nic:fixture".into(),
        os_fingerprint: "os:fixture".into(),
        app_build_fingerprint: "build:fixture".into(),
        tpm_quote: None,
    };
    let env_hash = compute_server_env_hash(&sep)?;
    let provider = InMemoryKeyProvider::new(*b"master key material for ihp pro!");
    let labels = CryptoDomainLabels::default();
    let network_context = IhpNetworkContext {
        rtt_bucket: 7,
        path_hint: 120,
    };
    let client_nonce = ClientNonce::new([7u8; NONCE_LEN]);
    let k_profile = derive_profile_key(&provider, ServerProfileId(42), &env_hash, &labels)
        .expect("profile key");
    let k_session = derive_session_key(
        &k_profile,
        b"tls exporter key material",
        &client_nonce,
        &network_context,
        ServerProfileId(42),
        &labels,
    )
    .expect("session key");
    let capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        &config,
        99,
        client_nonce,
        ServerProfileId(42),
        network_context,
        &env_hash,
        &k_session,
        &PasswordMaterial::new(b"fixture payload")?,
        CapsuleTimestamp::new(1_700_000_000)?,
    )?;

    let bytes = bincode::serialize(&capsule).map_err(|_| ihp::IhpError::SerializationFailed)?;
    let hex = bytes
        .iter()
        .map(|b| format!("{:02x}", b))
        .collect::<String>();
    std::fs::create_dir_all("tests/fixtures").expect("create fixtures dir");
    std::fs::write("tests/fixtures/capsule_v1.hex", hex.as_bytes()).expect("write fixture");

    let byte_len = hex.len() / 2;
    println!("Wrote {byte_len} bytes (hex) to tests/fixtures/capsule_v1.hex");
    Ok(())
}
