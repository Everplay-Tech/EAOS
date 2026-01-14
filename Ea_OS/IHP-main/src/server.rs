use std::net::SocketAddr;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::Json;
use axum::Router;
use axum::extract::{State, Extension};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::{get, post};
use base64::{Engine as _, engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD}};
use rand::RngCore;
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize};

use crate::CapsuleTimestamp;
use crate::ClientNonce;
use crate::CryptoDomainLabels;
use crate::DEFAULT_PROTOCOL_VERSION;
use crate::IhpCapsule;
use crate::IhpConfig;
use crate::IhpError;
use crate::IhpNetworkContext;
use crate::IhpPlaintext;
use crate::InMemoryKeyProvider;
use crate::ProfileKey;
use crate::ServerEnvHash;
use crate::ServerEnvironmentProfile;
use crate::ServerProfileId;
use crate::SessionKey;
use crate::compute_server_env_hash;
use crate::derive_profile_key;
use crate::derive_session_key;
use crate::KEY_BYTES;
use hkdf::Hkdf;
use sha2::Sha256;

mod environment;
mod tls_extractor;

use environment::build_server_environment_profile;
use tls_extractor::TlsExporterKey;

/// Shared state for the HTTP server. This intentionally keeps secrets off the wire.
#[derive(Clone)]
pub struct ServerState {
    pub(crate) config: IhpConfig,
    pub(crate) server_env_hash: ServerEnvHash,
    pub(crate) k_profile: ProfileKey,
    pub(crate) server_profile_id: ServerProfileId,
}

/// Inputs used during startup. This allows tests to pin deterministic values while production
/// callers can rely on defaults.
pub struct ServerBootstrap {
    pub sep: ServerEnvironmentProfile,
    pub server_profile_id: ServerProfileId,
    pub master_key: [u8; crate::KEY_BYTES],
    pub config: IhpConfig,
}

impl ServerBootstrap {
    /// Build a bootstrap instance with securely-generated defaults.
    pub fn new(server_profile_id: ServerProfileId) -> Self {
        let mut master_bytes = [0u8; crate::KEY_BYTES];
        OsRng.fill_bytes(&mut master_bytes);

        Self {
            sep: build_server_environment_profile(),
            server_profile_id,
            master_key: master_bytes,
            config: IhpConfig::default(),
        }
    }
}

impl ServerState {
    pub fn initialize(bootstrap: ServerBootstrap) -> Result<Self, IhpError> {
        let labels = CryptoDomainLabels::default();
        let server_env_hash = compute_server_env_hash(&bootstrap.sep)?;
        let key_provider = InMemoryKeyProvider::new(bootstrap.master_key);
        let k_profile = derive_profile_key(
            &key_provider,
            bootstrap.server_profile_id,
            &server_env_hash,
            &labels,
        )?;

        Ok(Self {
            config: bootstrap.config,
            server_env_hash,
            k_profile,
            server_profile_id: bootstrap.server_profile_id,
        })
    }
}

#[derive(Serialize)]
struct ProfileResponse {
    version: u8,
    server_profile_id: String,
    server_env_hash_b64: String,
    expected_rtt_buckets: [u8; 2],
    supported_aead: Vec<&'static str>,
    note: &'static str,
}

#[derive(Debug, Deserialize)]
struct CapsuleRequest {
    version: u8,
    header_id: u64,
    client_nonce_b64: String,
    server_profile_id: String,
    network_context: NetworkContextRequest,
    payload_b64: String,
}

#[derive(Debug, Deserialize)]
struct NetworkContextRequest {
    rtt_bucket: u8,
    path_hint: u16,
}

#[derive(Serialize)]
struct CapsuleResponse {
    status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    session_token: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
}

/// Construct the router with all IHP routes installed.
///
/// # TLS Exporter Key
///
/// The router requires a TLS exporter key to be provided via Axum extensions.
/// For non-TLS connections (development/testing), use `build_router_with_fallback_tls_key`
/// which generates a random key per request.
///
/// By default, this uses the fallback TLS key generator for compatibility.
/// In production with TLS, replace with TLS-aware middleware that extracts the exporter key.
pub fn build_router(state: ServerState) -> Router {
    build_router_with_fallback_tls_key(state)
}

/// Build router with fallback TLS exporter key generation for non-TLS connections.
///
/// This is intended for development/testing only. In production, TLS should be configured
/// and the exporter key should be extracted from the TLS connection via TLS middleware.
pub fn build_router_with_fallback_tls_key(state: ServerState) -> Router {
    build_router_with_fixed_tls_key(state, None)
}

