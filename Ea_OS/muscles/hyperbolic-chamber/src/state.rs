use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use anyhow::{Context, anyhow};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

const LOCK_ACQUIRE_TIMEOUT: Duration = Duration::from_secs(5);
const STALE_LOCK_TIMEOUT: Duration = Duration::from_secs(30);
const LOCK_RETRY_INTERVAL: Duration = Duration::from_millis(50);

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum InstallStatus {
    Success,
    Failed,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct InstallRecord {
    pub app_name: String,
    pub app_version: String,
    pub mode: String,
    pub os: String,
    pub cpu_arch: String,
    pub timestamp: DateTime<Utc>,
    pub status: InstallStatus,
    #[serde(default)]
    pub artifacts: Vec<Artifact>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(tag = "type")]
pub enum Artifact {
    DownloadedFile { path: PathBuf },
    ExtractedDirectory { path: PathBuf },
    CreatedFile { path: PathBuf },
    RuntimeEnv { root: PathBuf, kind: String },
}

#[derive(Debug, Serialize, Deserialize, Default, Clone)]
pub struct State {
    #[serde(default)]
    pub installs: Vec<InstallRecord>,
}

pub fn load_state() -> anyhow::Result<State> {
    with_state_lock(|lock| load_state_locked(lock))
}

pub fn save_state(state: &State) -> anyhow::Result<()> {
    with_state_lock(|lock| save_state_locked(lock, state))
}

pub fn add_install_record(record: InstallRecord) -> anyhow::Result<()> {
    with_state_lock(|lock| {
        let mut state = load_state_locked(lock)?;
        state.installs.push(record);
        save_state_locked(lock, &state)
    })
}

fn state_file_path() -> anyhow::Result<PathBuf> {
    let base = if let Ok(override_dir) = std::env::var("ENZYME_DATA_DIR") {
        PathBuf::from(override_dir)
    } else {
        dirs::data_dir()
            .ok_or_else(|| anyhow!("could not determine platform data directory"))?
            .join("enzyme-installer")
    };
    Ok(base.join("state.json"))
}

fn lock_file_path() -> anyhow::Result<PathBuf> {
    Ok(state_file_path()?.with_extension("lock"))
}

struct StateLockGuard {
    path: PathBuf,
}

impl StateLockGuard {
    fn acquire() -> anyhow::Result<Self> {
        let path = lock_file_path()?;
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)
                .with_context(|| format!("creating state directory {}", parent.display()))?;
        }

        let start = Instant::now();
        loop {
            match OpenOptions::new().create_new(true).write(true).open(&path) {
                Ok(mut file) => {
                    let timestamp = Utc::now().to_rfc3339();
                    file.write_all(timestamp.as_bytes())
                        .with_context(|| format!("writing lock file {}", path.display()))?;
                    file.sync_all().with_context(|| {
                        format!("syncing lock file contents for {}", path.display())
                    })?;
                    return Ok(Self { path });
                }
                Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {
                    if lock_is_stale(&path)? {
                        if let Err(e) = fs::remove_file(&path) {
                            if e.kind() != std::io::ErrorKind::NotFound {
                                return Err(e).with_context(|| {
                                    format!("removing stale state lock {}", path.display())
                                });
                            }
                        }
                        continue;
                    }

                    if start.elapsed() > LOCK_ACQUIRE_TIMEOUT {
                        return Err(anyhow!(
                            "timed out waiting to acquire state lock at {}",
                            path.display()
                        ));
                    }

                    std::thread::sleep(LOCK_RETRY_INTERVAL);
                }
                Err(err) => {
                    return Err(err).with_context(|| {
                        format!("creating state lock file at {}", path.display())
                    });
                }
            }
        }
    }
}

impl Drop for StateLockGuard {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn lock_is_stale(path: &Path) -> anyhow::Result<bool> {
    let contents = match fs::read_to_string(path) {
        Ok(contents) => contents,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(err) => {
            return Err(err).with_context(|| format!("reading state lock at {}", path.display()));
        }
    };

