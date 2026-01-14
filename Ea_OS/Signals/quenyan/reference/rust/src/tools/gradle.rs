use std::path::Path;

use super::BuildIntegration;

/// Detect Gradle projects via either `build.gradle` or `build.gradle.kts`.
pub fn detect(project_root: &Path) -> Option<BuildIntegration> {
    let groovy = project_root.join("build.gradle");
    let kotlin = project_root.join("build.gradle.kts");
    let manifest = if groovy.is_file() {
        Some(groovy)
    } else if kotlin.is_file() {
        Some(kotlin)
    } else {
        None
    }?;
    let commands = vec![
        "./gradlew assemble".to_string(),
        "mcs-reference project dependency-graph --project-root . --json".to_string(),
    ];
    Some(BuildIntegration::new("gradle", manifest, commands))
}
