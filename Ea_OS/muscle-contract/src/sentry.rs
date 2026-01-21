#![no_std]

/// Operations for the Sentry (Keymaster)
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum SentryOp {
    NoOp = 0x00,
    /// Initialize with key (one-time)
    Initialize = 0x01,
    /// Sign a hash
    SignHash = 0x02,
}

/// Request structure for Sentry
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SentryRequest {
    pub op: SentryOp,
    pub payload: [u8; 32], // Hash to sign or Key to load
}

/// Result of a Sentry operation
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SentryResult {
    pub signature: [u8; 64], // Ed25519 signature
    pub status: u8, // 0=OK, 1=Error
}
