//! # Eä Symbiote - IPC Synapse Layer
//!
//! The connective tissue of EAOS. Symbiote provides inter-process communication
//! between Organs (userspace agents) and the Referee Kernel. It translates
//! high-level document operations into low-level syscalls.
//!
//! ## Architecture
//!
//! ```text
//! [Organs/Agents] → [Symbiote/Synapse] → [Referee Kernel] → [PermFS Bridge]
//!       ↓                   ↓                   ↓                  ↓
//!   SovereignBlob      Syscall ABI         T9-Braid           Storage
//! ```
//!
//! ## Braid Governance (0xB8AD)
//!
//! All data committed through Symbiote must satisfy the Braid encryption header
//! requirement. The `SovereignBlob` type enforces this by including an
//! `encryption_header` field that marks data as governance-compliant.
//!
//! ## Example
//!
//! ```rust
//! use ea_symbiote::{Symbiote, SovereignBlob, BlobType};
//!
//! let mut synapse = Symbiote::new();
//!
//! // Create a document blob
//! let blob = SovereignBlob::new_document(b"Hello Sovereign World");
//!
//! // Commit to storage (in real system, invokes syscall)
//! let addr = synapse.commit_organ_data(blob);
//! ```

#![no_std]
#![deny(unsafe_code)]
#![warn(missing_docs, clippy::all)]

extern crate alloc;

use alloc::vec::Vec;
use alloc::string::String;
use core::fmt;
use muscle_contract::abi::SynapticVesicle;

// =============================================================================
// Syscall ABI Types (Mirrored from referee-kernel/src/syscall.rs)
// =============================================================================

/// Braid magic header constant.
/// All encrypted/braided data must have this marker.
pub const BRAID_MAGIC: u16 = 0xB8AD;

/// Block size for I/O operations (4KB).
pub const BLOCK_SIZE: usize = 4096;

/// 256-bit block address matching PermFS layout.
///
/// Structure: [node_id: 64][volume_id: 32][shard_id: 16][flags: 16][block_offset: 48][reserved: 80]
///
/// This is the canonical address type for all EAOS storage operations.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct BlockAddr {
    /// High 128 bits: node_id (64) + volume_id (32) + shard_id (16) + flags (16)
    pub high: u128,
    /// Low 128 bits: block_offset (48) + reserved (80)
    pub low: u128,
}

impl BlockAddr {
    /// Create a new block address.
    pub const fn new(node_id: u64, volume_id: u32, shard_id: u16, block_offset: u64) -> Self {
        let high = ((node_id as u128) << 64)
            | ((volume_id as u128) << 32)
            | ((shard_id as u128) << 16);
        let low = (block_offset as u128) << 80;
        Self { high, low }
    }

    /// Create a null/invalid address.
    pub const fn null() -> Self {
        Self { high: 0, low: 0 }
    }

    /// Check if address is null.
    pub const fn is_null(&self) -> bool {
        self.high == 0 && self.low == 0
    }

    /// Extract node ID from address.
    pub const fn node_id(&self) -> u64 {
        (self.high >> 64) as u64
    }

    /// Extract volume ID from address.
    pub const fn volume_id(&self) -> u32 {
        ((self.high >> 32) & 0xFFFF_FFFF) as u32
    }

    /// Extract shard ID from address.
    pub const fn shard_id(&self) -> u16 {
        ((self.high >> 16) & 0xFFFF) as u16
    }

    /// Extract block offset from address.
    pub const fn block_offset(&self) -> u64 {
        (self.low >> 80) as u64
    }
}

/// System call numbers for EAOS kernel interface.
///
/// These numbers MUST match `referee-kernel/src/syscall.rs::SyscallNumber`.
/// Do not modify without updating the kernel.
#[repr(u64)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SyscallNumber {
    /// Read a 4KB block from storage
    ReadBlock = 0,
    /// Write a 4KB block to storage
    WriteBlock = 1,
    /// Spawn a new task/muscle
    SpawnTask = 2,
    /// Yield CPU to scheduler
    Yield = 3,
    /// Exit current task
    Exit = 4,
    /// Allocate memory pages
    AllocPages = 5,
    /// Free memory pages
    FreePages = 6,
    /// Get system time (TSC-based)
    GetTime = 7,
    /// Log message to audit trail
    AuditLog = 8,
}

