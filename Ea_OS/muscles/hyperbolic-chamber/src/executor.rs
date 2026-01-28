use std::fs::{self, File};
use std::io::{BufRead, BufReader, BufWriter, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use anyhow::{Context, anyhow};
use bzip2::read::BzDecoder;
use flate2::read::GzDecoder;
use indicatif::{ProgressBar, ProgressStyle};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::time::Instant;
use tar::Archive;
use tracing::{debug, error, info, warn};
use xz2::read::XzDecoder;

use crate::manifest::{DownloadStep, ExtractStep, Step, TemplateConfigStep};
use crate::planner::{InstallPlan, PlannedStep};
use crate::runtime_env::{ExecutionContext, prepare_runtime_env};
use crate::security::check_url_allowed;
use crate::state::Artifact;

#[derive(Debug, Serialize)]
pub struct ExecutionResult {
    pub completed_steps: usize,
    pub total_steps: usize,
    pub artifacts: Vec<Artifact>,
}

#[derive(Debug, thiserror::Error)]
pub enum ExecutionError {
    #[error("step {index} failed: {message}")]
    StepFailed { index: usize, message: String },
    #[error(transparent)]
    Other(#[from] anyhow::Error),
}

pub fn execute_plan(plan: &InstallPlan) -> Result<ExecutionResult, ExecutionError> {
    info!(
        app_name = %plan.app_name,
        app_version = %plan.app_version,
        mode = %plan.chosen_mode,
        steps = plan.steps.len(),
        "Executing installation plan"
    );

    let context = prepare_runtime_env(plan).map_err(ExecutionError::Other)?;
    let mut artifacts = Vec::new();

    // Track runtime environment if created
    if let Some(ref runtime_env) = plan.runtime_env {
        if let Some(ref _ctx) = context {
            // Runtime env was created, track it
            artifacts.push(Artifact::RuntimeEnv {
                root: runtime_env.root.clone(),
                kind: match runtime_env.kind {
                    crate::manifest::RuntimeEnvType::NodeLocal => "node_local".to_string(),
                    crate::manifest::RuntimeEnvType::PythonVenv => "python_venv".to_string(),
                },
            });
        }
    }

    for (idx, step) in plan.steps.iter().enumerate() {
        info!(
            step_index = idx + 1,
            total_steps = plan.steps.len(),
            description = %step.description,
            "Executing step"
        );
        match execute_step(&plan.os, step, context.as_ref()) {
            Ok(step_artifacts) => {
                artifacts.extend(step_artifacts);
            }
            Err(err) => {
                return Err(match err {
                    ExecutionError::StepFailed { .. } => err,
                    ExecutionError::Other(source) => ExecutionError::StepFailed {
                        index: idx,
                        message: source.to_string(),
                    },
                });
            }
        }
    }

    Ok(ExecutionResult {
        completed_steps: plan.steps.len(),
        total_steps: plan.steps.len(),
        artifacts,
    })
}

fn execute_step(
    os: &str,
    step: &PlannedStep,
    ctx: Option<&ExecutionContext>,
) -> Result<Vec<Artifact>, ExecutionError> {
    match &step.step {
        Step::Run { run } => {
            run_command(os, run, ctx).map_err(|err| ExecutionError::StepFailed {
                index: step.index,
                message: err.to_string(),
            })?;
            Ok(Vec::new())
        }
        Step::Download { download } => {
            perform_download(download).map_err(|err| ExecutionError::StepFailed {
                index: step.index,
                message: err.to_string(),
            })?;
            // Track downloaded file
            Ok(vec![Artifact::DownloadedFile {
                path: download.dest.clone(),
            }])
        }
        Step::Extract { extract } => {
            perform_extract(extract).map_err(|err| ExecutionError::StepFailed {
                index: step.index,
                message: err.to_string(),
            })?;
            // Track extracted directory
            Ok(vec![Artifact::ExtractedDirectory {
                path: extract.dest.clone(),
            }])
        }
        Step::TemplateConfig { template_config } => {
            render_template(template_config).map_err(|err| ExecutionError::StepFailed {
                index: step.index,
                message: err.to_string(),
            })?;
            // Track created file
            Ok(vec![Artifact::CreatedFile {
                path: template_config.dest.clone(),
            }])
        }
    }
}

fn run_command(os: &str, command: &str, ctx: Option<&ExecutionContext>) -> anyhow::Result<()> {
    let shell_cmd = if os == "windows" {
        "cmd".to_string()
    } else {
        // Detect shell for Unix-like systems
        std::env::var("SHELL")
            .ok()
            .and_then(|s| {
                if std::path::Path::new(&s).exists() {
                    Some(s)
                } else {
                    None
                }
            })
            .or_else(|| {
                // Fallback to common shells
                for shell in ["/bin/bash", "/bin/sh"] {
                    if std::path::Path::new(shell).exists() {
                        return Some(shell.to_string());
                    }
                }
                None
            })
            .unwrap_or_else(|| "/bin/sh".to_string())
    };
    
    let shell_args: Vec<&str> = if os == "windows" {
        vec!["/C"]
    } else {
        vec!["-c"]
    };

    let mut cmd = Command::new(&shell_cmd);
    cmd.args(&shell_args).arg(command);
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    if let Some(ctx) = ctx {
        for (key, value) in &ctx.env {
            cmd.env(key, value);
        }
    }

    let mut child = cmd
        .spawn()
        .with_context(|| format!("spawning shell command: {command}"))?;

    // Capture stdout and stderr for error reporting
    let stdout = child.stdout.take().ok_or_else(|| {
        anyhow!("failed to capture stdout for command: {command}")
    })?;
    let stderr = child.stderr.take().ok_or_else(|| {
        anyhow!("failed to capture stderr for command: {command}")
    })?;

    // Store output for error messages
    let stdout_lines = Arc::new(Mutex::new(Vec::new()));
    let stderr_lines = Arc::new(Mutex::new(Vec::new()));

    let stdout_lines_clone = Arc::clone(&stdout_lines);
    let stderr_lines_clone = Arc::clone(&stderr_lines);

    // Spawn threads to stream stdout and stderr
    let stdout_handle = thread::spawn(move || {
        let reader = BufReader::new(stdout);
        let mut lines = stdout_lines_clone.lock().unwrap();
        for line in reader.lines() {
            match line {
                Ok(line) => {
                    println!("{}", line); // Keep println for user-visible output
                    lines.push(line);
                }
                Err(err) => {
                    error!(error = %err, "Error reading stdout line");
                }
            }
        }
    });

    let stderr_handle = thread::spawn(move || {
        let reader = BufReader::new(stderr);
        let mut lines = stderr_lines_clone.lock().unwrap();
        for line in reader.lines() {
            match line {
                Ok(line) => {
                    eprintln!("{}", line); // Keep eprintln for user-visible output
                    lines.push(line);
                }
                Err(err) => {
                    error!(error = %err, "Error reading stderr line");
                }
            }
        }
    });

    // Wait for output streams to finish
    stdout_handle.join().map_err(|_| {
        anyhow!("stdout thread panicked while running command: {command}")
    })?;
    stderr_handle.join().map_err(|_| {
        anyhow!("stderr thread panicked while running command: {command}")
    })?;

    // Wait for process to complete
    let status = child
        .wait()
        .with_context(|| format!("waiting for shell command: {command}"))?;

    if !status.success() {
        let stdout_output: Vec<String> = stdout_lines.lock().unwrap().clone();
        let stderr_output: Vec<String> = stderr_lines.lock().unwrap().clone();
        
        let mut error_msg = format!(
            "command exited with status {:?}",
            status.code()
        );
        
        if !stdout_output.is_empty() {
            error_msg.push_str("\n\nStdout:\n");
            error_msg.push_str(&stdout_output.join("\n"));
        }
        
        if !stderr_output.is_empty() {
            error_msg.push_str("\n\nStderr:\n");
            error_msg.push_str(&stderr_output.join("\n"));
        }
        
        return Err(anyhow!("{}", error_msg));
    }

    Ok(())
}

pub fn perform_download(step: &DownloadStep) -> anyhow::Result<()> {
    const DEFAULT_TIMEOUT_SECS: u64 = 30;
    const MAX_RETRIES: u32 = 3;
    const INITIAL_RETRY_DELAY_SECS: u64 = 1;

    // Check URL against security policy
    check_url_allowed(&step.url)
        .with_context(|| format!("URL security check failed for {}", step.url))?;

    let timeout_secs = step.timeout_secs.unwrap_or(DEFAULT_TIMEOUT_SECS);
    let timeout = Duration::from_secs(timeout_secs);

    let mut last_error = None;
    
    for attempt in 0..=MAX_RETRIES {
        let client = reqwest::blocking::Client::builder()
            .timeout(timeout)
            .build()
            .context("building HTTP client")?;

        match client.get(&step.url).send() {
            Ok(mut response) => {
                // Check status code
                if !response.status().is_success() {
                    let status = response.status();
                    // Don't retry on 4xx errors (client errors)
                    if status.is_client_error() {
                        return Err(anyhow!("download failed with status {}: {}", status, step.url));
                    }
                    // Retry on 5xx errors (server errors)
                    if status.is_server_error() {
                        last_error = Some(anyhow!("download failed with status {}: {}", status, step.url));
                        if attempt < MAX_RETRIES {
                            let delay = INITIAL_RETRY_DELAY_SECS * (1 << attempt);
                            std::thread::sleep(Duration::from_secs(delay));
                            continue;
                        }
                        return Err(last_error.unwrap());
                    }
                    return Err(anyhow!("download failed with status {}: {}", status, step.url));
                }

                // Success - proceed with download
                let server_reported_length = response.content_length();
                return perform_download_with_response(step, response, timeout_secs, server_reported_length);
            }
            Err(err) => {
                // Check if error is retryable
                let is_retryable = err.is_timeout() 
                    || err.is_connect() 
                    || err.is_request();

                if !is_retryable || attempt >= MAX_RETRIES {
                    return Err(if err.is_timeout() {
                        anyhow!(
                            "download timed out after {}s while requesting {}",
                            timeout_secs,
                            step.url
                        )
                    } else {
                        anyhow!("requesting {}: {err}", step.url)
                    });
                }

                last_error = Some(if err.is_timeout() {
                    anyhow!(
                        "download timed out after {}s while requesting {}",
                        timeout_secs,
                        step.url
                    )
                } else {
                    anyhow!("requesting {}: {err}", step.url)
                });

                // Exponential backoff
                let delay = INITIAL_RETRY_DELAY_SECS * (1 << attempt);
                std::thread::sleep(Duration::from_secs(delay));
            }
        }
    }

    Err(last_error.unwrap_or_else(|| anyhow!("download failed after {} retries", MAX_RETRIES)))
}

fn perform_download_with_response(
    step: &DownloadStep,
    mut response: reqwest::blocking::Response,
    timeout_secs: u64,
    _server_reported_length: Option<u64>,
) -> anyhow::Result<()> {
    let server_reported_length = response.content_length();

    if let Some(expected) = step.expected_size {
        if let Some(content_length) = server_reported_length {
            if content_length != expected {
                return Err(anyhow!(
                    "expected content length {} bytes but server reported {}",
                    expected,
                    content_length
                ));
            }
        }
    }

    if let Some(parent) = step.dest.parent() {
        fs::create_dir_all(parent)?;
    }

    let mut dest_file = BufWriter::new(
        File::create(&step.dest)
            .with_context(|| format!("creating destination file {}", step.dest.display()))?,
    );

    let mut hasher = step.expected_sha256.as_ref().map(|_| Sha256::new());
    let mut downloaded: u64 = 0;
    let mut buffer = [0u8; 8 * 1024];

    // Setup progress bar
    let total_size = step.expected_size.or(server_reported_length);
    let pb = if total_size.is_some() {
        let pb = ProgressBar::new(total_size.unwrap());
        pb.set_style(
            ProgressStyle::default_bar()
                .template("{spinner:.green} [{elapsed_precise}] [{wide_bar:.cyan/blue}] {bytes}/{total_bytes} ({bytes_per_sec}, {eta})")
                .unwrap()
                .progress_chars("#>-"),
        );
        Some(pb)
    } else {
        let pb = ProgressBar::new_spinner();
        pb.set_style(
            ProgressStyle::default_spinner()
                .template("{spinner:.green} [{elapsed_precise}] {bytes} downloaded ({bytes_per_sec})")
                .unwrap(),
        );
        Some(pb)
    };

    let start_time = Instant::now();
    let mut last_update = Instant::now();

    loop {
        let read = response.read(&mut buffer).map_err(|err| {
            if let Some(pb) = &pb {
                pb.finish_and_clear();
            }
            if err.kind() == std::io::ErrorKind::TimedOut {
                anyhow!(
                    "download timed out after {}s while reading {}",
                    timeout_secs,
                    step.url
                )
            } else if let Some(expected) = step.expected_size.or(server_reported_length) {
                anyhow!(
                    "downloaded size mismatch: expected {} bytes, got {} bytes",
                    expected,
                    downloaded
                )
            } else {
                anyhow!("reading response from {}: {err}", step.url)
            }
        })?;

        if read == 0 {
            break;
        }

        dest_file
            .write_all(&buffer[..read])
            .with_context(|| format!("writing to {}", step.dest.display()))?;
        downloaded += read as u64;

        if let Some(hasher) = hasher.as_mut() {
            hasher.update(&buffer[..read]);
        }

        // Update progress bar every 100ms or every 1MB
        if last_update.elapsed().as_millis() > 100 || downloaded % (1024 * 1024) == 0 {
            if let Some(pb) = &pb {
                if let Some(total) = total_size {
                    pb.set_position(downloaded);
                } else {
                    pb.set_length(downloaded.max(1));
                    pb.set_position(downloaded);
                }
            }
            last_update = Instant::now();
        }
    }

    if let Some(pb) = &pb {
        pb.finish_and_clear();
    }

    dest_file.flush()?;

    if let Some(expected) = step.expected_size {
        if downloaded != expected {
            return Err(anyhow!(
                "downloaded size mismatch: expected {} bytes, got {} bytes",
                expected,
                downloaded
            ));
        }
    }

    if let Some(expected_hash) = &step.expected_sha256 {
        let actual_hash = hasher
            .take()
            .expect("hasher created when expected_sha256 is Some")
            .finalize();
        let actual_hex = format!("{:x}", actual_hash);

        if !actual_hex.eq_ignore_ascii_case(expected_hash) {
            return Err(anyhow!(
                "download hash mismatch: expected {}, got {}",
                expected_hash,
                actual_hex
            ));
        }
    }

    Ok(())
}

#[derive(Debug, Clone, Copy)]
enum ArchiveFormat {
    Zip,
    Tar,
    TarGz,
    TarBz2,
    TarXz,
    Gz,
}

fn detect_archive_format(path: &Path) -> anyhow::Result<ArchiveFormat> {
    // First check file extension
    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
        let ext_lower = ext.to_lowercase();
        match ext_lower.as_str() {
            "zip" => return Ok(ArchiveFormat::Zip),
            "gz" => {
                // Could be .tar.gz or standalone .gz
                if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                    if stem.ends_with(".tar") {
                        return Ok(ArchiveFormat::TarGz);
                    }
                }
                return Ok(ArchiveFormat::Gz);
            }
            "bz2" => {
                // Could be .tar.bz2
                if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                    if stem.ends_with(".tar") {
                        return Ok(ArchiveFormat::TarBz2);
                    }
                }
                return Err(anyhow!("unsupported archive format: standalone .bz2 files are not supported"));
            }
            "xz" => {
                // Could be .tar.xz
                if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                    if stem.ends_with(".tar") {
                        return Ok(ArchiveFormat::TarXz);
                    }
                }
                return Err(anyhow!("unsupported archive format: standalone .xz files are not supported"));
            }
            "tar" => return Ok(ArchiveFormat::Tar),
            _ => {}
        }
    }

    // Fallback: check magic bytes
    let mut file = File::open(path)
        .with_context(|| format!("opening archive for format detection: {}", path.display()))?;
    let mut magic = [0u8; 4];
    file.read_exact(&mut magic)
        .with_context(|| format!("reading magic bytes from: {}", path.display()))?;

    match &magic {
        [0x50, 0x4B, 0x03, 0x04] | [0x50, 0x4B, 0x05, 0x06] | [0x50, 0x4B, 0x07, 0x08] => {
            Ok(ArchiveFormat::Zip)
        }
        [0x1F, 0x8B, ..] => Ok(ArchiveFormat::TarGz), // gzip magic
        [0x42, 0x5A, 0x68, ..] => Ok(ArchiveFormat::TarBz2), // bzip2 magic
        [0xFD, 0x37, 0x7A, 0x58] => Ok(ArchiveFormat::TarXz), // xz magic
        _ => {
            // Check if it's a tar file (tar files don't have a consistent magic header)
            // Try to read as tar
            if path.extension().and_then(|e| e.to_str()) == Some("tar") {
                Ok(ArchiveFormat::Tar)
            } else {
                Err(anyhow!(
                    "unable to detect archive format for: {}",
                    path.display()
                ))
            }
        }
    }
}

