//! Modern Virtio 1.0 Network Driver (MMIO)
//!
//! Architecture-agnostic Virtio 1.0 implementation using Memory-Mapped I/O.
//! This driver is designed for portability across x86, ARM, and RISC-V.
//!
//! ## Initialization State Machine (Virtio 1.0 Section 3.1)
//!
//! ```text
//! ┌─────────┐   ┌─────────────┐   ┌────────┐   ┌──────────┐
//! │  RESET  │ → │ ACKNOWLEDGE │ → │ DRIVER │ → │ FEATURES │
//! └─────────┘   └─────────────┘   └────────┘   └──────────┘
//!                                                    │
//!       ┌────────────────────────────────────────────┘
//!       ↓
//! ┌─────────────┐   ┌────────────┐   ┌───────────┐
//! │ FEATURES_OK │ → │   QUEUES   │ → │ DRIVER_OK │
//! └─────────────┘   └────────────┘   └───────────┘
//! ```
//!
//! ## Memory Strategy: Aligned BSS Trick
//!
//! Queue memory is statically allocated in .bss with 4096-byte alignment.
//! In identity-mapped UEFI: Physical Address = Virtual Address.

use core::ptr::{read_volatile, write_volatile};
use crate::pci_modern::VirtioMmioRegions;
use crate::interrupts::{read_isr, IsrResult, INTERRUPT_PENDING};

// ============================================================================
// Queue Configuration
// ============================================================================

/// Standard QEMU queue size
const QUEUE_SIZE: usize = 256;

/// Descriptor flag: buffer continues via next field
const VIRTQ_DESC_F_NEXT: u16 = 1;

/// Descriptor flag: buffer is device-writable
const VIRTQ_DESC_F_WRITE: u16 = 2;

// ============================================================================
// Device Status Bits (Virtio 1.0 Section 2.1)
// ============================================================================

const STATUS_ACKNOWLEDGE: u8 = 1;        // OS found device
const STATUS_DRIVER: u8 = 2;             // OS knows how to drive it
const STATUS_DRIVER_OK: u8 = 4;          // Driver ready
const STATUS_FEATURES_OK: u8 = 8;        // Feature negotiation complete
const STATUS_DEVICE_NEEDS_RESET: u8 = 64; // Unrecoverable error
const STATUS_FAILED: u8 = 128;           // Driver gave up

// ============================================================================
// Feature Bits (64-bit feature space)
// ============================================================================

/// MUST negotiate for Modern devices (Bit 32)
const VIRTIO_F_VERSION_1: u64 = 1 << 32;

/// Device provides MAC address (Bit 5)
const VIRTIO_NET_F_MAC: u64 = 1 << 5;

/// Device status available (Bit 16)
const VIRTIO_NET_F_STATUS: u64 = 1 << 16;

// ============================================================================
// CommonCfg Register Offsets (Virtio 1.0 Section 4.1.4.3)
// ============================================================================

const COMMON_DFSELECT: usize = 0x00;       // Device feature selector
const COMMON_DF: usize = 0x04;             // Device features (32-bit bank)
const COMMON_GFSELECT: usize = 0x08;       // Guest feature selector
const COMMON_GF: usize = 0x0C;             // Guest features (32-bit bank)
const COMMON_MSIX_CONFIG: usize = 0x10;    // MSI-X config vector
const COMMON_NUM_QUEUES: usize = 0x12;     // Number of virtqueues
const COMMON_DEVICE_STATUS: usize = 0x14;  // Device status (8-bit)
const COMMON_CONFIG_GEN: usize = 0x15;     // Config generation (8-bit)
const COMMON_QUEUE_SELECT: usize = 0x16;   // Queue selector (16-bit)
const COMMON_QUEUE_SIZE: usize = 0x18;     // Queue size (16-bit)
const COMMON_QUEUE_MSIX: usize = 0x1A;     // Queue MSI-X vector
const COMMON_QUEUE_ENABLE: usize = 0x1C;   // Queue enable (16-bit)
const COMMON_QUEUE_NOTIFY_OFF: usize = 0x1E; // Queue notify offset (16-bit)
const COMMON_QUEUE_DESC: usize = 0x20;     // Descriptor table addr (64-bit)
const COMMON_QUEUE_AVAIL: usize = 0x28;    // Available ring addr (64-bit)
const COMMON_QUEUE_USED: usize = 0x30;     // Used ring addr (64-bit)

