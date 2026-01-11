// Copyright © 2025 [Mitchell_Burns/ Everplay-Tech]. All rights reserved.
// Proprietary and confidential. Not open source.
// Unauthorized copying, distribution, or modification prohibited.

use roulette_macros::BraidInvariant;

/// BRAID THEORY PRIMITIVES FOR ROULETTE KERNEL
///
/// This module implements braid group theory operations for the T9-braid computation model.
/// Braids represent computation where strands are CPU registers and crossings are instructions.
///
/// Key concepts:
/// - Braid groups: `B_n` (braids on n strands)
/// - Generators: `σ_i` (crossing strand i over i+1)
/// - Inverse generators: `σ_i⁻¹` (crossing strand i+1 over i)
/// - Braid words: sequences of generators representing computations
///
/// Braid generator: fundamental operation of crossing two adjacent strands
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BraidGenerator {
    /// `σ_i`: strand i crosses over strand i+1 (left-to-right crossing)
    Left(u8),
    /// `σ_i⁻¹`: strand i+1 crosses over strand i (right-to-left crossing)
    Right(u8),
}

use crate::RouletteInt;
#[derive(Debug, Clone, PartialEq, Eq, BraidInvariant)]
pub struct BraidWord {
    pub generators: [BraidGenerator; 16],
    pub length: usize,
    /// Phantom data representing the homotopy dimension (braids live in dimension 1)
    pub _homotopy: core::marker::PhantomData<[(); 1]>,
}

impl BraidWord {
    /// Identity braid (no crossings)
    pub const IDENTITY: Self = Self {
        generators: [BraidGenerator::Left(0); 16], // Dummy values, length 0
        length: 0,
        _homotopy: core::marker::PhantomData,
    };

    /// Create braid word from `RouletteInt` compressed data
    #[must_use] 
    pub fn from_roulette_int(value: &RouletteInt) -> Self {
        let mut generators = [BraidGenerator::Left(0); 16];
        let mut length = 0;

        // Extract braid generators from compressed data patterns
        let braid_generators = value.extract_braid_word();

        for generator in &braid_generators {
            if *generator != BraidGenerator::Left(0) && length < 16 {
                generators[length] = *generator;
                length += 1;
            }
        }

        Self { generators, length, _homotopy: core::marker::PhantomData }
    }

    /// Reduce braid word using braid relations
    /// Braid relations: `σ_i` `σ_j` = `σ_j` `σ_i` for |i-j| ≥ 2
    ///                  `σ_i` `σ_i⁻¹` = `σ_i⁻¹` `σ_i` = identity
    ///                  `σ_i` σ_{i+1} `σ_i` = σ_{i+1} `σ_i` σ_{i+1}
    pub fn reduce(&mut self) {
        // Simple reduction: remove adjacent inverse pairs
        let mut i = 0;
        while i + 1 < self.length {
            let gen1 = self.generators[i];
            let gen2 = self.generators[i + 1];

            // Check for inverse pair
            if Self::are_inverse(gen1, gen2) {
                // Remove both generators by shifting array
                for j in i..self.length - 2 {
                    self.generators[j] = self.generators[j + 2];
                }
                self.length -= 2;
                // Don't increment i, check the new pair at this position
            } else {
                i += 1;
            }
        }
    }

    /// Check if two generators are inverses of each other
    fn are_inverse(gen1: BraidGenerator, gen2: BraidGenerator) -> bool {
        match (gen1, gen2) {
            (BraidGenerator::Left(n), BraidGenerator::Right(m)) if n == m => true,
            (BraidGenerator::Right(n), BraidGenerator::Left(m)) if n == m => true,
            _ => false,
        }
    }

    /// Get canonical form using Artin generators
    #[must_use] 
    pub fn canonical_form(&self) -> Self {
        let mut result = self.clone();
        result.reduce();
        result
    }

    /// Convert to Gödel number representation
    /// Each generator gets a prime number, braid word is product of primes
    #[must_use] 
    pub fn to_godel_number(&self) -> u128 {
        let mut result = 1u128;
        let primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53];

