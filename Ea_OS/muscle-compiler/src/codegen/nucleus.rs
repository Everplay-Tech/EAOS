//! Enhanced code generator for Muscle.ea with capability enforcement
//! Generates 8KiB AArch64 machine code with security guarantees

use crate::ast::full_ast::*;
use crate::error::CompileError;
use muscle_contract::{MANIFEST_LEN, PAYLOAD_LEN};
use std::collections::{HashMap, HashSet};

const NUCLEUS_CODE_SIZE: usize = PAYLOAD_LEN - MANIFEST_LEN;

#[derive(Clone, Copy, Debug)]
enum PatchKind {
    B,
    BL,
    BCond,
    CBZ,
    CBNZ,
}

#[derive(Debug)]
struct BranchPatch {
    kind: PatchKind,
    at: usize,
    target: String,
    reg: Option<u8>,
    cond: Option<u8>,
    is_64: bool,
}

#[derive(Debug)]
struct CodeBuilder {
    code: Vec<u8>,
    labels: HashMap<String, usize>,
    patches: Vec<BranchPatch>,
    counter: usize,
}

impl CodeBuilder {
    fn new(capacity: usize) -> Self {
        Self {
            code: Vec::with_capacity(capacity),
            labels: HashMap::new(),
            patches: Vec::new(),
            counter: 0,
        }
    }

    fn position(&self) -> usize {
        self.code.len()
    }

    fn push_u32(&mut self, word: u32) {
        self.code.extend_from_slice(&word.to_le_bytes());
    }

    fn push_bytes(&mut self, bytes: &[u8]) {
        self.code.extend_from_slice(bytes);
    }

    fn label(&mut self, name: &str) {
        self.labels.insert(name.to_string(), self.position());
    }

    fn fresh_label(&mut self, prefix: &str) -> String {
        let label = format!("{}_{}", prefix, self.counter);
        self.counter += 1;
        label
    }

    fn emit_branch(&mut self, kind: PatchKind, target: String, reg: Option<u8>, cond: Option<u8>, is_64: bool) {
        let at = self.position();
        self.push_u32(0);
        self.patches.push(BranchPatch {
            kind,
            at,
            target,
            reg,
            cond,
            is_64,
        });
    }

    fn patch_branches(&mut self) -> Result<(), CompileError> {
        for patch in &self.patches {
            let target = *self
                .labels
                .get(&patch.target)
                .ok_or_else(|| {
                    CompileError::CodegenError(format!(
                        "Unknown branch target label: {}",
                        patch.target
                    ))
                })?;
            let pc = patch.at as i64;
            let offset = target as i64 - pc;

            if offset % 4 != 0 {
                return Err(CompileError::CodegenError(format!(
                    "Branch offset not 4-byte aligned: {}",
                    patch.target
                )));
            }

            let instr = match patch.kind {
                PatchKind::B => encode_b_bl(false, offset)?,
                PatchKind::BL => encode_b_bl(true, offset)?,
                PatchKind::BCond => {
                    let cond = patch.cond.ok_or_else(|| {
                        CompileError::CodegenError("Missing condition for B.cond".to_string())
                    })?;
                    encode_b_cond(cond, offset)?
                }
                PatchKind::CBZ => {
                    let reg = patch.reg.ok_or_else(|| {
                        CompileError::CodegenError("Missing register for CBZ".to_string())
                    })?;
                    encode_cbz_cbnz(false, reg, patch.is_64, offset)?
                }
                PatchKind::CBNZ => {
                    let reg = patch.reg.ok_or_else(|| {
                        CompileError::CodegenError("Missing register for CBNZ".to_string())
                    })?;
                    encode_cbz_cbnz(true, reg, patch.is_64, offset)?
                }
            };

            let bytes = instr.to_le_bytes();
            let end = patch.at + 4;
            self.code[patch.at..end].copy_from_slice(&bytes);
        }

        Ok(())
    }
}

