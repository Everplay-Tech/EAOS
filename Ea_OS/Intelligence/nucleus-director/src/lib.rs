#![cfg_attr(not(feature = "std"), no_std)]

//! Nucleus Director - Central Orchestration for EAOS Organism
//!
//! The Nucleus Director coordinates all components of the EAOS organism:
//!
//! 1. **Request Handling**: Receives high-level requests from external systems
//! 2. **Agent Dispatch**: Routes requests to BIOwerk agents (Osteon, Myocyte)
//! 3. **Task Planning**: Uses Hyperbolic Chamber for complex operations
//! 4. **Storage Pipeline**: Coordinates PermFS-Bridge for data persistence
//! 5. **Audit Trail**: Ensures all operations are logged and traceable

extern crate alloc;

pub mod diagnostics;

use alloc::format;
use alloc::string::{String, ToString};
use alloc::vec::Vec;
use biowerk_agent::{AgentRequest, AgentResponse, BIOwerk};
use ea_cardio::CardioMonitor;
use ea_symbiote::{SovereignDocument, Symbiote};
use muscle_contract::BootParameters;
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
    pub timestamp: u64, // Real kernel timestamp (TSC)
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
        self.cardio.tick();
        let heartbeat = self.cardio.snapshot();
        let tick = heartbeat.tick;
        let uptime_secs = self.cardio.uptime_secs();
        let blob = heartbeat.to_blob();

        match self.synapse.commit_organ_data(blob) {
            Ok(addr) => {
                self.pending_tasks.push(PlannedTask::WriteBlocks {
                    block_count: 1,
                    metadata: TaskMetadata {
                        operation: format!("CardioHeartbeat:{}", tick),
                        timestamp: get_kernel_time(),
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
            timestamp: get_kernel_time(),
        });

        match response {
            AgentResponse::DocumentSaved { filename, address, size } => {
                self.pending_tasks.push(PlannedTask::WriteBlocks {
                    block_count: 1,
                    metadata: TaskMetadata {
                        operation: format!("WriteDocument:{}", filename),
                        timestamp: get_kernel_time(),
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
                self.pending_tasks.push(PlannedTask::WriteBlocks {
                    block_count: 1,
                    metadata: TaskMetadata {
                        operation: format!("ProcessLogic:{}", name),
                        timestamp: get_kernel_time(),
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
        let mut parts = input.splitn(2, ' ');
        let cmd = parts.next()?.to_lowercase();
        let rest = parts.next();

        match cmd.as_str() {
            "write" | "doc" => {
                if let Some(r) = rest {
                    let mut file_content = r.splitn(2, ' ');
                    let fname = file_content.next()?.to_string();
                    let content = file_content.next()?.to_string();
                    Some(DirectorRequest::WriteDocument { filename: fname, content })
                } else {
                    None
                }
            }
            "logic" | "calc" => {
                if let Some(r) = rest {
                    let mut name_formula = r.splitn(2, ' ');
                    let name = name_formula.next()?.to_string();
                    let formula = name_formula.next()?.to_string();
                    Some(DirectorRequest::ProcessLogic { name, formula })
                } else {
                    None
                }
            }
            "cardio" | "heartbeat" | "pulse" => Some(DirectorRequest::CardioHeartbeat),
            "status" => Some(DirectorRequest::SystemStatus),
            "list" => Some(DirectorRequest::ListDocuments),
            "help" | "?" => Some(DirectorRequest::Help),
            _ => None,
        }
    }

    /// Get help text
    pub fn help_text() -> String {
        "EAOS Nucleus Director - Office Suite Commands\n\n"
        .to_string()
    }

    pub fn pending_task_count(&self) -> usize {
        self.pending_tasks.len()
    }

    pub fn biowerk(&self) -> &BIOwerk {
        &self.biowerk
    }

    pub fn biowerk_mut(&mut self) -> &mut BIOwerk {
        &mut self.biowerk
    }
}

// ============================================================================ 
// Kernel Interop (Always Real Code)
// ============================================================================ 

/// Get real monotonic time from the Referee kernel via syscall 7
fn get_kernel_time() -> u64 {
    #[cfg(feature = "std")]
    {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0)
    }
    #[cfg(not(feature = "std"))]
    {
        let mut result: u64;
        unsafe {
            core::arch::asm!(
                "syscall",
                in("rax") 7u64, // SyscallNumber::GetTime
                out("rax") result,
                options(nostack, nomem)
            );
        }
        result
    }
}

mod thalamus;

mod font;

mod visual_cortex;

mod endocrine;

use thalamus::{Thalamus, Stimulus};
use visual_cortex::{VisualCortex, Color};
use endocrine::EndocrineSystem;
use muscle_contract::abi::Pheromone;
use ea_sentry::guard;
use muscle_contract::sentry::{SentryOp, SentryRequest};

// ...

/// Nucleus Trusted Entry Point (Stage 8 Manifestation)
///
/// This is the terminal destination of the UEFI boot chain:
/// Referee -> Preloader -> Nucleus
#[no_mangle]
pub extern "C" fn boot_entry(params: *const BootParameters) -> ! {
    let params = unsafe {
        if params.is_null() || (*params).magic != 0xEA05_B007 {
            loop { core::hint::spin_loop(); } // Invalid handoff
        }
        &*params
    };

    // Initialize Organs
    let mut director = NucleusDirector::new();
    let mut thalamus = Thalamus::new(params);
    let mut endocrine = EndocrineSystem::new();
    
    // Initialize Visual Cortex (The Retina)
    let mut visual = VisualCortex::new(params);
    if let Some(ref mut v) = visual {
        v.clear(Color::VOID);
        v.draw_text(20, 20, "EAOS Nucleus v1.0", Color::LIFE);
        v.draw_text(20, 40, "Event Loop: DOUBLE BUFFERED", Color::SYNAPSE);
    }
    
    // Initialize Sentry with Master Key
    let _ = guard(SentryRequest {
        op: SentryOp::Initialize,
        payload: params.master_key,
    });
    
    endocrine.secrete(Pheromone::Inert); // Kickstart

    // Nucleus Event Loop (The Choir)
    loop {
        // 1. Systole (Cycle Pheromones)
        endocrine.cycle();
        let mut signals = alloc::vec::Vec::new();
        signals.extend_from_slice(endocrine.sense());
        
        // 2. Diastole (Organs React to Circulation)
        
        // A. Visual Cortex (Perception)
        for signal in &signals {
            if let Some(ref mut v) = visual {
                match signal {
                    Pheromone::SomaticInput(byte) => {
                        v.draw_text(20, 100, "Input: Sensed", Color::LIFE);
                    }
                    Pheromone::ConceptFormed(val) => {
                        v.draw_text(20, 120, "Logic: Computed", Color::SYNAPSE);
                    }
                    Pheromone::OsteonCalcified => {
                        v.draw_text(20, 140, "SAVED", Color::LIFE);
                    }
                    Pheromone::Adrenaline(code) => {
                        v.draw_text(20, 160, "PANIC", Color::ALERT);
                    }
                    _ => {}
                }
            }
        }
        
        // B. Myocyte (Cognition)
        for signal in &signals {
            if let Pheromone::SomaticInput(b's') = signal {
                // 's' triggers simulation
                if let Ok(res) = director.biowerk().myocyte.evaluate_simple("2 + 2") {
                    endocrine.secrete(Pheromone::ConceptFormed(res));
                }
            }
        }
        
        // C. Osteon (Memory)
        for signal in &signals {
            if let Pheromone::ConceptFormed(_) = signal {
                // Save the thought
                let _ = director.process(DirectorRequest::WriteDocument {
                    filename: "thought.qyn".to_string(),
                    content: "4.0".to_string(),
                });
                endocrine.secrete(Pheromone::OsteonCalcified);
            }
        }
        
        // 3. Secretion (Input Gathering)
        // Thalamus pushes new sensory data for NEXT tick
        if let Some(stimulus) = thalamus.fetch_next_stimulus() {
             match stimulus {
                 Stimulus::Volition(bytes) => {
                     for b in bytes {
                         endocrine.secrete(Pheromone::SomaticInput(b));
                     }
                 }
                 Stimulus::Perception(bytes) => {
                     endocrine.secrete(Pheromone::VisceralInput(bytes.len()));
                 }
             }
        }

        // F. Rest: Yield to kernel
        #[cfg(not(feature = "std"))]
        unsafe {
            core::arch::asm!("syscall", in("rax") 3u64); // SyscallNumber::Yield
        }
    }
}