//! IVSHMEM (Inter-VM Shared Memory) PCI Driver
//!
//! Phase 4: THE OPTIC NERVE - Bridges kernel memory to host via QEMU shared memory.
//!
//! ## Architecture
//!
//! ```text
//! ┌─────────────────┐     IVSHMEM     ┌─────────────────┐     mmap      ┌──────────────┐
//! │     KERNEL      │ <=============> │   QEMU Device   │ <============>│  BIO-BRIDGE  │
//! │   (BioStream)   │   BAR2 MMIO     │  /dev/shm/...   │   Host File   │  (Host Tool) │
//! └─────────────────┘                 └─────────────────┘               └──────────────┘
//! ```
//!
//! ## QEMU Configuration
//!
//! ```bash
//! -device ivshmem-plain,memdev=biostream \
//! -object memory-backend-file,size=64K,share=on,mem-path=/dev/shm/eaos_biostream,id=biostream
//! ```
//!
//! ## PCI Device IDs
//!
//! - Vendor: Red Hat (0x1AF4)
//! - Device: IVSHMEM (0x1110)
//! - BAR0: Registers (interrupt control, not used)
//! - BAR2: Shared memory region (this is what we want)

use crate::pci::{pci_config_read_32, PciAddress, PciDeviceInfo, VIRTIO_VENDOR_ID};

// ============================================================================
// IVSHMEM Device IDs
// ============================================================================

/// IVSHMEM Device ID (ivshmem-plain)
pub const IVSHMEM_DEVICE_ID: u16 = 0x1110;

/// IVSHMEM Doorbell Device ID (ivshmem-doorbell, not used)
#[allow(dead_code)]
pub const IVSHMEM_DOORBELL_DEVICE_ID: u16 = 0x1110;

// ============================================================================
// IVSHMEM Driver
// ============================================================================

/// IVSHMEM driver instance
#[derive(Debug)]
pub struct IvshmemDevice {
    /// PCI address of the device
    pub address: PciAddress,
    /// Physical address of the shared memory region (BAR2)
    pub shm_base: u64,
    /// Size of the shared memory region
    pub shm_size: u64,
}

impl IvshmemDevice {
    /// Check if a PCI device is an IVSHMEM device
    pub fn is_ivshmem(info: &PciDeviceInfo) -> bool {
        info.vendor_id == VIRTIO_VENDOR_ID && info.device_id == IVSHMEM_DEVICE_ID
    }

    /// Probe and initialize an IVSHMEM device
    ///
    /// # Safety
    /// Performs PCI configuration space reads.
    pub unsafe fn probe(info: &PciDeviceInfo) -> Result<Self, &'static str> {
        if !Self::is_ivshmem(info) {
            return Err("Not an IVSHMEM device");
        }

        // Read BAR2 (the shared memory region)
        // BAR2 is at PCI config offset 0x18 (0x10 + 2*4)
        let bar2_low = pci_config_read_32(
            info.address.bus,
            info.address.device,
            info.address.function,
            0x18,
        );

        // Check if it's a memory BAR (bit 0 = 0)
        if (bar2_low & 0x01) != 0 {
            return Err("BAR2 is I/O space, expected memory");
        }

        // Check memory type (bits 1-2)
        let mem_type = (bar2_low >> 1) & 0x03;

        let shm_base = match mem_type {
            0b00 => {
                // 32-bit memory BAR
                (bar2_low & 0xFFFF_FFF0) as u64
            }
            0b10 => {
                // 64-bit memory BAR - read high 32 bits from BAR3
                let bar3_high = pci_config_read_32(
                    info.address.bus,
                    info.address.device,
                    info.address.function,
                    0x1C,
                );
                ((bar3_high as u64) << 32) | ((bar2_low & 0xFFFF_FFF0) as u64)
            }
            _ => return Err("Unsupported BAR2 memory type"),
        };

        if shm_base == 0 {
            return Err("BAR2 not configured by firmware");
        }

        // Determine BAR size by writing all 1s and reading back
        // This is the standard PCI BAR sizing mechanism
        let shm_size = Self::size_bar(
            info.address.bus,
            info.address.device,
            info.address.function,
            0x18,
            bar2_low,
        );

