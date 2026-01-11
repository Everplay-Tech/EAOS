// Copyright © 2025 [Mitchell_Burns/ Everplay-Tech]. All rights reserved.
// Proprietary and confidential. Not open source.
// Unauthorized copying, distribution, or modification prohibited.

use crate::{BraidCPU, BraidExecutionError};
use roulette_core::braid::{BraidWord, BraidGenerator};

/// OVERLAP BITSTRING EXECUTION ENGINE
///
/// Executes programs based on bit overlap patterns in braid words.
/// Each bit in a braid word predicts the next instruction, enabling
/// predictive execution and superior compression.
///
/// Key concepts:
/// - Bit overlap: Each bit predicts the probability of the next bit
/// - Predictive execution: Execute likely instructions before they're needed
/// - Compression: Overlap patterns enable better program encoding
///
/// Overlap execution engine
pub struct OverlapExecutionEngine {
    /// CPU instance for braid execution
    cpu: BraidCPU,
    /// Overlap prediction table (64 entries for 6-bit patterns)
    overlap_table: [i8; 64],
    /// Current bit position in the braid word
    bit_position: usize,
    /// Prediction buffer for speculative execution
    prediction_buffer: [BraidGenerator; 8],
}

impl OverlapExecutionEngine {
    /// Create new overlap execution engine
    #[must_use] 
    pub fn new() -> Self {
        // Initialize with pre-computed overlap scores from core
        let overlap_table = roulette_core::OVERLAP_SCORES;

        Self {
            cpu: BraidCPU::new(),
            overlap_table,
            bit_position: 0,
            prediction_buffer: [BraidGenerator::Left(0); 8],
        }
    }

    /// Load a braid program with overlap analysis
    pub fn load_program(&mut self, program: BraidWord) {
        self.cpu.load_program(program);
        self.bit_position = 0;
        self.analyze_overlaps();
    }

    /// Analyze bit overlaps in the current program
    fn analyze_overlaps(&mut self) {
        if let Some(ref program) = self.cpu.program {
            // Extract bit patterns from braid generators
            for i in 0..program.length.saturating_sub(1) {
                let current_gen = program.generators[i];
                let next_gen = program.generators[i + 1];

                // Convert generators to bit patterns
                let current_bits = Self::generator_to_bits(current_gen);
                let next_bits = Self::generator_to_bits(next_gen);

                // Calculate overlap score
                let overlap_score = Self::calculate_overlap(current_bits, next_bits);

                // Store in prediction table (simplified mapping)
                let table_index = (current_bits & 0x3F) as usize; // 6 bits
                if table_index < 64 {
                    self.overlap_table[table_index] = overlap_score;
                }
            }
        }
    }

    /// Convert braid generator to bit pattern
    fn generator_to_bits(generator: BraidGenerator) -> u8 {
        match generator {
            BraidGenerator::Left(n) => (n & 0xF) as u8, // 4 bits for strand index
            BraidGenerator::Right(n) => ((n & 0xF) as u8) | 0x10, // 4 bits + direction bit
        }
    }

    /// Calculate overlap score between two bit patterns
    fn calculate_overlap(bits1: u8, bits2: u8) -> i8 {
        let xor = bits1 ^ bits2;
        let overlap = (bits1 & bits2).count_ones() as i8;
        let difference = xor.count_ones() as i8;

        // Positive score for overlapping bits, negative for differences
        overlap - difference
    }

    /// Execute with overlap prediction
    pub fn execute_with_prediction(&mut self) -> Result<(), BraidExecutionError> {
        // Execute current instruction
        self.cpu.step()?;

        // Predict and speculatively execute next instructions
        self.predict_next_instructions();

        Ok(())
    }

