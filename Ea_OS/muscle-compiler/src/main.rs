use clap::{value_parser, Arg, ArgAction, ArgMatches, Command};
use std::fs;
use std::path::PathBuf;
use std::process;

mod ast;
mod codegen;
mod crypto;
mod error;
mod parser;

// UPDATED: Enhanced modules for full Wizard Stack specification
mod languages;

use ast::full_ast::{Declaration, Program};
use codegen::emit as emit_code;
use crypto::encrypt_muscle_blob;
use error::CompileError;
use languages::capability_checker::{verify_sacred_rules, CapabilityChecker};
use languages::formal_grammar::FormalParser;
use languages::LanguageFrontend;
use muscle_contract::{
    capabilities, ARCH_AARCH64, ARCH_WASM32, ARCH_X86_64, MANIFEST_LEN, PAYLOAD_LEN,
};
use parser::PythonParser;

fn main() {
    let matches = build_cli().get_matches();

    if let Err(e) = run(&matches) {
        eprintln!("❌ Error: {}", e);
        process::exit(1);
    }
}

fn build_cli() -> Command {
    Command::new("Muscle Compiler v6.0 - Wizard Stack")
        .version("5.0.0")
        .author("Eä Foundation")
        .about("Compiles Python NN definitions or Muscle.ea sources to encrypted muscle blobs")
        .arg(
            Arg::new("input")
                .short('i')
                .long("input")
                .value_name("FILE")
                .help("Input Python file (.py) or Nucleus source (.ea)")
                .required(true)
                .value_parser(value_parser!(String)),
        )
        .arg(
            Arg::new("output")
                .short('o')
                .long("output")
                .value_name("FILE")
                .help("Output encrypted blob file")
                .required(true)
                .value_parser(value_parser!(String)),
        )
        .arg(
            Arg::new("target")
                .short('t')
                .long("target")
                .value_name("ARCH")
                .help("Target architecture (aarch64, x86_64, nucleus)")
                .default_value("aarch64")
                .value_parser(value_parser!(String)),
        )
        .arg(
            Arg::new("chaos-master")
                .long("chaos-master")
                .value_name("KEY")
                .help("32-byte hex chaos master key for encryption")
                .required(true)
                .value_parser(value_parser!(String)),
        )
        .arg(
            Arg::new("verbose")
                .short('v')
                .long("verbose")
                .help("Enable verbose output")
                .action(ArgAction::Count),
        )
        .arg(
            Arg::new("verify-only")
                .long("verify-only")
                .help("Only verify the source code, don't compile")
                .action(ArgAction::SetTrue),
        )
        .arg(
            Arg::new("dump-ast")
                .long("dump-ast")
                .help("Dump the parsed AST for debugging")
                .action(ArgAction::SetTrue),
        )
}

fn run(matches: &ArgMatches) -> Result<(), CompileError> {
    let input_file = matches.get_one::<String>("input").unwrap();
    let output_file = matches.get_one::<String>("output").unwrap();
    let target_arch = matches.get_one::<String>("target").unwrap();
    let chaos_master_hex = matches.get_one::<String>("chaos-master").unwrap();
    let verbose = matches.get_count("verbose") > 0;
    let verify_only = matches.get_flag("verify-only");
    let dump_ast = matches.get_flag("dump-ast");

    if verbose {
        println!("🔧 Muscle Compiler v6.0 - Wizard Stack Specification");
        println!("   Input: {}", input_file);
        println!("   Output: {}", output_file);
        println!("   Target: {}", target_arch);
        println!(
            "   Mode: {}",
            if verify_only {
                "verify-only"
            } else {
                "compile"
            }
        );
    }

    // Parse chaos master key
    let chaos_master = parse_chaos_key(chaos_master_hex)?;

    // Read input file
    let input_path = PathBuf::from(input_file);
    if !input_path.exists() {
        return Err(CompileError::IoError(format!(
            "Input file not found: {}",
            input_file
        )));
    }

    // UPDATED: Enhanced file type detection with full spec support
    if input_path
        .extension()
        .map(|ext| ext == "ea")
        .unwrap_or(false)
    {
        // Compile .ea source file with full Wizard Stack specification
        compile_ea_source_full_spec(
            input_file,
            output_file,
            target_arch,
            &chaos_master,
            verbose,
            verify_only,
            dump_ast,
        )
    } else if input_path
        .extension()
        .map(|ext| ext == "py")
        .unwrap_or(false)
    {
        // Compile Python source file (traditional neural network muscle)
        compile_python_source(input_file, output_file, target_arch, &chaos_master, verbose)
    } else {
        Err(CompileError::IoError(
            "Input file must be .py or .ea extension".to_string(),
        ))
    }
}

