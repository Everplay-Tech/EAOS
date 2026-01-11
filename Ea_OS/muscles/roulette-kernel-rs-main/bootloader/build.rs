// Copyright © 2025 [Mitchell_Burns/ Everplay-Tech]. All rights reserved.
// Proprietary and confidential. Not open source.
// Unauthorized copying, distribution, or modification prohibited.

//! Simplified build script - NASM dependency removed
//! Using pure Rust bootloader crate instead

fn main() {
    // No build actions needed - using bootloader crate in kernel
    println!("cargo:rerun-if-changed=build.rs");
}
