use std::net::SocketAddr;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::Router;
use ihp::server::{ServerBootstrap, ServerState, build_router_with_fixed_tls_key};
use ihp::{
    IhpConfig, IhpServerProfile, ServerEnvironmentProfile, ServerProfileId,
    compute_server_env_hash, derive_profile_key, fetch_ihp_profile,
};
use reqwest::Client;
use tokio::task::JoinHandle;

const MASTER_KEY_A: [u8; ihp::KEY_BYTES] = *b"ihp master key material 32bytes!";
const TLS_EXPORTER_A: [u8; ihp::KEY_BYTES] = *b"tls exporter key material stub!!";
const MASTER_KEY_B: [u8; ihp::KEY_BYTES] = *b"different master key for ihp***!";
const TLS_EXPORTER_B: [u8; ihp::KEY_BYTES] = *b"different tls exporter stub!!";

#[tokio::test]
async fn stopped_flow_succeeds() {
    let sep = sample_sep_a();
    let (addr, handle) = start_server(sep.clone(), MASTER_KEY_A, TLS_EXPORTER_A, 7).await;

    let base_url = format!("http://{addr}");
    let profile = fetch_ihp_profile(&base_url).await.expect("profile");
    let k_profile = derive_profile_bytes(&sep, MASTER_KEY_A, profile.server_profile_id);

    let capsule = ihp::build_capsule_for_password(
        &profile,
        b"correct horse battery staple",
        &TLS_EXPORTER_A,
        &k_profile,
        now_secs(),
    )
    .await
    .expect("capsule");

    let client = Client::new();
    let response = client
        .post(format!("{base_url}/ihp/auth"))
        .json(&auth_body(&profile, &capsule))
        .send()
        .await
        .expect("auth request");
    assert_eq!(response.status(), reqwest::StatusCode::OK);
    let json: serde_json::Value = response.json().await.expect("json");
    assert_eq!(json["status"], "ok");
    assert!(json["session_token"].as_str().is_some());

    handle.abort();
}

#[tokio::test]
async fn moving_to_different_environment_rejects_capsule() {
    let sep_a = sample_sep_a();
    let sep_b = sample_sep_b();
    let (addr_a, handle_a) = start_server(sep_a.clone(), MASTER_KEY_A, TLS_EXPORTER_A, 11).await;
    let (addr_b, handle_b) = start_server(sep_b.clone(), MASTER_KEY_B, TLS_EXPORTER_B, 12).await;

    let base_a = format!("http://{addr_a}");
    let base_b = format!("http://{addr_b}");
    let profile_a = fetch_ihp_profile(&base_a).await.expect("profile a");
    let k_profile_a = derive_profile_bytes(&sep_a, MASTER_KEY_A, profile_a.server_profile_id);

    let capsule = ihp::build_capsule_for_password(
        &profile_a,
        b"correct horse battery staple",
        &TLS_EXPORTER_A,
        &k_profile_a,
        now_secs(),
    )
    .await
    .expect("capsule a");

    let client = Client::new();
    let response = client
        .post(format!("{base_b}/ihp/auth"))
        .json(&auth_body(&profile_a, &capsule))
        .send()
        .await
        .expect("auth request");
    assert_eq!(response.status(), reqwest::StatusCode::UNAUTHORIZED);
    let json: serde_json::Value = response.json().await.expect("json");
    assert_eq!(json["reason"], "invalid_credentials");

    handle_a.abort();
    handle_b.abort();
}

