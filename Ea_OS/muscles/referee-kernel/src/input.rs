use x86_64::instructions::port::Port;

pub struct Ps2Controller;

impl Ps2Controller {
    /// Poll the PS/2 controller for a scancode
    pub fn poll() -> Option<u8> {
        let mut status_port = Port::<u8>::new(0x64);
        let mut data_port = Port::<u8>::new(0x60);
        
        unsafe {
            // Check Output Buffer Full (Bit 0)
            if status_port.read() & 1 != 0 {
                Some(data_port.read())
            } else {
                None
            }
        }
    }

    /// Translate Set 2 Scancode to ASCII (Simplified)
    pub fn to_ascii(code: u8) -> Option<u8> {
        match code {
            0x1C => Some(b'a'), 0x32 => Some(b'b'), 0x21 => Some(b'c'), 0x23 => Some(b'd'),
            0x24 => Some(b'e'), 0x2B => Some(b'f'), 0x34 => Some(b'g'), 0x33 => Some(b'h'),
            0x43 => Some(b'i'), 0x3B => Some(b'j'), 0x42 => Some(b'k'), 0x4B => Some(b'l'),
            0x3A => Some(b'm'), 0x31 => Some(b'n'), 0x44 => Some(b'o'), 0x4D => Some(b'p'),
            0x15 => Some(b'q'), 0x2D => Some(b'r'), 0x1B => Some(b's'), 0x2C => Some(b't'),
            0x3C => Some(b'u'), 0x2A => Some(b'v'), 0x1D => Some(b'w'), 0x22 => Some(b'x'),
            0x35 => Some(b'y'), 0x1A => Some(b'z'),
            0x16 => Some(b'1'), 0x1E => Some(b'2'), 0x26 => Some(b'3'), 0x25 => Some(b'4'),
            0x2E => Some(b'5'), 0x36 => Some(b'6'), 0x3D => Some(b'7'), 0x3E => Some(b'8'),
            0x46 => Some(b'9'), 0x45 => Some(b'0'),
            0x29 => Some(b' '), 0x5A => Some(b'\n'), 0x66 => Some(0x08), // Backspace
            _ => None,
        }
    }
}
