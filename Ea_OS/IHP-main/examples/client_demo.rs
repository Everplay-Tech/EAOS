use std::env;
use std::io::{self, Read};
use std::time::{SystemTime, UNIX_EPOCH};

use base64::{Engine as _, engine::general_purpose::STANDARD};
use ihp::ProfileKey;
use ihp::client::{
    CapsuleBuildOptions, build_capsule_for_password_with_options, fetch_ihp_profile,
};
use reqwest::Client;

fn decode_key(env_var: &str) -> Result<[u8; ihp::KEY_BYTES], Box<dyn std::error::Error>> {
    let value = env::var(env_var)?;
    let decoded = STANDARD.decode(value)?;
    let bytes: [u8; ihp::KEY_BYTES] = decoded
        .try_into()
        .map_err(|_| format!("{env_var} must be {} bytes", ihp::KEY_BYTES))?;
    Ok(bytes)
}

fn read_password() -> Result<Vec<u8>, io::Error> {
    let mut buffer = Vec::new();
    io::stdin().read_to_end(&mut buffer)?;
    Ok(buffer)
}

fn now_timestamp() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("time")
        .as_secs() as i64
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let base_url = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "http://127.0.0.1:3000".into());

    let tls_exporter_key = decode_key("IHP_TLS_EXPORTER_B64")?;
    let profile_key_bytes = decode_key("IHP_PROFILE_KEY_B64")?;
    let profile_key = ProfileKey::from_bytes(profile_key_bytes);
    println!("Reading password material from stdin...");
    let password = read_password()?;

    let server_profile = fetch_ihp_profile(&base_url).await?;
    let capsule = build_capsule_for_password_with_options(
        &server_profile,
        &password,
        &tls_exporter_key,
        &profile_key,
        now_timestamp(),
        CapsuleBuildOptions::default(),
    )
    .await?;

    let client = Client::new();
    let response = client
        .post(format!("{base_url}/ihp/auth"))
        .json(&serde_json::json!({
            "version": capsule.version,
            "header_id": capsule.header_id,
            "client_nonce_b64": STANDARD.encode(capsule.client_nonce),
            "server_profile_id": capsule.server_profile_id.0.to_string(),
            "network_context": {
                "rtt_bucket": capsule.network_context.rtt_bucket,
                "path_hint": capsule.network_context.path_hint,
            },
            "payload_b64": STANDARD.encode(&capsule.payload),
        }))
        .send()
        .await?;

    if response.status().is_success() {
        println!("Auth succeeded: {}", response.text().await?);
    } else {
        eprintln!("Auth failed: {}", response.text().await?);
    }

    Ok(())
}
