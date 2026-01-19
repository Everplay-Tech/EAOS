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
use core::sync::atomic::{fence, Ordering};
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

/// RX buffer pool for received packets
#[repr(C, align(4096))]
pub struct RxBufferPool {
    /// Array of packet buffers
    pub buffers: [[u8; PACKET_BUF_SIZE]; NUM_RX_BUFFERS],
}

/// RX packet buffer pool
///
/// Phase 2: Made public for ARACHNID Spider access from scheduler.
pub static mut RX_BUFFERS: RxBufferPool = RxBufferPool {
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

        // CRITICAL: Barrier ensures hardware sees buffer addresses BEFORE the doorbell
        fence(Ordering::Release);

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

    /// Process completed RX buffers from used ring
    ///
    /// Returns `Some((buffer_id, byte_length))` if a packet was received,
    /// `None` if no new packets are available.
    pub fn process_rx(&mut self) -> Option<(usize, u32)> {
        unsafe {
            let used = &RX_QUEUE.used.used;
            let used_idx = read_volatile(&used.idx as *const u16);

            // Barrier: Ensure we see the data the hardware wrote
            fence(Ordering::Acquire);

            if self.rx_queue.last_used_idx == used_idx {
                return None; // Nothing new in the bucket
            }

            let idx = (self.rx_queue.last_used_idx as usize) % QUEUE_SIZE;
            let elem = read_volatile(&used.ring[idx] as *const VirtqUsedElem);

            // SAFETY: Defense against oversized packets (P1 Fix)
            if elem.len > PACKET_BUF_SIZE as u32 {
                return None;
            }

            self.rx_queue.last_used_idx = self.rx_queue.last_used_idx.wrapping_add(1);
            Some((elem.id as usize, elem.len)) // Returns (Buffer ID, Byte Length)
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

// ============================================================================
// BIO-S/1.0 Zero-Copy Telemetry Bridge
// ============================================================================

/// Magic sync word for BIO-STREAM protocol
pub const BIO_MAGIC: u32 = 0xEA01_EA01;

/// Invalid magic (signals write in progress)
pub const BIO_MAGIC_INVALID: u32 = 0x0000_0000;

/// The Sovereign Protocol: BIO-STREAM (Fixed 32 Bytes)
///
/// This structure is the wire format for kernel-to-userspace telemetry.
/// It's designed for zero-copy transfer via shared memory.
///
/// ## Tearing Prevention (SeqLock Pattern)
///
/// The `seq` field is a sequence counter:
/// - Odd value = write in progress (reader must retry)
/// - Even value = write complete (data is consistent)
///
/// Reader protocol:
/// 1. Read `seq` (if odd, spin)
/// 2. Read data
/// 3. Read `seq` again (if changed, retry from step 1)
#[repr(C)]
#[derive(Clone, Copy)]
pub struct BioFrame {
    /// Sequence counter for tearing detection (odd = write in progress)
    pub seq: u32,
    /// Sync Word (0xEA01EA01) - allows receiver to verify frame alignment
    pub magic: u32,
    /// CPU pressure: 0-1000 (maps to 0.0-100.0%)
    pub cpu_pressure: u16,
    /// Memory pressure: 0-1000 (maps to 0.0-100.0%)
    pub mem_pressure: u16,
    /// Packets Per Second received (instant)
    pub pps_rx: u32,
    /// Packets Per Second transmitted (instant)
    pub pps_tx: u32,
    /// System uptime in kernel ticks
    pub sys_uptime: u64,
    /// Status flags bitmask (bit 0: Alert, bit 1: Throttle)
    pub flags: u32,
}

impl BioFrame {
    /// Size of BioFrame in bytes (for protocol versioning)
    pub const SIZE: usize = 32;

    /// Create a new BioFrame with magic word set
    pub const fn new() -> Self {
        Self {
            seq: 0,  // Even = ready to read
            magic: BIO_MAGIC,
            cpu_pressure: 0,
            mem_pressure: 0,
            pps_rx: 0,
            pps_tx: 0,
            sys_uptime: 0,
            flags: 0,
        }
    }

    /// Check if sequence indicates write in progress
    #[inline]
    pub fn is_write_in_progress(seq: u32) -> bool {
        seq & 1 != 0  // Odd = writing
    }
}

/// The "Aligned BSS Bridge" (4KB Telemetry Page)
///
/// This structure is page-aligned for direct mmap by userspace.
/// The headroom allows WebSocket headers to be prepended without copying.
///
/// ## SeqLock Protocol
///
/// Writer (kernel):
/// 1. Increment seq to odd (atomic)
/// 2. Memory fence (Release)
/// 3. Write all fields
/// 4. Memory fence (Release)
/// 5. Increment seq to even (atomic)
///
/// Reader (userspace):
/// 1. Read seq (if odd, retry)
/// 2. Memory fence (Acquire)
/// 3. Copy all fields
/// 4. Memory fence (Acquire)
/// 5. Read seq again (if changed, retry)
#[repr(C, align(4096))]
pub struct SharedTelemetry {
    /// Headroom for WebSocket frame header (opcode + length)
    /// Allows zero-copy send: write header here, pass single pointer to NIC
    pub headroom: [u8; 4],
    /// The actual telemetry frame
    pub frame: BioFrame,
    /// Padding to fill 4KB page
    _pad: [u8; 4096 - 4 - BioFrame::SIZE],
}

impl SharedTelemetry {
    /// Create zeroed telemetry page with magic initialized
    pub const fn new() -> Self {
        Self {
            headroom: [0; 4],
            frame: BioFrame::new(),
            _pad: [0; 4096 - 4 - BioFrame::SIZE],
        }
    }

    /// Get physical address of the telemetry page (for userspace mmap)
    pub fn phys_addr(&self) -> usize {
        self as *const _ as usize
    }

    /// Update telemetry with SeqLock tearing prevention (Writer Side)
    ///
    /// This ensures readers always see a consistent frame, never a
    /// "Frankenstein" mix of old and new values.
    ///
    /// ## SeqLock Writer Protocol
    /// ```text
    /// 1. seq++ (odd = write in progress)
    /// 2. smp_wmb() - write barrier
    /// 3. write payload
    /// 4. smp_wmb() - write barrier
    /// 5. seq++ (even = write complete)
    /// ```
    pub fn update(&mut self, cpu: u16, mem: u16, pps_rx: u32, pps_tx: u32, uptime: u64, flags: u32) {
        unsafe {
            // Step 1: Increment seq to ODD (signals "write in progress")
            let old_seq = read_volatile(&self.frame.seq as *const u32);
            let write_seq = old_seq.wrapping_add(1);
            write_volatile(&mut self.frame.seq as *mut u32, write_seq);

            // Step 2: WRITE MEMORY BARRIER (smp_wmb)
            // Ensures seq increment is globally visible BEFORE payload writes
            fence(Ordering::Release);

            // Step 3: Write all data fields using volatile writes
            // This prevents compiler from reordering or caching these stores
            write_volatile(&mut self.frame.magic as *mut u32, BIO_MAGIC);
            write_volatile(&mut self.frame.cpu_pressure as *mut u16, cpu);
            write_volatile(&mut self.frame.mem_pressure as *mut u16, mem);
            write_volatile(&mut self.frame.pps_rx as *mut u32, pps_rx);
            write_volatile(&mut self.frame.pps_tx as *mut u32, pps_tx);
            write_volatile(&mut self.frame.sys_uptime as *mut u64, uptime);
            write_volatile(&mut self.frame.flags as *mut u32, flags);

            // Step 4: WRITE MEMORY BARRIER (smp_wmb)
            // Ensures ALL payload writes complete BEFORE seq increment
            fence(Ordering::Release);

            // Step 5: Increment seq to EVEN (signals "write complete")
            let done_seq = write_seq.wrapping_add(1);
            write_volatile(&mut self.frame.seq as *mut u32, done_seq);
        }
    }

    /// Read telemetry with SeqLock tearing prevention (Reader Side)
    ///
    /// Returns a consistent copy of the BioFrame, retrying if a write
    /// was in progress during the read.
    ///
    /// ## SeqLock Reader Protocol
    /// ```text
    /// do {
    ///     1. snapshot = seq
    ///     2. smp_rmb() - read barrier
    ///     3. optimistic read of payload
    ///     4. smp_rmb() - read barrier
    /// } while (snapshot is ODD || snapshot != seq)
    /// ```
    ///
    /// # Safety
    /// Caller must ensure the SharedTelemetry is valid and not being deallocated.
    pub unsafe fn read_safe(&self) -> BioFrame {
        let mut result: BioFrame;
        let mut seq_snapshot: u32;

        loop {
            // Step 1: Snapshot the sequence counter
            seq_snapshot = read_volatile(&self.frame.seq as *const u32);

            // If seq is ODD, a write is in progress - spin wait
            if seq_snapshot & 1 != 0 {
                core::hint::spin_loop();
                continue;
            }

            // Step 2: READ MEMORY BARRIER (smp_rmb)
            // Ensures we read seq BEFORE we read the payload
            fence(Ordering::Acquire);

            // Step 3: Optimistic read of all fields
            result = BioFrame {
                seq: seq_snapshot,
                magic: read_volatile(&self.frame.magic as *const u32),
                cpu_pressure: read_volatile(&self.frame.cpu_pressure as *const u16),
                mem_pressure: read_volatile(&self.frame.mem_pressure as *const u16),
                pps_rx: read_volatile(&self.frame.pps_rx as *const u32),
                pps_tx: read_volatile(&self.frame.pps_tx as *const u32),
                sys_uptime: read_volatile(&self.frame.sys_uptime as *const u64),
                flags: read_volatile(&self.frame.flags as *const u32),
            };

            // Step 4: READ MEMORY BARRIER (smp_rmb)
            // Ensures all payload reads complete BEFORE we re-check seq
            fence(Ordering::Acquire);

            // Step 5: Validation - check if seq changed during read
            let seq_final = read_volatile(&self.frame.seq as *const u32);
            if seq_snapshot == seq_final {
                // Success! Data is consistent
                break;
            }

            // Seq changed during read - data is torn, retry
            core::hint::spin_loop();
        }

        result
    }

    /// Prepare WebSocket binary frame header in headroom
    /// Format: [0x82, length] for binary frame <= 125 bytes
    pub fn prepare_ws_header(&mut self) {
        self.headroom[0] = 0x82; // Binary frame, FIN bit set
        self.headroom[1] = BioFrame::SIZE as u8; // Payload length
        self.headroom[2] = 0;
        self.headroom[3] = 0;
    }
}

/// Global shared telemetry bridge
/// This is the kernel's side of the zero-copy bridge to userspace
pub static mut NEON_BRIDGE: SharedTelemetry = SharedTelemetry::new();

// ============================================================================
// Telemetry Statistics Collector
// ============================================================================

use core::sync::atomic::AtomicU64;

/// Kernel-side telemetry collector
pub struct TelemetryCollector {
    /// Tick counter (incremented each scheduler loop)
    pub tick: AtomicU64,
    /// RX packet counter (current window)
    pub rx_packets: AtomicU64,
    /// TX packet counter (current window)
    pub tx_packets: AtomicU64,
    /// Last tick when PPS was calculated
    last_pps_tick: AtomicU64,
    /// Calculated RX PPS
    pub pps_rx: AtomicU64,
    /// Calculated TX PPS
    pub pps_tx: AtomicU64,
}

impl TelemetryCollector {
    pub const fn new() -> Self {
        Self {
            tick: AtomicU64::new(0),
            rx_packets: AtomicU64::new(0),
            tx_packets: AtomicU64::new(0),
            last_pps_tick: AtomicU64::new(0),
            pps_rx: AtomicU64::new(0),
            pps_tx: AtomicU64::new(0),
        }
    }

    /// Increment tick counter
    pub fn tick(&self) {
        self.tick.fetch_add(1, Ordering::Relaxed);
    }

    /// Record received packet
    pub fn record_rx(&self) {
        self.rx_packets.fetch_add(1, Ordering::Relaxed);
    }

    /// Record transmitted packet
    pub fn record_tx(&self) {
        self.tx_packets.fetch_add(1, Ordering::Relaxed);
    }

    /// Calculate PPS and update bridge (call every ~1 second worth of ticks)
    pub fn update_pps(&self, ticks_per_second: u64) {
        let current_tick = self.tick.load(Ordering::Relaxed);
        let last_tick = self.last_pps_tick.load(Ordering::Relaxed);

        if current_tick.saturating_sub(last_tick) >= ticks_per_second {
            // Calculate PPS
            let rx = self.rx_packets.swap(0, Ordering::Relaxed);
            let tx = self.tx_packets.swap(0, Ordering::Relaxed);

            self.pps_rx.store(rx, Ordering::Relaxed);
            self.pps_tx.store(tx, Ordering::Relaxed);
            self.last_pps_tick.store(current_tick, Ordering::Relaxed);
        }
    }

    /// Push current state to the NEON_BRIDGE
    ///
    /// # Safety
    /// Must not be called concurrently from multiple contexts
    pub unsafe fn push_to_bridge(&self, cpu_pressure: u16, mem_pressure: u16, flags: u32) {
        let uptime = self.tick.load(Ordering::Relaxed);
        let pps_rx = self.pps_rx.load(Ordering::Relaxed) as u32;
        let pps_tx = self.pps_tx.load(Ordering::Relaxed) as u32;

        NEON_BRIDGE.update(cpu_pressure, mem_pressure, pps_rx, pps_tx, uptime, flags);
    }
}

/// Global telemetry collector instance
pub static TELEMETRY: TelemetryCollector = TelemetryCollector::new();

// ============================================================================
// BIO-C/1.0 Zero-Copy Command Bridge (Upstream: UI → Kernel)
// ============================================================================

/// Magic sync word for BIO-COMMAND protocol
pub const BIOC_MAGIC: u16 = 0xB10C;

/// Command ID: Entropy flux (RNG harvest rate)
pub const CMD_ENTROPY_FLUX: u8 = 0x01;

/// Command ID: Network choke (RX queue limit)
pub const CMD_NET_CHOKE: u8 = 0x02;

/// Command ID: Log verbosity level (0-4)
pub const CMD_VERBOSITY: u8 = 0x03;

/// Command ID: Memory page poisoning (ACID test)
pub const CMD_MEM_ACID: u8 = 0x04;

/// Command flags
pub const CMDF_ARMED: u8 = 0x01;  // Deadman switch is armed

/// BIO-C/1.0 Command Frame (16 bytes, aligned)
///
/// Wire format for upstream commands from UI to kernel.
/// CRC32 protects against corruption on the wire.
///
/// ```text
///  0                   1                   2                   3
///  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
/// +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
/// |      MAGIC (0xB10C)           |     SEQ_ID (Rolling u16)      |
/// +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
/// |    CMD_ID     |     FLAGS     |          PADDING (0x00)       |
/// +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
/// |                       PAYLOAD (Float32)                       |
/// +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
/// |                       CRC32 (Checksum)                        |
/// +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
/// ```
#[repr(C, align(16))]
#[derive(Clone, Copy, Debug)]
pub struct BioCommand {
    /// Protocol magic (0xB10C)
    pub magic: u16,
    /// Rolling sequence ID for replay detection
    pub seq_id: u16,
    /// Command ID (0x01-0x04)
    pub cmd_id: u8,
    /// Command flags (bit 0: ARMED for deadman switches)
    pub flags: u8,
    /// Padding for alignment
    pub _pad: [u8; 2],
    /// Payload value (0.0 - 1.0 normalized)
    pub payload: f32,
    /// CRC32 checksum of bytes 0-11
    pub crc32: u32,
}

impl BioCommand {
    /// Frame size in bytes
    pub const SIZE: usize = 16;

    /// Parse a raw buffer into a BioCommand
    ///
    /// Returns `None` if magic is wrong, CRC fails, or buffer too small.
    pub fn from_bytes(buf: &[u8]) -> Option<Self> {
        if buf.len() < Self::SIZE {
            return None;
        }

        // Parse fields (Little Endian)
        let magic = u16::from_le_bytes([buf[0], buf[1]]);
        if magic != BIOC_MAGIC {
            return None;
        }

        let seq_id = u16::from_le_bytes([buf[2], buf[3]]);
        let cmd_id = buf[4];
        let flags = buf[5];
        let payload = f32::from_le_bytes([buf[8], buf[9], buf[10], buf[11]]);
        let crc_received = u32::from_le_bytes([buf[12], buf[13], buf[14], buf[15]]);

        // Validate CRC32 over bytes 0-11
        let crc_computed = crc32_ieee(&buf[0..12]);
        if crc_computed != crc_received {
            return None;
        }

        Some(Self {
            magic,
            seq_id,
            cmd_id,
            flags,
            _pad: [0; 2],
            payload,
            crc32: crc_received,
        })
    }

    /// Check if ARMED flag is set (for deadman switches)
    pub fn is_armed(&self) -> bool {
        self.flags & CMDF_ARMED != 0
    }
}

/// CRC32 (IEEE 802.3 polynomial) calculation
///
/// Uses the standard Ethernet polynomial: 0xEDB88320 (reflected form)
fn crc32_ieee(data: &[u8]) -> u32 {
    const POLY: u32 = 0xEDB88320;
    let mut crc: u32 = 0xFFFFFFFF;

    for &byte in data {
        crc ^= byte as u32;
        for _ in 0..8 {
            if crc & 1 != 0 {
                crc = (crc >> 1) ^ POLY;
            } else {
                crc >>= 1;
            }
        }
    }

    crc ^ 0xFFFFFFFF
}

// ============================================================================
// Command Dispatcher
// ============================================================================

/// Result of command dispatch
#[derive(Debug, Clone, Copy)]
pub enum CommandResult {
    /// Command accepted and applied
    Accepted,
    /// Command rejected (invalid value or safety check failed)
    Rejected(&'static str),
    /// Command requires ARMED flag but it wasn't set
    NotArmed,
    /// Unknown command ID
    UnknownCommand,
}

/// Current kernel parameter state (controlled by tactile deck)
pub struct KernelOverrides {
    /// Entropy harvest rate multiplier (0.0 - 1.0)
    pub entropy_flux: f32,
    /// Network RX throttle (0.0 = no limit, 1.0 = max choke)
    pub net_choke: f32,
    /// Log verbosity level (0-4)
    pub verbosity: u8,
    /// Memory page poisoning level (0.0 - 1.0, requires ARMED)
    pub mem_acid: f32,
    /// Last received sequence ID (for replay detection)
    last_seq: u16,
}

impl KernelOverrides {
    /// Create with safe defaults
    pub const fn new() -> Self {
        Self {
            entropy_flux: 0.5,  // Medium harvest rate
            net_choke: 0.0,    // No throttling
            verbosity: 2,      // Default log level
            mem_acid: 0.0,     // No poisoning
            last_seq: 0,
        }
    }

    /// Process a received BioCommand
    ///
    /// Returns the result of dispatch (accepted/rejected/etc).
    pub fn dispatch(&mut self, cmd: &BioCommand) -> CommandResult {
        // Replay detection: reject if seq_id is not newer
        // Handle wraparound with signed comparison trick
        let seq_diff = cmd.seq_id.wrapping_sub(self.last_seq) as i16;
        if seq_diff <= 0 && self.last_seq != 0 {
            return CommandResult::Rejected("Stale sequence");
        }
        self.last_seq = cmd.seq_id;

        // Clamp payload to 0.0 - 1.0
        let value = cmd.payload.clamp(0.0, 1.0);

        match cmd.cmd_id {
            CMD_ENTROPY_FLUX => {
                // Entropy flux: direct mapping
                self.entropy_flux = value;
                CommandResult::Accepted
            }

            CMD_NET_CHOKE => {
                // Network choke: direct mapping
                self.net_choke = value;
                CommandResult::Accepted
            }

            CMD_VERBOSITY => {
                // Verbosity: map 0.0-1.0 to discrete 0-4
                // (no_std: manual round via floor + 0.5)
                self.verbosity = (value * 4.0 + 0.5) as u8;
                CommandResult::Accepted
            }

            CMD_MEM_ACID => {
                // Memory acid: REQUIRES ARMED flag (deadman switch)
                if !cmd.is_armed() {
                    // Not armed = spring return to safe
                    self.mem_acid = 0.0;
                    return CommandResult::NotArmed;
                }
                // Armed: allow poisoning
                self.mem_acid = value;
                CommandResult::Accepted
            }

            _ => CommandResult::UnknownCommand,
        }
    }

    /// Get entropy harvest rate as percentage
    pub fn entropy_percent(&self) -> u8 {
        (self.entropy_flux * 100.0) as u8
    }

    /// Get net choke as queue limit (0 = no limit)
    pub fn net_queue_limit(&self) -> u16 {
        if self.net_choke < 0.01 {
            0  // No throttle
        } else {
            // Map 0.01-1.0 to 256-1 (inverse: more choke = smaller queue)
            // (no_std: manual round via floor + 0.5)
            let limit = 256.0 * (1.0 - self.net_choke) + 0.5;
            (limit as u16).max(1)
        }
    }
}

/// Global kernel overrides instance
pub static mut KERNEL_OVERRIDES: KernelOverrides = KernelOverrides::new();
