use mcs_reference::crypto::{
    decrypt_archive, KeyHierarchy, Metadata, Provenance, RotationMetadata,
};
use mcs_reference::encoder::{EntropyError, EntropyMaterial, EntropyRequest, EntropyStrategy};

fn fixed_entropy() -> EntropyMaterial {
    EntropyMaterial {
        salt: vec![7u8; 32],
        nonce: vec![9u8; 12],
        deterministic: true,
    }
}

#[test]
fn rejects_nonce_reuse_without_manager() {
    let strategy = EntropyStrategy::new();
    let salt = vec![1u8; 32];
    let nonce = vec![2u8; 12];
    strategy
        .material_for(
            "project/file/gen1",
            EntropyRequest::Provided {
                salt: salt.clone(),
                nonce: nonce.clone(),
                manager: None,
            },
        )
        .expect("first use should succeed");

    let err = strategy
        .material_for(
            "project/file/gen1",
            EntropyRequest::Provided {
                salt,
                nonce,
                manager: None,
            },
        )
        .expect_err("second use must be rejected");
    assert!(matches!(err, EntropyError::NonceReuse(_)));
}

#[test]
fn tampered_provenance_is_detected() {
    let rotation = RotationMetadata::new("proj", 1, vec![3u8; 32], "1970-01-01T00:00:00Z", None);
    let hierarchy = KeyHierarchy::from_passphrase("passphrase", rotation.clone()).unwrap();

    let metadata = Metadata {
        project_id: "proj".to_string(),
        file_path: "artifact.bin".to_string(),
        rotation,
        provenance: Provenance {
            created: "1970-01-01T00:00:00Z".to_string(),
            commit: Some("abc123".to_string()),
            inputs: Default::default(),
            manifest: None,
        },
    };

    let archive = hierarchy
        .encrypt(b"payload", metadata, fixed_entropy())
        .expect("encryption should succeed");

    assert!(decrypt_archive("passphrase", &archive).is_ok());

    let mut tampered = archive.clone();
    tampered.metadata.provenance.created = "1971-01-01T00:00:00Z".to_string();
    assert!(decrypt_archive("passphrase", &tampered).is_err());
}
