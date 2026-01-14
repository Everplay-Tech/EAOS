mod package;

use anyhow::{Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use clap::{Parser, Subcommand};
use ea_symbiote::{BlobType, SovereignBlob};
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
        /// Extract from SovereignBlob wrapper if present
        #[arg(long)]
        from_sovereign: bool,
    },
    /// Encode a JSON descriptor into a framed package
    Encode {
        #[arg(long)]
        passphrase: String,
        #[arg(long)]
        input: Option<PathBuf>,
        #[arg(long)]
        output: Option<PathBuf>,
        /// Wrap output in SovereignBlob for PermFS storage
        #[arg(long)]
        emit_sovereign: bool,
        /// Label for the SovereignBlob (used with --emit-sovereign)
        #[arg(long)]
        label: Option<String>,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Decode {
            passphrase,
            input,
            output,
            from_sovereign,
        } => {
            let data = read_all(input)?;

            // If from_sovereign, unwrap the SovereignBlob first
            let raw = if from_sovereign {
                let blob = SovereignBlob::deserialize(&data)
                    .context("failed to deserialize SovereignBlob")?;
                if blob.blob_type != BlobType::Logic {
                    anyhow::bail!("expected Logic blob type for QYN data, got {:?}", blob.blob_type);
                }
                // The payload is base64-encoded QYN frame
                blob.payload
            } else {
                STANDARD.decode(data.trim_ascii_end())?
            };

            let descriptor = decode_descriptor(&raw, &passphrase)?;
            let serialised = serde_json::to_vec(&descriptor)?;
            write_all(output, &serialised)?;
        }
        Commands::Encode {
            passphrase,
            input,
            output,
            emit_sovereign,
            label,
        } => {
            let data = read_all(input)?;
            let descriptor: Descriptor = serde_json::from_slice(&data)?;
            let encoded = encode_descriptor(descriptor, &passphrase)?;

            if emit_sovereign {
                // Wrap in SovereignBlob for PermFS storage
                let mut blob = SovereignBlob::new_logic(&encoded);
                if let Some(lbl) = label {
                    blob = blob.with_label(&lbl);
                }
                let serialized = blob.serialize();
                write_all(output, &serialized)?;
            } else {
                let b64 = STANDARD.encode(encoded);
                write_all(output, b64.as_bytes())?;
            }
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
