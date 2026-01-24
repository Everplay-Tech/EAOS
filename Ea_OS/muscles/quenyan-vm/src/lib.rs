#![no_std]

extern crate alloc;
use alloc::vec::Vec;
use alloc::string::{String, ToString};
use alloc::format;

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Opcode {
    /// Load immediate value into register: [0x01, reg, val(f64)]
    LoadReg = 0x01,
    /// Add: dest = src1 + src2: [0x02, dest, src1, src2]
    Add = 0x02,
    /// Sub: dest = src1 - src2: [0x03, dest, src1, src2]
    Sub = 0x03,
    /// Mul: dest = src1 * src2: [0x04, dest, src1, src2]
    Mul = 0x04,
    /// Div: dest = src1 / src2: [0x05, dest, src1, src2]
    Div = 0x05,
    /// Compare: reg1 vs reg2 (Sets flags): [0x06, reg1, reg2]
    Cmp = 0x06,
    /// Jump Unconditional: [0x07, target(u16)]
    Jmp = 0x07,
    /// Jump if Greater: [0x08, target(u16)]
    JmpIfGt = 0x08,
    /// Jump if Less: [0x09, target(u16)]
    JmpIfLt = 0x09,
    /// Return value from register: [0xFF, reg]
    Return = 0xFF,
}

#[derive(Default)]
struct Flags {
    gt: bool,
    lt: bool,
    eq: bool,
}

pub struct QuenyanVM {
    /// 16 General Purpose Registers (f64)
    registers: [f64; 16],
    /// Comparison flags
    flags: Flags,
}

impl Default for QuenyanVM {
    fn default() -> Self {
        Self::new()
    }
}

impl QuenyanVM {
    pub fn new() -> Self {
        Self { 
            registers: [0.0; 16],
            flags: Flags::default(),
        }
    }

    /// Execute bytecode. Returns the value of the register specified in Return opcode.
    pub fn execute(&mut self, bytecode: &[u8]) -> Result<f64, String> {
        let mut pc = 0;
        let mut cycles = 0;
        const MAX_CYCLES: u32 = 10000; 

        while pc < bytecode.len() {
            if cycles > MAX_CYCLES {
                return Err("Energy exhaustion (timeout)".to_string());
            }
            cycles += 1;

            let op = bytecode[pc];
            pc += 1;

            match op {
                0x01 => { // LoadReg reg, val
                    if pc + 9 > bytecode.len() { return Err("Truncated bytecode".to_string()); }
                    let reg = bytecode[pc] as usize;
                    if reg >= 16 { return Err("Invalid register".to_string()); }
                    let val_bytes: [u8; 8] = bytecode[pc+1..pc+9].try_into().unwrap();
                    let val = f64::from_le_bytes(val_bytes);
                    self.registers[reg] = val;
                    pc += 9;
                },
                0x02 => self.binary_op(bytecode, &mut pc, |a, b| a + b)?,
                0x03 => self.binary_op(bytecode, &mut pc, |a, b| a - b)?,
                0x04 => self.binary_op(bytecode, &mut pc, |a, b| a * b)?,
                0x05 => { // Div with check
                    if pc + 3 > bytecode.len() { return Err("Truncated bytecode".to_string()); }
                    let dest = bytecode[pc] as usize;
                    let src1 = bytecode[pc+1] as usize;
                    let src2 = bytecode[pc+2] as usize;
                    pc += 3;
                    
                    if dest >= 16 || src1 >= 16 || src2 >= 16 { return Err("Invalid register".to_string()); }
                    let b = self.registers[src2];
                    if b == 0.0 { return Err("Division by zero".to_string()); }
                    self.registers[dest] = self.registers[src1] / b;
                },
                0x06 => { // Cmp
                    if pc + 2 > bytecode.len() { return Err("Truncated bytecode".to_string()); }
                    let r1 = bytecode[pc] as usize;
                    let r2 = bytecode[pc+1] as usize;
                    pc += 2;
                    if r1 >= 16 || r2 >= 16 { return Err("Invalid register".to_string()); }
                    
                    let a = self.registers[r1];
                    let b = self.registers[r2];
                    self.flags.gt = a > b;
                    self.flags.lt = a < b;
                    self.flags.eq = (a - b).abs() < f64::EPSILON;
                },
                0x07 => self.jump(bytecode, &mut pc, true)?, // Unconditional
                0x08 => self.jump(bytecode, &mut pc, self.flags.gt)?,
                0x09 => self.jump(bytecode, &mut pc, self.flags.lt)?,
                0xFF => { // Return
                    if pc + 1 > bytecode.len() { return Err("Truncated bytecode".to_string()); }
                    let reg = bytecode[pc] as usize;
                    if reg >= 16 { return Err("Invalid register".to_string()); }
                    return Ok(self.registers[reg]);
                },
                _ => return Err(format!("Unknown opcode: {:02X}", op)),
            }
        }
        
        Err("End of bytecode without return".to_string())
    }

