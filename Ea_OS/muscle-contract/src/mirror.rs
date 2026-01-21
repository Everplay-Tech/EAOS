#![no_std]

/// Operations for the Mirror (Simulation Engine)
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum MirrorOp {
    NoOp = 0x00,
    /// Analyze an intent for safety
    SimulateIntent = 0x01,
}

/// Safety Level returned by Mirror
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum SafetyLevel {
    Safe = 0x00,
    Caution = 0x01,
    Hazard = 0x02,
    Forbidden = 0xFF,
}

/// Request structure for Mirror
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct MirrorRequest {
    pub op: MirrorOp,
    pub intent_type: u8, // e.g., IntentOp form Broca
    pub target_id: u64,
}

/// Result of a Mirror simulation
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct MirrorResult {
    pub level: SafetyLevel,
    pub consequence_code: u32,
}
