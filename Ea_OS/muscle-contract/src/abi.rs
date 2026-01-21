#![no_std]

/// Standardized container for transporting Pheromones over the network.
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SynapticVesicle {
    /// Magic number / Version (e.g. 0xEA05_0001)
    pub protocol_id: u32,
    /// Sequence number
    pub packet_id: u64,
    /// Timestamp (Kernel time)
    pub timestamp: u64,
    /// Size of the payload
    pub payload_size: u32,
    /// Fixed-size payload buffer (holds serialized Pheromone)
    pub payload: [u8; 1024],
}

impl SynapticVesicle {
    pub const PROTOCOL_ID: u32 = 0xEA05_0001;

    pub fn new(packet_id: u64, timestamp: u64, data: &[u8]) -> Self {
        let mut payload = [0u8; 1024];
        let size = data.len().min(1024);
        payload[..size].copy_from_slice(&data[..size]);

        Self {
            protocol_id: Self::PROTOCOL_ID,
            packet_id,
            timestamp,
            payload_size: size as u32,
            payload,
        }
    }
}
