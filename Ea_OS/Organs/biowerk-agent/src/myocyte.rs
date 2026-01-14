//! Myocyte Agent - Logic Processor for BIOwerk Office Suite
//!
//! Named after muscle cells, Myocyte provides the computational power
//! for EAOS. It handles:
//!
//! - Processing formulas and expressions
//! - Compiling logic to bytecode (via Quenyan when available)
//! - Storing logic units as SovereignBlob containers
//! - Executing simple computations

use ea_symbiote::{BlockAddr, SovereignDocument, Symbiote};

use crate::{AgentResponse, LogicUnit};

/// Myocyte Agent: The Logic Processor
///
/// Handles formula processing, compilation, and logic storage.
pub struct MyocyteAgent {
    /// Track of recently processed logic addresses
    recent_logic: Vec<BlockAddr>,
}

impl Default for MyocyteAgent {
    fn default() -> Self {
        Self::new()
    }
}

impl MyocyteAgent {
    /// Create a new Myocyte agent
    pub fn new() -> Self {
        Self {
            recent_logic: Vec::new(),
        }
    }

    /// Process a logic formula
    ///
    /// This function:
    /// 1. Creates a LogicUnit with the formula
    /// 2. Compiles the formula to bytecode (simplified for now)
    /// 3. Wraps it in a SovereignBlob of type Logic
    /// 4. Sends it to Symbiote for storage
    ///
    /// # Arguments
    /// * `synapse` - The Symbiote IPC layer
    /// * `name` - The logic unit name/label
    /// * `formula` - The formula or expression to process
    ///
    /// # Returns
    /// An AgentResponse indicating success or failure
    pub fn process_logic(
        &mut self,
        synapse: &mut Symbiote,
        name: &str,
        formula: &str,
    ) -> AgentResponse {
        // Compile the formula to bytecode
        // In a full implementation, this would use the Quenyan compiler
        let bytecode = self.compile_formula(formula);
        let bytecode_size = bytecode.len();

        // Create the logic unit with compiled bytecode
        let logic = LogicUnit::new(name, formula).with_bytecode(bytecode);

        // Convert to SovereignBlob
        let blob = logic.to_blob().with_label(name);

        // Commit through Symbiote
        match synapse.commit_organ_data(blob) {
            Ok(addr) => {
                self.recent_logic.push(addr);
                AgentResponse::LogicProcessed {
                    name: name.to_string(),
                    address: addr,
                    bytecode_size,
                }
            }
            Err(e) => AgentResponse::Error(format!("Failed to process logic: {:?}", e)),
        }
    }

    /// Compile a formula to bytecode
    ///
    /// This is a simplified compiler that generates a basic bytecode representation.
    /// In the full implementation, this would use the Quenyan compiler with
    /// the --emit-sovereign flag to produce proper morpheme-compressed bytecode.
    fn compile_formula(&self, formula: &str) -> Vec<u8> {
        // Simple bytecode format:
        // [0x4C, 0x4F, 0x47, 0x49, 0x43] = "LOGIC" magic
        // [len_hi, len_lo] = formula length
        // [formula bytes...]
        // [checksum]

        let mut bytecode = Vec::new();

        // Magic header
        bytecode.extend_from_slice(b"LOGIC");

        // Formula length (2 bytes, big-endian)
        let len = formula.len() as u16;
        bytecode.push((len >> 8) as u8);
        bytecode.push(len as u8);

        // Formula bytes
        bytecode.extend_from_slice(formula.as_bytes());

        // Simple checksum (sum of all bytes mod 256)
        let checksum: u8 = bytecode.iter().fold(0u8, |acc, &b| acc.wrapping_add(b));
        bytecode.push(checksum);

        bytecode
    }

    /// Execute a simple arithmetic formula
    ///
    /// Supports basic operations: +, -, *, /
    /// Returns the result as a string, or an error message.
    pub fn evaluate_simple(&self, formula: &str) -> Result<f64, String> {
        // Very basic expression evaluator for simple arithmetic
        let formula = formula.trim();

        // Try to parse as a single number first
        if let Ok(n) = formula.parse::<f64>() {
            return Ok(n);
        }

        // Look for operators (left to right, no precedence)
        for op in ['+', '-', '*', '/'] {
            if let Some(pos) = formula.rfind(op) {
                if pos > 0 {
                    let left = &formula[..pos].trim();
                    let right = &formula[pos + 1..].trim();

                    let left_val = self.evaluate_simple(left)?;
                    let right_val = self.evaluate_simple(right)?;

                    return match op {
                        '+' => Ok(left_val + right_val),
                        '-' => Ok(left_val - right_val),
                        '*' => Ok(left_val * right_val),
                        '/' => {
                            if right_val == 0.0 {
                                Err("Division by zero".to_string())
                            } else {
                                Ok(left_val / right_val)
                            }
                        }
                        _ => unreachable!(),
                    };
                }
            }
        }

        Err(format!("Cannot parse expression: {}", formula))
    }

