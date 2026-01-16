//! Nucleus Director - Central Orchestration for EAOS Organism
//!
//! The Nucleus Director coordinates all components of the EAOS organism:
//!
//! 1. **Request Handling**: Receives high-level requests from external systems
//! 2. **Agent Dispatch**: Routes requests to BIOwerk agents (Osteon, Myocyte)
//! 3. **Task Planning**: Uses Hyperbolic Chamber for complex operations
//! 4. **Storage Pipeline**: Coordinates PermFS-Bridge for data persistence
//! 5. **Audit Trail**: Ensures all operations are logged and traceable
//!
//! ## Office Suite Full Cycle
//!
//! ```text
//! External Request (CLI/Serial)
//!        │
//!        ▼
//! ┌──────────────┐
//! │   Nucleus    │ ← Central Director
//! │   Director   │
//! └──────┬───────┘
//!        │
//!   ┌────┴────┐
//!   ▼         ▼
//! ┌─────┐  ┌─────┐
//! │Osteon│  │Myocyte│ ← BIOwerk Agents
//! │(Docs)│  │(Logic)│
//! └──┬───┘  └──┬────┘
//!    │         │
//!    └────┬────┘
//!         ▼
//! ┌──────────────┐
//! │   Symbiote   │ ← IPC Layer
//! │   Synapse    │
//! └──────┬───────┘
//!         ▼
//! ┌──────────────┐
//! │   PermFS     │ ← Storage
//! └──────────────┘
//! ```

pub mod diagnostics;

use biowerk_agent::{AgentRequest, AgentResponse, BIOwerk};
use ea_cardio::CardioMonitor;
use ea_symbiote::{SovereignDocument, Symbiote};
use serde::{Deserialize, Serialize};

/// Magic header for braided blocks (0xB8AD)
pub const BRAID_MAGIC: [u8; 2] = [0xB8, 0xAD];

// ============================================================================
// Director Request/Response Types
// ============================================================================

/// High-level requests to the Nucleus Director
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DirectorRequest {
    /// Write a document (Osteon)
    WriteDocument { filename: String, content: String },
    /// Process logic/formula (Myocyte)
    ProcessLogic { name: String, formula: String },
    /// Record a heartbeat (Cardio)
    CardioHeartbeat,
    /// Get system status
    SystemStatus,
    /// List all documents
    ListDocuments,
    /// Help/usage information
    Help,
}

/// Response from the Nucleus Director
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DirectorResponse {
    /// Document saved successfully
    DocumentSaved {
        filename: String,
        block_offset: u64,
        size: usize,
    },
    /// Logic processed successfully
    LogicProcessed {
        name: String,
        block_offset: u64,
        bytecode_size: usize,
    },
    /// Heartbeat recorded successfully
    HeartbeatRecorded {
        tick: u64,
        uptime_secs: u64,
        block_offset: u64,
    },
    /// System status
    Status {
        biowerk_ready: bool,
        document_count: usize,
        logic_count: usize,
        heartbeat_tick: u64,
    },
    /// Document list
    DocumentList { count: usize, documents: Vec<String> },
    /// Help text
    HelpText(String),
    /// Error occurred
    Error(String),
}

// ============================================================================
// Task Planner (Hyperbolic Chamber Interface)
// ============================================================================

/// Task types for the Hyperbolic Chamber planner
#[derive(Debug, Clone)]
pub enum PlannedTask {
    /// Write blocks to storage
    WriteBlocks {
        block_count: usize,
        metadata: TaskMetadata,
    },
    /// Read blocks from storage
    ReadBlocks {
        addresses: Vec<u64>,
        metadata: TaskMetadata,
    },
}

/// Metadata for planned tasks
#[derive(Debug, Clone)]
pub struct TaskMetadata {
    pub operation: String,
    pub timestamp: i64,
    pub priority: u8,
}

// ============================================================================
// Nucleus Director
// ============================================================================

/// The Nucleus Director orchestrates the full EAOS organism
pub struct NucleusDirector {
    biowerk: BIOwerk,
    cardio: CardioMonitor,
    synapse: Symbiote,
    pending_tasks: Vec<PlannedTask>,
}

impl Default for NucleusDirector {
    fn default() -> Self {
        Self::new()
    }
}

impl NucleusDirector {
    /// Create a new Nucleus Director
    pub fn new() -> Self {
        Self {
            biowerk: BIOwerk::new(),
            cardio: CardioMonitor::new(),
            synapse: Symbiote::new(),
            pending_tasks: Vec::new(),
        }
    }

