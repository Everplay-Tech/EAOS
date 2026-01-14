//! PermFS Bridge - Syscall-to-Storage Translation Layer
//!
//! This crate provides the bridge between the Referee Kernel's syscall interface
//! and the PermFS storage layer. It translates syscall requests into PermFS
//! operations while maintaining the 256-bit addressing scheme.
//!
//! ## Braid Transformation
//!
//! Write operations pass through the T9-Braid transformer before storage,
//! providing 30-70% compression using nested-radix encoding and braid theory.
//!
//! ## Dr-Lex Governance (Stage 6)
//!
//! When the `governance` feature is enabled, all write operations are audited
//! against the Healthcare Constitution before being committed to storage.

#![cfg_attr(not(feature = "std"), no_std)]

#[cfg(feature = "governance")]
use dr_lex::{audit_data_write, is_ethically_corrupt};

// Full permfs support when std feature is enabled
#[cfg(feature = "std")]
use permfs::{BlockAddr as PermFsBlockAddr, BlockDevice, BLOCK_SIZE};

// Minimal definitions for UEFI builds without permfs
#[cfg(not(feature = "std"))]
pub const BLOCK_SIZE: usize = 4096;

use roulette_rs::{BraidTransformer, T9BraidTransformer};

/// Syscall-compatible 256-bit block address.
/// Matches the layout defined in referee-kernel/src/syscall.rs
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SyscallBlockAddr {
    pub high: u128,
    pub low: u128,
}

#[cfg(feature = "std")]
impl SyscallBlockAddr {
    /// Convert from syscall format to PermFS BlockAddr.
    pub fn to_permfs_addr(&self) -> PermFsBlockAddr {
        let node_id = (self.high >> 64) as u64;
        let volume_id = ((self.high >> 32) & 0xFFFF_FFFF) as u32;
        let shard_id = ((self.high >> 16) & 0xFFFF) as u16;
        let block_offset = (self.low >> 80) as u64;

        PermFsBlockAddr::new(node_id, volume_id, shard_id, block_offset)
    }

    /// Convert from PermFS BlockAddr to syscall format.
    pub fn from_permfs_addr(addr: PermFsBlockAddr) -> Self {
        let high = ((addr.node_id() as u128) << 64)
            | ((addr.volume_id() as u128) << 32)
            | ((addr.shard_id() as u128) << 16);
        let low = (addr.block_offset() as u128) << 80;
        Self { high, low }
    }
}

/// Result codes matching syscall.rs SyscallResult.
#[repr(i64)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BridgeResult {
    Success = 0,
    InvalidAddress = -2,
    IoError = -3,
    PermissionDenied = -4,
    InvalidBuffer = -6,
    /// Dr-Lex audit blocked the write (ethically corrupt data)
    AuditBlocked = -10,
}

/// Configuration for braid transformation
#[derive(Debug, Clone, Copy)]
pub struct BraidConfig {
    /// Enable braid compression on writes
    pub compress_writes: bool,
    /// Minimum compression ratio to accept (0.0 - 1.0)
    pub min_compression_ratio: f32,
}

impl Default for BraidConfig {
    fn default() -> Self {
        Self {
            compress_writes: true,
            min_compression_ratio: 0.7, // Only compress if we get 30%+ reduction
        }
    }
}

/// Bridge state holding the PermFS device reference and braid transformer.
/// Only available when std feature is enabled (requires full permfs).
#[cfg(feature = "std")]
pub struct PermFsBridge<D: BlockDevice> {
    device: D,
    node_id: u64,
    volume_id: u32,
    transformer: T9BraidTransformer,
    config: BraidConfig,
}

#[cfg(feature = "std")]
impl<D: BlockDevice> PermFsBridge<D> {
    /// Create a new bridge with the given block device.
    pub fn new(device: D, node_id: u64, volume_id: u32) -> Self {
        Self {
            device,
            node_id,
            volume_id,
            transformer: T9BraidTransformer::new(),
            config: BraidConfig::default(),
        }
    }

