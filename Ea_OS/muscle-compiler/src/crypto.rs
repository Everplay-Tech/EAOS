use crate::error::CompileError;
use blake3::hash;
use muscle_contract::{
    build_payload, seal_with_nonce, EaM6Header, MuscleManifestV1, MANIFEST_LEN, NONCE_LEN,
    PAYLOAD_LEN,
};
use rand_core::{OsRng, RngCore};

/// Encrypts and seals a muscle payload with the chaos master key.
pub fn encrypt_muscle_blob(
    machine_code: &[u8],
    chaos_master: &[u8; 32],
    arch: u8,
    cap_bitmap: u32,
) -> Result<Vec<u8>, CompileError> {
    if machine_code.len() > PAYLOAD_LEN - MANIFEST_LEN {
        return Err(CompileError::CryptoError(format!(
            "Machine code exceeds {} bytes ({} bytes provided)",
            PAYLOAD_LEN - MANIFEST_LEN,
            machine_code.len()
        )));
    }

    let mut muscle_id = [0u8; 32];
    muscle_id.copy_from_slice(hash(machine_code).as_bytes());

    let code_size = machine_code.len() as u16;
    let pages = ((machine_code.len() + 4095) / 4096).max(1) as u16;

    let manifest = MuscleManifestV1::new(
        arch,
        0, // raw ABI
        code_size,
        0, // entrypoint offset
        pages,
        1,  // stack pages
        1,  // heap pages
        16, // update budget
        16, // IO budget
        cap_bitmap,
        muscle_id,
        1, // muscle version
    );

    let payload = build_payload(&manifest, machine_code).map_err(|e| {
        CompileError::CryptoError(format!("Payload build failed: {:?}", e))
    })?;

    let header = EaM6Header::new(arch, cap_bitmap, 0);

    let mut nonce = [0u8; NONCE_LEN];
    OsRng.fill_bytes(&mut nonce);

    let sealed = seal_with_nonce(chaos_master, &header, &nonce, &payload).map_err(|e| {
        CompileError::CryptoError(format!("Sealing failed: {:?}", e))
    })?;

    Ok(sealed.to_vec())
}
