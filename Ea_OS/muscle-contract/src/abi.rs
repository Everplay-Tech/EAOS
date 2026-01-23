#![no_std]

/// The chemical signals of the OS
#[derive(Clone, Copy, Debug, PartialEq)]
#[repr(C)]
pub enum Pheromone {
    // HOMEOSTASIS
    Inert,                    // No signal
    Adrenaline(u8),           // System Panic/Error Code
    Dopamine,                 // Success Reward
    
    // SENSORY (Thalamus -> Brain)
    SomaticInput(u8),         // Raw UART byte (Keyboard)
    VisceralInput(usize),     // Pointer to Web Buffer (Mock)

    // COGNITION (Myocyte -> Body)
    ConceptFormed(f64),       // Logic Engine Result
    
    // MEMORY (Osteon -> Cortex)
    OsteonCalcified,          // Save Complete Confirmation
}

/// Synaptic Vesicle: Network Packet Container
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SynapticVesicle {
    /// The destination IP (IPv4 as bytes)
    pub target_synapse: [u8; 4], 
    pub target_port: u16,

    /// The Payload: Encrypted, Signed, and Sealed by the Nucleus.
    /// The Referee cannot read this. It only delivers it.
    pub payload_size: usize,
    pub payload: [u8; 1024], 
}

impl SynapticVesicle {
    pub fn new(ip: [u8; 4], port: u16, data: &[u8]) -> Self {
        let mut payload = [0u8; 1024];
        let size = data.len().min(1024);
        payload[..size].copy_from_slice(&data[..size]);

        Self {
            target_synapse: ip,
            target_port: port,
            payload_size: size,
            payload,
        }
    }
}