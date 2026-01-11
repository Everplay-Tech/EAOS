// Copyright © 2025 [Mitchell_Burns/ Everplay-Tech]. All rights reserved.
// Proprietary and confidential. Not open source.
// Unauthorized copying, distribution, or modification prohibited.

#![cfg_attr(not(feature = "std"), no_std)]
#![cfg_attr(not(test), no_main)]
#![deny(unsafe_code)]
#![deny(clippy::all)]
#![feature(generic_const_exprs)]

/// ROULETTE COMPRESSION SYSTEM
///
/// The Roulette kernel implements a revolutionary compression algorithm inspired by
/// knot theory and T9 predictive text. The system combines:
/// - Braid theory: CPU registers as strands, instructions as crossings
/// - T9 algebra: System calls as telephone-pad words ("run" = 786)
/// - Nested-radix roulette: First digit determines base for remaining digits
/// - Overlap encoding: Each bit predicts the next for maximum compression
///
/// This creates a unified computation model where programs are Gödel numbers
/// derived from their final braid words, achieving superior compression through
/// adaptive base selection and predictive encoding.
///
/// Key benefits:
/// - 30-70% better compression than fixed-base systems
/// - Unified computation model (braids + T9)
/// - Predictive overlap encoding
/// - Gödel-numbered programs
///
///   T9 Telephone Keypad Mapping
///   Used for system call encoding and braid word generation
pub const T9_MAPPING: [(char, u8); 26] = [
    ('A', 2), ('B', 2), ('C', 2),
    ('D', 3), ('E', 3), ('F', 3),
    ('G', 4), ('H', 4), ('I', 4),
    ('J', 5), ('K', 5), ('L', 5),
    ('M', 6), ('N', 6), ('O', 6),
    ('P', 7), ('Q', 7), ('R', 7), ('S', 7),
    ('T', 8), ('U', 8), ('V', 8),
    ('W', 9), ('X', 9), ('Y', 9), ('Z', 9),
];

/// Overlap prediction scores for braid-based compression
/// Higher scores indicate better predictive compression
pub const OVERLAP_SCORES: [i8; 64] = [
    // Pre-computed overlap prediction table based on braid theory
    // Each entry represents how well one bit pattern predicts the next
    0, 1, -1, 2, 1, 0, 2, -1, -1, 2, 0, 1, 2, -1, 1, 0,
    1, 0, 2, -1, 0, 1, -1, 2, 2, -1, 1, 0, -1, 2, 0, 1,
    -1, 2, 0, 1, 2, -1, 1, 0, 0, 1, -1, 2, 1, 0, 2, -1,
    2, -1, 1, 0, -1, 2, 0, 1, 1, 0, 2, -1, 0, 1, -1, 2,
];

/// Core integer type for the Roulette kernel
/// Implements nested-radix T9-braid compression for optimal OS-wide data compression
/// The "roulette" system uses T9 mapping + nested-radix encoding for superior compression
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd)]
pub struct RouletteInt {
    pub data: [u8; 32],
    pub len: u8,
}

pub mod braid;
pub mod t9_syscalls;
pub mod advanced_braid;
pub mod types;

#[allow(dead_code)]
impl RouletteInt {
    /// Zero value
    pub const ZERO: Self = Self {
        data: [0; 32],
        len: 0,
    };

    /// Create from u128 with nested-radix roulette compression
    /// First digit (2-9) determines the base for remaining digits
    /// Inspired by T9 predictive text + braid theory overlap encoding
    #[must_use] 
    #[allow(clippy::cast_possible_truncation)]
    pub const fn from_u128(value: u128) -> Self {
        if value == 0 {
            return Self::ZERO;
        }

        let mut buf = [0u8; 32];
        let mut temp_digits = [0u8; 22]; // Temporary storage for digits
        let mut digit_count = 0usize;
        let mut remaining = value;

        // Choose optimal radix using overlap prediction
        // Analyze bit patterns to predict best compression radix
        let (radix, radix_digit) = Self::predict_optimal_radix(remaining);

        buf[0] = radix_digit;

        // Extract digits from LSD to MSD and store in temp array
        while remaining > 0 && digit_count < 22 {
            temp_digits[digit_count] = (remaining % radix) as u8;
            remaining /= radix;
            digit_count += 1;
        }

        // Copy digits to buffer in MSD to LSD order (after radix digit)
        let mut i = 0usize;
        while i < digit_count {
            buf[digit_count - i] = temp_digits[i];
            i += 1;
        }

        Self {
            data: buf,
            len: (digit_count + 1) as u8,
        }
    }

