//! PCI Bus Scanner for Virtio Device Discovery
//!
//! This module implements raw PCI Configuration Mechanism #1 access
//! to enumerate devices on the PCI bus and locate Virtio network devices.
//!
//! ## PCI Configuration Space Access
//!
//! Legacy PCI uses two I/O ports:
//! - CONFIG_ADDRESS (0xCF8): Write the address we want to query
//! - CONFIG_DATA (0xCFC): Read/write the actual configuration data
//!
//! The 32-bit address format:
//! ```text
//! 31    | 30-24    | 23-16 | 15-11  | 10-8     | 7-2    | 1-0
//! Enable| Reserved | Bus   | Device | Function | Offset | 00
//! ```

use x86_64::instructions::port::{Port, PortWriteOnly};

// ============================================================================
// PCI Configuration Ports
// ============================================================================

/// PCI Configuration Address Port
const CONFIG_ADDRESS: u16 = 0x0CF8;

/// PCI Configuration Data Port
const CONFIG_DATA: u16 = 0x0CFC;

// ============================================================================
// Virtio Device IDs
// ============================================================================

/// Red Hat/Qumranet Virtio Vendor ID
pub const VIRTIO_VENDOR_ID: u16 = 0x1AF4;

/// Virtio Network Device IDs
/// Legacy transitional device ID (QEMU default)
pub const VIRTIO_NET_DEVICE_ID_LEGACY: u16 = 0x1000;
/// Modern virtio-net device ID (1.0+ spec)
pub const VIRTIO_NET_DEVICE_ID_MODERN: u16 = 0x1041;

/// Invalid vendor ID (empty slot)
const INVALID_VENDOR_ID: u16 = 0xFFFF;

// ============================================================================
// PCI Address Components
// ============================================================================

/// Bus/Device/Function address for a PCI device
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PciAddress {
    pub bus: u8,
    pub device: u8,
    pub function: u8,
}

impl PciAddress {
    /// Create a new PCI address
    pub const fn new(bus: u8, device: u8, function: u8) -> Self {
        Self { bus, device, function }
    }

    /// Format as BDF string for logging (e.g., "00:03.0")
    pub fn format_bdf<'a>(&self, buf: &'a mut [u8; 8]) -> &'a str {
        // Format: BB:DD.F
        let hex = b"0123456789ABCDEF";
        buf[0] = hex[(self.bus >> 4) as usize];
        buf[1] = hex[(self.bus & 0xF) as usize];
        buf[2] = b':';
        buf[3] = hex[(self.device >> 4) as usize];
        buf[4] = hex[(self.device & 0xF) as usize];
        buf[5] = b'.';
        buf[6] = hex[(self.function & 0x7) as usize];
        buf[7] = 0;

        // Safe because we only use ASCII hex digits
        unsafe { core::str::from_utf8_unchecked(&buf[..7]) }
    }
}

/// Information about a discovered PCI device
#[derive(Debug, Clone, Copy)]
pub struct PciDeviceInfo {
    pub address: PciAddress,
    pub vendor_id: u16,
    pub device_id: u16,
    pub class_code: u8,
    pub subclass: u8,
    pub prog_if: u8,
    pub revision_id: u8,
    pub header_type: u8,
}

impl PciDeviceInfo {
    /// Check if this is a Virtio network device
    pub fn is_virtio_net(&self) -> bool {
        self.vendor_id == VIRTIO_VENDOR_ID
            && (self.device_id == VIRTIO_NET_DEVICE_ID_LEGACY
                || self.device_id == VIRTIO_NET_DEVICE_ID_MODERN)
    }

    /// Check if this is any Virtio device
    pub fn is_virtio(&self) -> bool {
        self.vendor_id == VIRTIO_VENDOR_ID
    }
}

// ============================================================================
// PCI Configuration Space Access
// ============================================================================

/// Build a PCI configuration address for port 0xCF8
///
/// The address format is:
/// - Bit 31: Enable bit (must be 1)
/// - Bits 23-16: Bus number
/// - Bits 15-11: Device number
/// - Bits 10-8: Function number
/// - Bits 7-2: Register offset (must be 32-bit aligned)
/// - Bits 1-0: Always 0
#[inline]
fn build_config_address(bus: u8, device: u8, function: u8, offset: u8) -> u32 {
    // Enable bit | Bus | Device | Function | Offset (aligned)
    0x8000_0000
        | ((bus as u32) << 16)
        | ((device as u32) << 11)
        | ((function as u32) << 8)
        | ((offset as u32) & 0xFC) // Mask to ensure 32-bit alignment
}

