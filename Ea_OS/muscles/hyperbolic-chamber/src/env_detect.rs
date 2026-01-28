use std::process::Command;

use serde::Serialize;
use sysinfo::System;
use which::which;

use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Serialize)]
pub struct Environment {
    pub os: String,
    pub os_version: String,
    pub cpu_arch: String,
    pub ram_gb: u64,
    pub pkg_managers: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fingerprint: Option<Fingerprint>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Fingerprint {
    pub os: String,
    pub os_version: String,
    pub cpu_arch: String,
    pub ram_gb: u64,
    pub hostname: Option<String>,
    pub extra: Option<serde_json::Value>,
    pub hash: String,
}

pub fn detect_environment() -> anyhow::Result<Environment> {
    let mut system = System::new_all();
    system.refresh_all();

    let os = normalize_os(std::env::consts::OS);
    let os_version = System::long_os_version()
        .or_else(System::os_version)
        .unwrap_or_else(|| "unknown".to_string());
    let cpu_arch = normalize_arch(std::env::consts::ARCH);
    let ram_gb = system.total_memory() / 1_048_576; // KiB to GiB
    let pkg_managers = detect_package_managers(&os);

    let fingerprint = compute_fingerprint(&os, &os_version, &cpu_arch, ram_gb, System::host_name());

    Ok(Environment {
        os,
        os_version,
        cpu_arch,
        ram_gb,
        pkg_managers,
        fingerprint: Some(fingerprint),
    })
}

fn compute_fingerprint(
    os: &str,
    os_version: &str,
    cpu_arch: &str,
    ram_gb: u64,
    hostname: Option<String>,
) -> Fingerprint {
    let mut hasher = Sha256::new();
    hasher.update(os.as_bytes());
    hasher.update(os_version.as_bytes());
    hasher.update(cpu_arch.as_bytes());
    hasher.update(ram_gb.to_le_bytes());
    if let Some(ref host) = hostname {
        hasher.update(host.as_bytes());
    }
    let hash = format!("{:x}", hasher.finalize());

    Fingerprint {
        os: os.to_string(),
        os_version: os_version.to_string(),
        cpu_arch: cpu_arch.to_string(),
        ram_gb,
        hostname,
        extra: None,
        hash,
    }
}

fn normalize_os(raw: &str) -> String {
    let lowered = raw.to_lowercase();
    match lowered.as_str() {
        "macos" | "darwin" | "osx" => "macos".to_string(),
        "windows" => "windows".to_string(),
        "linux" | "gnu/linux" => "linux".to_string(),
        other => other.to_string(),
    }
}

fn normalize_arch(raw: &str) -> String {
    match raw {
        "x86_64" => "x64".to_string(),
        "aarch64" => "arm64".to_string(),
        other => other.to_lowercase(),
    }
}

fn detect_package_managers(os: &str) -> Vec<String> {
    let mut managers = Vec::new();

    match os {
        "macos" => {
            if has_command("brew") {
                managers.push("brew".to_string());
            }
        }
        "linux" => {
            if has_command("apt") {
                managers.push("apt".to_string());
            }
            if has_command("dnf") {
                managers.push("dnf".to_string());
            }
            if has_command("yum") {
                managers.push("yum".to_string());
            }
            if has_command("zypper") {
                managers.push("zypper".to_string());
            }
            if has_command("pacman") {
                managers.push("pacman".to_string());
            }
        }
        "windows" => {
            if has_command("winget") {
                managers.push("winget".to_string());
            }
            if has_command("choco") {
                managers.push("choco".to_string());
            }
            if has_command("scoop") {
                managers.push("scoop".to_string());
            }
        }
        _ => {}
    }

    managers
}

fn has_command(cmd: &str) -> bool {
    which(cmd).is_ok()
        || Command::new(cmd)
            .arg("--version")
            .output()
            .map(|output| output.status.success())
            .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::os::unix::fs::PermissionsExt;

    use super::{detect_package_managers, Environment, Fingerprint};
    use super::normalize_os;

    fn make_executable(path: &std::path::Path) {
        let mut perms = fs::metadata(path)
            .expect("metadata should be available for created file")
            .permissions();
        perms.set_mode(0o755);
        fs::set_permissions(path, perms).expect("should be able to mark file executable");
    }

    #[test]
    fn normalizes_known_operating_systems() {
        assert_eq!(normalize_os("Linux"), "linux");
        assert_eq!(normalize_os("linux"), "linux");
        assert_eq!(normalize_os("GNU/Linux"), "linux");
        assert_eq!(normalize_os("WINDOWS"), "windows");
        assert_eq!(normalize_os("macOS"), "macos");
        assert_eq!(normalize_os("OSX"), "macos");
    }

    #[test]
    fn detects_linux_package_managers_and_serializes_environment() {
        let temp_dir = tempfile::tempdir().expect("should create temp dir for package managers");

        for name in ["apt", "dnf", "yum", "zypper", "pacman"] {
            let path = temp_dir.path().join(name);
            fs::write(&path, "#!/bin/sh\nexit 0\n").expect("should create fake package manager");
            make_executable(&path);
        }

        let original_path = std::env::var_os("PATH");
        let temp_path = if let Some(existing) = &original_path {
            format!("{}:{}", temp_dir.path().display(), existing.to_string_lossy())
        } else {
            temp_dir.path().display().to_string()
        };
        unsafe {
            std::env::set_var("PATH", &temp_path);
        }

        let managers = detect_package_managers("linux");

        if let Some(path) = original_path {
            unsafe {
                std::env::set_var("PATH", path);
            }
        } else {
            unsafe {
                std::env::remove_var("PATH");
            }
        }

        assert_eq!(
            managers,
            vec![
                "apt".to_string(),
                "dnf".to_string(),
                "yum".to_string(),
                "zypper".to_string(),
                "pacman".to_string()
            ]
        );

        let env = Environment {
            os: "linux".to_string(),
            os_version: "example".to_string(),
            cpu_arch: "x64".to_string(),
            ram_gb: 16,
            pkg_managers: managers,
            fingerprint: Some(Fingerprint {
                os: "linux".to_string(),
                os_version: "example".to_string(),
                cpu_arch: "x64".to_string(),
                ram_gb: 16,
                hostname: Some("host".to_string()),
                extra: None,
                hash: "abc".to_string(),
            }),
        };

        let serialized = serde_json::to_value(env).expect("environment should serialize to JSON");
        assert_eq!(
            serialized["pkg_managers"],
            serde_json::json!(["apt", "dnf", "yum", "zypper", "pacman"])
        );
    }
}
