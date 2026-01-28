use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

use hyperbolic_chamber::executor::perform_download;
use hyperbolic_chamber::manifest::DownloadStep;
use sha2::{Digest, Sha256};
use tempfile::tempdir;

fn start_server(
    body: Vec<u8>,
    response_delay: Option<Duration>,
    reported_length: Option<u64>,
) -> (thread::JoinHandle<()>, String) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("port bindable");
    let addr = listener.local_addr().expect("address available");
    let (ready_tx, ready_rx) = mpsc::channel();

    let handle = thread::spawn(move || {
        let _ = ready_tx.send(());
        if let Ok((mut stream, _)) = listener.accept() {
            if let Some(delay) = response_delay {
                thread::sleep(delay);
            }

            let mut buffer = [0u8; 512];
            let _ = stream.read(&mut buffer);

            let length = reported_length.unwrap_or(body.len() as u64);
            let header =
                format!("HTTP/1.1 200 OK\r\nContent-Length: {length}\r\nConnection: close\r\n\r\n");
            let _ = stream.write_all(header.as_bytes());
            let _ = stream.write_all(&body);
        }
    });

    ready_rx.recv().expect("server thread should be ready");
    (handle, format!("http://{}", addr))
}

#[test]
fn streams_and_validates_download() {
    let body = b"hello world".to_vec();
    let expected_hash = format!("{:x}", Sha256::digest(&body));
    let (handle, url) = start_server(body.clone(), None, None);
    let temp = tempdir().unwrap();
    let dest = temp.path().join("file.bin");

    let step = DownloadStep {
        url,
        dest: dest.clone(),
        expected_sha256: Some(expected_hash.clone()),
        expected_size: Some(body.len() as u64),
        timeout_secs: Some(5),
    };

    perform_download(&step).expect("download should succeed");
    handle.join().unwrap();

    let downloaded = std::fs::read(&dest).unwrap();
    assert_eq!(downloaded, body);
}

#[test]
fn detects_hash_mismatch() {
    let body = b"hello".to_vec();
    let (handle, url) = start_server(body.clone(), None, None);
    let temp = tempdir().unwrap();
    let dest = temp.path().join("file.bin");

    let step = DownloadStep {
        url,
        dest,
        expected_sha256: Some("deadbeef".to_string()),
        expected_size: Some(body.len() as u64),
        timeout_secs: None,
    };

    let err = perform_download(&step).expect_err("hash mismatch should fail");
    handle.join().unwrap();
    let message = err.to_string();
    assert!(
        message.contains("hash mismatch"),
        "unexpected error: {message}"
    );
}

#[test]
fn times_out_when_server_is_slow() {
    let body = b"slow".to_vec();
    let (handle, url) = start_server(body, Some(Duration::from_secs(3)), None);
    let temp = tempdir().unwrap();
    let dest = temp.path().join("file.bin");

    let step = DownloadStep {
        url,
        dest,
        expected_sha256: None,
        expected_size: None,
        timeout_secs: Some(1),
    };

    let err = perform_download(&step).expect_err("timeout should fail download");
    handle.join().unwrap();
    let msg = err.to_string();
    assert!(
        msg.contains("timed out") || msg.contains("connection refused") || msg.contains("reset") || msg.contains("error sending request"),
        "unexpected error: {msg}"
    );
}

#[test]
fn enforces_reported_content_length() {
    let body = b"abc".to_vec();
    let (handle, url) = start_server(body, None, Some(5));
    let temp = tempdir().unwrap();
    let dest = temp.path().join("file.bin");

    let step = DownloadStep {
        url,
        dest,
        expected_sha256: None,
        expected_size: Some(5),
        timeout_secs: None,
    };

    let err = perform_download(&step).expect_err("length mismatch should fail");
    handle.join().unwrap();
    let message = err.to_string();
    assert!(
        message.contains("size mismatch") || message.contains("content length"),
        "unexpected error: {message}"
    );
}
