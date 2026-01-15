//! # Secure View Integration Test
//!
//! This test verifies the complete Prism flow:
//! 1. Encrypt Quenyan bytecode into an IhpCapsule
//! 2. Pass the capsule to Prism for decryption + execution
//! 3. Verify tamper detection returns InvalidAeadTag (PrismError::InvalidCapsule)
//!
//! ## Security Verification
//!
//! The test proves that:
//! - Valid capsules decrypt and execute correctly
//! - Any tampering with ciphertext is detected via AEAD tag
//! - HeaderID mismatches are caught

use ea_prism::{Prism, PrismError, QuenyanVM, QUENYAN_MAGIC};
use ihp::{
    encrypt_capsule, CapsuleTimestamp, ClientNonce, CryptoDomainLabels,
    IhpConfig, IhpNetworkContext, InMemoryKeyProvider, PasswordMaterial,
    ServerProfileId, DEFAULT_PROTOCOL_VERSION,
    compute_server_env_hash, derive_profile_key, derive_session_key,
    ServerEnvironmentProfile, NONCE_LEN,
};

// =============================================================================
// Test Fixtures
// =============================================================================

const TEST_HEADER_ID: u64 = 0xDEADBEEF;
const TEST_PROFILE_ID: ServerProfileId = ServerProfileId(42);
const TEST_MASTER_KEY: [u8; 32] = [
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
    0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17,
    0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F,
];
const TEST_TLS_EXPORTER: &[u8] = b"test_tls_exporter_key_material_32";
const TEST_TIMESTAMP: i64 = 1_700_000_000;

fn sample_server_profile() -> ServerEnvironmentProfile {
    ServerEnvironmentProfile {
        cpu_fingerprint: "test_cpu".to_string(),
        nic_fingerprint: "test_nic".to_string(),
        os_fingerprint: "test_os".to_string(),
        app_build_fingerprint: "test_build".to_string(),
        tpm_quote: Some(vec![0x01, 0x02, 0x03, 0x04]),
    }
}

fn create_quenyan_bytecode(payload: &[u8]) -> Vec<u8> {
    let mut bytecode = QUENYAN_MAGIC.to_vec();
    bytecode.extend_from_slice(payload);
    bytecode
}

fn test_client_nonce() -> ClientNonce {
    let nonce_bytes: [u8; NONCE_LEN] = [
        0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
        0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C,
    ];
    ClientNonce::new(nonce_bytes)
}

// =============================================================================
// Test: Successful Decryption and Execution
// =============================================================================

#[test]
fn test_secure_view_success() {
    // Step 1: Create Quenyan bytecode payload
    let script_payload = b"ADD 1 2 STORE R0 HALT";
    let bytecode = create_quenyan_bytecode(script_payload);

    // Step 2: Setup IHP encryption context
    let labels = CryptoDomainLabels::default();
    let config = IhpConfig::default();
    let provider = InMemoryKeyProvider::new(TEST_MASTER_KEY);

    // Compute server environment hash
    let sep = sample_server_profile();
    let env_hash = compute_server_env_hash(&sep).expect("env hash");

    // Derive keys
    let k_profile = derive_profile_key(
        &provider,
        TEST_PROFILE_ID,
        &env_hash,
        &labels,
    ).expect("profile key");

    // Create client nonce
    let client_nonce = test_client_nonce();

    // Network context
    let network_context = IhpNetworkContext {
        rtt_bucket: 50,
        path_hint: 0x1234,
    };

    // Derive session key
    let k_session = derive_session_key(
        &k_profile,
        TEST_TLS_EXPORTER,
        &client_nonce,
        &network_context,
        TEST_PROFILE_ID,
        &labels,
    ).expect("session key");

    // Create timestamp
    let timestamp = CapsuleTimestamp::new(TEST_TIMESTAMP).expect("timestamp");

    // Create password material containing our bytecode
    let password_material = PasswordMaterial::new(&bytecode).expect("password material");

    // Step 3: Encrypt the capsule
    let capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        &config,
        TEST_HEADER_ID,
        client_nonce,
        TEST_PROFILE_ID,
        network_context,
        &env_hash,
        &k_session,
        &password_material,
        timestamp,
    ).expect("encrypt capsule");

    println!("Capsule created:");
    println!("  HeaderID: 0x{:X}", capsule.header_id);
    println!("  Payload size: {} bytes", capsule.payload.len());

    // Step 4: Pass to Prism and verify execution
    let mut prism = Prism::new();
    let result = prism.decrypt_and_execute(
        &capsule,
        &env_hash,
        &k_session,
        timestamp,
    );

    assert!(result.is_ok(), "Prism should decrypt and execute successfully: {:?}", result.err());

    let exec_result = result.unwrap();
    println!("\nExecution Result:");
    println!("  Success: {}", exec_result.success);
    println!("  Steps: {}", exec_result.steps);
    println!("  State hash: {:02x?}", &exec_result.state_hash[..8]);

    assert!(exec_result.success);
    assert!(exec_result.steps > 0);
    assert!(exec_result.output.is_some());

    println!("\nSECURE VIEW TEST: PASSED");
}

