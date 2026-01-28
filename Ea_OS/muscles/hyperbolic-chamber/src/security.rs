use std::fs;

use anyhow::{Context, Result};
use base64::{Engine as _, engine::general_purpose};
use ed25519_dalek::{Signature, VerifyingKey};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct SecurityConfig {
    #[serde(default)]
    pub url_allowlist: Vec<String>,
    #[serde(default)]
    pub url_blocklist: Vec<String>,
    #[serde(default)]
    pub public_keys: Vec<String>,
}

pub fn load_security_config() -> Result<Option<SecurityConfig>> {
    let config_path = get_security_config_path()?;
    
    if !config_path.exists() {
        return Ok(None);
    }

    let content = fs::read_to_string(&config_path)
        .with_context(|| format!("reading security config {}", config_path.display()))?;
    
    let config: SecurityConfig = toml::from_str(&content)
        .with_context(|| format!("parsing security config {}", config_path.display()))?;
    
    Ok(Some(config))
}

pub fn get_security_config_path() -> Result<std::path::PathBuf> {
    let base = dirs::config_dir()
        .ok_or_else(|| anyhow::anyhow!("could not determine platform config directory"))?
        .join("enzyme-installer");
    Ok(base.join("security.toml"))
}

pub fn check_url_allowed(url: &str) -> Result<()> {
    if let Some(config) = load_security_config()? {
        // Check blocklist first
        for pattern in &config.url_blocklist {
            if url_matches_pattern(url, pattern) {
                return Err(anyhow::anyhow!("URL {} is blocked by security policy", url));
            }
        }
        
        // If allowlist exists, check it
        if !config.url_allowlist.is_empty() {
            let mut allowed = false;
            for pattern in &config.url_allowlist {
                if url_matches_pattern(url, pattern) {
                    allowed = true;
                    break;
                }
            }
            if !allowed {
                return Err(anyhow::anyhow!("URL {} is not in the allowlist", url));
            }
        }
    }
    
    Ok(())
}

fn url_matches_pattern(url: &str, pattern: &str) -> bool {
    // Simple pattern matching: supports * wildcard
    if pattern.contains('*') {
        let regex_pattern = pattern
            .replace(".", "\\.")
            .replace("*", ".*");
        if let Ok(re) = regex::Regex::new(&format!("^{}$", regex_pattern)) {
            return re.is_match(url);
        }
    }
    url == pattern || url.starts_with(pattern)
}