        Ok(Self {
            address: info.address,
            shm_base,
            shm_size,
        })
    }

    /// Size a BAR by writing all 1s and measuring the mask
    ///
    /// # Safety
    /// Temporarily modifies BAR value (restored after).
    unsafe fn size_bar(bus: u8, device: u8, function: u8, offset: u8, original: u32) -> u64 {
        use crate::pci::pci_config_write_32;

        // Write all 1s to measure size
        pci_config_write_32(bus, device, function, offset, 0xFFFF_FFFF);

        // Read back to see which bits are hardwired
        let sized = pci_config_read_32(bus, device, function, offset);

        // Restore original value
        pci_config_write_32(bus, device, function, offset, original);

        // Mask out the type bits and invert to get size
        let mask = sized & 0xFFFF_FFF0;
        if mask == 0 {
            return 0;
        }

        // Size = ~mask + 1 (two's complement)
        ((!mask) as u64) + 1
    }

    /// Get the shared memory region as a mutable pointer
    ///
    /// # Safety
    /// The returned pointer is valid only if:
    /// - The BAR is mapped in the address space
    /// - No other code accesses the same memory concurrently
    pub unsafe fn shm_ptr<T>(&self) -> *mut T {
        self.shm_base as *mut T
    }

    /// Format device info for logging
    pub fn format_info<'a>(&self, buf: &'a mut [u8; 64]) -> &'a str {
        // Format: "IVSHMEM @ BB:DD.F, SHM=0xXXXX, SIZE=XXK"
        let hex = b"0123456789ABCDEF";
        let mut pos = 0;

        // "IVSHMEM @ "
        let prefix = b"IVSHMEM @ ";
        buf[..prefix.len()].copy_from_slice(prefix);
        pos += prefix.len();

        // BDF
        buf[pos] = hex[(self.address.bus >> 4) as usize];
        buf[pos + 1] = hex[(self.address.bus & 0xF) as usize];
        buf[pos + 2] = b':';
        buf[pos + 3] = hex[(self.address.device >> 4) as usize];
        buf[pos + 4] = hex[(self.address.device & 0xF) as usize];
        buf[pos + 5] = b'.';
        buf[pos + 6] = hex[(self.address.function & 0x7) as usize];
        pos += 7;

        // ", SHM=0x"
        let shm_prefix = b", SHM=0x";
        buf[pos..pos + shm_prefix.len()].copy_from_slice(shm_prefix);
        pos += shm_prefix.len();

        // Address (16 hex digits for 64-bit)
        for i in (0..16).rev() {
            let nibble = ((self.shm_base >> (i * 4)) & 0xF) as usize;
            buf[pos] = hex[nibble];
            pos += 1;
        }

        // Size in KB
        let size_kb = self.shm_size / 1024;
        if size_kb > 0 && size_kb < 10000 {
            let size_suffix = b", SIZE=";
            buf[pos..pos + size_suffix.len()].copy_from_slice(size_suffix);
            pos += size_suffix.len();

            // Simple decimal for size
            if size_kb >= 1000 {
                buf[pos] = b'0' + ((size_kb / 1000) % 10) as u8;
                pos += 1;
            }
            if size_kb >= 100 {
                buf[pos] = b'0' + ((size_kb / 100) % 10) as u8;
                pos += 1;
            }
            if size_kb >= 10 {
                buf[pos] = b'0' + ((size_kb / 10) % 10) as u8;
                pos += 1;
            }
            buf[pos] = b'0' + (size_kb % 10) as u8;
            pos += 1;

            buf[pos] = b'K';
            pos += 1;
        }

        core::str::from_utf8(&buf[..pos]).unwrap_or("IVSHMEM")
    }
}

// ============================================================================
// Global IVSHMEM Instance
// ============================================================================

/// Global IVSHMEM device (set during PCI scan)
pub static mut IVSHMEM_DEVICE: Option<IvshmemDevice> = None;

/// Scan PCI bus for IVSHMEM device
///
/// # Safety
/// Performs PCI configuration space reads. Must be called during boot.
pub unsafe fn scan_for_ivshmem() -> Option<&'static IvshmemDevice> {
    // Scan buses 0-7 (QEMU usually puts devices on bus 0)
    for bus in 0..8u8 {
        for device in 0..32u8 {
            // Read vendor/device ID
            let id_reg = pci_config_read_32(bus, device, 0, 0);
            let vendor_id = (id_reg & 0xFFFF) as u16;
            let device_id = ((id_reg >> 16) & 0xFFFF) as u16;

            if vendor_id == 0xFFFF {
                continue; // Empty slot
            }

            if vendor_id == VIRTIO_VENDOR_ID && device_id == IVSHMEM_DEVICE_ID {
                // Found IVSHMEM device
                let class_reg = pci_config_read_32(bus, device, 0, 0x08);
                let header_reg = pci_config_read_32(bus, device, 0, 0x0C);

                let info = PciDeviceInfo {
                    address: PciAddress::new(bus, device, 0),
                    vendor_id,
                    device_id,
                    class_code: ((class_reg >> 24) & 0xFF) as u8,
                    subclass: ((class_reg >> 16) & 0xFF) as u8,
                    prog_if: ((class_reg >> 8) & 0xFF) as u8,
                    revision_id: (class_reg & 0xFF) as u8,
                    header_type: ((header_reg >> 16) & 0xFF) as u8,
                };

                if let Ok(dev) = IvshmemDevice::probe(&info) {
                    IVSHMEM_DEVICE = Some(dev);
                    return IVSHMEM_DEVICE.as_ref();
                }
            }
        }
    }

    None
}

/// Get the global IVSHMEM device (if found)
pub fn get_ivshmem() -> Option<&'static IvshmemDevice> {
    unsafe { IVSHMEM_DEVICE.as_ref() }
}

// ============================================================================
// BioStream Integration
// ============================================================================

/// Get pointer to BioStream in IVSHMEM
///
/// This returns a pointer to the shared memory region where BioStream
/// should be mapped. The bio-bridge host tool will mmap the same region.
///
/// # Safety
/// Caller must ensure BioStream struct fits within the shared memory size.
pub unsafe fn get_biostream_ptr() -> Option<*mut u8> {
    get_ivshmem().map(|dev| dev.shm_base as *mut u8)
}

/// Get the size of the IVSHMEM shared memory region
pub fn get_ivshmem_size() -> Option<u64> {
    get_ivshmem().map(|dev| dev.shm_size)
}
