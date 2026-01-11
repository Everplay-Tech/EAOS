//! Server environment fingerprinting for IHP.
//!
//! Detects CPU, NIC, OS, and build fingerprints for server environment profiling.
//! Supports environment variable overrides for containerized deployments.

use std::env;
use crate::ServerEnvironmentProfile;

/// Detect CPU fingerprint from system or environment variable.
pub fn detect_cpu_fingerprint() -> String {
    // Check environment variable first (for containerized deployments)
    if let Ok(fp) = env::var("IHP_CPU_FINGERPRINT") {
        return fp;
    }

    // Try to detect from system
    #[cfg(target_os = "linux")]
    {
        if let Ok(cpuinfo) = std::fs::read_to_string("/proc/cpuinfo") {
            // Extract model name or processor info
            for line in cpuinfo.lines() {
                if line.starts_with("model name") || line.starts_with("Processor") {
                    if let Some((_, value)) = line.split_once(':') {
                        let trimmed = value.trim();
                        if !trimmed.is_empty() {
                            return format!("cpu:{}", trimmed);
                        }
                    }
                }
            }
        }
    }

    #[cfg(target_os = "macos")]
    {
        if let Ok(output) = std::process::Command::new("sysctl")
            .arg("-n")
            .arg("machdep.cpu.brand_string")
            .output()
        {
            if output.status.success() {
                if let Ok(brand) = String::from_utf8(output.stdout) {
                    let trimmed = brand.trim();
                    if !trimmed.is_empty() {
                        return format!("cpu:{}", trimmed);
                    }
                }
            }
        }
    }

    // Fallback: use target architecture
    format!("cpu:{}", env::consts::ARCH)
}

/// Detect NIC fingerprint from system or environment variable.
pub fn detect_nic_fingerprint() -> String {
    // Check environment variable first
    if let Ok(fp) = env::var("IHP_NIC_FINGERPRINT") {
        return fp;
    }

    // Try to detect from network interfaces
    #[cfg(target_os = "linux")]
    {
        if let Ok(entries) = std::fs::read_dir("/sys/class/net") {
            let mut interfaces = Vec::new();
            for entry in entries.flatten() {
                if let Some(name) = entry.file_name().to_str() {
                    // Skip loopback and virtual interfaces
                    if name != "lo" && !name.starts_with("docker") && !name.starts_with("veth") {
                        interfaces.push(name.to_string());
                    }
                }
            }
            if !interfaces.is_empty() {
                // Use first non-loopback interface
                return format!("nic:{}", interfaces[0]);
            }
        }
    }

    #[cfg(target_os = "macos")]
    {
        if let Ok(output) = std::process::Command::new("networksetup")
            .arg("-listallhardwareports")
            .output()
        {
            if output.status.success() {
                if let Ok(text) = String::from_utf8(output.stdout) {
                    for line in text.lines() {
                        if line.contains("Hardware Port:") {
                            if let Some((_, port)) = line.split_once(':') {
                                let trimmed = port.trim();
                                if !trimmed.is_empty() && trimmed != "Loopback" {
                                    return format!("nic:{}", trimmed);
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Fallback: use hostname or generic identifier
    env::var("HOSTNAME")
        .or_else(|_| env::var("COMPUTERNAME"))
        .map(|h| format!("nic:{}", h))
        .unwrap_or_else(|_| "nic:default".to_string())
}

/// Detect OS fingerprint from system or environment variable.
pub fn detect_os_fingerprint() -> String {
    // Check environment variable first
    if let Ok(fp) = env::var("IHP_OS_FINGERPRINT") {
        return fp;
    }

    // Use standard library OS detection
    let os = env::consts::OS;
    let arch = env::consts::ARCH;
    
    // Try to get OS version if available
    #[cfg(target_os = "linux")]
    {
        if let Ok(release) = std::fs::read_to_string("/etc/os-release") {
            for line in release.lines() {
                if line.starts_with("PRETTY_NAME=") {
                    if let Some((_, value)) = line.split_once('=') {
                        let trimmed = value.trim_matches('"');
                        return format!("os:{}:{}", trimmed, arch);
                    }
                }
            }
        }
    }

    #[cfg(target_os = "macos")]
    {
        if let Ok(output) = std::process::Command::new("sw_vers")
            .arg("-productVersion")
            .output()
        {
            if output.status.success() {
                if let Ok(version) = String::from_utf8(output.stdout) {
                    let trimmed = version.trim();
                    return format!("os:macOS-{}:{}", trimmed, arch);
                }
            }
        }
    }

    format!("os:{}:{}", os, arch)
}

/// Detect build fingerprint from environment or build metadata.
pub fn detect_build_fingerprint() -> String {
    // Check environment variable first
    if let Ok(fp) = env::var("IHP_BUILD_FINGERPRINT") {
        return fp;
    }

    // Try to get from Cargo build metadata
    let version = env::var("CARGO_PKG_VERSION")
        .unwrap_or_else(|_| "unknown".to_string());
    
    // Include build timestamp if available
    let timestamp = env::var("SOURCE_DATE_EPOCH")
        .or_else(|_| {
            // Fallback to current time if SOURCE_DATE_EPOCH not set
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs().to_string())
        })
        .unwrap_or_else(|_| "unknown".to_string());

    format!("build:v{}:{}", version, timestamp)
}

/// Build a complete server environment profile using detected or overridden values.
pub fn build_server_environment_profile() -> ServerEnvironmentProfile {
    ServerEnvironmentProfile {
        cpu_fingerprint: detect_cpu_fingerprint(),
        nic_fingerprint: detect_nic_fingerprint(),
        os_fingerprint: detect_os_fingerprint(),
        app_build_fingerprint: detect_build_fingerprint(),
        tpm_quote: None, // TPM quote detection would require additional libraries
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_environment_variable_override() {
        env::set_var("IHP_CPU_FINGERPRINT", "test-cpu");
        env::set_var("IHP_NIC_FINGERPRINT", "test-nic");
        env::set_var("IHP_OS_FINGERPRINT", "test-os");
        env::set_var("IHP_BUILD_FINGERPRINT", "test-build");

        assert_eq!(detect_cpu_fingerprint(), "test-cpu");
        assert_eq!(detect_nic_fingerprint(), "test-nic");
        assert_eq!(detect_os_fingerprint(), "test-os");
        assert_eq!(detect_build_fingerprint(), "test-build");

        // Cleanup
        env::remove_var("IHP_CPU_FINGERPRINT");
        env::remove_var("IHP_NIC_FINGERPRINT");
        env::remove_var("IHP_OS_FINGERPRINT");
        env::remove_var("IHP_BUILD_FINGERPRINT");
    }

    #[test]
    fn test_build_profile() {
        let profile = build_server_environment_profile();
        assert!(!profile.cpu_fingerprint.is_empty());
        assert!(!profile.nic_fingerprint.is_empty());
        assert!(!profile.os_fingerprint.is_empty());
        assert!(!profile.app_build_fingerprint.is_empty());
    }
}
