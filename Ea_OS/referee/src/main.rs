// referee/src/main.rs
// Eä Referee v6.0 — Secure UEFI Bootloader with EaM6 integration
#![no_std]
#![no_main]
#![feature(abi_efiapi)]

extern crate alloc;

use uefi::prelude::*;
use uefi::table::boot::BootServices;
use alloc::format;

mod muscle_loader;
mod uart;

use crate::muscle_loader::{load_muscle, LoadedMuscle};
use muscle_contract::BLOB_LEN;
use crate::uart::Uart;

const N_MUSCLES: usize = 50;
// Assumes the nucleus blob is stored in this slot of the muscle bundle.
const NUCLEUS_SLOT: usize = 0;
const MUSCLE_BUNDLE_BASE: u64 = 0x9100_0000;
const MUSCLE_SIZE: usize = BLOB_LEN;
const MASTER_KEY_ADDR: u64 = 0x9000_0000;

#[repr(C)]
#[derive(Clone, Copy)]
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

impl BootParameters {
    const fn empty() -> Self {
        Self {
            memory_map_addr: 0,
            memory_map_size: 0,
            lattice_root: [0u8; 32],
            master_key_addr: 0,
            nucleus_blob_addr: 0,
            nucleus_blob_len: 0,
            nucleus_entry_offset: 0,
            nucleus_hash: [0u8; 32],
        }
    }
}

/// Global system state
struct RefereeState {
    muscles: [Option<LoadedMuscle>; N_MUSCLES],
    loaded_count: usize,
}

impl RefereeState {
    const fn new() -> Self {
        Self {
            muscles: [const { None }; N_MUSCLES],
            loaded_count: 0,
        }
    }
}

static mut STATE: RefereeState = RefereeState::new();
static mut BOOT_PARAMS: BootParameters = BootParameters::empty();

#[entry]
fn efi_main(_image: Handle, mut system_table: SystemTable<Boot>) -> Status {
    // Initialize UEFI services
    uefi_services::init(&mut system_table).unwrap();

    let boot_services = system_table.boot_services();
    let mut uart = Uart::new();

    // Initialize UART for logging
    if let Err(e) = uart.init() {
        log(&mut uart, "ERROR", &format!("UART init failed: {:?}", e));
        return Status::LOAD_ERROR;
    }

    log(&mut uart, "INFO", "Eä Referee v6.0 awakening...");

    // Load master chaos key
    let master_key = match load_master_key(boot_services) {
        Ok(key) => {
            log(&mut uart, "INFO", "Chaos master key acquired");
            key
        }
        Err(e) => {
            log(&mut uart, "FATAL", &format!("Master key load failed: {}", e));
            return Status::LOAD_ERROR;
        }
    };

    // Load and validate all muscles
    if let Err(e) = load_all_muscles(boot_services, &master_key, &mut uart) {
        log(&mut uart, "FATAL", &format!("Muscle loading failed: {}", e));
        return Status::LOAD_ERROR;
    }

    log(
        &mut uart,
        "INFO",
        &format!("{} muscles alive — Eä breathes", unsafe {
            STATE.loaded_count
        }),
    );

    let nucleus = match unsafe { &STATE.muscles[NUCLEUS_SLOT] } {
        Some(muscle) => muscle,
        None => {
            log(&mut uart, "FATAL", "Nucleus slot empty; cannot build boot params");
            return Status::LOAD_ERROR;
        }
    };

    let boot_params = BootParameters {
        memory_map_addr: 0,
        memory_map_size: 0,
        lattice_root: [0u8; 32],
        master_key_addr: MASTER_KEY_ADDR,
        nucleus_blob_addr: nucleus.code_base,
        nucleus_blob_len: BLOB_LEN as u64,
        nucleus_entry_offset: nucleus.entry_offset,
        nucleus_hash: nucleus.blob_hash,
    };

    let boot_params_ptr = unsafe {
        BOOT_PARAMS = boot_params;
        &BOOT_PARAMS as *const BootParameters
    };

    // Transfer control to scheduler
    run_scheduler(&mut uart, boot_services, boot_params_ptr)
}

