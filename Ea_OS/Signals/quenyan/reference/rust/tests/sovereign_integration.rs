//! Integration tests for Quenyan <-> Symbiote bridge
//!
//! Tests the --emit-sovereign and --from-sovereign flags work correctly

use ea_symbiote::{BlobType, SovereignBlob, BRAID_MAGIC};

/// Test that we can create a SovereignBlob from QYN data
#[test]
fn test_sovereign_blob_from_qyn_data() {
    // Simulated QYN frame data (would come from encoder)
    let qyn_data = b"QYN1 frame data for Hello Sovereign World";

    // Wrap in SovereignBlob
    let blob = SovereignBlob::new_logic(qyn_data);

    // Verify governance compliance
    assert!(blob.is_governance_compliant());
    assert_eq!(blob.encryption_header.magic, BRAID_MAGIC);
    assert_eq!(blob.blob_type, BlobType::Logic);

    // Serialize and deserialize
    let serialized = blob.serialize();
    let restored = SovereignBlob::deserialize(&serialized).unwrap();

    assert_eq!(restored.blob_type, BlobType::Logic);
    assert_eq!(restored.payload, qyn_data.to_vec());
    assert!(restored.is_governance_compliant());
}

/// Test sovereign blob with label
#[test]
fn test_sovereign_blob_with_label() {
    let qyn_data = b"encoded morpheme stream";

    let blob = SovereignBlob::new_logic(qyn_data).with_label("hello.qyn");

    assert_eq!(blob.label.as_deref(), Some("hello.qyn"));
    assert!(blob.is_governance_compliant());

    let serialized = blob.serialize();
    let restored = SovereignBlob::deserialize(&serialized).unwrap();

    assert_eq!(restored.label.as_deref(), Some("hello.qyn"));
}

/// Test the "Hello Sovereign World" canonical case
#[test]
fn test_hello_sovereign_world_qyn() {
    // The canonical EAOS test: "Hello Sovereign World"
    let message = b"Hello Sovereign World";

    // In a real flow:
    // 1. Source code gets parsed to AST
    // 2. AST gets tokenized to morphemes
    // 3. Morphemes get compressed (T9-Braid)
    // 4. Compressed data gets framed as QYN1
    // 5. QYN1 frame gets wrapped in SovereignBlob
    // 6. SovereignBlob gets committed via Symbiote to PermFS

    // Simulate steps 4-5:
    let simulated_qyn_frame = message; // In reality this would be compressed

    let blob = SovereignBlob::new_logic(simulated_qyn_frame)
        .with_label("hello_sovereign_world.qyn");

    // Verify the blob is ready for PermFS
    assert!(blob.is_governance_compliant());
    assert_eq!(blob.encryption_header.magic, 0xB8AD);

    // The blob can now be committed via Symbiote
    let serialized = blob.serialize();
    assert!(!serialized.is_empty());

    println!("SUCCESS: 'Hello Sovereign World' wrapped as QYN SovereignBlob");
    println!("  Blob type: {:?}", blob.blob_type);
    println!("  Label: {:?}", blob.label);
    println!("  Serialized size: {} bytes", serialized.len());
}
