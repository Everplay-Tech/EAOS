#![cfg_attr(not(feature = "std"), no_std)]

use heapless::Vec;
use muscle_contract::abi::Pheromone;

pub struct EndocrineSystem {
    // "heapless" crate is standard for this in no_std
    secretions: Vec<Pheromone, 32>,
    circulating: Vec<Pheromone, 32>,
}

impl Default for EndocrineSystem {
    fn default() -> Self {
        Self::new()
    }
}

impl EndocrineSystem {
    pub fn new() -> Self {
        Self {
            secretions: Vec::new(),
            circulating: Vec::new(),
        }
    }

    /// The Heartbeat: Moves new secretions into circulation
    pub fn cycle(&mut self) {
        self.circulating = self.secretions.clone();
        self.secretions.clear();
    }
    
    /// Organs call this to emit a signal
    pub fn secrete(&mut self, p: Pheromone) {
        // If full, we drop the signal (biological saturation)
        let _ = self.secretions.push(p);
    }

    /// Organs call this to sense the environment
    pub fn sense(&self) -> &[Pheromone] {
        &self.circulating
    }
}