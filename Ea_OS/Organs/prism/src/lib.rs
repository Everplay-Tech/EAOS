//! # Ea Prism - Secure Capsule Decryption Organ
//!
//! Prism accepts encrypted IHP capsules, decrypts them, and executes
//! the contained Quenyan bytecode payload.
//!
//! ## Architecture
//!
//! ```text
//! IhpCapsule (encrypted)
//!      │
//!      ▼
//! ┌─────────────┐
//! │   PRISM     │
//! │  Decryptor  │
//! └──────┬──────┘
//!        │
//!        ▼
//! ┌─────────────┐
//! │  Quenyan    │
//! │     VM      │
//! └──────┬──────┘
//!        │
//!        ▼
//!   ExecutionResult
//! ```
//!
//! ## Security
//!
//! - Uses IHP's AES-256-GCM AEAD encryption
//! - Tampered capsules return `PrismError::InvalidCapsule`
//! - Keys are zeroized on drop

#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;

use alloc::string::String;
use alloc::vec::Vec;

use ea_symbiote::{BlobType, SovereignDocument};
use ihp::{
    decrypt_capsule, CapsuleTimestamp, IhpCapsule, IhpConfig, IhpError,
    ServerEnvHash, SessionKey,
};

// =============================================================================
// Prism Error Types
// =============================================================================

/// Errors that can occur during Prism operations.
#[derive(Debug, Clone)]
pub enum PrismError {
    /// IHP decryption failed (tampered, wrong key, etc.)
    InvalidCapsule(String),
    /// Quenyan bytecode validation failed
    InvalidBytecode(String),
    /// VM execution failed
    ExecutionFailed(String),
    /// Configuration error
    ConfigError(String),
}

impl From<IhpError> for PrismError {
    fn from(err: IhpError) -> Self {
        match err {
            IhpError::InvalidAeadTag => PrismError::InvalidCapsule("AEAD tag mismatch - capsule tampered".into()),
            IhpError::HeaderIdMismatch => PrismError::InvalidCapsule("HeaderID mismatch".into()),
            IhpError::StaleTimestamp => PrismError::InvalidCapsule("Timestamp too old".into()),
            IhpError::InvalidVersion => PrismError::InvalidCapsule("Unknown protocol version".into()),
            IhpError::Codec(msg) => PrismError::InvalidCapsule(msg),
            IhpError::Config(msg) => PrismError::ConfigError(msg),
            other => PrismError::InvalidCapsule(alloc::format!("{:?}", other)),
        }
    }
}

// =============================================================================
// Quenyan VM - Bytecode Executor
// =============================================================================

/// Magic bytes for Quenyan bytecode (QYN1)
pub const QUENYAN_MAGIC: [u8; 4] = [0x51, 0x59, 0x4E, 0x31]; // "QYN1"

/// Result of Quenyan bytecode execution.
#[derive(Debug, Clone)]
pub struct ExecutionResult {
    /// Whether execution completed successfully
    pub success: bool,
    /// Output value (if any)
    pub output: Option<Vec<u8>>,
    /// Execution steps taken
    pub steps: u64,
    /// Hash of execution state
    pub state_hash: [u8; 32],
}

impl SovereignDocument for ExecutionResult {
    fn blob_type(&self) -> BlobType {
        BlobType::Record
    }

    fn to_bytes(&self) -> Vec<u8> {
        let mut buf = Vec::with_capacity(64);
        buf.push(if self.success { 1 } else { 0 });
        buf.extend_from_slice(&self.steps.to_le_bytes());
        buf.extend_from_slice(&self.state_hash);
        if let Some(ref output) = self.output {
            buf.extend_from_slice(&(output.len() as u32).to_le_bytes());
            buf.extend_from_slice(output);
        }
        buf
    }

    fn from_bytes(data: &[u8]) -> Option<Self>
    where
        Self: Sized,
    {
        if data.len() < 41 {
            return None;
        }
        let success = data[0] == 1;
        let steps = u64::from_le_bytes(data[1..9].try_into().ok()?);
        let state_hash: [u8; 32] = data[9..41].try_into().ok()?;
        let output = if data.len() > 45 {
            let len = u32::from_le_bytes(data[41..45].try_into().ok()?) as usize;
            if data.len() >= 45 + len {
                Some(data[45..45 + len].to_vec())
            } else {
                None
            }
        } else {
            None
        };
        Some(Self {
            success,
            output,
            steps,
            state_hash,
        })
    }
}

/// Quenyan Virtual Machine for bytecode execution.
///
/// The VM executes Quenyan bytecode extracted from IHP capsules.
/// It provides a sandboxed execution environment with:
/// - Step limiting for gas-like execution bounds
/// - State hashing for verifiable execution
/// - Output capture for result extraction
pub struct QuenyanVM {
    /// Maximum execution steps allowed
    max_steps: u64,
    /// Current step counter
    current_step: u64,
    /// VM state
    state: Vec<u8>,
}

