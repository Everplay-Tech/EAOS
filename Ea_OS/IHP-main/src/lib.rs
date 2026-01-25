#![forbid(unsafe_code)]

//! Industrial-grade IHP capsule implementation with hardened cryptographic hygiene.
//!
//! The library provides version-aware encryption and decryption backed by HKDF and
//! AEAD with strict zeroization guarantees. Observability hooks (tracing + metrics)
//! are gated behind the `observability` feature to keep the hot path minimal while
//! still enabling production-grade telemetry when desired.

pub mod client;
pub mod server;

pub use client::{
    CapsuleBuildOptions, DEFAULT_PATH_HINT, IhpClientError, IhpServerProfile,
    build_capsule_for_password, build_capsule_for_password_with_options, fetch_ihp_profile,
    measure_rtt_bucket,
};

use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::{Aes256Gcm, Nonce as AesNonce};
use blake3::Hasher;
use hkdf::Hkdf;
use rand_core::{CryptoRng, RngCore};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use std::collections::HashSet;
use std::fmt;
use std::sync::Arc;
#[cfg(test)]
use std::sync::atomic::{AtomicBool, Ordering};
use subtle::ConstantTimeEq;
use zeroize::{Zeroize, Zeroizing};

#[cfg(feature = "observability")]
use metrics::{counter, histogram};
#[cfg(feature = "observability")]
use tracing::{info, instrument};

/// Default protocol version for this crate.
pub const DEFAULT_PROTOCOL_VERSION: ProtocolVersion = ProtocolVersion::V1;
/// Default allowable timestamp drift in seconds when validating capsules.
pub const DEFAULT_MAX_TIMESTAMP_DRIFT_SECONDS: i64 = 300;
/// Maximum payload bytes accepted by the library.
pub const MAX_PAYLOAD_BYTES: usize = 64 * 1024;
/// Maximum allowed fingerprint bytes to guard against unbounded inputs.
pub const MAX_FINGERPRINT_BYTES: usize = 4 * 1024;
/// Upper bound for caller-configured drift to avoid runaway values.
pub const MAX_TIMESTAMP_DRIFT_CAP_SECONDS: i64 = 7 * 86_400;
/// Domain separator injected into AAD to prevent cross-protocol misuse.
pub const AAD_DOMAIN: &[u8] = b"IHP_CAPSULE_AAD:v1";

/// Telemetry-friendly reason codes for instrumentation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TelemetryCode {
    AeadTagInvalid,
    TimestampStale,
    HeaderIdMismatch,
    VersionUnsupported,
    KeyLength,
    ConfigRejected,
    CodecError,
    NonceReuse,
    NonceCollision,
}

/// Error variants surfaced by the IHP implementation. Sensitive material never appears in
/// `Display` or `Debug`.
#[derive(Debug, PartialEq, Eq)]
pub enum IhpError {
    InvalidAeadTag,
    StaleTimestamp,
    HeaderIdMismatch,
    InvalidVersion,
    KeyLength,
    Config(String),
    Codec(String),
    NonceReuse,
    NonceCollision,
    KeyDerivation,
    InvalidNonceLength,
    InvalidTimestamp,
}

impl IhpError {
    /// Map errors to telemetry codes without revealing secrets.
    pub fn to_telemetry(&self) -> TelemetryCode {
        match self {
            IhpError::InvalidAeadTag => TelemetryCode::AeadTagInvalid,
            IhpError::StaleTimestamp => TelemetryCode::TimestampStale,
            IhpError::HeaderIdMismatch => TelemetryCode::HeaderIdMismatch,
            IhpError::InvalidVersion => TelemetryCode::VersionUnsupported,
            IhpError::KeyLength => TelemetryCode::KeyLength,
            IhpError::Config(_) => TelemetryCode::ConfigRejected,
            IhpError::Codec(_) => TelemetryCode::CodecError,
            IhpError::NonceReuse => TelemetryCode::NonceReuse,
            IhpError::NonceCollision => TelemetryCode::NonceCollision,
            IhpError::KeyDerivation => TelemetryCode::KeyLength,
            IhpError::InvalidNonceLength | IhpError::InvalidTimestamp => {
                TelemetryCode::ConfigRejected
            }
        }
    }
}

impl fmt::Display for IhpError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let msg = match self {
            IhpError::InvalidAeadTag => "AEAD authentication failed",
            IhpError::StaleTimestamp => "capsule timestamp outside allowed drift",
            IhpError::HeaderIdMismatch => "plaintext header_id mismatch",
            IhpError::InvalidVersion => "capsule version not supported",
            IhpError::KeyLength => "invalid key length",
            IhpError::Config(_) => "configuration rejected",
            IhpError::Codec(_) => "encoding or decoding failure",
            IhpError::NonceReuse => "nonce reuse detected",
            IhpError::NonceCollision => "nonce collision detected",
            IhpError::KeyDerivation => "hkdf expansion failed",
            IhpError::InvalidNonceLength => "nonce length mismatch",
            IhpError::InvalidTimestamp => "timestamp out of range",
        };
        write!(f, "{msg}")
    }
}

impl std::error::Error for IhpError {}

/// Protocol version enumeration with explicit experimental gating.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ProtocolVersion {
    V1,
    #[cfg(feature = "experimental_v2")]
    ExperimentalV2,
}

impl ProtocolVersion {
    pub fn as_u8(&self) -> u8 {
        match self {
            ProtocolVersion::V1 => 1,
            #[cfg(feature = "experimental_v2")]
            ProtocolVersion::ExperimentalV2 => 2,
        }
    }

    pub fn from_wire(value: u8) -> Option<Self> {
        match value {
            1 => Some(ProtocolVersion::V1),
            #[cfg(feature = "experimental_v2")]
            2 => Some(ProtocolVersion::ExperimentalV2),
            _ => None,
        }
    }
}

/// Maximum allowable timestamp drift to protect clocks from misconfiguration.
pub const MAX_ALLOWED_DRIFT_SECONDS: i64 = 7 * 86_400;
/// Bytes in a symmetric key.
pub const KEY_BYTES: usize = 32;
/// Nonce size for AES-GCM.
pub const NONCE_LEN: usize = 12;

/// Zeroized secret key material used across the IHP protocol.
#[derive(Clone)]
pub struct SecretKey {
    inner: Zeroizing<[u8; KEY_BYTES]>,
    #[cfg(test)]
    drop_witness: Option<Arc<AtomicBool>>,
}

impl SecretKey {
    pub fn new(bytes: [u8; KEY_BYTES]) -> Self {
        Self {
            inner: Zeroizing::new(bytes),
            #[cfg(test)]
            drop_witness: None,
        }
    }

    pub fn from_hsm(bytes: Zeroizing<[u8; KEY_BYTES]>) -> Self {
        Self {
            inner: bytes,
            #[cfg(test)]
            drop_witness: None,
        }
    }

    pub(crate) fn expose(&self) -> &[u8; KEY_BYTES] {
        &self.inner
    }

    #[cfg(test)]
    pub fn new_with_witness(bytes: [u8; KEY_BYTES], witness: Arc<AtomicBool>) -> Self {
        Self {
            inner: Zeroizing::new(bytes),
            drop_witness: Some(witness),
        }
    }
}

