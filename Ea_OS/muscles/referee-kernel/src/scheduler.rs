use uefi::table::boot::BootServices;
use crate::cell::Cell;
use crate::uart::Uart;

/// Round-robin scheduler that executes muscle cells in sequence.
/// Each muscle is called and expected to return; the scheduler then
/// moves to the next muscle.
pub fn run_scheduler(bt: &BootServices, cells: &[Option<Cell>], uart: &mut Uart) -> ! {
    let mut index = 0;
    let mut execution_count: u64 = 0;

    uart.log("INFO", "Scheduler starting round-robin execution");

    loop {
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
