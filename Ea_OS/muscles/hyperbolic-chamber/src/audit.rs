use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::PathBuf;

use anyhow::{Context, Result};
use chrono::Utc;
use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct AuditEntry {
    pub timestamp: String,
    pub user: String,
    pub command: String,
    pub manifest_path: Option<String>,
    pub app_name: Option<String>,
    pub app_version: Option<String>,
    pub mode: Option<String>,
    pub steps_executed: Option<usize>,
    pub result: String,
    pub error: Option<String>,
}

pub fn get_audit_log_path() -> Result<PathBuf> {
    let base = dirs::data_dir()
        .ok_or_else(|| anyhow::anyhow!("could not determine platform data directory"))?
        .join("enzyme-installer");
    Ok(base.join("audit.log"))
}

pub fn write_audit_entry(entry: &AuditEntry) -> Result<()> {
    let log_path = get_audit_log_path()?;
    
    if let Some(parent) = log_path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("creating audit log directory {}", parent.display()))?;
    }

    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .with_context(|| format!("opening audit log {}", log_path.display()))?;

    let json = serde_json::to_string(entry)
        .context("serializing audit entry")?;
    
    writeln!(file, "{}", json)
        .with_context(|| format!("writing to audit log {}", log_path.display()))?;
    
    Ok(())
}

pub fn create_audit_entry(
    command: &str,
    manifest_path: Option<&std::path::Path>,
    app_name: Option<&str>,
    app_version: Option<&str>,
    mode: Option<&str>,
    steps_executed: Option<usize>,
    result: &str,
    error: Option<&str>,
) -> AuditEntry {
    let user = std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_else(|_| "unknown".to_string());

    AuditEntry {
        timestamp: Utc::now().to_rfc3339(),
        user,
        command: command.to_string(),
        manifest_path: manifest_path.map(|p| p.display().to_string()),
        app_name: app_name.map(|s| s.to_string()),
        app_version: app_version.map(|s| s.to_string()),
        mode: mode.map(|s| s.to_string()),
        steps_executed,
        result: result.to_string(),
        error: error.map(|s| s.to_string()),
    }
}