    fn binary_op<F>(&mut self, bytecode: &[u8], pc: &mut usize, op: F) -> Result<(), String> 
    where F: Fn(f64, f64) -> f64 {
        if *pc + 3 > bytecode.len() { return Err("Truncated bytecode".to_string()); }
        let dest = bytecode[*pc] as usize;
        let src1 = bytecode[*pc+1] as usize;
        let src2 = bytecode[*pc+2] as usize;
        *pc += 3;
        
        if dest >= 16 || src1 >= 16 || src2 >= 16 { return Err("Invalid register".to_string()); }
        self.registers[dest] = op(self.registers[src1], self.registers[src2]);
        Ok(())
    }

    fn jump(&mut self, bytecode: &[u8], pc: &mut usize, condition: bool) -> Result<(), String> {
        if *pc + 2 > bytecode.len() { return Err("Truncated bytecode".to_string()); }
        let target = u16::from_le_bytes(bytecode[*pc..*pc+2].try_into().unwrap()) as usize;
        *pc += 2;
        
        if condition {
            if target >= bytecode.len() { return Err("Jump out of bounds".to_string()); }
            *pc = target;
        }
        Ok(())
    }
}

/// Helper to build bytecode (Assembler)
pub struct Assembler {
    code: Vec<u8>,
}

impl Default for Assembler {
    fn default() -> Self {
        Self::new()
    }
}

impl Assembler {
    pub fn new() -> Self {
        Self { code: Vec::new() }
    }

    pub fn current_offset(&self) -> u16 {
        self.code.len() as u16
    }

    pub fn load_reg(&mut self, reg: u8, val: f64) {
        self.code.push(Opcode::LoadReg as u8);
        self.code.push(reg);
        self.code.extend_from_slice(&val.to_le_bytes());
    }

    pub fn add(&mut self, dest: u8, src1: u8, src2: u8) {
        self.code.push(Opcode::Add as u8);
        self.code.push(dest);
        self.code.push(src1);
        self.code.push(src2);
    }

    pub fn sub(&mut self, dest: u8, src1: u8, src2: u8) {
        self.code.push(Opcode::Sub as u8);
        self.code.push(dest);
        self.code.push(src1);
        self.code.push(src2);
    }

    pub fn mul(&mut self, dest: u8, src1: u8, src2: u8) {
        self.code.push(Opcode::Mul as u8);
        self.code.push(dest);
        self.code.push(src1);
        self.code.push(src2);
    }

    pub fn div(&mut self, dest: u8, src1: u8, src2: u8) {
        self.code.push(Opcode::Div as u8);
        self.code.push(dest);
        self.code.push(src1);
        self.code.push(src2);
    }

    pub fn cmp(&mut self, r1: u8, r2: u8) {
        self.code.push(Opcode::Cmp as u8);
        self.code.push(r1);
        self.code.push(r2);
    }

    pub fn jmp(&mut self, target: u16) {
        self.code.push(Opcode::Jmp as u8);
        self.code.extend_from_slice(&target.to_le_bytes());
    }

    pub fn jmp_if_gt(&mut self, target: u16) {
        self.code.push(Opcode::JmpIfGt as u8);
        self.code.extend_from_slice(&target.to_le_bytes());
    }

