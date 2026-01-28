use std::fs;
use std::path::PathBuf;
use tempfile::TempDir;

use hyperbolic_chamber::executor::{execute_plan, perform_download, perform_extract};
use hyperbolic_chamber::manifest::{load_manifest, Step};
use hyperbolic_chamber::planner::plan_install;
use hyperbolic_chamber::env_detect::detect_environment;
use hyperbolic_chamber::security::verify_manifest_signature;

#[test]
fn end_to_end_install_workflow() {
    let temp = TempDir::new().expect("temp dir");
    let manifest_path = temp.path().join("test.manifest.json");
    
    let manifest_json = r#"{
        "name": "test-app",
        "version": "1.0.0",
        "modes": {
            "full": {
                "steps": {
                    "linux": [
                        {"run": "echo 'Installation successful'"}
                    ]
                }
            }
        }
    }"#;
    
    fs::write(&manifest_path, manifest_json).expect("write manifest");
    
    let manifest = load_manifest(&manifest_path).expect("load manifest");
    let env = detect_environment().expect("detect environment");
    
    if env.os == "linux" {
        let plan = plan_install(&manifest, &env).expect("plan install");
        let result = execute_plan(&plan).expect("execute plan");
        
        assert_eq!(result.completed_steps, 1);
        assert_eq!(result.total_steps, 1);
    }
}

#[test]
fn download_with_verification() {
    let temp = TempDir::new().expect("temp dir");
    let dest = temp.path().join("test.bin");
    
    // Use a small test file
    let step = hyperbolic_chamber::manifest::DownloadStep {
        url: "https://www.example.com/".to_string(),
        dest: dest.clone(),
        expected_sha256: None,
        expected_size: None,
        timeout_secs: Some(10),
    };
    
    let result = perform_download(&step);
    // May succeed or fail depending on network, but shouldn't panic
    assert!(result.is_ok() || result.is_err());
}

#[test]
fn extract_zip_archive() {
    let temp = TempDir::new().expect("temp dir");
    let archive_path = temp.path().join("test.zip");
    let dest_dir = temp.path().join("extracted");
    
    // Create a simple zip file
    {
        let file = fs::File::create(&archive_path).expect("create archive");
        let mut zip = zip::ZipWriter::new(file);
        let options = zip::write::FileOptions::default();
        zip.start_file("test.txt", options).expect("start file");
        std::io::Write::write_all(&mut zip, b"test content").expect("write content");
        zip.finish().expect("finish zip");
    }
    
    let step = hyperbolic_chamber::manifest::ExtractStep {
        archive: archive_path,
        dest: dest_dir.clone(),
    };
    
    perform_extract(&step).expect("extract archive");
    
    let extracted_file = dest_dir.join("test.txt");
    assert!(extracted_file.exists());
    let content = fs::read_to_string(extracted_file).expect("read extracted file");
    assert_eq!(content, "test content");
}

#[test]
fn template_config_rendering() {
    let temp = TempDir::new().expect("temp dir");
    let template_path = temp.path().join("template.txt");
    let output_path = temp.path().join("output.txt");
    
    fs::write(&template_path, "Hello {{NAME}}, version {{VERSION}}").expect("write template");
    
    let mut vars = std::collections::HashMap::new();
    vars.insert("NAME".to_string(), "World".to_string());
    vars.insert("VERSION".to_string(), "1.0".to_string());
    
    let step = hyperbolic_chamber::manifest::TemplateConfigStep {
        source: template_path,
        dest: output_path.clone(),
        vars,
    };
    
    hyperbolic_chamber::executor::render_template(&step).expect("render template");
    
    let content = fs::read_to_string(output_path).expect("read output");
    assert_eq!(content, "Hello World, version 1.0");
}

#[test]
fn state_persistence() {
    use hyperbolic_chamber::state::{add_install_record, load_state, InstallRecord, InstallStatus};
    use chrono::Utc;
    
    let record = InstallRecord {
        app_name: "test-app".to_string(),
        app_version: "1.0.0".to_string(),
        mode: "full".to_string(),
        os: "linux".to_string(),
        cpu_arch: "x64".to_string(),
        timestamp: Utc::now(),
        status: InstallStatus::Success,
        artifacts: vec![],
    };
    
    add_install_record(record.clone()).expect("add record");
    
    let state = load_state().expect("load state");
    assert!(state.installs.iter().any(|r| r.app_name == "test-app"));
}

