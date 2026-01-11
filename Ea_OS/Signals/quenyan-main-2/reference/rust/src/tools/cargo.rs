use std::path::Path;

use super::BuildIntegration;

/// Detect Cargo projects by locating a `Cargo.toml` file at the root.
pub fn detect(project_root: &Path) -> Option<BuildIntegration> {
    let manifest = project_root.join("Cargo.toml");
    if manifest.is_file() {
        let commands = vec![
            "cargo fetch --locked".to_string(),
            "cargo build --locked --workspace".to_string(),
            "mcs-reference project batch-encode --passphrase $QYN1_PASSPHRASE --project-root . --output-dir target/quenyan-artifacts".to_string(),
        ];
        return Some(BuildIntegration::new("cargo", manifest, commands));
    }
    None
}
