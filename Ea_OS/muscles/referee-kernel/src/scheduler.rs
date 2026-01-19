//! EAOS Round-Robin Scheduler with ARACHNID Network Integration
//!
//! ## Phase 5: Persistent Physiology & Control Wiring
//!
//! - ENTROPY_FLUX: Maps to bookmark selection (Spider::tune)
//! - MEM_ACID + ARMED: Ignition control (Spider::ignite)
//! - NET_CHOKE: Baud rate throttling (passed to Spider::poll)

extern crate alloc;

use uefi::table::boot::BootServices;
use crate::cell::Cell;
use crate::uart::Uart;
use crate::arachnid::{SPIDER, NETWORK, sync_state, get_stream, SpiderState};
use crate::virtio_modern::{KERNEL_OVERRIDES, RX_BUFFERS, VirtioModern};

// ============================================================================
// Phase 5: Tick Functions with Control Wiring
// ============================================================================

/// Tick the ARACHNID spider with raw packet processing and control wiring
///
/// # Safety
/// Accesses global mutable statics. Must only be called from single-threaded scheduler.
unsafe fn tick_arachnid_network(driver: &mut VirtioModern) {
    // Initialize network manager with MAC if needed
    if !NETWORK.is_initialized() {
        NETWORK.init(driver.mac);
    }

    // ========================================================================
    // Read Control Overrides from Tactile Deck
    // ========================================================================
    let entropy = KERNEL_OVERRIDES.entropy_flux;
    let choke = KERNEL_OVERRIDES.net_choke;
    let mem_acid = KERNEL_OVERRIDES.mem_acid;
    let armed = KERNEL_OVERRIDES.is_armed();

    // ========================================================================
    // CONTROL WIRING: ENTROPY_FLUX -> Bookmark Selection
    // ========================================================================
    // Maps the entropy knob (0.0-1.0) to bookmark index
    SPIDER.tune(entropy);

    // ========================================================================
    // CONTROL WIRING: MEM_ACID + ARMED -> Ignition / Deadman Switch
    // ========================================================================
    // If armed and slide > 0.5: initiate connection
    // If not armed during operation: abort (deadman switch)
    SPIDER.ignite(armed, mem_acid);

    // ========================================================================
    // Process Received Packets
    // ========================================================================
    while let Some((buffer_id, length)) = driver.process_rx() {
        let data = &RX_BUFFERS.buffers[buffer_id][..length as usize];

        // If harvesting, feed through Spider's Acid Bath
        if SPIDER.state() == SpiderState::Harvesting {
            SPIDER.poll(data, get_stream(), choke);
        }

        // Re-provision the buffer for next packet
        driver.reprovision_rx(buffer_id);
    }

    // Sync spider state to ring buffer (for UI polling)
    sync_state();
}

/// Tick for state sync only (no network driver - demo mode)
///
/// Still processes control inputs for UI feedback.
unsafe fn tick_arachnid_sync_only() {
    // Wire controls even in demo mode
    let entropy = KERNEL_OVERRIDES.entropy_flux;
    let mem_acid = KERNEL_OVERRIDES.mem_acid;
    let armed = KERNEL_OVERRIDES.is_armed();

    SPIDER.tune(entropy);
    SPIDER.ignite(armed, mem_acid);

    sync_state();
}

// ============================================================================
// Scheduler Entry Points
// ============================================================================

/// Round-robin scheduler that executes muscle cells in sequence.
pub fn run_scheduler(bt: &BootServices, cells: &[Option<Cell>], uart: &mut Uart) -> ! {
    run_scheduler_with_net(bt, cells, uart, None)
}

/// Scheduler with optional network driver
///
/// This is the main entry point when a Virtio network driver is available.
pub fn run_scheduler_with_net(
    bt: &BootServices,
    cells: &[Option<Cell>],
    uart: &mut Uart,
    mut net_driver: Option<VirtioModern>,
) -> ! {
    let mut index = 0;
    let mut execution_count: u64 = 0;

    uart.log("INFO", "Scheduler starting round-robin execution");
    uart.log("INFO", "ARACHNID Spider: ARMED");

    if net_driver.is_some() {
        uart.log("INFO", "Phase 5: Network driver ONLINE");
        uart.log("INFO", "Phase 5: Control wiring active");
    } else {
        uart.log("WARN", "No network driver - ARACHNID in demo mode");
    }

    // Log optic nerve status
    if crate::arachnid::is_optic_nerve_active() {
        uart.log("IVSHMEM", "Optic Nerve ACTIVE");
    }

    loop {
        // ================================================================
        // PHASE 5: Poll ARACHNID with Control Wiring
        // ================================================================
        if let Some(ref mut driver) = net_driver {
            unsafe {
                tick_arachnid_network(driver);
            }
        } else {
            unsafe {
                tick_arachnid_sync_only();
            }
        }

        // ================================================================
        // Execute muscle cells
        // ================================================================
        if let Some(cell) = &cells[index % cells.len()] {
            // Validate canary before execution
            if !cell.validate_canary() {
                uart.log("FATAL", "Stack canary corrupted - system halted");
                break;
            }

            execution_count += 1;

            // Log every 1000 executions
            if execution_count % 1000 == 0 {
                uart.log("DEBUG", "Milestone: 1000 muscle calls executed");
            }

            // Execute muscle
            unsafe {
                let func: extern "C" fn() = core::mem::transmute(cell.entry_point);
                func();
            }
        }

        index += 1;

        // Small delay to prevent busyloop (1ms)
        bt.stall(1000);
    }

    uart.log("FATAL", "Scheduler halted due to error");

    // If we break from the loop, halt the system
    loop {
        bt.stall(10_000_000);
    }
}
