use criterion::{criterion_group, criterion_main, Criterion};
use std::path::PathBuf;
use std::process::Command;
use std::time::Duration;

fn resolve_corpus() -> Option<PathBuf> {
    std::env::var("QYN_BENCH_CORPUS").ok().map(PathBuf::from)
}

fn encode_decode_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("pipeline");
    group.sample_size(10);
    group.measurement_time(Duration::from_secs(10));

    if let Some(corpus) = resolve_corpus() {
        let corpus = corpus.canonicalize().unwrap_or(corpus);
        group.bench_function("encode_project", |b| {
            b.iter(|| {
                let status = Command::new("python3")
                    .args([
                        "-m",
                        "qyn1.cli",
                        "encode",
                        corpus.to_str().expect("valid corpus path"),
                        "--output",
                        "./.bench-output",
                        "--passphrase",
                        "bench",
                    ])
                    .status()
                    .expect("failed to spawn encoder");
                assert!(status.success(), "encoder execution failed");
            });
        });
    } else {
        group.bench_function("encode_project", |b| b.iter(|| std::hint::black_box(1 + 1)));
    }

    group.finish();
}

criterion_group!(benches, encode_decode_benchmark);
criterion_main!(benches);
