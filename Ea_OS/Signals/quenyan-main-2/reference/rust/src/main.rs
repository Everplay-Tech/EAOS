mod package;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use package::{decode_descriptor, encode_descriptor, Descriptor};
use std::fs;
use std::io::{self, Read, Write};
use std::path::PathBuf;

#[derive(Parser)]
#[command(
    name = "mcs-reference",
    about = "Reference MCS encoder/decoder for framed packages (CRC-validated, payload channels supported)",
    disable_help_subcommand = true
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Decode a framed package into a JSON descriptor
    Decode {
        #[arg(long)]
        passphrase: String,
        #[arg(long)]
        input: Option<PathBuf>,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    /// Encode a JSON descriptor into a framed package
    Encode {
        #[arg(long)]
        passphrase: String,
        #[arg(long)]
        input: Option<PathBuf>,
        #[arg(long)]
        output: Option<PathBuf>,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Decode {
            passphrase,
            input,
            output,
        } => {
            let data = read_all(input)?;
            let raw = base64::decode(data.trim_end())?;
            let descriptor = decode_descriptor(&raw, &passphrase)?;
            let serialised = serde_json::to_vec(&descriptor)?;
            write_all(output, &serialised)?;
        }
        Commands::Encode {
            passphrase,
            input,
            output,
        } => {
            let data = read_all(input)?;
            let descriptor: Descriptor = serde_json::from_slice(&data)?;
            let encoded = encode_descriptor(descriptor, &passphrase)?;
            let b64 = base64::encode(encoded);
            write_all(output, b64.as_bytes())?;
        }
    }
    Ok(())
}

fn read_all(path: Option<PathBuf>) -> Result<Vec<u8>> {
    let mut buf = Vec::new();
    match path {
        Some(p) => buf = fs::read(p).context("failed to read input file")?,
        None => {
            io::stdin()
                .read_to_end(&mut buf)
                .context("failed to read stdin")?;
        }
    }
    Ok(buf)
}

fn write_all(path: Option<PathBuf>, data: &[u8]) -> Result<()> {
    match path {
        Some(p) => fs::write(p, data).context("failed to write output file")?,
        None => {
            io::stdout()
                .write_all(data)
                .context("failed to write stdout")?;
        }
    }
    Ok(())
}
