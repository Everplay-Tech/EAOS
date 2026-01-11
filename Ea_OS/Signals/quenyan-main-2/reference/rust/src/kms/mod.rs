//! Lightweight key management service abstractions used by the CLI.

use anyhow::{anyhow, Context, Result};
use chrono::{DateTime, Utc};
use clap::ValueEnum;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

pub mod aws;
pub mod azure;
pub mod local;

/// Normalised view of key metadata provided by the different backends.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeyMetadata {
    pub provider: String,
    pub key_id: String,
    pub key_version: String,
    pub rotation_due: String,
    pub state: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub audit_trail: Vec<KeyAuditEvent>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub alias: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub material_arn: Option<String>,
}

/// Audit entry describing key lifecycle events.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeyAuditEvent {
    pub action: String,
    pub timestamp: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub actor: Option<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub context: BTreeMap<String, Value>,
}

/// Supported key-management providers.
#[derive(Clone, Copy, Debug, ValueEnum)]
pub enum Provider {
    Aws,
    Azure,
    Local,
}

impl Provider {
    pub fn as_str(&self) -> &'static str {
        match self {
            Provider::Aws => "aws",
            Provider::Azure => "azure",
            Provider::Local => "local",
        }
    }
}

/// Common interface shared by the provider implementations.
pub trait KeyManagement {
    fn describe_key(&self, key_id: &str) -> Result<KeyMetadata>;
    fn rotate_key(&self, key_id: &str) -> Result<KeyMetadata>;
}

/// Load the requested provider, optionally using a file-backed metadata store.
pub fn connect(provider: Provider, metadata_path: Option<&Path>) -> Result<Box<dyn KeyManagement>> {
    match provider {
        Provider::Aws => aws::connect(metadata_path),
        Provider::Azure => azure::connect(metadata_path),
        Provider::Local => local::connect(metadata_path),
    }
}

/// Simplified persistence layer shared by all key provider implementations.
pub struct FileBackedVault {
    provider: &'static str,
    path: PathBuf,
}

impl FileBackedVault {
    pub fn new(provider: &'static str, path: PathBuf) -> Self {
        Self { provider, path }
    }

    fn load(&self) -> Result<BTreeMap<String, KeyMetadata>> {
        if !self.path.exists() {
            return Ok(BTreeMap::new());
        }
        let raw = fs::read_to_string(&self.path)
            .with_context(|| format!("failed to read key metadata store: {:?}", self.path))?;
        if raw.trim().is_empty() {
            return Ok(BTreeMap::new());
        }
        let mut parsed: BTreeMap<String, KeyMetadata> = serde_json::from_str(&raw)
            .with_context(|| format!("invalid key metadata JSON in {:?}", self.path))?;
        for metadata in parsed.values_mut() {
            metadata.provider = self.provider.to_string();
        }
        Ok(parsed)
    }

    fn store(&self, data: &BTreeMap<String, KeyMetadata>) -> Result<()> {
        let serialised = serde_json::to_string_pretty(data)?;
        fs::create_dir_all(
            self.path
                .parent()
                .ok_or_else(|| anyhow!("metadata path has no parent"))?,
        )?;
        fs::write(&self.path, serialised)
            .with_context(|| format!("failed to write key metadata store: {:?}", self.path))
    }

    pub fn describe_key(&self, key_id: &str) -> Result<KeyMetadata> {
        let store = self.load()?;
        store
            .get(key_id)
            .cloned()
            .ok_or_else(|| anyhow!("key '{}' not found in {} vault", key_id, self.provider))
    }

    pub fn rotate_key(&self, key_id: &str) -> Result<KeyMetadata> {
        let mut store = self.load()?;
        let mut entry = store
            .remove(key_id)
            .ok_or_else(|| anyhow!("key '{}' not found in {} vault", key_id, self.provider))?;
        entry.key_version = bump_version(&entry.key_version);
        entry.rotation_due = next_rotation_window();
        let mut audit = entry.audit_trail;
        audit.push(KeyAuditEvent {
            action: "rotate".to_string(),
            timestamp: iso_timestamp(),
            actor: Some("quenyan-cli".to_string()),
            context: BTreeMap::from([
                (
                    "provider".to_string(),
                    Value::String(self.provider.to_string()),
                ),
                (
                    "key_version".to_string(),
                    Value::String(entry.key_version.clone()),
                ),
            ]),
        });
        entry.audit_trail = audit;
        store.insert(key_id.to_string(), entry.clone());
        self.store(&store)?;
        Ok(entry)
    }
}

fn iso_timestamp() -> String {
    let now: DateTime<Utc> = Utc::now();
    now.to_rfc3339()
}

fn next_rotation_window() -> String {
    let now: DateTime<Utc> = Utc::now();
    let future = now + chrono::Duration::days(30);
    future.to_rfc3339()
}

fn bump_version(current: &str) -> String {
    let mut digits = String::new();
    for ch in current.chars().rev() {
        if ch.is_ascii_digit() {
            digits.push(ch);
        } else {
            break;
        }
    }
    if digits.is_empty() {
        return format!("{}-1", current);
    }
    let digits: String = digits.chars().rev().collect();
    let prefix_len = current.len() - digits.len();
    let prefix = &current[..prefix_len];
    match digits.parse::<u32>() {
        Ok(value) => format!("{}{}", prefix, value + 1),
        Err(_) => format!("{}{}", prefix, digits),
    }
}

fn default_store_path(provider: Provider) -> Result<PathBuf> {
    let base = std::env::var("QYN1_KMS_DIR")
        .or_else(|_| std::env::var("HOME"))
        .map(PathBuf::from)?;
    Ok(base
        .join(".quenyan")
        .join(format!("{}-kms.json", provider.as_str())))
}

pub(crate) fn resolve_store_path(provider: Provider, path: Option<&Path>) -> Result<PathBuf> {
    match path {
        Some(p) => Ok(p.to_path_buf()),
        None => default_store_path(provider),
    }
}
