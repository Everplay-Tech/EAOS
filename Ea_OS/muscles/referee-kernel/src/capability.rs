use blake3::Hasher;

#[derive(Debug, Clone, Copy)]
pub struct ChaosCapability {
    key: [u8; 32],
    rights: u8,
}

impl ChaosCapability {
    pub fn new_master(key: [u8; 32]) -> Self {
        Self { key, rights: 0b1111 }
    }
    
    pub fn derive_child_key(parent: &[u8; 32], salt: u64) -> [u8; 32] {
        let mut context = [0u8; 32];
        context[0..8].copy_from_slice(b"child-v3");
        context[8..16].copy_from_slice(&salt.to_le_bytes());
        
        Hasher::new_keyed(parent)
            .update(&context)
            .finalize()
            .as_bytes()
            .clone()
    }
    
    pub fn can_spawn(&self) -> bool { self.rights & 1 != 0 }
    pub fn can_memory(&self) -> bool { self.rights & 2 != 0 }
    pub fn can_io(&self) -> bool { self.rights & 4 != 0 }
    pub fn can_exec(&self) -> bool { self.rights & 8 != 0 }
    
    pub fn downgrade_spawn(mut self) -> Self {
        self.rights &= !1;
        self
    }
}
