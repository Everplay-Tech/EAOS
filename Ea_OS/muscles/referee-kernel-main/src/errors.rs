#[derive(Debug, Clone, Copy)]
pub enum LoadError {
    InvalidMagic,
    ChecksumMismatch,
    MemoryAllocationFailed,
    DecryptionFailed,
    InvalidCanary,
}

#[derive(Debug, Clone, Copy)]
pub enum KeyError {
    InvalidHeader,
    KeyNotFound,
    KeyCorrupted,
}
