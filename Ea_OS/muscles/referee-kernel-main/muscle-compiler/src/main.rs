// muscle-compiler/src/main.rs
// Eä Muscle Compiler v5.0 — Integrated with Crypto Engine v5.0

use std::{env, fs, path::Path};
use blake3::Hasher;

mod parser;
mod crypto;
mod codegen;
mod blob;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 5 || args[2] != "--chaos-master" || args[4] != "--target" {
        eprintln!("Usage: {} <input.py> --chaos-master <hex> --target <aarch64|x86_64>", args[0]);
        std::process::exit(1);
    }

    let input_path = Path::new(&args[1]);
    let chaos_hex = &args[3];
    let target_arch = &args[5];

    // Validate target
    if target_arch != "aarch64" && target_arch != "x86_64" {
        eprintln!("Error: Unsupported target '{}'. Use 'aarch64' or 'x86_64'", target_arch);
        std::process::exit(1);
    }

    // Read and parse source
    let source = fs::read_to_string(input_path)
        .map_err(|e| format!("Failed to read {}: {}", input_path.display(), e))?;

    let weights = parser::extract_weights(&source)
        .map_err(|e| format!("Failed to parse weights: {}", e))?;

    // Parse master key
    let master_key: [u8; 32] = hex::decode(chaos_hex)
        .map_err(|e| format!("Invalid hex in chaos-master: {}", e))?
        .try_into()
        .map_err(|_| "chaos-master must be exactly 32 bytes (64 hex chars)")?;

    // Generate salt from input path
    let salt: crypto::MuscleSalt = {
        let hash = Hasher::new()
            .update(input_path.to_string_lossy().as_bytes())
            .finalize();
        let mut salt = [0u8; 16];
        salt.copy_from_slice(&hash.as_bytes()[..16]);
        salt
    };

    // Generate machine code
    let raw_blob = match target_arch {
        "aarch64" => codegen::aarch64::emit(&weights),
        "x86_64" => codegen::x86_64::emit(&weights),
        _ => unreachable!(),
    };

    // Encrypt with crypto engine v5.0
    let sealed = crypto::seal(&master_key, &salt, 1, &raw_blob);

    // Create final .muscle blob
    let muscle_name = input_path.file_stem()
        .unwrap()
        .to_string_lossy();
    let final_blob = blob::forge(&muscle_name, target_arch, &sealed);

    // Write output
    let out_name = format!("{}.muscle", muscle_name);
    fs::write(&out_name, &final_blob)
        .map_err(|e| format!("Failed to write {}: {}", out_name, e))?;

    println!("✓ Eä forged {} → {} ({} bytes, target: {})", 
             input_path.display(), out_name, final_blob.len(), target_arch);

    Ok(())
}
