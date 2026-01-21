#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;
use alloc::vec::Vec;
use alloc::string::String;
use serde::{Serialize, Deserialize};

/// The universal message type for the Endocrine System
#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum Pheromone {
    /// Lifecycle: System has started
    SystemStart,
    /// Lifecycle: System is shutting down
    Shutdown,
    /// Osteon: Document saved at block offset
    OsteonSaved(u64),
    /// Myocyte: Logic processed at block offset
    MyocyteProcessed(u64),
    /// Cardio: Heartbeat tick
    CardioPulse(u64),
    /// Somatic: User Command (raw text from Broca/UART)
    SomaticInput(String),
    /// Visual: Stimulus code (e.g. status color)
    VisualStimulus(u32),
    /// Error: Generic system error
    SystemError(String),
}

/// The Message Broker
pub struct EndocrineSystem {
    /// Events processed in the current frame
    inbox: Vec<Pheromone>,
    /// Events queued for the next frame
    outbox: Vec<Pheromone>,
}

impl Default for EndocrineSystem {
    fn default() -> Self {
        Self::new()
    }
}

impl EndocrineSystem {
    pub fn new() -> Self {
        Self {
            inbox: Vec::with_capacity(16),
            outbox: Vec::with_capacity(16),
        }
    }

    /// Push an event into the outbox (secrete into bloodstream)
    pub fn secrete(&mut self, p: Pheromone) {
        self.outbox.push(p);
    }

    /// Circulate: Move outbox to inbox and return the new inbox for processing
    pub fn circulate(&mut self) -> &[Pheromone] {
        self.inbox.clear();
        self.inbox.append(&mut self.outbox);
        &self.inbox
    }
}
