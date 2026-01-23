use ea_quenyan::{Assembler, QuenyanVM};
use ea_symbiote::SovereignBlob; // For persistence mock

#[test]
fn test_lazarus_trajectory() {
    println!("\n========================================");
    println!("  🧪 TEST SUITE: THE LAZARUS TRAJECTORY");
    println!("========================================\n");

    phase_1_complexity();
    phase_2_safety();
    phase_3_persistence();
}

fn phase_1_complexity() {
    println!("Phase 1: Complexity (The Descent)");
    
    // Build Bytecode
    let mut asm = Assembler::new();
    
    // Init Registers
    // 0=Alt, 1=Grav, 2=Vel, 3=Drag
    asm.load_reg(0, 10000.0);
    asm.load_reg(1, 10.0);
    asm.load_reg(2, 50.0);
    asm.load_reg(3, 2.0); // Also used as Divisor 2
    
    // LOOP_START (Offset: 40)
    let loop_start = asm.current_offset();
    assert_eq!(loop_start, 40, "Loop start offset mismatch");
    
    // Temp(4) = Vel(2) * Drag(3) => 50 * 2 = 100
    asm.mul(4, 2, 3);
    // Temp(4) = Temp(4) + Grav(1) => 100 + 10 = 110
    asm.add(4, 4, 1);
    // Alt(0) = Alt(0) - Temp(4) => 10000 - 110 = 9890
    asm.sub(0, 0, 4);
    
    // PARACHUTE_CHECK
    asm.load_reg(4, 5000.0);
    asm.cmp(0, 4); // Alt vs 5000
    
    // If Alt > 5000, Jmp to CHECK_GROUND (Skip Div)
    // Div is 4 bytes. Current is at 52 + 10 + 3 = 65. Jmp instr is 3. Next is 68.
    // Div is at 68. Check Ground at 72.
    asm.jmp_if_gt(72);
    
    // DEPLOY_PARACHUTE (Offset 68)
    // Vel(2) = Vel(2) / Drag(3) => 50 / 2 = 25
    asm.div(2, 2, 3);
    
    // CHECK_GROUND (Offset 72)
    assert_eq!(asm.current_offset(), 72, "Check ground offset mismatch");
    asm.load_reg(4, 0.0);
    asm.cmp(0, 4); // Alt vs 0
    
    // If Alt < 0, Jmp to CRASH
    // Current 72 + 10 + 3 = 85. JmpIf is 3. Next 88.
    // Jmp Loop is 3. Next 91. Crash is 91.
    asm.jmp_if_lt(91);
    
    // Loop
    asm.jmp(loop_start);
    
    // CRASH (Offset 91)
    assert_eq!(asm.current_offset(), 91, "Crash offset mismatch");
    asm.ret(0);
    
    let bytecode = asm.finish();
    println!("  Bytecode size: {} bytes", bytecode.len());
    
    // Execute
    let mut vm = QuenyanVM::new();
    let result = vm.execute(&bytecode);
    
    match result {
        Ok(alt) => {
            println!("  Touchdown Altitude: {}", alt);
            // It should be negative (just below 0) because we check < 0.
            // Loop runs until alt < 0.
            assert!(alt < 0.0, "Altitude should be below zero");
            assert!(alt > -200.0, "Altitude should not be too far below zero"); // Rough check
            println!("  Result: SURVIVED (Logic Valid)");
        }
        Err(e) => panic!("  CRASHED: VM Error: {}", e),
    }
}

fn phase_2_safety() {
    println!("\nPhase 2: Safety (The Solar Flare)");
    
    // 1. Division by Zero
    let mut asm = Assembler::new();
    asm.load_reg(0, 100.0);
    asm.load_reg(1, 0.0);
    asm.div(2, 0, 1); // 100 / 0
    asm.ret(2);
    
    let mut vm = QuenyanVM::new();
    let res = vm.execute(&asm.finish());
    assert!(res.is_err());
    println!("  Scenario 1 (Black Hole): PASSED (Caught '{}')", res.err().unwrap());
    
    // 2. Infinite Loop (Energy Exhaustion)
    let mut asm = Assembler::new();
    let start = asm.current_offset();
    asm.jmp(start); // Infinite Jump
    
    let mut vm = QuenyanVM::new();
    let res = vm.execute(&asm.finish());
    assert!(res.is_err());
    println!("  Scenario 2 (Infinite Mirror): PASSED (Caught '{}')", res.err().unwrap());
    
    // 3. Invalid Opcode
    let bad_code = vec![0xFF, 0x00, 0xAA]; // Return 0, then 0xAA (Garbage)
    // Wait, 0xFF is valid Return.
    // Let's execute just [0xAA]
    let bad_code = vec![0xAA];
    let mut vm = QuenyanVM::new();
    let res = vm.execute(&bad_code);
    assert!(res.is_err());
    println!("  Scenario 3 (Alien Word): PASSED (Caught '{}')", res.err().unwrap());
}

fn phase_3_persistence() {
    println!("\nPhase 3: Persistence (The Resurrection)");
    
    // 1. Imprint (Compile)
    // We use a simple logic: Return 42
    let mut asm = Assembler::new();
    asm.load_reg(0, 42.0);
    asm.ret(0);
    let original_code = asm.finish();
    
    // 2. Ossify (Save to Blob)
    // We simulate PermFS storage by wrapping in SovereignBlob
    let blob = SovereignBlob::new_logic(&original_code);
    let serialized = blob.serialize();
    
    println!("  Ossified to {} bytes", serialized.len());
    
    // 3. Lobotomy (Destroy VM, Keep Blob)
    let mut vm = QuenyanVM::new(); // New instance, empty state
    
    // 4. Rebirth (Load from Blob)
    let loaded_blob = SovereignBlob::deserialize(&serialized).unwrap();
    let restored_code = loaded_blob.payload;
    
    assert_eq!(original_code, restored_code, "Code mutation detected!");
    
    let result = vm.execute(&restored_code).unwrap();
    assert_eq!(result, 42.0);
    
    println!("  Resurrection: SUCCESS (Output: {})", result);
}