#[tokio::test]
async fn tampering_in_transit_is_rejected() {
    let sep = sample_sep_a();
    let (addr, handle) = start_server(sep.clone(), MASTER_KEY_A, TLS_EXPORTER_A, 21).await;
    let base_url = format!("http://{addr}");
    let profile = fetch_ihp_profile(&base_url).await.expect("profile");
    let k_profile = derive_profile_bytes(&sep, MASTER_KEY_A, profile.server_profile_id);

    let mut capsule = ihp::build_capsule_for_password(
        &profile,
        b"correct horse battery staple",
        &TLS_EXPORTER_A,
        &k_profile,
        now_secs(),
    )
    .await
    .expect("capsule");

    // Flip a bit in the payload to simulate corruption.
    capsule.payload[0] ^= 0xFF;

    let client = Client::new();
    let response = client
        .post(format!("{base_url}/ihp/auth"))
        .json(&auth_body(&profile, &capsule))
        .send()
        .await
        .expect("tamper request");
    assert_eq!(response.status(), reqwest::StatusCode::UNAUTHORIZED);
    let json: serde_json::Value = response.json().await.expect("json");
    assert_eq!(json["reason"], "invalid_credentials");

    // Tamper with RTT bucket to simulate replay over a different network path.
    let mut capsule_bucket_tamper = capsule.clone();
    capsule_bucket_tamper.network_context.rtt_bucket ^= 1;
    let bucket_response = client
        .post(format!("{base_url}/ihp/auth"))
        .json(&auth_body(&profile, &capsule_bucket_tamper))
        .send()
        .await
        .expect("bucket tamper request");
    assert_eq!(bucket_response.status(), reqwest::StatusCode::UNAUTHORIZED);

    handle.abort();
}

fn derive_profile_bytes(
    sep: &ServerEnvironmentProfile,
    master_key: [u8; ihp::KEY_BYTES],
    server_profile_id: ServerProfileId,
) -> [u8; ihp::KEY_BYTES] {
    let env_hash = compute_server_env_hash(sep).expect("env hash");
    let labels = ihp::CryptoDomainLabels::default();
    let provider = ihp::InMemoryKeyProvider::new(master_key);
    let profile =
        derive_profile_key(&provider, server_profile_id, &env_hash, &labels).expect("profile");
    *profile.expose()
}

fn auth_body(profile: &IhpServerProfile, capsule: &ihp::IhpCapsule) -> serde_json::Value {
    serde_json::json!({
        "version": capsule.version,
        "header_id": capsule.header_id,
        "client_nonce_b64": base64::encode(capsule.client_nonce),
        "server_profile_id": profile.server_profile_id.0.to_string(),
        "network_context": {
            "rtt_bucket": capsule.network_context.rtt_bucket,
            "path_hint": capsule.network_context.path_hint,
        },
        "payload_b64": base64::encode(&capsule.payload),
    })
}

async fn start_server(
    sep: ServerEnvironmentProfile,
    master_key: [u8; ihp::KEY_BYTES],
    tls_exporter: [u8; ihp::KEY_BYTES],
    profile_id: u64,
) -> (SocketAddr, JoinHandle<()>) {
    let server_profile_id = ServerProfileId(profile_id);
    let bootstrap = ServerBootstrap {
        sep,
        server_profile_id,
        master_key,
        config: IhpConfig::default(),
    };
    let state = ServerState::initialize(bootstrap).expect("state");
    let router = build_router_with_fixed_tls_key(state, Some(tls_exporter));
    spawn_router(router).await
}

async fn spawn_router(router: Router) -> (SocketAddr, JoinHandle<()>) {
    let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0))
        .await
        .expect("bind");
    let addr = listener.local_addr().expect("addr");
    let handle = tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });
    (addr, handle)
}

fn sample_sep_a() -> ServerEnvironmentProfile {
    ServerEnvironmentProfile {
        cpu_fingerprint: "cpu:abcd".into(),
        nic_fingerprint: "nic:efgh".into(),
        os_fingerprint: "os:linux".into(),
        app_build_fingerprint: "build:1.0.0".into(),
        tpm_quote: None,
    }
}

fn sample_sep_b() -> ServerEnvironmentProfile {
    ServerEnvironmentProfile {
        cpu_fingerprint: "cpu:wxyz".into(),
        nic_fingerprint: "nic:qwer".into(),
        os_fingerprint: "os:linux-alt".into(),
        app_build_fingerprint: "build:2.0.0".into(),
        tpm_quote: None,
    }
}

fn now_secs() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("time")
        .as_secs() as i64
}
