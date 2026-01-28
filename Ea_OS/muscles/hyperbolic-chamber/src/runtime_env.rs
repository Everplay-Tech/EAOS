use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use anyhow::{Context, anyhow};
use flate2::read::GzDecoder;
use sha2::{Digest, Sha256};
use tar::Archive;
use which::which;

use crate::manifest::{RuntimeEnv, RuntimeEnvType};
use crate::planner::InstallPlan;

#[derive(Debug, Clone)]
pub struct ExecutionContext {
    pub env: HashMap<String, String>,
    pub path_prefixes: Vec<PathBuf>,
}

impl ExecutionContext {
    pub fn new() -> Self {
        Self {
            env: HashMap::new(),
            path_prefixes: Vec::new(),
        }
    }

    pub fn merged_path(&self) -> Option<String> {
        if self.path_prefixes.is_empty() {
            return None;
        }

        let existing = std::env::var_os("PATH")
            .map(|p| p.into_string().unwrap_or_default())
            .unwrap_or_default();
        let separator = if cfg!(windows) { ';' } else { ':' };
        let mut segments: Vec<String> = self
            .path_prefixes
            .iter()
            .map(|p| p.to_string_lossy().to_string())
            .collect();
        if !existing.is_empty() {
            segments.push(existing);
        }

        Some(segments.join(&separator.to_string()))
    }
}

pub fn prepare_runtime_env(plan: &InstallPlan) -> anyhow::Result<Option<ExecutionContext>> {
    let Some(runtime) = plan.runtime_env.as_ref() else {
        return Ok(None);
    };

    let mut ctx = ExecutionContext::new();
    match runtime.kind {
        RuntimeEnvType::NodeLocal => prepare_node_env(runtime, &plan.os, &mut ctx)?,
        RuntimeEnvType::PythonVenv => prepare_python_env(runtime, &plan.os, &mut ctx)?,
    }

    if let Some(path) = ctx.merged_path() {
        ctx.env.insert("PATH".to_string(), path);
    }

    Ok(Some(ctx))
}

fn prepare_node_env(
    runtime: &RuntimeEnv,
    os: &str,
    ctx: &mut ExecutionContext,
) -> anyhow::Result<()> {
    let root = resolve_root(&runtime.root)?;
    let node_root = root.join("node");
    std::fs::create_dir_all(&node_root)
        .with_context(|| format!("creating node runtime at {}", node_root.display()))?;

    let strategy = runtime
        .node
        .as_ref()
        .and_then(|n| n.install_strategy.clone())
        .unwrap_or_else(|| "local_bundle_or_global".to_string());

    if let Some(bin_dir) = locate_existing_node(&node_root, os) {
        ctx.path_prefixes.push(bin_dir);
        return Ok(());
    }

    if strategy.contains("global") && which("node").is_ok() {
        return Ok(());
    }

    let version = runtime
        .node
        .as_ref()
        .and_then(|n| n.version.clone())
        .ok_or_else(|| anyhow!("node version must be specified for managed installations"))?;

    let bin_dir = install_node_version(&node_root, &version, os)?;
    ctx.path_prefixes.push(bin_dir);

    Ok(())
}

fn prepare_python_env(
    runtime: &RuntimeEnv,
    os: &str,
    ctx: &mut ExecutionContext,
) -> anyhow::Result<()> {
    let root = resolve_root(&runtime.root)?;
    let venv_dir = root.join("venv");
    let bin_dir = if os == "windows" {
        venv_dir.join("Scripts")
    } else {
        venv_dir.join("bin")
    };

    let python_cfg = runtime
        .python
        .as_ref()
        .ok_or_else(|| anyhow!("python runtime configuration must be provided"))?;
    let strategy = python_cfg
        .install_strategy
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .unwrap_or("venv_or_global")
        .to_string();
    if strategy != "venv_or_global" && strategy != "local_only" {
        return Err(anyhow!("unsupported python install_strategy {strategy}"));
    }
    let required_version = python_cfg
        .version
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty());

    let resolved = select_python_interpreter(&root, os, required_version, &strategy)?;

    // Probe the interpreter we intend to use to ensure it is callable before venv creation.
    let resolved_version = probe_python_version(&resolved.command)?;
    if required_version
        .map(|req| !version_satisfies(&resolved_version, req))
        .unwrap_or(false)
    {
        return Err(anyhow!(
            "selected Python interpreter version {resolved_version} does not satisfy required {req}",
            req = required_version.unwrap_or_default()
        ));
    }

    if venv_exists(&bin_dir, os) {
        let venv_python = python_in_dir(&bin_dir, os);
        let venv_version = probe_python_version(&PythonCommand::from_path(
            &venv_python,
            "existing virtualenv",
        ))?;

        if required_version
            .map(|req| !version_satisfies(&venv_version, req))
            .unwrap_or(false)
        {
            fs::remove_dir_all(&venv_dir)
                .with_context(|| format!("removing incompatible venv at {}", venv_dir.display()))?;
        }
    }

    if !venv_exists(&bin_dir, os) {
        create_venv(&venv_dir, os, &resolved.command)?;
    }

    let venv_python = python_in_dir(&bin_dir, os);
    let active_version = probe_python_version(&PythonCommand::from_path(
        &venv_python,
        "prepared virtualenv",
    ))?;

    if required_version
        .map(|req| !version_satisfies(&active_version, req))
        .unwrap_or(false)
    {
        return Err(anyhow!(
            "virtualenv Python version {active_version} does not satisfy required {req}",
            req = required_version.unwrap_or_default()
        ));
    }

    ctx.env.insert(
        "VIRTUAL_ENV".to_string(),
        venv_dir.to_string_lossy().to_string(),
    );
    ctx.path_prefixes.push(bin_dir);

    Ok(())
}