/// Load master key from fixed memory location
fn load_master_key(_boot_services: &BootServices) -> Result<[u8; 32], &'static str> {
    let key_ptr = MASTER_KEY_ADDR as *const u8;

    // Verify key header
    const MASTER_KEY_MAGIC: &[u8; 8] = b"EaKEYv6\0";
    let header = unsafe { core::slice::from_raw_parts(key_ptr, MASTER_KEY_MAGIC.len()) };
    if header != MASTER_KEY_MAGIC {
        return Err("invalid key header");
    }

    // Extract key
    let mut key = [0u8; 32];
    unsafe {
        core::ptr::copy_nonoverlapping(key_ptr.add(8), key.as_mut_ptr(), 32);
    }

    Ok(key)
}

/// Load all muscles from bundle
fn load_all_muscles(
    boot_services: &BootServices,
    master_key: &[u8; 32],
    uart: &mut Uart,
) -> Result<(), &'static str> {
    for i in 0..N_MUSCLES {
        let muscle_addr = MUSCLE_BUNDLE_BASE + (i * MUSCLE_SIZE) as u64;

        // Read muscle blob from memory
        let blob_data =
            unsafe { core::slice::from_raw_parts(muscle_addr as *const u8, MUSCLE_SIZE) };

        // Skip empty slots
        if blob_data.iter().all(|&b| b == 0) {
            continue;
        }

        // Load and validate muscle
        match load_muscle(boot_services, master_key, blob_data, i) {
            Ok(loaded_muscle) => {
                log(
                    uart,
                    "INFO",
                    &format!("Muscle '{}' loaded successfully", loaded_muscle.name),
                );
                unsafe {
                    STATE.muscles[i] = Some(loaded_muscle);
                    STATE.loaded_count += 1;
                }
            }
            Err(e) => {
                log(
                    uart,
                    "WARN",
                    &format!("Muscle {} failed to load: {:?}", i, e),
                );
                // Continue with other muscles (graceful degradation)
            }
        }
    }

    if unsafe { STATE.loaded_count } == 0 {
        return Err("no muscles loaded successfully");
    }

    Ok(())
}

/// Simple round-robin scheduler
fn run_scheduler(
    uart: &mut Uart,
    boot_services: &BootServices,
    boot_params: *const BootParameters,
) -> ! {
    log(uart, "INFO", "Starting muscle scheduler...");

    let mut current_muscle = 0;
    let mut execution_count = 0;

    loop {
        // Find next available muscle
        let muscle_idx = current_muscle % N_MUSCLES;

        if let Some(muscle) = unsafe { &STATE.muscles[muscle_idx] } {
            execution_count += 1;

            // Log every 1000 executions
            if execution_count % 1000 == 0 {
                log(uart, "DEBUG", &format!("Executions: {}", execution_count));
            }

            // Execute muscle
            unsafe {
                execute_muscle(muscle.entry_point, boot_params);
            }
        }

        current_muscle += 1;

        // Small delay to prevent busyloop
        boot_services.stall(1000);
    }
}

/// Execute muscle at given entry point
unsafe fn execute_muscle(entry_point: u64, boot_params: *const BootParameters) {
    // For AArch64
    #[cfg(target_arch = "aarch64")]
    core::arch::asm!(
        "mov x0, {boot_params}",
        "blr {entry_point}",
        boot_params = in(reg) boot_params,
        entry_point = in(reg) entry_point,
        options(noreturn)
    );

    // For x86_64
    #[cfg(target_arch = "x86_64")]
    {
        core::arch::asm!(
            "mov rdi, {boot_params}",
            "call {entry_point}",
            boot_params = in(reg) boot_params,
            entry_point = in(reg) entry_point,
            options(noreturn)
        );
    }
}

/// Log message via UART
fn log(uart: &mut Uart, level: &str, message: &str) {
    let _ = uart.write_str(&format!("[{}] {}\n", level, message));
}