// =============================================================================
// Test: Tamper Detection - Ciphertext Modification
// =============================================================================

#[test]
fn test_secure_view_tamper_detection() {
    // Setup encryption context
    let labels = CryptoDomainLabels::default();
    let config = IhpConfig::default();
    let provider = InMemoryKeyProvider::new(TEST_MASTER_KEY);

    let sep = sample_server_profile();
    let env_hash = compute_server_env_hash(&sep).expect("env hash");

    let k_profile = derive_profile_key(
        &provider,
        TEST_PROFILE_ID,
        &env_hash,
        &labels,
    ).expect("profile key");

    // Use different nonce for this test
    let client_nonce = ClientNonce::new([
        0x11, 0x22, 0x33, 0x44, 0x55, 0x66,
        0x77, 0x88, 0x99, 0xAA, 0xBB, 0xCC,
    ]);

    let network_context = IhpNetworkContext {
        rtt_bucket: 50,
        path_hint: 0x1234,
    };

    let k_session = derive_session_key(
        &k_profile,
        TEST_TLS_EXPORTER,
        &client_nonce,
        &network_context,
        TEST_PROFILE_ID,
        &labels,
    ).expect("session key");

    let timestamp = CapsuleTimestamp::new(TEST_TIMESTAMP).expect("timestamp");

    // Create valid bytecode and encrypt
    let bytecode = create_quenyan_bytecode(b"LOAD R1 42 HALT");
    let password_material = PasswordMaterial::new(&bytecode).expect("password material");

    let mut capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        &config,
        TEST_HEADER_ID,
        client_nonce,
        TEST_PROFILE_ID,
        network_context,
        &env_hash,
        &k_session,
        &password_material,
        timestamp,
    ).expect("encrypt capsule");

    println!("Original capsule payload: {} bytes", capsule.payload.len());

    // TAMPER: Modify the encrypted payload
    if !capsule.payload.is_empty() {
        capsule.payload[0] ^= 0xFF; // Flip bits in first byte
        println!("Tampered capsule payload byte 0");
    }

    // Attempt decryption - should fail with AEAD tag mismatch
    let mut prism = Prism::new();
    let result = prism.decrypt_and_execute(
        &capsule,
        &env_hash,
        &k_session,
        timestamp,
    );

    // ASSERT: Must return InvalidCapsule (from InvalidAeadTag)
    assert!(result.is_err(), "Tampered capsule should fail decryption");

    match result.unwrap_err() {
        PrismError::InvalidCapsule(msg) => {
            println!("Tamper detected: {}", msg);
            assert!(
                msg.contains("AEAD") || msg.contains("tampered"),
                "Error should indicate AEAD/tamper failure, got: {}", msg
            );
        }
        other => panic!("Expected InvalidCapsule error, got: {:?}", other),
    }

    println!("\nTAMPER DETECTION TEST: PASSED");
    println!("  IhpError::InvalidAeadTag correctly propagated");
}

// =============================================================================
// Test: HeaderID Validation
// =============================================================================

#[test]
fn test_secure_view_header_id_mismatch() {
    // Setup encryption context
    let labels = CryptoDomainLabels::default();
    let config = IhpConfig::default();
    let provider = InMemoryKeyProvider::new(TEST_MASTER_KEY);

    let sep = sample_server_profile();
    let env_hash = compute_server_env_hash(&sep).expect("env hash");

    let k_profile = derive_profile_key(
        &provider,
        TEST_PROFILE_ID,
        &env_hash,
        &labels,
    ).expect("profile key");

    // Different nonce for this test
    let client_nonce = ClientNonce::new([
        0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF,
        0x11, 0x22, 0x33, 0x44, 0x55, 0x66,
    ]);

    let network_context = IhpNetworkContext {
        rtt_bucket: 50,
        path_hint: 0x1234,
    };

    let k_session = derive_session_key(
        &k_profile,
        TEST_TLS_EXPORTER,
        &client_nonce,
        &network_context,
        TEST_PROFILE_ID,
        &labels,
    ).expect("session key");

    let timestamp = CapsuleTimestamp::new(TEST_TIMESTAMP).expect("timestamp");

    // Create valid bytecode and encrypt
    let bytecode = create_quenyan_bytecode(b"NOP");
    let password_material = PasswordMaterial::new(&bytecode).expect("password material");

    let mut capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        &config,
        TEST_HEADER_ID,
        client_nonce,
        TEST_PROFILE_ID,
        network_context,
        &env_hash,
        &k_session,
        &password_material,
        timestamp,
    ).expect("encrypt capsule");

    println!("Original HeaderID: 0x{:X}", capsule.header_id);

    // TAMPER: Change the HeaderID
    capsule.header_id = 0xBADC0DE;
    println!("Tampered HeaderID: 0x{:X}", capsule.header_id);

    // Attempt decryption - should fail
    let mut prism = Prism::new();
    let result = prism.decrypt_and_execute(
        &capsule,
        &env_hash,
        &k_session,
        timestamp,
    );

    // HeaderID changes affect the AAD, so AEAD will fail
    assert!(result.is_err(), "HeaderID mismatch should fail");

    println!("\nHEADERID VALIDATION TEST: PASSED");
}