    /// Create bridge with custom braid configuration
    pub fn with_config(device: D, node_id: u64, volume_id: u32, config: BraidConfig) -> Self {
        Self {
            device,
            node_id,
            volume_id,
            transformer: T9BraidTransformer::new(),
            config,
        }
    }

    /// Apply braid transformation to data before writing
    fn transform_for_write(&self, data: &[u8; BLOCK_SIZE]) -> (bool, [u8; BLOCK_SIZE]) {
        if !self.config.compress_writes {
            return (false, *data);
        }

        let result = self.transformer.transform(data);

        // Only use compression if it meets our ratio threshold
        if result.ratio <= self.config.min_compression_ratio {
            // Pack compressed data with header
            let mut output = [0u8; BLOCK_SIZE];

            // Header: magic (2 bytes) + compressed_len (2 bytes) + godel_low (8 bytes)
            output[0] = 0xB8; // Magic: "B8AD" for Braid
            output[1] = 0xAD;
            output[2] = (result.compressed_len >> 8) as u8;
            output[3] = result.compressed_len as u8;

            // Store lower 64 bits of Gödel number for verification
            let godel_bytes = (result.godel_number as u64).to_le_bytes();
            output[4..12].copy_from_slice(&godel_bytes);

            // Copy compressed data
            let data_start = 12;
            let copy_len = result.compressed_len.min(BLOCK_SIZE - data_start);
            output[data_start..data_start + copy_len]
                .copy_from_slice(&result.data[..copy_len]);

            (true, output)
        } else {
            // Compression not beneficial, store raw
            (false, *data)
        }
    }

    /// Reverse braid transformation after reading
    fn transform_for_read(&self, data: &[u8; BLOCK_SIZE]) -> [u8; BLOCK_SIZE] {
        // Check for braid magic header (0xB8AD)
        if data[0] == 0xB8 && data[1] == 0xAD {
            let compressed_len = ((data[2] as usize) << 8) | (data[3] as usize);

            // Reconstruct BraidResult
            let mut compressed_data = [0u8; BLOCK_SIZE];
            let data_start = 12;
            let copy_len = compressed_len.min(BLOCK_SIZE - data_start);
            compressed_data[..copy_len].copy_from_slice(&data[data_start..data_start + copy_len]);

            let result = roulette_rs::BraidResult {
                data: compressed_data,
                compressed_len,
                godel_number: 0, // Not needed for decompression
                ratio: 0.0,
            };

            self.transformer.inverse_transform(&result)
        } else {
            // Not compressed, return as-is
            *data
        }
    }

    /// Handle a read block syscall.
    ///
    /// # Safety
    /// The buffer must point to valid memory of at least BLOCK_SIZE bytes.
    pub unsafe fn handle_read(
        &self,
        addr: SyscallBlockAddr,
        buffer: *mut u8,
    ) -> BridgeResult {
        if buffer.is_null() {
            return BridgeResult::InvalidBuffer;
        }

        let permfs_addr = addr.to_permfs_addr();

        // Validate address belongs to this node/volume
        if permfs_addr.node_id() != self.node_id
            || permfs_addr.volume_id() != self.volume_id
        {
            return BridgeResult::InvalidAddress;
        }

        // Read into temporary buffer
        let mut raw_data = [0u8; BLOCK_SIZE];
        match self.device.read_block(permfs_addr, &mut raw_data) {
            Ok(()) => {
                // Apply inverse braid transformation
                let decompressed = self.transform_for_read(&raw_data);

                // Copy to output buffer
                let buf_slice = core::slice::from_raw_parts_mut(buffer, BLOCK_SIZE);
                buf_slice.copy_from_slice(&decompressed);

                BridgeResult::Success
            }
            Err(_) => BridgeResult::IoError,
        }
    }