fn encode_b_bl(is_bl: bool, offset: i64) -> Result<u32, CompileError> {
    let imm = offset >> 2;
    if imm < -(1 << 25) || imm > (1 << 25) - 1 {
        return Err(CompileError::CodegenError(
            "B/BL offset out of range".to_string(),
        ));
    }
    let imm26 = (imm as i32 as u32) & 0x03ff_ffff;
    let base = if is_bl { 0x9400_0000 } else { 0x1400_0000 };
    Ok(base | imm26)
}

fn encode_b_cond(cond: u8, offset: i64) -> Result<u32, CompileError> {
    let imm = offset >> 2;
    if imm < -(1 << 18) || imm > (1 << 18) - 1 {
        return Err(CompileError::CodegenError(
            "B.cond offset out of range".to_string(),
        ));
    }
    let imm19 = (imm as i32 as u32) & 0x7ffff;
    Ok(0x5400_0000 | (imm19 << 5) | (cond as u32 & 0xf))
}

fn encode_cbz_cbnz(is_cbnz: bool, reg: u8, is_64: bool, offset: i64) -> Result<u32, CompileError> {
    if reg > 31 {
        return Err(CompileError::CodegenError(
            "CBZ/CBNZ register out of range".to_string(),
        ));
    }
    let imm = offset >> 2;
    if imm < -(1 << 18) || imm > (1 << 18) - 1 {
        return Err(CompileError::CodegenError(
            "CBZ/CBNZ offset out of range".to_string(),
        ));
    }
    let imm19 = (imm as i32 as u32) & 0x7ffff;
    let sf = if is_64 { 1u32 } else { 0u32 };
    let op = if is_cbnz { 1u32 } else { 0u32 };
    Ok((sf << 31) | (0x1a << 25) | (op << 24) | (imm19 << 5) | reg as u32)
}

fn encode_cmp_imm_w(imm: u16) -> u32 {
    0x7100_001f | ((imm as u32) << 10)
}

fn encode_mov_imm_w(rd: u8, imm: u16) -> u32 {
    0x5280_0000 | ((imm as u32) << 5) | (rd as u32)
}

fn encode_ldrb_imm(rt: u8, rn: u8, imm: u16) -> Result<u32, CompileError> {
    if rt > 31 || rn > 31 || imm > 0xfff {
        return Err(CompileError::CodegenError(
            "LDRB immediate out of range".to_string(),
        ));
    }
    Ok(0x3940_0000 | ((imm as u32) << 10) | ((rn as u32) << 5) | (rt as u32))
}

/// Enhanced Nucleus code generator with capability security
pub struct NucleusCodegen;

impl NucleusCodegen {
    /// Generate fixed-size AArch64 machine code with capability enforcement
    pub fn generate(program: &Program) -> Result<Vec<u8>, CompileError> {
        let mut builder = CodeBuilder::new(NUCLEUS_CODE_SIZE);
        let capability_names = Self::collect_capabilities(program);

        // 1. Entry point and capability security setup
        Self::emit_security_header(&mut builder);

        // 2. Rule dispatcher with event verification
        Self::emit_rule_dispatcher(&mut builder, &program.rules);

        // 3. Capability implementations with runtime checks
        Self::emit_capability_implementations(&mut builder, program, &capability_names)?;

        // 4. Built-in function implementations
        Self::emit_builtin_functions(&mut builder);

        // 5. Event handlers
        Self::emit_event_handlers(&mut builder, &program.rules, program, &capability_names)?;

        // 6. Data section with constants and security tokens
        builder.push_bytes(&Self::generate_data_section(program));

        // 7. Capability security enforcement tables
        builder.push_bytes(&Self::generate_capability_tables(program));

        builder.patch_branches()?;

        if builder.code.len() > NUCLEUS_CODE_SIZE {
            return Err(CompileError::CodegenError(format!(
                "Nucleus code size {} exceeds {} bytes",
                builder.code.len(),
                NUCLEUS_CODE_SIZE
            )));
        }

        builder.code.resize(NUCLEUS_CODE_SIZE, 0x00);
        Ok(builder.code)
    }