impl Drop for SecretKey {
    fn drop(&mut self) {
        self.inner.zeroize();
        #[cfg(test)]
        if let Some(flag) = &self.drop_witness {
            flag.store(true, Ordering::SeqCst);
        }
    }
}

impl fmt::Debug for SecretKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("SecretKey")
            .field("bytes", &"[REDACTED]")
            .finish()
    }
}

/// Domain-specific key wrappers to prevent accidental interchange.
#[derive(Clone)]
pub struct MasterKey(SecretKey);

#[derive(Clone)]
pub struct ProfileKey(SecretKey);

#[derive(Clone)]
pub struct SessionKey(SecretKey);

impl MasterKey {
    pub fn new(bytes: [u8; KEY_BYTES]) -> Self {
        Self(SecretKey::new(bytes))
    }

    pub fn from_hsm(bytes: Zeroizing<[u8; KEY_BYTES]>) -> Self {
        Self(SecretKey::from_hsm(bytes))
    }

    pub(crate) fn expose(&self) -> &[u8; KEY_BYTES] {
        self.0.expose()
    }
}

impl ProfileKey {
    fn new(secret: SecretKey) -> Self {
        Self(secret)
    }

    pub fn from_bytes(bytes: [u8; KEY_BYTES]) -> Self {
        Self(SecretKey::new(bytes))
    }

    pub(crate) fn expose(&self) -> &[u8; KEY_BYTES] {
        self.0.expose()
    }
}

impl SessionKey {
    fn new(secret: SecretKey) -> Self {
        Self(secret)
    }

    pub fn from_bytes(bytes: [u8; KEY_BYTES]) -> Self {
        Self(SecretKey::new(bytes))
    }

    pub(crate) fn expose(&self) -> &[u8; KEY_BYTES] {
        self.0.expose()
    }
}

impl fmt::Debug for MasterKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("MasterKey").field(&"[REDACTED]").finish()
    }
}

impl fmt::Debug for ProfileKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("ProfileKey").field(&"[REDACTED]").finish()
    }
}

impl fmt::Debug for SessionKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("SessionKey").field(&"[REDACTED]").finish()
    }
}

/// Zeroized nonce wrapper for AEAD operations.
#[derive(Clone)]
pub struct SecretNonce<const N: usize> {
    inner: Zeroizing<[u8; N]>,
    #[cfg(test)]
    drop_witness: Option<Arc<AtomicBool>>,
}

impl<const N: usize> SecretNonce<N> {
    pub fn try_from_slice(bytes: &[u8]) -> Result<Self, IhpError> {
        if bytes.len() != N {
            return Err(IhpError::InvalidNonceLength);
        }
        let mut arr = [0u8; N];
        arr.copy_from_slice(bytes);
        Ok(Self {
            inner: Zeroizing::new(arr),
            #[cfg(test)]
            drop_witness: None,
        })
    }

    pub fn from_array(bytes: [u8; N]) -> Self {
        Self {
            inner: Zeroizing::new(bytes),
            #[cfg(test)]
            drop_witness: None,
        }
    }

    pub fn expose(&self) -> &[u8; N] {
        &self.inner
    }

    #[cfg(test)]
    pub fn new_with_witness(bytes: [u8; N], witness: Arc<AtomicBool>) -> Self {
        Self {
            inner: Zeroizing::new(bytes),
            drop_witness: Some(witness),
        }
    }
}

impl<const N: usize> fmt::Debug for SecretNonce<N> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("SecretNonce").field(&"[REDACTED]").finish()
    }
}

impl<const N: usize> Drop for SecretNonce<N> {
    fn drop(&mut self) {
        self.inner.zeroize();
        #[cfg(test)]
        if let Some(flag) = &self.drop_witness {
            flag.store(true, Ordering::SeqCst);
        }
    }
}

/// Client-provided nonce that seeds session key derivations and AEAD nonces.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ClientNonce([u8; NONCE_LEN]);

impl ClientNonce {
    pub fn new(bytes: [u8; NONCE_LEN]) -> Self {
        Self(bytes)
    }

    pub fn try_from_slice(bytes: &[u8]) -> Result<Self, IhpError> {
        if bytes.len() != NONCE_LEN {
            return Err(IhpError::InvalidNonceLength);
        }
        let mut arr = [0u8; NONCE_LEN];
        arr.copy_from_slice(bytes);
        Ok(Self(arr))
    }

    pub fn as_array(&self) -> &[u8; NONCE_LEN] {
        &self.0
    }
}

/// Generate a random client nonce with a caller-provided RNG to enable deterministic testing.
pub fn generate_client_nonce(rng: &mut (impl RngCore + CryptoRng)) -> ClientNonce {
    let mut bytes = [0u8; NONCE_LEN];
    rng.fill_bytes(&mut bytes);
    ClientNonce::new(bytes)
}

/// Timestamp wrapper that documents the capsule creation time in seconds since the Unix epoch.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct CapsuleTimestamp(i64);

impl CapsuleTimestamp {
    pub fn new(timestamp: i64) -> Result<Self, IhpError> {
        if timestamp == i64::MIN {
            return Err(IhpError::InvalidTimestamp);
        }
        Ok(Self(timestamp))
    }

    pub fn value(&self) -> i64 {
        self.0
    }
}

/// Password material with bound checking to avoid unbounded allocations.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PasswordMaterial(Zeroizing<Vec<u8>>);

impl PasswordMaterial {
    pub fn new(bytes: impl AsRef<[u8]>) -> Result<Self, IhpError> {
        let data = bytes.as_ref();
        if data.len() > MAX_PAYLOAD_BYTES {
            return Err(IhpError::Codec("password material too large".into()));
        }
        Ok(Self(Zeroizing::new(data.to_vec())))
    }

    pub fn as_slice(&self) -> &[u8] {
        &self.0
    }
}

/// Configurable maximum allowable timestamp drift for decryptions.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct MaxDrift(i64);

impl MaxDrift {
    pub fn new(seconds: i64) -> Result<Self, IhpError> {
        if seconds.is_negative() || seconds > MAX_TIMESTAMP_DRIFT_CAP_SECONDS {
            return Err(IhpError::InvalidTimestamp);
        }
        Ok(Self(seconds))
    }

    pub fn seconds(&self) -> i64 {
        self.0
    }
}

/// Server environment attributes used to bind keys to a specific host profile.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ServerEnvironmentProfile {
    pub cpu_fingerprint: String,
    pub nic_fingerprint: String,
    pub os_fingerprint: String,
    pub app_build_fingerprint: String,
    pub tpm_quote: Option<Vec<u8>>,
}

impl ServerEnvironmentProfile {
    pub fn validate(&self, max_len: usize) -> Result<(), IhpError> {
        let parts = [
            self.cpu_fingerprint.as_bytes(),
            self.nic_fingerprint.as_bytes(),
            self.os_fingerprint.as_bytes(),
            self.app_build_fingerprint.as_bytes(),
        ];
        if parts.iter().any(|p| p.len() > max_len) {
            return Err(IhpError::Codec("server fingerprint too long".into()));
        }
        if let Some(quote) = &self.tpm_quote {
            if quote.len() > max_len {
                return Err(IhpError::Codec("tpm quote too long".into()));
            }
        }
        Ok(())
    }
}

/// Hash of a server environment profile.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ServerEnvHash(pub [u8; 32]);

