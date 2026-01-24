#![no_std]

extern crate alloc;
use alloc::vec::Vec;
use alloc::string::String;
use muscle_contract::abi::Pheromone;

/// Antibody Muscle: The Auto-immune Fuzzer
pub struct Antibody {
    seed: u32,
}

impl Antibody {
    pub fn new(seed: u32) -> Self {
        Self { seed }
    }

    /// Linear Congruential Generator for no_std randomness
    fn next_u32(&mut self) -> u32 {
        self.seed = self.seed.wrapping_mul(1103515245).wrapping_add(12345);
        self.seed
    }

    /// Generate a "Mutated Command" to stress Broca and Quenyan
    pub fn generate_toxin(&mut self) -> Pheromone {
        let roll = self.next_u32() % 5;
        match roll {
            0 => Pheromone::SomaticInput(b'!'), // Junk character
            1 => Pheromone::SomaticInput(0xFF), // Invalid ASCII
            2 => Pheromone::Adrenaline(self.next_u32() as u8), // System Stress signal
            3 => Pheromone::SomaticInput(b's'), // Valid but frequent trigger
            _ => Pheromone::Inert,
        }
    }

    /// Produce a "Logic Pathogen" string for Quenyan
    pub fn generate_pathogen(&mut self) -> String {
        let roll = self.next_u32() % 3;
        match roll {
            0 => String::from("1 / 0"), // Division by zero
            1 => String::from("( ( ( ( 1 ) ) )"), // Unbalanced parens
            _ => String::from("9999999999999999999999"), // Overflow attempt
        }
    }
}
