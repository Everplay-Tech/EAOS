//! # Ea Cardio - The Heartbeat Organ
//!
//! A third-party EAOS Organ demonstrating ecosystem extensibility.
//! Cardio tracks system heartbeat, uptime, and vital statistics.
//!
//! ## Architecture
//!
//! This crate proves that external developers can create Organs that:
//! 1. Implement `SovereignDocument` trait from Symbiote
//! 2. Store data via Symbiote's `commit_organ_data()` without kernel changes
//! 3. Participate in the Braid ecosystem with 0xB8AD compliance
//!
//! ## Example
//!
//! ```rust
//! use ea_cardio::{Heartbeat, CardioMonitor};
//! use ea_symbiote::{Symbiote, SovereignDocument};
//!
//! let mut monitor = CardioMonitor::new();
//! monitor.tick(); // Advance heartbeat
//!
//! // Create heartbeat record
//! let heartbeat = monitor.snapshot();
//!
//! // Store via Symbiote (SovereignDocument is auto-implemented)
//! let mut synapse = Symbiote::new();
//! let blob = heartbeat.to_blob();
//! let addr = synapse.commit_organ_data(blob).expect("commit failed");
//! ```

#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;

use alloc::vec::Vec;
use ea_symbiote::{BlobType, SovereignDocument};

// =============================================================================
// Heartbeat - The Pulse of EAOS
// =============================================================================

/// A single heartbeat snapshot capturing system vital signs.
///
/// Each heartbeat contains:
/// - `tick`: Monotonic counter (increments per cycle)
/// - `uptime_ms`: System uptime in milliseconds
/// - `pulse_rate`: Current heartbeat rate (beats per minute)
/// - `status`: System health status code
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Heartbeat {
    /// Monotonic tick counter
    pub tick: u64,
    /// System uptime in milliseconds
    pub uptime_ms: u64,
    /// Current pulse rate (beats per minute)
    pub pulse_rate: u16,
    /// System status code (0 = healthy, >0 = anomaly codes)
    pub status: u16,
}

impl Default for Heartbeat {
    fn default() -> Self {
        Self::new()
    }
}

impl Heartbeat {
    /// Create a new heartbeat at tick 0.
    pub const fn new() -> Self {
        Self {
            tick: 0,
            uptime_ms: 0,
            pulse_rate: 60, // Default: 60 BPM
            status: 0,      // Healthy
        }
    }

    /// Create a heartbeat with specific values.
    pub const fn with_values(tick: u64, uptime_ms: u64, pulse_rate: u16, status: u16) -> Self {
        Self {
            tick,
            uptime_ms,
            pulse_rate,
            status,
        }
    }

    /// Check if system is healthy (status == 0).
    pub const fn is_healthy(&self) -> bool {
        self.status == 0
    }

    /// Check if system is in anomaly state.
    pub const fn has_anomaly(&self) -> bool {
        self.status != 0
    }
}

/// Implement SovereignDocument for Heartbeat.
///
/// This is the CRUCIAL demonstration: external types can implement
/// the trait and be stored via Symbiote without any kernel modifications.
impl SovereignDocument for Heartbeat {
    fn blob_type(&self) -> BlobType {
        // Use Record type for structured data
        BlobType::Record
    }

    fn to_bytes(&self) -> Vec<u8> {
        // Serialize: tick(8) + uptime_ms(8) + pulse_rate(2) + status(2) = 20 bytes
        let mut buf = Vec::with_capacity(20);
        buf.extend_from_slice(&self.tick.to_le_bytes());
        buf.extend_from_slice(&self.uptime_ms.to_le_bytes());
        buf.extend_from_slice(&self.pulse_rate.to_le_bytes());
        buf.extend_from_slice(&self.status.to_le_bytes());
        buf
    }

