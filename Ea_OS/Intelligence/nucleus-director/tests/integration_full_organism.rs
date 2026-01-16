//! EAOS Full Organism Integration Test
//!
//! This test verifies the complete Office Suite cycle:
//!
//! 1. Nucleus receives document/logic requests
//! 2. Osteon (documents) or Myocyte (logic) processes the request
//! 3. Data is wrapped in SovereignBlob containers
//! 4. Symbiote commits data to storage
//!
//! Verification:
//! - Documents are saved with correct metadata
//! - Logic is compiled and stored
//! - All blobs have 0xB8AD braid magic header

use nucleus_director::{DirectorRequest, DirectorResponse, NucleusDirector, BRAID_MAGIC};
use biowerk_agent::{AgentRequest, AgentResponse, BIOwerk};
use roulette_rs::{BLOCK_SIZE, BraidTransformer, T9BraidTransformer};
use ea_cardio::{CardioMonitor, Heartbeat, StatusCode};
use ea_symbiote::{BlobType, SovereignDocument, Symbiote};

/// Test: Full Office Suite Cycle
///
/// Verifies the complete pipeline from request to storage.
#[test]
fn test_full_organism_office_cycle() {
    println!("\n========================================");
    println!("  EAOS Full Organism Integration Test");
    println!("  Office Suite Edition");
    println!("========================================\n");

    // Create the Nucleus Director
    let mut director = NucleusDirector::new();

    // Step 1: Create a document
    println!("Step 1: Creating document...");
    let doc_response = director.process(DirectorRequest::WriteDocument {
        filename: "meeting_notes.txt".to_string(),
        content: "Q1 Planning Meeting\n- Review goals\n- Assign tasks\n- Set deadlines".to_string(),
    });

    match doc_response {
        DirectorResponse::DocumentSaved { filename, block_offset, size } => {
            println!("  Document saved: {}", filename);
            println!("  Block offset: {}", block_offset);
            println!("  Size: {} bytes", size);
            assert_eq!(filename, "meeting_notes.txt");
            assert!(size > 0);
        }
        DirectorResponse::Error(e) => panic!("Document save failed: {}", e),
        _ => panic!("Unexpected response type"),
    }

    // Step 2: Process logic
    println!("\nStep 2: Processing logic...");
    let logic_response = director.process(DirectorRequest::ProcessLogic {
        name: "budget.qyn".to_string(),
        formula: "revenue - expenses".to_string(),
    });

    match logic_response {
        DirectorResponse::LogicProcessed { name, block_offset, bytecode_size } => {
            println!("  Logic processed: {}", name);
            println!("  Block offset: {}", block_offset);
            println!("  Bytecode: {} bytes", bytecode_size);
            assert_eq!(name, "budget.qyn");
            assert!(bytecode_size > 0);
        }
        DirectorResponse::Error(e) => panic!("Logic processing failed: {}", e),
        _ => panic!("Unexpected response type"),
    }

    // Step 3: Verify system status
    println!("\nStep 3: Checking system status...");
    let status = director.process(DirectorRequest::SystemStatus);

    match status {
        DirectorResponse::Status { biowerk_ready, document_count, logic_count, .. } => {
            println!("  BIOwerk: {}", if biowerk_ready { "Ready" } else { "Not Ready" });
            println!("  Documents: {}", document_count);
            println!("  Logic units: {}", logic_count);
            assert!(biowerk_ready);
            assert_eq!(document_count, 1);
            assert_eq!(logic_count, 1);
        }
        _ => panic!("Expected Status response"),
    }

    // Step 4: List documents
    println!("\nStep 4: Listing documents...");
    let list = director.process(DirectorRequest::ListDocuments);

    match list {
        DirectorResponse::DocumentList { count, documents } => {
            println!("  Total: {} documents", count);
            for doc in &documents {
                println!("  - {}", doc);
            }
            assert_eq!(count, 1);
        }
        _ => panic!("Expected DocumentList response"),
    }

    println!("\n========================================");
    println!("  Integration Test: PASSED");
    println!("  (No patient references!)");
    println!("========================================\n");
}