fn venv_exists(bin_dir: &Path, os: &str) -> bool {
    python_in_dir(bin_dir, os).exists()
}

fn create_venv(path: &Path, _os: &str, python: &PythonCommand) -> anyhow::Result<()> {
    std::fs::create_dir_all(path.parent().unwrap_or(Path::new(".")))?;

    probe_python_version(&PythonCommand {
        program: python.program.clone(),
        args: python.args.clone(),
        origin: format!("{} (probe)", python.origin),
    })?;

    let mut cmd = python.to_command();
    cmd.args(["-m", "venv", path.to_string_lossy().as_ref()]);
    let status = cmd
        .status()
        .with_context(|| format!("creating python virtual environment with {}", python.origin))?;

    if !status.success() {
        return Err(anyhow!(
            "failed to create python virtual environment using {}",
            python.origin
        ));
    }

    Ok(())
}

fn python_in_dir(bin_dir: &Path, os: &str) -> PathBuf {
    bin_dir.join(if os == "windows" {
        "python.exe"
    } else {
        "python"
    })
}

#[derive(Debug, Clone)]
struct PythonCommand {
    program: PathBuf,
    args: Vec<String>,
    origin: String,
}

impl PythonCommand {
    fn new(program: PathBuf, args: Vec<String>, origin: String) -> Self {
        Self {
            program,
            args,
            origin,
        }
    }

    fn from_path(program: &Path, origin: &str) -> Self {
        Self {
            program: program.to_path_buf(),
            args: Vec::new(),
            origin: origin.to_string(),
        }
    }

    fn to_command(&self) -> Command {
        let mut cmd = Command::new(&self.program);
        cmd.args(&self.args);
        cmd
    }
}

#[derive(Debug, Clone)]
struct ResolvedPython {
    command: PythonCommand,
    version: String,
}

fn select_python_interpreter(
    root: &Path,
    os: &str,
    required_version: Option<&str>,
    strategy: &str,
) -> anyhow::Result<ResolvedPython> {
    let mut observed: Vec<(String, String)> = Vec::new();

    let managed_python = locate_managed_python(root, os);
    if let Some(managed) = managed_python.clone() {
        if let Ok(version) =
            probe_python_version(&PythonCommand::from_path(&managed, "managed python"))
        {
            if required_version
                .map(|req| version_satisfies(&version, req))
                .unwrap_or(true)
            {
                return Ok(ResolvedPython {
                    command: PythonCommand::from_path(&managed, "managed python"),
                    version,
                });
            }
            observed.push(("managed python".to_string(), version));
        }
    }

    if strategy != "local_only" {
        for candidate in global_python_candidates(os)? {
            match probe_python_version(&candidate) {
                Ok(version) => {
                    if required_version
                        .map(|req| version_satisfies(&version, req))
                        .unwrap_or(true)
                    {
                        return Ok(ResolvedPython {
                            command: candidate,
                            version,
                        });
                    }

                    observed.push((candidate.origin.clone(), version));
                }
                Err(err) => {
                    observed.push((candidate.origin.clone(), format!("probe failed: {err}")));
                }
            }
        }
    }

    if let Some(req) = required_version {
        if let Some(downloaded) = install_python_version(root, req, os)? {
            let cmd = PythonCommand::from_path(&downloaded, "downloaded python");
            let version = probe_python_version(&cmd)?;
            if version_satisfies(&version, req) {
                return Ok(ResolvedPython {
                    command: cmd,
                    version,
                });
            }

            observed.push(("downloaded python".to_string(), version));
        }
    }

    if let Some(req) = required_version {
        let discovered = if observed.is_empty() {
            "none found".to_string()
        } else {
            observed
                .iter()
                .map(|(origin, version)| format!("{origin} ({version})"))
                .collect::<Vec<_>>()
                .join(", ")
        };
        if strategy == "local_only" && managed_python.is_none() {
            return Err(anyhow!(
                "install_strategy local_only requires a bundled Python {req}; discovered {discovered}"
            ));
        }

        let download_hint = if std::env::var("ENZYME_PYTHON_RUNTIME").is_err() {
            " Set ENZYME_PYTHON_RUNTIME to a compatible interpreter binary to allow downloads."
                .to_string()
        } else {
            String::new()
        };

        return Err(anyhow!(
            "no compatible Python interpreter found for {req}; discovered {discovered}.{download_hint}"
        ));
    }

    Err(anyhow!("no usable Python interpreter found"))
}

