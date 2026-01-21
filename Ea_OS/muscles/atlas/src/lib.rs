#![no_std]

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KeyAction {
    Press,
    Release,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KeyCode {
    Char(char),
    Enter,
    Backspace,
    Space,
    Escape,
    Shift,
    Unknown,
}

#[derive(Debug, Clone, Copy)]
pub struct KeyEvent {
    pub action: KeyAction,
    pub code: KeyCode,
}

pub struct Atlas {
    state: State,
    shift: bool,
}

enum State {
    Idle,
    Release,
    Extended, // For E0 prefix
}

impl Atlas {
    pub fn new() -> Self {
        Self { state: State::Idle, shift: false }
    }

    /// Process a PS/2 scancode byte
    pub fn process(&mut self, scancode: u8) -> Option<KeyEvent> {
        match self.state {
            State::Idle => {
                match scancode {
                    0xF0 => {
                        self.state = State::Release;
                        None
                    }
                    0xE0 => {
                        self.state = State::Extended;
                        None
                    }
                    _ => self.map_scancode(scancode, KeyAction::Press),
                }
            }
            State::Release => {
                self.state = State::Idle;
                self.map_scancode(scancode, KeyAction::Release)
            }
            State::Extended => {
                self.state = State::Idle; // Ignore extended specifics for now
                None 
            }
        }
    }

    fn map_scancode(&mut self, code: u8, action: KeyAction) -> Option<KeyEvent> {
        let key = match code {
            0x1C => KeyCode::Char('a'),
            0x32 => KeyCode::Char('b'),
            0x21 => KeyCode::Char('c'),
            0x23 => KeyCode::Char('d'),
            0x24 => KeyCode::Char('e'),
            0x2B => KeyCode::Char('f'),
            0x34 => KeyCode::Char('g'),
            0x33 => KeyCode::Char('h'),
            0x43 => KeyCode::Char('i'),
            0x3B => KeyCode::Char('j'),
            0x42 => KeyCode::Char('k'),
            0x4B => KeyCode::Char('l'),
            0x3A => KeyCode::Char('m'),
            0x31 => KeyCode::Char('n'),
            0x44 => KeyCode::Char('o'),
            0x4D => KeyCode::Char('p'),
            0x15 => KeyCode::Char('q'),
            0x2D => KeyCode::Char('r'),
            0x1B => KeyCode::Char('s'),
            0x2C => KeyCode::Char('t'),
            0x3C => KeyCode::Char('u'),
            0x2A => KeyCode::Char('v'),
            0x1D => KeyCode::Char('w'),
            0x22 => KeyCode::Char('x'),
            0x35 => KeyCode::Char('y'),
            0x1A => KeyCode::Char('z'),
            
            0x16 => KeyCode::Char('1'),
            0x1E => KeyCode::Char('2'),
            0x26 => KeyCode::Char('3'),
            0x25 => KeyCode::Char('4'),
            0x2E => KeyCode::Char('5'),
            0x36 => KeyCode::Char('6'),
            0x3D => KeyCode::Char('7'),
            0x3E => KeyCode::Char('8'),
            0x46 => KeyCode::Char('9'),
            0x45 => KeyCode::Char('0'),

            0x5A => KeyCode::Enter,
            0x66 => KeyCode::Backspace,
            0x29 => KeyCode::Space,
            0x76 => KeyCode::Escape,
            
            0x12 | 0x59 => {
                if action == KeyAction::Press { self.shift = true; }
                if action == KeyAction::Release { self.shift = false; }
                KeyCode::Shift
            }

            _ => KeyCode::Unknown,
        };

        if key == KeyCode::Unknown || key == KeyCode::Shift {
            return None;
        }

        // Apply shift modifier
        let final_key = if self.shift && action == KeyAction::Press {
            match key {
                KeyCode::Char(c) if c.is_ascii_lowercase() => KeyCode::Char(c.to_ascii_uppercase()),
                _ => key
            }
        } else {
            key
        };

        Some(KeyEvent { action, code: final_key })
    }
}