/// Syscall result codes.
///
/// These codes MUST match `referee-kernel/src/syscall.rs::SyscallResult`.
#[repr(i64)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SyscallResult {
    /// Operation completed successfully
    Success = 0,
    /// Invalid syscall number
    InvalidSyscall = -1,
    /// Invalid block address
    InvalidAddress = -2,
    /// I/O error during operation
    IoError = -3,
    /// Permission denied (may indicate Dr-Lex audit failure)
    PermissionDenied = -4,
    /// Out of memory
    OutOfMemory = -5,
    /// Invalid buffer pointer
    InvalidBuffer = -6,
    /// Task not found
    TaskNotFound = -7,
    /// Dr-Lex governance blocked the operation
    GovernanceBlocked = -10,
}

impl SyscallResult {
    /// Check if result indicates success.
    pub const fn is_ok(&self) -> bool {
        matches!(self, SyscallResult::Success)
    }

    /// Check if result indicates an error.
    pub const fn is_err(&self) -> bool {
        !self.is_ok()
    }
}

// =============================================================================
// SovereignBlob - Generic Document Container
// =============================================================================

/// Type identifier for SovereignBlob contents.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BlobType {
    /// Raw binary data
    Raw = 0,
    /// Plain text document (Osteon)
    Document = 1,
    /// Spreadsheet/tabular data (Myocyte)
    Spreadsheet = 2,
    /// Logic/computation result (Myocyte)
    Logic = 3,
    /// Structured record (JSON-like)
    Record = 4,
    /// Encrypted/sealed data
    Encrypted = 5,
}

/// Encryption header for Braid compliance.
///
/// This header satisfies the 0xB8AD governance requirement.
/// All data persisted through Symbiote must include this header.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct EncryptionHeader {
    /// Magic number (must be 0xB8AD for braided data)
    pub magic: u16,
    /// Compressed data length
    pub compressed_len: u16,
    /// Lower 64 bits of Gödel number for verification
    pub godel_number: u64,
}

impl Default for EncryptionHeader {
    fn default() -> Self {
        Self {
            magic: BRAID_MAGIC,
            compressed_len: 0,
            godel_number: 0,
        }
    }
}

impl EncryptionHeader {
    /// Create a new encryption header with the braid magic.
    pub const fn new() -> Self {
        Self {
            magic: BRAID_MAGIC,
            compressed_len: 0,
            godel_number: 0,
        }
    }

    /// Check if header has valid braid magic.
    pub const fn is_braided(&self) -> bool {
        self.magic == BRAID_MAGIC
    }

    /// Serialize header to bytes.
    pub fn to_bytes(&self) -> [u8; 12] {
        let mut buf = [0u8; 12];
        buf[0] = (self.magic >> 8) as u8;
        buf[1] = self.magic as u8;
        buf[2] = (self.compressed_len >> 8) as u8;
        buf[3] = self.compressed_len as u8;
        buf[4..12].copy_from_slice(&self.godel_number.to_le_bytes());
        buf
    }

    /// Parse header from bytes.
    pub fn from_bytes(buf: &[u8; 12]) -> Self {
        let magic = ((buf[0] as u16) << 8) | (buf[1] as u16);
        let compressed_len = ((buf[2] as u16) << 8) | (buf[3] as u16);
        let godel_number = u64::from_le_bytes(buf[4..12].try_into().unwrap());
        Self {
            magic,
            compressed_len,
            godel_number,
        }
    }
}

/// SovereignBlob - Universal container for Office Suite data.
///
/// This is the primary data structure for all Organ (agent) communication.
/// It wraps arbitrary data with metadata required for Braid governance.
#[derive(Clone, Debug)]
pub struct SovereignBlob {
    /// Blob type identifier
    pub blob_type: BlobType,
    /// Encryption header for Braid compliance
    pub encryption_header: EncryptionHeader,
    /// Content hash (blake3)
    pub content_hash: [u8; 32],
    /// Actual payload data
    pub payload: Vec<u8>,
    /// Optional label/name for the blob
    pub label: Option<String>,
}

impl SovereignBlob {
    /// Create a new SovereignBlob with raw data.
    pub fn new(blob_type: BlobType, data: &[u8]) -> Self {
        let content_hash: [u8; 32] = blake3::hash(data).into();
        Self {
            blob_type,
            encryption_header: EncryptionHeader::new(),
            content_hash,
            payload: data.to_vec(),
            label: None,
        }
    }