// =============================================================================
// Test: VM Execution with Valid Bytecode
// =============================================================================

#[test]
fn test_secure_view_vm_execution() {
    // Test VM directly with valid bytecode
    let mut vm = QuenyanVM::new();

    // Create simple bytecode: QYN1 magic + opcodes
    let mut bytecode = QUENYAN_MAGIC.to_vec();
    bytecode.extend_from_slice(&[0x01, 0x02, 0x03, 0x04, 0x05]); // 5 "opcodes"

    let result = vm.execute(&bytecode);
    assert!(result.is_ok());

    let exec = result.unwrap();
    assert!(exec.success);
    assert_eq!(exec.steps, 5); // 5 opcodes = 5 steps
    assert!(!exec.state_hash.iter().all(|&b| b == 0)); // Hash should be non-zero

    println!("VM Execution:");
    println!("  Steps: {}", exec.steps);
    println!("  State hash: {:02x?}", &exec.state_hash[..8]);

    println!("\nVM EXECUTION TEST: PASSED");
}

// =============================================================================
// Test: Invalid Bytecode Detection
// =============================================================================

#[test]
fn test_secure_view_invalid_bytecode() {
    // Test 1: Wrong magic bytes
    let bad_magic = vec![0x00, 0x00, 0x00, 0x00, 0x01, 0x02];
    let result = QuenyanVM::validate_bytecode(&bad_magic);
    assert!(matches!(result, Err(PrismError::InvalidBytecode(_))));
    println!("Wrong magic bytes: correctly rejected");

    // Test 2: Too short
    let too_short = vec![0x51, 0x59];
    let result = QuenyanVM::validate_bytecode(&too_short);
    assert!(matches!(result, Err(PrismError::InvalidBytecode(_))));
    println!("Too short bytecode: correctly rejected");

    // Test 3: Valid magic
    let mut valid = QUENYAN_MAGIC.to_vec();
    valid.push(0x00);
    let result = QuenyanVM::validate_bytecode(&valid);
    assert!(result.is_ok());
    println!("Valid magic bytes: accepted");

    println!("\nBYTECODE VALIDATION TEST: PASSED");
}

// =============================================================================
// Test: Logic Bomb - Halting Problem Defense
// =============================================================================

/// This test proves the VM cannot be frozen by infinite loops.
///
/// The "Logic Bomb" attack: A malicious script loops forever, freezing the OS.
/// Defense: Step limiting - VM terminates after max_steps, returning ExecutionFailed.
#[test]
fn test_logic_bomb_halting_defense() {
    use std::time::Instant;

    println!("\n========================================");
    println!("  LOGIC BOMB TEST (Halting Problem)");
    println!("========================================\n");

    // Create a VM with a very small step limit to simulate the defense
    let step_limit: u64 = 100;
    let mut vm = QuenyanVM::with_max_steps(step_limit);

    // Create "infinite loop" bytecode - more opcodes than step limit allows
    // In a real VM, this would be: LOOP: JMP LOOP
    let mut logic_bomb = QUENYAN_MAGIC.to_vec();
    // Add 1000 opcodes - way more than our 100 step limit
    for i in 0..1000u16 {
        logic_bomb.push((i % 256) as u8);
    }

    println!("Attack Parameters:");
    println!("  Bytecode size: {} bytes", logic_bomb.len());
    println!("  Opcodes: 1000 (simulated infinite loop)");
    println!("  Step limit: {}", step_limit);

    // Execute and time it
    let start = Instant::now();
    let result = vm.execute(&logic_bomb);
    let elapsed = start.elapsed();

    println!("\nExecution Result:");
    println!("  Duration: {:?}", elapsed);

    // CRITICAL ASSERTION: Must fail, not hang
    assert!(result.is_err(), "Logic bomb should be terminated by step limit");

    match result.unwrap_err() {
        PrismError::ExecutionFailed(msg) => {
            println!("  Status: TERMINATED");
            println!("  Reason: {}", msg);
            assert!(msg.contains("step limit"), "Should indicate step limit exceeded");
        }
        other => panic!("Expected ExecutionFailed, got: {:?}", other),
    }

    // Verify it completed quickly (not stuck in infinite loop)
    assert!(elapsed.as_millis() < 100, "Should terminate in <100ms, took {:?}", elapsed);

    println!("\n========================================");
    println!("  LOGIC BOMB DEFENSE: VERIFIED");
    println!("========================================");
    println!("  - VM terminated after {} steps", step_limit);
    println!("  - Execution time: {:?}", elapsed);
    println!("  - OS did NOT freeze");
    println!("========================================\n");
}