pub fn perform_extract(step: &ExtractStep) -> anyhow::Result<()> {
    let archive_path = &step.archive;
    let dest_dir = &step.dest;

    if let Some(parent) = dest_dir.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::create_dir_all(dest_dir)?;

    let format = detect_archive_format(archive_path)?;

    match format {
        ArchiveFormat::Zip => extract_zip(archive_path, dest_dir)?,
        ArchiveFormat::Tar => extract_tar(archive_path, dest_dir)?,
        ArchiveFormat::TarGz => extract_tar_gz(archive_path, dest_dir)?,
        ArchiveFormat::TarBz2 => extract_tar_bz2(archive_path, dest_dir)?,
        ArchiveFormat::TarXz => extract_tar_xz(archive_path, dest_dir)?,
        ArchiveFormat::Gz => extract_gz(archive_path, dest_dir)?,
    }

    Ok(())
}

fn extract_zip(archive_path: &Path, dest_dir: &Path) -> anyhow::Result<()> {
    let file = File::open(archive_path)
        .with_context(|| format!("opening zip archive {}", archive_path.display()))?;
    let mut archive = zip::ZipArchive::new(file)
        .with_context(|| format!("reading zip archive {}", archive_path.display()))?;

    for i in 0..archive.len() {
        let mut file = archive.by_index(i)?;
        let outpath = sanitize_extract_path(dest_dir, file.name())?;

        if file.is_dir() {
            fs::create_dir_all(&outpath)?;
        } else {
            if let Some(parent) = outpath.parent() {
                fs::create_dir_all(parent)?;
            }
            let mut outfile = File::create(&outpath)?;
            std::io::copy(&mut file, &mut outfile)?;

            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Some(mode) = file.unix_mode() {
                    fs::set_permissions(&outpath, fs::Permissions::from_mode(mode))?;
                }
            }
        }
    }

    Ok(())
}

