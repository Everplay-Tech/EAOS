#![cfg_attr(not(feature = "std"), no_std)]

//! BIOwerk Office Suite for EAOS
//!
//! This crate provides generic document and computation agents:
//!
//! - **Osteon**: Document agent - creates, formats, and stores text documents
//! - **Myocyte**: Logic agent - processes formulas and computations
//! - **Hemato**: Transport agent - handles data flow between organs
//!
//! All output is wrapped in SovereignBlob containers for PermFS storage via Symbiote.

extern crate alloc;

pub mod osteon;
pub mod myocyte;

use alloc::string::{String, ToString};
use alloc::vec::Vec;
use alloc::format;
use ea_symbiote::{BlobType, SovereignDocument, Symbiote, BlockAddr};
use serde::{Deserialize, Serialize};

// ============================================================================
// Generic Document Types
// ============================================================================

/// A generic text document for the Office Suite
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Document {
    /// Document title/filename
    pub title: String,
    /// Document content
    pub content: String,
    /// Creation timestamp (Unix epoch)
    pub created_at: i64,
    /// Last modified timestamp
    pub modified_at: i64,
    /// Document metadata
    pub metadata: DocumentMetadata,
}

/// Metadata for documents
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DocumentMetadata {
    /// Author name
    pub author: Option<String>,
    /// Document tags
    pub tags: Vec<String>,
    /// Document version
    pub version: u32,
}

impl Document {
    /// Create a new document with explicit timestamp (in seconds)
    pub fn new(title: &str, content: &str, timestamp: u64) -> Self {
        Self {
            title: title.to_string(),
            content: content.to_string(),
            created_at: timestamp as i64,
            modified_at: timestamp as i64,
            metadata: DocumentMetadata::default(),
        }
    }

    /// Set the author
    pub fn with_author(mut self, author: &str) -> Self {
        self.metadata.author = Some(author.to_string());
        self
    }

    /// Add a tag
    pub fn with_tag(mut self, tag: &str) -> Self {
        self.metadata.tags.push(tag.to_string());
        self
    }
}

impl SovereignDocument for Document {
    fn blob_type(&self) -> BlobType {
        BlobType::Document
    }

    fn to_bytes(&self) -> Vec<u8> {
        serde_json::to_vec(self).unwrap_or_default()
    }

    fn from_bytes(data: &[u8]) -> Option<Self> {
        serde_json::from_slice(data).ok()
    }
}

// ============================================================================
// Logic/Computation Types
// ============================================================================

/// A logic computation unit
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogicUnit {
    /// Name/identifier for this logic
    pub name: String,
    /// The formula or expression
    pub formula: String,
    /// Compiled bytecode (after processing)
    pub bytecode: Option<Vec<u8>>,
    /// Result of computation (if executed)
    pub result: Option<String>,
}

impl LogicUnit {
    /// Create a new logic unit
    pub fn new(name: &str, formula: &str) -> Self {
        Self {
            name: name.to_string(),
            formula: formula.to_string(),
            bytecode: None,
            result: None,
        }
    }

    /// Set compiled bytecode
    pub fn with_bytecode(mut self, bytecode: Vec<u8>) -> Self {
        self.bytecode = Some(bytecode);
        self
    }

    /// Set computation result
    pub fn with_result(mut self, result: &str) -> Self {
        self.result = Some(result.to_string());
        self
    }
}

impl SovereignDocument for LogicUnit {
    fn blob_type(&self) -> BlobType {
        BlobType::Logic
    }

    fn to_bytes(&self) -> Vec<u8> {
        serde_json::to_vec(self).unwrap_or_default()
    }

    fn from_bytes(data: &[u8]) -> Option<Self> {
        serde_json::from_slice(data).ok()
    }
}

// ============================================================================
// Agent Request/Response Types
// ============================================================================

/// Request types for BIOwerk agents
#[derive(Debug, Clone)]
pub enum AgentRequest {
    /// Write a text document (requires timestamp from director)
    WriteDocument { filename: String, content: String, timestamp: u64 },
    /// Process a logic formula
    ProcessLogic { name: String, formula: String },
    /// Read a document by address
    ReadDocument(BlockAddr),
    /// List recent documents
    ListDocuments,
}

/// Response from BIOwerk agents
#[derive(Debug, Clone)]
pub enum AgentResponse {
    /// Document was saved successfully
    DocumentSaved {
        filename: String,
        address: BlockAddr,
        size: usize,
    },
    /// Logic was processed successfully
    LogicProcessed {
        name: String,
        address: BlockAddr,
        bytecode_size: usize,
    },
    /// Document content retrieved
    DocumentContent(Document),
    /// List of document addresses
    DocumentList(Vec<BlockAddr>),
    /// Error occurred
    Error(String),
}