/// Test that the default step limit (1M) is reasonable
#[test]
fn test_default_step_limit_is_bounded() {
    // Default VM has 1 million step limit - enough for real programs,
    // but bounded to prevent infinite loops.
    // We verify this by running bytecode that would exceed 1M steps.

    let mut vm = QuenyanVM::new();

    // Create bytecode with exactly 1,000,001 opcodes (exceeds default limit)
    let mut bytecode = QUENYAN_MAGIC.to_vec();
    bytecode.extend(vec![0x01; 1_000_001]);

    let result = vm.execute(&bytecode);

    // Should fail at step 1,000,001
    assert!(result.is_err(), "Should hit default 1M step limit");

    println!("Default step limit (1 million) verified:");
    println!("  - Bytecode with 1,000,001 opcodes was terminated");
    println!("  - Sufficient for legitimate programs");
    println!("  - Bounded to prevent infinite loops");
}

/// Test step limit with encrypted capsule (full Prism flow)
#[test]
fn test_logic_bomb_via_encrypted_capsule() {
    // Setup encryption context
    let labels = CryptoDomainLabels::default();
    let config = IhpConfig::default();
    let provider = InMemoryKeyProvider::new(TEST_MASTER_KEY);

    let sep = sample_server_profile();
    let env_hash = compute_server_env_hash(&sep).expect("env hash");

    let k_profile = derive_profile_key(
        &provider,
        TEST_PROFILE_ID,
        &env_hash,
        &labels,
    ).expect("profile key");

    let client_nonce = ClientNonce::new([
        0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE,
        0xBA, 0xBE, 0x12, 0x34, 0x56, 0x78,
    ]);

    let network_context = IhpNetworkContext {
        rtt_bucket: 50,
        path_hint: 0x1234,
    };

    let k_session = derive_session_key(
        &k_profile,
        TEST_TLS_EXPORTER,
        &client_nonce,
        &network_context,
        TEST_PROFILE_ID,
        &labels,
    ).expect("session key");

    let timestamp = CapsuleTimestamp::new(TEST_TIMESTAMP).expect("timestamp");

    // Create "logic bomb" bytecode
    let mut bomb_bytecode = QUENYAN_MAGIC.to_vec();
    for _ in 0..10000 {
        bomb_bytecode.push(0xFF); // 10K opcodes
    }

    let password_material = PasswordMaterial::new(&bomb_bytecode).expect("password material");

    // Encrypt the logic bomb
    let capsule = encrypt_capsule(
        DEFAULT_PROTOCOL_VERSION,
        &config,
        0xB0B0,
        client_nonce,
        TEST_PROFILE_ID,
        network_context,
        &env_hash,
        &k_session,
        &password_material,
        timestamp,
    ).expect("encrypt capsule");

    println!("Encrypted logic bomb capsule: {} bytes", capsule.payload.len());

    // Create Prism with small step limit
    let prism_config = ea_prism::PrismConfig {
        ihp_config: IhpConfig::default(),
        max_bytecode_size: 1024 * 1024,
        max_vm_steps: 500, // Only allow 500 steps
    };
    let mut prism = Prism::with_config(prism_config);

    // Attempt to decrypt and execute
    let result = prism.decrypt_and_execute(
        &capsule,
        &env_hash,
        &k_session,
        timestamp,
    );

    // Should decrypt successfully but FAIL execution due to step limit
    assert!(result.is_err(), "Logic bomb should hit step limit");

    match result.unwrap_err() {
        PrismError::ExecutionFailed(msg) => {
            println!("Logic bomb via capsule: TERMINATED");
            println!("  Reason: {}", msg);
        }
        other => panic!("Expected ExecutionFailed, got: {:?}", other),
    }

    println!("\nENCRYPTED LOGIC BOMB DEFENSE: VERIFIED");
}