    pub fn jmp_if_lt(&mut self, target: u16) {
        self.code.push(Opcode::JmpIfLt as u8);
        self.code.extend_from_slice(&target.to_le_bytes());
    }

    pub fn ret(&mut self, reg: u8) {
        self.code.push(Opcode::Return as u8);
        self.code.push(reg);
    }

    pub fn finish(self) -> Vec<u8> {
        self.code
    }
}

// Recursive Descent Parser for arithmetic
struct Parser {
    tokens: Vec<Token>,
    pos: usize,
    asm: Assembler,
    next_reg: u8,
}

impl Parser {
    fn new(tokens: Vec<Token>) -> Self {
        Self { tokens, pos: 0, asm: Assembler::new(), next_reg: 0 }
    }

    fn alloc_reg(&mut self) -> u8 {
        let r = self.next_reg;
        self.next_reg += 1;
        if self.next_reg >= 16 { 
            // In a real system we'd spill to stack, but for V1 we panic/error
            // Since we can't panic in no_std without abort, we handle it?
            // Just wrap in 16.
            return 15; 
        }
        r
    }

    fn free_reg(&mut self) {
        if self.next_reg > 0 { self.next_reg -= 1; }
    }

    fn peek(&self) -> Option<&Token> {
        self.tokens.get(self.pos)
    }

    fn advance(&mut self) {
        self.pos += 1;
    }

    fn parse(&mut self) -> Vec<u8> {
        let result_reg = self.expression();
        self.asm.ret(result_reg);
        let asm = core::mem::replace(&mut self.asm, Assembler::new());
        asm.finish()
    }

    fn expression(&mut self) -> u8 {
        let left = self.term();

        while let Some(Token::Op(op)) = self.peek() {
            if *op == '+' || *op == '-' {
                let op_char = *op;
                self.advance();
                let right = self.term();
                match op_char {
                    '+' => self.asm.add(left, left, right),
                    '-' => self.asm.sub(left, left, right),
                    _ => {}
                }
                self.free_reg(); // Release 'right' register
            } else {
                break;
            }
        }
        left
    }

    fn term(&mut self) -> u8 {
        let left = self.factor();

        while let Some(Token::Op(op)) = self.peek() {
            if *op == '*' || *op == '/' {
                let op_char = *op;
                self.advance();
                let right = self.factor();
                match op_char {
                    '*' => self.asm.mul(left, left, right),
                    '/' => self.asm.div(left, left, right),
                    _ => {}
                }
                self.free_reg();
            } else {
                break;
            }
        }
        left
    }

    fn factor(&mut self) -> u8 {
        if let Some(Token::Num(n)) = self.peek() {
            let val = *n;
            self.advance();
            let reg = self.alloc_reg();
            self.asm.load_reg(reg, val);
            reg
        } else if let Some(Token::Op('(')) = self.peek() {
            self.advance();
            let reg = self.expression();
            if let Some(Token::Op(')')) = self.peek() {
                self.advance();
            }
            reg
        } else {
            0 // Should handle error
        }
    }
}

pub struct Compiler;

impl Compiler {
    pub fn compile(source: &str) -> Vec<u8> {
        let tokens = tokenize(source);
        if tokens.is_empty() { return Vec::new(); }
        let mut parser = Parser::new(tokens);
        parser.parse()
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum Token {
    Num(f64),
    Op(char),
}

fn tokenize(s: &str) -> Vec<Token> {
    let mut tokens = Vec::new();
    let mut chars = s.chars().peekable();
    
    while let Some(&c) = chars.peek() {
        if c.is_ascii_digit() || c == '.' {
            let mut num_str = String::new();
            while let Some(&d) = chars.peek() {
                if d.is_ascii_digit() || d == '.' {
                    num_str.push(d);
                    chars.next();
                } else {
                    break;
                }
            }
            if let Ok(n) = num_str.parse::<f64>() {
                tokens.push(Token::Num(n));
            }
        } else if "+-*/()".contains(c) {
            tokens.push(Token::Op(c));
            chars.next();
        } else {
            chars.next(); // Skip whitespace
        }
    }
    tokens
}
