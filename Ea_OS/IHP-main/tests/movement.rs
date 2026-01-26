use std::net::SocketAddr;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::Router;
use base64::{Engine as _, engine::general_purpose::STANDARD};
use ihp::client::{
    CapsuleBuildOptions, DEFAULT_PATH_HINT, build_capsule_for_password_with_options,
    fetch_ihp_profile,
};
use ihp::server::{ServerBootstrap, ServerState, build_router_with_fixed_tls_key};
use ihp::{
    CapsuleTimestamp, CryptoDomainLabels, IhpCapsule, IhpConfig, InMemoryKeyProvider,
    ServerEnvironmentProfile, ServerProfileId, derive_profile_key,
};
use reqwest::Client;
use tokio::task::JoinHandle;

const MASTER_KEY_PRIMARY: [u8; ihp::KEY_BYTES] = *b"ihp primary master key materi!!";
const MASTER_KEY_SECONDARY: [u8; ihp::KEY_BYTES] = *b"ihp secondary master key mat!!";
const TLS_EXPORTER_STUB: [u8; ihp::KEY_BYTES] = *b"tls exporter key material stub!!";

#[tokio::test]
async fn stopped_profile_allows_auth() {
    let sep = sample_sep("stopped");
    let server_profile_id = ServerProfileId(77);
    let config = IhpConfig::default();
    let bootstrap = ServerBootstrap {
        sep: sep.clone(),
        server_profile_id,
        master_key: MASTER_KEY_PRIMARY,
        config: config.clone(),
    };
    let state = ServerState::initialize(bootstrap).expect("state");
    let router = build_router_with_fixed_tls_key(state, Some(TLS_EXPORTER_STUB));
    let (addr, handle) = start_server(router).await;
    let base_url = format!("http://{addr}");

    let server_profile = fetch_ihp_profile(&base_url).await.expect("profile");
    assert_eq!(server_profile.server_profile_id, server_profile_id);

    let k_profile = derive_profile(&sep, server_profile_id, MASTER_KEY_PRIMARY);
    let capsule = build_capsule_for_password_with_options(
        &server_profile,
        b"stopped-password",
        &TLS_EXPORTER_STUB,
        &k_profile,
        now_timestamp(),
        CapsuleBuildOptions {
            rtt_bucket_override: Some(12),
            path_hint: DEFAULT_PATH_HINT,
            header_id_override: Some(0xAA11),
        },
    )
    .await
    .expect("capsule");

    let client = Client::new();
    let response = client
        .post(format!("{base_url}/ihp/auth"))
        .json(&auth_body(&capsule))
        .send()
        .await
        .expect("auth request");
    assert_eq!(response.status(), reqwest::StatusCode::OK);
    let json: serde_json::Value = response.json().await.expect("json");
    assert_eq!(json["status"], "ok");
    assert!(json["session_token"].is_string());

    handle.abort();
}

#[tokio::test]
async fn moving_to_new_environment_is_rejected() {
    let sep_primary = sample_sep("primary");
    let sep_secondary = sample_sep("secondary");
    let server_profile_id = ServerProfileId(404);
    let base_config = IhpConfig::default();

    let primary_state = ServerState::initialize(ServerBootstrap {
        sep: sep_primary.clone(),
        server_profile_id,
        master_key: MASTER_KEY_PRIMARY,
        config: base_config.clone(),
    })
    .expect("primary");
    let primary_router = build_router_with_fixed_tls_key(primary_state, Some(TLS_EXPORTER_STUB));
    let (primary_addr, primary_handle) = start_server(primary_router).await;
    let primary_url = format!("http://{primary_addr}");

    let secondary_state = ServerState::initialize(ServerBootstrap {
        sep: sep_secondary.clone(),
        server_profile_id,
        master_key: MASTER_KEY_SECONDARY,
        config: base_config.clone(),
    })
    .expect("secondary");
    let secondary_router = build_router_with_fixed_tls_key(secondary_state, Some(TLS_EXPORTER_STUB));
    let (secondary_addr, secondary_handle) = start_server(secondary_router).await;
    let secondary_url = format!("http://{secondary_addr}");

    let primary_profile = fetch_ihp_profile(&primary_url).await.expect("profile");
    let k_profile = derive_profile(&sep_primary, server_profile_id, MASTER_KEY_PRIMARY);
    let capsule = build_capsule_for_password_with_options(
        &primary_profile,
        b"moving-password",
        &TLS_EXPORTER_STUB,
        &k_profile,
        now_timestamp(),
        CapsuleBuildOptions {
            rtt_bucket_override: Some(8),
            path_hint: DEFAULT_PATH_HINT,
            header_id_override: Some(0xBB22),
        },
    )
    .await
    .expect("capsule");

    let client = Client::new();
    let response = client
        .post(format!("{secondary_url}/ihp/auth"))
        .json(&auth_body(&capsule))
        .send()
        .await
        .expect("auth request");
    assert_eq!(response.status(), reqwest::StatusCode::UNAUTHORIZED);
    let json: serde_json::Value = response.json().await.expect("json");
    assert_eq!(json["reason"], "invalid_credentials");

    primary_handle.abort();
    secondary_handle.abort();
}

