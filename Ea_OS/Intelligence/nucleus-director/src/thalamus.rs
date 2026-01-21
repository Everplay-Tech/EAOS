#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;

use alloc::vec::Vec;
use alloc::collections::VecDeque;
use core::sync::atomic::{AtomicBool, Ordering};
use muscle_contract::BootParameters;

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
    // optic_nerve: BioStreamReader, // TODO: Implement BioStreamReader
    afferent_signal: &'static AtomicBool, // Placeholder for shared flag
}

impl Thalamus {
    pub fn new(_params: &BootParameters) -> Self {
        // In a real implementation, we would map the UART buffer and BioStream from params.
        // For now, we initialize empty.
        static DUMMY_SIGNAL: AtomicBool = AtomicBool::new(false);
        
        Self {
            uart_nerve: VecDeque::with_capacity(128),
            afferent_signal: &DUMMY_SIGNAL,
        }
    }

    /// The "Gating" function.
    /// Returns the most critical stimulus, suppressing noise if Volition is active.
    pub fn fetch_next_stimulus(&mut self) -> Option<Stimulus> {
        // A. Check the Reflex Arc (Optimization)
        // If the nerve hasn't fired and we have no pending conscious tasks, return.
        if !self.afferent_signal.load(Ordering::Relaxed) && self.uart_nerve.is_empty() {
            // Check optic nerve (lower priority)
            // if let Some(data) = self.optic_nerve.read_latest() {
            //     return Some(Stimulus::Perception(data));
            // }
            return None; 
        }

        // B. Somatic Override (Conscious Volition)
        // In a real system, we'd read from the shared UART ring buffer here.
        if !self.uart_nerve.is_empty() {
            let mut cmd = Vec::new();
            while let Some(byte) = self.uart_nerve.pop_front() {
                cmd.push(byte);
            }
            
            // Acknowledge the signal to reset the reflex
            self.afferent_signal.store(false, Ordering::Relaxed);
            return Some(Stimulus::Volition(cmd));
        }

        None
    }
    
    // Helper to simulate UART input (since we can't really read hardware yet)
    pub fn inject_uart(&mut self, byte: u8) {
        self.uart_nerve.push_back(byte);
        self.afferent_signal.store(true, Ordering::Relaxed);
    }
}