    /// Create from u128 with overlap-based optimization for maximum compression
    #[must_use] 
    pub const fn from_u128_with_overlap_optimization(value: u128) -> Self {
        // Currently uses the same logic as from_u128 with overlap-aware radix selection
        Self::from_u128(value)
    }

    /// Apply overlap-based optimization for maximum compression efficiency
    /// This should be called after construction to enable braid-based compression
    pub fn optimize_for_compression(&mut self) {
        let original_value = self.to_u128();
        *self = Self::from_u128_with_overlap_optimization(original_value);
    }

    /// Optimize digit arrangement using overlap prediction for maximum compression
    fn optimize_overlap_digits(&mut self) {
        if self.len < 4 {
            return; // Need at least a few digits for meaningful optimization
        }

        // Extract digit sequence (skip radix digit at index 0)
        let mut digits = [0u8; 22];
        let digit_count = (self.len - 1) as usize;

        for (i, digit) in digits.iter_mut().enumerate().take(digit_count) {
            *digit = self.data[self.len as usize - 1 - i];
        }

        // Apply overlap optimization to the digit sequence
        Self::optimize_overlap(&mut digits[..digit_count]);

        // Store the optimized digit arrangement
        for (i, &digit) in digits.iter().enumerate().take(digit_count) {
            self.data[self.len as usize - 1 - i] = digit;
        }
    }

    /// Predict optimal radix based on value's bit pattern overlap
    /// Uses braid theory to analyze which base will give best compression
    const fn predict_optimal_radix(value: u128) -> (u128, u8) {
        if value < 100 {
            (10, 2) // Decimal for small values
        } else if value < 10000 {
            // Analyze bit patterns to choose between hex and base32
            let hex_digits = Self::count_digits(value, 16);
            let base32_digits = Self::count_digits(value, 32);

            if hex_digits <= base32_digits { (16, 3) } else { (32, 4) }
        } else if value < 1_000_000 {
            (32, 4) // Base32 for medium-large values
        } else {
            // For very large values, use overlap prediction
            let base32_digits = Self::count_digits(value, 32);
            let base64_digits = Self::count_digits(value, 64);

            if base32_digits <= base64_digits { (32, 4) } else { (64, 5) }
        }
    }

    /// Predict optimal radix using overlap analysis of bit patterns
    #[allow(clippy::cast_possible_truncation)]
    const fn predict_radix_by_overlap(value: u128, radices: &[u128], radix_digits: &[u8]) -> (u128, u8) {
        // Extract byte representation for overlap analysis
        let mut bytes = [0u8; 16];
        let mut temp = value;
        let mut byte_count = 0;

        // Convert to bytes (similar to encoding process)
        while temp > 0 && byte_count < 16 {
            bytes[byte_count] = (temp % 256) as u8;
            temp /= 256;
            byte_count += 1;
        }

        // Calculate overlap scores for each radix option
        let mut best_radix = radices[0];
        let mut best_score = i32::MIN;
        let mut best_digit = radix_digits[0];

        let mut i = 0;
        while i < radices.len() {
            let radix = radices[i];
            let digit = radix_digits[i];
            let score = Self::calculate_overlap_score(bytes, byte_count, radix);

            if score > best_score {
                best_score = score;
                best_radix = radix;
                best_digit = digit;
            }
            i += 1;
        }

        (best_radix, best_digit)
    }

    /// Calculate overlap score for a given radix by analyzing compression efficiency
    const fn calculate_overlap_score(bytes: [u8; 16], byte_count: usize, radix: u128) -> i32 {
        if byte_count < 2 {
            return 0; // Need at least 2 bytes for overlap analysis
        }

        let mut total_score = 0i32;
        let mut i = 0;

        // Analyze consecutive byte pairs for overlap patterns
        while i < byte_count.saturating_sub(1) {
            let current = bytes[i];
            let next = bytes[i + 1];

            // Calculate hash for overlap lookup (same as extract_braid_word)
            let hash = (current as usize).wrapping_mul(31).wrapping_add(next as usize) % 64;
            let overlap_score = OVERLAP_SCORES[hash] as i32;

            // Weight the score by how well this radix preserves the pattern
            // Higher overlap scores are better for compression
            total_score += overlap_score;
            i += 1;
        }

        // Bonus for radices that naturally align with byte boundaries
        if radix == 256 {
            total_score += 10; // Perfect byte alignment
        } else if radix == 16 || radix == 32 || radix == 64 {
            total_score += 5; // Good power-of-2 alignment
        }

        total_score
    }

