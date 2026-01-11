use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Once;
use std::time::{Duration, Instant};
use std::time::{SystemTime, UNIX_EPOCH};

pub fn wait_for_path(path: &Path, timeout: Duration) -> Result<(), String> {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if path.exists() {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    Err(format!("timed out waiting for {}", path.display()))
}

pub fn unix_socket_supported() -> bool {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let mut dir = std::env::temp_dir();
    dir.push(format!("ledgerd-socket-probe-{nanos}"));
    if std::fs::create_dir_all(&dir).is_err() {
        return false;
    }
    let path = dir.join("probe.sock");
    let result = std::os::unix::net::UnixListener::bind(&path).is_ok();
    let _ = std::fs::remove_file(&path);
    let _ = std::fs::remove_dir_all(&dir);
    result
}

static LEDGERD_BUILD: Once = Once::new();

pub fn ledgerd_bin() -> PathBuf {
    if let Ok(path) = std::env::var("CARGO_BIN_EXE_ledgerd") {
        return PathBuf::from(path);
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let workspace_root = manifest_dir
        .parent()
        .map(PathBuf::from)
        .unwrap_or_else(|| manifest_dir.clone());
    let target_dir = std::env::var_os("CARGO_TARGET_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| workspace_root.join("target"));
    let profile = std::env::var("PROFILE").unwrap_or_else(|_| "debug".to_string());
    let bin_name = if cfg!(windows) { "ledgerd.exe" } else { "ledgerd" };

    let bin_path = target_dir.join(&profile).join(bin_name);

    LEDGERD_BUILD.call_once(|| {
        let cargo = std::env::var("CARGO").unwrap_or_else(|_| "cargo".to_string());
        let status = Command::new(cargo)
            .current_dir(&workspace_root)
            .args(["build", "--offline", "-p", "ledgerd"])
            .status()
            .expect("failed to invoke cargo build for ledgerd");
        if !status.success() {
            panic!("cargo build -p ledgerd failed with status {status}");
        }
    });

    if bin_path.exists() {
        return bin_path;
    }

    panic!("ledgerd binary not found at {}", bin_path.display());
}