fn global_python_candidates(os: &str) -> anyhow::Result<Vec<PythonCommand>> {
    let mut candidates = Vec::new();
    let names = match os {
        "windows" => vec!["py", "python", "python3"],
        _ => vec!["python3", "python"],
    };

    for name in names {
        if let Ok(path) = which(name) {
            candidates.push(PythonCommand::new(
                path,
                Vec::new(),
                format!("{name} on PATH"),
            ));
        }
    }

    Ok(candidates)
}

fn probe_python_version(candidate: &PythonCommand) -> anyhow::Result<String> {
    let mut cmd = candidate.to_command();
    cmd.arg("-V");
    let output = cmd
        .output()
        .with_context(|| format!("probing python version via {}", candidate.origin))?;

    if !output.status.success() {
        return Err(anyhow!(
            "python version probe failed for {} with status {}",
            candidate.origin,
            output.status
        ));
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let combined = format!("{stdout}{stderr}");
    let parsed = parse_python_version(&combined)
        .ok_or_else(|| anyhow!("unable to parse python version from probe output"))?;

    Ok(parsed)
}

fn parse_python_version(output: &str) -> Option<String> {
    output
        .split_whitespace()
        .nth(1)
        .map(|v| v.trim().to_string())
}

fn version_satisfies(found: &str, required: &str) -> bool {
    let required_parts: Vec<&str> = required.split('.').collect();
    let found_parts: Vec<&str> = found.split('.').collect();

    for (idx, req) in required_parts.iter().enumerate() {
        match found_parts.get(idx) {
            Some(found) if found == req => continue,
            _ => return false,
        }
    }

    true
}

fn install_python_version(root: &Path, version: &str, os: &str) -> anyhow::Result<Option<PathBuf>> {
    let Ok(source) = std::env::var("ENZYME_PYTHON_RUNTIME") else {
        return Ok(None);
    };

    let source_path = PathBuf::from(&source);
    if !source_path.exists() {
        return Err(anyhow!(
            "ENZYME_PYTHON_RUNTIME={source} does not exist; cannot install Python {version}"
        ));
    }

    let install_root = root.join("python").join("runtime");
    let bin_dir = if os == "windows" {
        install_root.clone()
    } else {
        install_root.join("bin")
    };
    fs::create_dir_all(&bin_dir).context("creating python runtime directory")?;

    let target = python_in_dir(&bin_dir, os);
    fs::copy(&source_path, &target).with_context(|| {
        format!(
            "copying python runtime from {} to {}",
            source_path.display(),
            target.display()
        )
    })?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&target)?.permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&target, permissions)?;
    }

    Ok(Some(target))
}

fn locate_managed_python(root: &Path, os: &str) -> Option<PathBuf> {
    let install_root = root.join("python").join("runtime");
    let bin_dir = if os == "windows" {
        install_root.clone()
    } else {
        install_root.join("bin")
    };

    let candidate = python_in_dir(&bin_dir, os);
    if candidate.exists() {
        Some(candidate)
    } else {
        None
    }
}

fn resolve_root(root: &Path) -> anyhow::Result<PathBuf> {
    if root.is_absolute() {
        return Ok(root.to_path_buf());
    }

    let cwd = std::env::current_dir().context("resolving runtime_env root")?;
    Ok(cwd.join(root))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ArchiveKind {
    TarGz,
    Zip,
}

const DEFAULT_DOWNLOAD_TIMEOUT: Duration = Duration::from_secs(30);
const MAX_CHECKSUM_DOWNLOAD_BYTES: u64 = 10 * 1024 * 1024; // 10MB safety ceiling for checksum metadata.
const MAX_BUNDLE_DOWNLOAD_BYTES: u64 = 1_024 * 1024 * 1024; // 1GB cap for runtime bundles.

#[derive(Clone, Copy)]
struct DownloadOptions<'a> {
    timeout: Duration,
    max_length: Option<u64>,
    expected_sha256: Option<&'a str>,
}

