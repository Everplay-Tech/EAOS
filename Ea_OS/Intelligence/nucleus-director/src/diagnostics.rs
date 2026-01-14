//! Diagnostics Module - Exports Gödel numbers and system metrics for dashboard visualization
//!
//! Generates diagnostics.json with:
//! - Gödel numbers from Roulette-RS transformations
//! - Compression ratios
//! - Block storage statistics
//! - System health metrics

use serde::{Deserialize, Serialize};

/// Diagnostic entry for a single braid transformation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BraidDiagnostic {
    pub block_id: u64,
    pub godel_number: String, // String to handle u128 in JSON
    pub godel_hex: String,
    pub original_size: usize,
    pub compressed_size: usize,
    pub compression_ratio: f32,
    pub timestamp: i64,
    pub has_valid_header: bool,
}

/// Diagnostic entry for a stored block
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BlockDiagnostic {
    pub address: u64,
    pub braid_info: Option<BraidDiagnostic>,
    pub patient_id: Option<String>,
    pub record_type: String,
}

/// System health metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemHealth {
    pub biowerk_ready: bool,
    pub storage_ready: bool,
    pub dr_lex_enabled: bool,
    pub sefirot_chaos_mode: bool,
    pub pending_tasks: usize,
    pub total_blocks_stored: usize,
    pub total_bytes_compressed: usize,
    pub average_compression_ratio: f32,
}

/// Complete diagnostics export
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiagnosticsReport {
    pub version: String,
    pub generated_at: i64,
    pub system_health: SystemHealth,
    pub godel_numbers: Vec<BraidDiagnostic>,
    pub stored_blocks: Vec<BlockDiagnostic>,
    pub audit_summary: AuditSummary,
}

/// Summary of Dr-Lex audit activity
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditSummary {
    pub total_audits: usize,
    pub approved: usize,
    pub blocked: usize,
    pub violations_by_type: Vec<ViolationCount>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ViolationCount {
    pub violation_type: String,
    pub count: usize,
}

impl Default for AuditSummary {
    fn default() -> Self {
        Self {
            total_audits: 0,
            approved: 0,
            blocked: 0,
            violations_by_type: Vec::new(),
        }
    }
}

/// Diagnostics collector
pub struct DiagnosticsCollector {
    braids: Vec<BraidDiagnostic>,
    blocks: Vec<BlockDiagnostic>,
    total_original: usize,
    total_compressed: usize,
    audit_approved: usize,
    audit_blocked: usize,
}

impl Default for DiagnosticsCollector {
    fn default() -> Self {
        Self::new()
    }
}

impl DiagnosticsCollector {
    pub fn new() -> Self {
        Self {
            braids: Vec::new(),
            blocks: Vec::new(),
            total_original: 0,
            total_compressed: 0,
            audit_approved: 0,
            audit_blocked: 0,
        }
    }

    /// Record a braid transformation
    pub fn record_braid(
        &mut self,
        block_id: u64,
        godel_number: u128,
        original_size: usize,
        compressed_size: usize,
        has_valid_header: bool,
    ) {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs() as i64)
            .unwrap_or(0);

        let ratio = if original_size > 0 {
            compressed_size as f32 / original_size as f32
        } else {
            1.0
        };

        self.braids.push(BraidDiagnostic {
            block_id,
            godel_number: godel_number.to_string(),
            godel_hex: format!("0x{:032X}", godel_number),
            original_size,
            compressed_size,
            compression_ratio: ratio,
            timestamp,
            has_valid_header,
        });

        self.total_original += original_size;
        self.total_compressed += compressed_size;
    }

    /// Record a stored block
    pub fn record_block(
        &mut self,
        address: u64,
        braid_info: Option<BraidDiagnostic>,
        patient_id: Option<String>,
        record_type: &str,
    ) {
        self.blocks.push(BlockDiagnostic {
            address,
            braid_info,
            patient_id,
            record_type: record_type.to_string(),
        });
    }

    /// Record audit result
    pub fn record_audit(&mut self, approved: bool) {
        if approved {
            self.audit_approved += 1;
        } else {
            self.audit_blocked += 1;
        }
    }

    /// Generate the diagnostics report
    pub fn generate_report(&self, biowerk_ready: bool, storage_ready: bool) -> DiagnosticsReport {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs() as i64)
            .unwrap_or(0);

        let avg_ratio = if self.total_original > 0 {
            self.total_compressed as f32 / self.total_original as f32
        } else {
            1.0
        };

        DiagnosticsReport {
            version: "1.0.0".to_string(),
            generated_at: timestamp,
            system_health: SystemHealth {
                biowerk_ready,
                storage_ready,
                dr_lex_enabled: true,
                sefirot_chaos_mode: false,
                pending_tasks: 0,
                total_blocks_stored: self.blocks.len(),
                total_bytes_compressed: self.total_compressed,
                average_compression_ratio: avg_ratio,
            },
            godel_numbers: self.braids.clone(),
            stored_blocks: self.blocks.clone(),
            audit_summary: AuditSummary {
                total_audits: self.audit_approved + self.audit_blocked,
                approved: self.audit_approved,
                blocked: self.audit_blocked,
                violations_by_type: Vec::new(),
            },
        }
    }

    /// Export diagnostics to JSON string
    pub fn export_json(&self, biowerk_ready: bool, storage_ready: bool) -> Result<String, serde_json::Error> {
        let report = self.generate_report(biowerk_ready, storage_ready);
        serde_json::to_string_pretty(&report)
    }

    /// Export diagnostics to a file
    #[cfg(feature = "std")]
    pub fn export_to_file(
        &self,
        path: &str,
        biowerk_ready: bool,
        storage_ready: bool,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let json = self.export_json(biowerk_ready, storage_ready)?;
        std::fs::write(path, json)?;
        Ok(())
    }

    /// Get all Gödel numbers as a simple list (for dashboard)
    pub fn get_godel_numbers(&self) -> Vec<(u64, String)> {
        self.braids
            .iter()
            .map(|b| (b.block_id, b.godel_number.clone()))
            .collect()
    }

    /// Get compression statistics
    pub fn get_compression_stats(&self) -> (usize, usize, f32) {
        let avg_ratio = if self.total_original > 0 {
            self.total_compressed as f32 / self.total_original as f32
        } else {
            1.0
        };
        (self.total_original, self.total_compressed, avg_ratio)
    }
}

