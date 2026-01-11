use std::env;
use std::fmt::Write as _;
use std::fs;
use std::path::Path;

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=src/");

    // Check that we're building for UEFI
    let target = env::var("TARGET").unwrap();
    if !target.contains("uefi") {
        panic!("Pre-nucleus loader must be built for UEFI target");
    }

    // Generate size verification
    generate_size_checks();
    generate_expected_hash();
}

fn generate_size_checks() {
    let out_dir = env::var_os("OUT_DIR").unwrap();
    let dest_path = std::path::Path::new(&out_dir).join("size_check.rs");

    let check_code = r#"
        // Compile-time size assertion for pre-nucleus loader
        const _: () = assert!(core::mem::size_of::<PreNucleusLoader>() <= 2048, 
                             "Pre-nucleus loader exceeds 2KiB size limit");
    "#;

    fs::write(&dest_path, check_code).unwrap();
    println!("cargo:rustc-cfg=size_checked");
}

fn generate_expected_hash() {
    let out_dir = env::var_os("OUT_DIR").unwrap();
    let dest_path = Path::new(&out_dir).join("expected_hash.rs");

    let mut hash_bytes = [0u8; 32];
    if let Ok(hex) = env::var("EXPECTED_NUCLEUS_HASH_HEX") {
        if hex.len() != 64 {
            panic!("EXPECTED_NUCLEUS_HASH_HEX must be 64 hex chars");
        }
        for i in 0..32 {
            let start = i * 2;
            let byte = u8::from_str_radix(&hex[start..start + 2], 16)
                .expect("EXPECTED_NUCLEUS_HASH_HEX must be valid hex");
            hash_bytes[i] = byte;
        }
    }

    let mut out = String::new();
    out.push_str("const EXPECTED_NUCLEUS_HASH: [u8; 32] = [");
    for (idx, byte) in hash_bytes.iter().enumerate() {
        if idx > 0 {
            out.push_str(", ");
        }
        write!(&mut out, "0x{:02x}", byte).unwrap();
    }
    out.push_str("];\n");

    fs::write(dest_path, out).unwrap();
}
