use std::net::SocketAddr;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::Router;
use base64::{Engine as _, engine::general_purpose::STANDARD};
use ihp::server::{ServerBootstrap, ServerState, build_router};
use ihp::{
    CapsuleTimestamp, ClientNonce, CryptoDomainLabels, DEFAULT_PROTOCOL_VERSION, IhpCapsule,
    IhpConfig, IhpNetworkContext, InMemoryKeyProvider, NONCE_LEN, PasswordMaterial,
    ServerEnvironmentProfile, ServerProfileId, derive_profile_key, derive_session_key,
    encrypt_capsule,
};
use rand::{RngCore, rngs::OsRng};
use reqwest::Client;
use tokio::task::JoinHandle;

const MASTER_KEY: [u8; ihp::KEY_BYTES] = *b"ihp master key material 32bytes!";
const TLS_EXPORTER_STUB: [u8; ihp::KEY_BYTES] = *b"tls exporter key material stub!!";

#[tokio::test]
async fn auth_success_and_failure_modes() {
    let sep = sample_sep();
    let server_profile_id = ServerProfileId(42);
    let config = IhpConfig::default();
    let bootstrap = ServerBootstrap {
        sep: sep.clone(),
        server_profile_id,
        master_key: MASTER_KEY,
        config: config.clone(),
    };
    let state = ServerState::initialize(bootstrap).expect("state");
    let router = build_router_with_fixed_tls_key(state.clone(), Some(TLS_EXPORTER_STUB));
    let (addr, server) = start_server(router).await;

    let (capsule, client_nonce) = build_capsule(
        &sep,
        server_profile_id,
        &config,
        client_nonce(),
        TLS_EXPORTER_STUB,
    );
    let client = Client::new();
    let ok_status = client
        .post(format!("http://{addr}/ihp/auth"))
        .json(&auth_body(&capsule, client_nonce))
        .send()
        .await
        .expect("http ok");
    assert_eq!(ok_status.status(), reqwest::StatusCode::OK);
    let ok_json: serde_json::Value = ok_status.json().await.expect("json");
    assert_eq!(ok_json["status"], "ok");
    assert!(ok_json["session_token"].is_string());

    // Tamper with ciphertext to force AEAD failure.
    let mut tampered_capsule = capsule.clone();
    tampered_capsule.payload[0] ^= 0xFF;
    let tampered_status = client
        .post(format!("http://{addr}/ihp/auth"))
        .json(&auth_body(&tampered_capsule, client_nonce))
        .send()
        .await
        .expect("http tamper");
    assert_eq!(tampered_status.status(), reqwest::StatusCode::UNAUTHORIZED);

    // Swap server profile ID to ensure mismatch is rejected.
    let mut wrong_profile_body = auth_body(&capsule, client_nonce);
    wrong_profile_body["server_profile_id"] = serde_json::Value::String("9999".into());
    let wrong_profile_status = client
        .post(format!("http://{addr}/ihp/auth"))
        .json(&wrong_profile_body)
        .send()
        .await
        .expect("http profile mismatch");
    assert_eq!(
        wrong_profile_status.status(),
        reqwest::StatusCode::UNAUTHORIZED
    );

    server.abort();
}

fn build_capsule(
    sep: &ServerEnvironmentProfile,
    server_profile_id: ServerProfileId,
    config: &IhpConfig,
    client_nonce: ClientNonce,
    tls_exporter_stub: [u8; ihp::KEY_BYTES],
) -> (IhpCapsule, ClientNonce) {
    let env_hash = ihp::compute_server_env_hash(sep).expect("env hash");
    let labels = CryptoDomainLabels::default();
    let provider = InMemoryKeyProvider::new(MASTER_KEY);
    let k_profile =
        derive_profile_key(&provider, server_profile_id, &env_hash, &labels).expect("profile");
    let network_context = IhpNetworkContext {
        rtt_bucket: 7,
        path_hint: 120,
    };
    let k_session = derive_session_key(
        &k_profile,
        &tls_exporter_key,
        &client_nonce,
        &network_context,
        server_profile_id,
        &labels,
    )
    .expect("session key");
    let now_secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("time")
        .as_secs() as i64;
    let timestamp = CapsuleTimestamp::new(now_secs).expect("timestamp");
    let password = PasswordMaterial::new(b"super-secret").expect("password");

    let capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        config,
        777,
        client_nonce,
        server_profile_id,
        network_context,
        &env_hash,
        &k_session,
        &password,
        timestamp,
    )
    .expect("capsule encrypt");
    (capsule, client_nonce)
}

fn auth_body(capsule: &IhpCapsule, _client_nonce: ClientNonce) -> serde_json::Value {
    serde_json::json!({
        "version": capsule.version,
        "header_id": capsule.header_id,
        "client_nonce_b64": STANDARD.encode(capsule.client_nonce),
        "server_profile_id": capsule.server_profile_id.0.to_string(),
        "network_context": {
            "rtt_bucket": capsule.network_context.rtt_bucket,
            "path_hint": capsule.network_context.path_hint,
        },
        "payload_b64": STANDARD.encode(&capsule.payload),
    })
}

fn start_server(router: Router) -> impl std::future::Future<Output = (SocketAddr, JoinHandle<()>)> {
    async move {
        let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0))
            .await
            .expect("bind");
        let addr = listener.local_addr().expect("addr");
        let handle = tokio::spawn(async move {
            axum::serve(listener, router).await.unwrap();
        });
        (addr, handle)
    }
}

fn sample_sep() -> ServerEnvironmentProfile {
    ServerEnvironmentProfile {
        cpu_fingerprint: "cpu:abcd".into(),
        nic_fingerprint: "nic:efgh".into(),
        os_fingerprint: "os:linux".into(),
        app_build_fingerprint: "build:1.0.0".into(),
        tpm_quote: None,
    }
}

fn client_nonce() -> ClientNonce {
    let mut bytes = [0u8; NONCE_LEN];
    OsRng.fill_bytes(&mut bytes);
    ClientNonce::new(bytes)
}