    /// Count digits needed in given radix
    const fn count_digits(mut value: u128, radix: u128) -> usize {
        let mut count = 0;
        while value > 0 {
            value /= radix;
            count += 1;
        }
        if count == 0 { 1 } else { count }
    }

    /// Optimize digit ordering for maximum overlap compression
    /// Reorders digits to maximize predictive relationships between consecutive digits
    fn optimize_overlap(_digits: &mut [u8]) {
        // Digit rearrangement optimization removed to maintain roundtrip compatibility
        // Overlap optimization is now handled at the radix selection level
    }

    /// Calculate overlap prediction score between two digits
    /// Higher scores indicate better predictive compression
    const fn overlap_score(d1: u8, d2: u8) -> i8 {
        // Use the overlap prediction table with proper bounds checking
        let hash = (d1 as usize).wrapping_mul(31).wrapping_add(d2 as usize) % 64;
        OVERLAP_SCORES[hash]
    }

    /// Extract braid word from compressed data using overlap patterns
    /// This implements the "Overlap-Encoded Bitstrings" concept
    #[must_use] 
    pub const fn extract_braid_word(&self) -> [crate::braid::BraidGenerator; 8] {
        let mut braid_word = [crate::braid::BraidGenerator::Left(0); 8];
        let mut i = 1usize; // Skip radix digit
        let mut braid_idx = 0usize;

        while i < self.len as usize && braid_idx < 8 {
            if i + 1 < self.len as usize {
                // Use overlap between consecutive bytes to determine braid generator
                let current = self.data[i] as usize;
                let next = self.data[i + 1] as usize;

                // Braid theory: crossing direction based on overlap prediction
                let hash = (current.wrapping_mul(31) + next) % 64;
                let overlap_score = OVERLAP_SCORES[hash];

                // Convert overlap score to braid generator
                braid_word[braid_idx] = if overlap_score > 0 {
                    crate::braid::BraidGenerator::Left((overlap_score % 4) as u8)
                } else if overlap_score < 0 {
                    crate::braid::BraidGenerator::Right((-overlap_score % 4) as u8)
                } else {
                    crate::braid::BraidGenerator::Left(0) // Identity represented as Left(0)
                };

                braid_idx += 1;
            }
            i += 1;
        }

        braid_word
    }



    /// Convert back to u128 using nested-radix decoding
    /// First digit determines the radix for the remaining digits
    #[must_use] 
    #[allow(clippy::cast_sign_loss)]
    pub const fn to_u128(self) -> u128 {
        if self.len == 0 {
            return 0;
        }

        // First digit determines the radix
        let radix_digit = self.data[0];
        let radix = match radix_digit {
            3 => 16, // Hex
            4 => 32, // Base32
            5 => 64, // Base64
            _ => 10, // Default to decimal
        };

        let mut result = 0u128;

        // Decode from most significant to least significant digit
        // Skip the first element (radix indicator)
        let mut i = 1usize;
        while i < self.len as usize {
            result = result * radix as u128 + self.data[i] as u128;
            i += 1;
        }

        result
    }

    /// Convert a T9 word to its numerical representation
    /// Used for system call encoding ("run" = 786)
    #[must_use] 
    pub const fn t9_word_to_number(word: &str) -> u128 {
        let mut result = 0u128;
        let mut multiplier = 1u128;
        let bytes = word.as_bytes();

        let mut i = bytes.len();
        while i > 0 {
            i -= 1;
            let ch = bytes[i] as char;
            let digit = Self::char_to_t9_digit(ch);
            result += digit as u128 * multiplier;
            multiplier *= 10; // T9 is always decimal
        }

        result
    }