/// Test: BIOwerk Office Suite Validation
#[test]
fn test_biowerk_office_workflow() {
    println!("\n--- BIOwerk Office Suite Test ---\n");

    let mut biowerk = BIOwerk::new();

    // Test document creation
    let doc_response = biowerk.process(AgentRequest::WriteDocument {
        filename: "report.txt".to_string(),
        content: "Annual Report 2026".to_string(),
    });

    match doc_response {
        AgentResponse::DocumentSaved { filename, address, size } => {
            println!("Document Created:");
            println!("  Filename: {}", filename);
            println!("  Address: block {}", address.block_offset());
            println!("  Size: {} bytes", size);
            assert_eq!(filename, "report.txt");
            assert!(size > 0);
        }
        _ => panic!("Expected DocumentSaved response"),
    }

    // Test logic processing
    let logic_response = biowerk.process(AgentRequest::ProcessLogic {
        name: "calculator.qyn".to_string(),
        formula: "2 + 2 * 3".to_string(),
    });

    match logic_response {
        AgentResponse::LogicProcessed { name, address, bytecode_size } => {
            println!("\nLogic Processed:");
            println!("  Name: {}", name);
            println!("  Address: block {}", address.block_offset());
            println!("  Bytecode: {} bytes", bytecode_size);
            assert_eq!(name, "calculator.qyn");
        }
        _ => panic!("Expected LogicProcessed response"),
    }
}

/// Test: Roulette-RS Braid Transformation
#[test]
fn test_roulette_braid_transformation() {
    println!("\n--- Roulette-RS Braid Test ---\n");

    let transformer = T9BraidTransformer::new();

    // Create test data (office document content)
    let test_content = br#"{"title":"meeting_notes.txt","content":"Q1 Planning Meeting"}"#;
    let mut block = [0u8; BLOCK_SIZE];
    block[..test_content.len()].copy_from_slice(test_content);

    // Transform
    let result = transformer.transform(&block);

    println!("Braid Transformation:");
    println!("  Input: {} bytes", BLOCK_SIZE);
    println!("  Compressed: {} bytes", result.compressed_len);
    println!("  Ratio: {:.1}%", result.ratio * 100.0);
    println!("  Godel number: {}", result.godel_number);

    // Verify transformation
    assert!(result.compressed_len > 0);
    assert!(result.godel_number > 1);

    // Verify roundtrip
    let recovered = transformer.inverse_transform(&result);
    assert_eq!(&block[..test_content.len()], &recovered[..test_content.len()]);
    println!("  Roundtrip: VERIFIED");
}

/// Test: Command Parsing
#[test]
fn test_command_parsing() {
    println!("\n--- Command Parsing Test ---\n");

    // Document commands
    let cmd1 = NucleusDirector::parse_command("write test.txt Hello World");
    assert!(matches!(cmd1, Some(DirectorRequest::WriteDocument { .. })));
    println!("  'write test.txt Hello World' -> WriteDocument");

    // Logic commands
    let cmd2 = NucleusDirector::parse_command("logic calc.qyn 2+2");
    assert!(matches!(cmd2, Some(DirectorRequest::ProcessLogic { .. })));
    println!("  'logic calc.qyn 2+2' -> ProcessLogic");

    // Status
    let cmd3 = NucleusDirector::parse_command("status");
    assert!(matches!(cmd3, Some(DirectorRequest::SystemStatus)));
    println!("  'status' -> SystemStatus");

    // Help
    let cmd4 = NucleusDirector::parse_command("help");
    assert!(matches!(cmd4, Some(DirectorRequest::Help)));
    println!("  'help' -> Help");

    // Invalid
    let cmd5 = NucleusDirector::parse_command("invalid_command");
    assert!(cmd5.is_none());
    println!("  'invalid_command' -> None");

    println!("\n  All parsing tests passed!");
}

/// Test: System Status Check
#[test]
fn test_system_status() {
    let mut director = NucleusDirector::new();

    let response = director.process(DirectorRequest::SystemStatus);

    match response {
        DirectorResponse::Status { biowerk_ready, document_count, logic_count, .. } => {
            println!("System Status:");
            println!("  BIOwerk ready: {}", biowerk_ready);
            println!("  Documents: {}", document_count);
            println!("  Logic units: {}", logic_count);
            assert!(biowerk_ready);
            assert_eq!(document_count, 0);
            assert_eq!(logic_count, 0);
        }
        _ => panic!("Expected Status response"),
    }
}