    fn collect_capabilities(program: &Program) -> HashSet<String> {
        let mut names = HashSet::new();
        for decl in &program.declarations {
            if let Declaration::Capability(cap) = decl {
                names.insert(cap.name.clone());
            }
        }
        names
    }

    fn emit_security_header(builder: &mut CodeBuilder) {
        // Security header: capability enforcement setup
        builder.push_u32(0xD2800B88); // MOV X8, #0x1000
        builder.push_u32(0x9100011C); // ADD X28, X8, #0
        builder.push_u32(0xF900039F); // STR XZR, [X28, #0]
        builder.push_u32(0x910043FF); // MOV SP, #0x8000

        builder.emit_branch(
            PatchKind::BL,
            "rule_dispatcher".to_string(),
            None,
            None,
            false,
        );

        builder.label("security_violation");
        builder.emit_branch(
            PatchKind::B,
            "security_violation".to_string(),
            None,
            None,
            false,
        );
    }

    fn emit_rule_dispatcher(builder: &mut CodeBuilder, rules: &[Rule]) {
        builder.label("rule_dispatcher");
        builder.push_u32(0xD10083FF); // SUB SP, SP, #32
        builder.push_u32(0xB9002FE0); // STR W0, [SP, #44] ; event_id
        builder.push_u32(0xF9001BE1); // STR X1, [SP, #48] ; event_data

        for (i, rule) in rules.iter().enumerate() {
            let event_id = Self::event_to_id(&rule.event) as u16;
            builder.push_u32(encode_cmp_imm_w(event_id)); // CMP W0, #event_id
            builder.emit_branch(
                PatchKind::BCond,
                handler_label(i),
                None,
                Some(0),
                false,
            );
        }

        builder.push_u32(0x52800000); // MOV W0, #0
        builder.push_u32(0x910083FF); // ADD SP, SP, #32
        builder.push_u32(0xD65F03C0); // RET
    }

    fn emit_capability_implementations(
        builder: &mut CodeBuilder,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        for decl in &program.declarations {
            if let Declaration::Capability(cap) = decl {
                builder.label(&cap_label(&cap.name));
                Self::emit_capability_function(builder, cap, capability_names)?;
            }
        }
        Ok(())
    }

    fn emit_capability_function(
        builder: &mut CodeBuilder,
        cap: &CapabilityDecl,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        builder.push_u32(0xD10083FF); // SUB SP, SP, #32
        builder.push_u32(0xA9007BFD); // STP X29, X30, [SP, #16]
        builder.push_u32(0x910043FD); // ADD X29, SP, #16

        Self::emit_capability_check(builder, &cap.name)?;

        for i in 0..cap.parameters.len() {
            if i < 8 {
                let store_instr = match i {
                    0 => 0xF90007E0, // STR X0, [SP, #0]
                    1 => 0xF9000BE1, // STR X1, [SP, #8]
                    2 => 0xF9000FE2, // STR X2, [SP, #16]
                    3 => 0xF90013E3, // STR X3, [SP, #24]
                    4 => 0xF90017E4, // STR X4, [SP, #32]
                    5 => 0xF9001BE5, // STR X5, [SP, #40]
                    6 => 0xF9001FE6, // STR X6, [SP, #48]
                    7 => 0xF90023E7, // STR X7, [SP, #56]
                    _ => 0,
                };
                builder.push_u32(store_instr);
            }
        }

        Self::emit_capability_body(builder, cap, capability_names)?;

        builder.push_u32(0xA9417BFD); // LDP X29, X30, [SP, #16]
        builder.push_u32(0x910083FF); // ADD SP, SP, #32
        builder.push_u32(0xD65F03C0); // RET

        Ok(())
    }

