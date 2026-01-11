//! Lightweight client-side helpers for constructing IHP capsules in integration tests and demos.
//!
//! These helpers intentionally keep the protocol surface small and clearly separate research-only
//! scaffolding (such as RTT bucketing heuristics) from the core capsule construction logic.

use std::time::Instant;

use base64::{Engine as _, engine::general_purpose::STANDARD};
use rand::RngCore;
use rand::rngs::OsRng;
use reqwest::Client;

use crate::{
    CapsuleTimestamp, ClientNonce, CryptoDomainLabels, IhpCapsule, IhpConfig, IhpError,
    IhpNetworkContext, PasswordMaterial, ProfileKey, ProtocolVersion, ServerEnvHash,
    ServerProfileId, SessionKey, derive_session_key, encrypt_capsule, generate_client_nonce,
};

/// Hydrated server profile derived from `/ihp/profile`.
#[derive(Debug, Clone)]
pub struct IhpServerProfile {
    pub base_url: String,
    pub version: ProtocolVersion,
    pub server_profile_id: ServerProfileId,
    pub server_env_hash: ServerEnvHash,
    pub expected_rtt_buckets: [u8; 2],
    pub supported_aead: Vec<String>,
}

/// Errors surfaced by the client helper routines.
#[derive(Debug)]
pub enum IhpClientError {
    Http(reqwest::Error),
    Decode(String),
use std::time::Instant;

use base64::{Engine as _, engine::general_purpose::STANDARD};
use rand::rngs::OsRng;
use rand::{CryptoRng, RngCore};
use reqwest::Client;
use serde::Deserialize;

use crate::{
    CapsuleTimestamp, CryptoDomainLabels, IhpCapsule, IhpConfig, IhpError, IhpNetworkContext,
    PasswordMaterial, ProfileKey, ProtocolVersion, ServerEnvHash, ServerProfileId,
};
use crate::{derive_session_key, encrypt_capsule, generate_client_nonce};

/// Default hop hint for research scaffolding. Real deployments may overwrite this when a more
/// meaningful value is available.
pub const DEFAULT_PATH_HINT: u16 = 120;
/// Number of RTT measurements used to smooth out jitter.
const RTT_SAMPLES: usize = 4;
/// Milliseconds represented by a single RTT bucket. Buckets are clamped to `[0, 255]`.
const RTT_MS_PER_BUCKET: f64 = 5.0;

/// Client-visible view of `/ihp/profile`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IhpServerProfile {
    pub base_url: String,
    pub version: u8,
    pub server_profile_id: ServerProfileId,
    pub expected_rtt_buckets: [u8; 2],
    pub supported_aead: Vec<String>,
    pub server_env_hash: ServerEnvHash,
}

/// Errors emitted by the lightweight client helper.
#[derive(Debug)]
pub enum IhpClientError {
    Http(reqwest::Error),
    Parse(String),
    Crypto(IhpError),
}

impl std::fmt::Display for IhpClientError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            IhpClientError::Http(err) => write!(f, "http error: {err}"),
            IhpClientError::Decode(msg) => write!(f, "protocol decode failed: {msg}"),
            IhpClientError::Parse(msg) => write!(f, "decode error: {msg}"),
            IhpClientError::Crypto(err) => write!(f, "crypto error: {err}"),
        }
    }
}

impl std::error::Error for IhpClientError {}

