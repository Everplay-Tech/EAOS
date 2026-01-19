use uefi::table::boot::BootServices;
use crate::cell::Cell;
use crate::uart::Uart;
use crate::arachnid::{SPIDER, ARACHNID_STREAM, sync_state, SpiderState};
use crate::virtio_modern::{KERNEL_OVERRIDES, RX_BUFFERS, VirtioModern};

/// Tick the ARACHNID spider (poll network, feed to sanitizer)
///
/// This is called every scheduler tick to process incoming network data.
/// When the Spider is in harvesting mode, incoming TCP data is passed
/// through the Acid Bath sanitizer and into the BIO-STREAM ring buffer.
///
/// # Safety
///
/// Accesses global mutable statics (SPIDER, ARACHNID_STREAM, KERNEL_OVERRIDES).
/// Must only be called from the single-threaded scheduler loop.
unsafe fn tick_arachnid(driver: Option<&mut VirtioModern>) {
    // Only process if we have a network driver
    let Some(driver) = driver else {
        return;
    };

    // Check for received packets
    while let Some((buffer_id, length)) = driver.process_rx() {
        // Get the received data
        let data = &RX_BUFFERS.buffers[buffer_id][..length as usize];

        // Get current choke value
        let choke = KERNEL_OVERRIDES.net_choke;

        // Feed to spider if harvesting
        if SPIDER.state() == SpiderState::Harvesting {
            SPIDER.poll(data, &ARACHNID_STREAM, choke);
        }

        // TODO: Re-provision the RX buffer for next packet
        // This requires calling driver.provision_rx_buffer(buffer_id)
    }

    // Sync spider state to ring buffer (for UI polling)
    sync_state();
}

/// Round-robin scheduler that executes muscle cells in sequence.
/// Each muscle is called and expected to return; the scheduler then
/// moves to the next muscle.
///
/// ## Phase 2: ARACHNID Integration
///
/// Each tick now also polls the network and feeds data to the Spider.
pub fn run_scheduler(bt: &BootServices, cells: &[Option<Cell>], uart: &mut Uart) -> ! {
    let mut index = 0;
    let mut execution_count: u64 = 0;

    uart.log("INFO", "Scheduler starting round-robin execution");
    uart.log("INFO", "ARACHNID Spider: ARMED");

    loop {
        // ================================================================
        // PHASE 2: Poll ARACHNID spider
        // ================================================================
        // Note: VirtioModern driver would need to be passed in here
        // For now, this scaffolding is ready for when TCP integration lands
        unsafe {
            tick_arachnid(None); // TODO: Pass actual driver reference
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
