//! Integration tests for Symbiote IPC Synapse Layer
//!
//! These tests simulate Organs (agents) using Symbiote to communicate
//! with the Referee Kernel via the syscall ABI.

use ea_symbiote::{
    BlockAddr, BlobType, EncryptionHeader, SovereignBlob, SovereignDocument,
    Symbiote, SymbioteError, SyscallNumber, SyscallResult, BRAID_MAGIC, BLOCK_SIZE,
};

// =============================================================================
// Syscall ABI Tests
// =============================================================================

#[test]
fn test_syscall_numbers_match_referee_kernel() {
    // These values MUST match referee-kernel/src/syscall.rs
    // If this test fails, the ABI is broken!
    assert_eq!(SyscallNumber::ReadBlock as u64, 0);
    assert_eq!(SyscallNumber::WriteBlock as u64, 1);
    assert_eq!(SyscallNumber::SpawnTask as u64, 2);
    assert_eq!(SyscallNumber::Yield as u64, 3);
    assert_eq!(SyscallNumber::Exit as u64, 4);
    assert_eq!(SyscallNumber::AllocPages as u64, 5);
    assert_eq!(SyscallNumber::FreePages as u64, 6);
    assert_eq!(SyscallNumber::GetTime as u64, 7);
    assert_eq!(SyscallNumber::AuditLog as u64, 8);
}

#[test]
fn test_syscall_result_codes() {
    assert_eq!(SyscallResult::Success as i64, 0);
    assert_eq!(SyscallResult::InvalidSyscall as i64, -1);
    assert_eq!(SyscallResult::InvalidAddress as i64, -2);
    assert_eq!(SyscallResult::IoError as i64, -3);
    assert_eq!(SyscallResult::PermissionDenied as i64, -4);
    assert_eq!(SyscallResult::OutOfMemory as i64, -5);
    assert_eq!(SyscallResult::InvalidBuffer as i64, -6);
    assert_eq!(SyscallResult::TaskNotFound as i64, -7);
    assert_eq!(SyscallResult::GovernanceBlocked as i64, -10);
}

#[test]
fn test_block_addr_256bit_layout() {
    let addr = BlockAddr::new(42, 7, 3, 100);

    // Verify we can reconstruct the components
    assert_eq!(addr.node_id(), 42);
    assert_eq!(addr.volume_id(), 7);
    assert_eq!(addr.shard_id(), 3);
    assert_eq!(addr.block_offset(), 100);

    // Verify the 256-bit address is not null
    assert!(!addr.is_null());

    // Verify null detection
    let null_addr = BlockAddr::null();
    assert!(null_addr.is_null());
}

// =============================================================================
// SovereignBlob Tests
// =============================================================================

#[test]
fn test_sovereign_blob_governance_compliance() {
    // All blobs must have the 0xB8AD header
    let blob = SovereignBlob::new_document(b"Test document");

    assert!(blob.is_governance_compliant());
    assert_eq!(blob.encryption_header.magic, BRAID_MAGIC);
}

#[test]
fn test_sovereign_blob_types() {
    let doc = SovereignBlob::new_document(b"Text content");
    assert_eq!(doc.blob_type, BlobType::Document);

    let sheet = SovereignBlob::new_spreadsheet(b"1,2,3\n4,5,6");
    assert_eq!(sheet.blob_type, BlobType::Spreadsheet);

    let logic = SovereignBlob::new_logic(b"computation result");
    assert_eq!(logic.blob_type, BlobType::Logic);

    let record = SovereignBlob::new_record(b"{\"key\": \"value\"}");
    assert_eq!(record.blob_type, BlobType::Record);
}

#[test]
fn test_sovereign_blob_serialization() {
    let original = SovereignBlob::new_document(b"Hello Sovereign World")
        .with_label("greeting.txt");

    let serialized = original.serialize();

    // Should fit in a single block
    assert!(serialized.len() <= BLOCK_SIZE);

    // Deserialize and verify
    let restored = SovereignBlob::deserialize(&serialized).unwrap();
    assert_eq!(restored.blob_type, original.blob_type);
    assert_eq!(restored.payload, original.payload);
    assert_eq!(restored.content_hash, original.content_hash);
    assert!(restored.is_governance_compliant());
}

#[test]
fn test_encryption_header_format() {
    let header = EncryptionHeader::new();

    // Check magic
    assert_eq!(header.magic, 0xB8AD);
    assert!(header.is_braided());

    // Serialize and parse
    let bytes = header.to_bytes();
    assert_eq!(bytes.len(), 12);

    let parsed = EncryptionHeader::from_bytes(&bytes);
    assert_eq!(parsed.magic, header.magic);
    assert_eq!(parsed.compressed_len, header.compressed_len);
    assert_eq!(parsed.godel_number, header.godel_number);
}

// =============================================================================
// Symbiote IPC Tests
// =============================================================================

#[test]
fn test_symbiote_initialization() {
    let synapse = Symbiote::new();
    // Should have default node/volume

    let configured = Symbiote::with_config(5, 10);
    // Should use custom config
    let _ = configured; // Verify it compiles
}

#[test]
fn test_symbiote_commit_organ_data() {
    let mut synapse = Symbiote::new();
    let blob = SovereignBlob::new_document(b"Hello Sovereign World");

    let result = synapse.commit_organ_data(blob);
    assert!(result.is_ok());

    let addr = result.unwrap();
    assert!(!addr.is_null());
    assert_eq!(addr.node_id(), 0);
    assert_eq!(addr.volume_id(), 1);
}