fn install_node_version(node_root: &Path, version: &str, os: &str) -> anyhow::Result<PathBuf> {
    let arch = normalize_arch(std::env::consts::ARCH);
    let (platform, archive_kind, extension) = platform_triple(os, &arch)?;

    let cache_dir = node_root.join("cache");
    fs::create_dir_all(&cache_dir).context("creating node cache directory")?;

    let file_name = format!("node-v{version}-{platform}.{extension}");
    let bundle_path = cache_dir.join(&file_name);
    let shasums_path = cache_dir.join("SHASUMS256.txt");

    let dist_base = node_dist_base();
    let bundle_url = format!("{dist_base}/v{version}/{file_name}");
    let checksum_url = format!("{dist_base}/v{version}/SHASUMS256.txt");

    if !shasums_path.exists() {
        download_file(
            &checksum_url,
            &shasums_path,
            DownloadOptions {
                timeout: DEFAULT_DOWNLOAD_TIMEOUT,
                max_length: Some(MAX_CHECKSUM_DOWNLOAD_BYTES),
                expected_sha256: None,
            },
        )
        .with_context(|| format!("downloading Node checksums from {checksum_url}"))?;
    }

    let expected_checksum = read_expected_checksum(&shasums_path, &file_name)?;

    if !bundle_path.exists() {
        download_file(
            &bundle_url,
            &bundle_path,
            DownloadOptions {
                timeout: DEFAULT_DOWNLOAD_TIMEOUT,
                max_length: Some(MAX_BUNDLE_DOWNLOAD_BYTES),
                expected_sha256: Some(&expected_checksum),
            },
        )
        .with_context(|| format!("downloading Node bundle from {bundle_url}"))?;
    }

    verify_checksum(&bundle_path, &expected_checksum)?;

    let install_dir = node_root.join("runtime");
    let staging_dir = node_root.join("staging");
    if staging_dir.exists() {
        fs::remove_dir_all(&staging_dir)
            .with_context(|| format!("clearing staging directory at {}", staging_dir.display()))?;
    }
    fs::create_dir_all(&staging_dir)
        .with_context(|| format!("creating staging directory at {}", staging_dir.display()))?;

    extract_bundle(&bundle_path, &staging_dir, archive_kind)?;

    let node_binary = locate_node_binary(&staging_dir, os)
        .ok_or_else(|| anyhow!("downloaded Node bundle did not contain a node binary"))?;

    let distribution_root = candidate_distribution_root(&node_binary);

    if install_dir.exists() {
        fs::remove_dir_all(&install_dir)
            .with_context(|| format!("clearing previous install at {}", install_dir.display()))?;
    }

    fs::rename(&distribution_root, &install_dir).with_context(|| {
        format!(
            "moving extracted node distribution from {} to {}",
            distribution_root.display(),
            install_dir.display()
        )
    })?;

    if staging_dir.exists() {
        let _ = fs::remove_dir_all(&staging_dir);
    }

    let bin_dir = stable_bin_dir(&install_dir, os)?;
    Ok(bin_dir)
}

fn stable_bin_dir(install_dir: &Path, os: &str) -> anyhow::Result<PathBuf> {
    let bin_dir = install_dir.join("bin");
    let primary_binary = bin_dir.join(if os == "windows" { "node.exe" } else { "node" });
    if primary_binary.exists() {
        return Ok(bin_dir);
    }

    let fallback = install_dir.join(if os == "windows" { "node.exe" } else { "node" });
    if fallback.exists() {
        return Ok(install_dir.to_path_buf());
    }

    Err(anyhow!(
        "installed Node runtime did not contain an executable binary"
    ))
}

fn node_dist_base() -> String {
    std::env::var("ENZYME_NODE_MIRROR").unwrap_or_else(|_| "https://nodejs.org/dist".to_string())
}

fn platform_triple(os: &str, arch: &str) -> anyhow::Result<(String, ArchiveKind, &'static str)> {
    match os {
        "windows" => Ok((format!("win-{arch}"), ArchiveKind::Zip, "zip")),
        "macos" => Ok((format!("darwin-{arch}"), ArchiveKind::TarGz, "tar.gz")),
        "linux" => Ok((format!("linux-{arch}"), ArchiveKind::TarGz, "tar.gz")),
        other => Err(anyhow!("unsupported platform for node runtime: {other}")),
    }
}

fn normalize_arch(raw: &str) -> String {
    match raw {
        "x86_64" => "x64".to_string(),
        "aarch64" => "arm64".to_string(),
        other => other.to_lowercase(),
    }
}

fn locate_existing_node(node_root: &Path, os: &str) -> Option<PathBuf> {
    let install_dir = node_root.join("runtime");
    stable_bin_dir(&install_dir, os).ok()
}

fn extract_bundle(bundle: &Path, dest: &Path, kind: ArchiveKind) -> anyhow::Result<()> {
    match kind {
        ArchiveKind::TarGz => {
            let file = File::open(bundle)
                .with_context(|| format!("opening archive {}", bundle.display()))?;
            let decoder = GzDecoder::new(file);
            let mut archive = Archive::new(decoder);
            archive
                .unpack(dest)
                .with_context(|| format!("extracting tar archive to {}", dest.display()))?;
        }
        ArchiveKind::Zip => extract_zip(bundle, dest)?,
    }

    Ok(())
}

fn candidate_distribution_root(node_binary: &Path) -> PathBuf {
    let parent = node_binary.parent().unwrap_or(node_binary);
    if parent.file_name().map(|p| p == "bin").unwrap_or(false) {
        parent.parent().unwrap_or(parent).to_path_buf()
    } else {
        parent.to_path_buf()
    }
}