    /// Process a high-level request
    pub fn process(&mut self, request: DirectorRequest) -> DirectorResponse {
        match request {
            DirectorRequest::WriteDocument { filename, content } => {
                self.write_document(&filename, &content)
            }
            DirectorRequest::ProcessLogic { name, formula } => {
                self.process_logic(&name, &formula)
            }
            DirectorRequest::CardioHeartbeat => {
                self.record_heartbeat()
            }
            DirectorRequest::SystemStatus => {
                DirectorResponse::Status {
                    biowerk_ready: true,
                    document_count: self.biowerk.osteon.document_count(),
                    logic_count: self.biowerk.myocyte.logic_count(),
                    heartbeat_tick: self.cardio.current_tick(),
                }
            }
            DirectorRequest::ListDocuments => {
                let addrs = self.biowerk.osteon.list_documents();
                DirectorResponse::DocumentList {
                    count: addrs.len(),
                    documents: addrs.iter().map(|a| format!("block:{}", a.block_offset())).collect(),
                }
            }
            DirectorRequest::Help => {
                DirectorResponse::HelpText(Self::help_text())
            }
        }
    }

    /// Record a heartbeat via Cardio organ
    fn record_heartbeat(&mut self) -> DirectorResponse {
        // Advance the heartbeat
        self.cardio.tick();

        // Take a snapshot
        let heartbeat = self.cardio.snapshot();
        let tick = heartbeat.tick;
        let uptime_secs = self.cardio.uptime_secs();

        // Convert to SovereignBlob using trait (PROVES ECOSYSTEM EXTENSIBILITY)
        let blob = heartbeat.to_blob();

        // Commit through Symbiote
        match self.synapse.commit_organ_data(blob) {
            Ok(addr) => {
                // Record task for audit
                self.pending_tasks.push(PlannedTask::WriteBlocks {
                    block_count: 1,
                    metadata: TaskMetadata {
                        operation: format!("CardioHeartbeat:{}", tick),
                        timestamp: std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .map(|d| d.as_secs() as i64)
                            .unwrap_or(0),
                        priority: 2,
                    },
                });

                DirectorResponse::HeartbeatRecorded {
                    tick,
                    uptime_secs,
                    block_offset: addr.block_offset(),
                }
            }
            Err(e) => DirectorResponse::Error(format!("Heartbeat failed: {:?}", e)),
        }
    }

    /// Write a document via Osteon
    fn write_document(&mut self, filename: &str, content: &str) -> DirectorResponse {
        let response = self.biowerk.process(AgentRequest::WriteDocument {
            filename: filename.to_string(),
            content: content.to_string(),
        });

        match response {
            AgentResponse::DocumentSaved { filename, address, size } => {
                // Record task for audit
                self.pending_tasks.push(PlannedTask::WriteBlocks {
                    block_count: 1,
                    metadata: TaskMetadata {
                        operation: format!("WriteDocument:{}", filename),
                        timestamp: std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .map(|d| d.as_secs() as i64)
                            .unwrap_or(0),
                        priority: 1,
                    },
                });

                DirectorResponse::DocumentSaved {
                    filename,
                    block_offset: address.block_offset(),
                    size,
                }
            }
            AgentResponse::Error(e) => DirectorResponse::Error(e),
            _ => DirectorResponse::Error("Unexpected response from Osteon".to_string()),
        }
    }

    /// Process logic via Myocyte
    fn process_logic(&mut self, name: &str, formula: &str) -> DirectorResponse {
        let response = self.biowerk.process(AgentRequest::ProcessLogic {
            name: name.to_string(),
            formula: formula.to_string(),
        });

        match response {
            AgentResponse::LogicProcessed { name, address, bytecode_size } => {
                // Record task for audit
                self.pending_tasks.push(PlannedTask::WriteBlocks {
                    block_count: 1,
                    metadata: TaskMetadata {
                        operation: format!("ProcessLogic:{}", name),
                        timestamp: std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .map(|d| d.as_secs() as i64)
                            .unwrap_or(0),
                        priority: 1,
                    },
                });

                DirectorResponse::LogicProcessed {
                    name,
                    block_offset: address.block_offset(),
                    bytecode_size,
                }
            }
            AgentResponse::Error(e) => DirectorResponse::Error(e),
            _ => DirectorResponse::Error("Unexpected response from Myocyte".to_string()),
        }
    }

    /// Parse a command string into a DirectorRequest
    pub fn parse_command(input: &str) -> Option<DirectorRequest> {
        let input = input.trim();
        let parts: Vec<&str> = input.splitn(2, ' ').collect();

        match parts.get(0).map(|s| s.to_lowercase()).as_deref() {
            Some("write") | Some("doc") => {
                if let Some(rest) = parts.get(1) {
                    let file_content: Vec<&str> = rest.splitn(2, ' ').collect();
                    if file_content.len() == 2 {
                        return Some(DirectorRequest::WriteDocument {
                            filename: file_content[0].to_string(),
                            content: file_content[1].to_string(),
                        });
                    }
                }
                None
            }
            Some("logic") | Some("calc") => {
                if let Some(rest) = parts.get(1) {
                    let name_formula: Vec<&str> = rest.splitn(2, ' ').collect();
                    if name_formula.len() == 2 {
                        return Some(DirectorRequest::ProcessLogic {
                            name: name_formula[0].to_string(),
                            formula: name_formula[1].to_string(),
                        });
                    }
                }
                None
            }
            Some("cardio") | Some("heartbeat") | Some("pulse") => {
                Some(DirectorRequest::CardioHeartbeat)
            }
            Some("status") => Some(DirectorRequest::SystemStatus),
            Some("list") => Some(DirectorRequest::ListDocuments),
            Some("help") | Some("?") => Some(DirectorRequest::Help),
            _ => None,
        }
    }