impl Default for QuenyanVM {
    fn default() -> Self {
        Self::new()
    }
}

impl QuenyanVM {
    /// Create a new Quenyan VM with default configuration.
    pub fn new() -> Self {
        Self {
            max_steps: 1_000_000,
            current_step: 0,
            state: Vec::new(),
        }
    }

    /// Create a VM with custom step limit.
    pub fn with_max_steps(max_steps: u64) -> Self {
        Self {
            max_steps,
            current_step: 0,
            state: Vec::new(),
        }
    }

    /// Validate Quenyan bytecode format.
    pub fn validate_bytecode(bytecode: &[u8]) -> Result<(), PrismError> {
        if bytecode.len() < 4 {
            return Err(PrismError::InvalidBytecode("bytecode too short".into()));
        }

        if &bytecode[0..4] != &QUENYAN_MAGIC {
            return Err(PrismError::InvalidBytecode("invalid magic bytes".into()));
        }

        Ok(())
    }

    /// Execute Quenyan bytecode.
    ///
    /// Returns execution result including output and state hash.
    pub fn execute(&mut self, bytecode: &[u8]) -> Result<ExecutionResult, PrismError> {
        // Validate bytecode format
        Self::validate_bytecode(bytecode)?;

        // Initialize state with bytecode
        self.state = bytecode.to_vec();
        self.current_step = 0;

        // Execute bytecode (simplified execution model)
        // Real implementation would interpret opcodes
        let output = self.run_program(&bytecode[4..])?;

        // Compute state hash
        let state_hash = blake3::hash(&self.state).into();

        Ok(ExecutionResult {
            success: true,
            output: Some(output),
            steps: self.current_step,
            state_hash,
        })
    }

    /// Internal program runner (simplified).
    fn run_program(&mut self, program: &[u8]) -> Result<Vec<u8>, PrismError> {
        // Simplified execution: each byte is a "step"
        // Real implementation would decode and execute opcodes
        for &byte in program {
            self.current_step += 1;
            if self.current_step > self.max_steps {
                return Err(PrismError::ExecutionFailed("step limit exceeded".into()));
            }

            // Simple state accumulation
            self.state.push(byte ^ 0xAA);
        }

        // Return the transformed state as output
        Ok(self.state.clone())
    }

    /// Reset VM state for next execution.
    pub fn reset(&mut self) {
        self.current_step = 0;
        self.state.clear();
    }
}

// =============================================================================
// Prism Decryptor
// =============================================================================

/// Configuration for Prism operations.
#[derive(Debug, Clone)]
pub struct PrismConfig {
    /// IHP configuration for decryption
    pub ihp_config: IhpConfig,
    /// Maximum bytecode size to accept
    pub max_bytecode_size: usize,
    /// Maximum VM execution steps
    pub max_vm_steps: u64,
}

impl Default for PrismConfig {
    fn default() -> Self {
        Self {
            ihp_config: IhpConfig::default(),
            max_bytecode_size: 1024 * 1024, // 1MB
            max_vm_steps: 1_000_000,
        }
    }
}

/// Prism Organ - Secure capsule decryption and bytecode execution.
pub struct Prism {
    config: PrismConfig,
    vm: QuenyanVM,
}

impl Default for Prism {
    fn default() -> Self {
        Self::new()
    }
}

impl Prism {
    /// Create a new Prism with default configuration.
    pub fn new() -> Self {
        Self {
            config: PrismConfig::default(),
            vm: QuenyanVM::new(),
        }
    }

    /// Create Prism with custom configuration.
    pub fn with_config(config: PrismConfig) -> Self {
        Self {
            vm: QuenyanVM::with_max_steps(config.max_vm_steps),
            config,
        }
    }

    /// Decrypt an IHP capsule and execute its Quenyan bytecode payload.
    ///
    /// # Arguments
    ///
    /// * `capsule` - The encrypted IHP capsule
    /// * `server_env_hash` - Server environment hash
    /// * `session_key` - Pre-derived session key for decryption
    /// * `timestamp` - Current timestamp for replay protection
    ///
    /// # Returns
    ///
    /// `ExecutionResult` on success, `PrismError` on failure.
    ///
    /// # Errors
    ///
    /// - `PrismError::InvalidCapsule` - Capsule tampered or wrong key (IhpError::InvalidAeadTag)
    /// - `PrismError::InvalidBytecode` - Payload is not valid Quenyan bytecode
    /// - `PrismError::ExecutionFailed` - VM execution failed
    pub fn decrypt_and_execute(
        &mut self,
        capsule: &IhpCapsule,
        server_env_hash: &ServerEnvHash,
        session_key: &SessionKey,
        timestamp: CapsuleTimestamp,
    ) -> Result<ExecutionResult, PrismError> {
        // Decrypt the capsule
        let plaintext = decrypt_capsule(
            capsule,
            server_env_hash,
            session_key,
            timestamp,
            &self.config.ihp_config,
        )?;

        // Extract bytecode from payload
        let bytecode = plaintext.password_material.as_slice();

        // Validate bytecode size
        if bytecode.len() > self.config.max_bytecode_size {
            return Err(PrismError::InvalidBytecode("bytecode too large".into()));
        }

        // Reset VM and execute
        self.vm.reset();
        self.vm.execute(bytecode)
    }