    fn from_bytes(data: &[u8]) -> Option<Self>
    where
        Self: Sized,
    {
        if data.len() < 20 {
            return None;
        }

        let tick = u64::from_le_bytes(data[0..8].try_into().ok()?);
        let uptime_ms = u64::from_le_bytes(data[8..16].try_into().ok()?);
        let pulse_rate = u16::from_le_bytes(data[16..18].try_into().ok()?);
        let status = u16::from_le_bytes(data[18..20].try_into().ok()?);

        Some(Self {
            tick,
            uptime_ms,
            pulse_rate,
            status,
        })
    }
}

// =============================================================================
// CardioMonitor - The Heart Rate Monitor
// =============================================================================

/// System health status codes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u16)]
pub enum StatusCode {
    /// System is healthy
    Healthy = 0,
    /// High CPU usage warning
    HighCpu = 1,
    /// Low memory warning
    LowMemory = 2,
    /// Storage pressure warning
    StoragePressure = 3,
    /// Thermal warning
    ThermalWarning = 4,
    /// Critical: System unstable
    Critical = 255,
}

/// CardioMonitor tracks system heartbeat over time.
///
/// Use this struct to maintain system uptime and generate heartbeat snapshots.
#[derive(Clone, Debug)]
pub struct CardioMonitor {
    /// Current tick counter
    tick: u64,
    /// Current uptime in milliseconds
    uptime_ms: u64,
    /// Current pulse rate
    pulse_rate: u16,
    /// Current status
    status: u16,
    /// Tick interval in milliseconds (default: 1000ms = 1 second)
    tick_interval_ms: u64,
}

impl Default for CardioMonitor {
    fn default() -> Self {
        Self::new()
    }
}

impl CardioMonitor {
    /// Create a new CardioMonitor with default settings (1 second tick).
    pub const fn new() -> Self {
        Self {
            tick: 0,
            uptime_ms: 0,
            pulse_rate: 60,
            status: 0,
            tick_interval_ms: 1000,
        }
    }

    /// Create a monitor with custom tick interval.
    pub const fn with_interval(tick_interval_ms: u64) -> Self {
        Self {
            tick: 0,
            uptime_ms: 0,
            pulse_rate: 60,
            status: 0,
            tick_interval_ms,
        }
    }

    /// Advance the heartbeat by one tick.
    pub fn tick(&mut self) {
        self.tick += 1;
        self.uptime_ms += self.tick_interval_ms;
    }

    /// Advance the heartbeat by N ticks.
    pub fn tick_n(&mut self, n: u64) {
        self.tick += n;
        self.uptime_ms += n * self.tick_interval_ms;
    }

    /// Set the current status code.
    pub fn set_status(&mut self, status: StatusCode) {
        self.status = status as u16;
    }

    /// Set a raw status code.
    pub fn set_status_raw(&mut self, status: u16) {
        self.status = status;
    }

    /// Update pulse rate based on system activity.
    pub fn set_pulse_rate(&mut self, rate: u16) {
        self.pulse_rate = rate;
    }

    /// Get current tick count.
    pub const fn current_tick(&self) -> u64 {
        self.tick
    }

    /// Get current uptime in milliseconds.
    pub const fn uptime_ms(&self) -> u64 {
        self.uptime_ms
    }

    /// Get current uptime in seconds.
    pub const fn uptime_secs(&self) -> u64 {
        self.uptime_ms / 1000
    }

    /// Get current uptime formatted as (hours, minutes, seconds).
    pub const fn uptime_hms(&self) -> (u64, u64, u64) {
        let total_secs = self.uptime_secs();
        let hours = total_secs / 3600;
        let minutes = (total_secs % 3600) / 60;
        let seconds = total_secs % 60;
        (hours, minutes, seconds)
    }

    /// Create a heartbeat snapshot of current state.
    pub const fn snapshot(&self) -> Heartbeat {
        Heartbeat {
            tick: self.tick,
            uptime_ms: self.uptime_ms,
            pulse_rate: self.pulse_rate,
            status: self.status,
        }
    }