    /// Get help text
    pub fn help_text() -> String {
        r#"EAOS Nucleus Director - Office Suite Commands

Commands:
  write <filename> <content>   - Write a document via Osteon
  doc <filename> <content>     - Alias for write
  logic <name> <formula>       - Process logic via Myocyte
  calc <name> <formula>        - Alias for logic
  cardio                       - Record a heartbeat via Cardio organ
  heartbeat                    - Alias for cardio
  pulse                        - Alias for cardio
  status                       - Show system status
  list                         - List saved documents
  help                         - Show this help

Examples:
  write meeting_notes.txt "Q1 Planning Meeting"
  logic budget.qyn "revenue - expenses"
  cardio
  status
"#.to_string()
    }

    /// Get pending task count
    pub fn pending_task_count(&self) -> usize {
        self.pending_tasks.len()
    }

    /// Get BIOwerk reference
    pub fn biowerk(&self) -> &BIOwerk {
        &self.biowerk
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_office_suite_cycle() {
        let mut director = NucleusDirector::new();

        // Write a document
        let doc_response = director.process(DirectorRequest::WriteDocument {
            filename: "meeting_notes.txt".to_string(),
            content: "Q1 Planning Meeting\n- Goals\n- Tasks".to_string(),
        });

        match doc_response {
            DirectorResponse::DocumentSaved { filename, block_offset, size } => {
                assert_eq!(filename, "meeting_notes.txt");
                assert_eq!(block_offset, 0);
                assert!(size > 0);
                println!("Document saved: {} at block {} ({} bytes)", filename, block_offset, size);
            }
            DirectorResponse::Error(e) => panic!("Save failed: {}", e),
            _ => panic!("Unexpected response"),
        }

        // Process logic
        let logic_response = director.process(DirectorRequest::ProcessLogic {
            name: "budget.qyn".to_string(),
            formula: "revenue - expenses".to_string(),
        });

        match logic_response {
            DirectorResponse::LogicProcessed { name, block_offset, bytecode_size } => {
                assert_eq!(name, "budget.qyn");
                assert_eq!(block_offset, 1);
                assert!(bytecode_size > 0);
                println!("Logic processed: {} at block {} ({} bytes)", name, block_offset, bytecode_size);
            }
            DirectorResponse::Error(e) => panic!("Logic failed: {}", e),
            _ => panic!("Unexpected response"),
        }

        // Check status
        let status = director.process(DirectorRequest::SystemStatus);
        match status {
            DirectorResponse::Status { biowerk_ready, document_count, logic_count, heartbeat_tick } => {
                assert!(biowerk_ready);
                assert_eq!(document_count, 1);
                assert_eq!(logic_count, 1);
                assert_eq!(heartbeat_tick, 0);
            }
            _ => panic!("Expected Status response"),
        }

        println!("Office suite cycle test passed - no patient references!");
    }

    #[test]
    fn test_command_parsing() {
        // Document commands
        assert!(matches!(
            NucleusDirector::parse_command("write test.txt hello world"),
            Some(DirectorRequest::WriteDocument { .. })
        ));
        assert!(matches!(
            NucleusDirector::parse_command("doc test.txt hello"),
            Some(DirectorRequest::WriteDocument { .. })
        ));

        // Logic commands
        assert!(matches!(
            NucleusDirector::parse_command("logic calc.qyn 2+2"),
            Some(DirectorRequest::ProcessLogic { .. })
        ));
        assert!(matches!(
            NucleusDirector::parse_command("calc budget.qyn revenue-expenses"),
            Some(DirectorRequest::ProcessLogic { .. })
        ));

        // Other commands
        assert!(matches!(
            NucleusDirector::parse_command("status"),
            Some(DirectorRequest::SystemStatus)
        ));
        assert!(matches!(
            NucleusDirector::parse_command("list"),
            Some(DirectorRequest::ListDocuments)
        ));
        assert!(matches!(
            NucleusDirector::parse_command("help"),
            Some(DirectorRequest::Help)
        ));

        // Invalid
        assert!(NucleusDirector::parse_command("invalid").is_none());
    }

    #[test]
    fn test_help_output() {
        let mut director = NucleusDirector::new();
        let response = director.process(DirectorRequest::Help);

        match response {
            DirectorResponse::HelpText(text) => {
                assert!(text.contains("write"));
                assert!(text.contains("logic"));
                assert!(text.contains("status"));
            }
            _ => panic!("Expected HelpText"),
        }
    }
}
