// Copyright © 2025 [Mitchell_Burns/ Everplay-Tech]. All rights reserved.
// Proprietary and confidential. Not open source.
// Unauthorized copying, distribution, or modification prohibited.

/// T9 SYSTEM CALL ALGEBRA FOR ROULETTE KERNEL
///
/// System calls implemented as T9 words that select braid generators.
/// Each system call is encoded as a telephone keypad sequence that
/// maps to specific braid operations for execution.
///
/// Examples:
/// - "run" = 786 → `BraidGenerator::Left(1)` + `BraidGenerator::Right(2)`
/// - "open" = 6736 → `BraidGenerator::Left(3)` + `BraidGenerator::Right(1)`
/// - "read" = 7323 → `BraidGenerator::Right(2)` + `BraidGenerator::Left(1)`
///
/// System call numbers (traditional enum for compatibility)
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum SystemCall {
    Run = 1,
    Open = 2,
    Read = 3,
    Write = 4,
    Close = 5,
    Exit = 6,
    Fork = 7,
    Exec = 8,
    Wait = 9,
    Kill = 10,
}

/// T9 word to system call mapping
pub const T9_SYSTEM_CALLS: &[(&str, SystemCall, &[BraidGenerator])] = &[
    ("run", SystemCall::Run, &[BraidGenerator::Left(1), BraidGenerator::Right(2)]),
    ("open", SystemCall::Open, &[BraidGenerator::Left(3), BraidGenerator::Right(1)]),
    ("read", SystemCall::Read, &[BraidGenerator::Right(2), BraidGenerator::Left(1)]),
    ("write", SystemCall::Write, &[BraidGenerator::Left(2), BraidGenerator::Right(3)]),
    ("close", SystemCall::Close, &[BraidGenerator::Right(1), BraidGenerator::Left(3)]),
    ("exit", SystemCall::Exit, &[BraidGenerator::Left(4), BraidGenerator::Right(4)]),
    ("fork", SystemCall::Fork, &[BraidGenerator::Right(3), BraidGenerator::Left(2)]),
    ("exec", SystemCall::Exec, &[BraidGenerator::Left(1), BraidGenerator::Right(4)]),
    ("wait", SystemCall::Wait, &[BraidGenerator::Right(4), BraidGenerator::Left(1)]),
    ("kill", SystemCall::Kill, &[BraidGenerator::Left(3), BraidGenerator::Right(2)]),
];

use crate::{RouletteInt, braid::{BraidWord, BraidGenerator}};

/// T9 System Call Interpreter
pub struct T9SyscallInterpreter;

impl T9SyscallInterpreter {
    /// Convert T9 word to system call braid word
    #[must_use] 
    pub fn word_to_syscall_braid(word: &str) -> Option<BraidWord> {
        // Convert word to T9 number
        let t9_number = RouletteInt::t9_word_to_number(word);

        // Find matching system call
        for (syscall_word, _syscall, braid_generators) in T9_SYSTEM_CALLS {
            if RouletteInt::t9_word_to_number(syscall_word) == t9_number {
                let mut generators = [BraidGenerator::Left(0); 16];
                let length: usize = braid_generators.len().min(16);

                generators[..length].copy_from_slice(&braid_generators[..length]);

                return Some(BraidWord { generators, length, _homotopy: core::marker::PhantomData });
            }
        }

        None
    }

    /// Execute system call from T9 word
    ///
    /// # Errors
    /// Returns `T9SyscallError::UnknownSyscall` if the T9 word does not correspond to a valid system call.
    /// Returns `T9SyscallError::InvalidFormat` if the T9 word format is invalid.
    pub fn execute_t9_syscall(word: &str) -> Result<SystemCallResult, T9SyscallError> {
        let _braid_word = Self::word_to_syscall_braid(word)
            .ok_or(T9SyscallError::UnknownSyscall)?;

        // Find the system call
        let t9_number = RouletteInt::t9_word_to_number(word);
        let mut syscall = None;

        for (syscall_word, sys, _) in T9_SYSTEM_CALLS {
            if RouletteInt::t9_word_to_number(syscall_word) == t9_number {
                syscall = Some(*sys);
                break;
            }
        }

        match syscall {
            Some(SystemCall::Exit) => Ok(SystemCallResult::Exit),
            // Add more system call implementations as needed
            _ => Ok(SystemCallResult::Success(0)), // Placeholder
        }
    }

