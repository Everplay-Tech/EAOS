use uefi::table::boot::{BootServices, MemoryType, AllocateType};

/// Represents a loaded and validated muscle cell ready for execution.
#[derive(Clone, Copy)]
pub struct Cell {
    pub entry_point: u64,
    pub canary: u64,
}

impl Cell {
    pub fn load_and_validate(
        bt: &BootServices,
        addr: u64,
        key: &[u8; 32]
    ) -> Result<Self, &'static str> {
        // Cast address to pointer for arithmetic
        let base_ptr = addr as *const u8;

        // Validate magic header
        let header = unsafe { &*(base_ptr as *const [u8; 8]) };
        if header != b"E\xe4M3\0\0\0\0" {
            return Err("Invalid magic header");
        }

        // Verify checksum (using pointer arithmetic)
        let stored_checksum = unsafe { &*(base_ptr.add(8) as *const [u8; 32]) };
        let data = unsafe { core::slice::from_raw_parts(base_ptr.add(40), 4056) };
        let computed = blake3::keyed_hash(key, data);

        if stored_checksum != computed.as_bytes() {
            return Err("Checksum mismatch");
        }

        // Allocate executable memory
        // Note: uefi 0.24 uses LOADER_CODE (uppercase constant)
        let page = bt.allocate_pages(
            AllocateType::AnyPages,
            MemoryType::LOADER_CODE,
            1,
        ).map_err(|_| "Memory allocation failed")?;

        // Decrypt and copy
        let mut buffer = [0u8; 4096];
        unsafe {
            core::ptr::copy_nonoverlapping(
                base_ptr,
                buffer.as_mut_ptr(),
                4096
            );
        }

        // Simple XOR decryption
        for (i, byte) in buffer.iter_mut().enumerate() {
            *byte ^= key[i % 32];
        }

        // Copy to executable page
        unsafe {
            core::ptr::copy_nonoverlapping(
                buffer.as_ptr(),
                page as *mut u8,
                4096
            );
        }

        // Generate canary from a simple source (UEFI TSC or fallback)
        // Note: get_random is in the RNG protocol, not directly on BootServices
        let canary_value = generate_canary(addr);

        Ok(Self {
            entry_point: page as u64,
            canary: canary_value,
        })
    }

    pub fn validate_canary(&self) -> bool {
        self.canary != 0 && self.canary != !0
    }
}

/// Generate a pseudo-random canary value using available entropy sources.
/// In a real implementation, this would use UEFI RNG protocol.
fn generate_canary(seed: u64) -> u64 {
    // Use TSC (Time Stamp Counter) if available, mixed with seed
    #[cfg(target_arch = "x86_64")]
    {
        let lo: u32;
        let hi: u32;
        unsafe {
            core::arch::asm!(
                "rdtsc",
                out("eax") lo,
                out("edx") hi,
                options(nomem, nostack)
            );
        }
        let tsc = ((hi as u64) << 32) | (lo as u64);
        tsc ^ seed ^ 0xDEADBEEF_CAFEBABE
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        seed ^ 0xDEADBEEF_CAFEBABE
    }
}
