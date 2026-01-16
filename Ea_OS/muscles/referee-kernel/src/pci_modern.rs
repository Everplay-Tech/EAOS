//! Modern PCI Capability Parser for Virtio 1.0 Devices
//!
//! This module provides architecture-agnostic PCI capability parsing with
//! explicit Little Endian handling for cross-platform compatibility.
//!
//! ## Safety Features
//!
//! - TTL-protected capability traversal (48 hops max)
//! - Explicit LE byte ordering for all multi-byte reads
//! - Validation of capability pointer alignment
//!
//! ## Capability Types
//!
//! Virtio uses Vendor-Specific capabilities (ID 0x09) with cfg_type:
//! - 1: CommonCfg - Device control registers
//! - 2: NotifyCfg - Queue notification doorbell
//! - 3: IsrCfg - Interrupt status
//! - 4: DeviceCfg - Device-specific config (MAC address, etc.)

use crate::pci::{pci_config_read_32, PciAddress};

// ============================================================================
// Constants
// ============================================================================

/// PCI Capability ID for Vendor-Specific
const PCI_CAP_ID_VENDOR: u8 = 0x09;

/// Maximum capability chain traversal (TTL to prevent infinite loops)
const CAPABILITY_TTL: usize = 48;

/// Minimum valid capability offset (must be >= 0x40 and 32-bit aligned)
const MIN_CAP_OFFSET: u8 = 0x40;

// ============================================================================
// Little Endian Helpers (Architecture Agnostic)
// ============================================================================

/// Reconstruct u16 from Little Endian bytes
#[inline]
const fn le_u16(low: u8, high: u8) -> u16 {
    (low as u16) | ((high as u16) << 8)
}

/// Reconstruct u32 from Little Endian bytes
#[inline]
const fn le_u32(b0: u8, b1: u8, b2: u8, b3: u8) -> u32 {
    (b0 as u32) | ((b1 as u32) << 8) | ((b2 as u32) << 16) | ((b3 as u32) << 24)
}

/// Extract byte from 32-bit value at position
#[inline]
const fn byte_of(val: u32, pos: usize) -> u8 {
    ((val >> (pos * 8)) & 0xFF) as u8
}

// ============================================================================
// Virtio Capability Types
// ============================================================================

/// Virtio PCI Capability Type (cfg_type field)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum VirtioCfgType {
    /// Common configuration (device control)
    CommonCfg = 1,
    /// Notification structure (doorbell)
    NotifyCfg = 2,
    /// ISR status register
    IsrCfg = 3,
    /// Device-specific configuration
    DeviceCfg = 4,
    /// Alternative PCI config access
    PciCfg = 5,
}

impl VirtioCfgType {
    fn from_u8(val: u8) -> Option<Self> {
        match val {
            1 => Some(Self::CommonCfg),
            2 => Some(Self::NotifyCfg),
            3 => Some(Self::IsrCfg),
            4 => Some(Self::DeviceCfg),
            5 => Some(Self::PciCfg),
            _ => None,
        }
    }

    /// Human-readable name for logging
    pub fn name(&self) -> &'static str {
        match self {
            Self::CommonCfg => "CommonCfg",
            Self::NotifyCfg => "NotifyCfg",
            Self::IsrCfg => "IsrCfg",
            Self::DeviceCfg => "DeviceCfg",
            Self::PciCfg => "PciCfg",
        }
    }
}

// ============================================================================
// Parsed Capability Structures
// ============================================================================

/// Single parsed Virtio PCI capability
#[derive(Debug, Clone, Copy)]
pub struct VirtioCapability {
    /// Capability type
    pub cfg_type: VirtioCfgType,
    /// BAR index (0-5)
    pub bar: u8,
    /// Offset within the BAR (LE reconstructed)
    pub offset: u32,
    /// Region length (LE reconstructed)
    pub length: u32,
    /// Notification offset multiplier (NotifyCfg only)
    pub notify_off_multiplier: u32,
}

impl VirtioCapability {
    /// Return a human-readable type name for logging
    pub fn format_type(&self) -> &'static str {
        self.cfg_type.name()
    }
}

/// Collection of all discovered Virtio capabilities
#[derive(Debug, Default)]
pub struct VirtioCapabilities {
    /// Common configuration (required)
    pub common_cfg: Option<VirtioCapability>,
    /// Notification/doorbell (required)
    pub notify_cfg: Option<VirtioCapability>,
    /// ISR status (required)
    pub isr_cfg: Option<VirtioCapability>,
    /// Device-specific config (required for net)
    pub device_cfg: Option<VirtioCapability>,
}

