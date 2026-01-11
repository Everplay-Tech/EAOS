#![cfg(feature = "observability")]

use ihp::*;
use metrics::{Counter, Gauge, Histogram, Key, KeyName, Metadata, Recorder, Unit, counter};
use std::collections::HashMap;
use std::fmt;
use std::sync::{Arc, Mutex, OnceLock};
use tracing::field::{Field, Visit};
use tracing::subscriber::DefaultGuard;
use tracing::{Subscriber, subscriber::set_default};
use tracing_subscriber::Layer;
use tracing_subscriber::layer::{Context, SubscriberExt};
use tracing_subscriber::registry::LookupSpan;

#[derive(Debug, Clone, Default)]
struct CounterValue {
    name: String,
    counts: Arc<Mutex<HashMap<String, u64>>>,
}

impl metrics::counter::CounterFn for CounterValue {
    fn increment(&self, value: u64) {
        let mut guard = self.counts.lock().expect("counts poisoned");
        *guard.entry(self.name.clone()).or_default() += value;
    }

    fn absolute(&self, value: u64) {
        let mut guard = self.counts.lock().expect("counts poisoned");
        guard.insert(self.name.clone(), value);
    }
}

#[derive(Debug, Clone, Default)]
struct NoopGauge;

impl metrics::gauge::GaugeFn for NoopGauge {
    fn set(&self, _value: f64) {}
    fn increment(&self, _value: f64) {}
    fn decrement(&self, _value: f64) {}
}

#[derive(Debug, Clone, Default)]
struct NoopHistogram;

impl metrics::histogram::HistogramFn for NoopHistogram {
    fn record(&self, _value: f64) {}
}

#[derive(Clone, Default)]
struct TestRecorder {
    counters: Arc<Mutex<HashMap<String, u64>>>,
}

impl TestRecorder {
    fn install() -> Arc<Self> {
        static RECORDER: OnceLock<Arc<TestRecorder>> = OnceLock::new();
        RECORDER
            .get_or_init(|| {
                let recorder = Arc::new(TestRecorder::default());
                metrics::set_boxed_recorder(Box::new(recorder.clone()))
                    .expect("recorder not yet installed");
                recorder
            })
            .clone()
    }

    fn counter_sum(&self, prefix: &str) -> u64 {
        let guard = self.counters.lock().expect("counts poisoned");
        guard
            .iter()
            .filter(|(name, _)| name.starts_with(prefix))
            .map(|(_, v)| *v)
            .sum()
    }

    fn reset(&self) {
        self.counters.lock().expect("counts poisoned").clear();
    }
}

impl Recorder for TestRecorder {
    fn describe_counter(
        &self,
        _key: KeyName,
        _unit: Option<Unit>,
        _description: Option<&'static str>,
    ) {
    }

    fn describe_gauge(
        &self,
        _key: KeyName,
        _unit: Option<Unit>,
        _description: Option<&'static str>,
    ) {
    }

    fn describe_histogram(
        &self,
        _key: KeyName,
        _unit: Option<Unit>,
        _description: Option<&'static str>,
    ) {
    }

    fn register_counter(&self, key: &Key, _metadata: &Metadata<'_>) -> Counter {
        let counter = CounterValue {
            name: key.to_string(),
            counts: self.counters.clone(),
        };
        Counter::from_arc(Arc::new(counter))
    }

    fn register_gauge(&self, _key: &Key, _metadata: &Metadata<'_>) -> Gauge {
        Gauge::from_arc(Arc::new(NoopGauge))
    }

    fn register_histogram(&self, _key: &Key, _metadata: &Metadata<'_>) -> Histogram {
        Histogram::from_arc(Arc::new(NoopHistogram))
    }
}

#[derive(Default, Clone)]
struct SpanRecord {
    name: String,
    fields: HashMap<String, String>,
}

#[derive(Default, Clone)]
struct SpanCollector {
    spans: Arc<Mutex<HashMap<u64, SpanRecord>>>,
}

impl SpanCollector {
    fn install(self) -> (Self, DefaultGuard) {
        let subscriber = tracing_subscriber::registry().with(self.clone());
        let guard = set_default(subscriber);
        (self, guard)
    }

    fn drain(&self) -> Vec<SpanRecord> {
        let mut guard = self.spans.lock().expect("spans poisoned");
        guard.values().cloned().collect()
    }
}

struct FieldRecorder<'a> {
    fields: &'a mut HashMap<String, String>,
}

impl Visit for FieldRecorder<'_> {
    fn record_debug(&mut self, field: &Field, value: &dyn fmt::Debug) {
        self.fields
            .insert(field.name().to_string(), format!("{value:?}"));
    }
}

