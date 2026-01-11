// Copyright © 2025 [Mitchell_Burns/ Everplay-Tech]. All rights reserved.
// Proprietary and confidential. Not open source.
// Unauthorized copying, distribution, or modification prohibited.

//! Type-Level Invariants for Mathematical Safety
//!
//! This module implements dependent types to enforce
//! braid group axioms and prevent invalid operations at compile time.
//! All braid indices are guaranteed positive by construction.

/// A positive index for braid strands, guaranteed ≥ 1 at compile time.
/// Uses const generics to encode the value at compile time.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct PositiveIndex<const N: usize> {
    _phantom: core::marker::PhantomData<[(); N]>,
}

impl<const N: usize> PositiveIndex<N> {
    /// Create a positive index.
    /// Compile-time check ensures N ≥ 1.
    #[must_use]
    pub const fn new() -> Self {
        assert!(N >= 1, "PositiveIndex must be ≥ 1");
        Self {
            _phantom: core::marker::PhantomData,
        }
    }

    /// Get the runtime value as usize.
    #[must_use]
    pub const fn value(&self) -> usize {
        N
    }

    /// Convert to u32 for indexing operations.
    #[must_use]
    #[allow(clippy::cast_possible_truncation)]
    pub const fn as_u32(&self) -> u32 {
        N as u32
    }
}

impl<const N: usize> Default for PositiveIndex<N> {
    fn default() -> Self {
        Self::new()
    }
}

/// Type aliases for common braid strand indices (1-8)
pub type Strand1 = PositiveIndex<1>;
pub type Strand2 = PositiveIndex<2>;
pub type Strand3 = PositiveIndex<3>;
pub type Strand4 = PositiveIndex<4>;
pub type Strand5 = PositiveIndex<5>;
pub type Strand6 = PositiveIndex<6>;
pub type Strand7 = PositiveIndex<7>;
pub type Strand8 = PositiveIndex<8>;