impl ServerEnvHash {
    pub fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }
}

/// Short identifier used to reference a stored server environment hash.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ServerProfileId(pub u64);

/// Network context used when deriving per-session keys.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct IhpNetworkContext {
    pub rtt_bucket: u8,
    pub path_hint: u16,
}

impl IhpNetworkContext {
    pub fn validate(&self) -> Result<(), IhpError> {
        if self.rtt_bucket > 255 {
            return Err(IhpError::Codec("rtt bucket out of range".into()));
        }
        if self.path_hint == 0 {
            return Err(IhpError::Codec("path_hint must be non-zero".into()));
        }
        Ok(())
    }
}

/// Supported AEAD implementations.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AeadAlgorithm {
    Aes256Gcm,
}

/// Explicit configuration passed to encryption and decryption entrypoints.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IhpConfig {
    pub max_timestamp_drift: MaxDrift,
    pub allowed_versions: HashSet<ProtocolVersion>,
    pub aead_algorithm: AeadAlgorithm,
    pub max_payload_bytes: usize,
    pub max_fingerprint_bytes: usize,
}

impl Default for IhpConfig {
    fn default() -> Self {
        let mut allowed_versions = HashSet::new();
        allowed_versions.insert(DEFAULT_PROTOCOL_VERSION);
        Self {
            max_timestamp_drift: MaxDrift::new(DEFAULT_MAX_TIMESTAMP_DRIFT_SECONDS)
                .expect("default drift fits cap"),
            allowed_versions,
            aead_algorithm: AeadAlgorithm::Aes256Gcm,
            max_payload_bytes: MAX_PAYLOAD_BYTES,
            max_fingerprint_bytes: MAX_FINGERPRINT_BYTES,
        }
    }
}

impl IhpConfig {
    pub fn builder() -> IhpConfigBuilder {
        IhpConfigBuilder::default()
    }

    pub fn is_version_allowed(&self, version: ProtocolVersion) -> bool {
        self.allowed_versions.contains(&version)
    }

    pub fn validate(&self) -> Result<(), IhpError> {
        if self.allowed_versions.is_empty() {
            return Err(IhpError::Config("no protocol versions allowed".into()));
        }
        if self.max_timestamp_drift.seconds() < 0
            || self.max_timestamp_drift.seconds() > MAX_TIMESTAMP_DRIFT_CAP_SECONDS
        {
            return Err(IhpError::Config("timestamp drift out of bounds".into()));
        }
        if self.max_payload_bytes == 0 || self.max_payload_bytes > MAX_PAYLOAD_BYTES {
            return Err(IhpError::Config("payload length out of bounds".into()));
        }
        if self.max_fingerprint_bytes == 0 || self.max_fingerprint_bytes > MAX_FINGERPRINT_BYTES {
            return Err(IhpError::Config("fingerprint length out of bounds".into()));
        }
        Ok(())
    }
}

/// Builder for [`IhpConfig`].
#[derive(Debug, Default)]
pub struct IhpConfigBuilder {
    max_timestamp_drift: Option<MaxDrift>,
    allowed_versions: Option<HashSet<ProtocolVersion>>,
    aead_algorithm: Option<AeadAlgorithm>,
    max_payload_bytes: Option<usize>,
    max_fingerprint_bytes: Option<usize>,
}

impl IhpConfigBuilder {
    pub fn max_timestamp_drift(mut self, seconds: i64) -> Result<Self, IhpError> {
        self.max_timestamp_drift = Some(MaxDrift::new(seconds)?);
        Ok(self)
    }

    pub fn allowed_versions(mut self, versions: HashSet<ProtocolVersion>) -> Self {
        self.allowed_versions = Some(versions);
        self
    }

    pub fn aead_algorithm(mut self, algorithm: AeadAlgorithm) -> Self {
        self.aead_algorithm = Some(algorithm);
        self
    }

    pub fn max_payload_bytes(mut self, max_payload_bytes: usize) -> Self {
        self.max_payload_bytes = Some(max_payload_bytes);
        self
    }

    pub fn max_fingerprint_bytes(mut self, max_fingerprint_bytes: usize) -> Self {
        self.max_fingerprint_bytes = Some(max_fingerprint_bytes);
        self
    }

    pub fn build(self) -> IhpConfig {
        let allowed_versions = self
            .allowed_versions
            .unwrap_or_else(|| HashSet::from([DEFAULT_PROTOCOL_VERSION]));
        IhpConfig {
            max_timestamp_drift: self.max_timestamp_drift.unwrap_or_else(|| {
                MaxDrift::new(DEFAULT_MAX_TIMESTAMP_DRIFT_SECONDS).expect("default drift fits cap")
            }),
            allowed_versions,
            aead_algorithm: self.aead_algorithm.unwrap_or(AeadAlgorithm::Aes256Gcm),
            max_payload_bytes: self.max_payload_bytes.unwrap_or(MAX_PAYLOAD_BYTES),
            max_fingerprint_bytes: self.max_fingerprint_bytes.unwrap_or(MAX_FINGERPRINT_BYTES),
        }
    }
}

/// Compute a hash over a server environment profile using BLAKE3.
pub fn compute_server_env_hash(sep: &ServerEnvironmentProfile) -> Result<ServerEnvHash, IhpError> {
    compute_server_env_hash_with_limit(sep, MAX_FINGERPRINT_BYTES)
}

pub fn compute_server_env_hash_with_limit(
    sep: &ServerEnvironmentProfile,
    max_len: usize,
) -> Result<ServerEnvHash, IhpError> {
    sep.validate(max_len)?;
    let mut hasher = Hasher::new();
    hasher.update(sep.cpu_fingerprint.as_bytes());
    hasher.update(&[0u8]);
    hasher.update(sep.nic_fingerprint.as_bytes());
    hasher.update(&[0u8]);
    hasher.update(sep.os_fingerprint.as_bytes());
    hasher.update(&[0u8]);
    hasher.update(sep.app_build_fingerprint.as_bytes());
    hasher.update(&[0u8]);
    match &sep.tpm_quote {
        Some(quote) => {
            hasher.update(&[1u8]);
            hasher.update(quote);
        }
        None => {
            hasher.update(&[0u8]);
        }
    }
    let hash = hasher.finalize();
    Ok(ServerEnvHash(*hash.as_bytes()))
}

/// Compute a server environment hash using the bounds specified in an [`IhpConfig`].
pub fn compute_server_env_hash_for_config(
    sep: &ServerEnvironmentProfile,
    config: &IhpConfig,
) -> Result<ServerEnvHash, IhpError> {
    compute_server_env_hash_with_limit(sep, config.max_fingerprint_bytes)
}

/// Validate a server environment profile using an [`IhpConfig`] before hashing.
pub fn compute_server_env_hash_checked(
    sep: &ServerEnvironmentProfile,
    config: &IhpConfig,
) -> Result<ServerEnvHash, IhpError> {
    compute_server_env_hash_for_config(sep, config)
}

/// Source of master key material (in-memory or HSM/KMS backed).
pub trait MasterKeyProvider: Send + Sync {
    fn fetch_master(&self) -> Result<MasterKey, IhpError>;
}