// ============================================================================
// Hemato Agent - Data Transport (Generic)
// ============================================================================

/// Hemato Agent: Handles data flow between organs
///
/// Named after blood cells, this agent transports data between
/// different parts of the EAOS organism.
pub struct HematoAgent {
    pending_requests: Vec<AgentRequest>,
}

impl Default for HematoAgent {
    fn default() -> Self {
        Self::new()
    }
}

impl HematoAgent {
    pub fn new() -> Self {
        Self {
            pending_requests: Vec::new(),
        }
    }

    /// Queue a request for processing
    pub fn enqueue(&mut self, request: AgentRequest) {
        self.pending_requests.push(request);
    }

    /// Get pending request count
    pub fn pending_count(&self) -> usize {
        self.pending_requests.len()
    }

    /// Drain all pending requests
    pub fn drain(&mut self) -> Vec<AgentRequest> {
        // In no_std, mem::take requires Default which Vec has
        core::mem::take(&mut self.pending_requests)
    }

    /// Route a request to the appropriate handler
    pub fn route(&self, request: &AgentRequest) -> &'static str {
        match request {
            AgentRequest::WriteDocument { .. } => "osteon",
            AgentRequest::ReadDocument(_) => "osteon",
            AgentRequest::ListDocuments => "osteon",
            AgentRequest::ProcessLogic { .. } => "myocyte",
        }
    }
}

// ============================================================================
// BIOwerk Coordinator
// ============================================================================

/// Coordinates all BIOwerk agents - the Office Suite coordinator
pub struct BIOwerk {
    /// Document agent
    pub osteon: osteon::OsteonAgent,
    /// Logic/computation agent
    pub myocyte: myocyte::MyocyteAgent,
    /// Data transport agent
    pub hemato: HematoAgent,
    /// Symbiote IPC layer
    synapse: Symbiote,
}

impl Default for BIOwerk {
    fn default() -> Self {
        Self::new()
    }
}

impl BIOwerk {
    pub fn new() -> Self {
        Self {
            osteon: osteon::OsteonAgent::new(),
            myocyte: myocyte::MyocyteAgent::new(),
            hemato: HematoAgent::new(),
            synapse: Symbiote::new(),
        }
    }

    /// Process a request through the appropriate agent
    pub fn process(&mut self, request: AgentRequest) -> AgentResponse {
        match request {
            AgentRequest::WriteDocument { filename, content, timestamp } => {
                self.osteon.write_text(&mut self.synapse, &filename, &content, timestamp)
            }
            AgentRequest::ProcessLogic { name, formula } => {
                self.myocyte.process_logic(&mut self.synapse, &name, &formula)
            }
            AgentRequest::ReadDocument(addr) => {
                self.osteon.read_document(&self.synapse, addr)
            }
            AgentRequest::ListDocuments => {
                AgentResponse::DocumentList(self.osteon.list_documents())
            }
        }
    }

    /// Get the Symbiote synapse for direct access
    pub fn synapse(&self) -> &Symbiote {
        &self.synapse
    }

    /// Get mutable synapse
    pub fn synapse_mut(&mut self) -> &mut Symbiote {
        &mut self.synapse
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_document_creation() {
        let doc = Document::new("test.txt", "Hello World", 1000)
            .with_author("EAOS")
            .with_tag("test");

        assert_eq!(doc.title, "test.txt");
        assert_eq!(doc.content, "Hello World");
        assert_eq!(doc.created_at, 1000);
        assert_eq!(doc.metadata.author, Some("EAOS".to_string()));
        assert!(doc.metadata.tags.contains(&"test".to_string()));
    }

    #[test]
    fn test_document_sovereign_trait() {
        let doc = Document::new("greeting.txt", "Hello Sovereign World", 2000);

        assert_eq!(doc.blob_type(), BlobType::Document);

        let bytes = doc.to_bytes();
        let restored = Document::from_bytes(&bytes).unwrap();

        assert_eq!(restored.title, doc.title);
        assert_eq!(restored.content, doc.content);
        assert_eq!(restored.created_at, 2000);
    }

    #[test]
    fn test_office_workflow() {
        let mut biowerk = BIOwerk::new();

        // Save a meeting notes document with explicit timestamp
        let doc_response = biowerk.process(AgentRequest::WriteDocument {
            filename: "meeting_notes.txt".to_string(),
            content: "Q1 Planning Meeting".to_string(),
            timestamp: 1234567890,
        });

        match doc_response {
            AgentResponse::DocumentSaved { filename, address, size } => {
                assert_eq!(filename, "meeting_notes.txt");
                assert!(!address.is_null());
                assert!(size > 0);
            }
            AgentResponse::Error(e) => panic!("Document save failed: {}", e),
            _ => panic!("Unexpected response"),
        }
    }
}