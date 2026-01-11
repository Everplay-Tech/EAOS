#![no_std]
#![no_main]
#![feature(abi_efiapi)]

use uefi::prelude::*;
use uefi::table::boot::BootServices;

mod capability;
mod cell;
mod memory;
mod uart;
mod scheduler;
mod errors;
mod audit;

use crate::uart::Uart;
use crate::capability::ChaosCapability;
use crate::scheduler::run_scheduler;

const N_CELLS: usize = 50;

#[entry]
fn efi_main(_image: Handle, st: SystemTable<Boot>) -> Status {
    uefi_services::init(&st).unwrap_success();
    
    let bt = st.boot_services();
    let mut uart = Uart::new();
    uart.init().unwrap();
    
    uart.log("INFO", "Eä referee v3.0 awakens — production ready");
    
    // Load master key and initialize cells
    let master_key = match crate::memory::load_master_key(bt) {
        Ok(key) => key,
        Err(_) => {
            uart.log("FATAL", "Failed to load master key");
            return Status::LOAD_ERROR;
        }
    };
    
    uart.log("INFO", "Chaos master key acquired");
    
    let mut cells = [None; N_CELLS];
    let mut valid_count = 0;
    
    for i in 0..N_CELLS {
        let child_key = ChaosCapability::derive_child_key(&master_key, i as u64);
        let blob_addr = 0x9100_0000 + i as u64 * 8192;
        
        match crate::cell::Cell::load_and_validate(bt, blob_addr, &child_key) {
            Ok(cell) => {
                cells[i] = Some(cell);
                valid_count += 1;
                audit::audit!("Muscle {} validated and loaded", i);
            }
            Err(e) => {
                uart.log("WARN", &format!("Muscle {} failed: {:?}", i, e));
                if !audit::recoverable() {
                    uart.log("FATAL", "Unrecoverable error");
                    return Status::LOAD_ERROR;
                }
            }
        }
    }
    
    uart.log("INFO", &format!("{} muscles alive — Eä breathes", valid_count));
    
    // Transfer control to scheduler
    run_scheduler(bt, &cells, &mut uart)
}
