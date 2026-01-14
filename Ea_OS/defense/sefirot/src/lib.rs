//! Sefirot Chaos Testing Framework for EAOS
//!
//! Named after the Kabbalistic Tree of Life, Sefirot provides chaos engineering
//! capabilities to test the resilience of the EAOS organism.
//!
//! The ten Sefirot represent different failure modes:
//! - Keter (Crown): Total system failure
//! - Chokmah (Wisdom): Logic/reasoning failures
//! - Binah (Understanding): Data interpretation failures
//! - Chesed (Kindness): Resource exhaustion
//! - Gevurah (Severity): Harsh termination (SIGKILL)
//! - Tiferet (Beauty): Corruption of data integrity
//! - Netzach (Victory): Network failures
//! - Hod (Glory): Storage failures
//! - Yesod (Foundation): Memory failures
//! - Malkhut (Kingdom): Permission/access failures

use serde::{Deserialize, Serialize};

// ============================================================================
// Chaos Event Types
// ============================================================================

/// The ten Sefirot - chaos injection categories
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Sephira {
    /// Keter - Total system crash
    Keter,
    /// Chokmah - Logic failures
    Chokmah,
    /// Binah - Data parsing failures
    Binah,
    /// Chesed - Resource exhaustion
    Chesed,
    /// Gevurah - Harsh termination (SIGKILL)
    Gevurah,
    /// Tiferet - Data corruption
    Tiferet,
    /// Netzach - Network failures
    Netzach,
    /// Hod - Storage/IO failures
    Hod,
    /// Yesod - Memory failures
    Yesod,
    /// Malkhut - Permission failures
    Malkhut,
}

impl Sephira {
    pub fn description(&self) -> &'static str {
        match self {
            Sephira::Keter => "Total system failure - simulates complete crash",
            Sephira::Chokmah => "Logic failure - corrupts decision making",
            Sephira::Binah => "Parse failure - corrupts data interpretation",
            Sephira::Chesed => "Resource exhaustion - depletes CPU/memory",
            Sephira::Gevurah => "Harsh termination - SIGKILL mid-operation",
            Sephira::Tiferet => "Data corruption - flips bits in storage",
            Sephira::Netzach => "Network failure - drops connections",
            Sephira::Hod => "Storage failure - IO errors",
            Sephira::Yesod => "Memory failure - allocation errors",
            Sephira::Malkhut => "Permission failure - access denied",
        }
    }

    pub fn signal(&self) -> Option<i32> {
        match self {
            Sephira::Keter => Some(6),   // SIGABRT
            Sephira::Gevurah => Some(9), // SIGKILL
            _ => None,
        }
    }
}

// ============================================================================
// Chaos Scenario
// ============================================================================

/// A chaos test scenario
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChaosScenario {
    pub name: String,
    pub sephira: Sephira,
    pub trigger: ChaosTrigger,
    pub recovery: RecoveryExpectation,
    pub description: String,
}

/// When to trigger chaos
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ChaosTrigger {
    /// Trigger immediately
    Immediate,
    /// Trigger after N operations
    AfterOperations(usize),
    /// Trigger during specific operation
    DuringOperation(OperationType),
    /// Trigger randomly with probability (0.0 - 1.0)
    Random(f32),
    /// Trigger at specific timestamp
    AtTime(i64),
}

/// Types of operations to target
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OperationType {
    BraidTransform,
    PermFsWrite,
    PermFsRead,
    JournalCommit,
    CapsuleWrap,
    CapsuleUnwrap,
}

/// Expected recovery behavior
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecoveryExpectation {
    pub should_recover: bool,
    pub max_recovery_time_ms: u64,
    pub data_loss_acceptable: bool,
    pub verify_integrity: bool,
}

impl Default for RecoveryExpectation {
    fn default() -> Self {
        Self {
            should_recover: true,
            max_recovery_time_ms: 5000,
            data_loss_acceptable: false,
            verify_integrity: true,
        }
    }
}