#[tokio::test]
async fn tampering_triggers_rejection() {
    let sep = sample_sep("tamper");
    let server_profile_id = ServerProfileId(505);
    let config = IhpConfig::default();
    let bootstrap = ServerBootstrap {
        sep: sep.clone(),
        server_profile_id,
        master_key: MASTER_KEY_PRIMARY,
        config: config.clone(),
    };
    let state = ServerState::initialize(bootstrap).expect("state");
    let router = build_router_with_fixed_tls_key(state, Some(TLS_EXPORTER_STUB));
    let (addr, handle) = start_server(router).await;
    let base_url = format!("http://{addr}");

    let server_profile = fetch_ihp_profile(&base_url).await.expect("profile");
    let k_profile = derive_profile(&sep, server_profile_id, MASTER_KEY_PRIMARY);
    let capsule = build_capsule_for_password_with_options(
        &server_profile,
        b"tamper-password",
        &TLS_EXPORTER_STUB,
        &k_profile,
        now_timestamp(),
        CapsuleBuildOptions {
            rtt_bucket_override: Some(5),
            path_hint: DEFAULT_PATH_HINT,
            header_id_override: Some(0xCC33),
        },
    )
    .await
    .expect("capsule");

    let mut tampered_payload = capsule.clone();
    tampered_payload.payload[0] ^= 0xFF;

    let mut tampered_network = capsule.clone();
    tampered_network.network_context.rtt_bucket ^= 0x01;

    let client = Client::new();
    for bad in [tampered_payload, tampered_network] {
        let response = client
            .post(format!("{base_url}/ihp/auth"))
            .json(&auth_body(&bad))
            .send()
            .await
            .expect("auth request");
        assert_eq!(response.status(), reqwest::StatusCode::UNAUTHORIZED);
        let json: serde_json::Value = response.json().await.expect("json");
        assert_eq!(json["reason"], "invalid_credentials");
    }

    handle.abort();
}

fn auth_body(capsule: &IhpCapsule) -> serde_json::Value {
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

fn now_timestamp() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("time")
        .as_secs() as i64
}

fn derive_profile(
    sep: &ServerEnvironmentProfile,
    server_profile_id: ServerProfileId,
    master_key: [u8; ihp::KEY_BYTES],
) -> ihp::ProfileKey {
    let env_hash = ihp::compute_server_env_hash(sep).expect("env hash");
    let labels = CryptoDomainLabels::default();
    let provider = InMemoryKeyProvider::new(master_key);
    derive_profile_key(&provider, server_profile_id, &env_hash, &labels).expect("profile")
}

fn sample_sep(tag: &str) -> ServerEnvironmentProfile {
    ServerEnvironmentProfile {
        cpu_fingerprint: format!("cpu:{tag}"),
        nic_fingerprint: format!("nic:{tag}"),
        os_fingerprint: "os:linux".into(),
        app_build_fingerprint: format!("build:{tag}"),
        tpm_quote: None,
    }
}

async fn start_server(router: Router) -> (SocketAddr, JoinHandle<()>) {
    let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0))
        .await
        .expect("bind");
    let addr = listener.local_addr().expect("addr");
    let handle = tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });
    (addr, handle)
}
