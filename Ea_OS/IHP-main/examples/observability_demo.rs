//! Demonstrates IHP observability features: tracing and metrics.
//!
//! This example shows how to:
//! 1. Enable tracing with tracing-subscriber
//! 2. Set up metrics collection (Prometheus-compatible)
//! 3. Observe IHP operations through spans and metrics
//!
//! Run with: `cargo run --example observability_demo --features observability`

#[cfg(not(feature = "observability"))]
fn main() {
    eprintln!("This example requires the 'observability' feature.");
    eprintln!("Run with: cargo run --example observability_demo --features observability");
    std::process::exit(1);
}

#[cfg(feature = "observability")]
fn main() -> Result<(), Box<dyn std::error::Error>> {
    use std::time::{SystemTime, UNIX_EPOCH};
    use ihp::*;
    use tracing_subscriber::{fmt, EnvFilter};

    // Initialize tracing subscriber
    // Set RUST_LOG=debug to see detailed spans
    tracing_subscriber::registry()
        .with(fmt::layer().with_target(false))
        .with(EnvFilter::from_default_env())
        .init();

    tracing::info!("Starting IHP observability demo");

    // Set up a simple metrics recorder (in production, use Prometheus or OpenTelemetry)
    // For this demo, we'll just print metrics as they're emitted
    metrics::set_boxed_recorder(Box::new(PrintRecorder))
        .expect("metrics recorder already installed");

    // Create a sample server environment profile
    let sep = ServerEnvironmentProfile {
        cpu_fingerprint: "cpu:demo".into(),
        nic_fingerprint: "nic:demo".into(),
        os_fingerprint: "os:demo".into(),
        app_build_fingerprint: "build:demo".into(),
        tpm_quote: None,
    };

    let env_hash = compute_server_env_hash(&sep)?;
    let server_profile_id = ServerProfileId(1);
    let config = IhpConfig::default();
    let labels = CryptoDomainLabels::default();

    // Derive keys (this will emit tracing spans)
    tracing::info!("Deriving profile and session keys");
    let provider = InMemoryKeyProvider::new(*b"master key material for ihp proto*");
    let k_profile = derive_profile_key(&provider, server_profile_id, &env_hash, &labels)?;

    let client_nonce = ClientNonce::new([1u8; NONCE_LEN]);
    let network_context = IhpNetworkContext {
        rtt_bucket: 5,
        path_hint: 120,
    };
    let tls_exporter_key = b"tls exporter key material";
    let k_session = derive_session_key(
        &k_profile,
        tls_exporter_key,
        &client_nonce,
        &network_context,
        server_profile_id,
        &labels,
    )?;

    // Encrypt a capsule (this will emit metrics and spans)
    tracing::info!("Encrypting capsule");
    let password = PasswordMaterial::new(b"demo-password")?;
    let now_secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)?
        .as_secs() as i64;
    let timestamp = CapsuleTimestamp::new(now_secs)?;

    let capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        &config,
        12345,
        client_nonce,
        server_profile_id,
        network_context,
        &env_hash,
        &k_session,
        &password,
        timestamp,
    )?;

    tracing::info!("Capsule encrypted successfully");

    // Decrypt the capsule (this will also emit metrics and spans)
    tracing::info!("Decrypting capsule");
    let plaintext = decrypt_capsule(
        &capsule,
        &env_hash,
        &k_session,
        timestamp,
        &config,
    )?;

    tracing::info!(
        "Decryption successful, payload length: {}",
        plaintext.password_material.as_slice().len()
    );

    // Demonstrate error metrics by attempting decryption with wrong key
    tracing::info!("Demonstrating error metrics with wrong key");
    let wrong_key = SessionKey::from_bytes([0u8; KEY_BYTES]);
    let _ = decrypt_capsule(
        &capsule,
        &env_hash,
        &wrong_key,
        timestamp,
        &config,
    );

    tracing::info!("Demo complete. Check metrics output above.");

    Ok(())
}

#[cfg(feature = "observability")]
use metrics::{Counter, Gauge, Histogram, Key, Metadata, Recorder, Unit};

#[cfg(feature = "observability")]
struct PrintRecorder;

#[cfg(feature = "observability")]
impl Recorder for PrintRecorder {
    fn describe_counter(&self, key: KeyName, unit: Option<Unit>, description: Option<&'static str>) {
        println!("[METRIC] Counter: {} ({:?}) - {:?}", key, unit, description);
    }

    fn describe_gauge(&self, key: KeyName, unit: Option<Unit>, description: Option<&'static str>) {
        println!("[METRIC] Gauge: {} ({:?}) - {:?}", key, unit, description);
    }

    fn describe_histogram(&self, key: KeyName, unit: Option<Unit>, description: Option<&'static str>) {
        println!("[METRIC] Histogram: {} ({:?}) - {:?}", key, unit, description);
    }

    fn register_counter(&self, key: &Key, _metadata: &Metadata<'_>) -> Counter {
        let key_str = key.to_string();
        Counter::from_arc(std::sync::Arc::new(move |value| {
            println!("[METRIC] Counter increment: {} += {}", key_str, value);
        }))
    }

    fn register_gauge(&self, key: &Key, _metadata: &Metadata<'_>) -> Gauge {
        let key_str = key.to_string();
        Gauge::from_arc(std::sync::Arc::new(move |value| {
            println!("[METRIC] Gauge set: {} = {}", key_str, value);
        }))
    }

    fn register_histogram(&self, key: &Key, _metadata: &Metadata<'_>) -> Histogram {
        let key_str = key.to_string();
        Histogram::from_arc(std::sync::Arc::new(move |value| {
            println!("[METRIC] Histogram record: {} = {}", key_str, value);
        }))
    }
}