/// UPDATED: Compile .ea source file with full Wizard Stack specification
fn compile_ea_source_full_spec(
    input_file: &str,
    output_file: &str,
    target_arch: &str,
    chaos_master: &[u8; 32],
    verbose: bool,
    verify_only: bool,
    dump_ast: bool,
) -> Result<(), CompileError> {
    if verbose {
        println!("🎯 Compiling .ea source with Wizard Stack Specification");
        println!("   Language: Muscle.ea v1.0 - The Language of Life");
    }

    // Validate target architecture for Nucleus
    if target_arch != "nucleus" && target_arch != "aarch64" {
        return Err(CompileError::CompileError(format!(
            "Nucleus muscles require aarch64 or nucleus target, got: {}",
            target_arch
        )));
    }

    // Read and parse .ea source with full EBNF grammar
    let source = fs::read_to_string(input_file)?;

    if verbose {
        println!("   📖 Parsing source code ({} bytes)", source.len());
    }

    let program = FormalParser::parse_program(&source)?;

    if dump_ast {
        println!("{:#?}", program);
    }

    if verbose {
        println!("   ✅ Parsed successfully:");
        println!("      - {} declarations", program.declarations.len());
        println!("      - {} rules", program.rules.len());

        // Count declaration types
        let mut input_count = 0;
        let mut capability_count = 0;
        let mut const_count = 0;

        for decl in &program.declarations {
            match decl {
                Declaration::Input(_) => input_count += 1,
                Declaration::Capability(_) => capability_count += 1,
                Declaration::Const(_) => const_count += 1,
                Declaration::Metadata(_) => {}
            }
        }

        println!(
            "      - {} inputs, {} capabilities, {} constants",
            input_count, capability_count, const_count
        );
    }

    // UPDATED: Enhanced security verification
    if verbose {
        println!("   🔒 Verifying capability security...");
    }

    let mut capability_checker = CapabilityChecker::new();
    capability_checker.verify_program(&program)?;

    if verbose {
        println!("   ✅ Capability security verified");
    }

    // UPDATED: Verify the Three Sacred Rules
    if verbose {
        println!("   📜 Verifying Sacred Rules of Muscle.ea...");
    }

    verify_sacred_rules(&program)?;

    if verbose {
        println!("   ✅ Sacred Rules verified:");
        println!("      - Append-only semantics");
        println!("      - Event-driven architecture");
        println!("      - Capability-security enforced");
        println!("      - No polling constructs");
    }

    if verify_only {
        println!("🎉 Verification completed successfully - program is valid Muscle.ea");
        return Ok(());
    }

    // UPDATED: Generate machine code with enhanced codegen
    if verbose {
        println!("   🔨 Generating machine code with capability enforcement...");
    }

    let generator = LanguageFrontend::get_code_generator("ea")?;
    let machine_code = generator.generate(&program)?;

    if verbose {
        println!("   ✅ Generated machine code: {} bytes", machine_code.len());

        // Verify code size against contract payload budget
        if machine_code.len() != PAYLOAD_LEN - MANIFEST_LEN {
            return Err(CompileError::CodegenError(format!(
                "Nucleus code must be exactly {} bytes, got: {}",
                PAYLOAD_LEN - MANIFEST_LEN,
                machine_code.len()
            )));
        }
        println!(
            "   📏 Nucleus size verified: {} bytes",
            PAYLOAD_LEN - MANIFEST_LEN
        );
    }

    // Encrypt and seal the blob using contract-aligned crypto
    if verbose {
        println!("   🔐 Encrypting and sealing blob...");
    }

    let arch_code = arch_code(target_arch)?;
    let cap_bitmap = capability_bitmap_for_program(&program);
    let sealed_blob = encrypt_muscle_blob(&machine_code, chaos_master, arch_code, cap_bitmap)?;

    // Write output file
    fs::write(output_file, &sealed_blob)?;

    if verbose {
        println!("   💾 Sealed blob written: {} bytes", sealed_blob.len());

        // Show security summary
        println!("   🛡️  Security Summary:");
        println!("      - Capability security: ENFORCED");
        println!("      - Sacred Rules: VERIFIED");
        println!("      - Cryptographic sealing: COMPLETE");
        println!("      - Biological integrity: MAINTAINED");

        println!("   📦 Nucleus muscle compilation complete!");
        println!("   🧬 Every valid program is a living cell ✓");
    }

    Ok(())
}