    /// Create a new document blob.
    pub fn new_document(text: &[u8]) -> Self {
        Self::new(BlobType::Document, text)
    }

    /// Create a new spreadsheet blob.
    pub fn new_spreadsheet(data: &[u8]) -> Self {
        Self::new(BlobType::Spreadsheet, data)
    }

    /// Create a new logic/computation blob.
    pub fn new_logic(data: &[u8]) -> Self {
        Self::new(BlobType::Logic, data)
    }

    /// Create a new record blob.
    pub fn new_record(data: &[u8]) -> Self {
        Self::new(BlobType::Record, data)
    }

    /// Set a label for this blob.
    pub fn with_label(mut self, label: &str) -> Self {
        self.label = Some(String::from(label));
        self
    }

    /// Get payload size in bytes.
    pub fn size(&self) -> usize {
        self.payload.len()
    }

    /// Check if this blob has a valid Braid header.
    pub fn is_governance_compliant(&self) -> bool {
        self.encryption_header.is_braided()
    }

    /// Serialize blob to bytes for storage.
    ///
    /// Format:
    /// - [0]: blob_type (1 byte)
    /// - [1..13]: encryption_header (12 bytes)
    /// - [13..45]: content_hash (32 bytes)
    /// - [45..49]: payload_len (4 bytes, big-endian)
    /// - [49..49+payload_len]: payload (variable)
    /// - [next 2 bytes]: label_len (2 bytes, big-endian, 0 if no label)
    /// - [remaining]: label (variable, UTF-8)
    pub fn serialize(&self) -> Vec<u8> {
        let label_bytes = self.label.as_ref().map(|s| s.as_bytes()).unwrap_or(&[]);
        let mut buf = Vec::with_capacity(51 + self.payload.len() + label_bytes.len());

        // Blob type
        buf.push(self.blob_type as u8);

        // Encryption header
        buf.extend_from_slice(&self.encryption_header.to_bytes());

        // Content hash
        buf.extend_from_slice(&self.content_hash);

        // Payload length (4 bytes, big-endian)
        let len = self.payload.len() as u32;
        buf.extend_from_slice(&len.to_be_bytes());

        // Payload
        buf.extend_from_slice(&self.payload);

        // Label length (2 bytes, big-endian)
        let label_len = label_bytes.len() as u16;
        buf.extend_from_slice(&label_len.to_be_bytes());

        // Label (if present)
        if !label_bytes.is_empty() {
            buf.extend_from_slice(label_bytes);
        }

        buf
    }

    /// Deserialize blob from bytes.
    pub fn deserialize(data: &[u8]) -> Option<Self> {
        if data.len() < 49 {
            return None;
        }

        let blob_type = match data[0] {
            0 => BlobType::Raw,
            1 => BlobType::Document,
            2 => BlobType::Spreadsheet,
            3 => BlobType::Logic,
            4 => BlobType::Record,
            5 => BlobType::Encrypted,
            _ => return None,
        };

        let header_bytes: [u8; 12] = data[1..13].try_into().ok()?;
        let encryption_header = EncryptionHeader::from_bytes(&header_bytes);

        let content_hash: [u8; 32] = data[13..45].try_into().ok()?;

        let payload_len = u32::from_be_bytes(data[45..49].try_into().ok()?) as usize;
        if data.len() < 49 + payload_len {
            return None;
        }

        let payload = data[49..49 + payload_len].to_vec();

        // Read label (if present)
        let label_offset = 49 + payload_len;
        let label = if data.len() >= label_offset + 2 {
            let label_len = u16::from_be_bytes(data[label_offset..label_offset + 2].try_into().ok()?) as usize;
            if label_len > 0 && data.len() >= label_offset + 2 + label_len {
                let label_bytes = &data[label_offset + 2..label_offset + 2 + label_len];
                core::str::from_utf8(label_bytes).ok().map(String::from)
            } else {
                None
            }
        } else {
            None
        };

        Some(Self {
            blob_type,
            encryption_header,
            content_hash,
            payload,
            label,
        })
    }
}

// =============================================================================
// Symbiote - The Synapse Interface
// =============================================================================

