//! Interrupt Handling for Virtio Devices
//!
//! This module provides ISR (Interrupt Service Routine) handling for Virtio
//! devices to prevent "scream loops" where interrupts keep firing because
//! they're not properly acknowledged.
//!
//! ## ISR Status Register
//!
//! The Virtio ISR status register must be read to:
//! 1. Determine what caused the interrupt (queue update or config change)
//! 2. Acknowledge and clear the interrupt (reading clears it)
//!
//! ## Interrupt Types
//!
//! - Bit 0: Queue interrupt (data available)
//! - Bit 1: Device configuration change

use core::ptr::read_volatile;
use core::sync::atomic::{AtomicBool, AtomicU64, Ordering};

// ============================================================================
// ISR Status Bits
// ============================================================================

/// Queue notification interrupt (data available)
pub const ISR_QUEUE: u8 = 0x01;

/// Device configuration change interrupt
pub const ISR_CONFIG: u8 = 0x02;

// ============================================================================
// Interrupt Statistics
// ============================================================================

/// Global interrupt statistics for debugging
pub struct InterruptStats {
    /// Total interrupts received
    pub total: AtomicU64,
    /// Queue interrupts
    pub queue: AtomicU64,
    /// Config change interrupts
    pub config: AtomicU64,
    /// Spurious interrupts (ISR was 0)
    pub spurious: AtomicU64,
}

impl InterruptStats {
    pub const fn new() -> Self {
        Self {
            total: AtomicU64::new(0),
            queue: AtomicU64::new(0),
            config: AtomicU64::new(0),
            spurious: AtomicU64::new(0),
        }
    }

    pub fn record_queue(&self) {
        self.total.fetch_add(1, Ordering::Relaxed);
        self.queue.fetch_add(1, Ordering::Relaxed);
    }

    pub fn record_config(&self) {
        self.total.fetch_add(1, Ordering::Relaxed);
        self.config.fetch_add(1, Ordering::Relaxed);
    }

    pub fn record_spurious(&self) {
        self.total.fetch_add(1, Ordering::Relaxed);
        self.spurious.fetch_add(1, Ordering::Relaxed);
    }
}

/// Global stats instance
pub static INTERRUPT_STATS: InterruptStats = InterruptStats::new();

// ============================================================================
// ISR Handler
// ============================================================================

/// Result of reading the ISR status
#[derive(Debug, Clone, Copy)]
pub struct IsrResult {
    /// Raw ISR value (reading clears the interrupt)
    pub raw: u8,
    /// Queue interrupt was pending
    pub queue_interrupt: bool,
    /// Config change interrupt was pending
    pub config_interrupt: bool,
}

impl IsrResult {
    /// Check if any interrupt was pending
    pub fn any_pending(&self) -> bool {
        self.raw != 0
    }
}

/// Read and acknowledge the ISR status register
///
/// # Important
/// Reading the ISR register clears the interrupt. This MUST be done
/// in the interrupt handler to prevent "scream loops".
///
/// # Safety
/// `isr_addr` must point to a valid MMIO ISR status register.
#[inline]
pub unsafe fn read_isr(isr_addr: usize) -> IsrResult {
    // Volatile read clears the interrupt
    let raw = read_volatile(isr_addr as *const u8);

    let queue_interrupt = (raw & ISR_QUEUE) != 0;
    let config_interrupt = (raw & ISR_CONFIG) != 0;

    // Update stats
    if queue_interrupt {
        INTERRUPT_STATS.record_queue();
    }
    if config_interrupt {
        INTERRUPT_STATS.record_config();
    }
    if raw == 0 {
        INTERRUPT_STATS.record_spurious();
    }

    IsrResult {
        raw,
        queue_interrupt,
        config_interrupt,
    }
}

// ============================================================================
// Interrupt State Machine
// ============================================================================

/// Tracks pending work from interrupts
pub struct InterruptPending {
    /// RX queue has data
    pub rx_ready: AtomicBool,
    /// TX queue has completed
    pub tx_ready: AtomicBool,
    /// Device config changed
    pub config_changed: AtomicBool,
}

impl InterruptPending {
    pub const fn new() -> Self {
        Self {
            rx_ready: AtomicBool::new(false),
            tx_ready: AtomicBool::new(false),
            config_changed: AtomicBool::new(false),
        }
    }

    /// Signal that RX data is ready
    pub fn signal_rx(&self) {
        self.rx_ready.store(true, Ordering::Release);
    }

    /// Signal that TX completed
    pub fn signal_tx(&self) {
        self.tx_ready.store(true, Ordering::Release);
    }

    /// Signal config change
    pub fn signal_config(&self) {
        self.config_changed.store(true, Ordering::Release);
    }

    /// Check and clear RX ready flag
    pub fn take_rx(&self) -> bool {
        self.rx_ready.swap(false, Ordering::AcqRel)
    }

    /// Check and clear TX ready flag
    pub fn take_tx(&self) -> bool {
        self.tx_ready.swap(false, Ordering::AcqRel)
    }

    /// Check and clear config change flag
    pub fn take_config(&self) -> bool {
        self.config_changed.swap(false, Ordering::AcqRel)
    }
}

/// Global pending interrupt work
pub static INTERRUPT_PENDING: InterruptPending = InterruptPending::new();

// ============================================================================
// Virtio-Net Interrupt Handler
// ============================================================================

/// Handle a Virtio-Net interrupt
///
/// This should be called from the actual interrupt handler (or polled).
/// It reads and acknowledges the ISR, then sets appropriate pending flags.
///
/// # Safety
/// `isr_addr` must point to a valid Virtio ISR status MMIO register.
pub unsafe fn handle_virtio_interrupt(isr_addr: usize) -> IsrResult {
    let result = read_isr(isr_addr);

    if result.queue_interrupt {
        // In a real implementation, we'd check which queue
        // For now, assume RX (most common case)
        INTERRUPT_PENDING.signal_rx();
    }

    if result.config_interrupt {
        INTERRUPT_PENDING.signal_config();
    }

    result
}

// ============================================================================
// Polling Interface (for UEFI without real interrupts)
// ============================================================================

/// Poll for interrupt status without blocking
///
/// In UEFI, we typically don't have real interrupts set up,
/// so we poll the ISR register instead.
///
/// # Safety
/// `isr_addr` must point to a valid Virtio ISR status MMIO register.
pub unsafe fn poll_interrupt(isr_addr: usize) -> Option<IsrResult> {
    let result = read_isr(isr_addr);
    if result.any_pending() {
        Some(result)
    } else {
        None
    }
}