impl From<reqwest::Error> for IhpClientError {
    fn from(err: reqwest::Error) -> Self {
        IhpClientError::Http(err)
    fn from(value: reqwest::Error) -> Self {
        IhpClientError::Http(value)
    }
}

impl From<IhpError> for IhpClientError {
    fn from(err: IhpError) -> Self {
        IhpClientError::Crypto(err)
    }
}

#[derive(serde::Deserialize)]
struct ProfileResponse {
    version: u8,
    server_profile_id: String,
    server_env_hash_b64: String,
    expected_rtt_buckets: [u8; 2],
    supported_aead: Vec<String>,
}

fn trim_base_url(base_url: &str) -> String {
    base_url.trim_end_matches('/').to_string()
}

/// Fetch and deserialize `/ihp/profile` from the provided base URL.
pub async fn fetch_ihp_profile(base_url: &str) -> Result<IhpServerProfile, IhpClientError> {
    let base = trim_base_url(base_url);
    let url = format!("{base}/ihp/profile");
    let client = Client::new();
    let raw: ProfileResponse = client
        .get(url)
    fn from(value: IhpError) -> Self {
        IhpClientError::Crypto(value)
    }
}

#[derive(Debug, Deserialize)]
struct ProfileResponse {
    version: u8,
    server_profile_id: String,
    expected_rtt_buckets: [u8; 2],
    supported_aead: Vec<String>,
    server_env_hash_b64: String,
}

/// Fetch `/ihp/profile` from the target server.
pub async fn fetch_ihp_profile(base_url: &str) -> Result<IhpServerProfile, IhpClientError> {
    let normalized = base_url.trim_end_matches('/').to_string();
    let url = format!("{normalized}/ihp/profile");
    let response: ProfileResponse = Client::new()
        .get(&url)
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?;
    let version = ProtocolVersion::from_wire(raw.version)
        .ok_or_else(|| IhpClientError::Decode("unsupported protocol version".into()))?;
    let server_profile_id = raw
        .server_profile_id
        .parse::<u64>()
        .map(ServerProfileId)
        .map_err(|_| IhpClientError::Decode("invalid server_profile_id".into()))?;
    let env_hash_bytes = STANDARD
        .decode(raw.server_env_hash_b64)
        .map_err(|_| IhpClientError::Decode("invalid env hash encoding".into()))?;
    let env_hash: [u8; 32] = env_hash_bytes
        .try_into()
        .map_err(|_| IhpClientError::Decode("env hash length mismatch".into()))?;

    Ok(IhpServerProfile {
        base_url: base,
        version,
        server_profile_id,
        server_env_hash: ServerEnvHash(env_hash),
        expected_rtt_buckets: raw.expected_rtt_buckets,
        supported_aead: raw.supported_aead,
    })
}

/// Measure a small number of HTTP round trips and bucketize the RTT into a coarse u8.
///
/// The current heuristic averages four HEAD requests to `/ihp/profile`, converts the average
/// latency in milliseconds into a bucket by dividing by two, rounding to the nearest integer, and
/// clamping to `[0, 255]`. The mapping is intentionally simple, deterministic, and documented so
/// it can be replaced with production-grade telemetry later.
pub async fn measure_rtt_bucket(base_url: &str) -> Result<u8, IhpClientError> {
    const SAMPLES: usize = 4;
    const MS_PER_BUCKET: f64 = 2.0;

    let client = Client::new();
    let url = format!("{}/ihp/profile", trim_base_url(base_url));
    let mut total = 0f64;
    for _ in 0..SAMPLES {
        let start = Instant::now();
        let resp = client.head(&url).send().await?;
        // Fall back to GET if the server does not support HEAD.
        if resp.status().is_client_error() {
            client.get(&url).send().await?.error_for_status()?;
        } else {
            resp.error_for_status()?;
        }
        total += start.elapsed().as_secs_f64() * 1000.0;
    }
    let avg_ms = total / SAMPLES as f64;
    let bucket = ((avg_ms / MS_PER_BUCKET).round() as i64).clamp(0, 255) as u8;
    Ok(bucket)
}

/// Build an [`IhpCapsule`] for the provided password material using a previously derived profile key.

    let server_profile_id = response
        .server_profile_id
        .parse::<u64>()
        .map_err(|_| IhpClientError::Parse("server_profile_id must be numeric".into()))?;
    let env_hash_bytes = STANDARD
        .decode(response.server_env_hash_b64)
        .map_err(|_| IhpClientError::Parse("server_env_hash_b64 was not valid base64".into()))?;
    let env_hash: [u8; 32] = env_hash_bytes
        .try_into()
        .map_err(|_| IhpClientError::Parse("server_env_hash_b64 length invalid".into()))?;

    Ok(IhpServerProfile {
        base_url: normalized,
        version: response.version,
        server_profile_id: ServerProfileId(server_profile_id),
        expected_rtt_buckets: response.expected_rtt_buckets,
        supported_aead: response.supported_aead,
        server_env_hash: ServerEnvHash(env_hash),
    })
}

/// Measure RTT to the server and map it into a coarse bucket.
pub async fn measure_rtt_bucket(base_url: &str) -> Result<u8, IhpClientError> {
    let normalized = base_url.trim_end_matches('/').to_string();
    let url = format!("{normalized}/ihp/profile");
    let client = Client::new();
    let mut samples = Vec::with_capacity(RTT_SAMPLES);

    for _ in 0..RTT_SAMPLES {
        let start = Instant::now();
        let response = client.get(&url).send().await?;
        response.error_for_status_ref()?;
        samples.push(start.elapsed().as_secs_f64());
    }

    let avg_secs = samples.iter().copied().sum::<f64>() / samples.len() as f64;
    let avg_ms = avg_secs * 1_000.0;
    let bucket = (avg_ms / RTT_MS_PER_BUCKET).round();
    let clamped = bucket.clamp(0.0, 255.0) as u8;
    Ok(clamped)
}