    /// Check if system is healthy.
    pub const fn is_healthy(&self) -> bool {
        self.status == 0
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use ea_symbiote::Symbiote;

    #[test]
    fn test_heartbeat_creation() {
        let hb = Heartbeat::new();
        assert_eq!(hb.tick, 0);
        assert_eq!(hb.uptime_ms, 0);
        assert_eq!(hb.pulse_rate, 60);
        assert_eq!(hb.status, 0);
        assert!(hb.is_healthy());
    }

    #[test]
    fn test_heartbeat_serialization_roundtrip() {
        let original = Heartbeat::with_values(42, 123456, 72, 0);

        // Serialize
        let bytes = original.to_bytes();
        assert_eq!(bytes.len(), 20);

        // Deserialize
        let recovered = Heartbeat::from_bytes(&bytes).unwrap();
        assert_eq!(recovered, original);
    }

    #[test]
    fn test_heartbeat_to_blob() {
        let hb = Heartbeat::with_values(100, 60000, 80, 0);

        // Convert to SovereignBlob using trait
        let blob = hb.to_blob();

        assert_eq!(blob.blob_type, BlobType::Record);
        assert!(blob.is_governance_compliant());
        assert_eq!(blob.payload.len(), 20);
    }

    #[test]
    fn test_heartbeat_symbiote_commit() {
        // This proves external Organs can commit data through Symbiote
        let mut synapse = Symbiote::new();
        let hb = Heartbeat::with_values(1000, 3600000, 65, 0);

        // Convert to blob and commit
        let blob = hb.to_blob();
        let result = synapse.commit_organ_data(blob);

        assert!(result.is_ok());
        let addr = result.unwrap();
        assert!(!addr.is_null());
    }

    #[test]
    fn test_cardio_monitor() {
        let mut monitor = CardioMonitor::new();

        // Advance time
        monitor.tick();
        monitor.tick();
        monitor.tick();

        assert_eq!(monitor.current_tick(), 3);
        assert_eq!(monitor.uptime_ms(), 3000);
        assert_eq!(monitor.uptime_secs(), 3);

        // Take snapshot
        let snapshot = monitor.snapshot();
        assert_eq!(snapshot.tick, 3);
        assert_eq!(snapshot.uptime_ms, 3000);
    }

    #[test]
    fn test_cardio_monitor_status() {
        let mut monitor = CardioMonitor::new();

        assert!(monitor.is_healthy());

        monitor.set_status(StatusCode::HighCpu);
        assert!(!monitor.is_healthy());

        let snapshot = monitor.snapshot();
        assert!(snapshot.has_anomaly());
        assert_eq!(snapshot.status, 1);
    }

    #[test]
    fn test_uptime_formatting() {
        let mut monitor = CardioMonitor::new();

        // Simulate 1 hour, 30 minutes, 45 seconds
        let total_ms = (1 * 3600 + 30 * 60 + 45) * 1000;
        let ticks = total_ms / 1000; // 1 second per tick
        monitor.tick_n(ticks);

        let (h, m, s) = monitor.uptime_hms();
        assert_eq!(h, 1);
        assert_eq!(m, 30);
        assert_eq!(s, 45);
    }

    #[test]
    fn test_ecosystem_expansion() {
        // STAGE 11.5 PROOF: External Organ creates SovereignDocument
        // without ANY modifications to Symbiote code!

        // 1. Third-party Heartbeat type
        let heartbeat = Heartbeat::with_values(9999, 86400000, 70, 0);

        // 2. Implements SovereignDocument trait
        let blob = heartbeat.to_blob();
        assert!(blob.is_governance_compliant());
        assert_eq!(blob.blob_type, BlobType::Record);

        // 3. Commits through Symbiote unchanged
        let mut synapse = Symbiote::new();
        let result = synapse.commit_organ_data(blob);

        // 4. SUCCESS: No Symbiote modifications needed!
        assert!(result.is_ok());

        println!("ECOSYSTEM EXPANSION: VERIFIED");
        println!("  External Organ: ea-cardio");
        println!("  Document Type: Heartbeat");
        println!("  Symbiote Version: Unchanged");
        println!("  Braid Compliant: YES");
    }
}
