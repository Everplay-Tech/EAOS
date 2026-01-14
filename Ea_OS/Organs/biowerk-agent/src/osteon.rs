//! Osteon Agent - Document Writer for BIOwerk Office Suite
//!
//! Named after bone cells (osteocytes), Osteon provides the structural
//! foundation for documents in EAOS. It handles:
//!
//! - Creating and formatting text documents
//! - Wrapping documents in SovereignBlob containers
//! - Storing documents via Symbiote to PermFS
//! - Retrieving and listing documents

use ea_symbiote::{BlockAddr, SovereignDocument, Symbiote};

use crate::{AgentResponse, Document};

/// Osteon Agent: The Document Writer
///
/// Handles all document creation, storage, and retrieval operations.
pub struct OsteonAgent {
    /// Track of recently saved document addresses
    recent_documents: Vec<BlockAddr>,
}

impl Default for OsteonAgent {
    fn default() -> Self {
        Self::new()
    }
}

impl OsteonAgent {
    /// Create a new Osteon agent
    pub fn new() -> Self {
        Self {
            recent_documents: Vec::new(),
        }
    }

    /// Write a text document to storage
    ///
    /// This function:
    /// 1. Creates a Document with the given filename and content
    /// 2. Converts it to a SovereignBlob of type Document
    /// 3. Applies the filename as a label
    /// 4. Sends it to Symbiote for storage
    ///
    /// # Arguments
    /// * `synapse` - The Symbiote IPC layer
    /// * `filename` - The document filename/label
    /// * `content` - The text content of the document
    ///
    /// # Returns
    /// An AgentResponse indicating success or failure
    pub fn write_text(
        &mut self,
        synapse: &mut Symbiote,
        filename: &str,
        content: &str,
    ) -> AgentResponse {
        // Create the document
        let doc = Document::new(filename, content);

        // Convert to SovereignBlob using the trait
        let blob = doc.to_blob().with_label(filename);

        // Get the size before committing
        let size = blob.size();

        // Commit through Symbiote
        match synapse.commit_organ_data(blob) {
            Ok(addr) => {
                self.recent_documents.push(addr);
                AgentResponse::DocumentSaved {
                    filename: filename.to_string(),
                    address: addr,
                    size,
                }
            }
            Err(e) => AgentResponse::Error(format!("Failed to save document: {:?}", e)),
        }
    }

    /// Write a raw document (already constructed)
    pub fn write_document(
        &mut self,
        synapse: &mut Symbiote,
        doc: Document,
    ) -> AgentResponse {
        let filename = doc.title.clone();
        let blob = doc.to_blob().with_label(&filename);
        let size = blob.size();

        match synapse.commit_organ_data(blob) {
            Ok(addr) => {
                self.recent_documents.push(addr);
                AgentResponse::DocumentSaved {
                    filename,
                    address: addr,
                    size,
                }
            }
            Err(e) => AgentResponse::Error(format!("Failed to save document: {:?}", e)),
        }
    }

    /// Read a document from storage
    ///
    /// Note: In the current Symbiote implementation, this returns an error
    /// for non-existent addresses. Full read support requires the Referee Kernel.
    pub fn read_document(&self, synapse: &Symbiote, addr: BlockAddr) -> AgentResponse {
        match synapse.read_organ_data(addr) {
            Ok(blob) => {
                // Deserialize the document from the blob payload
                match Document::from_bytes(&blob.payload) {
                    Some(doc) => AgentResponse::DocumentContent(doc),
                    None => AgentResponse::Error("Failed to deserialize document".to_string()),
                }
            }
            Err(e) => AgentResponse::Error(format!("Failed to read document: {:?}", e)),
        }
    }

    /// List recently saved documents
    pub fn list_documents(&self) -> Vec<BlockAddr> {
        self.recent_documents.clone()
    }

    /// Get the count of saved documents
    pub fn document_count(&self) -> usize {
        self.recent_documents.len()
    }

    /// Clear the recent documents list
    pub fn clear_history(&mut self) {
        self.recent_documents.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_osteon_write_text() {
        let mut synapse = Symbiote::new();
        let mut osteon = OsteonAgent::new();

        let response = osteon.write_text(
            &mut synapse,
            "hello.txt",
            "Hello Sovereign World",
        );

        match response {
            AgentResponse::DocumentSaved { filename, address, size } => {
                assert_eq!(filename, "hello.txt");
                assert!(!address.is_null());
                assert!(size > 0);
            }
            _ => panic!("Expected DocumentSaved response"),
        }

        assert_eq!(osteon.document_count(), 1);
    }

    #[test]
    fn test_osteon_multiple_documents() {
        let mut synapse = Symbiote::new();
        let mut osteon = OsteonAgent::new();

        osteon.write_text(&mut synapse, "doc1.txt", "First document");
        osteon.write_text(&mut synapse, "doc2.txt", "Second document");
        osteon.write_text(&mut synapse, "doc3.txt", "Third document");

        assert_eq!(osteon.document_count(), 3);

        let addresses = osteon.list_documents();
        assert_eq!(addresses.len(), 3);

        // Each should have a unique block offset
        assert_eq!(addresses[0].block_offset(), 0);
        assert_eq!(addresses[1].block_offset(), 1);
        assert_eq!(addresses[2].block_offset(), 2);
    }

    #[test]
    fn test_osteon_write_document() {
        let mut synapse = Symbiote::new();
        let mut osteon = OsteonAgent::new();

        let doc = Document::new("meeting_notes.txt", "Q1 Planning Meeting")
            .with_author("Team Lead")
            .with_tag("meeting")
            .with_tag("q1");

        let response = osteon.write_document(&mut synapse, doc);

        match response {
            AgentResponse::DocumentSaved { filename, .. } => {
                assert_eq!(filename, "meeting_notes.txt");
            }
            _ => panic!("Expected DocumentSaved response"),
        }
    }
}