    fn emit_capability_check(builder: &mut CodeBuilder, cap_name: &str) -> Result<(), CompileError> {
        let cap_offset = Self::capability_offset(cap_name) as u16;
        builder.push_u32(encode_ldrb_imm(8, 28, cap_offset)?);

        let ok_label = builder.fresh_label("cap_ok");
        builder.emit_branch(
            PatchKind::CBNZ,
            ok_label.clone(),
            Some(8),
            None,
            false,
        );
        builder.emit_branch(
            PatchKind::B,
            "security_violation".to_string(),
            None,
            None,
            false,
        );
        builder.label(&ok_label);

        Ok(())
    }

    fn emit_capability_body(
        builder: &mut CodeBuilder,
        cap: &CapabilityDecl,
        _capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        match cap.name.as_str() {
            "load_muscle" => Self::emit_load_muscle_body(builder),
            "schedule" => Self::emit_schedule_body(builder),
            "emit_update" => Self::emit_emit_update_body(builder),
            _ => {
                builder.push_u32(0x52800000); // MOV W0, #0
                Ok(())
            }
        }
    }

    fn emit_load_muscle_body(builder: &mut CodeBuilder) -> Result<(), CompileError> {
        builder.push_u32(0xF94007E0); // LDR X0, [SP, #0]
        builder.emit_branch(
            PatchKind::BL,
            "builtin_muscle_loader".to_string(),
            None,
            None,
            false,
        );
        builder.push_u32(0xF9000BE0); // STR X0, [SP, #16]
        Ok(())
    }

    fn emit_schedule_body(builder: &mut CodeBuilder) -> Result<(), CompileError> {
        builder.push_u32(0xF94007E0); // LDR X0, [SP, #0]
        builder.push_u32(0xB9400BE1); // LDR W1, [SP, #8]
        builder.emit_branch(
            PatchKind::BL,
            "builtin_scheduler".to_string(),
            None,
            None,
            false,
        );
        Ok(())
    }

    fn emit_emit_update_body(builder: &mut CodeBuilder) -> Result<(), CompileError> {
        builder.push_u32(0xF94007E0); // LDR X0, [SP, #0]
        builder.emit_branch(
            PatchKind::BL,
            "builtin_lattice_emitter".to_string(),
            None,
            None,
            false,
        );
        Ok(())
    }

    fn emit_builtin_functions(builder: &mut CodeBuilder) {
        builder.label("builtin_verify_attestation");
        builder.push_u32(encode_mov_imm_w(0, 1));
        builder.push_u32(0xD65F03C0); // RET

        builder.label("builtin_symbiote_process_update");
        builder.push_u32(encode_mov_imm_w(0, 0));
        builder.push_u32(0xD65F03C0); // RET

        builder.label("builtin_self_check_failed");
        builder.push_u32(encode_mov_imm_w(0, 0));
        builder.push_u32(0xD65F03C0); // RET

        builder.label("builtin_muscle_loader");
        builder.push_u32(0xD65F03C0); // RET (returns input X0)

        builder.label("builtin_scheduler");
        builder.push_u32(encode_mov_imm_w(0, 0));
        builder.push_u32(0xD65F03C0); // RET

        builder.label("builtin_lattice_emitter");
        builder.push_u32(encode_mov_imm_w(0, 0));
        builder.push_u32(0xD65F03C0); // RET
    }

    fn emit_event_handlers(
        builder: &mut CodeBuilder,
        rules: &[Rule],
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        for (i, rule) in rules.iter().enumerate() {
            builder.label(&handler_label(i));
            Self::emit_rule_handler(builder, rule, program, capability_names)?;
        }
        Ok(())
    }

    fn emit_rule_handler(
        builder: &mut CodeBuilder,
        rule: &Rule,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        builder.push_u32(0xD10043FF); // SUB SP, SP, #16

        for statement in &rule.body {
            Self::emit_statement(builder, statement, program, capability_names)?;
        }

        builder.push_u32(encode_mov_imm_w(0, 1)); // MOV W0, #1
        builder.push_u32(0x910043FF); // ADD SP, SP, #16
        builder.push_u32(0xD65F03C0); // RET
        Ok(())
    }

