#![no_std]

/// Operations for Mitochondria (Energy Governor)
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum MitochondriaOp {
    NoOp = 0x00,
    /// Report cycles consumed by a muscle
    ReportUsage = 0x01,
    /// Check if a muscle is within budget
    CheckBudget = 0x02,
}

/// Request structure
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct EnergyRequest {
    pub op: MitochondriaOp,
    pub muscle_id: u64,
    pub cycles: u64,
}

/// Energy Status
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum EnergyLevel {
    Optimal = 0x00,
    Draining = 0x01,
    Exhausted = 0x02,
}

/// Result
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct EnergyResult {
    pub level: EnergyLevel,
    pub remaining: u64,
}