        for i in 0..self.length {
            let prime_idx = match self.generators[i] {
                BraidGenerator::Left(n) => {
                    // Braid generators are positive strand indices
                    (n as usize).min(15)
                },
                BraidGenerator::Right(n) => {
                    // Right crossings are offset by 8 in the prime array
                    8 + (n as usize).min(7)
                },
            };
            result = result.saturating_mul(primes[prime_idx]);
        }

        result
    }
}

/// Braid group operations for kernel computations
#[derive(Debug, Clone)]
pub struct BraidGroup {
    strands: usize,
}

impl BraidGroup {
    /// Create braid group on n strands
    #[must_use] 
    pub const fn new(strands: usize) -> Self {
        Self { strands }
    }

    /// Apply braid word to initial strand permutation
    #[must_use] 
    pub fn apply_word(&self, word: &BraidWord) -> [usize; 16] {
        let mut permutation = [0; 16];

        // Initialize identity permutation
        for (i, perm) in permutation.iter_mut().enumerate().take(self.strands.min(16)) {
            *perm = i;
        }

        // Apply each generator in sequence
        for generator in word.generators.iter().take(word.length) {
            match generator {
                BraidGenerator::Left(n) => {
                    // Ensure n is non-negative and within bounds
                    #[allow(clippy::cast_sign_loss)]
                    let idx = (*n).max(0) as usize;
                    if idx + 1 < self.strands {
                        // Swap strands idx and idx+1
                        permutation.swap(idx, idx + 1);
                    }
                }
                BraidGenerator::Right(n) => {
                    // Ensure n is non-negative and within bounds
                    #[allow(clippy::cast_sign_loss)]
                    let idx = (*n).max(0) as usize;
                    if idx + 1 < self.strands {
                        // Swap strands idx and idx+1 (inverse operation)
                        permutation.swap(idx, idx + 1);
                    }
                }
            }
        }

        permutation
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::RouletteInt;

    #[test]
    fn test_braid_word_from_roulette_int() {
        let value = RouletteInt::from_u128(1337);
        let braid_word = BraidWord::from_roulette_int(&value);

        // Should extract some braid generators
        assert!(braid_word.length > 0);
    }

    #[test]
    fn test_braid_word_reduction() {
        let mut word = BraidWord {
            generators: [
                BraidGenerator::Left(1),
                BraidGenerator::Right(1), // Inverse of Left(1)
                BraidGenerator::Left(2),
                BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
            ],
            length: 3,
            _homotopy: core::marker::PhantomData,
        };

        word.reduce();

        // Should reduce Left(1) + Right(1) to identity, leaving Left(2)
        assert_eq!(word.length, 1);
        assert_eq!(word.generators[0], BraidGenerator::Left(2));
    }

    #[test]
    fn test_godel_number_generation() {
        let word = BraidWord {
            generators: [
                BraidGenerator::Left(1), BraidGenerator::Left(2),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0),
            ],
            length: 2,
            _homotopy: core::marker::PhantomData,
        };

        let godel = word.to_godel_number();
        assert!(godel > 1); // Should be product of primes
    }

    #[test]
    fn test_braid_group_operations() {
        let group = BraidGroup::new(4);
        let word = BraidWord {
            generators: [
                BraidGenerator::Left(1),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
                BraidGenerator::Left(0), BraidGenerator::Left(0), BraidGenerator::Left(0),
            ],
            length: 1,
            _homotopy: core::marker::PhantomData,
        };

        let permutation = group.apply_word(&word);
        // Left(1) should swap strands 1 and 2
        assert_eq!(permutation[0], 0); // Strand 0 unchanged
        assert_eq!(permutation[1], 2); // Strand 1 moved to position 2
        assert_eq!(permutation[2], 1); // Strand 2 moved to position 1
        assert_eq!(permutation[3], 3); // Strand 3 unchanged
    }
}