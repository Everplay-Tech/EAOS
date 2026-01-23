#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;

use alloc::vec::Vec;
use alloc::collections::VecDeque;
use core::sync::atomic::{AtomicBool, Ordering};
use muscle_contract::BootParameters;

use ea_symbiote::Symbiote;

// 1. THE SYNAPSE (Shared Memory Flag)
// In a real system, this would be a pointer to a specific memory address shared with the Referee.
// For now, we simulate it or expect it to be passed in BootParameters.
// Since we don't have a shared atomic in BootParameters yet, we'll assume polling for now.
// The Innovator said: "Referee... sets an atomic flag (The Synapse)."
// We will need to add this to BootParameters in the future.

// 2. THE STIMULI
#[derive(Debug, Clone)]
pub enum Stimulus {
    /// High Priority: Direct command from the Operator
    Volition(Vec<u8>), 
    /// Low Priority: Environmental data from Arachnid
    Perception(Vec<u8>),
}

// 3. THE THALAMUS (Multiplexer)
pub struct Thalamus {
    uart_nerve: VecDeque<u8>, 
    afferent_signal: &'static AtomicBool,
    synapse: Symbiote,
}

impl Thalamus {
    pub fn new(params: &BootParameters) -> Self {
        // Map Afferent Signal
        static DUMMY_SIGNAL: AtomicBool = AtomicBool::new(false);
        let signal = if params.afferent_signal_addr != 0 {
            unsafe { &*(params.afferent_signal_addr as *const AtomicBool) }
        } else {
            &DUMMY_SIGNAL
        };
        
        Self {
            uart_nerve: VecDeque::with_capacity(128),
            afferent_signal: signal,
            synapse: Symbiote::new(),
        }
    }

    /// The "Gating" function.
    /// Returns the most critical stimulus, suppressing noise if Volition is active.
    pub fn fetch_next_stimulus(&mut self) -> Option<Stimulus> {
        // A. Somatic Override (Conscious Volition)
        if self.afferent_signal.load(Ordering::Relaxed) || !self.uart_nerve.is_empty() {
            // Check real UART (simulated via inject_uart for now)
            if !self.uart_nerve.is_empty() {
                let mut cmd = Vec::new();
                while let Some(byte) = self.uart_nerve.pop_front() {
                    cmd.push(byte);
                }
                self.afferent_signal.store(false, Ordering::Relaxed);
                return Some(Stimulus::Volition(cmd));
            }
        }
        
        // B. Visceral Input (Network)
        if let Ok(data) = self.synapse.poll_network() {
            if !data.is_empty() {
                return Some(Stimulus::Perception(data));
            }
        }

        None
    }
    
    // Helper to simulate UART input (since we can't really read hardware yet)
    pub fn inject_uart(&mut self, byte: u8) {
        self.uart_nerve.push_back(byte);
        self.afferent_signal.store(true, Ordering::Relaxed);
    }
}