    /// Validate a capsule without executing (dry run).
    ///
    /// Decrypts and validates bytecode format but doesn't execute.
    pub fn validate_capsule(
        &self,
        capsule: &IhpCapsule,
        server_env_hash: &ServerEnvHash,
        session_key: &SessionKey,
        timestamp: CapsuleTimestamp,
    ) -> Result<(), PrismError> {
        let plaintext = decrypt_capsule(
            capsule,
            server_env_hash,
            session_key,
            timestamp,
            &self.config.ihp_config,
        )?;

        // Just validate bytecode format
        QuenyanVM::validate_bytecode(plaintext.password_material.as_slice())
    }

    /// Get reference to the VM.
    pub fn vm(&self) -> &QuenyanVM {
        &self.vm
    }

    /// Get mutable reference to the VM.
    pub fn vm_mut(&mut self) -> &mut QuenyanVM {
        &mut self.vm
    }

    /// Get reference to the configuration.
    pub fn config(&self) -> &PrismConfig {
        &self.config
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_quenyan_magic() {
        assert_eq!(&QUENYAN_MAGIC, b"QYN1");
    }

    #[test]
    fn test_vm_creation() {
        let vm = QuenyanVM::new();
        assert_eq!(vm.max_steps, 1_000_000);
        assert_eq!(vm.current_step, 0);
    }

    #[test]
    fn test_bytecode_validation_short() {
        let result = QuenyanVM::validate_bytecode(&[0x51, 0x59]);
        assert!(matches!(result, Err(PrismError::InvalidBytecode(_))));
    }

    #[test]
    fn test_bytecode_validation_wrong_magic() {
        let result = QuenyanVM::validate_bytecode(&[0x00, 0x00, 0x00, 0x00, 0x01, 0x02]);
        assert!(matches!(result, Err(PrismError::InvalidBytecode(_))));
    }

    #[test]
    fn test_bytecode_validation_success() {
        let mut bytecode = QUENYAN_MAGIC.to_vec();
        bytecode.extend_from_slice(&[0x01, 0x02, 0x03]);
        let result = QuenyanVM::validate_bytecode(&bytecode);
        assert!(result.is_ok());
    }

    #[test]
    fn test_vm_execute() {
        let mut vm = QuenyanVM::new();
        let mut bytecode = QUENYAN_MAGIC.to_vec();
        bytecode.extend_from_slice(&[0x10, 0x20, 0x30]);

        let result = vm.execute(&bytecode);
        assert!(result.is_ok());

        let exec_result = result.unwrap();
        assert!(exec_result.success);
        assert_eq!(exec_result.steps, 3);
        assert!(exec_result.output.is_some());
    }

    #[test]
    fn test_vm_step_limit() {
        let mut vm = QuenyanVM::with_max_steps(2);
        let mut bytecode = QUENYAN_MAGIC.to_vec();
        bytecode.extend_from_slice(&[0x01, 0x02, 0x03, 0x04, 0x05]);

        let result = vm.execute(&bytecode);
        assert!(matches!(result, Err(PrismError::ExecutionFailed(_))));
    }

    #[test]
    fn test_execution_result_serialization() {
        let result = ExecutionResult {
            success: true,
            output: Some(vec![0x01, 0x02, 0x03]),
            steps: 42,
            state_hash: [0xAB; 32],
        };

        let bytes = result.to_bytes();
        let recovered = ExecutionResult::from_bytes(&bytes).unwrap();

        assert_eq!(recovered.success, result.success);
        assert_eq!(recovered.steps, result.steps);
        assert_eq!(recovered.state_hash, result.state_hash);
    }

    #[test]
    fn test_prism_creation() {
        let prism = Prism::new();
        assert_eq!(prism.config.max_vm_steps, 1_000_000);
    }

    #[test]
    fn test_prism_error_from_ihp_aead() {
        let ihp_err = IhpError::InvalidAeadTag;
        let prism_err: PrismError = ihp_err.into();
        match prism_err {
            PrismError::InvalidCapsule(msg) => {
                assert!(msg.contains("AEAD") || msg.contains("tampered"));
            }
            _ => panic!("Expected InvalidCapsule"),
        }
    }

    #[test]
    fn test_prism_error_from_ihp_header() {
        let ihp_err = IhpError::HeaderIdMismatch;
        let prism_err: PrismError = ihp_err.into();
        match prism_err {
            PrismError::InvalidCapsule(msg) => {
                assert!(msg.contains("HeaderID"));
            }
            _ => panic!("Expected InvalidCapsule"),
        }
    }
}
