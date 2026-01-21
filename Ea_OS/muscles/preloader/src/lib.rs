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
use muscle_contract::BootParameters;

/// Pre-nucleus loader structure - must be <= 2KiB
#[repr(C, align(16))]
pub struct PreNucleusLoader {
    /// Verification key for Nucleus blob
    verification_key: [u8; 32],
    /// Expected nucleus hash (optional, zeroed if unused)
    expected_nucleus_hash: [u8; 32],
}

const NUCLEUS_BLOB_LEN: u64 = 8256;
const EMPTY_HASH: [u8; 32] = [0u8; 32];
const BOOT_MAGIC: u32 = 0xEA05_B007;

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

        if params.magic != BOOT_MAGIC {
            return 0;
        }

        if params.nucleus_addr == 0 || params.nucleus_size < 4096 {
            return 0;
        }

        // Optional: Check hash passed from Referee (if trusted)
        // or check against EXPECTED_NUCLEUS_HASH
        if EXPECTED_NUCLEUS_HASH != EMPTY_HASH && params.nucleus_hash != EXPECTED_NUCLEUS_HASH {
             // In Phase 3, we allow mismatch if Referee calculated it wrong, but ideally return 0
             // For now, strict check:
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
        // Base address + offset
        params.nucleus_addr + params.entry_point
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
