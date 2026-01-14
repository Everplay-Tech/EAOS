//! Build script for referee-kernel
//!
//! PermFS Bridge is now linked via Cargo dependency (permfs-bridge crate).

fn main() {
    println!("cargo:rerun-if-changed=build.rs");

    // Set the entry point for UEFI
    println!("cargo:rustc-cfg=uefi");

    // PermFS Bridge is linked via Cargo dependency, no manual linking needed.
    // See Cargo.toml: permfs-bridge = { ..., features = ["uefi"] }
}