/// Quick function to generate a sample diagnostics.json
pub fn generate_sample_diagnostics() -> String {
    let mut collector = DiagnosticsCollector::new();

    // Add sample braid data
    collector.record_braid(
        1,
        340282366920938463463374607431768211455u128, // Max u128
        4096,
        322,
        true,
    );
    collector.record_braid(
        2,
        123456789012345678901234567890u128,
        4096,
        410,
        true,
    );

    // Add sample block data
    collector.record_block(4096, None, Some("PAT-2025-001".to_string()), "PatientRecord");
    collector.record_block(8192, None, Some("PAT-2025-002".to_string()), "VitalSigns");

    // Record some audits
    collector.record_audit(true);
    collector.record_audit(true);
    collector.record_audit(false); // One blocked

    collector.export_json(true, true).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_diagnostics_collection() {
        let mut collector = DiagnosticsCollector::new();

        collector.record_braid(1, 12345678901234567890u128, 4096, 300, true);
        collector.record_audit(true);

        let report = collector.generate_report(true, true);

        assert_eq!(report.godel_numbers.len(), 1);
        assert_eq!(report.audit_summary.approved, 1);
        assert!(report.system_health.biowerk_ready);
    }

    #[test]
    fn test_json_export() {
        let collector = DiagnosticsCollector::new();
        let json = collector.export_json(true, true);

        assert!(json.is_ok());
        let json_str = json.unwrap();
        assert!(json_str.contains("godel_numbers"));
        assert!(json_str.contains("system_health"));
    }

    #[test]
    fn test_sample_diagnostics() {
        let json = generate_sample_diagnostics();
        assert!(json.contains("340282366920938463463374607431768211455"));
        assert!(json.contains("PAT-2025-001"));
    }
}
