use uefi::table::boot::BootServices;
use crate::cell::Cell;
use crate::uart::Uart;
use crate::arachnid::{SPIDER, ARACHNID_STREAM, NETWORK, sync_state, SpiderState};
use crate::virtio_modern::{KERNEL_OVERRIDES, RX_BUFFERS, VirtioModern};

/// Phase 3: Tick the ARACHNID spider with network polling
///
/// This handles raw packet processing and feeds data to the Spider.
/// Full smoltcp TCP integration is scaffolded but requires additional
/// work to handle the complex socket lifecycle.
///
/// # Safety
///
/// Accesses global mutable statics. Must only be called from single-threaded scheduler.
unsafe fn tick_arachnid_network(driver: &mut VirtioModern) {
    // Initialize network manager with MAC if needed
    if !NETWORK.is_initialized() {
        NETWORK.init(driver.mac);
    }

    let choke = KERNEL_OVERRIDES.net_choke;

    // Process any received packets
    while let Some((buffer_id, length)) = driver.process_rx() {
        let data = &RX_BUFFERS.buffers[buffer_id][..length as usize];

        // If harvesting, feed through Spider
        if SPIDER.state() == SpiderState::Harvesting {
            SPIDER.poll(data, &ARACHNID_STREAM, choke);
        }

        // TODO: Full smoltcp integration would process packets here:
        // 1. Pass Ethernet frame to smoltcp interface
        // 2. Let smoltcp handle ARP, IP, TCP
        // 3. Read from TCP socket buffer
        // 4. Feed to Spider.poll()
    }

    // Sync spider state to ring buffer (for UI polling)
    sync_state();
}

/// Tick for state sync only (no network driver)
unsafe fn tick_arachnid_sync_only() {
    sync_state();
}

/// Round-robin scheduler that executes muscle cells in sequence.
/// Each muscle is called and expected to return; the scheduler then
/// moves to the next muscle.
///
/// ## Phase 3: Network Integration
///
/// Each tick polls the network for received packets.
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
        uart.log("INFO", "Phase 3: Network driver ONLINE");
    } else {
        uart.log("WARN", "No network driver - ARACHNID in demo mode");
    }

    loop {
        // ================================================================
        // PHASE 3: Poll ARACHNID network
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

            // Log every 1000 executions (using static message)
            if execution_count % 1000 == 0 {
                uart.log("DEBUG", "Milestone: 1000 muscle calls executed");
            }

            // Execute muscle - FIXED: removed options(noreturn) so muscles can return
            // The muscle function is expected to be: extern "C" fn() -> ()
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