#[test]
fn test_symbiote_multiple_commits() {
    let mut synapse = Symbiote::new();

    // Commit multiple blobs
    let blob1 = SovereignBlob::new_document(b"First document");
    let blob2 = SovereignBlob::new_spreadsheet(b"1,2,3");
    let blob3 = SovereignBlob::new_logic(b"result: 42");

    let addr1 = synapse.commit_organ_data(blob1).unwrap();
    let addr2 = synapse.commit_organ_data(blob2).unwrap();
    let addr3 = synapse.commit_organ_data(blob3).unwrap();

    // Each should get a unique block offset
    assert_eq!(addr1.block_offset(), 0);
    assert_eq!(addr2.block_offset(), 1);
    assert_eq!(addr3.block_offset(), 2);
}

#[test]
fn test_symbiote_read_null_address() {
    let synapse = Symbiote::new();
    let null_addr = BlockAddr::null();

    let result = synapse.read_organ_data(null_addr);
    assert!(result.is_err());

    if let Err(SymbioteError::SyscallFailed(code)) = result {
        assert_eq!(code, SyscallResult::InvalidAddress);
    } else {
        panic!("Expected SyscallFailed error");
    }
}

#[test]
fn test_symbiote_prepare_syscall() {
    let addr = BlockAddr::new(1, 2, 3, 100);
    let data = [0u8; 4096];

    let (syscall_num, arg1, arg2, arg3) = Symbiote::prepare_write_syscall(addr, &data);

    assert_eq!(syscall_num, SyscallNumber::WriteBlock as u64);
    assert_eq!(arg1, addr.node_id());
    // arg2 contains lower bits of high
    // arg3 is the buffer pointer
    assert!(arg3 != 0);
}

// =============================================================================
// Office Suite Integration (Osteon Agent Simulation)
// =============================================================================

/// Simulated Osteon document agent
struct OsteonDocument {
    title: String,
    content: String,
}

impl OsteonDocument {
    fn new(title: &str, content: &str) -> Self {
        Self {
            title: title.to_string(),
            content: content.to_string(),
        }
    }
}

impl SovereignDocument for OsteonDocument {
    fn blob_type(&self) -> BlobType {
        BlobType::Document
    }

    fn to_bytes(&self) -> Vec<u8> {
        format!("{}|{}", self.title, self.content).into_bytes()
    }

    fn from_bytes(data: &[u8]) -> Option<Self> {
        let s = std::str::from_utf8(data).ok()?;
        let parts: Vec<&str> = s.splitn(2, '|').collect();
        if parts.len() == 2 {
            Some(Self {
                title: parts[0].to_string(),
                content: parts[1].to_string(),
            })
        } else {
            None
        }
    }
}

#[test]
fn test_osteon_agent_handshake() {
    // Simulate an Osteon agent using Symbiote to store a document
    let mut synapse = Symbiote::new();

    // Create a document
    let doc = OsteonDocument::new("greeting", "Hello Sovereign World");

    // Convert to blob using SovereignDocument trait
    let blob = doc.to_blob();

    // Verify governance compliance
    assert!(blob.is_governance_compliant());
    assert_eq!(blob.encryption_header.magic, BRAID_MAGIC);

    // Commit through Symbiote
    let result = synapse.commit_organ_data(blob);
    assert!(result.is_ok());

    let addr = result.unwrap();
    println!("Osteon: Stored document at block {}", addr.block_offset());

    // Verify the address is valid
    assert!(!addr.is_null());
}

#[test]
fn test_hello_sovereign_world() {
    // The canonical integration test: store "Hello Sovereign World"
    let mut synapse = Symbiote::new();

    let blob = SovereignBlob::new_document(b"Hello Sovereign World")
        .with_label("hello.txt");

    // Verify Braid compliance
    assert!(blob.is_governance_compliant());
    assert_eq!(blob.encryption_header.magic, 0xB8AD);

    // Commit to storage
    let addr = synapse.commit_organ_data(blob).expect("Commit should succeed");

    // Verify valid address
    assert!(!addr.is_null());
    assert_eq!(addr.node_id(), 0);
    assert_eq!(addr.volume_id(), 1);

    // Verify syscall preparation
    let data = b"Hello Sovereign World";
    let (syscall_num, _, _, _) = Symbiote::prepare_write_syscall(addr, data);
    assert_eq!(syscall_num, SyscallNumber::WriteBlock as u64);

    println!("SUCCESS: 'Hello Sovereign World' committed via Symbiote synapse");
}

// =============================================================================
// Property-based tests
// =============================================================================

#[cfg(feature = "proptest")]
proptest::proptest! {
    #[test]
    fn prop_blob_serialization_roundtrip(
        data in proptest::collection::vec(proptest::arbitrary::any::<u8>(), 0..1000),
    ) {
        let blob = SovereignBlob::new(BlobType::Raw, &data);
        let serialized = blob.serialize();
        let restored = SovereignBlob::deserialize(&serialized).unwrap();

        assert_eq!(restored.payload, blob.payload);
        assert_eq!(restored.content_hash, blob.content_hash);
    }

    #[test]
    fn prop_block_addr_components(
        node_id in 0u64..1000,
        volume_id in 0u32..100,
        shard_id in 0u16..50,
        block_offset in 0u64..10000,
    ) {
        let addr = BlockAddr::new(node_id, volume_id, shard_id, block_offset);

        assert_eq!(addr.node_id(), node_id);
        assert_eq!(addr.volume_id(), volume_id);
        assert_eq!(addr.shard_id(), shard_id);
        assert_eq!(addr.block_offset(), block_offset);
    }
}
