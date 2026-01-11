// muscle-compiler/src/codegen/aarch64.rs
// Eä AArch64 Code Generation v6.0 — Minimal 4→1 inference with ReLU

use crate::error::CompileError;
use crate::parser::Weights;

const LDR_LITERAL_F32: u32 = 0x1c00_0000;
const IMM19_MASK: u32 = 0x7ffff;

#[derive(Debug, Clone, Copy)]
struct LdrPatch {
    instr_offset: usize,
    reg: u8,
    const_index: usize,
}

/// Generate AArch64 machine code for a tiny NN:
/// y = ReLU(w0*x0 + w1*x1 + w2*x2 + w3*x3 + b)
///
/// ABI (AAPCS64): inputs in s0-s3, output in s0.
pub fn emit(weights: &Weights) -> Result<Vec<u8>, CompileError> {
    let mut code = Vec::with_capacity(96);
    let mut patches = Vec::new();

    // Load weights from literal pool.
    emit_ldr_literal_f32(&mut code, &mut patches, 4, 0);
    emit_ldr_literal_f32(&mut code, &mut patches, 5, 1);
    emit_ldr_literal_f32(&mut code, &mut patches, 6, 2);
    emit_ldr_literal_f32(&mut code, &mut patches, 7, 3);
    emit_ldr_literal_f32(&mut code, &mut patches, 8, 4);

    // z = w0*x0
    push_u32(&mut code, 0x1e24_0800); // fmul s0, s0, s4
    // z += w1*x1
    push_u32(&mut code, 0x1f05_0020); // fmadd s0, s1, s5, s0
    // z += w2*x2
    push_u32(&mut code, 0x1f06_0040); // fmadd s0, s2, s6, s0
    // z += w3*x3
    push_u32(&mut code, 0x1f07_0060); // fmadd s0, s3, s7, s0
    // z += b
    push_u32(&mut code, 0x1e28_2800); // fadd s0, s0, s8

    // ReLU: s0 = max(s0, 0.0)
    push_u32(&mut code, 0x1e27_03e1); // fmov s1, wzr
    push_u32(&mut code, 0x1e21_2000); // fcmp s0, s1
    push_u32(&mut code, 0x1e21_cc00); // fcsel s0, s0, s1, gt

    push_u32(&mut code, 0xd65f_03c0); // ret

    // Literal pool (4-byte aligned).
    let const_base = code.len();
    for value in [weights.w[0], weights.w[1], weights.w[2], weights.w[3], weights.b] {
        code.extend_from_slice(&value.to_le_bytes());
    }

    for patch in patches {
        patch_ldr_literal_f32(&mut code, patch, const_base)?;
    }

    Ok(code)
}

fn emit_ldr_literal_f32(code: &mut Vec<u8>, patches: &mut Vec<LdrPatch>, reg: u8, const_index: usize) {
    let instr_offset = code.len();
    push_u32(code, 0);
    patches.push(LdrPatch {
        instr_offset,
        reg,
        const_index,
    });
}

fn patch_ldr_literal_f32(
    code: &mut [u8],
    patch: LdrPatch,
    const_base: usize,
) -> Result<(), CompileError> {
    if patch.reg > 31 {
        return Err(CompileError::CodegenError(format!(
            "Invalid target register for LDR literal: {}",
            patch.reg
        )));
    }

    let pc = patch.instr_offset as i64;
    let target = (const_base + patch.const_index * 4) as i64;
    let offset = target - pc;

    if offset % 4 != 0 {
        return Err(CompileError::CodegenError(
            "LDR literal offset must be 4-byte aligned".to_string(),
        ));
    }

    let imm19 = offset / 4;
    if imm19 < -(1 << 18) || imm19 > (1 << 18) - 1 {
        return Err(CompileError::CodegenError(
            "LDR literal offset out of range".to_string(),
        ));
    }

    let imm19_bits = (imm19 as i32 as u32) & IMM19_MASK;
    let instr = LDR_LITERAL_F32 | (imm19_bits << 5) | (patch.reg as u32);
    let bytes = instr.to_le_bytes();
    let end = patch.instr_offset + 4;
    code[patch.instr_offset..end].copy_from_slice(&bytes);

    Ok(())
}

fn push_u32(code: &mut Vec<u8>, word: u32) {
    code.extend_from_slice(&word.to_le_bytes());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_code_generation() {
        let weights = Weights {
            w: [0.1, 0.2, 0.3, 0.4],
            b: 0.7,
        };

        let code = emit(&weights).expect("emit code");

        assert_eq!(code.len(), 56 + 20);

        let first = u32::from_le_bytes(code[0..4].try_into().unwrap());
        let second = u32::from_le_bytes(code[4..8].try_into().unwrap());
        let third = u32::from_le_bytes(code[8..12].try_into().unwrap());
        let fourth = u32::from_le_bytes(code[12..16].try_into().unwrap());
        let fifth = u32::from_le_bytes(code[16..20].try_into().unwrap());

        assert_eq!(first, 0x1c00_01c4);
        assert_eq!(second, 0x1c00_01c5);
        assert_eq!(third, 0x1c00_01c6);
        assert_eq!(fourth, 0x1c00_01c7);
        assert_eq!(fifth, 0x1c00_01c8);

        let consts = &code[56..76];
        let mut expected = Vec::new();
        for value in [weights.w[0], weights.w[1], weights.w[2], weights.w[3], weights.b] {
            expected.extend_from_slice(&value.to_le_bytes());
        }
        assert_eq!(consts, expected.as_slice());

        let ret = u32::from_le_bytes(code[52..56].try_into().unwrap());
        assert_eq!(ret, 0xd65f_03c0);
    }
}