impl<S> Layer<S> for SpanCollector
where
    S: Subscriber + for<'a> LookupSpan<'a>,
{
    fn on_new_span(
        &self,
        attrs: &tracing::span::Attributes<'_>,
        id: &tracing::span::Id,
        _ctx: Context<'_, S>,
    ) {
        let mut record = SpanRecord {
            name: attrs.metadata().name().to_string(),
            fields: HashMap::new(),
        };
        attrs.record(&mut FieldRecorder {
            fields: &mut record.fields,
        });
        self.spans
            .lock()
            .expect("spans poisoned")
            .insert(id.into_u64(), record);
    }

    fn on_record(
        &self,
        id: &tracing::span::Id,
        values: &tracing::span::Record<'_>,
        _ctx: Context<'_, S>,
    ) {
        if let Some(span) = self
            .spans
            .lock()
            .expect("spans poisoned")
            .get_mut(&id.into_u64())
        {
            values.record(&mut FieldRecorder {
                fields: &mut span.fields,
            });
        }
    }
}

fn sample_profile() -> ServerEnvironmentProfile {
    ServerEnvironmentProfile {
        cpu_fingerprint: "cpu".into(),
        nic_fingerprint: "nic".into(),
        os_fingerprint: "linux".into(),
        app_build_fingerprint: "build".into(),
        tpm_quote: Some(vec![1, 2, 3]),
    }
}

fn build_session(
    server_profile_id: ServerProfileId,
) -> (
    IhpConfig,
    ServerEnvHash,
    SessionKey,
    ClientNonce,
    IhpNetworkContext,
) {
    let config = IhpConfig::default();
    let sep = sample_profile();
    let env_hash = compute_server_env_hash_checked(&sep, &config).expect("env hash");
    let labels = CryptoDomainLabels::default();
    let provider = InMemoryKeyProvider::new(*b"master key material for ihp proto*");
    let profile =
        derive_profile_key(&provider, server_profile_id, &env_hash, &labels).expect("profile");
    let nonce = ClientNonce::new([7u8; NONCE_LEN]);
    let network = IhpNetworkContext {
        rtt_bucket: 3,
        path_hint: 11,
    };
    let session = derive_session_key(
        &profile,
        b"tls exporter key material",
        &nonce,
        &network,
        server_profile_id,
        &labels,
    )
    .expect("session");
    (config, env_hash, session, nonce, network)
}

#[test]
fn spans_capture_core_fields() {
    let recorder = TestRecorder::install();
    recorder.reset();
    let (collector, _guard) = SpanCollector::default().install();

    let (config, env_hash, session, nonce, network) = build_session(ServerProfileId(42));
    let material = PasswordMaterial::new(b"material").unwrap();
    let capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        &config,
        7,
        nonce,
        ServerProfileId(42),
        network,
        &env_hash,
        &session,
        &material,
        CapsuleTimestamp::new(1_700_000_123).unwrap(),
    )
    .expect("encryption succeeds");
    let _plaintext = decrypt_capsule(
        &capsule,
        &env_hash,
        &session,
        CapsuleTimestamp::new(1_700_000_200).unwrap(),
        &config,
    )
    .expect("decryption succeeds");

    let spans = collector.drain();
    let encrypt_span = spans
        .iter()
        .find(|span| span.name == "encrypt_capsule")
        .expect("encrypt span recorded");
    assert_eq!(encrypt_span.fields.get("version"), Some(&"1".to_string()));
    assert_eq!(
        encrypt_span.fields.get("server_profile_id"),
        Some(&"42".to_string())
    );
    let decrypt_span = spans
        .iter()
        .find(|span| span.name == "decrypt_capsule")
        .expect("decrypt span recorded");
    assert_eq!(decrypt_span.fields.get("version"), Some(&"1".to_string()));
    assert_eq!(
        decrypt_span.fields.get("server_profile_id"),
        Some(&"42".to_string())
    );
    assert_eq!(recorder.counter_sum("ihp_encrypt_success_total"), 1);
}

#[test]
fn version_mismatch_metrics_fire() {
    let recorder = TestRecorder::install();
    recorder.reset();
    let (config, env_hash, session, nonce, network) = build_session(ServerProfileId(9));
    let material = PasswordMaterial::new(b"payload").unwrap();
    let mut capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        &config,
        99,
        nonce,
        ServerProfileId(9),
        network,
        &env_hash,
        &session,
        &material,
        CapsuleTimestamp::new(1_700_000_321).unwrap(),
    )
    .expect("encryption succeeds");
    capsule.version = 255;
    let _ = decrypt_capsule(
        &capsule,
        &env_hash,
        &session,
        CapsuleTimestamp::new(1_700_000_400).unwrap(),
        &config,
    );
    assert_eq!(recorder.counter_sum("ihp_version_mismatch_total"), 1);
}
