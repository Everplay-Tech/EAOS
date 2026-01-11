// muscle-compiler/src/parser.rs
// Eä Weight Parser v6.0 — Robust Python weight extraction

use crate::ast::MuscleAst;
use once_cell::sync::Lazy;
use regex::Regex;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ParseError {
    #[error("Weight vector W not found")]
    WNotFound,
    #[error("Bias scalar b not found")]
    BNotFound,
    #[error("Invalid float value: {0}")]
    InvalidFloat(String),
    #[error("Invalid matrix dimensions: expected {expected}, found {found}")]
    InvalidDimensions { expected: usize, found: usize },
}

/// Neural network weights structure
#[derive(Debug, Clone, PartialEq)]
pub struct Weights {
    pub w: [f32; 4], // 4-element weight vector
    pub b: f32,      // output bias
}

impl Weights {
    /// Count the total number of learned floats stored in this structure
    pub fn len(&self) -> usize {
        self.w.len() + 1
    }
}

/// Python AST wrapper that exposes metadata and the parsed weights
pub struct PythonAst {
    pub muscle_ast: MuscleAst,
    pub weights: Weights,
}

impl PythonAst {
    pub fn metadata(&self) -> &std::collections::HashMap<String, String> {
        &self.muscle_ast.metadata
    }
}

/// Simple parser for Python-defined muscles
pub struct PythonParser;

impl PythonParser {
    pub fn parse(source: &str) -> Result<PythonAst, ParseError> {
        let weights = extract_weights(source)?;
        let mut muscle_ast = MuscleAst::new("py".to_string());
        muscle_ast.set_metadata("layers".to_string(), "python".to_string());
        Ok(PythonAst {
            muscle_ast,
            weights,
        })
    }
}

// Regex patterns for parsing Python numpy arrays
static RE_W: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"W\s*=\s*np\.array\s*\(\s*\[\s*([^\]]+)\s*\]\s*\)",
    )
    .unwrap()
});

static RE_B: Lazy<Regex> = Lazy::new(|| Regex::new(r"b\s*=\s*([\d\.\-e]+)").unwrap());

/// Parse a single f32 value from string
fn parse_float(s: &str) -> Result<f32, ParseError> {
    s.trim()
        .parse()
        .map_err(|_| ParseError::InvalidFloat(s.to_string()))
}

/// Parse a row of 3 f32 values
fn parse_vector_4(row_str: &str) -> Result<[f32; 4], ParseError> {
    let parts: Vec<&str> = row_str.split(',').map(|s| s.trim()).collect();
    if parts.len() != 4 {
        return Err(ParseError::InvalidDimensions {
            expected: 4,
            found: parts.len(),
        });
    }

    Ok([
        parse_float(parts[0])?,
        parse_float(parts[1])?,
        parse_float(parts[2])?,
        parse_float(parts[3])?,
    ])
}

/// Extract weights from Python source code
pub fn extract_weights(source: &str) -> Result<Weights, ParseError> {
    // Extract W (4-element vector)
    let w_caps = RE_W.captures(source).ok_or(ParseError::WNotFound)?;
    let w = parse_vector_4(w_caps.get(1).unwrap().as_str())?;

    // Extract b (scalar)
    let b = RE_B
        .captures(source)
        .and_then(|caps| parse_float(caps.get(1).unwrap().as_str()).ok())
        .ok_or(ParseError::BNotFound)?;

    Ok(Weights { w, b })
}

#[cfg(test)]
mod tests {
    use super::*;

    const TEST_SOURCE: &str = r#"
import numpy as np

# Neural network weights for family muscle
W = np.array([0.1, 0.2, 0.3, 0.4])

b = 0.7
"#;

    #[test]
    fn test_extract_weights() {
        let weights = extract_weights(TEST_SOURCE).unwrap();

        assert_eq!(weights.w, [0.1, 0.2, 0.3, 0.4]);
        assert_eq!(weights.b, 0.7);
    }

    #[test]
    fn test_missing_components() {
        let incomplete_source = "W = np.array([0.1, 0.2, 0.3, 0.4])";
        assert!(extract_weights(incomplete_source).is_err());
    }

    #[test]
    fn test_invalid_floats() {
        let bad_source = r#"
W = np.array([0.1, 0.2, invalid, 0.4])
b = 0.7
"#;
        assert!(extract_weights(bad_source).is_err());
    }
}
