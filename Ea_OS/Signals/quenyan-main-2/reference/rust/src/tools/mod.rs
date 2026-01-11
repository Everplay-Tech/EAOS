//! Build system integration helpers exposed through the CLI project workflows.

use serde::Serialize;
use std::path::{Path, PathBuf};

pub mod cargo;
pub mod gradle;
pub mod maven;
pub mod npm;

/// Summary of how the CLI can participate in an existing build system.
#[derive(Debug, Clone, Serialize)]
pub struct BuildIntegration {
    /// Name of the build system (e.g. `cargo`, `npm`).
    pub system: String,
    /// Location of the manifest or build file used for detection.
    pub manifest_path: PathBuf,
    /// Suggested commands that wrap the CLI in project mode.
    pub suggested_commands: Vec<String>,
    /// Optional reference CI pipeline provided by the repository.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ci_template: Option<String>,
}

impl BuildIntegration {
    pub fn new<P: Into<PathBuf>>(system: &str, manifest_path: P, commands: Vec<String>) -> Self {
        Self {
            system: system.to_string(),
            manifest_path: manifest_path.into(),
            suggested_commands: commands,
            ci_template: reference_ci_template(system),
        }
    }
}

fn reference_ci_template(system: &str) -> Option<String> {
    match system {
        "cargo" => Some("ci/pipelines/cargo-project.yml".to_string()),
        "npm" => Some("ci/pipelines/npm-project.yml".to_string()),
        "maven" => Some("ci/pipelines/maven-project.yml".to_string()),
        "gradle" => Some("ci/pipelines/gradle-project.yml".to_string()),
        _ => None,
    }
}

/// Detect build integrations rooted at `project_root`.
pub fn detect(project_root: &Path) -> Vec<BuildIntegration> {
    let mut results = Vec::new();
    if let Some(integration) = cargo::detect(project_root) {
        results.push(integration);
    }
    if let Some(integration) = npm::detect(project_root) {
        results.push(integration);
    }
    if let Some(integration) = maven::detect(project_root) {
        results.push(integration);
    }
    if let Some(integration) = gradle::detect(project_root) {
        results.push(integration);
    }
    results
}
