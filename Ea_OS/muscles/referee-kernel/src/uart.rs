use core::fmt::{self, Write};

pub struct Uart;

impl Uart {
    pub const fn new() -> Self {
        Self
    }
    
    pub fn init(&mut self) -> Result<(), &'static str> {
        unsafe {
            // Initialize 16550 UART
            let base = 0x3F8;
            
            // Disable interrupts
            core::ptr::write_volatile((base + 1) as *mut u8, 0x00);
            
            // Enable DLAB
            core::ptr::write_volatile((base + 3) as *mut u8, 0x80);
            
            // Set baud rate divisor
            core::ptr::write_volatile((base + 0) as *mut u8, 0x03); // 38400 baud
            core::ptr::write_volatile((base + 1) as *mut u8, 0x00);
            
            // Disable DLAB, set 8N1
            core::ptr::write_volatile((base + 3) as *mut u8, 0x03);
            
            // Enable FIFO
            core::ptr::write_volatile((base + 2) as *mut u8, 0xC7);
            
            // Enable modem control
            core::ptr::write_volatile((base + 4) as *mut u8, 0x0B);
        }
        
        Ok(())
    }
    
    pub fn write_byte(&mut self, byte: u8) {
        unsafe {
            let base = 0x3F8;
            
            // Wait for transmit buffer empty
            while core::ptr::read_volatile((base + 5) as *const u8) & 0x20 == 0 {}
            
            // Write byte
            core::ptr::write_volatile(base as *mut u8, byte);
        }
    }
    
    pub fn write_str(&mut self, s: &str) {
        for &byte in s.as_bytes() {
            self.write_byte(byte);
        }
    }
    
    pub fn log(&mut self, level: &str, message: &str) {
        let _ = write!(self, "[{}] {}\n", level, message);
    }
}

impl Write for Uart {
    fn write_str(&mut self, s: &str) -> fmt::Result {
        self.write_str(s);
        Ok(())
    }
}