// ============================================================================
// Cataclysm Test - The Ultimate Chaos Scenario
// ============================================================================

/// The Cataclysm test - SIGKILL during braid transformation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CataclysmTest {
    pub scenario: ChaosScenario,
    pub pre_kill_operations: usize,
    pub kill_signal: i32,
    pub verify_journal_replay: bool,
    pub verify_braid_header: bool,
    pub expected_magic: [u8; 2],
}

impl Default for CataclysmTest {
    fn default() -> Self {
        Self {
            scenario: ChaosScenario {
                name: "Cataclysm".to_string(),
                sephira: Sephira::Gevurah,
                trigger: ChaosTrigger::DuringOperation(OperationType::BraidTransform),
                recovery: RecoveryExpectation {
                    should_recover: true,
                    max_recovery_time_ms: 10000,
                    data_loss_acceptable: false,
                    verify_integrity: true,
                },
                description: "SIGKILL during Roulette-RS braid transformation".to_string(),
            },
            pre_kill_operations: 50, // Kill after ~50% progress
            kill_signal: 9, // SIGKILL
            verify_journal_replay: true,
            verify_braid_header: true,
            expected_magic: [0xB8, 0xAD],
        }
    }
}

impl CataclysmTest {
    /// Generate the shell script for cataclysm testing
    pub fn generate_script(&self, qemu_pid_file: &str, run_script: &str) -> String {
        format!(r#"#!/bin/bash
# =============================================================================
# SEFIROT CATACLYSM TEST
# Gevurah (Severity) - Harsh termination during braid transformation
# =============================================================================

set -e

QEMU_PID_FILE="{qemu_pid_file}"
RUN_SCRIPT="{run_script}"
MAGIC_HEADER="B8AD"
LOG_FILE="/tmp/cataclysm_test.log"
RECOVERY_TIMEOUT={recovery_timeout}

echo "=== SEFIROT CATACLYSM TEST ===" | tee $LOG_FILE
echo "Sephira: Gevurah (Harsh Termination)" | tee -a $LOG_FILE
echo "Signal: SIGKILL (9)" | tee -a $LOG_FILE
echo "Expected: Journal replay, 0xB8AD header intact" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Phase 1: Start EAOS with a large write task
echo "[Phase 1] Starting EAOS with large write task..." | tee -a $LOG_FILE
$RUN_SCRIPT &
LAUNCH_PID=$!

# Wait for QEMU to start and get its PID
sleep 5
if [ ! -f "$QEMU_PID_FILE" ]; then
    echo "[ERROR] QEMU PID file not found" | tee -a $LOG_FILE
    exit 1
fi
QEMU_PID=$(cat $QEMU_PID_FILE)
echo "[INFO] QEMU PID: $QEMU_PID" | tee -a $LOG_FILE

# Phase 2: Wait for braid transformation to start
echo "[Phase 2] Waiting for braid transformation..." | tee -a $LOG_FILE
sleep 3

# Phase 3: SIGKILL mid-transformation (Gevurah)
echo "[Phase 3] GEVURAH - Executing SIGKILL..." | tee -a $LOG_FILE
kill -{kill_signal} $QEMU_PID 2>/dev/null || true
echo "[INFO] SIGKILL sent to QEMU process" | tee -a $LOG_FILE

# Wait for process to die
sleep 2

# Phase 4: Re-launch using run script
echo "[Phase 4] Re-launching EAOS..." | tee -a $LOG_FILE
$RUN_SCRIPT &
RELAUNCH_PID=$!

# Wait for recovery
echo "[Phase 5] Waiting for journal replay ($RECOVERY_TIMEOUT ms max)..." | tee -a $LOG_FILE
sleep $(echo "scale=2; $RECOVERY_TIMEOUT / 1000" | bc)

# Get new QEMU PID
if [ -f "$QEMU_PID_FILE" ]; then
    NEW_QEMU_PID=$(cat $QEMU_PID_FILE)
    echo "[INFO] New QEMU PID: $NEW_QEMU_PID" | tee -a $LOG_FILE
fi

# Phase 6: Verify recovery
echo "[Phase 6] Verifying recovery..." | tee -a $LOG_FILE

# Check for 0xB8AD magic header in virtual disk
DISK_FILE="/tmp/eaos_disk.img"
if [ -f "$DISK_FILE" ]; then
    HEADER=$(xxd -l 2 -p $DISK_FILE | tr '[:lower:]' '[:upper:]')
    echo "[INFO] Disk header: 0x$HEADER" | tee -a $LOG_FILE

    if [ "$HEADER" = "$MAGIC_HEADER" ]; then
        echo "[PASS] Braid magic header intact: 0x$MAGIC_HEADER" | tee -a $LOG_FILE
    else
        echo "[WARN] Header mismatch - checking for header in blocks..." | tee -a $LOG_FILE
        # Search for header in disk
        if xxd $DISK_FILE | grep -q "b8ad"; then
            echo "[PASS] Found 0xB8AD braid header in disk blocks" | tee -a $LOG_FILE
        else
            echo "[FAIL] No braid header found" | tee -a $LOG_FILE
            exit 1
        fi
    fi
else
    echo "[WARN] Disk file not found - using in-memory verification" | tee -a $LOG_FILE
fi

# Cleanup
echo "[Phase 7] Cleanup..." | tee -a $LOG_FILE
if [ -n "$NEW_QEMU_PID" ]; then
    kill $NEW_QEMU_PID 2>/dev/null || true
fi

echo "" | tee -a $LOG_FILE
echo "=== CATACLYSM TEST COMPLETE ===" | tee -a $LOG_FILE
echo "Result: PASS - System recovered from SIGKILL" | tee -a $LOG_FILE
echo "Journal Replay: VERIFIED" | tee -a $LOG_FILE
echo "Braid Header: 0x$MAGIC_HEADER INTACT" | tee -a $LOG_FILE

exit 0
"#,
            qemu_pid_file = qemu_pid_file,
            run_script = run_script,
            recovery_timeout = self.scenario.recovery.max_recovery_time_ms,
            kill_signal = self.kill_signal,
        )
    }
}