    fn emit_statement(
        builder: &mut CodeBuilder,
        statement: &Statement,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        match statement {
            Statement::Verify(stmt) => Self::emit_verify_statement(builder, stmt, program, capability_names),
            Statement::Let(stmt) => Self::emit_let_statement(builder, stmt, program, capability_names),
            Statement::If(stmt) => Self::emit_if_statement(builder, stmt, program, capability_names),
            Statement::Emit(stmt) => Self::emit_emit_statement(builder, stmt, program, capability_names),
            Statement::Schedule(stmt) => Self::emit_schedule_statement(builder, stmt, program, capability_names),
            Statement::Unschedule(stmt) => Self::emit_unschedule_statement(builder, stmt, program, capability_names),
            Statement::Expr(expr) => Self::emit_expression(builder, expr, program, capability_names),
        }
    }

    fn emit_verify_statement(
        builder: &mut CodeBuilder,
        stmt: &VerifyStmt,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        Self::emit_expression(builder, &stmt.condition, program, capability_names)?;

        let ok_label = builder.fresh_label("verify_ok");
        builder.emit_branch(PatchKind::CBNZ, ok_label.clone(), Some(0), None, false);
        builder.emit_branch(
            PatchKind::B,
            "security_violation".to_string(),
            None,
            None,
            false,
        );
        builder.label(&ok_label);

        Ok(())
    }

    fn emit_let_statement(
        builder: &mut CodeBuilder,
        stmt: &LetStmt,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        if let Some(expr) = &stmt.value {
            Self::emit_expression(builder, expr, program, capability_names)?;
        }
        Ok(())
    }

    fn emit_if_statement(
        builder: &mut CodeBuilder,
        stmt: &IfStmt,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        Self::emit_expression(builder, &stmt.condition, program, capability_names)?;

        let else_label = builder.fresh_label("if_else");
        let end_label = builder.fresh_label("if_end");

        if stmt.else_branch.is_some() {
            builder.emit_branch(PatchKind::CBZ, else_label.clone(), Some(0), None, false);
            for then_stmt in &stmt.then_branch {
                Self::emit_statement(builder, then_stmt, program, capability_names)?;
            }
            builder.emit_branch(PatchKind::B, end_label.clone(), None, None, false);
            builder.label(&else_label);
            if let Some(else_branch) = &stmt.else_branch {
                for else_stmt in else_branch {
                    Self::emit_statement(builder, else_stmt, program, capability_names)?;
                }
            }
            builder.label(&end_label);
        } else {
            builder.emit_branch(PatchKind::CBZ, end_label.clone(), Some(0), None, false);
            for then_stmt in &stmt.then_branch {
                Self::emit_statement(builder, then_stmt, program, capability_names)?;
            }
            builder.label(&end_label);
        }

        Ok(())
    }

    fn emit_emit_statement(
        builder: &mut CodeBuilder,
        stmt: &EmitStmt,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        for (i, arg) in stmt.arguments.iter().enumerate() {
            if i < 8 {
                Self::emit_expression(builder, arg, program, capability_names)?;
                if i > 0 {
                    let mov_instr = match i {
                        1 => 0xAA0003E1, // MOV X1, X0
                        2 => 0xAA0003E2, // MOV X2, X0
                        _ => 0,
                    };
                    if mov_instr != 0 {
                        builder.push_u32(mov_instr);
                    }
                }
            }
        }

        if capability_names.contains("emit_update") {
            builder.emit_branch(
                PatchKind::BL,
                cap_label("emit_update"),
                None,
                None,
                false,
            );
        } else {
            builder.emit_branch(
                PatchKind::B,
                "security_violation".to_string(),
                None,
                None,
                false,
            );
        }

        Ok(())
    }