fn extract_tar(archive_path: &Path, dest_dir: &Path) -> anyhow::Result<()> {
    let file = File::open(archive_path)
        .with_context(|| format!("opening tar archive {}", archive_path.display()))?;
    let mut archive = Archive::new(file);
    archive
        .unpack(dest_dir)
        .with_context(|| format!("extracting tar archive to {}", dest_dir.display()))?;
    Ok(())
}

fn extract_tar_gz(archive_path: &Path, dest_dir: &Path) -> anyhow::Result<()> {
    let file = File::open(archive_path)
        .with_context(|| format!("opening tar.gz archive {}", archive_path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut archive = Archive::new(decoder);
    archive
        .unpack(dest_dir)
        .with_context(|| format!("extracting tar.gz archive to {}", dest_dir.display()))?;
    Ok(())
}

fn extract_tar_bz2(archive_path: &Path, dest_dir: &Path) -> anyhow::Result<()> {
    let file = File::open(archive_path)
        .with_context(|| format!("opening tar.bz2 archive {}", archive_path.display()))?;
    let decoder = BzDecoder::new(file);
    let mut archive = Archive::new(decoder);
    archive
        .unpack(dest_dir)
        .with_context(|| format!("extracting tar.bz2 archive to {}", dest_dir.display()))?;
    Ok(())
}

fn extract_tar_xz(archive_path: &Path, dest_dir: &Path) -> anyhow::Result<()> {
    let file = File::open(archive_path)
        .with_context(|| format!("opening tar.xz archive {}", archive_path.display()))?;
    let decoder = XzDecoder::new(file);
    let mut archive = Archive::new(decoder);
    archive
        .unpack(dest_dir)
        .with_context(|| format!("extracting tar.xz archive to {}", dest_dir.display()))?;
    Ok(())
}

fn extract_gz(archive_path: &Path, dest_dir: &Path) -> anyhow::Result<()> {
    // For standalone .gz files, extract to a single file
    let file = File::open(archive_path)
        .with_context(|| format!("opening gz archive {}", archive_path.display()))?;
    let mut decoder = GzDecoder::new(file);
    
    // Determine output filename (remove .gz extension)
    let output_name = archive_path
        .file_stem()
        .and_then(|s| s.to_str())
        .ok_or_else(|| anyhow!("unable to determine output filename for: {}", archive_path.display()))?;
    
    let output_path = dest_dir.join(output_name);
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    
    let mut output_file = File::create(&output_path)
        .with_context(|| format!("creating output file {}", output_path.display()))?;
    
    std::io::copy(&mut decoder, &mut output_file)
        .with_context(|| format!("decompressing gz file to {}", output_path.display()))?;
    
    Ok(())
}

fn sanitize_extract_path(dest: &Path, name: &str) -> anyhow::Result<PathBuf> {
    let path = PathBuf::from(name);
    if path
        .components()
        .any(|c| matches!(c, std::path::Component::ParentDir))
    {
        return Err(anyhow!("archive entry escapes destination: {name}"));
    }

    if path.is_absolute() {
        return Err(anyhow!("archive entry has absolute path: {name}"));
    }

    let full_path = dest.join(&path);
    
    // On systems with symlinked temp dirs (like macOS), directly comparing canonicalized paths
    // is safer but requires the target to exist. Since we are extracting, it doesn't exist yet.
    // Instead, we verify that the resolved parent of the target is within the resolved destination.
    let dest_canonical = fs::canonicalize(dest).unwrap_or_else(|_| dest.to_path_buf());
    
    // We can't canonicalize full_path if it doesn't exist.
    // We canonicalize the parent directory if possible, or just check the path structure.
    // Given the previous checks (no ParentDir components, no absolute), simple joining is usually safe
    // IF dest is safe.
    
    // Double check by resolving the parent
    if let Some(parent) = full_path.parent() {
        // If the parent directory exists, we can canonicalize it to ensure it's under dest
        if parent.exists() {
            let parent_canonical = fs::canonicalize(parent).unwrap_or_else(|_| parent.to_path_buf());
            if !parent_canonical.starts_with(&dest_canonical) {
                 return Err(anyhow!("archive entry outside destination: {name}"));
            }
        }
    }

    Ok(full_path)
}

pub fn render_template(step: &TemplateConfigStep) -> anyhow::Result<()> {
    let mut source = String::new();
    File::open(&step.source)
        .with_context(|| format!("opening template {}", step.source.display()))?
        .read_to_string(&mut source)?;

    let rendered = replace_placeholders(&source, &step.vars);

    if let Some(parent) = step.dest.parent() {
        fs::create_dir_all(parent)?;
    }

    let mut dest_file = File::create(&step.dest)
        .with_context(|| format!("writing templated config {}", step.dest.display()))?;
    dest_file.write_all(rendered.as_bytes())?;
    Ok(())
}

fn replace_placeholders(
    template: &str,
    vars: &std::collections::HashMap<String, String>,
) -> String {
    let mut result = String::new();
    let mut remainder = template;
    while let Some(start) = remainder.find("{{") {
        if let Some(end) = remainder[start + 2..].find("}}") {
            let end_index = start + 2 + end;
            result.push_str(&remainder[..start]);
            let key = &remainder[start + 2..end_index];
            if let Some(value) = vars.get(key.trim()) {
                result.push_str(value);
            } else {
                result.push_str("{{");
                result.push_str(key);
                result.push_str("}}");
            }
            remainder = &remainder[end_index + 2..];
            continue;
        }
        break;
    }
    result.push_str(remainder);
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn executes_linux_run_steps() {
        let dir = tempfile::tempdir().expect("tempdir should be created");
        let output = dir.path().join("out.txt");
        let command = format!("echo hi > {}", output.display());

        let plan = InstallPlan {
            app_name: "demo".into(),
            app_version: "1.0.0".into(),
            chosen_mode: "full".into(),
            os: "linux".into(),
            runtime_env: None,
            steps: vec![PlannedStep {
                description: "write to file".into(),
                command: Some(command.clone()),
                step: Step::Run { run: command },
                index: 0,
            }],
        };

        let result = execute_plan(&plan).expect("plan should execute");
        assert_eq!(result.completed_steps, 1);
        let written = std::fs::read_to_string(output).expect("file should exist");
        assert_eq!(written.trim(), "hi");
    }

    #[test]
    fn renders_template_and_respects_unknown_keys() {
        let dir = tempfile::tempdir().expect("tempdir should be created");
        let source = dir.path().join("template.txt");
        let dest = dir.path().join("output.txt");

        fs::write(&source, "hello {{NAME}} and {{MISSING}}!").expect("template should be written");

        let mut vars = HashMap::new();
        vars.insert("NAME".to_string(), "world".to_string());

        render_template(&TemplateConfigStep {
            source: source.clone(),
            dest: dest.clone(),
            vars,
        })
        .expect("templating should succeed");

        let rendered = fs::read_to_string(&dest).expect("output should exist");
        assert_eq!(rendered, "hello world and {{MISSING}}!");
    }

    #[test]
    fn extracts_zip_archives_safely() {
        let dir = tempfile::tempdir().expect("tempdir should be created");
        let archive_path = dir.path().join("archive.zip");
        let dest_dir = dir.path().join("out");

        {
            let file = File::create(&archive_path).expect("archive should be created");
            let mut zip = zip::ZipWriter::new(file);
            let options = zip::write::FileOptions::default();
            zip.start_file("nested/file.txt", options)
                .expect("file entry should start");
            zip.write_all(b"contents")
                .expect("zip entry should be written");
            zip.finish().expect("zip should finish");
        }

        perform_extract(&ExtractStep {
            archive: archive_path,
            dest: dest_dir.clone(),
        })
        .expect("extraction should succeed");

        let extracted = dest_dir.join("nested/file.txt");
        assert!(extracted.exists());
        let text = fs::read_to_string(extracted).expect("extracted file readable");
        assert_eq!(text, "contents");
    }
}
