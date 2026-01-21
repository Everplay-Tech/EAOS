#![no_std]

/// Operations for the Dreamer (Integrity Engine)
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum DreamerOp {
    /// No operation
    NoOp = 0x00,
    /// Verify checksums of a block range
    VerifyRange = 0x01,
    /// Build index for fast search
    BuildIndex = 0x02,
    /// Defragment/Optimize storage layout
    Optimize = 0x03,
}

/// Request structure for Dreamer
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct DreamerRequest {
    pub op: DreamerOp,
    pub start_block: u64,
    pub count: u64,
}

/// Result of a Dreamer operation
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct DreamerResult {
    pub op: DreamerOp,
    pub blocks_checked: u64,
    pub errors_found: u64,
    pub status: u8, // 0=OK, 1=Error
}