// ============================================================================
// Virtqueue Structures
// ============================================================================

/// Virtqueue Descriptor (16 bytes, 16-byte aligned)
#[repr(C, align(16))]
#[derive(Debug, Clone, Copy, Default)]
pub struct VirtqDesc {
    /// Buffer physical address
    pub addr: u64,
    /// Buffer length
    pub len: u32,
    /// Flags (NEXT, WRITE, INDIRECT)
    pub flags: u16,
    /// Next descriptor index
    pub next: u16,
}

/// Available Ring (driver → device)
#[repr(C, align(2))]
pub struct VirtqAvail {
    pub flags: u16,
    pub idx: u16,
    pub ring: [u16; QUEUE_SIZE],
    pub used_event: u16,
}

/// Used Ring Element
#[repr(C, align(4))]
#[derive(Debug, Clone, Copy, Default)]
pub struct VirtqUsedElem {
    pub id: u32,
    pub len: u32,
}

/// Used Ring (device → driver)
#[repr(C, align(4))]
pub struct VirtqUsed {
    pub flags: u16,
    pub idx: u16,
    pub ring: [VirtqUsedElem; QUEUE_SIZE],
    pub avail_event: u16,
}

// ============================================================================
// Page-Aligned Memory Layout
// ============================================================================

/// Descriptor Table (page-aligned)
#[repr(C, align(4096))]
pub struct DescTable {
    pub desc: [VirtqDesc; QUEUE_SIZE],
}

/// Available Ring (page-aligned)
#[repr(C, align(4096))]
pub struct AvailRing {
    pub avail: VirtqAvail,
}

/// Used Ring (page-aligned)
#[repr(C, align(4096))]
pub struct UsedRing {
    pub used: VirtqUsed,
}

/// Complete Virtqueue Memory
#[repr(C, align(4096))]
pub struct VirtqueueMem {
    pub desc: DescTable,
    pub avail: AvailRing,
    pub used: UsedRing,
}

impl VirtqueueMem {
    const fn zeroed() -> Self {
        Self {
            desc: DescTable {
                desc: [VirtqDesc { addr: 0, len: 0, flags: 0, next: 0 }; QUEUE_SIZE],
            },
            avail: AvailRing {
                avail: VirtqAvail {
                    flags: 0,
                    idx: 0,
                    ring: [0; QUEUE_SIZE],
                    used_event: 0,
                },
            },
            used: UsedRing {
                used: VirtqUsed {
                    flags: 0,
                    idx: 0,
                    ring: [VirtqUsedElem { id: 0, len: 0 }; QUEUE_SIZE],
                    avail_event: 0,
                },
            },
        }
    }
}

// ============================================================================
// Static BSS Allocations (Aligned BSS Trick)
// ============================================================================

/// RX Queue (receive)
static mut RX_QUEUE: VirtqueueMem = VirtqueueMem::zeroed();

/// TX Queue (transmit)
static mut TX_QUEUE: VirtqueueMem = VirtqueueMem::zeroed();

/// RX Packet Buffers
const PACKET_BUF_SIZE: usize = 2048;
const NUM_RX_BUFFERS: usize = 64;

#[repr(C, align(4096))]
struct RxBufferPool {
    buffers: [[u8; PACKET_BUF_SIZE]; NUM_RX_BUFFERS],
}

static mut RX_BUFFERS: RxBufferPool = RxBufferPool {
    buffers: [[0u8; PACKET_BUF_SIZE]; NUM_RX_BUFFERS],
};

// ============================================================================
// MMIO Helpers (Volatile, Architecture-Agnostic)
// ============================================================================

#[inline]
unsafe fn mmio_read8(addr: usize) -> u8 {
    read_volatile(addr as *const u8)
}

#[inline]
unsafe fn mmio_write8(addr: usize, val: u8) {
    write_volatile(addr as *mut u8, val);
}

#[inline]
unsafe fn mmio_read16(addr: usize) -> u16 {
    read_volatile(addr as *const u16)
}