/// EXISTING: Compile Python source file to neural network muscle blob
fn compile_python_source(
    input_file: &str,
    output_file: &str,
    target_arch: &str,
    chaos_master: &[u8; 32],
    verbose: bool,
) -> Result<(), CompileError> {
    if verbose {
        println!("🐍 Compiling Python source as neural network muscle");
    }

    // Read and parse Python source
    let source = fs::read_to_string(input_file)?;
    let python_ast = PythonParser::parse(&source)?;

    if verbose {
        println!(
            "   Parsed neural network with {} weights",
            python_ast.weights.len()
        );

        // Show architecture info if available
        if let Some(layers) = python_ast.metadata().get("layers") {
            println!("   Network architecture: {}", layers);
        }
    }

    // Generate machine code based on target architecture
    let machine_code = emit_code(&python_ast.weights, target_arch)?;

    if verbose {
        println!("   Generated machine code: {} bytes", machine_code.len());
    }

    // Encrypt and seal the blob
    let arch_code = arch_code(target_arch)?;
    let sealed_blob = encrypt_muscle_blob(&machine_code, chaos_master, arch_code, 0)?;

    // Write output file
    fs::write(output_file, &sealed_blob)?;

    if verbose {
        println!("   ✅ Sealed blob written: {} bytes", sealed_blob.len());
        println!("   📦 Neural network muscle compilation complete!");
    }

    Ok(())
}

/// Parse 32-byte hex chaos master key
fn parse_chaos_key(hex_str: &str) -> Result<[u8; 32], CompileError> {
    if hex_str.len() != 64 {
        return Err(CompileError::CryptoError(
            "Chaos master key must be 64 hex characters (32 bytes)".to_string(),
        ));
    }

    let mut key = [0u8; 32];
    hex::decode_to_slice(hex_str, &mut key)
        .map_err(|e| CompileError::CryptoError(format!("Invalid hex key: {}", e)))?;

    Ok(key)
}

fn arch_code(target_arch: &str) -> Result<u8, CompileError> {
    match target_arch {
        "aarch64" | "nucleus" => Ok(ARCH_AARCH64),
        "x86_64" => Ok(ARCH_X86_64),
        "wasm32" => Ok(ARCH_WASM32),
        _ => Err(CompileError::CompileError(format!(
            "Unsupported target architecture: {}",
            target_arch
        ))),
    }
}

fn capability_bitmap_for_program(program: &Program) -> u32 {
    let mut bitmap = 0u32;
    for decl in &program.declarations {
        if let Declaration::Capability(cap) = decl {
            bitmap |= capability_bit_for_name(&cap.name);
        }
    }
    bitmap
}

fn capability_bit_for_name(name: &str) -> u32 {
    match name {
        "emit_update" => capabilities::LATTICE_WRITE,
        "load_muscle" => capabilities::SPAWN_SUCCESSOR | capabilities::LATTICE_READ,
        _ => 0,
    }
}