/// Read a 32-bit value from PCI configuration space
///
/// # Safety
/// This performs raw port I/O which is unsafe. Should only be called
/// during early boot when we have exclusive hardware access.
pub unsafe fn pci_config_read_32(bus: u8, device: u8, function: u8, offset: u8) -> u32 {
    let address = build_config_address(bus, device, function, offset);

    let mut addr_port = PortWriteOnly::<u32>::new(CONFIG_ADDRESS);
    let mut data_port = Port::<u32>::new(CONFIG_DATA);

    addr_port.write(address);
    data_port.read()
}

/// Write a 32-bit value to PCI configuration space
///
/// # Safety
/// This performs raw port I/O which is unsafe.
#[allow(dead_code)]
pub unsafe fn pci_config_write_32(bus: u8, device: u8, function: u8, offset: u8, value: u32) {
    let address = build_config_address(bus, device, function, offset);

    let mut addr_port = PortWriteOnly::<u32>::new(CONFIG_ADDRESS);
    let mut data_port = Port::<u32>::new(CONFIG_DATA);

    addr_port.write(address);
    data_port.write(value);
}

/// Read a 16-bit value from PCI configuration space
///
/// # Safety
/// This performs raw port I/O which is unsafe.
pub unsafe fn pci_config_read_16(bus: u8, device: u8, function: u8, offset: u8) -> u16 {
    let dword = pci_config_read_32(bus, device, function, offset & 0xFC);
    let shift = ((offset & 2) * 8) as u32;
    ((dword >> shift) & 0xFFFF) as u16
}

// ============================================================================
// PCI Bus Scanner
// ============================================================================

/// Result of a PCI bus scan
pub struct PciScanResult {
    /// Found Virtio-Net device address (if any)
    pub virtio_net: Option<PciDeviceInfo>,
    /// Total devices found
    pub device_count: usize,
}

/// Scan the entire PCI bus for devices
///
/// This performs a brute-force enumeration of all possible BDF combinations:
/// - 256 buses (0-255)
/// - 32 devices per bus (0-31)
/// - 8 functions per device (0-7)
///
/// For efficiency, we skip functions 1-7 for devices that don't have
/// the multi-function bit set.
///
/// # Safety
/// Must be called with exclusive access to PCI configuration space.
pub unsafe fn scan_pci_bus() -> PciScanResult {
    let mut result = PciScanResult {
        virtio_net: None,
        device_count: 0,
    };

    // Scan all buses
    for bus in 0..=255u8 {
        scan_bus(bus, &mut result);
    }

    result
}

/// Scan a single PCI bus
unsafe fn scan_bus(bus: u8, result: &mut PciScanResult) {
    for device in 0..32u8 {
        scan_device(bus, device, result);
    }
}

/// Scan a single PCI device (all functions)
unsafe fn scan_device(bus: u8, device: u8, result: &mut PciScanResult) {
    // First check if device exists at function 0
    let vendor_id = pci_config_read_16(bus, device, 0, 0x00);
    if vendor_id == INVALID_VENDOR_ID {
        return; // Empty slot
    }

    // Read header type to check multi-function bit
    let header_type = (pci_config_read_32(bus, device, 0, 0x0C) >> 16) as u8;
    let is_multifunction = (header_type & 0x80) != 0;

    // Scan function 0
    if let Some(info) = read_device_info(bus, device, 0) {
        check_and_record_device(info, result);
    }

    // If multi-function, scan remaining functions
    if is_multifunction {
        for function in 1..8u8 {
            let vendor_id = pci_config_read_16(bus, device, function, 0x00);
            if vendor_id != INVALID_VENDOR_ID {
                if let Some(info) = read_device_info(bus, device, function) {
                    check_and_record_device(info, result);
                }
            }
        }
    }
}