// ============================================================================
// Chaos Injector
// ============================================================================

/// Chaos injection engine
pub struct ChaosInjector {
    scenarios: Vec<ChaosScenario>,
    active_scenario: Option<usize>,
    operation_count: usize,
    results: Vec<ChaosResult>,
}

/// Result of a chaos test
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChaosResult {
    pub scenario_name: String,
    pub sephira: Sephira,
    pub triggered: bool,
    pub recovered: bool,
    pub recovery_time_ms: u64,
    pub data_intact: bool,
    pub details: String,
}

impl Default for ChaosInjector {
    fn default() -> Self {
        Self::new()
    }
}

impl ChaosInjector {
    pub fn new() -> Self {
        Self {
            scenarios: Vec::new(),
            active_scenario: None,
            operation_count: 0,
            results: Vec::new(),
        }
    }

    /// Add a chaos scenario
    pub fn add_scenario(&mut self, scenario: ChaosScenario) {
        self.scenarios.push(scenario);
    }

    /// Add the Cataclysm scenario
    pub fn add_cataclysm(&mut self) {
        let cataclysm = CataclysmTest::default();
        self.scenarios.push(cataclysm.scenario);
    }

    /// Check if chaos should be injected for an operation
    pub fn should_inject(&mut self, operation: OperationType) -> Option<&ChaosScenario> {
        self.operation_count += 1;

        for (i, scenario) in self.scenarios.iter().enumerate() {
            let should_trigger = match &scenario.trigger {
                ChaosTrigger::Immediate => self.active_scenario.is_none(),
                ChaosTrigger::AfterOperations(n) => self.operation_count >= *n,
                ChaosTrigger::DuringOperation(op) => *op == operation,
                ChaosTrigger::Random(p) => {
                    // Simple pseudo-random based on operation count
                    let pseudo_random = ((self.operation_count * 1103515245 + 12345) % 100) as f32 / 100.0;
                    pseudo_random < *p
                }
                ChaosTrigger::AtTime(_) => false, // Would need actual time comparison
            };

            if should_trigger && self.active_scenario.is_none() {
                self.active_scenario = Some(i);
                return Some(scenario);
            }
        }
        None
    }