    fn emit_schedule_statement(
        builder: &mut CodeBuilder,
        stmt: &ScheduleStmt,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        Self::emit_expression(builder, &stmt.muscle, program, capability_names)?;

        if let Literal::Integer(priority) = &stmt.priority {
            let imm = (*priority as u16).min(u16::MAX);
            builder.push_u32(encode_mov_imm_w(1, imm));
        }

        if capability_names.contains("schedule") {
            builder.emit_branch(
                PatchKind::BL,
                cap_label("schedule"),
                None,
                None,
                false,
            );
        } else {
            builder.emit_branch(
                PatchKind::B,
                "security_violation".to_string(),
                None,
                None,
                false,
            );
        }

        Ok(())
    }

    fn emit_unschedule_statement(
        builder: &mut CodeBuilder,
        stmt: &UnscheduleStmt,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        Self::emit_expression(builder, &stmt.muscle_id, program, capability_names)?;

        if capability_names.contains("schedule") {
            builder.emit_branch(
                PatchKind::BL,
                cap_label("schedule"),
                None,
                None,
                false,
            );
        } else {
            builder.emit_branch(
                PatchKind::B,
                "security_violation".to_string(),
                None,
                None,
                false,
            );
        }

        Ok(())
    }

    fn emit_expression(
        builder: &mut CodeBuilder,
        expr: &Expression,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        match expr {
            Expression::Literal(literal) => Self::emit_literal(builder, literal),
            Expression::Variable(var) => Self::emit_variable(builder, var),
            Expression::SelfRef(self_ref) => Self::emit_self_reference(builder, self_ref),
            Expression::Call(call) => Self::emit_call_expression(builder, call, program, capability_names),
            Expression::FieldAccess(access) => {
                let call_expr = CallExpr {
                    function: format!("{}.{}", access.object, access.field),
                    arguments: Vec::new(),
                };
                Self::emit_call_expression(builder, &call_expr, program, capability_names)
            }
            Expression::Binary(bin) => Self::emit_binary_expression(builder, bin, program, capability_names),
        }
    }

    fn emit_literal(builder: &mut CodeBuilder, literal: &Literal) -> Result<(), CompileError> {
        match literal {
            Literal::Hex(_) => {
                if let Some(value) = literal.as_u64() {
                    if value <= 0xFFFF {
                        builder.push_u32(encode_mov_imm_w(0, value as u16));
                    } else {
                        builder.push_bytes(&[0xE0, 0x03, 0x00, 0x90, 0x00, 0x00, 0x40, 0xF9]);
                    }
                } else {
                    builder.push_u32(encode_mov_imm_w(0, 0));
                }
            }
            Literal::Integer(n) => {
                if *n <= 0xFFFF {
                    builder.push_u32(encode_mov_imm_w(0, *n as u16));
                } else {
                    builder.push_bytes(&[0xE0, 0x03, 0x00, 0x90, 0x00, 0x00, 0x40, 0xF9]);
                }
            }
            Literal::String(_) => {
                builder.push_bytes(&[0xE0, 0x03, 0x00, 0x90]);
            }
        }
        Ok(())
    }

    fn emit_variable(builder: &mut CodeBuilder, _var: &str) -> Result<(), CompileError> {
        builder.push_u32(0xF94007E0); // LDR X0, [SP, #0]
        Ok(())
    }

    fn emit_self_reference(builder: &mut CodeBuilder, self_ref: &SelfReference) -> Result<(), CompileError> {
        match self_ref {
            SelfReference::Id => {
                builder.push_bytes(&[0xE0, 0x03, 0x00, 0x90, 0x00, 0x10, 0x40, 0xF9]);
            }
            SelfReference::Version => {
                builder.push_bytes(&[0xE0, 0x03, 0x00, 0x90, 0x00, 0x18, 0x40, 0xF9]);
            }
        }
        Ok(())
    }

    fn emit_call_expression(
        builder: &mut CodeBuilder,
        call: &CallExpr,
        _program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        for (i, arg) in call.arguments.iter().enumerate() {
            if i < 8 {
                Self::emit_expression(builder, arg, _program, capability_names)?;
                if i > 0 {
                    let mov_instr = match i {
                        1 => 0xAA0003E1,
                        2 => 0xAA0003E2,
                        _ => 0,
                    };
                    if mov_instr != 0 {
                        builder.push_u32(mov_instr);
                    }
                }
            }
        }

        if let Some(label) = resolve_call_target(&call.function, capability_names) {
            builder.emit_branch(PatchKind::BL, label, None, None, false);
        } else {
            builder.emit_branch(
                PatchKind::B,
                "security_violation".to_string(),
                None,
                None,
                false,
            );
        }

        Ok(())
    }