impl VirtioCapabilities {
    /// Check if all required Modern capabilities are present
    pub fn is_complete(&self) -> bool {
        self.common_cfg.is_some()
            && self.notify_cfg.is_some()
            && self.isr_cfg.is_some()
            && self.device_cfg.is_some()
    }

    /// Count discovered capabilities
    pub fn count(&self) -> usize {
        let mut n = 0;
        if self.common_cfg.is_some() { n += 1; }
        if self.notify_cfg.is_some() { n += 1; }
        if self.isr_cfg.is_some() { n += 1; }
        if self.device_cfg.is_some() { n += 1; }
        n
    }
}

// ============================================================================
// Resolved MMIO Regions
// ============================================================================

/// Resolved physical memory addresses for Virtio MMIO access
#[derive(Debug, Clone, Copy)]
pub struct VirtioMmioRegions {
    /// CommonCfg base address
    pub common_cfg: usize,
    /// CommonCfg length
    pub common_cfg_len: u32,
    /// NotifyCfg base address (doorbell base)
    pub notify_cfg: usize,
    /// Notification offset multiplier
    pub notify_off_multiplier: u32,
    /// ISR status register address
    pub isr_cfg: usize,
    /// DeviceCfg base address
    pub device_cfg: usize,
    /// DeviceCfg length
    pub device_cfg_len: u32,
}

// ============================================================================
// PCI Capability Parser
// ============================================================================

/// Parse all Virtio capabilities from PCI configuration space
///
/// # Safety
/// Performs PCI configuration space reads via I/O ports.
///
/// # Arguments
/// * `addr` - PCI device address (Bus/Device/Function)
///
/// # Returns
/// * `Ok(VirtioCapabilities)` - Discovered capabilities
/// * `Err(&str)` - Parse error description
pub unsafe fn parse_virtio_capabilities(
    addr: &PciAddress,
) -> Result<VirtioCapabilities, &'static str> {
    let mut caps = VirtioCapabilities::default();

    // Check PCI Status register for Capabilities List bit (bit 4)
    let status_cmd = pci_config_read_32(addr.bus, addr.device, addr.function, 0x04);
    let status = (status_cmd >> 16) as u16;

    if (status & 0x10) == 0 {
        return Err("Device has no capability list");
    }

    // Read Capabilities Pointer (offset 0x34, byte 0)
    let cap_ptr_reg = pci_config_read_32(addr.bus, addr.device, addr.function, 0x34);
    let mut current = byte_of(cap_ptr_reg, 0);

    if current == 0 {
        return Err("Capabilities pointer is NULL");
    }

    // Traverse capability linked list with TTL protection
    let mut ttl = CAPABILITY_TTL;

    while current != 0 && ttl > 0 {
        ttl -= 1;

        // Validate pointer (must be >= 0x40 and 32-bit aligned)
        if current < MIN_CAP_OFFSET || (current & 0x03) != 0 {
            return Err("Invalid capability pointer alignment");
        }

        // Read capability header: [cap_id, next_ptr, ...]
        let hdr = pci_config_read_32(addr.bus, addr.device, addr.function, current);
        let cap_id = byte_of(hdr, 0);
        let next_ptr = byte_of(hdr, 1);

        // Check for Vendor-Specific capability (Virtio uses this)
        if cap_id == PCI_CAP_ID_VENDOR {
            if let Some(vcap) = parse_single_capability(addr, current) {
                match vcap.cfg_type {
                    VirtioCfgType::CommonCfg => caps.common_cfg = Some(vcap),
                    VirtioCfgType::NotifyCfg => caps.notify_cfg = Some(vcap),
                    VirtioCfgType::IsrCfg => caps.isr_cfg = Some(vcap),
                    VirtioCfgType::DeviceCfg => caps.device_cfg = Some(vcap),
                    VirtioCfgType::PciCfg => {} // Not needed for Modern
                }
            }
        }

        current = next_ptr;
    }

    if ttl == 0 && current != 0 {
        return Err("Capability chain TTL exceeded (loop detected)");
    }

    Ok(caps)
}