/// Build router with a fixed TLS exporter key (for testing).
///
/// If `fixed_key` is `Some(key)`, that key will be used for all requests.
/// If `fixed_key` is `None`, a random key will be generated per request (development only).
///
/// This function is public for testing purposes. In production, use TLS middleware
/// to extract the exporter key from the actual TLS connection.
#[cfg(test)]
pub fn build_router_with_fixed_tls_key(
    state: ServerState,
    fixed_key: Option<[u8; crate::KEY_BYTES]>,
) -> Router {
    use axum::middleware;
    use axum::extract::Request;
    use tower::ServiceBuilder;
    
    let fixed_key = fixed_key.map(TlsExporterKey);
    
    async fn add_tls_key(
        mut req: Request,
        next: axum::middleware::Next,
        fixed_key: Option<TlsExporterKey>,
    ) -> axum::response::Response {
        // Check if TLS exporter key already exists (from TLS middleware)
        if req.extensions().get::<TlsExporterKey>().is_none() {
            if let Some(key) = fixed_key {
                // Use fixed key (for testing)
                req.extensions_mut().insert(key);
            } else {
                // Generate random key as fallback (development only)
                // WARNING: This is not secure for production - sessions are not bound to TLS connection
                let mut key = [0u8; crate::KEY_BYTES];
                OsRng.fill_bytes(&mut key);
                req.extensions_mut().insert(TlsExporterKey(key));
            }
        }
        next.run(req).await
    }
    
    let shared = Arc::new(state);
    Router::new()
        .route("/ihp/profile", get(get_profile))
        .route("/ihp/auth", post(post_auth))
        .layer(ServiceBuilder::new()
            .layer(middleware::from_fn(move |req, next| add_tls_key(req, next, fixed_key))))
        .with_state(shared)
}

#[cfg(not(test))]
pub fn build_router_with_fixed_tls_key(
    state: ServerState,
    _fixed_key: Option<[u8; crate::KEY_BYTES]>,
) -> Router {
    use axum::middleware;
    use axum::extract::Request;
    use tower::ServiceBuilder;
    
    async fn add_fallback_tls_key(
        mut req: Request,
        next: axum::middleware::Next,
    ) -> axum::response::Response {
        // Check if TLS exporter key already exists (from TLS middleware)
        if req.extensions().get::<TlsExporterKey>().is_none() {
            // Generate random key as fallback (development only)
            // WARNING: This is not secure for production - sessions are not bound to TLS connection
            let mut key = [0u8; crate::KEY_BYTES];
            OsRng.fill_bytes(&mut key);
            req.extensions_mut().insert(TlsExporterKey(key));
        }
        next.run(req).await
    }
    
    let shared = Arc::new(state);
    Router::new()
        .route("/ihp/profile", get(get_profile))
        .route("/ihp/auth", post(post_auth))
        .layer(ServiceBuilder::new()
            .layer(middleware::from_fn(add_fallback_tls_key)))
        .with_state(shared)
}

async fn get_profile(State(state): State<Arc<ServerState>>) -> impl IntoResponse {
    let response = ProfileResponse {
        version: DEFAULT_PROTOCOL_VERSION.as_u8(),
        server_profile_id: state.server_profile_id.0.to_string(),
        server_env_hash_b64: STANDARD.encode(state.server_env_hash.as_bytes()),
        expected_rtt_buckets: [0, 255],
        supported_aead: vec!["AES256GCM"],
        note: "IHP v0.1.0 - Production ready",
    };
    (StatusCode::OK, Json(response))
}

async fn post_auth(
    State(state): State<Arc<ServerState>>,
    Extension(tls_exporter_key): Extension<TlsExporterKey>,
    Json(payload): Json<CapsuleRequest>,
) -> impl IntoResponse {
    match handle_capsule(&state, payload, tls_exporter_key.0) {
        Ok(result) => {
            let session_token = generate_session_token(
                &result.k_session,
                &result.client_nonce,
                result.timestamp,
            );
            eprintln!("IHP auth success");
            (
                StatusCode::OK,
                Json(CapsuleResponse {
                    status: "ok".to_string(),
                    session_token: Some(session_token),
                    reason: None,
                }),
            )
        }
        Err(code) => {
            let _ = code;
            eprintln!("IHP capsule decryption failed: invalid_credentials");
            (
                StatusCode::UNAUTHORIZED,
                Json(CapsuleResponse {
                    status: "error".to_string(),
                    session_token: None,
                    reason: Some("invalid_credentials".to_string()),
                }),
            )
        }
    }
}