/// Tunables used when building a capsule without making additional network calls.
#[derive(Debug, Clone)]
pub struct CapsuleBuildOptions {
    pub rtt_bucket_override: Option<u8>,
    pub path_hint: u16,
    pub header_id_override: Option<u64>,
}

impl Default for CapsuleBuildOptions {
    fn default() -> Self {
        Self {
            rtt_bucket_override: None,
            path_hint: DEFAULT_PATH_HINT,
            header_id_override: None,
        }
    }
}

/// Build a capsule using live RTT measurements and randomized client metadata.
pub async fn build_capsule_for_password(
    server_profile: &IhpServerProfile,
    password_bytes: &[u8],
    tls_exporter_key: &[u8],
    k_profile: &[u8],
    now_timestamp: i64,
) -> Result<IhpCapsule, IhpError> {
    let mut rng = OsRng;
    let client_nonce: ClientNonce = generate_client_nonce(&mut rng);
    let header_id: u64 = rng.next_u64();
    let rtt_bucket = measure_rtt_bucket(&server_profile.base_url)
        .await
        .map_err(|err| IhpError::Config(format!("rtt measurement failed: {err}")))?;

    let profile_bytes: [u8; crate::KEY_BYTES] =
        k_profile.try_into().map_err(|_| IhpError::KeyLength)?;
    let k_profile = ProfileKey::from_bytes(profile_bytes);

    let network_context = IhpNetworkContext {
        rtt_bucket,
        path_hint: 120,
    };
    let labels = CryptoDomainLabels::default();
    let k_session: SessionKey = derive_session_key(
        &k_profile,
    k_profile: &ProfileKey,
    now_timestamp: i64,
) -> Result<IhpCapsule, IhpClientError> {
    let rtt_bucket = measure_rtt_bucket(&server_profile.base_url).await?;
    build_capsule_for_password_with_options(
        server_profile,
        password_bytes,
        tls_exporter_key,
        k_profile,
        now_timestamp,
        CapsuleBuildOptions {
            rtt_bucket_override: Some(rtt_bucket),
            ..CapsuleBuildOptions::default()
        },
    )
    .await
}

/// Build a capsule while allowing tests to pin the RTT bucket and header ID for determinism.
pub async fn build_capsule_for_password_with_options(
    server_profile: &IhpServerProfile,
    password_bytes: &[u8],
    tls_exporter_key: &[u8],
    k_profile: &ProfileKey,
    now_timestamp: i64,
    options: CapsuleBuildOptions,
) -> Result<IhpCapsule, IhpClientError> {
    let mut rng = OsRng;
    build_capsule_internal(
        server_profile,
        password_bytes,
        tls_exporter_key,
        k_profile,
        now_timestamp,
        options,
        &mut rng,
    )
    .await
}

async fn build_capsule_internal(
    server_profile: &IhpServerProfile,
    password_bytes: &[u8],
    tls_exporter_key: &[u8],
    k_profile: &ProfileKey,
    now_timestamp: i64,
    options: CapsuleBuildOptions,
    rng: &mut (impl RngCore + CryptoRng),
) -> Result<IhpCapsule, IhpClientError> {
    let version =
        ProtocolVersion::from_wire(server_profile.version).ok_or(IhpError::InvalidVersion)?;
    let rtt_bucket = match options.rtt_bucket_override {
        Some(bucket) => bucket,
        None => measure_rtt_bucket(&server_profile.base_url).await?,
    };
    let path_hint = options.path_hint;
    let header_id = options.header_id_override.unwrap_or_else(|| rng.next_u64());

    let client_nonce = generate_client_nonce(rng);
    let network_context = IhpNetworkContext {
        rtt_bucket,
        path_hint,
    };
    let labels = CryptoDomainLabels::default();
    let k_session = derive_session_key(
        k_profile,
        tls_exporter_key,
        &client_nonce,
        &network_context,
        server_profile.server_profile_id,
        &labels,
    )?;

    let config = IhpConfig::default();
    let password_material = PasswordMaterial::new(password_bytes)?;
    let timestamp = CapsuleTimestamp::new(now_timestamp)?;

    encrypt_capsule(
        server_profile.version,
    let password_material = PasswordMaterial::new(password_bytes)?;
    let timestamp = CapsuleTimestamp::new(now_timestamp)?;
    let config = IhpConfig::default();

    encrypt_capsule(
        version,
        &config,
        header_id,
        client_nonce,
        server_profile.server_profile_id,
        network_context,
        &server_profile.server_env_hash,
        &k_session,
        &password_material,
        timestamp,
    )
    .map_err(IhpClientError::from)
}
