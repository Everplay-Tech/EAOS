use uefi::table::boot::BootServices;
use crate::cell::Cell;
use crate::uart::Uart;

pub fn run_scheduler(bt: &BootServices, cells: &[Option<Cell>], uart: &mut Uart) -> ! {
    let mut index = 0;
    let mut execution_count = 0;
    
    loop {
        if let Some(cell) = &cells[index % cells.len()] {
            // Validate canary before execution
            if !cell.validate_canary() {
                uart.log("FATAL", "Stack canary corrupted - system halted");
                break;
            }
            
            execution_count += 1;
            
            // Log every 1000 executions
            if execution_count % 1000 == 0 {
                uart.log("DEBUG", &format!("Executed {} muscle calls", execution_count));
            }
            
            // Execute muscle
            unsafe {
                core::arch::asm!(
                    "call {}",
                    in(reg) cell.entry_point,
                    options(noreturn)
                );
            }
        }
        
        index += 1;
        
        // Small delay to prevent busyloop
        bt.stall(1000);
    }
    
    // If we break from the loop, halt the system
    loop {
        bt.stall(10_000_000);
    }
}