    /// Predict next instructions based on overlap patterns
    fn predict_next_instructions(&mut self) {
        if let Some(ref program) = self.cpu.program {
            if self.cpu.pc >= program.length {
                return;
            }

            let current_gen = program.generators[self.cpu.pc];
            let current_bits = Self::generator_to_bits(current_gen);

            // Look up prediction score
            let table_index = (current_bits & 0x3F) as usize;
            let prediction_score = if table_index < 64 {
                self.overlap_table[table_index]
            } else {
                0
            };

            // If prediction score is positive, speculatively execute likely next instruction
            if prediction_score > 0 && self.cpu.pc + 1 < program.length {
                let predicted_gen = program.generators[self.cpu.pc + 1];

                // Store in prediction buffer for potential rollback
                self.prediction_buffer[0] = predicted_gen;

                // Apply predicted operation speculatively
                let word = BraidWord {
                    generators: [predicted_gen, BraidGenerator::Left(0), BraidGenerator::Left(0),
                               BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                               BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                               BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                               BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                               BraidGenerator::Left(0)],
                    length: 1,
                    _homotopy: core::marker::PhantomData,
                };

                // Note: In a real implementation, we'd need to save/restore CPU state
                // This is a simplified version for demonstration
                let _predicted_permutation = self.cpu.braid_group.apply_word(&word);
            }
        }
    }

    /// Get current CPU state
    #[must_use] 
    pub fn get_cpu(&self) -> &BraidCPU {
        &self.cpu
    }

    /// Get current CPU state mutably
    pub fn get_cpu_mut(&mut self) -> &mut BraidCPU {
        &mut self.cpu
    }

    /// Get overlap prediction statistics
    #[must_use] 
    pub fn get_overlap_stats(&self) -> OverlapStats {
        let mut positive_predictions = 0;
        let mut negative_predictions = 0;
        let mut total_overlap = 0i32;

        for &score in &self.overlap_table {
            if score > 0 {
                positive_predictions += 1;
            } else if score < 0 {
                negative_predictions += 1;
            }
            total_overlap += i32::from(score);
        }

        OverlapStats {
            positive_predictions,
            negative_predictions,
            average_overlap: total_overlap as f32 / 64.0,
        }
    }
}

/// Overlap execution statistics
#[derive(Debug, Clone, Copy)]
pub struct OverlapStats {
    pub positive_predictions: u32,
    pub negative_predictions: u32,
    pub average_overlap: f32,
}

#[cfg(test)]
mod tests {
    use super::*;
    use roulette_core::braid::BraidGenerator;

    #[test]
    fn test_overlap_execution_engine() {
        let mut engine = OverlapExecutionEngine::new();

        // Create a simple braid program
        let program = BraidWord {
            generators: [
                BraidGenerator::Left(1),
                BraidGenerator::Right(2),
                BraidGenerator::Left(1),
                BraidGenerator::Right(2),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
            ],
            length: 4,
            _homotopy: core::marker::PhantomData,
        };

        engine.load_program(program);

        // Execute with prediction
        assert!(engine.execute_with_prediction().is_ok());

        // Check overlap stats
        let stats = engine.get_overlap_stats();
        assert!(stats.average_overlap >= -2.0 && stats.average_overlap <= 2.0);
    }

    #[test]
    fn test_generator_to_bits() {
        let _engine = OverlapExecutionEngine::new();

        let bits_left = OverlapExecutionEngine::generator_to_bits(BraidGenerator::Left(3));
        assert_eq!(bits_left, 3);

        let bits_right = OverlapExecutionEngine::generator_to_bits(BraidGenerator::Right(3));
        assert_eq!(bits_right, 3 | 0x10);
    }

    #[test]
    fn test_overlap_calculation() {
        let _engine = OverlapExecutionEngine::new();

        // Same bits should have positive overlap
        let overlap_same = OverlapExecutionEngine::calculate_overlap(0b101010, 0b101010);
        assert_eq!(overlap_same, 3); // 3 bits overlap

        // Different bits should have negative overlap
        let overlap_diff = OverlapExecutionEngine::calculate_overlap(0b101010, 0b010101);
        assert_eq!(overlap_diff, -6); // All bits differ
    }
}

impl Default for OverlapExecutionEngine {
    fn default() -> Self {
        Self::new()
    }
}