#[inline]
unsafe fn mmio_write16(addr: usize, val: u16) {
    write_volatile(addr as *mut u16, val);
}

#[inline]
unsafe fn mmio_read32(addr: usize) -> u32 {
    read_volatile(addr as *const u32)
}

#[inline]
unsafe fn mmio_write32(addr: usize, val: u32) {
    write_volatile(addr as *mut u32, val);
}

/// Write 64-bit value (as two 32-bit writes, low then high)
#[inline]
unsafe fn mmio_write64(addr: usize, val: u64) {
    mmio_write32(addr, val as u32);
    mmio_write32(addr + 4, (val >> 32) as u32);
}

// ============================================================================
// Doorbell Calculation
// ============================================================================

/// Calculate the doorbell address for a queue
///
/// Formula: Doorbell = NotifyBase + (QueueNotifyOffset * NotifyOffMultiplier)
#[inline]
fn calc_doorbell(notify_base: usize, notify_off: u16, multiplier: u32) -> usize {
    notify_base + (notify_off as usize) * (multiplier as usize)
}

// ============================================================================
// Modern Virtio Network Driver
// ============================================================================

/// Queue runtime state
struct QueueState {
    /// Queue is enabled
    enabled: bool,
    /// Doorbell address for this queue
    doorbell: usize,
    /// Last seen used index
    last_used_idx: u16,
    /// Next available index to write
    next_avail_idx: u16,
}

impl QueueState {
    const fn new() -> Self {
        Self {
            enabled: false,
            doorbell: 0,
            last_used_idx: 0,
            next_avail_idx: 0,
        }
    }
}

/// Modern Virtio 1.0 Network Driver
pub struct VirtioModern {
    // MMIO region bases
    common_cfg: usize,
    notify_base: usize,
    notify_off_mult: u32,
    isr_cfg: usize,
    device_cfg: usize,
    device_cfg_len: u32,

    // Queue state
    rx_queue: QueueState,
    tx_queue: QueueState,

    // Device info
    pub mac: [u8; 6],
    num_queues: u16,
    features_ok: bool,
}

impl VirtioModern {
    /// Create driver from resolved MMIO regions
    pub fn new(regions: VirtioMmioRegions) -> Self {
        Self {
            common_cfg: regions.common_cfg,
            notify_base: regions.notify_cfg,
            notify_off_mult: regions.notify_off_multiplier,
            isr_cfg: regions.isr_cfg,
            device_cfg: regions.device_cfg,
            device_cfg_len: regions.device_cfg_len,
            rx_queue: QueueState::new(),
            tx_queue: QueueState::new(),
            mac: [0; 6],
            num_queues: 0,
            features_ok: false,
        }
    }