/// Provider that derives keys through HKDF expansions and zeroizes outputs automatically.
pub trait KeyProvider: Send + Sync {
    fn profile_key(
        &self,
        server_profile_id: ServerProfileId,
        server_env_hash: &ServerEnvHash,
        labels: &CryptoDomainLabels,
    ) -> Result<ProfileKey, IhpError>;

    fn session_key(
        &self,
        k_profile: &ProfileKey,
        derivation: &SessionDerivation<'_>,
        labels: &CryptoDomainLabels,
    ) -> Result<SessionKey, IhpError>;
}

/// HKDF-backed key provider that can wrap HSM- or memory-backed master keys.
pub struct HkdfKeyProvider<T: MasterKeyProvider> {
    master: Arc<T>,
}

impl<T: MasterKeyProvider> HkdfKeyProvider<T> {
    pub fn new(master: T) -> Self {
        Self {
            master: Arc::new(master),
        }
    }
}

/// In-memory key source primarily for testing.
pub struct InMemoryKeyProvider {
    key: MasterKey,
}

impl InMemoryKeyProvider {
    pub fn new(bytes: [u8; KEY_BYTES]) -> Self {
        Self {
            key: MasterKey::new(bytes),
        }
    }

    pub fn from_hsm_wrapped(bytes: Zeroizing<[u8; KEY_BYTES]>) -> Self {
        Self {
            key: MasterKey::from_hsm(bytes),
        }
    }
}

impl MasterKeyProvider for InMemoryKeyProvider {
    fn fetch_master(&self) -> Result<MasterKey, IhpError> {
        Ok(self.key.clone())
    }
}

/// HKDF labels grouped for domain separation so that profile and session derivations
/// cannot be confused or mixed with other protocol steps.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CryptoDomainLabels {
    pub hkdf_profile: &'static [u8],
    pub hkdf_session: &'static [u8],
}

impl Default for CryptoDomainLabels {
    fn default() -> Self {
        Self {
            hkdf_profile: b"IHP_PROFILE_KEY:v1",
            hkdf_session: b"IHP_SESSION_KEY:v1",
        }
    }
}

/// Inputs required to derive a session key while avoiding unnecessary copies.
pub struct SessionDerivation<'a> {
    pub tls_exporter_key: &'a [u8],
    pub client_nonce: ClientNonce,
    pub network_context: IhpNetworkContext,
    pub server_profile_id: ServerProfileId,
}

impl<'a> SessionDerivation<'a> {
    pub fn validate(&self) -> Result<(), IhpError> {
        self.network_context.validate()
    }
}

fn hkdf_expand(label: &[u8], salt: &[u8], ikm: &[u8]) -> Result<SecretKey, IhpError> {
    let hk = Hkdf::<Sha256>::new(Some(salt), ikm);
    let mut okm = [0u8; KEY_BYTES];
    hk.expand(label, &mut okm)
        .map_err(|_| IhpError::KeyDerivation)?;
    Ok(SecretKey::new(okm))
}

fn derive_profile_key_inner(
    master: &MasterKey,
    server_env_hash: &ServerEnvHash,
    labels: &CryptoDomainLabels,
) -> Result<ProfileKey, IhpError> {
    let derived = hkdf_expand(
        labels.hkdf_profile,
        server_env_hash.as_bytes(),
        master.expose(),
    )?;

    #[cfg(feature = "observability")]
    info!("derived profile key");

    Ok(ProfileKey::new(derived))
}

/// Derive a session key bound to TLS exporter material and network context.
fn derive_session_key_inner(
    k_profile: &ProfileKey,
    derivation: &SessionDerivation<'_>,
    labels: &CryptoDomainLabels,
) -> Result<SessionKey, IhpError> {
    derivation.validate()?;
    let mut info = Vec::with_capacity(32);
    info.extend_from_slice(labels.hkdf_session);
    info.extend_from_slice(derivation.client_nonce.as_array());
    info.push(derivation.network_context.rtt_bucket);
    info.extend_from_slice(&derivation.network_context.path_hint.to_le_bytes());
    info.extend_from_slice(&derivation.server_profile_id.0.to_le_bytes());
    let secret = hkdf_expand(&info, k_profile.expose(), derivation.tls_exporter_key)?;
    Ok(SessionKey::new(secret))
}

impl<T: MasterKeyProvider> KeyProvider for HkdfKeyProvider<T> {
    #[cfg_attr(feature = "observability", instrument(skip_all))]
    fn profile_key(
        &self,
        _server_profile_id: ServerProfileId,
        server_env_hash: &ServerEnvHash,
        labels: &CryptoDomainLabels,
    ) -> Result<ProfileKey, IhpError> {
        let master = self.master.fetch_master()?;
        derive_profile_key_inner(&master, server_env_hash, labels)
    }

    #[cfg_attr(feature = "observability", instrument(skip_all))]
    fn session_key(
        &self,
        k_profile: &ProfileKey,
        derivation: &SessionDerivation<'_>,
        labels: &CryptoDomainLabels,
    ) -> Result<SessionKey, IhpError> {
        derive_session_key_inner(k_profile, derivation, labels)
    }
}

/// Shared context bundling configuration, domain labels, and key providers.
#[derive(Clone)]
pub struct IhpContext<P: KeyProvider> {
    config: IhpConfig,
    key_provider: Arc<P>,
    labels: CryptoDomainLabels,
}

impl<P: KeyProvider> IhpContext<P> {
    pub fn new(config: IhpConfig, key_provider: P) -> Result<Self, IhpError> {
        config.validate()?;
        Ok(Self {
            config,
            key_provider: Arc::new(key_provider),
            labels: CryptoDomainLabels::default(),
        })
    }

    pub fn config(&self) -> &IhpConfig {
        &self.config
    }

    pub fn derive_profile_key(
        &self,
        server_profile_id: ServerProfileId,
        server_env_hash: &ServerEnvHash,
    ) -> Result<ProfileKey, IhpError> {
        self.key_provider
            .profile_key(server_profile_id, server_env_hash, &self.labels)
    }

    pub fn derive_session_key(
        &self,
        k_profile: &ProfileKey,
        derivation: SessionDerivation<'_>,
    ) -> Result<SessionKey, IhpError> {
        self.key_provider
            .session_key(k_profile, &derivation, &self.labels)
    }
}

/// Derive a profile key bound to a server environment hash using a master-key source.
#[cfg_attr(
    feature = "observability",
    instrument(skip_all, fields(profile_id = server_profile_id.0))
)]
pub fn derive_profile_key(
    provider: &dyn MasterKeyProvider,
    _server_profile_id: ServerProfileId,
    server_env_hash: &ServerEnvHash,
    labels: &CryptoDomainLabels,
) -> Result<ProfileKey, IhpError> {
    let master = provider.fetch_master()?;
    derive_profile_key_inner(&master, server_env_hash, labels)
}

/// Derive a session key bound to TLS exporter material and network context.
#[cfg_attr(
    feature = "observability",
    instrument(skip_all, fields(profile_id = server_profile_id.0))
)]
pub fn derive_session_key(
    k_profile: &ProfileKey,
    tls_exporter_key: &[u8],
    client_nonce: &ClientNonce,
    network_context: &IhpNetworkContext,
    server_profile_id: ServerProfileId,
    labels: &CryptoDomainLabels,
) -> Result<SessionKey, IhpError> {
    let derivation = SessionDerivation {
        tls_exporter_key,
        client_nonce: *client_nonce,
        network_context: *network_context,
        server_profile_id,
    };
    derive_session_key_inner(k_profile, &derivation, labels)
}

