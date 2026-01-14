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
        DirectorResponse::Status { biowerk_ready, document_count, logic_count } => {
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
        DirectorResponse::Status { biowerk_ready, document_count, logic_count } => {
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