/// Verify a manifest signature using Ed25519.
/// 
/// The signature should be a base64-encoded Ed25519 signature (64 bytes).
/// Public keys are loaded from the security configuration file.
/// 
/// The signature is computed on the manifest JSON content WITHOUT the signature field.
/// This function removes the signature field before verification.
/// 
/// # Arguments
/// * `manifest_content` - The raw JSON manifest content (as string, may include signature field)
/// * `signature` - Base64-encoded Ed25519 signature
/// 
/// # Returns
/// * `Ok(())` if signature is valid
/// * `Err` if signature is invalid, malformed, or no trusted public keys are configured
pub fn verify_manifest_signature(manifest_content: &str, signature: &str) -> Result<()> {
    // Parse JSON and remove signature field to get the content that was signed
    let mut manifest_json: serde_json::Value = serde_json::from_str(manifest_content)
        .context("failed to parse manifest JSON for signature verification")?;
    
    // Remove signature field if present (signatures are computed on content without signature)
    manifest_json.as_object_mut()
        .and_then(|obj| obj.remove("signature"));
    
    // Re-serialize to canonical form (compact, no whitespace) for verification
    // This matches how signatures are typically computed
    let content_to_verify = serde_json::to_string(&manifest_json)
        .context("failed to serialize manifest for signature verification")?;
    // Decode the base64 signature
    let signature_bytes = general_purpose::STANDARD
        .decode(signature.trim())
        .context("failed to decode base64 signature")?;

    // Ed25519 signatures are exactly 64 bytes
    if signature_bytes.len() != 64 {
        return Err(anyhow::anyhow!(
            "invalid signature length: expected 64 bytes, got {} bytes",
            signature_bytes.len()
        ));
    }

    // Convert bytes to Signature type
    // In ed25519-dalek 2.x, Signature implements TryFrom<&[u8]>
    let signature: Signature = signature_bytes.as_slice()
        .try_into()
        .map_err(|_| anyhow::anyhow!("invalid signature format: failed to convert bytes to Signature"))?;

    // Load public keys from security config
    let config = load_security_config()?
        .ok_or_else(|| anyhow::anyhow!(
            "manifest signature provided but no security configuration found. \
             Create a security.toml file with trusted public_keys"
        ))?;

    if config.public_keys.is_empty() {
        return Err(anyhow::anyhow!(
            "manifest signature provided but no trusted public keys configured. \
             Add public_keys to security.toml"
        ));
    }

    // Try each public key until one verifies
    let mut last_error = None;
    for (idx, key_str) in config.public_keys.iter().enumerate() {
        // Decode base64 public key
        let key_bytes = general_purpose::STANDARD
            .decode(key_str.trim())
            .with_context(|| format!("failed to decode public key #{}", idx + 1))?;

        // Ed25519 public keys are exactly 32 bytes
        if key_bytes.len() != 32 {
            last_error = Some(anyhow::anyhow!(
                "invalid public key #{} length: expected 32 bytes, got {} bytes",
                idx + 1,
                key_bytes.len()
            ));
            continue;
        }

        // Convert bytes to VerifyingKey
        let verifying_key = match VerifyingKey::from_bytes(&key_bytes.try_into().unwrap()) {
            Ok(key) => key,
            Err(e) => {
                last_error = Some(anyhow::anyhow!(
                    "invalid public key #{} format: {}",
                    idx + 1,
                    e
                ));
                continue;
            }
        };

        // Verify signature against manifest content (without signature field)
        match verifying_key.verify_strict(content_to_verify.as_bytes(), &signature) {
            Ok(_) => {
                // Signature verified successfully
                return Ok(());
            }
            Err(e) => {
                // This key didn't verify, try next one
                last_error = Some(anyhow::anyhow!(
                    "signature verification failed with public key #{}: {}",
                    idx + 1,
                    e
                ));
                continue;
            }
        }
    }

    // None of the public keys verified the signature
    Err(anyhow::anyhow!(
        "signature verification failed with all {} configured public key(s). \
         Last error: {}",
        config.public_keys.len(),
        last_error.unwrap_or_else(|| anyhow::anyhow!("unknown error"))
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};
    use std::fs;
    use tempfile::TempDir;
    use hex;

    // Pre-generated test keypairs for reproducible tests
    fn create_test_keypair() -> (SigningKey, VerifyingKey) {
        // Use a deterministic seed for testing
        let seed_bytes = [
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
            17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32,
        ];
        let signing_key = SigningKey::from_bytes(&seed_bytes);
        let verifying_key = signing_key.verifying_key();
        (signing_key, verifying_key)
    }
    
    fn create_test_keypair_2() -> (SigningKey, VerifyingKey) {
        // Use a different deterministic seed for second keypair
        let seed_bytes = [
            33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48,
            49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64,
        ];
        let signing_key = SigningKey::from_bytes(&seed_bytes);
        let verifying_key = signing_key.verifying_key();
        (signing_key, verifying_key)
    }

    fn create_test_security_config(public_keys: Vec<String>) -> (TempDir, std::path::PathBuf) {
        // Create temp dir and use it as home directory
        let temp_dir = TempDir::new().unwrap();
        
        // On macOS, dirs::config_dir() uses ~/Library/Application Support
        // So we need to create that structure
        let app_support = temp_dir.path().join("Library").join("Application Support");
        let config_dir = app_support.join("enzyme-installer");
        fs::create_dir_all(&config_dir).unwrap();
        
        let mut config_content = String::from("public_keys = [\n");
        for key in &public_keys {
            config_content.push_str(&format!("  \"{}\",\n", key));
        }
        config_content.push_str("]\n");
        
        let config_path = config_dir.join("security.toml");
        fs::write(&config_path, config_content).unwrap();
        
        // Set HOME to temp_dir so dirs::config_dir() uses our temp structure
        let original_home = std::env::var_os("HOME");
        unsafe {
            std::env::set_var("HOME", temp_dir.path());
        }
        
        (temp_dir, config_path)
    }
    
    fn restore_home(original_home: Option<std::ffi::OsString>) {
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

    #[test]
    fn verifies_valid_signature() {
        let (signing_key, verifying_key) = create_test_keypair();
        
        // Create manifest JSON (without signature)
        let manifest_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {}
        });
        let manifest_content_no_sig = serde_json::to_string(&manifest_json).unwrap();
        
        // Sign the manifest content (without signature field)
        let signature = signing_key.sign(manifest_content_no_sig.as_bytes());
        let signature_b64 = general_purpose::STANDARD.encode(signature.to_bytes());
        
        // Create manifest with signature field
        let mut manifest_with_sig = manifest_json.clone();
        manifest_with_sig["signature"] = serde_json::Value::String(signature_b64.clone());
        let manifest_content_with_sig = serde_json::to_string(&manifest_with_sig).unwrap();
        
        // Encode public key
        let public_key_b64 = general_purpose::STANDARD.encode(verifying_key.to_bytes());
        
        // Create security config
        let original_home = std::env::var_os("HOME");
        let (_temp_dir, _config_path) = create_test_security_config(vec![public_key_b64]);
        
        // Verify signature (pass content WITH signature field - function will remove it)
        let result = verify_manifest_signature(&manifest_content_with_sig, &signature_b64);
        
        // Restore original HOME
        restore_home(original_home);
        
        if let Err(e) = &result {
            eprintln!("Signature verification failed: {}", e);
        }
        assert!(result.is_ok(), "valid signature should verify successfully");
    }

    #[test]
    fn rejects_invalid_signature() {
        let (signing_key, verifying_key) = create_test_keypair();
        
        // Create manifest JSON
        let manifest_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {}
        });
        
        // Sign different content
        let wrong_json: serde_json::Value = serde_json::json!({
            "name": "different",
            "version": "1.0.0",
            "modes": {}
        });
        let wrong_content = serde_json::to_string(&wrong_json).unwrap();
        let signature = signing_key.sign(wrong_content.as_bytes());
        let signature_b64 = general_purpose::STANDARD.encode(signature.to_bytes());
        
        // Create manifest with signature (but signature is for wrong content)
        let mut manifest_with_sig = manifest_json.clone();
        manifest_with_sig["signature"] = serde_json::Value::String(signature_b64.clone());
        let manifest_content_with_sig = serde_json::to_string(&manifest_with_sig).unwrap();
        
        // Encode public key
        let public_key_b64 = general_purpose::STANDARD.encode(verifying_key.to_bytes());
        
        // Create security config
        let original_home = std::env::var_os("HOME");
        let (_temp_dir, _config_path) = create_test_security_config(vec![public_key_b64]);
        
        // Verify signature (should fail - signature doesn't match content)
        let result = verify_manifest_signature(&manifest_content_with_sig, &signature_b64);
        
        // Restore original HOME
        restore_home(original_home);
        
        assert!(result.is_err(), "invalid signature should fail verification");
        assert!(result.unwrap_err().to_string().contains("signature verification failed"));
    }

    #[test]
    fn rejects_malformed_base64_signature() {
        let manifest_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {},
            "signature": "not-valid-base64!!!"
        });
        let manifest_content = serde_json::to_string(&manifest_json).unwrap();
        let invalid_signature = "not-valid-base64!!!";
        
        let result = verify_manifest_signature(&manifest_content, invalid_signature);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("failed to decode base64 signature"));
    }

    #[test]
    fn rejects_wrong_length_signature() {
        let manifest_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {}
        });
        // Create a signature that's not 64 bytes (32 bytes instead)
        let short_signature_bytes = vec![0u8; 32];
        let short_signature_b64 = general_purpose::STANDARD.encode(&short_signature_bytes);
        
        let mut manifest_with_sig = manifest_json.clone();
        manifest_with_sig["signature"] = serde_json::Value::String(short_signature_b64.clone());
        let manifest_content = serde_json::to_string(&manifest_with_sig).unwrap();
        
        let result = verify_manifest_signature(&manifest_content, &short_signature_b64);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("invalid signature length"));
    }

    #[test]
    fn errors_when_no_security_config() {
        let manifest_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {},
            "signature": "dummy-signature"
        });
        let signature_b64 = general_purpose::STANDARD.encode(vec![0u8; 64]);
        let manifest_content = serde_json::to_string(&manifest_json).unwrap();
        
        // Use a temp dir that doesn't have security.toml
        let temp_dir = TempDir::new().unwrap();
        let original_home = std::env::var_os("HOME");
        unsafe {
            std::env::set_var("HOME", temp_dir.path());
        }
        
        let result = verify_manifest_signature(&manifest_content, &signature_b64);
        
        restore_home(original_home);
        
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("no security configuration found"));
    }

    #[test]
    fn errors_when_no_public_keys_configured() {
        let manifest_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {},
            "signature": "dummy-signature"
        });
        let signature_b64 = general_purpose::STANDARD.encode(vec![0u8; 64]);
        let manifest_content = serde_json::to_string(&manifest_json).unwrap();
        
        // Create security config with empty public_keys
        let original_home = std::env::var_os("HOME");
        let (_temp_dir, _config_path) = create_test_security_config(vec![]);
        
        let result = verify_manifest_signature(&manifest_content, &signature_b64);
        
        restore_home(original_home);
        
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("no trusted public keys configured"));
    }

    #[test]
    fn tries_multiple_public_keys() {
        let (signing_key1, verifying_key1) = create_test_keypair();
        let (_signing_key2, verifying_key2) = create_test_keypair_2();
        
        let manifest_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {}
        });
        let manifest_content_no_sig = serde_json::to_string(&manifest_json).unwrap();
        
        // Sign with first key
        let signature = signing_key1.sign(manifest_content_no_sig.as_bytes());
        let signature_b64 = general_purpose::STANDARD.encode(signature.to_bytes());
        
        // Create manifest with signature
        let mut manifest_with_sig = manifest_json.clone();
        manifest_with_sig["signature"] = serde_json::Value::String(signature_b64.clone());
        let manifest_content_with_sig = serde_json::to_string(&manifest_with_sig).unwrap();
        
        // Create config with both keys (wrong one first, correct one second)
        let key1_b64 = general_purpose::STANDARD.encode(verifying_key2.to_bytes());
        let key2_b64 = general_purpose::STANDARD.encode(verifying_key1.to_bytes());
        let original_home = std::env::var_os("HOME");
        let (_temp_dir, _config_path) = create_test_security_config(vec![key1_b64, key2_b64]);
        
        // Should succeed because second key matches
        let result = verify_manifest_signature(&manifest_content_with_sig, &signature_b64);
        
        restore_home(original_home);
        
        assert!(result.is_ok(), "should succeed with second public key");
    }

    #[test]
    fn rejects_wrong_public_key() {
        let (_signing_key1, verifying_key1) = create_test_keypair();
        let (signing_key2, _verifying_key2) = create_test_keypair_2();
        
        let manifest_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {}
        });
        let manifest_content_no_sig = serde_json::to_string(&manifest_json).unwrap();
        
        // Sign with second key
        let signature = signing_key2.sign(manifest_content_no_sig.as_bytes());
        let signature_b64 = general_purpose::STANDARD.encode(signature.to_bytes());
        
        // Create manifest with signature
        let mut manifest_with_sig = manifest_json.clone();
        manifest_with_sig["signature"] = serde_json::Value::String(signature_b64.clone());
        let manifest_content_with_sig = serde_json::to_string(&manifest_with_sig).unwrap();
        
        // Create config with first key (wrong one)
        let key1_b64 = general_purpose::STANDARD.encode(verifying_key1.to_bytes());
        let original_home = std::env::var_os("HOME");
        let (_temp_dir, _config_path) = create_test_security_config(vec![key1_b64]);
        
        // Should fail because key doesn't match
        let result = verify_manifest_signature(&manifest_content_with_sig, &signature_b64);
        
        restore_home(original_home);
        
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("signature verification failed"));
    }

    #[test]
    fn detects_manifest_tampering() {
        let (signing_key, verifying_key) = create_test_keypair();
        
        let original_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {}
        });
        let original_content = serde_json::to_string(&original_json).unwrap();
        
        // Sign original content
        let signature = signing_key.sign(original_content.as_bytes());
        let signature_b64 = general_purpose::STANDARD.encode(signature.to_bytes());
        
        // Tamper with content
        let tampered_json: serde_json::Value = serde_json::json!({
            "name": "hacked",
            "version": "1.0.0",
            "modes": {}
        });
        let mut tampered_with_sig = tampered_json.clone();
        tampered_with_sig["signature"] = serde_json::Value::String(signature_b64.clone());
        let tampered_content = serde_json::to_string(&tampered_with_sig).unwrap();
        
        // Encode public key
        let public_key_b64 = general_purpose::STANDARD.encode(verifying_key.to_bytes());
        let original_home = std::env::var_os("HOME");
        let (_temp_dir, _config_path) = create_test_security_config(vec![public_key_b64]);
        
        // Verify tampered content (should fail)
        let result = verify_manifest_signature(&tampered_content, &signature_b64);
        
        restore_home(original_home);
        
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("signature verification failed"));
    }

    #[test]
    fn handles_invalid_public_key_format() {
        let manifest_json: serde_json::Value = serde_json::json!({
            "name": "test",
            "version": "1.0.0",
            "modes": {},
            "signature": "dummy-signature"
        });
        let signature_b64 = general_purpose::STANDARD.encode(vec![0u8; 64]);
        let manifest_content = serde_json::to_string(&manifest_json).unwrap();
        
        // Create config with invalid public key (wrong length)
        let invalid_key_b64 = general_purpose::STANDARD.encode(vec![0u8; 16]); // 16 bytes instead of 32
        let original_home = std::env::var_os("HOME");
        let (_temp_dir, _config_path) = create_test_security_config(vec![invalid_key_b64]);
        
        let result = verify_manifest_signature(&manifest_content, &signature_b64);
        
        restore_home(original_home);
        
        assert!(result.is_err());
        let error_msg = result.unwrap_err().to_string();
        // When all keys are invalid format, we get an error about invalid public key length
        assert!(
            error_msg.contains("invalid public key") || 
            error_msg.contains("signature verification failed"),
            "Error message: {}",
            error_msg
        );
    }

    #[test]
    fn json_serialization_is_deterministic() {
        // Test that JSON serialization produces identical output regardless of input key order
        let json1 = r#"{"name":"test","version":"1.0.0","modes":{}}"#;
        let json2 = r#"{"version":"1.0.0","name":"test","modes":{}}"#;
        
        let val1: serde_json::Value = serde_json::from_str(json1).unwrap();
        let val2: serde_json::Value = serde_json::from_str(json2).unwrap();
        
        // Both should serialize to the same string (deterministic)
        let serialized1 = serde_json::to_string(&val1).unwrap();
        let serialized2 = serde_json::to_string(&val2).unwrap();
        
        assert_eq!(serialized1, serialized2, 
            "JSON serialization must be deterministic for signature verification");
        
        // Test with nested objects
        let nested_json1 = r#"{"name":"test","modes":{"full":{"steps":{"linux":[]}}}}"#;
        let nested_json2 = r#"{"modes":{"full":{"steps":{"linux":[]}}},"name":"test"}"#;
        
        let nested_val1: serde_json::Value = serde_json::from_str(nested_json1).unwrap();
        let nested_val2: serde_json::Value = serde_json::from_str(nested_json2).unwrap();
        
        let nested_serialized1 = serde_json::to_string(&nested_val1).unwrap();
        let nested_serialized2 = serde_json::to_string(&nested_val2).unwrap();
        
        assert_eq!(nested_serialized1, nested_serialized2,
            "Nested JSON serialization must be deterministic");
        
        // Test that parsing and re-serializing produces consistent results
        let original = r#"{"name":"app","version":"1.0.0","modes":{"full":{}}}"#;
        let parsed: serde_json::Value = serde_json::from_str(original).unwrap();
        let reserialized = serde_json::to_string(&parsed).unwrap();
        
        // Parse both and compare as values (since key order might differ in string representation)
        let original_val: serde_json::Value = serde_json::from_str(original).unwrap();
        let reserialized_val: serde_json::Value = serde_json::from_str(&reserialized).unwrap();
        
        assert_eq!(original_val, reserialized_val,
            "Parsing and re-serializing should produce semantically equivalent JSON");
        
        // Most importantly: multiple serializations of the same value should be identical
        let serialized_once = serde_json::to_string(&parsed).unwrap();
        let serialized_twice = serde_json::to_string(&parsed).unwrap();
        assert_eq!(serialized_once, serialized_twice,
            "Multiple serializations of the same value must be identical");
    }

    #[test]
    fn rfc8032_test_vector_1() {
        // RFC 8032 Test Vector 1: Empty message
        // Secret Key: 9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60
        // Public Key: d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a
        // Message: (empty, 0 bytes)
        // Signature: e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b
        
        let public_key_hex = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a";
        let signature_hex = "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b";
        let message: &[u8] = b""; // Empty message
        
        // Decode hex strings
        let public_key_bytes = hex::decode(public_key_hex).expect("failed to decode public key hex");
        let signature_bytes = hex::decode(signature_hex).expect("failed to decode signature hex");
        
        // Verify lengths
        assert_eq!(public_key_bytes.len(), 32, "public key must be 32 bytes");
        assert_eq!(signature_bytes.len(), 64, "signature must be 64 bytes");
        
        // Create VerifyingKey and Signature
        let verifying_key = VerifyingKey::from_bytes(
            &public_key_bytes.try_into().expect("public key bytes conversion failed")
        ).expect("failed to create VerifyingKey");
        
        let signature: Signature = signature_bytes.as_slice()
            .try_into()
            .expect("failed to create Signature");
        
        // Verify signature
        verifying_key.verify_strict(message, &signature)
            .expect("RFC 8032 Test Vector 1 verification failed");
    }

    #[test]
    fn rfc8032_test_vector_2() {
        // RFC 8032 Test Vector 2: Non-empty message
        // Secret Key: 4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb
        // Public Key: 3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
        // Message: 72 (hex, 1 byte = 0x72 = 'r')
        // Signature: 92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00
        
        let public_key_hex = "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c";
        let signature_hex = "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00";
        let message_hex = "72";
        let message = hex::decode(message_hex).expect("failed to decode message hex");
        
        // Decode hex strings
        let public_key_bytes = hex::decode(public_key_hex).expect("failed to decode public key hex");
        let signature_bytes = hex::decode(signature_hex).expect("failed to decode signature hex");
        
        // Verify lengths
        assert_eq!(public_key_bytes.len(), 32, "public key must be 32 bytes");
        assert_eq!(signature_bytes.len(), 64, "signature must be 64 bytes");
        assert_eq!(message.len(), 1, "message must be 1 byte");
        
        // Create VerifyingKey and Signature
        let verifying_key = VerifyingKey::from_bytes(
            &public_key_bytes.try_into().expect("public key bytes conversion failed")
        ).expect("failed to create VerifyingKey");
        
        let signature: Signature = signature_bytes.as_slice()
            .try_into()
            .expect("failed to create Signature");
        
        // Verify signature
        verifying_key.verify_strict(&message, &signature)
            .expect("RFC 8032 Test Vector 2 verification failed");
    }
}