    /// Validate T9 word format
    ///
    /// # Errors
    /// Returns `T9SyscallError::EmptyWord` if the word is empty.
    /// Returns `T9SyscallError::InvalidCharacter` if the word contains non-alphabetic characters.
    pub fn validate_t9_word(word: &str) -> Result<(), T9SyscallError> {
        if word.is_empty() {
            return Err(T9SyscallError::EmptyWord);
        }

        for ch in word.chars() {
            if !ch.is_ascii_alphabetic() {
                return Err(T9SyscallError::InvalidCharacter);
            }
        }

        Ok(())
    }
}

/// System call execution results
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum SystemCallResult {
    Success(u64),
    Exit,
    Error(i32),
}

/// T9 system call errors
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum T9SyscallError {
    UnknownSyscall,
    EmptyWord,
    InvalidCharacter,
    ExecutionFailed,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_t9_word_to_syscall_braid() {
        let braid_word = T9SyscallInterpreter::word_to_syscall_braid("run");
        assert!(braid_word.is_some());

        let word = braid_word.unwrap();
        assert_eq!(word.length, 2);
        assert_eq!(word.generators[0], BraidGenerator::Left(1));
        assert_eq!(word.generators[1], BraidGenerator::Right(2));
    }

    #[test]
    fn test_t9_syscall_execution() {
        let result = T9SyscallInterpreter::execute_t9_syscall("run");
        assert!(result.is_ok());

        let result = T9SyscallInterpreter::execute_t9_syscall("exit");
        assert_eq!(result, Ok(SystemCallResult::Exit));
    }

    #[test]
    fn test_t9_validation() {
        assert!(T9SyscallInterpreter::validate_t9_word("run").is_ok());
        assert!(T9SyscallInterpreter::validate_t9_word("").is_err());
        assert!(T9SyscallInterpreter::validate_t9_word("run123").is_err());
    }

    #[test]
    fn test_unknown_syscall() {
        let result = T9SyscallInterpreter::execute_t9_syscall("unknown");
        assert!(result.is_err());
    }

    /// RIGOROUS TEST: T9 Collision Resistance
    /// Validates that the T9 encoding is injective (no collisions)
    /// Property: ∀ syscall₁ ≠ syscall₂: T9(syscall₁) ≠ T9(syscall₂)
    #[test]
    fn test_t9_collision_resistance() {
        use std::collections::HashMap;

        let mut t9_to_syscall: HashMap<u128, SystemCall> = HashMap::new();

        // Verify each syscall has a unique T9 encoding
        for (word, syscall, _) in T9_SYSTEM_CALLS {
            let t9_number = RouletteInt::t9_word_to_number(word);

            // Check if this T9 number was already used
            if let Some(existing_syscall) = t9_to_syscall.get(&t9_number) {
                panic!(
                    "T9 COLLISION DETECTED!\n\
                     Syscall {:?} (word: {}) has same T9 code {} as {:?}\n\
                     This breaks injectivity and causes ambiguous syscall dispatch!",
                    syscall, word, t9_number, existing_syscall
                );
            }

            t9_to_syscall.insert(t9_number, *syscall);
        }

        // Verify we have all 10 syscalls with unique T9 codes
        assert_eq!(
            t9_to_syscall.len(),
            T9_SYSTEM_CALLS.len(),
            "T9 collision resistance violated: expected {} unique encodings, got {}",
            T9_SYSTEM_CALLS.len(),
            t9_to_syscall.len()
        );

        // Additional check: verify braid generators for duplicates
        // (Some may be the same, which is OK if T9 codes differ)
        for i in 0..T9_SYSTEM_CALLS.len() {
            for j in (i+1)..T9_SYSTEM_CALLS.len() {
                let (word1, syscall1, gens1) = T9_SYSTEM_CALLS[i];
                let (word2, syscall2, gens2) = T9_SYSTEM_CALLS[j];

                if gens1 == gens2 {
                    eprintln!(
                        "NOTE: Syscall {:?} (word: {}) has identical braid generators as {:?} (word: {})\n\
                         This is safe because T9 codes are unique, but may indicate duplicate patterns.",
                        syscall1, word1, syscall2, word2
                    );
                }
            }
        }
    }
}