    /// Initialize the device
    ///
    /// # Arguments
    /// * `phys_offset` - Value to subtract from VA to get PA (0 for identity mapped)
    pub fn init(&mut self, phys_offset: u64) -> Result<(), &'static str> {
        unsafe {
            // ================================================================
            // Step 1: RESET
            // ================================================================
            self.write_status(0);

            // Spin wait for reset
            for _ in 0..100_000 {
                if self.read_status() == 0 {
                    break;
                }
                core::hint::spin_loop();
            }

            if self.read_status() != 0 {
                return Err("Device failed to reset");
            }

            // ================================================================
            // Step 2: ACKNOWLEDGE
            // ================================================================
            self.write_status(STATUS_ACKNOWLEDGE);

            // ================================================================
            // Step 3: DRIVER
            // ================================================================
            self.write_status(STATUS_ACKNOWLEDGE | STATUS_DRIVER);

            // ================================================================
            // Step 4: Feature Negotiation (64-bit via selectors)
            // ================================================================

            // Read device features [31:0]
            mmio_write32(self.common_cfg + COMMON_DFSELECT, 0);
            let feat_low = mmio_read32(self.common_cfg + COMMON_DF);

            // Read device features [63:32]
            mmio_write32(self.common_cfg + COMMON_DFSELECT, 1);
            let feat_high = mmio_read32(self.common_cfg + COMMON_DF);

            let device_features = ((feat_high as u64) << 32) | (feat_low as u64);

            // MUST negotiate VERSION_1 for Modern devices
            if (device_features & VIRTIO_F_VERSION_1) == 0 {
                self.write_status(STATUS_FAILED);
                return Err("Device lacks VIRTIO_F_VERSION_1");
            }

            // Check for MAC feature
            if (device_features & VIRTIO_NET_F_MAC) == 0 {
                self.write_status(STATUS_FAILED);
                return Err("Device lacks VIRTIO_NET_F_MAC");
            }

            // Accept VERSION_1 and MAC
            let guest_features = VIRTIO_F_VERSION_1 | VIRTIO_NET_F_MAC;

            // Write guest features [31:0]
            mmio_write32(self.common_cfg + COMMON_GFSELECT, 0);
            mmio_write32(self.common_cfg + COMMON_GF, guest_features as u32);

            // Write guest features [63:32]
            mmio_write32(self.common_cfg + COMMON_GFSELECT, 1);
            mmio_write32(self.common_cfg + COMMON_GF, (guest_features >> 32) as u32);

            // ================================================================
            // Step 5: FEATURES_OK Gate
            // ================================================================
            self.write_status(STATUS_ACKNOWLEDGE | STATUS_DRIVER | STATUS_FEATURES_OK);

            // ================================================================
            // Step 6: Verify FEATURES_OK (CRITICAL)
            // ================================================================
            let status = self.read_status();
            if (status & STATUS_FEATURES_OK) == 0 {
                self.write_status(STATUS_FAILED);
                return Err("FEATURES_OK not accepted by device");
            }
            self.features_ok = true;

            // Read number of queues
            self.num_queues = mmio_read16(self.common_cfg + COMMON_NUM_QUEUES);

            // ================================================================
            // Step 7: Configure Queues
            // ================================================================

            // RX Queue (0)
            let rx_doorbell = self.setup_queue(0, &mut RX_QUEUE, phys_offset)?;
            self.rx_queue.doorbell = rx_doorbell;
            self.rx_queue.enabled = true;

            // TX Queue (1)
            let tx_doorbell = self.setup_queue(1, &mut TX_QUEUE, phys_offset)?;
            self.tx_queue.doorbell = tx_doorbell;
            self.tx_queue.enabled = true;

            // ================================================================
            // Step 8: DRIVER_OK
            // ================================================================
            self.write_status(
                STATUS_ACKNOWLEDGE | STATUS_DRIVER | STATUS_FEATURES_OK | STATUS_DRIVER_OK,
            );

            // Verify no errors
            let final_status = self.read_status();
            if (final_status & STATUS_FAILED) != 0 {
                return Err("Device set FAILED after DRIVER_OK");
            }
            if (final_status & STATUS_DEVICE_NEEDS_RESET) != 0 {
                return Err("Device needs reset");
            }

            // ================================================================
            // Step 9: Read MAC from DeviceCfg
            // ================================================================
            if self.device_cfg_len >= 6 {
                for i in 0..6 {
                    self.mac[i] = mmio_read8(self.device_cfg + i);
                }
            }

            // ================================================================
            // Step 10: Provision RX Queue
            // ================================================================
            self.provision_rx_queue(phys_offset)?;
        }

