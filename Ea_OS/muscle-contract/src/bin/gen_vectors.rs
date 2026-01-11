use muscle_contract::{
    build_payload, seal_with_nonce, EaM6Header, MuscleManifestV1, NONCE_LEN,
    FLAG_DETERMINISTIC_NONCE,
};
use serde::Serialize;

#[derive(Serialize)]
struct VectorV6 {
    version: u8,
    master_key_hex: String,
    header_hex: String,
    nonce_hex: String,
    payload_hex: String,
    blob_hex: String,
}

fn main() {
    let master_key = [0x42; 32];
    let header = EaM6Header::new(1, 0x01, FLAG_DETERMINISTIC_NONCE);

    let mut code = [0u8; 64];
    for (i, byte) in code.iter_mut().enumerate() {
        *byte = i as u8;
    }

    let manifest = MuscleManifestV1::new(
        1,
        0,
        code.len() as u16,
        0,
        2,
        1,
        1,
        8,
        16,
        0x01,
        [0x22; 32],
        7,
    );

    let payload = build_payload(&manifest, &code).expect("build payload");
    let nonce = [0xAA; NONCE_LEN];
    let blob = seal_with_nonce(&master_key, &header, &nonce, &payload).expect("seal blob");

    let vector = VectorV6 {
        version: 6,
        master_key_hex: hex::encode(master_key),
        header_hex: hex::encode(header.to_bytes()),
        nonce_hex: hex::encode(nonce),
        payload_hex: hex::encode(payload),
        blob_hex: hex::encode(blob),
    };

    let json = serde_json::to_string_pretty(&vector).expect("serialize json");
    println!("{}", json);
}
