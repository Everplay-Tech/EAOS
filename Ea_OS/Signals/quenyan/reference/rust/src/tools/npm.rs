use std::path::Path;

use super::BuildIntegration;

/// Detect Node.js projects by finding a `package.json` file.
pub fn detect(project_root: &Path) -> Option<BuildIntegration> {
    let manifest = project_root.join("package.json");
    if manifest.is_file() {
        let commands = vec![
            "npm install --no-audit".to_string(),
            "npm run build --if-present".to_string(),
            "mcs-reference project incremental-rebuild --passphrase $QYN1_PASSPHRASE --project-root . --output-dir build/quenyan --state-file .quenyan-state.json".to_string(),
        ];
        return Some(BuildIntegration::new("npm", manifest, commands));
    }
    None
}