    /// Process and evaluate a formula, storing both formula and result
    pub fn process_and_evaluate(
        &mut self,
        synapse: &mut Symbiote,
        name: &str,
        formula: &str,
    ) -> AgentResponse {
        // Try to evaluate the formula
        let result = match self.evaluate_simple(formula) {
            Ok(val) => format!("{}", val),
            Err(e) => format!("Error: {}", e),
        };

        // Compile the formula
        let bytecode = self.compile_formula(formula);
        let bytecode_size = bytecode.len();

        // Create logic unit with result
        let logic = LogicUnit::new(name, formula)
            .with_bytecode(bytecode)
            .with_result(&result);

        // Convert to SovereignBlob
        let blob = logic.to_blob().with_label(name);

        // Commit through Symbiote
        match synapse.commit_organ_data(blob) {
            Ok(addr) => {
                self.recent_logic.push(addr);
                AgentResponse::LogicProcessed {
                    name: name.to_string(),
                    address: addr,
                    bytecode_size,
                }
            }
            Err(e) => AgentResponse::Error(format!("Failed to process logic: {:?}", e)),
        }
    }

    /// List recently processed logic units
    pub fn list_logic(&self) -> Vec<BlockAddr> {
        self.recent_logic.clone()
    }

    /// Get the count of processed logic units
    pub fn logic_count(&self) -> usize {
        self.recent_logic.len()
    }

    /// Clear the recent logic list
    pub fn clear_history(&mut self) {
        self.recent_logic.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_myocyte_process_logic() {
        let mut synapse = Symbiote::new();
        let mut myocyte = MyocyteAgent::new();

        let response = myocyte.process_logic(
            &mut synapse,
            "budget.qyn",
            "revenue - expenses",
        );

        match response {
            AgentResponse::LogicProcessed { name, address, bytecode_size } => {
                assert_eq!(name, "budget.qyn");
                assert!(!address.is_null());
                assert!(bytecode_size > 0);
            }
            _ => panic!("Expected LogicProcessed response"),
        }

        assert_eq!(myocyte.logic_count(), 1);
    }

    #[test]
    fn test_myocyte_compile_formula() {
        let myocyte = MyocyteAgent::new();

        let bytecode = myocyte.compile_formula("2 + 2");

        // Should have LOGIC header
        assert_eq!(&bytecode[0..5], b"LOGIC");

        // Length should be 5 (for "2 + 2")
        let len = ((bytecode[5] as u16) << 8) | (bytecode[6] as u16);
        assert_eq!(len, 5);

        // Formula should be present
        assert_eq!(&bytecode[7..12], b"2 + 2");
    }

    #[test]
    fn test_myocyte_evaluate_simple() {
        let myocyte = MyocyteAgent::new();

        assert_eq!(myocyte.evaluate_simple("2 + 2").unwrap(), 4.0);
        assert_eq!(myocyte.evaluate_simple("10 - 3").unwrap(), 7.0);
        assert_eq!(myocyte.evaluate_simple("6 * 7").unwrap(), 42.0);
        assert_eq!(myocyte.evaluate_simple("100 / 4").unwrap(), 25.0);

        // Division by zero
        assert!(myocyte.evaluate_simple("5 / 0").is_err());
    }

    #[test]
    fn test_myocyte_multiple_logic() {
        let mut synapse = Symbiote::new();
        let mut myocyte = MyocyteAgent::new();

        myocyte.process_logic(&mut synapse, "calc1.qyn", "1 + 1");
        myocyte.process_logic(&mut synapse, "calc2.qyn", "2 * 3");
        myocyte.process_logic(&mut synapse, "calc3.qyn", "10 / 2");

        assert_eq!(myocyte.logic_count(), 3);

        let addresses = myocyte.list_logic();
        assert_eq!(addresses.len(), 3);
    }

    #[test]
    fn test_myocyte_process_and_evaluate() {
        let mut synapse = Symbiote::new();
        let mut myocyte = MyocyteAgent::new();

        let response = myocyte.process_and_evaluate(
            &mut synapse,
            "simple_calc.qyn",
            "2 + 2",
        );

        match response {
            AgentResponse::LogicProcessed { name, .. } => {
                assert_eq!(name, "simple_calc.qyn");
            }
            _ => panic!("Expected LogicProcessed response"),
        }
    }
}
