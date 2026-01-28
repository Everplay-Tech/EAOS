use anyhow::{Context, Result};
use base64::{Engine as _, engine::general_purpose};
use clap::Parser;
use ed25519_dalek::{Signature, VerifyingKey};
use std::fs;
use std::path::PathBuf;

/// Standalone Ed25519 signature verification tool
/// 
/// This tool verifies Ed25519 signatures independently of the main enzyme-installer
/// application, useful for manual verification and testing against RFC 8032 test vectors.
#[derive(Parser, Debug)]
#[command(name = "verify_signature")]
#[command(about = "Verify Ed25519 signatures independently", long_about = None)]
struct Args {
    /// Base64-encoded Ed25519 public key (32 bytes)
    #[arg(long, value_name = "BASE64")]
    pub public_key: String,

    /// Message to verify (as string)
    #[arg(long, value_name = "STRING", group = "message_input")]
    pub message: Option<String>,

    /// Path to file containing message to verify
    #[arg(long, value_name = "PATH", group = "message_input")]
    pub message_file: Option<PathBuf>,

    /// Base64-encoded Ed25519 signature (64 bytes)
    #[arg(long, value_name = "BASE64")]
    pub signature: String,

    /// Interpret inputs as hex instead of base64
    #[arg(long)]
    pub hex: bool,
}

fn decode_base64(input: &str, description: &str) -> Result<Vec<u8>> {
    general_purpose::STANDARD
        .decode(input.trim())
        .with_context(|| format!("failed to decode base64 {}: {}", description, input))
}

fn decode_hex(input: &str, description: &str) -> Result<Vec<u8>> {
    hex::decode(input.trim())
        .with_context(|| format!("failed to decode hex {}: {}", description, input))
}

fn main() -> Result<()> {
    let args = Args::parse();

    // Decode public key
    let public_key_bytes = if args.hex {
        decode_hex(&args.public_key, "public key")?
    } else {
        decode_base64(&args.public_key, "public key")?
    };

    if public_key_bytes.len() != 32 {
        anyhow::bail!(
            "invalid public key length: expected 32 bytes, got {} bytes",
            public_key_bytes.len()
        );
    }

    // Decode signature
    let signature_bytes = if args.hex {
        decode_hex(&args.signature, "signature")?
    } else {
        decode_base64(&args.signature, "signature")?
    };

    if signature_bytes.len() != 64 {
        anyhow::bail!(
            "invalid signature length: expected 64 bytes, got {} bytes",
            signature_bytes.len()
        );
    }

    // Get message
    let message = if let Some(msg) = args.message {
        msg.into_bytes()
    } else if let Some(path) = args.message_file {
        fs::read_to_string(&path)
            .with_context(|| format!("failed to read message file: {}", path.display()))?
            .into_bytes()
    } else {
        anyhow::bail!("must provide either --message or --message-file");
    };

    // Create VerifyingKey
    let verifying_key = VerifyingKey::from_bytes(
        &public_key_bytes.try_into().unwrap()
    ).context("failed to create VerifyingKey from bytes")?;

    // Create Signature
    let signature: Signature = signature_bytes.as_slice()
        .try_into()
        .context("failed to create Signature from bytes")?;

    // Verify signature
    match verifying_key.verify_strict(&message, &signature) {
        Ok(_) => {
            println!("✓ Signature verification SUCCESSFUL");
            Ok(())
        }
        Err(e) => {
            eprintln!("✗ Signature verification FAILED: {}", e);
            std::process::exit(1);
        }
    }
}