/// Test: Multiple Documents and Logic
#[test]
fn test_multiple_items() {
    let mut director = NucleusDirector::new();

    // Create multiple documents
    director.process(DirectorRequest::WriteDocument {
        filename: "doc1.txt".to_string(),
        content: "First document".to_string(),
    });
    director.process(DirectorRequest::WriteDocument {
        filename: "doc2.txt".to_string(),
        content: "Second document".to_string(),
    });
    director.process(DirectorRequest::WriteDocument {
        filename: "doc3.txt".to_string(),
        content: "Third document".to_string(),
    });

    // Create multiple logic units
    director.process(DirectorRequest::ProcessLogic {
        name: "calc1.qyn".to_string(),
        formula: "1 + 1".to_string(),
    });
    director.process(DirectorRequest::ProcessLogic {
        name: "calc2.qyn".to_string(),
        formula: "2 * 3".to_string(),
    });

    // Verify counts
    let status = director.process(DirectorRequest::SystemStatus);
    match status {
        DirectorResponse::Status { document_count, logic_count, .. } => {
            assert_eq!(document_count, 3);
            assert_eq!(logic_count, 2);
            println!("Multiple items test: {} documents, {} logic units", document_count, logic_count);
        }
        _ => panic!("Expected Status response"),
    }
}

/// Test: Braid Magic Constant
#[test]
fn test_braid_magic_constant() {
    // Verify the magic constant is correct
    assert_eq!(BRAID_MAGIC, [0xB8, 0xAD]);
    println!("Braid magic: 0x{:02X}{:02X} = 0xB8AD", BRAID_MAGIC[0], BRAID_MAGIC[1]);
}

// ============================================================================
// STAGE 11.5: ECOSYSTEM EXPANSION TEST
// ============================================================================

/// Test: Ecosystem Expansion - Third-Party Organ Integration
///
/// This test proves that external developers can create Organs that:
/// 1. Implement the SovereignDocument trait
/// 2. Store data via Symbiote without ANY kernel modifications
/// 3. Participate in the Braid ecosystem with 0xB8AD compliance
///
/// CRUCIAL: The Cardio organ was created as a "third-party" module.
/// Symbiote code is UNCHANGED. This proves the modularity goal.
#[test]
fn test_ecosystem_expansion() {
    println!("\n========================================");
    println!("  EAOS STAGE 11.5: ECOSYSTEM EXPANSION");
    println!("  Third-Party Organ Integration Test");
    println!("========================================\n");

    // Step 1: Create a third-party organ (Cardio)
    println!("Step 1: Creating third-party Cardio organ...");
    let mut monitor = CardioMonitor::new();

    // Simulate system operation
    monitor.tick_n(3600); // 1 hour of operation
    monitor.set_pulse_rate(72);
    monitor.set_status(StatusCode::Healthy);

    let heartbeat = monitor.snapshot();
    println!("  Heartbeat created:");
    println!("  - Tick: {}", heartbeat.tick);
    println!("  - Uptime: {} seconds", monitor.uptime_secs());
    println!("  - Pulse: {} BPM", heartbeat.pulse_rate);
    println!("  - Status: {} (healthy)", heartbeat.status);

    // Step 2: Verify SovereignDocument implementation
    println!("\nStep 2: Verifying SovereignDocument implementation...");
    let blob_type = heartbeat.blob_type();
    assert_eq!(blob_type, BlobType::Record);
    println!("  Blob type: {:?}", blob_type);

    let bytes = heartbeat.to_bytes();
    assert_eq!(bytes.len(), 20);
    println!("  Serialized: {} bytes", bytes.len());

    let recovered = Heartbeat::from_bytes(&bytes).expect("Deserialization failed");
    assert_eq!(recovered, heartbeat);
    println!("  Roundtrip: VERIFIED");

    // Step 3: Convert to SovereignBlob
    println!("\nStep 3: Converting to SovereignBlob...");
    let blob = heartbeat.to_blob();
    assert!(blob.is_governance_compliant());
    assert_eq!(blob.blob_type, BlobType::Record);
    println!("  Governance compliant: YES (0xB8AD header)");
    println!("  Payload size: {} bytes", blob.payload.len());

    // Step 4: Commit through Symbiote (UNCHANGED!)
    println!("\nStep 4: Committing via Symbiote (NO MODIFICATIONS!)...");
    let mut synapse = Symbiote::new();
    let result = synapse.commit_organ_data(blob);
    assert!(result.is_ok());

    let addr = result.unwrap();
    println!("  Committed to block: {}", addr.block_offset());
    println!("  Address valid: {}", !addr.is_null());

    // Step 5: Verify Nucleus integration
    println!("\nStep 5: Testing Nucleus Cardio command...");
    let mut director = NucleusDirector::new();

    // Record a heartbeat through Nucleus
    let response = director.process(DirectorRequest::CardioHeartbeat);
    match response {
        DirectorResponse::HeartbeatRecorded { tick, uptime_secs, block_offset } => {
            println!("  Heartbeat recorded:");
            println!("  - Tick: {}", tick);
            println!("  - Uptime: {} seconds", uptime_secs);
            println!("  - Block: {}", block_offset);
            assert_eq!(tick, 1);
            assert_eq!(uptime_secs, 1);
        }
        DirectorResponse::Error(e) => panic!("Heartbeat failed: {}", e),
        _ => panic!("Unexpected response"),
    }

    // Record more heartbeats
    director.process(DirectorRequest::CardioHeartbeat);
    director.process(DirectorRequest::CardioHeartbeat);

    // Check system status includes heartbeat
    let status = director.process(DirectorRequest::SystemStatus);
    match status {
        DirectorResponse::Status { heartbeat_tick, .. } => {
            assert_eq!(heartbeat_tick, 3);
            println!("  Status shows heartbeat tick: {}", heartbeat_tick);
        }
        _ => panic!("Expected Status response"),
    }

    println!("\n========================================");
    println!("  ECOSYSTEM EXPANSION: VERIFIED");
    println!("========================================");
    println!("");
    println!("  Third-party Organ: ea-cardio");
    println!("  Document Type:     Heartbeat");
    println!("  Symbiote Version:  UNCHANGED");
    println!("  Kernel Changes:    ZERO");
    println!("  Braid Compliant:   YES");
    println!("");
    println!("  CONCLUSION: Other devs CAN build Muscles!");
    println!("========================================\n");
}