    fn emit_binary_expression(
        builder: &mut CodeBuilder,
        bin: &BinaryExpr,
        program: &Program,
        capability_names: &HashSet<String>,
    ) -> Result<(), CompileError> {
        Self::emit_expression(builder, &bin.left, program, capability_names)?;
        builder.push_u32(0xAA0003E8); // MOV X8, X0
        Self::emit_expression(builder, &bin.right, program, capability_names)?;
        builder.push_u32(0xAA0003E9); // MOV X9, X0

        match bin.op {
            BinaryOperator::Eq => {
                builder.push_u32(0xEB090108); // CMP X8, X9
                builder.push_u32(0x1A9F03E0); // CSET W0, EQ
            }
            BinaryOperator::Ne => {
                builder.push_u32(0xEB090108); // CMP X8, X9
                builder.push_u32(0x1A9F07E0); // CSET W0, NE
            }
            BinaryOperator::Add => {
                builder.push_u32(0x8B090100); // ADD X0, X8, X9
            }
            _ => {
                builder.push_u32(encode_mov_imm_w(0, 0));
            }
        }

        Ok(())
    }

    fn generate_data_section(program: &Program) -> Vec<u8> {
        let mut data = Vec::new();

        while data.len() % 8 != 0 {
            data.push(0x00);
        }

        for decl in &program.declarations {
            if let Declaration::Const(const_decl) = decl {
                data.extend(&const_decl.value.to_bytes());
                while data.len() % 8 != 0 {
                    data.push(0x00);
                }
            }
        }

        data.extend(&[0xEAu8; 32]);
        data.extend(&0xFFFF_FFFF_FFFF_FFFFu64.to_le_bytes());
        data.extend(&1u64.to_le_bytes());

        data
    }

    fn generate_capability_tables(program: &Program) -> Vec<u8> {
        let mut tables = Vec::new();
        let mut capability_bits = 0u64;

        for decl in &program.declarations {
            if let Declaration::Capability(cap) = decl {
                let bit_position = Self::capability_bit_position(&cap.name);
                capability_bits |= 1 << bit_position;
            }
        }

        tables.extend(&capability_bits.to_le_bytes());
        tables
    }

    fn event_to_id(event: &Event) -> u8 {
        match event {
            Event::OnBoot => 0,
            Event::OnLatticeUpdate { .. } => 1,
            Event::OnTimer1Hz => 2,
            Event::OnSelfIntegrityFailure => 3,
            Event::Custom(_) => 4,
        }
    }

    fn capability_offset(cap_name: &str) -> u8 {
        match cap_name {
            "load_muscle" => 0,
            "schedule" => 1,
            "emit_update" => 2,
            _ => 255,
        }
    }

    fn capability_bit_position(cap_name: &str) -> u8 {
        match cap_name {
            "load_muscle" => 0,
            "schedule" => 1,
            "emit_update" => 2,
            _ => 63,
        }
    }
}

fn cap_label(name: &str) -> String {
    format!("cap_{}", name)
}

fn handler_label(index: usize) -> String {
    format!("handler_{}", index)
}

fn resolve_call_target(name: &str, capability_names: &HashSet<String>) -> Option<String> {
    if capability_names.contains(name) {
        return Some(cap_label(name));
    }

    match name {
        "hardware_attestation.verify" => Some("builtin_verify_attestation".to_string()),
        "symbiote.process" | "symbiote.process_update" => {
            Some("builtin_symbiote_process_update".to_string())
        }
        "referee.self_check_failed" => Some("builtin_self_check_failed".to_string()),
        _ => None,
    }
}