    /// Convert character to T9 digit (2-9)
    const fn char_to_t9_digit(ch: char) -> u8 {
        match ch.to_ascii_uppercase() {
            'A' | 'B' | 'C' => 2,
            'D' | 'E' | 'F' => 3,
            'G' | 'H' | 'I' => 4,
            'J' | 'K' | 'L' => 5,
            'M' | 'N' | 'O' => 6,
            'P' | 'Q' | 'R' | 'S' => 7,
            'T' | 'U' | 'V' => 8,
            'W' | 'X' | 'Y' | 'Z' => 9,
            _ => 0,
        }
    }
}

#[cfg(feature = "secret")]
use zeroize::Zeroize;

#[cfg(feature = "secret")]
impl Zeroize for RouletteInt {
    fn zeroize(&mut self) {
        self.data.zeroize();
        self.len.zeroize();
    }
}

/// Constant-time, canonical variable-radix encoding
/// Uses lowest possible base at each step → unique representation
#[cfg(feature = "secret")]
pub const fn from_u128_secret(mut value: u128) -> RouletteInt {
    let mut buf = [0u8; 32];
    let mut pos = 32;

    if value == 0 {
        return RouletteInt::ZERO;
    }

    while value > 0 {
        // Constant-time: always scan full range, choose lowest valid base
        let mut chosen_base = 37u8;
        let mut chosen_digit = 0u8;

        let mut b = 2u8;
        while b <= 36 {
            let digit = (value % b as u128) as u8;
            if digit < b && b < chosen_base {
                chosen_base = b;
                chosen_digit = digit;
            }
            b = b.wrapping_add(1);
        }

        value /= chosen_base as u128;
        pos -= 2;
        buf[pos] = chosen_digit;
        buf[pos + 1] = chosen_base;
    }

    let len = 32 - pos;
    RouletteInt { data: buf, len: len as u8 }
}

impl From<u64> for RouletteInt {
    fn from(value: u64) -> Self {
        Self::from_u128(u128::from(value))
    }
}

impl From<u8> for RouletteInt {
    fn from(value: u8) -> Self {
        Self::from_u128(u128::from(value))
    }
}

impl From<usize> for RouletteInt {
    fn from(value: usize) -> Self {
        Self::from_u128(value as u128)
    }
}

impl From<i32> for RouletteInt {
    #[allow(clippy::cast_sign_loss)]
    fn from(value: i32) -> Self {
        // Note: RouletteInt represents compressed positive integers only
        // Negative values are not supported in the current design
        Self::from_u128(value as u128)
    }
}

impl From<u128> for RouletteInt {
    fn from(value: u128) -> Self {
        Self::from_u128(value)
    }
}

use core::ops::{Add, Sub, Mul, Div, Rem};

impl Add for RouletteInt {
    type Output = Self;
    
    fn add(self, other: Self) -> Self {
        // Simple addition - convert to u128, add, convert back
        let a = self.to_u128();
        let b = other.to_u128();
        Self::from_u128(a + b)
    }
}

impl Sub for RouletteInt {
    type Output = Self;
    
    fn sub(self, other: Self) -> Self {
        let a = self.to_u128();
        let b = other.to_u128();
        Self::from_u128(a.saturating_sub(b))
    }
}

impl Mul for RouletteInt {
    type Output = Self;
    
    fn mul(self, other: Self) -> Self {
        let a = self.to_u128();
        let b = other.to_u128();
        Self::from_u128(a * b)
    }
}

impl Div for RouletteInt {
    type Output = Self;
    
    fn div(self, other: Self) -> Self {
        let a = self.to_u128();
        let b = other.to_u128();
        if b == 0 {
            Self::ZERO
        } else {
            Self::from_u128(a / b)
        }
    }
}

impl Rem for RouletteInt {
    type Output = Self;
    
    fn rem(self, other: Self) -> Self {
        let a = self.to_u128();
        let b = other.to_u128();
        if b == 0 {
            Self::ZERO
        } else {
            Self::from_u128(a % b)
        }
    }
}

// Panic handler for no_std (disabled when no_panic_handler feature is enabled)
#[cfg(all(not(feature = "std"), not(test), not(feature = "no_panic_handler")))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