fn extract_zip(archive_path: &Path, dest_dir: &Path) -> anyhow::Result<()> {
    if let Some(parent) = dest_dir.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::create_dir_all(dest_dir)?;

    let file = File::open(archive_path)
        .with_context(|| format!("opening archive {}", archive_path.display()))?;
    let mut archive = zip::ZipArchive::new(file)
        .with_context(|| format!("reading zip archive {}", archive_path.display()))?;

    for i in 0..archive.len() {
        let mut file = archive.by_index(i)?;
        let outpath = dest_dir.join(file.sanitized_name());

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

fn locate_node_binary(staging_dir: &Path, os: &str) -> Option<PathBuf> {
    let target = if os == "windows" { "node.exe" } else { "node" };
    let mut stack = vec![staging_dir.to_path_buf()];

    while let Some(dir) = stack.pop() {
        for entry in fs::read_dir(dir).ok()? {
            let entry = entry.ok()?;
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
            } else if path.file_name().map(|f| f == target).unwrap_or(false) {
                return Some(path);
            }
        }
    }

    None
}

fn download_file(url: &str, dest: &Path, options: DownloadOptions<'_>) -> anyhow::Result<()> {
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }

    let client = reqwest::blocking::Client::builder()
        .timeout(options.timeout)
        .build()
        .context("building HTTP client")?;

    let mut response = client
        .get(url)
        .send()
        .map_err(|err| download_error(err, url, options.timeout))?;
    if !response.status().is_success() {
        return Err(anyhow!("download failed with status {}", response.status()));
    }

    if let (Some(max_length), Some(content_length)) =
        (options.max_length, response.content_length())
    {
        if content_length > max_length {
            return Err(anyhow!(
                "download size {} exceeds limit of {} bytes",
                content_length,
                max_length
            ));
        }
    }

    let mut hasher = options.expected_sha256.as_ref().map(|_| Sha256::new());
    let expected_hash = options
        .expected_sha256
        .map(|value| value.trim().to_ascii_lowercase());

    let mut dest_file = File::create(dest)
        .with_context(|| format!("creating destination file {}", dest.display()))?;

    let result: anyhow::Result<()> = (|| {
        let mut bytes_read: u64 = 0;
        let mut buffer = [0u8; 8192];

        loop {
        let read = response.read(&mut buffer).map_err(|err| {
            if err.kind() == std::io::ErrorKind::TimedOut {
                anyhow!(
                    "download timed out after {:?} while reading {}",
                    options.timeout,
                    url
                )
            } else {
                anyhow!("reading response from {}: {err}", url)
            }
        })?;

            if read == 0 {
                break;
            }

            bytes_read += read as u64;
            if let Some(max_length) = options.max_length {
                if bytes_read > max_length {
                    return Err(anyhow!(
                        "download exceeded maximum size of {} bytes",
                        max_length
                    ));
                }
            }

            if let Some(hasher) = hasher.as_mut() {
                hasher.update(&buffer[..read]);
            }

            dest_file.write_all(&buffer[..read])?;
        }

        if let (Some(mut hasher), Some(expected)) = (hasher, expected_hash) {
            let actual = format!("{:x}", hasher.finalize());
            if actual != expected {
                return Err(anyhow!(
                    "checksum mismatch while downloading {url}: expected {expected}, got {actual}",
                ));
            }
        }

        dest_file.flush()?;
        Ok(())
    })();

    if result.is_err() {
        let _ = fs::remove_file(dest);
    }

    result
}

fn download_error(error: reqwest::Error, url: &str, timeout: Duration) -> anyhow::Error {
    if error.is_timeout() {
        anyhow!("download from {url} timed out after {:?}", timeout)
    } else {
        anyhow!("request to {url} failed: {error}")
    }
}

fn read_expected_checksum(shasums: &Path, file_name: &str) -> anyhow::Result<String> {
    let content = fs::read_to_string(shasums)
        .with_context(|| format!("reading checksum file {}", shasums.display()))?;

    for line in content.lines() {
        let mut parts = line.split_whitespace();
        if let (Some(sum), Some(name)) = (parts.next(), parts.next()) {
            if name == file_name {
                return Ok(sum.to_string());
            }
        }
    }

    Err(anyhow!(
        "checksum for {file_name} not found in {}",
        shasums.display()
    ))
}

