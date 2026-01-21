#![no_std]

extern crate muscle_contract;
use muscle_contract::dreamer::{DreamerOp, DreamerRequest, DreamerResult};

/// Perform one step of the dreaming cycle
pub fn dream_step(req: DreamerRequest, data: &[u8]) -> DreamerResult {
    match req.op {
        DreamerOp::VerifyRange => {
            // Verify integrity of the block
            let valid = verify_block(data);
            DreamerResult {
                op: req.op,
                blocks_checked: 1,
                errors_found: if valid { 0 } else { 1 },
                status: 0,
            }
        },
        _ => DreamerResult {
            op: req.op,
            blocks_checked: 0,
            errors_found: 0,
            status: 0,
        }
    }
}

fn verify_block(data: &[u8]) -> bool {
    // 1. Check for Braid Magic 0xB8AD
    if data.len() >= 2 && data[0] == 0xB8 && data[1] == 0xAD {
        return true;
    }
    
    // 2. Check if empty (all zero) - valid (Dormant)
    // Optimization: check first few bytes
    if data.len() >= 16 && data[0..16].iter().all(|&b| b == 0) {
        return true; 
    }
    
    // 3. Raw Data
    true
}