/// Parse a single Virtio capability at the given config space offset
///
/// Virtio PCI Capability Layout (Little Endian):
/// ```text
/// Offset +0x00: cap_vndr (0x09) | cap_next | cap_len | cfg_type
/// Offset +0x04: bar | padding[3]
/// Offset +0x08: offset[4] (LE 32-bit)
/// Offset +0x0C: length[4] (LE 32-bit)
/// Offset +0x10: notify_off_multiplier[4] (NotifyCfg only)
/// ```
unsafe fn parse_single_capability(addr: &PciAddress, offset: u8) -> Option<VirtioCapability> {
    // Read first two DWORDs
    let dword0 = pci_config_read_32(addr.bus, addr.device, addr.function, offset);
    let dword1 = pci_config_read_32(addr.bus, addr.device, addr.function, offset + 4);

    // Extract fields (bytes are in LE order within the DWORD)
    let _cap_vndr = byte_of(dword0, 0); // Should be 0x09
    let _cap_next = byte_of(dword0, 1);
    let _cap_len = byte_of(dword0, 2);
    let cfg_type_raw = byte_of(dword0, 3);

    let bar = byte_of(dword1, 0);

    // Validate bar index
    if bar > 5 {
        return None;
    }

    // Parse cfg_type
    let cfg_type = VirtioCfgType::from_u8(cfg_type_raw)?;

    // Read offset (bytes 8-11, LE)
    let offset_dword = pci_config_read_32(addr.bus, addr.device, addr.function, offset + 8);
    let cap_offset = le_u32(
        byte_of(offset_dword, 0),
        byte_of(offset_dword, 1),
        byte_of(offset_dword, 2),
        byte_of(offset_dword, 3),
    );

    // Read length (bytes 12-15, LE)
    let length_dword = pci_config_read_32(addr.bus, addr.device, addr.function, offset + 12);
    let cap_length = le_u32(
        byte_of(length_dword, 0),
        byte_of(length_dword, 1),
        byte_of(length_dword, 2),
        byte_of(length_dword, 3),
    );

    // Read notify_off_multiplier for NotifyCfg (bytes 16-19)
    let notify_off_multiplier = if cfg_type == VirtioCfgType::NotifyCfg {
        let mult_dword = pci_config_read_32(addr.bus, addr.device, addr.function, offset + 16);
        le_u32(
            byte_of(mult_dword, 0),
            byte_of(mult_dword, 1),
            byte_of(mult_dword, 2),
            byte_of(mult_dword, 3),
        )
    } else {
        0
    };

    Some(VirtioCapability {
        cfg_type,
        bar,
        offset: cap_offset,
        length: cap_length,
        notify_off_multiplier,
    })
}

// ============================================================================
// BAR Resolution
// ============================================================================

/// Resolve capabilities to absolute memory addresses
///
/// # Safety
/// Performs PCI configuration space reads.
pub unsafe fn resolve_mmio_regions(
    addr: &PciAddress,
    caps: &VirtioCapabilities,
) -> Result<VirtioMmioRegions, &'static str> {
    let common = caps.common_cfg.ok_or("Missing CommonCfg capability")?;
    let notify = caps.notify_cfg.ok_or("Missing NotifyCfg capability")?;
    let isr = caps.isr_cfg.ok_or("Missing IsrCfg capability")?;
    let device = caps.device_cfg.ok_or("Missing DeviceCfg capability")?;

    // Resolve BAR addresses
    let common_bar = read_bar_address(addr, common.bar)?;
    let notify_bar = read_bar_address(addr, notify.bar)?;
    let isr_bar = read_bar_address(addr, isr.bar)?;
    let device_bar = read_bar_address(addr, device.bar)?;

    Ok(VirtioMmioRegions {
        common_cfg: (common_bar + common.offset as u64) as usize,
        common_cfg_len: common.length,
        notify_cfg: (notify_bar + notify.offset as u64) as usize,
        notify_off_multiplier: notify.notify_off_multiplier,
        isr_cfg: (isr_bar + isr.offset as u64) as usize,
        device_cfg: (device_bar + device.offset as u64) as usize,
        device_cfg_len: device.length,
    })
}

/// Read a BAR and extract the memory base address
///
/// Handles both 32-bit and 64-bit Memory BARs.
unsafe fn read_bar_address(addr: &PciAddress, bar_idx: u8) -> Result<u64, &'static str> {
    if bar_idx > 5 {
        return Err("BAR index out of range");
    }

    let bar_offset = 0x10 + (bar_idx * 4);
    let bar_low = pci_config_read_32(addr.bus, addr.device, addr.function, bar_offset);

    // Check Memory vs I/O (bit 0)
    if (bar_low & 0x01) != 0 {
        return Err("BAR is I/O type (expected Memory)");
    }

    // Check memory type (bits 1-2)
    let mem_type = (bar_low >> 1) & 0x03;

    match mem_type {
        0b00 => {
            // 32-bit Memory BAR
            Ok((bar_low & 0xFFFF_FFF0) as u64)
        }
        0b10 => {
            // 64-bit Memory BAR - read high 32 bits from next BAR
            if bar_idx >= 5 {
                return Err("64-bit BAR at invalid position");
            }
            let bar_high = pci_config_read_32(addr.bus, addr.device, addr.function, bar_offset + 4);
            let full_addr = ((bar_high as u64) << 32) | ((bar_low & 0xFFFF_FFF0) as u64);
            Ok(full_addr)
        }
        _ => Err("Unsupported BAR memory type"),
    }
}
