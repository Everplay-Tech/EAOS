// Copyright © 2025 [Mitchell_Burns/ Everplay-Tech]. All rights reserved.
// Proprietary and confidential. Not open source.
// Unauthorized copying, distribution, or modification prohibited.

#![no_std]
#![no_main]
#![feature(abi_x86_interrupt)]

mod vga_buffer;
mod serial;

use core::panic::PanicInfo;
use roulette_core::advanced_braid::BraidCPUState;

/// Kernel entry point
#[no_mangle]
pub extern "C" fn _start() -> ! {
    // Initialize VGA and serial output
    vga_buffer::init();
    serial_println!("Roulette Kernel booting...");

    // Display boot banner
    println!("╔════════════════════════════════════════════════════════════════════════════╗");
    println!("║                    ROULETTE KERNEL - Braid CPU OS                          ║");
    println!("║                    Verified Braid-Theoretic Computing                      ║");
    println!("╚════════════════════════════════════════════════════════════════════════════╝");
    println!();

    serial_println!("[BOOT] VGA text mode initialized");
    serial_println!("[BOOT] Serial port COM1 initialized");

    // Initialize braid CPU with 4 strands (verified minimum)
    println!("Initializing Braid CPU (4 strands)...");
    let mut cpu_state = BraidCPUState::<4>::new();
    serial_println!("[BOOT] Braid CPU initialized with 4 strands");

    // Demonstrate verified braid operations
    println!("Testing braid operations...");
    cpu_state.write_register(0, 42, roulette_core::braid::BraidGenerator::Left(1));
    let value = cpu_state.read_register(0);

    println!("  Register 0 test: {} (expected: 42)", value);
    serial_println!("[TEST] Braid CPU register test: value={}", value);

    if value == 42 {
        println!("  ✓ CPU test PASSED");
        serial_println!("[TEST] CPU test PASSED");
    } else {
        println!("  ✗ CPU test FAILED");
        serial_println!("[TEST] CPU test FAILED - expected 42, got {}", value);
    }

    println!();
    println!("Kernel initialized successfully.");
    println!("Entering idle loop...");
    serial_println!("[BOOT] Kernel initialized, entering idle loop");

    // Halt loop - kernel is now running
    loop {
        x86_64::instructions::hlt();
    }
}

/// Panic handler - called on kernel panic
#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    serial_println!("[PANIC] {}", info);
    println!();
    println!("╔════════════════════════════════════════════════════════════════════════════╗");
    println!("║                           KERNEL PANIC                                     ║");
    println!("╚════════════════════════════════════════════════════════════════════════════╝");
    println!("{}", info);

    loop {
        x86_64::instructions::hlt();
    }
}
