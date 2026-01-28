pub mod audit;
pub mod cli;
pub mod env_detect;
pub mod executor;
pub mod manifest;
pub mod planner;
pub mod runtime_env;
pub mod security;
pub mod state;

use anyhow::Context;
use tracing_subscriber::EnvFilter;

pub fn init_logging(log_level: Option<&str>, log_file: Option<&std::path::Path>) -> anyhow::Result<()> {
    let filter = if let Some(level) = log_level {
        EnvFilter::new(level)
    } else {
        EnvFilter::from_default_env()
    };

    if let Some(log_path) = log_file {
        let file = std::fs::File::create(log_path)
            .with_context(|| format!("creating log file {}", log_path.display()))?;
        tracing_subscriber::fmt()
            .with_env_filter(filter)
            .with_writer(file)
            .json()
            .init();
    } else {
        tracing_subscriber::fmt()
            .with_env_filter(filter)
            .init();
    }

    Ok(())
}

/// Run the command line interface and return an exit code.
pub fn run_cli() -> i32 {
    cli::run()
}
