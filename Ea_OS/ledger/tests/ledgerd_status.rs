use assert_cmd::prelude::*;
use std::fs::File;
use std::io::Write;
use std::process::{Command, Stdio};
use std::time::Duration;
use tempfile::tempdir;

use ledger_spec::{ChannelPolicy, ChannelSpec, Envelope, EnvelopeBody, EnvelopeHeader};

mod support;
use support::{ledgerd_bin, unix_socket_supported, wait_for_path};

fn available_status_port() -> Option<u16> {
    std::net::TcpListener::bind("127.0.0.1:0")
        .and_then(|listener| listener.local_addr())
        .map(|addr| addr.port())
        .ok()
}

#[test]
fn metrics_and_health_endpoints_respond() -> Result<(), Box<dyn std::error::Error>> {
    if !unix_socket_supported() {
        eprintln!("skipping status endpoint test: unix sockets not permitted");
        return Ok(());
    }
    let temp = tempdir()?;
    let socket_path = temp.path().join("ledger.sock");
    let registry_path = temp.path().join("registry.json");
    let envelope_path = temp.path().join("env.json");

    // Registry with a single channel that uses the default policy.
    let registry = vec![ChannelSpec {
        name: "ipc_demo".into(),
        policy: ChannelPolicy::default(),
    }];
    let mut reg_file = File::create(&registry_path)?;
    reg_file.write_all(serde_json::to_string(&registry)?.as_bytes())?;

    // Seed envelope that will be signed by the CLI when appended.
    let env = Envelope {
        header: EnvelopeHeader {
            channel: "ipc_demo".into(),
            version: 1,
            prev: None,
            body_hash: ledger_spec::hash_body(&EnvelopeBody {
                payload: serde_json::json!({"hello": "world"}),
                payload_type: Some("test".into()),
            }),
            timestamp: 1,
        },
        body: EnvelopeBody {
            payload: serde_json::json!({"hello": "world"}),
            payload_type: Some("test".into()),
        },
        signatures: Vec::new(),
        attestations: Vec::new(),
    };
    let mut env_file = File::create(&envelope_path)?;
    serde_json::to_writer(&mut env_file, &env)?;

    let Some(status_port) = available_status_port() else {
        eprintln!("skipping status endpoint test: tcp bind not permitted");
        return Ok(());
    };

    // Start daemon bound to the Unix socket.
    let mut daemon = Command::new(ledgerd_bin())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .arg("--transport")
        .arg("unix")
        .arg("--unix-path")
        .arg(&socket_path)
        .arg("--registry")
        .arg(&registry_path)
        .arg("--status-addr")
        .arg(format!("127.0.0.1:{status_port}"))
        .arg("daemon")
        .arg("--checkpoint")
        .arg("2")
        .spawn()?;

    wait_for_path(&socket_path, Duration::from_secs(2))?;
    std::thread::sleep(Duration::from_millis(200));

    // Append via CLI.
    Command::new(ledgerd_bin())
        .arg("--transport")
        .arg("unix")
        .arg("--unix-path")
        .arg(&socket_path)
        .arg("--registry")
        .arg(&registry_path)
        .arg("append")
        .arg("--file")
        .arg(&envelope_path)
        .assert()
        .success();

    // Poll metrics endpoint.
    let metrics_body =
        reqwest::blocking::get(format!("http://127.0.0.1:{status_port}/metrics"))?.text()?;
    assert!(
        metrics_body.contains("ledgerd_appends_total"),
        "metrics body missing expected counter"
    );

    // Poll health endpoint.
    let health: serde_json::Value =
        reqwest::blocking::get(format!("http://127.0.0.1:{status_port}/healthz"))?.json()?;
    assert_eq!(health["status"], "ok");
    assert!(
        health["log_length"].as_u64().unwrap_or(0) >= 1,
        "expected log length to be at least 1"
    );

    let _ = daemon.kill();
    let _ = daemon.wait();
    Ok(())
}