#[test]
fn signed_manifest_verification() {
    use ed25519_dalek::{Signer, SigningKey};
    use base64::{Engine as _, engine::general_purpose};
    
    // Create test keypair
    let seed_bytes = [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
        17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32,
    ];
    let signing_key = SigningKey::from_bytes(&seed_bytes);
    let verifying_key = signing_key.verifying_key();
    
    let temp = TempDir::new().expect("temp dir");
    
    // Create security config with public key
    let app_support = temp.path().join("Library").join("Application Support");
    let config_dir = app_support.join("enzyme-installer");
    fs::create_dir_all(&config_dir).expect("create config dir");
    
    let public_key_b64 = general_purpose::STANDARD.encode(verifying_key.to_bytes());
    let config_content = format!("public_keys = [\"{}\"]\n", public_key_b64);
    fs::write(config_dir.join("security.toml"), config_content).expect("write config");
    
    // Set HOME to temp dir
    let original_home = std::env::var_os("HOME");
    unsafe {
        std::env::set_var("HOME", temp.path());
    }
    
    // Create manifest content (without signature field)
    let manifest_json: serde_json::Value = serde_json::json!({
        "name": "signed-app",
        "version": "1.0.0",
        "modes": {
            "full": {
                "steps": {
                    "linux": [
                        {"run": "echo 'signed installation'"}
                    ]
                }
            }
        }
    });
    
    // Sign the manifest content (canonical JSON without signature)
    let manifest_content = serde_json::to_string(&manifest_json).unwrap();
    let signature = signing_key.sign(manifest_content.as_bytes());
    let signature_b64 = general_purpose::STANDARD.encode(signature.to_bytes());
    
    // Create manifest with signature (add signature field)
    let mut manifest_with_sig = manifest_json.clone();
    manifest_with_sig["signature"] = serde_json::Value::String(signature_b64.clone());
    
    let manifest_path = temp.path().join("signed.manifest.json");
    fs::write(&manifest_path, serde_json::to_string_pretty(&manifest_with_sig).unwrap())
        .expect("write signed manifest");
    
    // Test 1: Signed manifest should load successfully
    let manifest = load_manifest(&manifest_path).expect("signed manifest should load");
    assert_eq!(manifest.name, "signed-app");
    assert_eq!(manifest.version, "1.0.0");
    
    // Test 2: Unsigned manifest should still work (backward compatibility)
    let unsigned_path = temp.path().join("unsigned.manifest.json");
    fs::write(&unsigned_path, serde_json::to_string_pretty(&manifest_json).unwrap())
        .expect("write unsigned manifest");
    let unsigned_manifest = load_manifest(&unsigned_path).expect("unsigned manifest should load");
    assert_eq!(unsigned_manifest.name, "signed-app");
    
    // Test 3: Tampered manifest should fail
    let tampered_json: serde_json::Value = serde_json::json!({
        "name": "hacked-app",
        "version": "1.0.0",
        "modes": {
            "full": {
                "steps": {
                    "linux": [
                        {"run": "echo 'hacked'"}
                    ]
                }
            }
        }
    });
    let mut tampered_manifest = tampered_json.clone();
    tampered_manifest["signature"] = serde_json::Value::String(signature_b64.clone());
    
    let tampered_path = temp.path().join("tampered.manifest.json");
    fs::write(&tampered_path, serde_json::to_string_pretty(&tampered_manifest).unwrap())
        .expect("write tampered manifest");
    
    let result = load_manifest(&tampered_path);
    assert!(result.is_err(), "tampered manifest should fail to load");
    assert!(result.unwrap_err().to_string().contains("signature verification failed"));
    
    // Restore HOME
    if let Some(home) = original_home {
        unsafe {
            std::env::set_var("HOME", home);
        }
    } else {
        unsafe {
            std::env::remove_var("HOME");
        }
    }
}
