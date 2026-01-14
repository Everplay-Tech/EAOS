#![no_std]
#![no_main]

use uefi::prelude::*;

mod capability;
mod cell;
mod memory;
mod uart;
mod scheduler;
mod errors;
mod audit;
mod syscall;
mod bridge;

use crate::uart::Uart;
use crate::capability::ChaosCapability;
use crate::cell::Cell;
use crate::scheduler::run_scheduler;

const N_CELLS: usize = 50;

#[entry]
fn efi_main(_image: Handle, mut st: SystemTable<Boot>) -> Status {
    // Initialize UEFI services (uefi 0.24 API)
    if uefi_services::init(&mut st).is_err() {
        return Status::LOAD_ERROR;
    }

    let bt = st.boot_services();
    let mut uart = Uart::new();
    if uart.init().is_err() {
        return Status::LOAD_ERROR;
    }

    uart.log("INFO", "Ea referee v3.0 awakens - production ready");

    // Load master key and initialize cells
    let master_key = match crate::memory::load_master_key(bt) {
        Ok(key) => key,
        Err(_) => {
            uart.log("FATAL", "Failed to load master key");
            return Status::LOAD_ERROR;
        }
    };

    uart.log("INFO", "Chaos master key acquired");

    // Initialize cells array (Cell is Copy, so this works)
    let mut cells: [Option<Cell>; N_CELLS] = [None; N_CELLS];
    let mut valid_count: usize = 0;

    for i in 0..N_CELLS {
        let child_key = ChaosCapability::derive_child_key(&master_key, i as u64);
        let blob_addr = 0x9100_0000 + i as u64 * 8192;

        match Cell::load_and_validate(bt, blob_addr, &child_key) {
            Ok(cell) => {
                cells[i] = Some(cell);
                valid_count += 1;
                audit!("Muscle validated and loaded");
            }
            Err(_e) => {
                // Log static error message (no format! in no_std)
                uart.log("WARN", "Muscle validation failed");
                if !audit::recoverable() {
                    uart.log("FATAL", "Unrecoverable error");
                    return Status::LOAD_ERROR;
                }
            }
        }
    }

    // Log completion with static message
    if valid_count > 0 {
        uart.log("INFO", "Muscles loaded - Ea breathes");
    } else {
        uart.log("WARN", "No muscles loaded");
    }

    // ========================================================================
    // Initialize PermFS Bridge (Final Birthing)
    // ========================================================================
    // Connect the referee-kernel to PermFS storage layer with T9-Braid
    // compression. This enables:
    //   - Healthcare record storage with 0xB8AD braid headers
    //   - Dr-Lex governance auditing on writes
    //   - Gödel number generation for data integrity
    uart.log("INFO", "Initializing PermFS bridge...");

    let node_id: u64 = 0;  // Single-node deployment
    let volume_id: u32 = 1; // Primary health pod volume

    let bridge_ok = bridge::init_bridge(node_id, volume_id);

    if bridge_ok {
        uart.log("INFO", "PermFS bridge connected - Braid ready");
    } else {
        // Bridge initialization is optional - we can still run without storage
        uart.log("WARN", "PermFS bridge not available - running in memory-only mode");
    }

    // Transfer control to scheduler
    run_scheduler(bt, &cells, &mut uart)
}