/// Assemble authenticated data with explicit domain separation and versioning.
fn build_aad(
    version: ProtocolVersion,
    server_profile_id: ServerProfileId,
    network_context: IhpNetworkContext,
    server_env_hash: &ServerEnvHash,
) -> Vec<u8> {
    let mut aad = Vec::with_capacity(AAD_DOMAIN.len() + 1 + 8 + 1 + 2 + 32);
    aad.extend_from_slice(AAD_DOMAIN);
    aad.push(version.as_u8());
    aad.extend_from_slice(&server_profile_id.0.to_le_bytes());
    aad.push(network_context.rtt_bucket);
    aad.extend_from_slice(&network_context.path_hint.to_le_bytes());
    aad.extend_from_slice(server_env_hash.as_bytes());
    aad
}

fn constant_time_equal(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.ct_eq(b).into()
}

fn encode_plaintext(
    password_material: &PasswordMaterial,
    timestamp: CapsuleTimestamp,
    header_id: u64,
    max_payload_bytes: usize,
) -> Result<Vec<u8>, IhpError> {
    if password_material.as_slice().len() > max_payload_bytes {
        return Err(IhpError::Codec("password material too large".into()));
    }
    let mut out =
        Vec::with_capacity(4 + password_material.as_slice().len() + std::mem::size_of::<u32>());
    let password_len: u32 = password_material
        .as_slice()
        .len()
        .try_into()
        .map_err(|_| IhpError::Codec("password_material too long".into()))?;
    out.extend_from_slice(&password_len.to_le_bytes());
    out.extend_from_slice(password_material.as_slice());
    out.extend_from_slice(&timestamp.value().to_le_bytes());
    out.extend_from_slice(&header_id.to_le_bytes());
    Ok(out)
}

fn decode_plaintext(bytes: &[u8], max_payload_bytes: usize) -> Result<IhpPlaintext, IhpError> {
    if bytes.len() < 4 + 8 + 8 {
        return Err(IhpError::Codec("buffer too short".into()));
    }
    let password_len = u32::from_le_bytes(bytes[0..4].try_into().unwrap()) as usize;
    let expected_len = 4 + password_len + 8 + 8;
    if password_len > max_payload_bytes || bytes.len() != expected_len {
        return Err(IhpError::Codec("length mismatch".into()));
    }
    let password_material = PasswordMaterial::new(&bytes[4..4 + password_len])?;
    let timestamp_offset = 4 + password_len;
    let timestamp = i64::from_le_bytes(
        bytes[timestamp_offset..timestamp_offset + 8]
            .try_into()
            .unwrap(),
    );
    let header_id = u64::from_le_bytes(bytes[timestamp_offset + 8..].try_into().unwrap());
    let timestamp = CapsuleTimestamp::new(timestamp)?;
    Ok(IhpPlaintext {
        password_material,
        timestamp,
        header_id,
    })
}

fn select_cipher(algorithm: AeadAlgorithm, key: &SessionKey) -> Result<Aes256Gcm, IhpError> {
    match algorithm {
        AeadAlgorithm::Aes256Gcm => {
            Aes256Gcm::new_from_slice(key.expose()).map_err(|_| IhpError::KeyDerivation)
        }
    }
}

fn encrypt_inner(
    algorithm: AeadAlgorithm,
    aad: &[u8],
    nonce: &SecretNonce<NONCE_LEN>,
    key: &SessionKey,
    plaintext_bytes: &[u8],
) -> Result<Vec<u8>, IhpError> {
    let cipher = select_cipher(algorithm, key)?;
    let nonce = AesNonce::from_slice(nonce.expose());
    cipher
        .encrypt(
            nonce,
            Payload {
                msg: plaintext_bytes,
                aad,
            },
        )
        .map_err(|_| IhpError::InvalidAeadTag)
}

fn decrypt_inner(
    algorithm: AeadAlgorithm,
    aad: &[u8],
    nonce: &SecretNonce<NONCE_LEN>,
    key: &SessionKey,
    ciphertext: &[u8],
) -> Result<Vec<u8>, IhpError> {
    let cipher = select_cipher(algorithm, key)?;
    let nonce = AesNonce::from_slice(nonce.expose());
    cipher
        .decrypt(
            nonce,
            Payload {
                msg: ciphertext,
                aad,
            },
        )
        .map_err(|_| IhpError::InvalidAeadTag)
}

/// Ciphertext container for IHP metadata and protected payload.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IhpCapsule {
    pub version: u8,
    pub header_id: u64,
    pub client_nonce: [u8; NONCE_LEN],
    pub server_profile_id: ServerProfileId,
    pub network_context: IhpNetworkContext,
    pub payload: Vec<u8>,
}

/// Decrypted content carried inside an [`IhpCapsule`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IhpPlaintext {
    pub password_material: PasswordMaterial,
    pub timestamp: CapsuleTimestamp,
    pub header_id: u64,
}

/// Encrypt a plaintext into an [`IhpCapsule`] using AES-256-GCM.
#[cfg_attr(
    feature = "observability",
    instrument(
        level = "info",
        skip_all,
        fields(version = %version.as_u8(), server_profile_id = server_profile_id.0)
    )
)]
pub fn encrypt_capsule(
    version: ProtocolVersion,
    config: &IhpConfig,
    header_id: u64,
    client_nonce: ClientNonce,
    server_profile_id: ServerProfileId,
    network_context: IhpNetworkContext,
    server_env_hash: &ServerEnvHash,
    k_session: &SessionKey,
    password_material: &PasswordMaterial,
    timestamp: CapsuleTimestamp,
) -> Result<IhpCapsule, IhpError> {
    network_context.validate()?;
    config.validate()?;
    if !config.is_version_allowed(version) {
        #[cfg(feature = "observability")]
        counter!(
            "ihp_version_mismatch_total",
            1,
            "version" => version.as_u8().to_string()
        );
        return Err(IhpError::InvalidVersion);
    }

    let plaintext_bytes = encode_plaintext(
        password_material,
        timestamp,
        header_id,
        config.max_payload_bytes,
    )?;

    let aad = build_aad(version, server_profile_id, network_context, server_env_hash);
    let nonce = SecretNonce::from_array(*client_nonce.as_array());
    let ciphertext = encrypt_inner(
        config.aead_algorithm,
        &aad,
        &nonce,
        k_session,
        &plaintext_bytes,
    )
    .map_err(|err| {
        #[cfg(feature = "observability")]
        counter!(
            "ihp.encrypt.failure",
            1,
            "code" => format!("{:?}", err.to_telemetry())
        );
        err
    })?;

    #[cfg(feature = "observability")]
    {
        counter!(
            "ihp_encrypt_success_total",
            1,
            "version" => version.as_u8().to_string()
        );
    }

    Ok(IhpCapsule {
        version: version.as_u8(),
        header_id,
        client_nonce: *client_nonce.as_array(),
        server_profile_id,
        network_context,
        payload: ciphertext,
    })
}