        Ok(())
    }

    /// Setup a single virtqueue
    unsafe fn setup_queue(
        &self,
        index: u16,
        mem: &mut VirtqueueMem,
        phys_offset: u64,
    ) -> Result<usize, &'static str> {
        // Select queue
        mmio_write16(self.common_cfg + COMMON_QUEUE_SELECT, index);

        // Read size
        let size = mmio_read16(self.common_cfg + COMMON_QUEUE_SIZE);
        if size == 0 {
            return Err("Queue unavailable (size=0)");
        }
        if size > QUEUE_SIZE as u16 {
            return Err("Queue too large for allocation");
        }

        // Calculate physical addresses
        let desc_virt = &mem.desc as *const _ as u64;
        let avail_virt = &mem.avail as *const _ as u64;
        let used_virt = &mem.used as *const _ as u64;

        let desc_phys = desc_virt.wrapping_sub(phys_offset);
        let avail_phys = avail_virt.wrapping_sub(phys_offset);
        let used_phys = used_virt.wrapping_sub(phys_offset);

        // Write 64-bit addresses
        mmio_write64(self.common_cfg + COMMON_QUEUE_DESC, desc_phys);
        mmio_write64(self.common_cfg + COMMON_QUEUE_AVAIL, avail_phys);
        mmio_write64(self.common_cfg + COMMON_QUEUE_USED, used_phys);

        // Read queue notify offset
        let notify_off = mmio_read16(self.common_cfg + COMMON_QUEUE_NOTIFY_OFF);

        // Enable the queue
        mmio_write16(self.common_cfg + COMMON_QUEUE_ENABLE, 1);

        // Calculate doorbell address
        let doorbell = calc_doorbell(self.notify_base, notify_off, self.notify_off_mult);

        Ok(doorbell)
    }

    /// Provision RX queue with receive buffers
    unsafe fn provision_rx_queue(&mut self, phys_offset: u64) -> Result<(), &'static str> {
        let desc = &mut RX_QUEUE.desc.desc;
        let avail = &mut RX_QUEUE.avail.avail;

        for i in 0..NUM_RX_BUFFERS {
            let buf_virt = &RX_BUFFERS.buffers[i] as *const _ as u64;
            let buf_phys = buf_virt.wrapping_sub(phys_offset);

            // Setup descriptor
            desc[i].addr = buf_phys;
            desc[i].len = PACKET_BUF_SIZE as u32;
            desc[i].flags = VIRTQ_DESC_F_WRITE; // Device writes here
            desc[i].next = 0;

            // Add to available ring
            avail.ring[i] = i as u16;
        }

        // Update available index
        avail.idx = NUM_RX_BUFFERS as u16;
        self.rx_queue.next_avail_idx = NUM_RX_BUFFERS as u16;

        // Ring doorbell to notify device
        self.ring_doorbell(0);

        Ok(())
    }

    /// Ring the doorbell for a queue
    pub fn ring_doorbell(&self, queue: u16) {
        unsafe {
            let doorbell = match queue {
                0 => self.rx_queue.doorbell,
                1 => self.tx_queue.doorbell,
                _ => return,
            };
            mmio_write16(doorbell, queue);
        }
    }

    /// Poll for and handle interrupts
    ///
    /// Call this regularly in UEFI (no hardware interrupts).
    pub fn poll(&mut self) -> Option<IsrResult> {
        unsafe {
            let result = read_isr(self.isr_cfg);
            if result.any_pending() {
                if result.queue_interrupt {
                    INTERRUPT_PENDING.signal_rx();
                }
                if result.config_interrupt {
                    INTERRUPT_PENDING.signal_config();
                }
                Some(result)
            } else {
                None
            }
        }
    }

    /// Check if device is operational
    pub fn is_alive(&self) -> bool {
        unsafe {
            let s = self.read_status();
            (s & STATUS_DRIVER_OK) != 0
                && (s & STATUS_FAILED) == 0
                && (s & STATUS_DEVICE_NEEDS_RESET) == 0
        }
    }

    /// Get number of available queues
    pub fn num_queues(&self) -> u16 {
        self.num_queues
    }

    /// Check if FEATURES_OK was accepted
    pub fn features_ok(&self) -> bool {
        self.features_ok
    }

    /// Format MAC for logging
    pub fn format_mac<'a>(&self, buf: &'a mut [u8; 18]) -> &'a str {
        const HEX: &[u8; 16] = b"0123456789ABCDEF";
        for i in 0..6 {
            buf[i * 3] = HEX[(self.mac[i] >> 4) as usize];
            buf[i * 3 + 1] = HEX[(self.mac[i] & 0x0F) as usize];
            if i < 5 {
                buf[i * 3 + 2] = b':';
            }
        }
        core::str::from_utf8(&buf[..17]).unwrap_or("??:??:??:??:??:??")
    }

    // ========================================================================
    // Internal Helpers
    // ========================================================================

    unsafe fn read_status(&self) -> u8 {
        mmio_read8(self.common_cfg + COMMON_DEVICE_STATUS)
    }

    unsafe fn write_status(&self, status: u8) {
        mmio_write8(self.common_cfg + COMMON_DEVICE_STATUS, status);
    }
}
