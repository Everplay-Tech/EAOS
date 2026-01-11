fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    
    // Set the entry point for UEFI
    println!("cargo:rustc-cfg=uefi");
}