/// Decrypt an [`IhpCapsule`] and validate protocol invariants.
#[cfg_attr(
    feature = "observability",
    instrument(
        level = "info",
        skip_all,
        fields(version = capsule.version, server_profile_id = capsule.server_profile_id.0)
    )
)]
pub fn decrypt_capsule(
    capsule: &IhpCapsule,
    server_env_hash: &ServerEnvHash,
    k_session: &SessionKey,
    now_timestamp: CapsuleTimestamp,
    config: &IhpConfig,
) -> Result<IhpPlaintext, IhpError> {
    config.validate()?;
    let Some(version) = ProtocolVersion::from_wire(capsule.version) else {
        #[cfg(feature = "observability")]
        counter!(
            "ihp_version_mismatch_total",
            1,
            "version" => capsule.version.to_string()
        );
        return Err(IhpError::InvalidVersion);
    };

    capsule.network_context.validate()?;
    if !config.is_version_allowed(version) {
        #[cfg(feature = "observability")]
        counter!(
            "ihp_version_mismatch_total",
            1,
            "version" => version.as_u8().to_string()
        );
        return Err(IhpError::InvalidVersion);
    }

    let nonce = SecretNonce::from_array(capsule.client_nonce);
    let aad = build_aad(
        version,
        capsule.server_profile_id,
        capsule.network_context,
        server_env_hash,
    );

    let decrypted = decrypt_inner(
        config.aead_algorithm,
        &aad,
        &nonce,
        k_session,
        &capsule.payload,
    )
    .map_err(|err| {
        #[cfg(feature = "observability")]
        counter!(
            "ihp.decrypt.failure",
            1,
            "code" => format!("{:?}", err.to_telemetry())
        );
        err
    })?;
    let plaintext = decode_plaintext(&decrypted, config.max_payload_bytes)?;

    let header_match = constant_time_equal(
        &plaintext.header_id.to_le_bytes(),
        &capsule.header_id.to_le_bytes(),
    );
    if !header_match {
        #[cfg(feature = "observability")]
        counter!("ihp.decrypt.header_mismatch", 1);
        return Err(IhpError::HeaderIdMismatch);
    }

    let drift = (now_timestamp.value() - plaintext.timestamp.value()).abs();
    if drift > config.max_timestamp_drift.seconds() {
        #[cfg(feature = "observability")]
        counter!("ihp.decrypt.drift_rejected", 1);
        return Err(IhpError::StaleTimestamp);
    }

    #[cfg(feature = "observability")]
    {
        counter!("ihp.decrypt.success", 1, "version" => version.as_u8().to_string());
        histogram!("ihp.drift.seconds", drift as f64);
    }

    Ok(plaintext)
}