/// Symbiote error type.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SymbioteError {
    /// Syscall failed with the given result code
    SyscallFailed(SyscallResult),
    /// Data is not governance compliant (missing 0xB8AD header)
    GovernanceViolation,
    /// Buffer too large for single block
    BufferTooLarge,
    /// Invalid blob format
    InvalidBlob,
    /// Address allocation failed
    AllocationFailed,
}

impl fmt::Display for SymbioteError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::SyscallFailed(code) => write!(f, "Syscall failed: {:?}", code),
            Self::GovernanceViolation => write!(f, "Data missing Braid header (0xB8AD)"),
            Self::BufferTooLarge => write!(f, "Buffer exceeds single block size"),
            Self::InvalidBlob => write!(f, "Invalid blob format"),
            Self::AllocationFailed => write!(f, "Block address allocation failed"),
        }
    }
}

/// Symbiote - IPC Synapse for EAOS Organs.
///
/// This is the primary interface for Organs (userspace agents) to communicate
/// with the Referee Kernel. It translates high-level operations into syscalls.
#[derive(Debug, Clone)]
pub struct Symbiote {
    /// Current node ID for this Symbiote instance
    node_id: u64,
    /// Current volume ID
    volume_id: u32,
    /// Next block offset for allocation (simple bump allocator)
    next_block: u64,
}

impl Default for Symbiote {
    fn default() -> Self {
        Self::new()
    }
}

impl Symbiote {
    /// Create a new Symbiote instance.
    pub fn new() -> Self {
        Self {
            node_id: 0,
            volume_id: 1,
            next_block: 0,
        }
    }

    /// Create a Symbiote with specific node/volume configuration.
    pub fn with_config(node_id: u64, volume_id: u32) -> Self {
        Self {
            node_id,
            volume_id,
            next_block: 0,
        }
    }

    /// Allocate a new block address.
    fn allocate_block(&mut self) -> BlockAddr {
        let addr = BlockAddr::new(self.node_id, self.volume_id, 0, self.next_block);
        self.next_block += 1;
        addr
    }

    /// Commit organ data to storage.
    ///
    /// This is the primary API for Organs to persist data. The blob must be
    /// governance compliant (have valid Braid header).
    ///
    /// # Returns
    /// - `Ok(BlockAddr)` - The address where data was stored
    /// - `Err(SymbioteError)` - On failure
    ///
    /// # Example
    /// ```rust
    /// use ea_symbiote::{Symbiote, SovereignBlob};
    ///
    /// let mut synapse = Symbiote::new();
    /// let blob = SovereignBlob::new_document(b"Hello Sovereign World");
    /// let result = synapse.commit_organ_data(blob);
    /// ```
    pub fn commit_organ_data(&mut self, blob: SovereignBlob) -> Result<BlockAddr, SymbioteError> {
        // Verify governance compliance
        if !blob.is_governance_compliant() {
            return Err(SymbioteError::GovernanceViolation);
        }

        // Serialize the blob
        let serialized = blob.serialize();

        // Check if it fits in a single block (for now)
        if serialized.len() > BLOCK_SIZE {
            return Err(SymbioteError::BufferTooLarge);
        }

        // Allocate a block address
        let addr = self.allocate_block();

        // In a real implementation, this would invoke the syscall:
        // syscall(SyscallNumber::WriteBlock, addr.high, addr.low, buffer_ptr)
        //
        // For now, we simulate success
        log::debug!(
            "Synapse: Committed {} bytes to {:?}",
            serialized.len(),
            addr
        );

        Ok(addr)
    }

    /// Read organ data from storage.
    ///
    /// # Returns
    /// - `Ok(SovereignBlob)` - The retrieved blob
    /// - `Err(SymbioteError)` - On failure
    pub fn read_organ_data(&self, addr: BlockAddr) -> Result<SovereignBlob, SymbioteError> {
        if addr.is_null() {
            return Err(SymbioteError::SyscallFailed(SyscallResult::InvalidAddress));
        }

        // In a real implementation, this would invoke the syscall:
        // syscall(SyscallNumber::ReadBlock, addr.high, addr.low, buffer_ptr)
        //
        // For now, return an error indicating not implemented
        log::debug!("Synapse: Read request for {:?}", addr);

        Err(SymbioteError::SyscallFailed(SyscallResult::IoError))
    }

    /// Submit a network request (Hive Mind).
    pub fn submit_request(&mut self, _vesicle: SynapticVesicle) -> Result<(), SymbioteError> {
        // Syscall 9: SubmitRequest
        Ok(())
    }