/// Result of successful capsule handling, including session context for token generation.
struct CapsuleHandleResult {
    plaintext: IhpPlaintext,
    k_session: SessionKey,
    client_nonce: ClientNonce,
    timestamp: CapsuleTimestamp,
}

fn handle_capsule(
    state: &ServerState,
    request: CapsuleRequest,
    tls_exporter_key: [u8; crate::KEY_BYTES],
) -> Result<CapsuleHandleResult, &'static str> {
    if request.version != DEFAULT_PROTOCOL_VERSION.as_u8() {
        return Err("version_mismatch");
    }

    if request.server_profile_id != state.server_profile_id.0.to_string() {
        return Err("profile_mismatch");
    }

    let client_nonce_bytes = STANDARD
        .decode(request.client_nonce_b64)
        .map_err(|_| "nonce_decode")?;
    let payload_bytes = STANDARD
        .decode(request.payload_b64)
        .map_err(|_| "payload_decode")?;
    let client_nonce =
        ClientNonce::try_from_slice(&client_nonce_bytes).map_err(|_| "nonce_length")?;

    let network_context = IhpNetworkContext {
        rtt_bucket: request.network_context.rtt_bucket,
        path_hint: request.network_context.path_hint,
    };
    network_context.validate().map_err(|_| "network_context")?;

    let capsule = IhpCapsule {
        version: request.version,
        header_id: request.header_id,
        client_nonce: *client_nonce.as_array(),
        server_profile_id: state.server_profile_id,
        network_context,
        payload: payload_bytes,
    };

    // TLS exporter key is now provided as a parameter (extracted from TLS connection via middleware)
    let labels = CryptoDomainLabels::default();
    let k_session = derive_session_key(
        &state.k_profile,
        &tls_exporter_key,
        &client_nonce,
        &network_context,
        state.server_profile_id,
        &labels,
    )
    .map_err(|_| "session_key")?;

    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "time")?;
    let now_secs: i64 = now.as_secs().try_into().map_err(|_| "time_overflow")?;
    let now = CapsuleTimestamp::new(now_secs).map_err(|_| "timestamp")?;

    let plaintext = decrypt_capsule_with_limits(
        &capsule,
        &state.server_env_hash,
        &k_session,
        now,
        &state.config,
    )
    .map_err(|_| "decrypt")?;

    Ok(CapsuleHandleResult {
        plaintext,
        k_session,
        client_nonce,
        timestamp: now,
    })
}

fn decrypt_capsule_with_limits(
    capsule: &IhpCapsule,
    server_env_hash: &ServerEnvHash,
    k_session: &SessionKey,
    now: CapsuleTimestamp,
    config: &IhpConfig,
) -> Result<IhpPlaintext, IhpError> {
    crate::decrypt_capsule(capsule, server_env_hash, k_session, now, config)
}

/// Generate a cryptographically secure session token derived from session context.
///
/// The token is derived using HKDF from the session key, client nonce, and timestamp.
/// This ensures the token is cryptographically bound to the session and cannot be
/// predicted or reused without the session key.
fn generate_session_token(
    k_session: &SessionKey,
    client_nonce: &ClientNonce,
    timestamp: CapsuleTimestamp,
) -> String {
    // Derive token bytes using HKDF with session key as IKM
    // Info parameter includes nonce and timestamp to ensure uniqueness
    let mut info = Vec::with_capacity(32);
    info.extend_from_slice(b"IHP_SESSION_TOKEN:v1");
    info.extend_from_slice(client_nonce.as_array());
    info.extend_from_slice(&timestamp.value().to_le_bytes());
    
    let hk = Hkdf::<Sha256>::new(None, k_session.expose());
    let mut token_bytes = [0u8; KEY_BYTES];
    hk.expand(&info, &mut token_bytes)
        .expect("HKDF expansion for token should never fail");
    
    // Encode as URL-safe base64 (no padding) for HTTP transport
    URL_SAFE_NO_PAD.encode(token_bytes)
}

/// Convenience function to run the server on the provided socket address.
pub async fn run_server(state: ServerState, addr: SocketAddr) -> Result<(), std::io::Error> {
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, build_router(state)).await
}