/// Known-good serialized capsules for compatibility detection.
pub const GOLDEN_CAPSULE_V1: &str = include_str!("../golden_capsule_v1.json");

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;
    use serde_json::{from_str, to_string};
    use std::sync::atomic::{AtomicBool, Ordering};

    const KAT_MASTER_KEY: [u8; KEY_BYTES] = *b"IHP deterministic master keyseed";
    const KAT_TLS_EXPORTER: &[u8] = b"tls exporter key material";
    const KAT_PASSWORD: &[u8] = b"known-answer";
    const KAT_CLIENT_NONCE: [u8; NONCE_LEN] = [1u8; NONCE_LEN];
    const KAT_ENV_HASH: ServerEnvHash = ServerEnvHash([0x42u8; 32]);
    const KAT_PROFILE_KEY: [u8; KEY_BYTES] = [
        42, 87, 168, 215, 162, 203, 208, 176, 143, 241, 155, 11, 138, 69, 87, 171, 168, 242, 63,
        32, 21, 128, 131, 231, 55, 133, 142, 185, 93, 4, 220, 225,
    ];
    const KAT_SESSION_KEY: [u8; KEY_BYTES] = [
        208, 221, 46, 68, 101, 92, 115, 181, 231, 1, 50, 96, 236, 54, 48, 137, 215, 87, 120, 82,
        195, 171, 96, 230, 41, 9, 220, 65, 45, 68, 140, 199,
    ];
    const KAT_CIPHERTEXT: [u8; 48] = [
        77, 180, 95, 53, 4, 122, 217, 216, 60, 13, 133, 11, 184, 237, 42, 196, 187, 206, 228, 12,
        190, 92, 8, 56, 188, 52, 183, 96, 165, 69, 86, 233, 44, 203, 254, 8, 235, 135, 49, 8, 87,
        9, 148, 233, 14, 171, 139, 83,
    ];

    #[derive(Default)]
    struct CountingHsmProvider {
        loads: Arc<std::sync::Mutex<u32>>,
        key: [u8; 32],
    }

    impl CountingHsmProvider {
        fn new(key: [u8; 32]) -> Self {
            Self {
                loads: Arc::new(std::sync::Mutex::new(0)),
                key,
            }
        }

        fn load_count(&self) -> u32 {
            *self.loads.lock().unwrap()
        }
    }

    impl MasterKeyProvider for CountingHsmProvider {
        fn fetch_master(&self) -> Result<MasterKey, IhpError> {
            *self.loads.lock().unwrap() += 1;
            Ok(MasterKey::new(self.key))
        }
    }

    fn sample_sep() -> ServerEnvironmentProfile {
        ServerEnvironmentProfile {
            cpu_fingerprint: "cpu:abcd".into(),
            nic_fingerprint: "nic:efgh".into(),
            os_fingerprint: "os:linux".into(),
            app_build_fingerprint: "build:1.0.0".into(),
            tpm_quote: Some(vec![1, 2, 3, 4]),
        }
    }

    fn base_keys(
        env_hash: &ServerEnvHash,
        rtt_bucket: u8,
    ) -> (ProfileKey, SessionKey, ClientNonce) {
        let provider = InMemoryKeyProvider::new(KAT_MASTER_KEY);
        let labels = CryptoDomainLabels::default();
        let k_profile =
            derive_profile_key(&provider, ServerProfileId(42), env_hash, &labels).expect("profile");
        let tls_exporter_key = b"tls exporter key material";
        let client_nonce = ClientNonce::new([7; NONCE_LEN]);
        let network_context = IhpNetworkContext {
            rtt_bucket,
            path_hint: 120,
        };
        let k_session = derive_session_key(
            &k_profile,
            tls_exporter_key,
            &client_nonce,
            &network_context,
            ServerProfileId(42),
            &labels,
        )
        .expect("session key");
        (k_profile, k_session, client_nonce)
    }

    fn capsule_round_trip() -> (IhpCapsule, SessionKey, CapsuleTimestamp, ServerEnvHash) {
        let sep = sample_sep();
        let env_hash = compute_server_env_hash(&sep).expect("hash");
        let (_, k_session, client_nonce) = base_keys(&env_hash, 7);
        let network_context = IhpNetworkContext {
            rtt_bucket: 7,
            path_hint: 120,
        };
        let timestamp = CapsuleTimestamp::new(1_700_000_000).expect("timestamp");
        let config = IhpConfig::default();
        let password = PasswordMaterial::new(b"super-secret").unwrap();

        let capsule = encrypt_capsule(
            DEFAULT_PROTOCOL_VERSION,
            &config,
            99,
            client_nonce,
            ServerProfileId(42),
            network_context,
            &env_hash,
            &k_session,
            &password,
            timestamp,
        )
        .expect("encrypt capsule");

        (capsule, k_session, timestamp, env_hash)
    }

    #[test]
    fn round_trip_success() {
        let (capsule, k_session, timestamp, env_hash) = capsule_round_trip();
        let config = IhpConfig::default();
        let plaintext = decrypt_capsule(&capsule, &env_hash, &k_session, timestamp, &config)
            .expect("decrypt capsule");
        assert_eq!(plaintext.password_material.as_slice(), b"super-secret");
        assert_eq!(plaintext.header_id, 99);
    }

    #[test]
    fn fails_with_wrong_env_hash() {
        let (capsule, k_session, timestamp, _) = capsule_round_trip();
        let wrong_env_hash = ServerEnvHash([9u8; 32]);
        let config = IhpConfig::default();
        let result = decrypt_capsule(&capsule, &wrong_env_hash, &k_session, timestamp, &config);
        assert!(matches!(result, Err(IhpError::InvalidAeadTag)));
    }

    #[test]
    fn fails_on_header_id_tamper() {
        let (mut capsule, k_session, timestamp, env_hash) = capsule_round_trip();
        capsule.header_id ^= 1;
        let config = IhpConfig::default();
        let result = decrypt_capsule(&capsule, &env_hash, &k_session, timestamp, &config);
        assert!(matches!(result, Err(IhpError::HeaderIdMismatch)));
    }

    #[test]
    fn client_nonce_length_validated() {
        assert!(matches!(
            ClientNonce::try_from_slice(&[0u8; NONCE_LEN - 1]),
            Err(IhpError::InvalidNonceLength)
        ));
    }

    #[test]
    fn fingerprint_validation_blocks_long_values() {
        let mut sep = sample_sep();
        sep.cpu_fingerprint = "x".repeat(MAX_FINGERPRINT_BYTES + 1);
        let err = compute_server_env_hash(&sep).unwrap_err();
        assert!(matches!(err, IhpError::Codec(_)));
    }

    #[test]
    fn contexts_do_not_leak_config() {
        let sep = sample_sep();
        let env_hash = compute_server_env_hash(&sep).unwrap();
        let (_, k_session, client_nonce) = base_keys(&env_hash, 1);
        let network_context = IhpNetworkContext {
            rtt_bucket: 1,
            path_hint: 10,
        };
        let timestamp = CapsuleTimestamp::new(1_700_000_000).unwrap();
        let now = CapsuleTimestamp::new(1_700_000_005).unwrap();
        let lenient = IhpConfig::default();
        let strict = IhpConfig::builder().max_timestamp_drift(0).unwrap().build();
        let password = PasswordMaterial::new(b"tightrope").unwrap();
        let capsule = encrypt_capsule(
            DEFAULT_PROTOCOL_VERSION,
            &lenient,
            5,
            client_nonce,
            ServerProfileId(7),
            network_context,
            &env_hash,
            &k_session,
            &password,
            timestamp,
        )
        .unwrap();
        decrypt_capsule(&capsule, &env_hash, &k_session, now, &lenient).unwrap();
        let strict_result = decrypt_capsule(&capsule, &env_hash, &k_session, now, &strict);
        assert!(matches!(strict_result, Err(IhpError::StaleTimestamp)));
        decrypt_capsule(&capsule, &env_hash, &k_session, now, &lenient).unwrap();
    }

    #[test]
    fn oversized_payload_is_rejected() {
        let sep = sample_sep();
        let env_hash = compute_server_env_hash(&sep).unwrap();
        let (_, k_session, client_nonce) = base_keys(&env_hash, 3);
        let network_context = IhpNetworkContext {
            rtt_bucket: 3,
            path_hint: 11,
        };
        let config = IhpConfig::builder().max_payload_bytes(4).build();
        let password = PasswordMaterial::new(&[1u8; 8]).unwrap();
        let result = encrypt_capsule(
            DEFAULT_PROTOCOL_VERSION,
            &config,
            77,
            client_nonce,
            ServerProfileId(9),
            network_context,
            &env_hash,
            &k_session,
            &password,
            CapsuleTimestamp::new(1_700_000_001).unwrap(),
        );
        assert!(matches!(result, Err(IhpError::Codec(_))));
    }

    #[test]
    fn rejects_unknown_version_byte() {
        let (mut capsule, k_session, timestamp, env_hash) = capsule_round_trip();
        capsule.version = 99;
        let config = IhpConfig::default();
        let result = decrypt_capsule(&capsule, &env_hash, &k_session, timestamp, &config);
        assert!(matches!(result, Err(IhpError::InvalidVersion)));
    }

    #[test]
    fn aad_domain_is_stable() {
        let aad = build_aad(
            DEFAULT_PROTOCOL_VERSION,
            ServerProfileId(5),
            IhpNetworkContext {
                rtt_bucket: 7,
                path_hint: 120,
            },
            &ServerEnvHash([5u8; 32]),
        );
        let mut expected = b"IHP_CAPSULE_AAD:v1".to_vec();
        expected.push(DEFAULT_PROTOCOL_VERSION.as_u8());
        expected.extend_from_slice(&5u64.to_le_bytes());
        expected.push(7);
        expected.extend_from_slice(&120u16.to_le_bytes());
        expected.extend_from_slice(&[5u8; 32]);
        assert_eq!(aad, expected);
    }

    #[test]
    fn ciphertext_tamper_is_detected() {
        let (mut capsule, k_session, timestamp, env_hash) = capsule_round_trip();
        capsule.payload[0] ^= 0xAA;
        let config = IhpConfig::default();
        let result = decrypt_capsule(&capsule, &env_hash, &k_session, timestamp, &config);
        assert!(matches!(result, Err(IhpError::InvalidAeadTag)));
    }

    #[test]
    fn secret_material_zeroizes_on_drop() {
        let flag = Arc::new(AtomicBool::new(false));
        {
            let key = SecretKey::new_with_witness([0xAA; KEY_BYTES], flag.clone());
            assert_eq!(key.expose()[0], 0xAA);
        }
        assert!(flag.load(Ordering::SeqCst));
    }

    #[test]
    fn nonce_zeroizes_on_drop() {
        let flag = Arc::new(AtomicBool::new(false));
        {
            let nonce = SecretNonce::<NONCE_LEN>::new_with_witness([0x11; NONCE_LEN], flag.clone());
            assert_eq!(nonce.expose()[0], 0x11);
        }
        assert!(flag.load(Ordering::SeqCst));
    }

    #[test]
    fn hsm_provider_is_invoked() {
        let provider = CountingHsmProvider::new(KAT_MASTER_KEY);
        let labels = CryptoDomainLabels::default();
        let env_hash = ServerEnvHash([1u8; 32]);
        let _ = derive_profile_key(&provider, ServerProfileId(7), &env_hash, &labels).unwrap();
        let _ = derive_profile_key(&provider, ServerProfileId(8), &env_hash, &labels).unwrap();
        assert_eq!(provider.load_count(), 2);
    }

    #[test]
    fn hkdf_key_provider_invokes_master_loader() {
        let provider = CountingHsmProvider::new(KAT_MASTER_KEY);
        let load_counter = provider.loads.clone();
        let hkdf_provider = HkdfKeyProvider::new(provider);
        let env_hash = compute_server_env_hash(&sample_sep()).unwrap();
        let ctx = IhpContext::new(IhpConfig::default(), hkdf_provider).unwrap();
        let k_profile = ctx
            .derive_profile_key(ServerProfileId(9), &env_hash)
            .expect("profile key");
        let derivation = SessionDerivation {
            tls_exporter_key: b"tls exporter key material",
            client_nonce: ClientNonce::new([1u8; NONCE_LEN]),
            network_context: IhpNetworkContext {
                rtt_bucket: 4,
                path_hint: 77,
            },
            server_profile_id: ServerProfileId(9),
        };
        let _ = ctx
            .derive_session_key(&k_profile, derivation)
            .expect("session key");
        assert_eq!(*load_counter.lock().unwrap(), 1);
    }

    #[test]
    fn config_allows_version_list() {
        let mut allowed = HashSet::new();
        allowed.insert(DEFAULT_PROTOCOL_VERSION);
        #[cfg(feature = "experimental_v2")]
        {
            allowed.insert(ProtocolVersion::ExperimentalV2);
        }
        let config = IhpConfig::builder().allowed_versions(allowed).build();
        assert!(config.is_version_allowed(DEFAULT_PROTOCOL_VERSION));
    }

    #[test]
    fn golden_fixture_round_trip() {
        let capsule: IhpCapsule = serde_json::from_str(GOLDEN_CAPSULE_V1).expect("fixture");
        let encoded = to_string(&capsule).unwrap();
        let decoded: IhpCapsule = from_str(&encoded).unwrap();
        assert_eq!(capsule, decoded);
    }

    #[test]
    fn golden_fixture_decrypts() {
        let capsule: IhpCapsule = serde_json::from_str(GOLDEN_CAPSULE_V1).expect("fixture");
        let session = SessionKey::new(SecretKey::new(KAT_SESSION_KEY));
        let plaintext = decrypt_capsule(
            &capsule,
            &KAT_ENV_HASH,
            &session,
            CapsuleTimestamp::new(1_700_000_123).unwrap(),
            &IhpConfig::default(),
        )
        .unwrap();
        assert_eq!(plaintext.password_material.as_slice(), KAT_PASSWORD);
        assert_eq!(plaintext.header_id, 44);
    }

    #[test]
    fn hkdf_known_answers_are_stable() {
        let labels = CryptoDomainLabels::default();
        let provider = InMemoryKeyProvider::new(KAT_MASTER_KEY);
        let profile =
            derive_profile_key(&provider, ServerProfileId(1), &KAT_ENV_HASH, &labels).unwrap();
        assert_eq!(profile.expose(), &KAT_PROFILE_KEY);
        let client_nonce = ClientNonce::new(KAT_CLIENT_NONCE);
        let network_context = IhpNetworkContext {
            rtt_bucket: 5,
            path_hint: 120,
        };
        let session = derive_session_key(
            &profile,
            KAT_TLS_EXPORTER,
            &client_nonce,
            &network_context,
            ServerProfileId(1),
            &labels,
        )
        .unwrap();
        assert_eq!(session.expose(), &KAT_SESSION_KEY);
    }

    #[test]
    fn ciphertext_known_answer_matches_fixture() {
        let labels = CryptoDomainLabels::default();
        let provider = InMemoryKeyProvider::new(KAT_MASTER_KEY);
        let profile =
            derive_profile_key(&provider, ServerProfileId(1), &KAT_ENV_HASH, &labels).unwrap();
        let client_nonce = ClientNonce::new(KAT_CLIENT_NONCE);
        let network_context = IhpNetworkContext {
            rtt_bucket: 5,
            path_hint: 120,
        };
        let session = derive_session_key(
            &profile,
            KAT_TLS_EXPORTER,
            &client_nonce,
            &network_context,
            ServerProfileId(1),
            &labels,
        )
        .unwrap();
        let password = PasswordMaterial::new(KAT_PASSWORD).unwrap();
        let capsule = encrypt_capsule(
            DEFAULT_PROTOCOL_VERSION,
            &IhpConfig::default(),
            44,
            client_nonce,
            ServerProfileId(1),
            network_context,
            &KAT_ENV_HASH,
            &session,
            &password,
            CapsuleTimestamp::new(1_700_000_123).unwrap(),
        )
        .unwrap();
        assert_eq!(capsule.payload.as_slice(), &KAT_CIPHERTEXT);
        let plaintext = decrypt_capsule(
            &capsule,
            &KAT_ENV_HASH,
            &session,
            CapsuleTimestamp::new(1_700_000_123).unwrap(),
            &IhpConfig::default(),
        )
        .unwrap();
        assert_eq!(plaintext.password_material.as_slice(), KAT_PASSWORD);
    }

    #[test]
    fn config_validation_enforces_bounds() {
        let mut config = IhpConfig::default();
        config.allowed_versions.clear();
        assert!(config.validate().is_err());
        let too_big_payload = IhpConfig {
            max_payload_bytes: MAX_PAYLOAD_BYTES + 1,
            ..IhpConfig::default()
        };
        assert!(too_big_payload.validate().is_err());
    }

    proptest! {
        #[test]
        fn proptest_round_trip(payload in prop::collection::vec(any::<u8>(), 0..64), header_id in any::<u64>()) {
            let sep = sample_sep();
            let env_hash = compute_server_env_hash(&sep).unwrap();
            let (_, k_session, client_nonce) = base_keys(&env_hash, 5);
            let network_context = IhpNetworkContext { rtt_bucket: 5, path_hint: 42 };
            let timestamp = CapsuleTimestamp::new(1_700_000_000).unwrap();
            let config = IhpConfig::default();
            let material = PasswordMaterial::new(&payload).unwrap();
            let capsule = encrypt_capsule(
                DEFAULT_PROTOCOL_VERSION,
                &config,
                header_id,
                client_nonce,
                ServerProfileId(1),
                network_context,
                &env_hash,
                &k_session,
                &material,
                timestamp,
            ).unwrap();
            let plaintext = decrypt_capsule(&capsule, &env_hash, &k_session, timestamp, &config).unwrap();
            assert_eq!(plaintext.password_material.as_slice(), payload.as_slice());
            assert_eq!(plaintext.header_id, header_id);
        }

        #[test]
        fn proptest_detects_tamper(payload in prop::collection::vec(any::<u8>(), 0..64), header_id in any::<u64>()) {
            let sep = sample_sep();
            let env_hash = compute_server_env_hash(&sep).unwrap();
            let (_, k_session, client_nonce) = base_keys(&env_hash, 5);
            let network_context = IhpNetworkContext { rtt_bucket: 5, path_hint: 42 };
            let timestamp = CapsuleTimestamp::new(1_700_000_000).unwrap();
            let config = IhpConfig::default();
            let material = PasswordMaterial::new(&payload).unwrap();
            let mut capsule = encrypt_capsule(
                DEFAULT_PROTOCOL_VERSION,
                &config,
                header_id,
                client_nonce,
                ServerProfileId(1),
                network_context,
                &env_hash,
                &k_session,
                &material,
                timestamp,
            ).unwrap();
            capsule.payload[0] ^= 0xAA;
            let tampered = decrypt_capsule(&capsule, &env_hash, &k_session, timestamp, &config);
            prop_assert!(tampered.is_err());
        }
    }
}
