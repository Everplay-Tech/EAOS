use std::path::PathBuf;

use chrono::Utc;
use clap::{Parser, Subcommand};
use serde::Serialize;
use tracing::{debug, error, info, warn};

use crate::audit::{create_audit_entry, write_audit_entry};
use crate::env_detect::detect_environment;
use crate::executor::{ExecutionError, ExecutionResult, execute_plan};
use crate::manifest::load_manifest;
use crate::planner::{InstallPlan, PlannerError, plan_install};
use crate::state::{InstallRecord, InstallStatus, add_install_record, load_state};

#[derive(Debug, Parser)]
#[command(
    name = "enzyme-installer",
    version,
    about = "Adaptive installer for heterogeneous machines"
)]
pub struct Cli {
    /// Emit JSON output for the selected subcommand
    #[arg(long, global = true)]
    json: bool,
    
    /// Set logging level (trace, debug, info, warn, error)
    #[arg(long, global = true)]
    log_level: Option<String>,
    
    /// Write logs to file
    #[arg(long, global = true)]
    log_file: Option<PathBuf>,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    /// Detect the current environment
    Detect,
    /// Build an installation plan from a manifest without executing it
    Plan {
        /// Path to the manifest file
        manifest_path: PathBuf,
    },
    /// Build and execute an installation plan
    Install {
        /// Path to the manifest file
        manifest_path: PathBuf,
        /// Show what would be executed without actually running commands
        #[arg(long)]
        dry_run: bool,
    },
    /// List previous installs recorded on this machine
    #[command(name = "list-installed")]
    ListInstalled,
    /// Uninstall a previously installed application
    Uninstall {
        /// Application name to uninstall
        app_name: String,
        /// Specific version to uninstall (optional, uninstalls all versions if omitted)
        #[arg(long)]
        version: Option<String>,
        /// Show what would be removed without actually removing
        #[arg(long)]
        dry_run: bool,
    },
}