    /// Handle a write block syscall with braid transformation.
    ///
    /// # Safety
    /// The buffer must point to valid memory of at least BLOCK_SIZE bytes.
    ///
    /// # Dr-Lex Governance
    /// When the `governance` feature is enabled, data is audited against
    /// the Healthcare Constitution before being written. Ethically corrupt
    /// data will be blocked with `BridgeResult::AuditBlocked`.
    pub unsafe fn handle_write(
        &self,
        addr: SyscallBlockAddr,
        buffer: *const u8,
    ) -> BridgeResult {
        if buffer.is_null() {
            return BridgeResult::InvalidBuffer;
        }

        let permfs_addr = addr.to_permfs_addr();

        // Validate address belongs to this node/volume
        if permfs_addr.node_id() != self.node_id
            || permfs_addr.volume_id() != self.volume_id
        {
            return BridgeResult::InvalidAddress;
        }

        // Create input buffer
        let buf_slice = core::slice::from_raw_parts(buffer, BLOCK_SIZE);
        let input: &[u8; BLOCK_SIZE] = match buf_slice.try_into() {
            Ok(arr) => arr,
            Err(_) => return BridgeResult::InvalidBuffer,
        };

        // === Dr-Lex Governance Audit Hook (Stage 6) ===
        #[cfg(feature = "governance")]
        {
            // Check for ethically corrupt data
            if is_ethically_corrupt(input) {
                return BridgeResult::AuditBlocked;
            }

            // Audit against Healthcare Constitution
            // Healthcare data is encrypted (has braid header), system data is not
            let encrypted = input[0] == 0xB8 && input[1] == 0xAD;
            if let Err(_) = audit_data_write(input, encrypted, "healthcare") {
                return BridgeResult::AuditBlocked;
            }
        }

        // Apply braid transformation
        let (_compressed, transformed) = self.transform_for_write(input);

        // Perform the write
        match self.device.write_block(permfs_addr, &transformed) {
            Ok(()) => BridgeResult::Success,
            Err(_) => BridgeResult::IoError,
        }
    }

    /// Sync all pending writes to storage.
    pub fn sync(&self) -> BridgeResult {
        match self.device.sync() {
            Ok(()) => BridgeResult::Success,
            Err(_) => BridgeResult::IoError,
        }
    }

    /// Get compression statistics
    pub fn estimate_compression(&self, data: &[u8; BLOCK_SIZE]) -> f32 {
        self.transformer.estimate_compression(data)
    }
}

// ============================================================================
// C ABI Entry Points for Kernel Integration
// ============================================================================

/// Opaque handle to bridge state (for C interop).
pub type BridgeHandle = *mut core::ffi::c_void;

/// Global braid transformer for C ABI (stateless operations)
static GLOBAL_TRANSFORMER: T9BraidTransformer = T9BraidTransformer::new();

/// Initialize the bridge (called by Referee during boot).
/// Returns a handle to the bridge state.
#[no_mangle]
pub extern "C" fn permfs_bridge_init(
    _device_ptr: *mut core::ffi::c_void,
    _node_id: u64,
    _volume_id: u32,
) -> BridgeHandle {
    // In a real implementation, this would:
    // 1. Cast device_ptr to the appropriate BlockDevice type
    // 2. Create a PermFsBridge instance
    // 3. Box it and return a raw pointer
    core::ptr::null_mut()
}

/// Read a block through the bridge.
#[no_mangle]
pub extern "C" fn permfs_bridge_read(
    _handle: BridgeHandle,
    addr_high: u128,
    addr_low: u128,
    buffer: *mut u8,
) -> i64 {
    if _handle.is_null() || buffer.is_null() {
        return BridgeResult::InvalidBuffer as i64;
    }

    let _addr = SyscallBlockAddr {
        high: addr_high,
        low: addr_low,
    };

    // Placeholder - would dispatch to actual bridge
    BridgeResult::Success as i64
}

