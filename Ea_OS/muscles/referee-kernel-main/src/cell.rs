use uefi::table::boot::{BootServices, MemoryType, AllocateType};

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
        // Validate magic header
        let header = unsafe { &*(addr as *const [u8; 8]) };
        if header != b"E\xe4M3\0\0\0\0" {
            return Err("Invalid magic header");
        }
        
        // Verify checksum
        let stored_checksum = unsafe { &*(addr.add(8) as *const [u8; 32]) };
        let data = unsafe { core::slice::from_raw_parts(addr.add(40) as *const u8, 4056) };
        let computed = blake3::keyed_hash(key, data).as_bytes();
        
        if stored_checksum != computed {
            return Err("Checksum mismatch");
        }
        
        // Allocate executable memory
        let page = bt.allocate_pages(
            AllocateType::AnyPages,
            MemoryType::LoaderCode,
            1,
        ).map_err(|_| "Memory allocation failed")?;
        
        // Decrypt and copy
        let mut buffer = [0u8; 4096];
        unsafe {
            core::ptr::copy_nonoverlapping(
                addr as *const u8,
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
        
        // Generate random canary
        let mut canary = [0u8; 8];
        bt.get_random_bytes(&mut canary)
            .map_err(|_| "Failed to generate canary")?;
        
        let canary_value = u64::from_le_bytes(canary);
        
        Ok(Self {
            entry_point: page as u64,
            canary: canary_value,
        })
    }
    
    pub fn validate_canary(&self) -> bool {
        self.canary != 0 && self.canary != !0
    }
}
