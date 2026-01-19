//! VirtioPhy: smoltcp Device adapter for Virtio-Net
//!
//! Phase 3: Bridges the VirtioModern driver to smoltcp's Device trait,
//! enabling TCP/IP stack operation over the Virtio network interface.
//!
//! ## Architecture
//!
//! ```text
//! ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
//! │  smoltcp    │     │  VirtioPhy  │     │ VirtioModern│
//! │  Interface  │◄───►│  (Adapter)  │◄───►│  (Driver)   │
//! └─────────────┘     └─────────────┘     └─────────────┘
//!       TCP/IP            Tokens            Raw Ethernet
//! ```
//!
//! ## Strategy: Copy-Based Tokens
//!
//! For Phase 3 stability, we use copy-based tokens rather than zero-copy DMA.
//! This simplifies buffer management at the cost of one memcpy per packet.

extern crate alloc;

use alloc::vec;
use alloc::vec::Vec;
use smoltcp::phy::{Device, DeviceCapabilities, Medium, RxToken, TxToken};
use smoltcp::time::Instant;

use crate::virtio_modern::{VirtioModern, RX_BUFFERS, PACKET_BUF_SIZE};

/// Maximum Transmission Unit (standard Ethernet)
const MTU: usize = 1500;

/// Virtio-Net header size (we strip this before passing to smoltcp)
const VIRTIO_NET_HDR_SIZE: usize = 12;

// ============================================================================
// VirtioPhy: The Device Adapter
// ============================================================================

/// VirtioPhy adapts VirtioModern to smoltcp's Device trait
///
/// This allows smoltcp to send and receive Ethernet frames through
/// the Virtio network interface.
pub struct VirtioPhy<'a> {
    /// Reference to the Virtio driver
    pub driver: &'a mut VirtioModern,
}

impl<'a> VirtioPhy<'a> {
    /// Create a new VirtioPhy adapter
    pub fn new(driver: &'a mut VirtioModern) -> Self {
        Self { driver }
    }
}

impl<'a> Device for VirtioPhy<'a> {
    type RxToken<'b> = VirtioRxToken where Self: 'b;
    type TxToken<'b> = VirtioTxToken<'b> where Self: 'b;

    fn receive(&mut self, _timestamp: Instant) -> Option<(Self::RxToken<'_>, Self::TxToken<'_>)> {
        // Check for received packet
        if let Some((buffer_id, length)) = self.driver.process_rx() {
            // Copy data from Virtio RX buffer (skip virtio-net header)
            let data = unsafe {
                let raw = &RX_BUFFERS.buffers[buffer_id];
                let payload_start = VIRTIO_NET_HDR_SIZE.min(length as usize);
                let payload_end = length as usize;

                if payload_end > payload_start {
                    raw[payload_start..payload_end].to_vec()
                } else {
                    return None;
                }
            };

            // Phase 4: Re-provision the RX buffer for next packet
            self.driver.reprovision_rx(buffer_id);

            let rx = VirtioRxToken { buffer: data };
            let tx = VirtioTxToken { driver: self.driver };
            Some((rx, tx))
        } else {
            None
        }
    }

    fn transmit(&mut self, _timestamp: Instant) -> Option<Self::TxToken<'_>> {
        // Always ready to transmit (TX queue management is internal)
        Some(VirtioTxToken { driver: self.driver })
    }

    fn capabilities(&self) -> DeviceCapabilities {
        let mut caps = DeviceCapabilities::default();
        caps.medium = Medium::Ethernet;
        caps.max_transmission_unit = MTU;
        caps.max_burst_size = Some(1);
        caps
    }
}

// ============================================================================
// RxToken: Received Packet
// ============================================================================

/// Token representing a received Ethernet frame
pub struct VirtioRxToken {
    /// The received frame data (copied from Virtio buffer)
    buffer: Vec<u8>,
}

impl RxToken for VirtioRxToken {
    fn consume<R, F>(mut self, f: F) -> R
    where
        F: FnOnce(&mut [u8]) -> R,
    {
        f(&mut self.buffer)
    }
}

// ============================================================================
// TxToken: Transmit Capability
// ============================================================================

/// Token representing ability to transmit an Ethernet frame
pub struct VirtioTxToken<'a> {
    /// Reference to driver for transmit
    driver: &'a mut VirtioModern,
}

impl<'a> TxToken for VirtioTxToken<'a> {
    fn consume<R, F>(self, len: usize, f: F) -> R
    where
        F: FnOnce(&mut [u8]) -> R,
    {
        // Allocate buffer with virtio-net header space
        let total_len = VIRTIO_NET_HDR_SIZE + len;
        let mut buffer = vec![0u8; total_len];

        // Write virtio-net header (flags=0, gso_type=0, etc.)
        // Header is 12 bytes: flags(1) + gso_type(1) + hdr_len(2) +
        //                     gso_size(2) + csum_start(2) + csum_offset(2) + num_buffers(2)
        // All zeros for basic operation

        // Let smoltcp write the Ethernet frame after the header
        let result = f(&mut buffer[VIRTIO_NET_HDR_SIZE..]);

        // Phase 4: Transmit via Virtio driver
        self.driver.transmit(&buffer);

        result
    }
}

// ============================================================================
// Network Configuration Constants
// ============================================================================

/// QEMU User Network (SLIRP) guest IP
pub const GUEST_IP: [u8; 4] = [10, 0, 2, 15];

/// QEMU User Network gateway IP
pub const GATEWAY_IP: [u8; 4] = [10, 0, 2, 2];

/// Subnet mask (/24)
pub const SUBNET_MASK: [u8; 4] = [255, 255, 255, 0];

/// DNS server (Cloudflare)
pub const DNS_IP: [u8; 4] = [1, 1, 1, 1];

// ============================================================================
// Helper Functions
// ============================================================================

/// Get current timestamp in milliseconds (for smoltcp)
///
/// Uses UEFI timer or a simple counter if not available.
pub fn get_timestamp_ms() -> u64 {
    // TODO: Hook into actual UEFI timer
    // For now, use a static counter incremented each poll
    static COUNTER: core::sync::atomic::AtomicU64 = core::sync::atomic::AtomicU64::new(0);
    COUNTER.fetch_add(1, core::sync::atomic::Ordering::Relaxed)
}