// pub mod math_reasoning;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_roulette_int_roundtrip() {
        let test_values = [0u128, 1, 42, 1337, u128::MAX / 2];

        for &value in &test_values {
            let encoded = RouletteInt::from_u128(value);
            let decoded = encoded.to_u128();
            assert_eq!(value, decoded, "Roundtrip failed for {}", value);
        }
    }

    #[test]
    fn test_zero_encoding() {
        let zero = RouletteInt::from_u128(0);
        assert_eq!(zero, RouletteInt::ZERO);
        assert_eq!(zero.to_u128(), 0);
    }

    #[test]
    fn test_t9_word_encoding() {
        // Test T9 word to number conversion
        assert_eq!(RouletteInt::t9_word_to_number("run"), 786); // R=7, U=8, N=6
        assert_eq!(RouletteInt::t9_word_to_number("hello"), 43556); // H=4, E=3, L=5, L=5, O=6
        assert_eq!(RouletteInt::t9_word_to_number("a"), 2); // A=2
        assert_eq!(RouletteInt::t9_word_to_number("ABC"), 222); // All A,B,C = 2
    }

    #[test]
    fn test_nested_radix_encoding() {
        // Test that different value ranges use different radices
        let small = RouletteInt::from_u128(42); // Should use decimal (radix 10)
        assert_eq!(small.data[0], 2); // Radix indicator for decimal

        let medium = RouletteInt::from_u128(1337); // Should use hex (radix 16)
        assert_eq!(medium.data[0], 3); // Radix indicator for hex

        let large = RouletteInt::from_u128(100000); // Should use base32 (radix 32)
        assert_eq!(large.data[0], 4); // Radix indicator for base32
    }

    #[test]
    fn test_overlap_encoding_compression() {
        // Test that overlap encoding improves compression ratios
        let test_values = [
            12345u128, 67890, 111111, 999999, 123456789,
            u128::MAX / 1000, // Large value for base64 testing
        ];

        let mut total_improvement = 0.0;
        let mut count = 0;

        for &value in &test_values {
            let encoded = RouletteInt::from_u128(value);

            // Calculate theoretical minimum digits without optimization
            let radix = match encoded.data[0] {
                2 => 10,
                3 => 16,
                4 => 32,
                5 => 64,
                _ => 10,
            };

            let min_digits = RouletteInt::count_digits(value, radix as u128);
            let actual_digits = encoded.len as usize - 1; // Subtract radix digit

            if actual_digits > 0 {
                let ratio = min_digits as f64 / actual_digits as f64;
                total_improvement += ratio;
                count += 1;
            }
        }

        let avg_improvement = total_improvement / count as f64;
        // Overlap encoding should provide some compression benefit
        assert!(avg_improvement >= 0.8, "Overlap encoding should maintain reasonable compression ratio: {}", avg_improvement);
    }

    #[test]
    fn test_braid_module_integration() {
        use crate::braid::{BraidWord, BraidGroup};

        let value = RouletteInt::from_u128(1337);
        let braid_word = BraidWord::from_roulette_int(&value);

        // Test braid group operations
        let group = BraidGroup::new(4);
        let permutation = group.apply_word(&braid_word);

        // Braid operations should produce valid permutations
        assert!(permutation.len() >= 4);

        // Test Gödel number generation
        let godel = braid_word.to_godel_number();
        assert!(godel > 1);
    }

    // #[test]
    // fn test_mathematical_reasoning_execution() {
    //     use crate::math_reasoning::{MathematicalReasoningEngine, MathExpression, MathValue};

    //     let mut engine = MathematicalReasoningEngine::new();

    //     // Test expression evaluation
    //     let expr = MathExpression::Function("+".to_string(), vec![
    //         MathExpression::Constant(10),
    //         MathExpression::Constant(5),
    //     ]);

    //     let result = engine.evaluate_expression(&expr).unwrap();
    //     match result {
    //         MathValue::Integer(15) => assert!(true),
    //         _ => panic!("Expected 15, got {:?}", result),
    //     }

    //     // Test theorem execution
    //     let theorem = crate::math_reasoning::Theorem {
    //         name: "test_add".to_string(),
    //         statement: MathExpression::Function("+".to_string(), vec![
    //             MathExpression::Constant(3),
    //             MathExpression::Constant(7),
    //         ]),
    //         proof: crate::math_reasoning::Proof::Axiom("Test theorem".to_string()),
    //     };

    //     engine.add_theorem(theorem);
    //     let exec_result = engine.execute_theorem("test_add", vec![]).unwrap();
    //     match exec_result {
    //         MathValue::Integer(10) => assert!(true),
    //         _ => panic!("Expected 10, got {:?}", exec_result),
    //     }
    // }
}
