#![no_std]

extern crate muscle_contract;
use muscle_contract::mitochondria::{MitochondriaOp, EnergyRequest, EnergyResult, EnergyLevel};

// Simple global tracker (mocking per-process tracking)
// In a real system, this would be a map of MuscleID -> Cycles
static mut TOTAL_CYCLES: u64 = 0;
const MAX_CYCLES: u64 = 1_000_000;

pub fn regulate(req: EnergyRequest) -> EnergyResult {
    match req.op {
        MitochondriaOp::ReportUsage => {
            unsafe {
                TOTAL_CYCLES += req.cycles;
                // Simple metabolic decay
                if TOTAL_CYCLES > 500 {
                    TOTAL_CYCLES -= 500; 
                }
            }
            check_status()
        },
        MitochondriaOp::CheckBudget => check_status(),
        _ => EnergyResult { level: EnergyLevel::Optimal, remaining: 0 },
    }
}

fn check_status() -> EnergyResult {
    unsafe {
        if TOTAL_CYCLES > MAX_CYCLES {
            EnergyResult { level: EnergyLevel::Exhausted, remaining: 0 }
        } else if TOTAL_CYCLES > MAX_CYCLES / 2 {
            EnergyResult { level: EnergyLevel::Draining, remaining: MAX_CYCLES - TOTAL_CYCLES }
        } else {
            EnergyResult { level: EnergyLevel::Optimal, remaining: MAX_CYCLES - TOTAL_CYCLES }
        }
    }
}