    /// Prepare syscall arguments for WriteBlock.
    ///
    /// This is a low-level helper for direct syscall invocation.
    pub fn prepare_write_syscall(
        addr: BlockAddr,
        data: &[u8],
    ) -> (u64, u64, u64, u64) {
        let syscall_num = SyscallNumber::WriteBlock as u64;
        let arg1 = (addr.high >> 64) as u64;
        let arg2 = addr.high as u64;
        let arg3 = data.as_ptr() as u64;
        (syscall_num, arg1, arg2, arg3)
    }

    /// Prepare syscall arguments for ReadBlock.
    ///
    /// This is a low-level helper for direct syscall invocation.
    pub fn prepare_read_syscall(
        addr: BlockAddr,
        buffer: &mut [u8],
    ) -> (u64, u64, u64, u64) {
        let syscall_num = SyscallNumber::ReadBlock as u64;
        let arg1 = (addr.high >> 64) as u64;
        let arg2 = addr.high as u64;
        let arg3 = buffer.as_mut_ptr() as u64;
        (syscall_num, arg1, arg2, arg3)
    }
}

// =============================================================================
// Document Trait for Office Suite
// =============================================================================

/// Generic document trait for Office Suite agents.
///
/// Implement this trait for custom document types (text, spreadsheet, etc.)
pub trait SovereignDocument {
    /// Get the blob type for this document.
    fn blob_type(&self) -> BlobType;

    /// Serialize document to bytes.
    fn to_bytes(&self) -> Vec<u8>;

    /// Create document from bytes.
    fn from_bytes(data: &[u8]) -> Option<Self>
    where
        Self: Sized;

    /// Convert to SovereignBlob for storage.
    fn to_blob(&self) -> SovereignBlob {
        SovereignBlob::new(self.blob_type(), &self.to_bytes())
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_block_addr_creation() {
        let addr = BlockAddr::new(42, 7, 3, 100);
        assert_eq!(addr.node_id(), 42);
        assert_eq!(addr.volume_id(), 7);
        assert_eq!(addr.shard_id(), 3);
        assert_eq!(addr.block_offset(), 100);
    }

    #[test]
    fn test_block_addr_null() {
        let null_addr = BlockAddr::null();
        assert!(null_addr.is_null());

        let valid_addr = BlockAddr::new(1, 1, 1, 1);
        assert!(!valid_addr.is_null());
    }

    #[test]
    fn test_sovereign_blob_creation() {
        let blob = SovereignBlob::new_document(b"Hello Sovereign World");
        assert_eq!(blob.blob_type, BlobType::Document);
        assert!(blob.is_governance_compliant());
        assert_eq!(blob.payload, b"Hello Sovereign World");
    }

    #[test]
    fn test_blob_serialization_roundtrip() {
        let original = SovereignBlob::new_document(b"Test data for serialization");
        let serialized = original.serialize();
        let deserialized = SovereignBlob::deserialize(&serialized).unwrap();

        assert_eq!(deserialized.blob_type, original.blob_type);
        assert_eq!(deserialized.payload, original.payload);
        assert_eq!(deserialized.content_hash, original.content_hash);
    }

    #[test]
    fn test_encryption_header() {
        let header = EncryptionHeader::new();
        assert_eq!(header.magic, BRAID_MAGIC);
        assert!(header.is_braided());

        let bytes = header.to_bytes();
        let parsed = EncryptionHeader::from_bytes(&bytes);
        assert_eq!(parsed.magic, header.magic);
    }

    #[test]
    fn test_symbiote_commit() {
        let mut synapse = Symbiote::new();
        let blob = SovereignBlob::new_document(b"Hello Sovereign World");

        let result = synapse.commit_organ_data(blob);
        assert!(result.is_ok());

        let addr = result.unwrap();
        assert!(!addr.is_null());
    }

    #[test]
    fn test_syscall_numbers_match() {
        // Verify our syscall numbers match referee-kernel
        assert_eq!(SyscallNumber::ReadBlock as u64, 0);
        assert_eq!(SyscallNumber::WriteBlock as u64, 1);
        assert_eq!(SyscallNumber::SpawnTask as u64, 2);
        assert_eq!(SyscallNumber::Yield as u64, 3);
        assert_eq!(SyscallNumber::Exit as u64, 4);
    }
}