fn verify_checksum(file: &Path, expected_hex: &str) -> anyhow::Result<()> {
    let mut hasher = Sha256::new();
    let mut f = File::open(file)
        .with_context(|| format!("opening archive for checksum {}", file.display()))?;
    let mut buffer = [0u8; 8192];
    loop {
        let read = f.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }

    let actual = format!("{:x}", hasher.finalize());
    if actual == expected_hex {
        return Ok(());
    }

    Err(anyhow!(
        "checksum mismatch for {}: expected {}, got {}",
        file.display(),
        expected_hex,
        actual
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::fs;
    use std::net::{TcpListener, TcpStream};
    use std::path::Path;
    use std::thread;
    use std::time::Duration;

    use tempfile::tempdir;
    use flate2::{Compression, write::GzEncoder};

    use crate::manifest::{NodeRuntime, PythonRuntime, RuntimeEnv, RuntimeEnvType};
    use std::sync::{Mutex, OnceLock};

    fn env_lock() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    struct ScopedEnv {
        key: String,
        original: Option<String>,
    }

    impl ScopedEnv {
        fn new(key: &str, value: &str) -> Self {
            let original = std::env::var(key).ok();
            unsafe { std::env::set_var(key, value); }
            Self { key: key.to_string(), original }
        }
    }

    impl Drop for ScopedEnv {
        fn drop(&mut self) {
            unsafe {
                if let Some(val) = &self.original {
                    std::env::set_var(&self.key, val);
                } else {
                    std::env::remove_var(&self.key);
                }
            }
        }
    }

    fn write_python_shim(path: &Path, version: &str) {
        let script = format!(
            "#!/bin/sh\nif [ \"$1\" = \"-V\" ] || [ \"$1\" = \"--version\" ]; then\n  echo \"Python {version}\"\n  exit 0\nfi\nif [ \"$1\" = \"-m\" ] && [ \"$2\" = \"venv\" ]; then\n  target=\"$3\"\n  mkdir -p \"$target/bin\"\n  cat > \"$target/bin/python\" <<'EOF'\n#!/bin/sh\necho \"Python {version}\"\nEOF\n  chmod +x \"$target/bin/python\"\n  exit 0\nfi\necho \"unsupported args\" 1>&2\nexit 1\n"
        );

        fs::write(path, script).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut permissions = fs::metadata(path).unwrap().permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(path, permissions).unwrap();
        }
    }

    fn start_http_server<F>(handler: F) -> String
    where
        F: FnOnce(TcpStream) + Send + 'static,
    {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();

        thread::spawn(move || {
            if let Ok((stream, _)) = listener.accept() {
                handler(stream);
            }
        });

        format!("http://{}", addr)
    }

    fn write_http_response(mut stream: TcpStream, body: &[u8]) {
        write!(
            stream,
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        )
        .unwrap();
        stream.write_all(body).unwrap();
    }

    #[test]
    fn installs_node_from_cached_bundle() {
        let temp = tempdir().unwrap();
        let root = temp.path();
        let version = "1.2.3";
        let os = "linux";

        let expected_bin = seed_cached_node_bundle(root, version, os, true);

        let ctx = prepare_runtime_env(&plan_with_runtime(root, version, os, "local_only"))
            .expect("runtime env should prepare")
            .expect("execution context expected");

        assert!(expected_bin.join("node").exists());
        assert!(
            ctx.env
                .get("PATH")
                .map(|p| p.starts_with(expected_bin.to_string_lossy().as_ref()))
                .unwrap_or(false)
        );
        assert_eq!(ctx.path_prefixes, vec![expected_bin]);
    }

    #[test]
    fn reuses_existing_installation() {
        let temp = tempdir().unwrap();
        let root = temp.path();
        let version = "2.0.0";
        let os = "linux";

        let bin_dir = seed_cached_node_bundle(root, version, os, true);
        let plan = plan_with_runtime(root, version, os, "local_only");

        prepare_runtime_env(&plan).expect("initial install");
        let binary_path = bin_dir.join("node");
        let original_mtime = fs::metadata(&binary_path).unwrap().modified().unwrap();

        let ctx = prepare_runtime_env(&plan).expect("reuse install").unwrap();

        assert_eq!(ctx.path_prefixes, vec![bin_dir.clone()]);
        let reused_mtime = fs::metadata(&binary_path).unwrap().modified().unwrap();
        assert!(
            reused_mtime
                .duration_since(original_mtime)
                .unwrap_or_default()
                < std::time::Duration::from_secs(1)
        );
        assert!(!root.join("node").join("staging").exists());
    }

    #[test]
    fn errors_on_checksum_mismatch() {
        let temp = tempdir().unwrap();
        let root = temp.path();
        let version = "3.1.4";
        let os = "linux";

        seed_cached_node_bundle(root, version, os, false);

        let err = prepare_runtime_env(&plan_with_runtime(root, version, os, "local_only"))
            .expect_err("checksum mismatch should error");
        assert!(err.to_string().contains("checksum mismatch"));
    }

    #[test]
    fn falls_back_to_global_python_when_local_missing() {
        let _guard = env_lock().lock().unwrap();
        let temp = tempdir().unwrap();
        let root = temp.path();
        let os = "linux";

        let shim_dir = root.join("shims");
        fs::create_dir_all(&shim_dir).unwrap();
        let shim_path = shim_dir.join("python3");
        write_python_shim(&shim_path, "3.11.4");

        let original_path = std::env::var("PATH").unwrap_or_default();
        let _path_env = ScopedEnv::new("PATH", &format!("{}:{}", shim_dir.display(), original_path));

        let ctx = prepare_runtime_env(&plan_with_python(root, Some("3.11"), os, "venv_or_global"))
            .expect("runtime env should prepare")
            .expect("execution context expected");

        let venv_python = root.join("venv").join("bin").join("python");
        let version = probe_python_version(&PythonCommand::from_path(&venv_python, "venv python"))
            .expect("version should probe");
        assert!(version_satisfies(&version, "3.11"));
        assert!(ctx.env.get("VIRTUAL_ENV").is_some());
    }

    #[test]
    fn rebuilds_incompatible_virtualenv_with_new_interpreter() {
        let _guard = env_lock().lock().unwrap();
        let temp = tempdir().unwrap();
        let root = temp.path();
        let os = "linux";

        let venv_bin = root.join("venv").join("bin");
        fs::create_dir_all(&venv_bin).unwrap();
        let existing_python = python_in_dir(&venv_bin, os);
        write_python_shim(&existing_python, "3.9.0");

        let shim_dir = root.join("shim_rebuild");
        fs::create_dir_all(&shim_dir).unwrap();
        let shim_path = shim_dir.join("python3");
        write_python_shim(&shim_path, "3.10.2");

        let original_path = std::env::var("PATH").unwrap_or_default();
        let _path_env = ScopedEnv::new("PATH", &format!("{}:{}", shim_dir.display(), original_path));

        let ctx = prepare_runtime_env(&plan_with_python(root, Some("3.10"), os, "venv_or_global"))
            .expect("runtime env should prepare")
            .expect("execution context expected");

        let venv_python = python_in_dir(&root.join("venv").join("bin"), os);
        let version = probe_python_version(&PythonCommand::from_path(&venv_python, "venv python"))
            .expect("version should probe");
        assert!(version_satisfies(&version, "3.10"));
        assert!(ctx.env.get("VIRTUAL_ENV").is_some());
    }

    #[test]
    fn downloads_python_when_globals_incompatible() {
        let _guard = env_lock().lock().unwrap();
        let temp = tempdir().unwrap();
        let root = temp.path();
        let os = "linux";

        let shim_dir = root.join("shim_incompatible_download");
        fs::create_dir_all(&shim_dir).unwrap();
        let shim_path = shim_dir.join("python3");
        write_python_shim(&shim_path, "3.9.0");

        let download_source = root.join("python-3-10");
        write_python_shim(&download_source, "3.10.1");

        let original_path = std::env::var("PATH").unwrap_or_default();
        let _path_env = ScopedEnv::new("PATH", &format!("{}:{}", shim_dir.display(), original_path));
        let _runtime_env = ScopedEnv::new("ENZYME_PYTHON_RUNTIME", &download_source.to_string_lossy());

        let ctx = prepare_runtime_env(&plan_with_python(root, Some("3.10"), os, "venv_or_global"))
            .expect("runtime env should prepare")
            .expect("execution context expected");

        let managed_python =
            locate_managed_python(root, os).expect("managed runtime should be installed");
        let managed_version =
            probe_python_version(&PythonCommand::from_path(&managed_python, "managed python"))
                .expect("managed version should probe");
        assert!(version_satisfies(&managed_version, "3.10"));

        let venv_python = python_in_dir(&root.join("venv").join("bin"), os);
        let version = probe_python_version(&PythonCommand::from_path(&venv_python, "venv python"))
            .expect("version should probe");
        assert!(version_satisfies(&version, "3.10"));
        assert!(ctx.env.get("VIRTUAL_ENV").is_some());
    }

    #[test]
    fn local_only_errors_without_bundled_python() {
        let _guard = env_lock().lock().unwrap();
        let temp = tempdir().unwrap();
        let root = temp.path();
        let os = "linux";

        let shim_dir = root.join("shim_local_only");
        fs::create_dir_all(&shim_dir).unwrap();
        let shim_path = shim_dir.join("python3");
        write_python_shim(&shim_path, "3.10.5");

        let original_path = std::env::var("PATH").unwrap_or_default();
        let _path_env = ScopedEnv::new("PATH", &format!("{}:{}", shim_dir.display(), original_path));

        // Make sure ENZYME_PYTHON_RUNTIME is not set
        let _runtime_env_guard = ScopedEnv { key: "ENZYME_PYTHON_RUNTIME".to_string(), original: std::env::var("ENZYME_PYTHON_RUNTIME").ok() };
        unsafe { std::env::remove_var("ENZYME_PYTHON_RUNTIME"); }

        let err = prepare_runtime_env(&plan_with_python(root, Some("3.10"), os, "local_only"))
            .expect_err("local_only should not rely on global interpreters");
        let message = err.to_string();
        assert!(message.contains("local_only"));
        assert!(message.contains("3.10"));
    }

    #[test]
    fn errors_when_python_version_is_incompatible() {
        let _guard = env_lock().lock().unwrap();
        let temp = tempdir().unwrap();
        let root = temp.path();
        let os = "linux";

        let shim_dir = root.join("shim_incompatible");
        fs::create_dir_all(&shim_dir).unwrap();
        let shim_path = shim_dir.join("python3");
        write_python_shim(&shim_path, "3.9.0");

        let original_path = std::env::var("PATH").unwrap_or_default();
        let _path_env = ScopedEnv::new("PATH", &format!("{}:{}", shim_dir.display(), original_path));

        let err = prepare_runtime_env(&plan_with_python(root, Some("3.11"), os, "venv_or_global"))
            .expect_err("should fail when only incompatible versions exist");
        let message = err.to_string();
        assert!(message.contains("3.11"));
        assert!(message.contains("3.9.0"));
    }

    fn plan_with_runtime(root: &Path, version: &str, os: &str, strategy: &str) -> InstallPlan {
        InstallPlan {
            app_name: "app".into(),
            app_version: "0.0.1".into(),
            chosen_mode: "test".into(),
            os: os.to_string(),
            runtime_env: Some(RuntimeEnv {
                kind: RuntimeEnvType::NodeLocal,
                root: root.to_path_buf(),
                node: Some(NodeRuntime {
                    version: Some(version.to_string()),
                    install_strategy: Some(strategy.to_string()),
                }),
                python: None,
            }),
            steps: vec![],
        }
    }

    fn plan_with_python(
        root: &Path,
        version: Option<&str>,
        os: &str,
        strategy: &str,
    ) -> InstallPlan {
        InstallPlan {
            app_name: "app".into(),
            app_version: "0.0.1".into(),
            chosen_mode: "test".into(),
            os: os.to_string(),
            runtime_env: Some(RuntimeEnv {
                kind: RuntimeEnvType::PythonVenv,
                root: root.to_path_buf(),
                node: None,
                python: Some(PythonRuntime {
                    version: version.map(|v| v.to_string()),
                    install_strategy: Some(strategy.to_string()),
                }),
            }),
            steps: vec![],
        }
    }

    fn seed_cached_node_bundle(
        root: &Path,
        version: &str,
        os: &str,
        valid_checksum: bool,
    ) -> PathBuf {
        let node_root = root.join("node");
        fs::create_dir_all(&node_root).unwrap();

        let arch = normalize_arch(std::env::consts::ARCH);
        let (platform, archive_kind, extension) = platform_triple(os, &arch).unwrap();
        assert_eq!(archive_kind, ArchiveKind::TarGz);

        let file_name = format!("node-v{version}-{platform}.{extension}");
        let cache_dir = node_root.join("cache");
        fs::create_dir_all(&cache_dir).unwrap();
        let bundle_path = cache_dir.join(&file_name);

        write_tarball(&bundle_path, version, &platform).unwrap();
        write_shasums(
            &cache_dir.join("SHASUMS256.txt"),
            &file_name,
            &bundle_path,
            valid_checksum,
        )
        .unwrap();

        node_root.join("runtime").join("bin")
    }

    fn write_tarball(bundle_path: &Path, version: &str, platform: &str) -> anyhow::Result<()> {
        if let Some(parent) = bundle_path.parent() {
            fs::create_dir_all(parent)?;
        }
        let file = File::create(bundle_path)?;
        let encoder = GzEncoder::new(file, Compression::default());
        let mut tar = tar::Builder::new(encoder);

        let binary_path = format!("node-v{version}-{platform}/bin/node");
        let mut header = tar::Header::new_gnu();
        let contents = b"#!/usr/bin/env node";
        header.set_path(&binary_path)?;
        header.set_mode(0o755);
        header.set_size(contents.len() as u64);
        header.set_cksum();
        tar.append(&header, &contents[..])?;
        tar.finish()?;
        let encoder = tar.into_inner()?;
        encoder.finish()?;

        Ok(())
    }

    fn write_shasums(
        shasum_path: &Path,
        file_name: &str,
        bundle_path: &Path,
        valid_checksum: bool,
    ) -> anyhow::Result<()> {
        let checksum = if valid_checksum {
            compute_checksum(bundle_path)?
        } else {
            "deadbeef".repeat(8)
        };

        let mut file = File::create(shasum_path)?;
        writeln!(file, "{checksum}  {file_name}")?;
        Ok(())
    }

    fn compute_checksum(path: &Path) -> anyhow::Result<String> {
        let mut hasher = Sha256::new();
        let mut file = File::open(path)?;
        let mut buf = [0u8; 4096];
        loop {
            let read = file.read(&mut buf)?;
            if read == 0 {
                break;
            }
            hasher.update(&buf[..read]);
        }

        Ok(format!("{:x}", hasher.finalize()))
    }

    #[test]
    fn download_file_times_out_when_server_stalls() {
        let url = start_http_server(|stream| {
            thread::sleep(Duration::from_millis(200));
            write_http_response(stream, b"slow response");
        });

        let temp = tempdir().unwrap();
        let dest = temp.path().join("timeout.txt");

        let err = download_file(
            &(url + "/timeout"),
            &dest,
            DownloadOptions {
                timeout: Duration::from_millis(50),
                max_length: None,
                expected_sha256: None,
            },
        )
        .expect_err("download should time out");

        assert!(
            err.to_string().contains("timed out"),
            "unexpected error: {err:?}"
        );
        assert!(!dest.exists());
    }

    #[test]
    fn download_file_rejects_oversized_body() {
        let body = vec![0u8; 32];
        let url = start_http_server(move |stream| write_http_response(stream, &body));

        let temp = tempdir().unwrap();
        let dest = temp.path().join("oversized.bin");

        let err = download_file(
            &(url + "/oversized"),
            &dest,
            DownloadOptions {
                timeout: Duration::from_secs(1),
                max_length: Some(8),
                expected_sha256: None,
            },
        )
        .expect_err("download should fail due to size constraint");

        assert!(
            err.to_string().contains("exceeds limit"),
            "unexpected error: {err:?}"
        );
        assert!(!dest.exists());
    }

    #[test]
    fn download_file_aborts_on_checksum_mismatch() {
        let body = b"expected payload".to_vec();
        let url = start_http_server(move |stream| write_http_response(stream, &body));
        let expected = format!("{:x}", Sha256::digest(b"different payload"));

        let temp = tempdir().unwrap();
        let dest = temp.path().join("checksum.bin");

        let err = download_file(
            &(url + "/checksum"),
            &dest,
            DownloadOptions {
                timeout: Duration::from_secs(1),
                max_length: Some(1024),
                expected_sha256: Some(&expected),
            },
        )
        .expect_err("download should fail checksum validation");

        assert!(
            err.to_string().contains("checksum mismatch"),
            "unexpected error: {err:?}"
        );
        assert!(!dest.exists());
    }
}
