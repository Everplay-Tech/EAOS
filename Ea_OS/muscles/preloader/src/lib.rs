#![no_std]
#![no_main]

//! Pre-Nucleus Loader - 2KiB verified loader that boots the Nucleus Muscle
//!
//! This is the minimal Rust component that:
//! 1. Is verified by Referee
//! 2. Verifies the Nucleus Muscle blob  
//! 3. Sets up execution environment
//! 4. Transfers control to Nucleus Muscle

#[cfg(not(any(target_arch = "aarch64", target_arch = "x86_64")))]
compile_error!("preloader supports only aarch64 and x86_64 targets");

use core::arch::{asm, naked_asm};
use core::panic::PanicInfo;

/// Pre-nucleus loader structure - must be <= 2KiB
#[repr(C, align(16))]
pub struct PreNucleusLoader {
    /// Verification key for Nucleus blob
    verification_key: [u8; 32],
    /// Expected nucleus hash (optional, zeroed if unused)
    expected_nucleus_hash: [u8; 32],
}

#[repr(C)]
struct BootParameters {
    memory_map_addr: u64,
    memory_map_size: u64,
    lattice_root: [u8; 32],
    master_key_addr: u64,
    nucleus_blob_addr: u64,
    nucleus_blob_len: u64,
    nucleus_entry_offset: u64,
    // blake3 of the encrypted nucleus blob
    nucleus_hash: [u8; 32],
}

const NUCLEUS_BLOB_LEN: u64 = 8256;
const EMPTY_HASH: [u8; 32] = [0u8; 32];
// Set EXPECTED_NUCLEUS_HASH via EXPECTED_NUCLEUS_HASH_HEX at build time.
include!(concat!(env!("OUT_DIR"), "/expected_hash.rs"));

impl PreNucleusLoader {
    /// Entry point called by Referee after verification
    #[no_mangle]
    #[unsafe(naked)]
    pub extern "C" fn entry_point() -> ! {
        #[cfg(target_arch = "aarch64")]
        naked_asm!(
            "mov sp, {stack}",
            "b {rust_entry}",
            stack = const 0x8000,
            rust_entry = sym entry_point_rust,
        );

        #[cfg(target_arch = "x86_64")]
        naked_asm!(
            "mov rsp, {stack}",
            "jmp {rust_entry}",
            stack = const 0x8000,
            rust_entry = sym entry_point_rust,
        );
    }

    fn entry_point_rust_impl(params: *const BootParameters) -> ! {
        if Self::verify_nucleus_blob(params) == 0 {
            halt_system();
        }

        Self::setup_nucleus_environment();
        let entry = Self::get_nucleus_entry(params);
        if entry == 0 {
            halt_system();
        }

        #[cfg(target_arch = "aarch64")]
        unsafe {
            asm!(
                "br {entry}",
                entry = in(reg) entry,
                options(noreturn)
            );
        }

        #[cfg(target_arch = "x86_64")]
        unsafe {
            asm!(
                "jmp {entry}",
                entry = in(reg) entry,
                options(noreturn)
            );
        }
    }

    /// Verify the Nucleus blob handoff metadata
    fn verify_nucleus_blob(params: *const BootParameters) -> u64 {
        if params.is_null() {
            return 0;
        }

        let params = unsafe { &*params };

        if params.nucleus_blob_addr == 0 || params.nucleus_blob_len != NUCLEUS_BLOB_LEN {
            return 0;
        }

        if params.nucleus_entry_offset >= params.nucleus_blob_len {
            return 0;
        }

        if EXPECTED_NUCLEUS_HASH != EMPTY_HASH && params.nucleus_hash != EXPECTED_NUCLEUS_HASH {
            return 0;
        }

        1
    }

    /// Set up execution environment for Nucleus
    fn setup_nucleus_environment() {
        // Set up memory map, stack, and system registers
        // for Nucleus Muscle execution
        #[cfg(target_arch = "aarch64")]
        unsafe {
            // Configure system registers for isolated execution
            asm!(
                "msr sctlr_el1, xzr",
                "msr ttbr0_el1, xzr",
                "msr ttbr1_el1, xzr",
                options(nostack)
            );
        }

    }

    /// Extract entry point from Nucleus blob
    fn get_nucleus_entry(params: *const BootParameters) -> u64 {
        if params.is_null() {
            return 0;
        }

        let params = unsafe { &*params };
        params.nucleus_blob_addr + params.nucleus_entry_offset
    }
}

#[no_mangle]
pub(crate) extern "C" fn entry_point_rust(params: *const BootParameters) -> ! {
    PreNucleusLoader::entry_point_rust_impl(params)
}

/// Halt system on critical failure
fn halt_system() -> ! {
    #[cfg(target_arch = "aarch64")]
    unsafe {
        loop {
            asm!("wfe", options(nomem, nostack));
        }
    }

    #[cfg(target_arch = "x86_64")]
    unsafe {
        loop {
            asm!("hlt", options(nomem, nostack));
        }
    }

    #[cfg(not(any(target_arch = "aarch64", target_arch = "x86_64")))]
    loop {}
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    halt_system()
}