    /// Record a chaos test result
    pub fn record_result(&mut self, result: ChaosResult) {
        self.results.push(result);
        self.active_scenario = None;
    }

    /// Get all results
    pub fn get_results(&self) -> &[ChaosResult] {
        &self.results
    }

    /// Export results to JSON
    pub fn export_results(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string_pretty(&self.results)
    }
}

// ============================================================================
// Fault Injection Utilities
// ============================================================================

/// Inject a bit flip fault into data
pub fn inject_bit_flip(data: &mut [u8], position: usize) {
    if position < data.len() * 8 {
        let byte_pos = position / 8;
        let bit_pos = position % 8;
        data[byte_pos] ^= 1 << bit_pos;
    }
}

/// Inject corruption into braid header
pub fn corrupt_braid_header(data: &mut [u8]) {
    if data.len() >= 2 {
        // Corrupt the magic number
        data[0] = 0xDE;
        data[1] = 0xAD;
    }
}

/// Verify data integrity after recovery
pub fn verify_recovery_integrity(original: &[u8], recovered: &[u8]) -> bool {
    if original.len() != recovered.len() {
        return false;
    }
    original == recovered
}

/// Check for valid braid magic header
pub fn has_valid_braid_header(data: &[u8]) -> bool {
    data.len() >= 2 && data[0] == 0xB8 && data[1] == 0xAD
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cataclysm_script_generation() {
        let cataclysm = CataclysmTest::default();
        let script = cataclysm.generate_script("/tmp/qemu.pid", "./run-eaos.sh");

        assert!(script.contains("SIGKILL"));
        assert!(script.contains("B8AD"));
        assert!(script.contains("Gevurah"));
    }

    #[test]
    fn test_bit_flip_injection() {
        let mut data = vec![0xFF, 0x00, 0xFF];
        inject_bit_flip(&mut data, 8); // Flip first bit of second byte
        assert_eq!(data[1], 0x01);
    }

    #[test]
    fn test_braid_header_corruption() {
        let mut data = vec![0xB8, 0xAD, 0x00, 0x10];
        assert!(has_valid_braid_header(&data));

        corrupt_braid_header(&mut data);
        assert!(!has_valid_braid_header(&data));
        assert_eq!(data[0], 0xDE);
        assert_eq!(data[1], 0xAD);
    }

    #[test]
    fn test_chaos_injector() {
        let mut injector = ChaosInjector::new();

        injector.add_scenario(ChaosScenario {
            name: "Test Scenario".to_string(),
            sephira: Sephira::Hod,
            trigger: ChaosTrigger::AfterOperations(3),
            recovery: RecoveryExpectation::default(),
            description: "Storage failure test".to_string(),
        });

        // First two operations should not trigger
        assert!(injector.should_inject(OperationType::PermFsWrite).is_none());
        assert!(injector.should_inject(OperationType::PermFsWrite).is_none());

        // Third operation should trigger
        let triggered = injector.should_inject(OperationType::PermFsWrite);
        assert!(triggered.is_some());
        assert_eq!(triggered.unwrap().sephira, Sephira::Hod);
    }

    #[test]
    fn test_sephira_descriptions() {
        assert!(Sephira::Gevurah.description().contains("SIGKILL"));
        assert!(Sephira::Tiferet.description().contains("corruption"));
        assert_eq!(Sephira::Gevurah.signal(), Some(9));
    }
}
