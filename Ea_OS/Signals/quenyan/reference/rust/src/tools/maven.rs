use std::path::Path;

use super::BuildIntegration;

/// Detect Maven projects by looking for a `pom.xml` file.
pub fn detect(project_root: &Path) -> Option<BuildIntegration> {
    let manifest = project_root.join("pom.xml");
    if manifest.is_file() {
        let commands = vec![
            "mvn --batch-mode -DskipTests package".to_string(),
            "mcs-reference project batch-encode --passphrase $QYN1_PASSPHRASE --project-root . --output-dir target/quenyan-artifacts".to_string(),
        ];
        return Some(BuildIntegration::new("maven", manifest, commands));
    }
    None
}