/// Write a block through the bridge with braid transformation.
#[no_mangle]
pub extern "C" fn permfs_bridge_write(
    _handle: BridgeHandle,
    addr_high: u128,
    addr_low: u128,
    buffer: *const u8,
) -> i64 {
    if _handle.is_null() || buffer.is_null() {
        return BridgeResult::InvalidBuffer as i64;
    }

    let _addr = SyscallBlockAddr {
        high: addr_high,
        low: addr_low,
    };

    // In full implementation: apply braid transformation before write
    // let transformed = GLOBAL_TRANSFORMER.transform(input);

    // Placeholder - would dispatch to actual bridge
    BridgeResult::Success as i64
}

/// Transform a block using braid compression (standalone function for testing).
#[no_mangle]
pub extern "C" fn permfs_bridge_transform(
    input: *const u8,
    output: *mut u8,
    compressed_len: *mut usize,
) -> i64 {
    if input.is_null() || output.is_null() || compressed_len.is_null() {
        return BridgeResult::InvalidBuffer as i64;
    }

    unsafe {
        let input_slice = core::slice::from_raw_parts(input, BLOCK_SIZE);
        let input_array: &[u8; BLOCK_SIZE] = match input_slice.try_into() {
            Ok(arr) => arr,
            Err(_) => return BridgeResult::InvalidBuffer as i64,
        };

        let result = GLOBAL_TRANSFORMER.transform(input_array);

        // Copy to output
        let output_slice = core::slice::from_raw_parts_mut(output, BLOCK_SIZE);
        output_slice.copy_from_slice(&result.data);
        *compressed_len = result.compressed_len;
    }

    BridgeResult::Success as i64
}

/// Cleanup and shutdown the bridge.
#[no_mangle]
pub extern "C" fn permfs_bridge_shutdown(_handle: BridgeHandle) {
    if !_handle.is_null() {
        // Would drop the boxed bridge state
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_addr_conversion() {
        let syscall_addr = SyscallBlockAddr {
            high: (42u128 << 64) | (7u128 << 32) | (3u128 << 16),
            low: 100u128 << 80,
        };

        let permfs_addr = syscall_addr.to_permfs_addr();
        assert_eq!(permfs_addr.node_id(), 42);
        assert_eq!(permfs_addr.volume_id(), 7);
        assert_eq!(permfs_addr.shard_id(), 3);
        assert_eq!(permfs_addr.block_offset(), 100);

        let roundtrip = SyscallBlockAddr::from_permfs_addr(permfs_addr);
        assert_eq!(roundtrip.high, syscall_addr.high);
    }

    #[test]
    fn test_braid_transformation() {
        let transformer = T9BraidTransformer::new();

        // Create test data
        let mut input = [0u8; BLOCK_SIZE];
        for (i, byte) in input.iter_mut().enumerate() {
            *byte = (i % 256) as u8;
        }

        let result = transformer.transform(&input);
        assert!(result.compressed_len > 0);
        assert!(result.godel_number > 0);
    }

    #[test]
    #[cfg(feature = "governance")]
    fn test_dr_lex_ethical_blocking() {
        // Test that ethically corrupt data is blocked
        let corrupt_data = b"delete_all_records bypass_consent";
        assert!(is_ethically_corrupt(corrupt_data));

        // Test that clean data passes
        let clean_data = b"normal patient record data";
        assert!(!is_ethically_corrupt(clean_data));

        // Test audit_data_write
        let encrypted_data = [0xB8, 0xAD, 0x00, 0x10]; // Has braid header
        let result = audit_data_write(&encrypted_data, true, "healthcare");
        assert!(result.is_ok());

        // Unencrypted PII should be blocked
        let pii_data = br#"{"patient_id": "123", "name": "John"}"#;
        let result = audit_data_write(pii_data, false, "healthcare");
        assert!(result.is_err());
    }

    #[test]
    fn test_bridge_result_audit_blocked() {
        // Verify AuditBlocked result code exists
        assert_eq!(BridgeResult::AuditBlocked as i64, -10);
    }
}
