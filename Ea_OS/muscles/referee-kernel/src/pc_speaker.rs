use x86_64::instructions::port::Port;

/// PC Speaker Driver (8253/8254 PIT)
pub struct PcSpeaker {
    /// PIT Channel 2 Data Port
    pit_data: Port<u8>,
    /// PIT Command Port
    pit_cmd: Port<u8>,
    /// Speaker Control Port
    control: Port<u8>,
}

impl PcSpeaker {
    pub const fn new() -> Self {
        Self {
            pit_data: Port::new(0x42),
            pit_cmd: Port::new(0x43),
            control: Port::new(0x61),
        }
    }

    /// Enable the speaker
    pub unsafe fn enable(&mut self) {
        let prev = self.control.read();
        // Set bit 0 (Gate 2) and bit 1 (Speaker Data)
        self.control.write(prev | 3);
    }

    /// Disable the speaker
    pub unsafe fn disable(&mut self) {
        let prev = self.control.read();
        // Clear bit 0 and 1
        self.control.write(prev & !3);
    }

    /// Play a sound at a specific frequency (Hz)
    pub unsafe fn play(&mut self, freq: u32) {
        if freq == 0 {
            self.disable();
            return;
        }

        // The PIT clock runs at 1.193182 MHz
        let divisor = 1193180 / freq;
        
        // Command: Channel 2, Access Lo/Hi, Square Wave, Binary
        self.pit_cmd.write(0xB6);
        
        // Write divisor (Low byte then High byte)
        self.pit_data.write((divisor & 0xFF) as u8);
        self.pit_data.write((divisor >> 8) as u8);

        self.enable();
    }

    /// Beep for a short duration
    /// Note: This busy-waits. In a real system, we'd use a timer event.
    pub unsafe fn beep(&mut self, freq: u32, iterations: u64) {
        self.play(freq);
        for _ in 0..iterations {
            core::arch::asm!("pause");
        }
        self.disable();
    }
}

pub static mut SPEAKER: PcSpeaker = PcSpeaker::new();