// UPDATED: Enhanced integration tests for full specification
#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::NamedTempFile;

    #[test]
    fn test_full_spec_nucleus_compilation() {
        let source = r#"
input lattice_stream<MuscleUpdate>
input hardware_attestation<DeviceProof>
input symbiote<SealedBlob>

capability load_muscle(id: muscle_id) -> ExecutableMuscle
capability schedule(muscle: ExecutableMuscle, priority: u8) 
capability emit_update(blob: SealedBlob)

const SYMBIOTE_ID: muscle_id = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF

rule on_boot:
    verify hardware_attestation.verify()
    verify lattice_root == 0xEA0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f
    let symbiote_instance = load_muscle(SYMBIOTE_ID)
    schedule(symbiote_instance, priority: 255)

rule on_lattice_update(update: MuscleUpdate):
    if symbiote.process_update(update) -> healing:
        emit_update(healing.blob)

rule on_timer_1hz:
    emit heartbeat(self.id, self.version)

rule on_self_integrity_failure:
    emit corruption_report(self.id, self.version)
"#;

        let temp_file = NamedTempFile::new().unwrap();
        fs::write(temp_file.path(), source).unwrap();

        let output_file = NamedTempFile::new().unwrap();
        let chaos_key = [0u8; 32];

        let result = compile_ea_source_full_spec(
            temp_file.path().to_str().unwrap(),
            output_file.path().to_str().unwrap(),
            "aarch64",
            &chaos_key,
            false,
            false,
            false,
        );

        if let Err(err) = result {
            panic!("compile failed: {}", err);
        }

        let output_data = fs::read(output_file.path()).unwrap();
        assert_eq!(output_data.len(), 8256); // Standard sealed blob size
    }

    #[test]
    fn test_minimal_living_cell() {
        let source = r#"
input lattice_stream<MuscleUpdate>
input hardware_attestation<DeviceProof>
capability emit_update(blob: SealedBlob)

rule on_boot:
    emit heartbeat("I am alive")

rule on_timer_1hz:
    emit heartbeat("Still breathing")
"#;

        let program = FormalParser::parse_program(source).unwrap();
        let mut checker = CapabilityChecker::new();
        assert!(checker.verify_program(&program).is_ok());
        assert!(verify_sacred_rules(&program).is_ok());
    }

    #[test]
    fn test_capability_enforcement_failure() {
        let source = r#"
input lattice_stream<MuscleUpdate>
# Missing capability declaration for emit_update
input hardware_attestation<DeviceProof>

rule on_boot:
    emit heartbeat("This should fail")  # Uses undeclared capability
"#;

        let program = FormalParser::parse_program(source).unwrap();
        let mut checker = CapabilityChecker::new();
        assert!(checker.verify_program(&program).is_err());
    }

    #[test]
    fn test_chaos_key_parsing() {
        let valid_key = "a".repeat(64);
        let result = parse_chaos_key(&valid_key);
        assert!(result.is_ok());

        let invalid_key = "a".repeat(63);
        let result = parse_chaos_key(&invalid_key);
        assert!(result.is_err());
    }

    #[test]
    fn test_verification_only_mode() {
        let source = r#"
input lattice_stream<MuscleUpdate>
input hardware_attestation<DeviceProof>
capability emit_update(blob: SealedBlob)

rule on_boot:
    emit heartbeat("Verification test")
"#;

        let temp_file = NamedTempFile::new().unwrap();
        fs::write(temp_file.path(), source).unwrap();

        let output_dir = tempfile::tempdir().unwrap();
        let output_path = output_dir.path().join("verify_only.blob");
        let chaos_key = [0u8; 32];

        let result = compile_ea_source_full_spec(
            temp_file.path().to_str().unwrap(),
            output_path.to_str().unwrap(),
            "aarch64",
            &chaos_key,
            false,
            true, // verify-only
            false,
        );

        assert!(result.is_ok());

        // Output file should not exist in verify-only mode
        assert!(!output_path.exists());
    }
}