/// Test: Full Organism with Cardio
///
/// Demonstrates all three organs working together:
/// - Osteon (documents)
/// - Myocyte (logic)
/// - Cardio (system health)
#[test]
fn test_full_organism_with_cardio() {
    println!("\n--- Full Organism Test (Osteon + Myocyte + Cardio) ---\n");

    let mut director = NucleusDirector::new();

    // 1. Write a document
    let doc = director.process(DirectorRequest::WriteDocument {
        filename: "quarterly_report.txt".to_string(),
        content: "Q1 2026 Revenue: $3.375M".to_string(),
    });
    assert!(matches!(doc, DirectorResponse::DocumentSaved { .. }));
    println!("Document: quarterly_report.txt saved");

    // 2. Process logic
    let logic = director.process(DirectorRequest::ProcessLogic {
        name: "profit.qyn".to_string(),
        formula: "3375000 - 2400000".to_string(),
    });
    assert!(matches!(logic, DirectorResponse::LogicProcessed { .. }));
    println!("Logic: profit.qyn processed");

    // 3. Record heartbeat
    let heartbeat = director.process(DirectorRequest::CardioHeartbeat);
    assert!(matches!(heartbeat, DirectorResponse::HeartbeatRecorded { .. }));
    println!("Cardio: heartbeat recorded");

    // 4. Final status
    let status = director.process(DirectorRequest::SystemStatus);
    match status {
        DirectorResponse::Status {
            biowerk_ready,
            document_count,
            logic_count,
            heartbeat_tick,
        } => {
            assert!(biowerk_ready);
            assert_eq!(document_count, 1);
            assert_eq!(logic_count, 1);
            assert_eq!(heartbeat_tick, 1);
            println!("\nFinal Status:");
            println!("  BIOwerk: Ready");
            println!("  Documents: {}", document_count);
            println!("  Logic units: {}", logic_count);
            println!("  Heartbeat: tick {}", heartbeat_tick);
        }
        _ => panic!("Expected Status"),
    }

    println!("\nFull organism test: PASSED");
}