#[derive(Debug, Serialize)]
struct DetectResponse<T> {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    environment: Option<T>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

#[derive(Debug, Serialize)]
struct PlanResponse {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    plan: Option<InstallPlan>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<PlanErrorResponse>,
}

#[derive(Debug, Serialize)]
struct PlanErrorResponse {
    message: String,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    details: Vec<String>,
    environment: Option<crate::env_detect::Environment>,
}

#[derive(Debug, Serialize)]
struct InstallResponse {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    plan: Option<InstallPlan>,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<ExecutionResult>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<InstallErrorResponse>,
}

#[derive(Debug, Serialize)]
struct InstallErrorResponse {
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    failed_step_index: Option<usize>,
}

#[derive(Debug, Serialize)]
struct ListResponse {
    ok: bool,
    installs: Vec<InstallRecord>,
}

#[derive(Debug, Serialize)]
struct ListErrorResponse {
    ok: bool,
    error: String,
}

pub fn run() -> i32 {
    let cli = Cli::parse();
    let json = cli.json;
    
    // Initialize logging if requested
    if cli.log_level.is_some() || cli.log_file.is_some() {
        if let Err(e) = crate::init_logging(
            cli.log_level.as_deref(),
            cli.log_file.as_deref(),
        ) {
            eprintln!("Failed to initialize logging: {}", e);
            return 1;
        }
    }

    let exit_code = match cli.command {
        Commands::Detect => handle_detect(json),
        Commands::Plan { manifest_path } => handle_plan(json, manifest_path),
        Commands::Install { manifest_path, dry_run } => handle_install(json, manifest_path, dry_run),
        Commands::ListInstalled => handle_list_installed(json),
        Commands::Uninstall { app_name, version, dry_run } => handle_uninstall(json, app_name, version, dry_run),
    };

    if exit_code != 0 {
        std::process::exit(exit_code);
    }

    0
}

fn handle_detect(json: bool) -> i32 {
    match detect_environment() {
        Ok(env) => {
            if json {
                print_json(&DetectResponse {
                    ok: true,
                    environment: Some(env),
                    error: None,
                });
            } else {
                match serde_json::to_string_pretty(&env) {
                    Ok(json) => println!("{}", json),
                    Err(err) => {
                        eprintln!("Failed to serialize environment output: {}", err);
                        return 1;
                    }
                }
            }
            0
        }
        Err(err) => {
            if json {
                print_json(&DetectResponse::<()> {
                    ok: false,
                    environment: None,
                    error: Some(err.to_string()),
                });
            } else {
                eprintln!("{err}");
            }
            1
        }
    }
}

fn handle_plan(json: bool, manifest_path: PathBuf) -> i32 {
    let manifest = match load_manifest(&manifest_path) {
        Ok(m) => m,
        Err(err) => {
            if json {
                print_json(&PlanResponse {
                    ok: false,
                    plan: None,
                    error: Some(PlanErrorResponse {
                        message: err.to_string(),
                        details: Vec::new(),
                        environment: None,
                    }),
                });
            } else {
                eprintln!("{err}");
            }
            return 1;
        }
    };

    let env = match detect_environment() {
        Ok(env) => env,
        Err(err) => {
            if json {
                print_json(&PlanResponse {
                    ok: false,
                    plan: None,
                    error: Some(PlanErrorResponse {
                        message: err.to_string(),
                        details: Vec::new(),
                        environment: None,
                    }),
                });
            } else {
                eprintln!("{err}");
            }
            return 1;
        }
    };

    match plan_install(&manifest, &env) {
        Ok(plan) => {
            if json {
                print_json(&PlanResponse {
                    ok: true,
                    plan: Some(plan),
                    error: None,
                });
            } else {
                println!(
                    "Plan for {} {} using '{}' mode ({} steps)",
                    manifest.name,
                    manifest.version,
                    plan.chosen_mode,
                    plan.steps.len()
                );
                match serde_json::to_string_pretty(&plan) {
                    Ok(json) => println!("{}", json),
                    Err(err) => {
                        eprintln!("Failed to serialize plan output: {}", err);
                        return 1;
                    }
                }
            }
            0
        }
        Err(PlannerError::NoCompatibleMode {
            environment,
            reasons,
        }) => {
            if json {
                print_json(&PlanResponse {
                    ok: false,
                    plan: None,
                    error: Some(PlanErrorResponse {
                        message: "No compatible modes for this environment".to_string(),
                        details: reasons,
                        environment: Some(environment),
                    }),
                });
            } else {
                eprintln!("No compatible modes found:");
                for reason in reasons {
                    eprintln!("- {reason}");
                }
            }
            2
        }
    }
}

fn handle_install(json: bool, manifest_path: PathBuf, dry_run: bool) -> i32 {
    let manifest = match load_manifest(&manifest_path) {
        Ok(m) => m,
        Err(err) => {
            emit_install_error(json, None, &err.to_string(), None);
            return 1;
        }
    };

    let env = match detect_environment() {
        Ok(env) => env,
        Err(err) => {
            emit_install_error(json, None, &err.to_string(), None);
            return 1;
        }
    };

    let plan = match plan_install(&manifest, &env) {
        Ok(plan) => plan,
        Err(PlannerError::NoCompatibleMode {
            environment,
            reasons,
        }) => {
            let message = "No compatible modes for this environment".to_string();
            let detail = PlanErrorResponse {
                message: message.clone(),
                details: reasons.clone(),
                environment: Some(environment),
            };
            if json {
                print_json(&InstallResponse {
                    ok: false,
                    plan: None,
                    result: None,
                    error: Some(InstallErrorResponse {
                        message: format!("{message}: {}", reasons.join("; ")),
                        failed_step_index: None,
                    }),
                });
            } else {
                eprintln!("No compatible modes found for install.");
                match serde_json::to_string_pretty(&detail) {
                    Ok(json) => eprintln!("{}", json),
                    Err(err) => {
                        eprintln!("Failed to serialize error details: {}", err);
                    }
                }
            }
            return 2;
        }
    };

    if !json {
        if dry_run {
            println!(
                "Dry run: Would install {} {} using mode '{}' ({} steps)",
                manifest.name,
                manifest.version,
                plan.chosen_mode,
                plan.steps.len()
            );
            println!("\nSteps that would be executed:");
            for (idx, step) in plan.steps.iter().enumerate() {
                println!("  [{}/{}] {}", idx + 1, plan.steps.len(), step.description);
            }
            return 0;
        } else {
            println!(
                "Preparing to install {} {} using mode '{}' ({} steps)",
                manifest.name,
                manifest.version,
                plan.chosen_mode,
                plan.steps.len()
            );
        }
    } else if dry_run {
        // JSON dry-run output
        print_json(&serde_json::json!({
            "ok": true,
            "dry_run": true,
            "plan": plan,
            "steps_count": plan.steps.len()
        }));
        return 0;
    }

    match execute_plan(&plan) {
        Ok(result) => {
            let record = InstallRecord {
                app_name: manifest.name.clone(),
                app_version: manifest.version.clone(),
                mode: plan.chosen_mode.clone(),
                os: env.os.clone(),
                cpu_arch: env.cpu_arch.clone(),
                timestamp: Utc::now(),
                status: InstallStatus::Success,
                artifacts: result.artifacts.clone(),
            };
            let _ = add_install_record(record);
            
            // Write audit entry
            let audit_entry = create_audit_entry(
                "install",
                Some(&manifest_path),
                Some(&manifest.name),
                Some(&manifest.version),
                Some(&plan.chosen_mode),
                Some(result.completed_steps),
                "success",
                None,
            );
            let _ = write_audit_entry(&audit_entry);

            if json {
                print_json(&InstallResponse {
                    ok: true,
                    plan: Some(plan),
                    result: Some(result),
                    error: None,
                });
            } else {
                println!("Installation complete ({} steps).", result.completed_steps);
            }
            0
        }
        Err(err) => {
            let failed_index = match &err {
                ExecutionError::StepFailed { index, .. } => Some(*index),
                _ => None,
            };
            let record = InstallRecord {
                app_name: manifest.name.clone(),
                app_version: manifest.version.clone(),
                mode: plan.chosen_mode.clone(),
                os: env.os.clone(),
                cpu_arch: env.cpu_arch.clone(),
                timestamp: Utc::now(),
                status: InstallStatus::Failed,
                artifacts: Vec::new(), // Failed installs don't track artifacts
            };
            let _ = add_install_record(record);
            
            // Write audit entry
            let error_msg = err.to_string();
            let audit_entry = create_audit_entry(
                "install",
                Some(&manifest_path),
                Some(&manifest.name),
                Some(&manifest.version),
                Some(&plan.chosen_mode),
                None,
                "failed",
                Some(&error_msg),
            );
            let _ = write_audit_entry(&audit_entry);

            emit_install_error(json, Some(&plan), &err.to_string(), failed_index);
            3
        }
    }
}

fn handle_list_installed(json: bool) -> i32 {
    match load_state() {
        Ok(state) => {
            if json {
                print_json(&ListResponse {
                    ok: true,
                    installs: state.installs,
                });
            } else {
                if state.installs.is_empty() {
                    println!("No installs recorded yet.");
                } else {
                    println!("Recorded installs:");
                    for record in state.installs {
                        println!(
                            "- {} {} [{}] on {} ({}): {:?} at {}",
                            record.app_name,
                            record.app_version,
                            record.mode,
                            record.os,
                            record.cpu_arch,
                            record.status,
                            record.timestamp
                        );
                    }
                }
            }
            0
        }
        Err(err) => {
            if json {
                print_json(&ListErrorResponse {
                    ok: false,
                    error: err.to_string(),
                });
            } else {
                eprintln!("{err}");
            }
            1
        }
    }
}

fn emit_install_error(
    json: bool,
    plan: Option<&InstallPlan>,
    message: &str,
    failed_index: Option<usize>,
) {
    if json {
        print_json(&InstallResponse {
            ok: false,
            plan: plan.cloned(),
            result: None,
            error: Some(InstallErrorResponse {
                message: message.to_string(),
                failed_step_index: failed_index,
            }),
        });
    } else {
        eprintln!("{message}");
        if let Some(plan) = plan {
            eprintln!(
                "Plan '{}' with {} steps was in progress.",
                plan.chosen_mode,
                plan.steps.len()
            );
        }
    }
}

fn handle_uninstall(json: bool, app_name: String, version: Option<String>, dry_run: bool) -> i32 {
    use crate::state::{load_state, save_state, Artifact};
    use std::fs;

    match load_state() {
        Ok(mut state) => {
            // Find matching installs
            let mut to_remove: Vec<usize> = Vec::new();
            let mut artifacts_to_clean: Vec<Artifact> = Vec::new();

            for (idx, record) in state.installs.iter().enumerate() {
                if record.app_name == app_name {
                    if let Some(ref ver) = version {
                        if record.app_version == *ver && record.status == crate::state::InstallStatus::Success {
                            to_remove.push(idx);
                            artifacts_to_clean.extend(record.artifacts.clone());
                        }
                    } else if record.status == crate::state::InstallStatus::Success {
                        to_remove.push(idx);
                        artifacts_to_clean.extend(record.artifacts.clone());
                    }
                }
            }

            if to_remove.is_empty() {
                if json {
                    print_json(&serde_json::json!({
                        "ok": false,
                        "error": format!("No successful installation found for {} {}", app_name, version.as_ref().map(|v| format!("version {}", v)).unwrap_or_else(|| "any version".to_string()))
                    }));
                } else {
                    eprintln!("No successful installation found for {} {}", app_name, version.as_ref().map(|v| format!("version {}", v)).unwrap_or_else(|| "any version".to_string()));
                }
                return 1;
            }

            if dry_run {
                if json {
                    print_json(&serde_json::json!({
                        "ok": true,
                        "dry_run": true,
                        "would_remove": to_remove.len(),
                        "artifacts": artifacts_to_clean
                    }));
                } else {
                    println!("Dry run: Would remove {} installation(s) and {} artifact(s)", to_remove.len(), artifacts_to_clean.len());
                    for artifact in &artifacts_to_clean {
                        match artifact {
                            Artifact::DownloadedFile { path } => println!("  - Downloaded file: {}", path.display()),
                            Artifact::ExtractedDirectory { path } => println!("  - Extracted directory: {}", path.display()),
                            Artifact::CreatedFile { path } => println!("  - Created file: {}", path.display()),
                            Artifact::RuntimeEnv { root, kind } => println!("  - Runtime environment ({}) at: {}", kind, root.display()),
                        }
                    }
                }
                return 0;
            }

            // Remove artifacts
            let mut removed_count = 0;
            let mut errors = Vec::new();

            for artifact in &artifacts_to_clean {
                match artifact {
                    Artifact::DownloadedFile { path } | Artifact::CreatedFile { path } => {
                        if path.exists() {
                            if let Err(e) = fs::remove_file(path) {
                                errors.push(format!("Failed to remove file {}: {}", path.display(), e));
                            } else {
                                removed_count += 1;
                            }
                        }
                    }
                    Artifact::ExtractedDirectory { path } | Artifact::RuntimeEnv { root: path, .. } => {
                        if path.exists() {
                            if let Err(e) = fs::remove_dir_all(path) {
                                errors.push(format!("Failed to remove directory {}: {}", path.display(), e));
                            } else {
                                removed_count += 1;
                            }
                        }
                    }
                }
            }

            let removed_installs_count = to_remove.len();
            
            // Remove records (in reverse order to maintain indices)
            to_remove.reverse();
            for idx in to_remove {
                state.installs.remove(idx);
            }

            if let Err(e) = save_state(&state) {
                if json {
                    print_json(&serde_json::json!({
                        "ok": false,
                        "error": format!("Failed to save state: {}", e)
                    }));
                } else {
                    eprintln!("Failed to save state: {}", e);
                }
                return 1;
            }

            if json {
                print_json(&serde_json::json!({
                    "ok": true,
                    "removed_installs": removed_installs_count,
                    "removed_artifacts": removed_count,
                    "errors": errors
                }));
            } else {
                println!("Uninstalled {} (removed {} installation(s), {} artifact(s))", app_name, removed_installs_count, removed_count);
                if !errors.is_empty() {
                    eprintln!("Warnings:");
                    for error in &errors {
                        eprintln!("  - {}", error);
                    }
                }
            }
            
            // Write audit entry
            let error_msg = if errors.is_empty() { None } else { Some(errors.join("; ")) };
            let audit_entry = create_audit_entry(
                "uninstall",
                None,
                Some(&app_name),
                version.as_deref(),
                None,
                Some(removed_installs_count),
                "success",
                error_msg.as_deref(),
            );
            let _ = write_audit_entry(&audit_entry);

            0
        }
        Err(err) => {
            if json {
                print_json(&serde_json::json!({
                    "ok": false,
                    "error": err.to_string()
                }));
            } else {
                eprintln!("{}", err);
            }
            1
        }
    }
}

fn print_json<T: Serialize>(value: &T) {
    match serde_json::to_string_pretty(value) {
        Ok(text) => println!("{text}"),
        Err(err) => eprintln!("failed to render JSON: {err}"),
    }
}
