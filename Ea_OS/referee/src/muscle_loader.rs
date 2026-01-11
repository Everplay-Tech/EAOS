// referee/src/muscle_loader.rs
// Eä Muscle Loader v6.0 — Compatible with EaM6 blob format

use alloc::string::String;
#[cfg(feature = "uefi")]
use alloc::format;
#[cfg(feature = "uefi")]
use muscle_contract::{
    open, parse_manifest, verify_code_hash, ARCH_AARCH64, ARCH_WASM32, ARCH_X86_64, BLOB_LEN,
    MANIFEST_LEN,
};
#[cfg(feature = "uefi")]
use uefi::table::boot::{AllocateType, BootServices, MemoryType};

/// Parsed muscle blob information
pub struct LoadedMuscle {
    pub entry_point: u64,
    pub code_base: u64,
    pub entry_offset: u64,
    pub blob_hash: [u8; 32],
    pub memory_pages: u64,
    pub name: String,
    pub arch: String,
}

/// Error types for muscle loading
#[derive(Debug)]
pub enum LoadError {
    InvalidFormat,
    IntegrityCheckFailed,
    MemoryAllocationFailed,
    ArchitectureMismatch,
    DecryptionFailed,
    ManifestMismatch,
}

/// Load and validate a muscle blob from memory
#[cfg(feature = "uefi")]
pub fn load_muscle(
    boot_services: &BootServices,
    master_key: &[u8; 32],
    blob_data: &[u8],
    _muscle_index: usize,
) -> Result<LoadedMuscle, LoadError> {
    if blob_data.len() != BLOB_LEN {
        return Err(LoadError::InvalidFormat);
    }

    let blob: &[u8; BLOB_LEN] = blob_data.try_into().map_err(|_| LoadError::InvalidFormat)?;

    let (header, payload) = open(master_key, blob).map_err(|_| LoadError::DecryptionFailed)?;
    let manifest = parse_manifest(&payload).map_err(|_| LoadError::InvalidFormat)?;

    if manifest.capability_bitmap != header.cap_bitmap {
        return Err(LoadError::ManifestMismatch);
    }

    verify_code_hash(&manifest, &payload).map_err(|_| LoadError::IntegrityCheckFailed)?;

    let arch = match manifest.arch {
        ARCH_AARCH64 => "aarch64",
        ARCH_X86_64 => "x86_64",
        ARCH_WASM32 => "wasm32",
        _ => return Err(LoadError::ArchitectureMismatch),
    };

    if !is_architecture_supported(arch) {
        return Err(LoadError::ArchitectureMismatch);
    }

    let mut memory_pages = manifest.memory_pages as usize;
    if memory_pages == 0 {
        memory_pages = calculate_required_pages(manifest.code_size as usize);
    }

    let memory_ptr = boot_services
        .allocate_pages(
            AllocateType::AnyPages,
            MemoryType::LOADER_CODE,
            memory_pages,
        )
        .map_err(|_| LoadError::MemoryAllocationFailed)?;

    let code_start = MANIFEST_LEN;
    let code_end = code_start + manifest.code_size as usize;
    let code = &payload[code_start..code_end];

    // Copy decrypted code to executable memory
    unsafe {
        core::ptr::copy_nonoverlapping(code.as_ptr(), memory_ptr as *mut u8, code.len());
    }

    let entry_offset = manifest.entrypoint as u64;
    let entry_point = memory_ptr + entry_offset;
    let blob_hash = blake3::hash(blob_data);

    Ok(LoadedMuscle {
        entry_point,
        code_base: memory_ptr,
        entry_offset,
        blob_hash: *blob_hash.as_bytes(),
        memory_pages: memory_pages as u64,
        name: muscle_name(&manifest.muscle_id),
        arch: String::from(arch),
    })
}

#[cfg(feature = "uefi")]
fn muscle_name(muscle_id: &[u8; 32]) -> String {
    format!(
        "muscle_{:02x}{:02x}{:02x}{:02x}",
        muscle_id[0], muscle_id[1], muscle_id[2], muscle_id[3]
    )
}

/// Check if architecture is supported
#[cfg(feature = "uefi")]
fn is_architecture_supported(arch: &str) -> bool {
    // For now, support both - in production this would check current platform
    arch == "aarch64" || arch == "x86_64"
}

/// Calculate required pages for muscle
pub fn calculate_required_pages(size: usize) -> usize {
    (size + 4095) / 4096
}

pub fn generate_salt(muscle_index: usize, label: &str) -> [u8; 16] {
    let mut hasher = blake3::Hasher::new();
    hasher.update(&muscle_index.to_le_bytes());
    hasher.update(label.as_bytes());
    let hash = hasher.finalize();

    let mut out = [0u8; 16];
    out.copy_from_slice(&hash.as_bytes()[..16]);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_page_calculation() {
        assert_eq!(calculate_required_pages(0), 0);
        assert_eq!(calculate_required_pages(1), 1);
        assert_eq!(calculate_required_pages(4096), 1);
        assert_eq!(calculate_required_pages(4097), 2);
    }
}
