#![no_std]

/// The "Language" of the Sovereign Pod.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum IntentOp {
    NoOp = 0x00,
    /// "List Files" - Scan PermFS
    Survey = 0x01,
    /// "Read" - Fetch document by ID
    Recall = 0x02,
    /// "Write" - Save document
    Memorize = 0x03,
    /// "Net" - Trigger Arachnid harvest
    Harvest = 0x04,
    /// "Exec" - Load another muscle
    Innervate = 0x05,
    /// Parse Error / Syntax Error
    Aphasia = 0xFF,
}

/// The structured result of speech processing.
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct DirectorRequest {
    pub intent: IntentOp,
    pub target_id: u64,       // e.g., Document ID
    pub param: u64,           // e.g., Timestamp or Size
    pub payload: [u8; 64],    // Short payload (e.g., filename)
    pub payload_len: u8,
}
