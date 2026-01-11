// muscle-compiler/src/codegen/x86_64.rs
// Eä x86_64 Code Generation v6.0 — Minimal 4→1 inference with ReLU

use crate::error::CompileError;
use crate::parser::Weights;

#[derive(Debug, Clone, Copy)]
struct RipPatch {
    disp_offset: usize,
    instr_end: usize,
    const_index: usize,
}

/// Generate x86_64 machine code for a tiny NN:
/// y = ReLU(w0*x0 + w1*x1 + w2*x2 + w3*x3 + b)
///
/// ABI (System V): inputs in xmm0-xmm3, output in xmm0.
/// Requires FMA3 support for vfmadd231ss.
pub fn emit(weights: &Weights) -> Result<Vec<u8>, CompileError> {
    let mut code = Vec::with_capacity(128);
    let mut patches = Vec::new();

    emit_movss_rip(&mut code, &mut patches, MovssKind::Xmm4, 0);
    emit_movss_rip(&mut code, &mut patches, MovssKind::Xmm5, 1);
    emit_movss_rip(&mut code, &mut patches, MovssKind::Xmm6, 2);
    emit_movss_rip(&mut code, &mut patches, MovssKind::Xmm7, 3);
    emit_movss_rip(&mut code, &mut patches, MovssKind::Xmm8, 4);

    code.extend_from_slice(&[0xF3, 0x0F, 0x59, 0xC4]); // mulss xmm0, xmm4
    code.extend_from_slice(&[0xC4, 0xE2, 0x71, 0xB9, 0xC5]); // vfmadd231ss xmm0, xmm1, xmm5
    code.extend_from_slice(&[0xC4, 0xE2, 0x69, 0xB9, 0xC6]); // vfmadd231ss xmm0, xmm2, xmm6
    code.extend_from_slice(&[0xC4, 0xE2, 0x61, 0xB9, 0xC7]); // vfmadd231ss xmm0, xmm3, xmm7
    code.extend_from_slice(&[0xF3, 0x41, 0x0F, 0x58, 0xC0]); // addss xmm0, xmm8
    code.extend_from_slice(&[0x0F, 0x57, 0xC9]); // xorps xmm1, xmm1
    code.extend_from_slice(&[0xF3, 0x0F, 0x5F, 0xC1]); // maxss xmm0, xmm1
    code.push(0xC3); // ret

    let const_base = code.len();
    for value in [weights.w[0], weights.w[1], weights.w[2], weights.w[3], weights.b] {
        code.extend_from_slice(&value.to_le_bytes());
    }

    for patch in patches {
        patch_rip_disp(&mut code, patch, const_base)?;
    }

    Ok(code)
}

#[derive(Clone, Copy)]
enum MovssKind {
    Xmm4,
    Xmm5,
    Xmm6,
    Xmm7,
    Xmm8,
}

fn emit_movss_rip(
    code: &mut Vec<u8>,
    patches: &mut Vec<RipPatch>,
    kind: MovssKind,
    const_index: usize,
) {
    let (prefix, len) = match kind {
        MovssKind::Xmm4 => (&[0xF3, 0x0F, 0x10, 0x25][..], 8),
        MovssKind::Xmm5 => (&[0xF3, 0x0F, 0x10, 0x2D][..], 8),
        MovssKind::Xmm6 => (&[0xF3, 0x0F, 0x10, 0x35][..], 8),
        MovssKind::Xmm7 => (&[0xF3, 0x0F, 0x10, 0x3D][..], 8),
        MovssKind::Xmm8 => (&[0xF3, 0x44, 0x0F, 0x10, 0x05][..], 9),
    };

    let disp_offset = code.len() + prefix.len();
    code.extend_from_slice(prefix);
    code.extend_from_slice(&[0u8; 4]);
    let instr_end = code.len();

    patches.push(RipPatch {
        disp_offset,
        instr_end,
        const_index,
    });

    debug_assert_eq!(instr_end - (disp_offset - prefix.len()), len);
}

fn patch_rip_disp(
    code: &mut [u8],
    patch: RipPatch,
    const_base: usize,
) -> Result<(), CompileError> {
    let target = (const_base + patch.const_index * 4) as i64;
    let instr_end = patch.instr_end as i64;
    let disp = target - instr_end;

    if disp < i32::MIN as i64 || disp > i32::MAX as i64 {
        return Err(CompileError::CodegenError(
            "RIP-relative displacement out of range".to_string(),
        ));
    }

    let disp_bytes = (disp as i32).to_le_bytes();
    let end = patch.disp_offset + 4;
    code[patch.disp_offset..end].copy_from_slice(&disp_bytes);

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_x86_code_generation() {
        let weights = Weights {
            w: [0.1, 0.2, 0.3, 0.4],
            b: 0.7,
        };

        let code = emit(&weights).expect("emit code");

        assert!(code.len() >= 64, "Generated code too small");
        assert!(code.ends_with(&weights.b.to_le_bytes()));

        let mulss = [0xF3, 0x0F, 0x59, 0xC4];
        assert!(code.windows(mulss.len()).any(|w| w == mulss));

        let const_base = code.len() - (5 * 4);
        assert_eq!(code[const_base - 1], 0xC3);
    }
}