    match DateTime::parse_from_rfc3339(contents.trim()) {
        Ok(timestamp) => {
            let elapsed = Utc::now()
                .signed_duration_since(timestamp.with_timezone(&Utc))
                .to_std()
                .unwrap_or_else(|_| Duration::from_secs(u64::MAX));

            Ok(elapsed > STALE_LOCK_TIMEOUT)
        }
        Err(_) => Ok(true),
    }
}

fn with_state_lock<R>(
    operation: impl FnOnce(&StateLockGuard) -> anyhow::Result<R>,
) -> anyhow::Result<R> {
    let lock = StateLockGuard::acquire()?;
    let result = operation(&lock);
    result
}

fn load_state_locked(_lock: &StateLockGuard) -> anyhow::Result<State> {
    let _ = _lock;
    let path = state_file_path()?;
    if !path.exists() {
        return Ok(State::default());
    }

    let data = fs::read_to_string(&path)
        .with_context(|| format!("reading state file at {}", path.display()))?;
    let state: State = serde_json::from_str(&data)
        .with_context(|| format!("parsing state file at {}", path.display()))?;
    Ok(state)
}

fn save_state_locked(_lock: &StateLockGuard, state: &State) -> anyhow::Result<()> {
    let _ = _lock;
    let path = state_file_path()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("creating state directory {}", parent.display()))?;
    }

    let tmp_path = path.with_extension("tmp");
    let data = serde_json::to_string_pretty(state)?;
    fs::write(&tmp_path, data)
        .with_context(|| format!("writing temp state file {}", tmp_path.display()))?;
    fs::rename(&tmp_path, &path)
        .with_context(|| format!("committing state file to {}", path.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        InstallRecord, InstallStatus, add_install_record, load_state, lock_file_path,
        state_file_path,
    };
    use chrono::{Duration as ChronoDuration, Utc};
    use std::fs;
    use std::sync::{Mutex, OnceLock};
    use std::thread;
    use tempfile::TempDir;

    fn test_mutex() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    #[test]
    fn concurrent_writers_preserve_all_records() {
        let _guard = test_mutex().lock().unwrap();
        let temp_dir = TempDir::new().expect("temp dir");
        unsafe {
            std::env::set_var("ENZYME_DATA_DIR", temp_dir.path());
        }

        let writer_count = 8;
        let mut handles = Vec::with_capacity(writer_count);
        for index in 0..writer_count {
            handles.push(thread::spawn(move || {
                let record = InstallRecord {
                    app_name: format!("app-{index}"),
                    app_version: "1.0.0".to_string(),
                    mode: "standard".to_string(),
                    os: "linux".to_string(),
                    cpu_arch: "x86_64".to_string(),
                    timestamp: Utc::now(),
                    status: InstallStatus::Success,
                    artifacts: vec![],
                };
                add_install_record(record)
            }));
        }

        for handle in handles {
            handle.join().expect("thread join").expect("add record");
        }

        let state = load_state().expect("load state");
        assert_eq!(state.installs.len(), writer_count);

        let mut app_names: Vec<_> = state
            .installs
            .into_iter()
            .map(|record| record.app_name)
            .collect();
        app_names.sort();
        app_names.dedup();
        assert_eq!(app_names.len(), writer_count);
    }

    #[test]
    fn stale_lock_is_cleaned_up() {
        let _guard = test_mutex().lock().unwrap();
        let temp_dir = TempDir::new().expect("temp dir");
        unsafe {
            std::env::set_var("ENZYME_DATA_DIR", temp_dir.path());
        }

        let lock_path = lock_file_path().expect("lock path");
        if let Some(parent) = lock_path.parent() {
            fs::create_dir_all(parent).expect("lock parent dir");
        }

        let stale_timestamp = (Utc::now() - ChronoDuration::seconds(120)).to_rfc3339();
        fs::write(&lock_path, stale_timestamp).expect("write stale lock");

        let record = InstallRecord {
            app_name: "stale-app".to_string(),
            app_version: "1.0.0".to_string(),
            mode: "standard".to_string(),
            os: "linux".to_string(),
            cpu_arch: "x86_64".to_string(),
            timestamp: Utc::now(),
            status: InstallStatus::Success,
            artifacts: vec![],
        };

        add_install_record(record).expect("write after stale lock");

        let state_path = state_file_path().expect("state path");
        assert!(state_path.exists(), "state file should exist after write");
        assert!(
            !lock_path.exists(),
            "stale lock should be removed after operation"
        );
    }
}
