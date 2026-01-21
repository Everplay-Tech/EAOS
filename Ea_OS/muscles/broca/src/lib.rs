#![no_std]

extern crate muscle_contract;
use muscle_contract::broca::{DirectorRequest, IntentOp};
use core::slice;
use core::str;

/// Entry Point: Transforms raw somatic bytes into Will.
/// Input: ptr to UART buffer. Output: DirectorRequest struct.
#[no_mangle]
pub extern "C" fn process_speech(input_ptr: *const u8, input_len: usize) -> DirectorRequest {
    // 1. Safety Boundary
    if input_ptr.is_null() || input_len == 0 {
        return error_req(IntentOp::NoOp);
    }
    let bytes = unsafe { slice::from_raw_parts(input_ptr, input_len) };

    // 2. Decode & Trim
    let text = match str::from_utf8(bytes) {
        Ok(s) => s.trim(),
        Err(_) => return error_req(IntentOp::Aphasia),
    };

    // 3. Tokenize (Zero-Alloc Iterator)
    let mut parts = text.split_ascii_whitespace();
    let verb = parts.next().unwrap_or("");

    // 4. Map Verb to Intent (Case-insensitive via manual check)
    if eq_ignore_case(verb, "LS") || eq_ignore_case(verb, "LIST") {
        req(IntentOp::Survey, 0, 0, "")
    } else if eq_ignore_case(verb, "READ") || eq_ignore_case(verb, "CAT") {
        let arg = parts.next().unwrap_or("0");
        let id = parse_hex(arg).unwrap_or(0);
        req(IntentOp::Recall, id, 0, "")
    } else if eq_ignore_case(verb, "SAVE") || eq_ignore_case(verb, "WRITE") {
        // usage: SAVE <filename>
        let filename = parts.next().unwrap_or("untitled");
        req(IntentOp::Memorize, 0, 0, filename)
    } else if eq_ignore_case(verb, "HUNT") || eq_ignore_case(verb, "GET") {
        // usage: HUNT <bookmark_id>
        let arg = parts.next().unwrap_or("0");
        let id = parse_decimal(arg).unwrap_or(0);
        req(IntentOp::Harvest, id, 0, "")
    } else if eq_ignore_case(verb, "BOOT") || eq_ignore_case(verb, "EXEC") {
        // usage: BOOT <muscle_name>
        let name = parts.next().unwrap_or("");
        req(IntentOp::Innervate, 0, 0, name)
    } else if verb.is_empty() {
        error_req(IntentOp::NoOp)
    } else {
        error_req(IntentOp::Aphasia)
    }
}

// --- Helpers ---

fn req(op: IntentOp, id: u64, param: u64, text: &str) -> DirectorRequest {
    let mut payload = [0u8; 64];
    let bytes = text.as_bytes();
    let len = core::cmp::min(bytes.len(), 64);
    payload[..len].copy_from_slice(&bytes[..len]);

    DirectorRequest {
        intent: op,
        target_id: id,
        param,
        payload,
        payload_len: len as u8,
    }
}

fn error_req(op: IntentOp) -> DirectorRequest {
    req(op, 0, 0, "")
}

fn eq_ignore_case(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }
    a.bytes().zip(b.bytes()).all(|(c1, c2)| c1.to_ascii_uppercase() == c2.to_ascii_uppercase())
}

fn parse_hex(s: &str) -> Option<u64> {
    let s = s.strip_prefix("0x").unwrap_or(s);
    let mut res: u64 = 0;
    for c in s.bytes() {
        res = res.checked_shl(4)?;
        let d = match c {
            b'0'..=b'9' => c - b'0',
            b'a'..=b'f' => c - b'a' + 10,
            b'A'..=b'F' => c - b'A' + 10,
            _ => return None,
        };
        res |= d as u64;
    }
    Some(res)
}

fn parse_decimal(s: &str) -> Option<u64> {
    let mut res: u64 = 0;
    for c in s.bytes() {
        if !c.is_ascii_digit() { return None; }
        res = res.checked_mul(10)?;
        res = res.checked_add((c - b'0') as u64)?;
    }
    Some(res)
}