/// Read full device information from configuration space
unsafe fn read_device_info(bus: u8, device: u8, function: u8) -> Option<PciDeviceInfo> {
    let vendor_device = pci_config_read_32(bus, device, function, 0x00);
    let vendor_id = (vendor_device & 0xFFFF) as u16;
    let device_id = ((vendor_device >> 16) & 0xFFFF) as u16;

    if vendor_id == INVALID_VENDOR_ID {
        return None;
    }

    let class_rev = pci_config_read_32(bus, device, function, 0x08);
    let revision_id = (class_rev & 0xFF) as u8;
    let prog_if = ((class_rev >> 8) & 0xFF) as u8;
    let subclass = ((class_rev >> 16) & 0xFF) as u8;
    let class_code = ((class_rev >> 24) & 0xFF) as u8;

    let header_bist = pci_config_read_32(bus, device, function, 0x0C);
    let header_type = ((header_bist >> 16) & 0x7F) as u8; // Mask out multi-function bit

    Some(PciDeviceInfo {
        address: PciAddress::new(bus, device, function),
        vendor_id,
        device_id,
        class_code,
        subclass,
        prog_if,
        revision_id,
        header_type,
    })
}

/// Check if device is interesting and record it
fn check_and_record_device(info: PciDeviceInfo, result: &mut PciScanResult) {
    result.device_count += 1;

    // Check for Virtio-Net specifically
    if info.is_virtio_net() && result.virtio_net.is_none() {
        result.virtio_net = Some(info);
    }
}

// ============================================================================
// High-Level Interface
// ============================================================================

/// Find the first Virtio-Net device on the PCI bus
///
/// Returns the device info and BDF address if found.
///
/// # Safety
/// Must be called with exclusive access to PCI configuration space.
pub unsafe fn find_virtio_net() -> Option<PciDeviceInfo> {
    scan_pci_bus().virtio_net
}

/// Read a BAR (Base Address Register) from a PCI device
///
/// BARs are at offsets 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24
///
/// # Safety
/// Must be called with exclusive access to PCI configuration space.
pub unsafe fn read_bar(addr: &PciAddress, bar_index: u8) -> u32 {
    assert!(bar_index < 6, "BAR index must be 0-5");
    let offset = 0x10 + (bar_index * 4);
    pci_config_read_32(addr.bus, addr.device, addr.function, offset)
}

/// Determine if a BAR is memory-mapped or I/O
pub fn bar_is_memory(bar_value: u32) -> bool {
    (bar_value & 0x01) == 0
}

/// Get the base address from a memory BAR (masking flags)
pub fn bar_memory_address(bar_value: u32) -> u32 {
    bar_value & 0xFFFF_FFF0
}

/// Get the base address from an I/O BAR (masking flags)
pub fn bar_io_address(bar_value: u32) -> u32 {
    bar_value & 0xFFFF_FFFC
}

// ============================================================================
// Tests (for host builds only)
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_address_format() {
        // Bus 0, Device 3, Function 0, Offset 0
        let addr = build_config_address(0, 3, 0, 0);
        assert_eq!(addr, 0x8000_1800);

        // Bus 0, Device 4, Function 1, Offset 0x10
        let addr = build_config_address(0, 4, 1, 0x10);
        assert_eq!(addr, 0x8000_2110);

        // Bus 1, Device 0, Function 0, Offset 0
        let addr = build_config_address(1, 0, 0, 0);
        assert_eq!(addr, 0x8001_0000);
    }

    #[test]
    fn test_bdf_format() {
        let addr = PciAddress::new(0, 3, 0);
        let mut buf = [0u8; 8];
        let bdf = addr.format_bdf(&mut buf);
        assert_eq!(bdf, "00:03.0");

        let addr = PciAddress::new(1, 15, 2);
        let bdf = addr.format_bdf(&mut buf);
        assert_eq!(bdf, "01:0F.2");
    }

    #[test]
    fn test_virtio_detection() {
        let info = PciDeviceInfo {
            address: PciAddress::new(0, 3, 0),
            vendor_id: VIRTIO_VENDOR_ID,
            device_id: VIRTIO_NET_DEVICE_ID_LEGACY,
            class_code: 0x02,
            subclass: 0x00,
            prog_if: 0x00,
            revision_id: 0x00,
            header_type: 0x00,
        };
        assert!(info.is_virtio_net());
        assert!(info.is_virtio());

        let non_virtio = PciDeviceInfo {
            vendor_id: 0x8086,
            device_id: 0x1234,
            ..info
        };
        assert!(!non_virtio.is_virtio_net());
        assert!(!non_virtio.is_virtio());
    }
}
