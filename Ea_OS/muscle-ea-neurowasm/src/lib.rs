#![cfg_attr(not(feature = "std"), no_std)]
#![forbid(unsafe_code)]
#![deny(missing_docs, clippy::all, clippy::pedantic)]
#![doc = r#"
NeuroWasmMuscle — first true hybrid organ of the Eä lineage.

Native Eä bytecode interpreter fused with living WASM organelles 
for hyper-adaptive computation. Represents the evolutionary bridge
between pure biological computing and specialized organelle execution.
"#]

extern crate alloc;

use alloc::{format, vec::Vec};
use core::cell::RefCell;
use core::marker::PhantomData;
use lru::LruCache;
use muscle_ea_core::{
    biology::*,
    error::MuscleError,
    runtime::{Muscle, MuscleContext, MuscleOutput, MuscleSuccessor, SuccessorMetadata},
};
use muscle_ea_pathfinder::PathfinderMuscle;
use rand_core::{CryptoRng, RngCore};
use sha3::{Digest, Sha3_256};
use zeroize::Zeroizing;

/// Execution modes for the NeuroWasm hybrid organ
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum NeuroMode {
    /// Pure Eä bytecode execution - baseline biological computation
    PureEä = 0,
    /// Pure WASM execution - specialized organelle function  
    PureWasm = 1,
    /// Hybrid fusion - symbiotic execution with organelle spawning
    Hybrid = 0xFF,
}

impl TryFrom<u8> for NeuroMode {
    type Error = MuscleError;

    fn try_from(value: u8) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::PureEä),
            1 => Ok(Self::PureWasm),
            0xFF => Ok(Self::Hybrid),
            _ => Err(MuscleError::Custom(format!(
                "Invalid neuro mode: {}",
                value
            ))),
        }
    }
}

/// Header for NeuroWasm hybrid blobs
#[derive(Debug, Clone)]
pub struct NeuroHeader {
    /// Execution mode for this hybrid organ
    pub mode: NeuroMode,
    /// Offset to WASM blob in hybrid mode
    pub wasm_offset: u32,
    /// Length of WASM blob in hybrid mode
    pub wasm_length: u32,
    /// Number of successor keys
    pub successor_count: u32,
    /// Total length of Eä bytecode
    pub eä_code_length: u32,
}

const NEURO_HEADER_LEN: usize = 17;

/// The first true hybrid organ — NeuroWasmMuscle v1 "Thalamus"
pub struct NeuroWasmMuscle<R: RngCore + CryptoRng = rand_core::OsRng> {
    _phantom: PhantomData<R>,
    /// Cache of interpreted Eä bytecode results (biological computation memory)
    interpretation_cache: RefCell<LruCache<[u8; 32], Vec<u8>>>,
}

impl<R: RngCore + CryptoRng> Default for NeuroWasmMuscle<R> {
    fn default() -> Self {
        Self {
            _phantom: PhantomData,
            interpretation_cache: RefCell::new(LruCache::new(64.try_into().unwrap())),
        }
    }
}

impl<R: RngCore + CryptoRng> NeuroWasmMuscle<R> {
    fn cache_mut(&self) -> core::cell::RefMut<'_, LruCache<[u8; 32], Vec<u8>>> {
        self.interpretation_cache.borrow_mut()
    }
}

impl<R: RngCore + CryptoRng> Muscle for NeuroWasmMuscle<R> {
    type PrivateInput = Vec<u8>;
    type PrivateOutput = Vec<u8>;

    fn execute(
        &self,
        ctx: &mut MuscleContext<impl RngCore + CryptoRng>,
        private_input: Self::PrivateInput,
    ) -> Result<MuscleOutput<Self::PrivateOutput>, MuscleError> {
        let blob = ctx.current_blob().clone();
        let header = parse_neurowasm_header(&blob.payload)?;

        match header.mode {
            NeuroMode::PureEä => {
                self.execute_native_eä(&blob.payload, &private_input, ctx, &header)
            }
            NeuroMode::PureWasm => {
                self.delegate_to_pathfinder(&blob.payload, &private_input, ctx, &header, &blob.salt)
            }
            NeuroMode::Hybrid => {
                self.execute_hybrid_fusion(&blob.payload, &private_input, ctx, &header)
            }
        }
    }
}

/// Core innovation: symbiotic execution where Eä bytecode can spawn living WASM organelles on-demand
impl<R: RngCore + CryptoRng> NeuroWasmMuscle<R> {
    fn execute_native_eä<Rng: RngCore + CryptoRng>(
        &self,
        sealed: &[u8],
        input: &[u8],
        ctx: &mut MuscleContext<Rng>,
        header: &NeuroHeader,
    ) -> Result<MuscleOutput<Vec<u8>>, MuscleError> {
        // Pure Eä bytecode interpretation - baseline biological computation
        let eä_code = &sealed[NEURO_HEADER_LEN..][..header.eä_code_length as usize];

        // Check cache first (biological short-term memory)
        let code_hash: [u8; 32] = Sha3_256::digest(eä_code).into();
        if let Some(cached) = self.cache_mut().get(&code_hash) {
            return Ok(MuscleOutput {
                output: cached.clone(),
                successors: Vec::new(),
            });
        }

        // Interpret Eä bytecode safely
        let result = interpret_eä_bytecode(eä_code, input, ctx)?;

        // Cache the result (biological learning)
        self.cache_mut().put(code_hash, result.output.clone());

        Ok(result)
    }

    fn delegate_to_pathfinder<Rng: RngCore + CryptoRng>(
        &self,
        sealed: &[u8],
        input: &[u8],
        ctx: &mut MuscleContext<Rng>,
        header: &NeuroHeader,
        salt: &MuscleSalt,
    ) -> Result<MuscleOutput<Vec<u8>>, MuscleError> {
        // Pure WASM execution via pathfinder muscle (specialized organelle)
        let pathfinder = PathfinderMuscle::<Rng>::default();
        let master_key = *ctx.master_key();

        // Create a synthetic blob for pathfinder execution
        let wasm_blob = SealedBlob::new(
            sealed[header.wasm_offset as usize..][..header.wasm_length as usize].to_vec(),
            salt.clone(),
            3, // Pathfinder version
        );

        let rng = ctx.rng();
        let mut pathfinder_ctx = MuscleContext::new(wasm_blob, master_key, rng);

        pathfinder.execute(&mut pathfinder_ctx, input.to_vec())
    }

    fn execute_hybrid_fusion<Rng: RngCore + CryptoRng>(
        &self,
        sealed: &[u8],
        input: &[u8],
        ctx: &mut MuscleContext<Rng>,
        header: &NeuroHeader,
    ) -> Result<MuscleOutput<Vec<u8>>, MuscleError> {
        // Hybrid symbiotic execution: Eä bytecode + WASM organelles
        let eä_code = &sealed[NEURO_HEADER_LEN..][..header.eä_code_length as usize];
        let wasm_blob = &sealed[header.wasm_offset as usize..][..header.wasm_length as usize];

        // Create hybrid virtual machine for symbiotic execution
        let mut hybrid_vm = HybridVm::new(wasm_blob.to_vec(), input.to_vec(), ctx)?;

        // Interpret Eä bytecode with organelle extension capability
        self.interpret_eä_with_organelles(eä_code, &mut hybrid_vm)?;

        Ok(hybrid_vm.into_result())
    }

    fn interpret_eä_with_organelles<Rng: RngCore + CryptoRng>(
        &self,
        code: &[u8],
        vm: &mut HybridVm<'_, Rng>,
    ) -> Result<(), MuscleError> {
        // Safe interpretation of Eä bytecode with organelle spawning
        let mut pc = 0;
        let mut stack: Vec<u8> = Vec::new();

        while pc < code.len() {
            let opcode = code[pc];
            pc += 1;

            match opcode {
                // Standard Eä operations (0x00-0xFE)
                0x00..=0xFE => {
                    self.execute_standard_eä_op(opcode, &mut stack)?;
                }
                // Organelle spawn operation (0xFF)
                0xFF => {
                    vm.spawn_wasm_organelle()?;
                }
            }
        }

        Ok(())
    }

    fn execute_standard_eä_op(
        &self,
        opcode: u8,
        stack: &mut Vec<u8>,
    ) -> Result<(), MuscleError> {
        // Simplified Eä bytecode interpreter for demonstration
        match opcode {
            // Push operations
            0x01..=0x7F => {
                stack.push(opcode);
            }
            // Arithmetic operations
            0x80..=0x8F => {
                if stack.len() < 2 {
                    return Err(MuscleError::Custom("stack underflow".to_string()));
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                let result = match opcode {
                    0x80 => a.wrapping_add(b),
                    0x81 => a.wrapping_sub(b),
                    0x82 => a.wrapping_mul(b),
                    _ => return Err(MuscleError::MalformedOrganelle),
                };
                stack.push(result);
            }
            _ => return Err(MuscleError::MalformedOrganelle),
        }
        Ok(())
    }
}

/// Living bridge between Eä VM and WASM organelles - enables symbiotic execution
struct HybridVm<'a, R: RngCore + CryptoRng> {
    input: Vec<u8>,
    output: Zeroizing<Vec<u8>>,
    successors: Vec<MuscleSuccessor>,
    wasm_blob: Vec<u8>,
    rng: &'a mut R,
    _pathfinder_muscle: PathfinderMuscle<R>,
}

impl<'a, R: RngCore + CryptoRng> HybridVm<'a, R> {
    fn new(
        wasm_blob: Vec<u8>,
        input: Vec<u8>,
        ctx: &'a mut MuscleContext<R>,
    ) -> Result<Self, MuscleError> {
        Ok(Self {
            input,
            output: Zeroizing::new(Vec::new()),
            successors: Vec::new(),
            wasm_blob,
            rng: ctx.rng(),
            _pathfinder_muscle: PathfinderMuscle::default(),
        })
    }

    fn spawn_wasm_organelle(&mut self) -> Result<(), MuscleError> {
        // Spawn WASM organelle using the pathfinder muscle
        // In full implementation, this would use a proper MuscleContext
        // For now, demonstrate the biological concept

        // Simulate organelle execution by processing input through WASM logic
        let simulated_output = self.process_through_wasm_organelle(&self.input)?;
        self.output.extend_from_slice(&simulated_output);

        // Create successor representing the evolved organelle
        let successor = MuscleSuccessor {
            blob: SealedBlob::new(
                self.wasm_blob.clone(),
                MuscleSalt::random(self.rng),
                3,
            ),
            metadata: SuccessorMetadata::new(3, "evolved_organelle".to_string())
                .with_property("evolution".to_string(), "symbiotic_fusion".to_string()),
        };

        self.successors.push(successor);
        Ok(())
    }

    fn process_through_wasm_organelle(&self, input: &[u8]) -> Result<Vec<u8>, MuscleError> {
        // Simplified WASM organelle processing
        // In full implementation, this would execute actual WASM
        let mut output = Vec::with_capacity(input.len());
        for &byte in input {
            output.push(byte.wrapping_add(1)); // Simple transformation
        }
        Ok(output)
    }

    fn into_result(self) -> MuscleOutput<Vec<u8>> {
        MuscleOutput {
            output: self.output.to_vec(),
            successors: self.successors,
        }
    }
}

/// Parse NeuroWasm hybrid blob header
fn parse_neurowasm_header(sealed: &[u8]) -> Result<NeuroHeader, MuscleError> {
    if sealed.len() < NEURO_HEADER_LEN {
        return Err(MuscleError::InvalidBlob);
    }

    let mode = NeuroMode::try_from(sealed[0])?;

    // Parse header fields from sealed blob
    let wasm_offset = u32::from_le_bytes(sealed[1..5].try_into().unwrap());
    let wasm_length = u32::from_le_bytes(sealed[5..9].try_into().unwrap());
    let successor_count = u32::from_le_bytes(sealed[9..13].try_into().unwrap());
    let eä_code_length = u32::from_le_bytes(sealed[13..17].try_into().unwrap());

    Ok(NeuroHeader {
        mode,
        wasm_offset,
        wasm_length,
        successor_count,
        eä_code_length,
    })
}

/// Safe interpretation of Eä bytecode
fn interpret_eä_bytecode(
    code: &[u8],
    input: &[u8],
    _ctx: &mut MuscleContext<impl RngCore + CryptoRng>,
) -> Result<MuscleOutput<Vec<u8>>, MuscleError> {
    // Simplified bytecode interpreter for demonstration
    let mut output = Vec::new();
    let mut stack: Vec<u8> = Vec::new();

    for &opcode in code {
        match opcode {
            // Push input bytes
            0x10..=0x1F => {
                let idx = (opcode - 0x10) as usize;
                if idx < input.len() {
                    stack.push(input[idx]);
                }
            }
            // Output operations
            0x20..=0x2F => {
                if let Some(value) = stack.pop() {
                    output.push(value);
                }
            }
            // Basic arithmetic
            0x30..=0x3F => {
                if stack.len() >= 2 {
                    let b = stack.pop().unwrap();
                    let a = stack.pop().unwrap();
                    let result = a.wrapping_add(b); // Simplified
                    stack.push(result);
                }
            }
            _ => {} // Ignore unknown opcodes for demo
        }
    }

    Ok(MuscleOutput {
        output,
        successors: Vec::new(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand_core::OsRng;

    #[test]
    fn test_neuro_mode_conversion() {
        assert_eq!(NeuroMode::try_from(0).unwrap(), NeuroMode::PureEä);
        assert_eq!(NeuroMode::try_from(1).unwrap(), NeuroMode::PureWasm);
        assert_eq!(NeuroMode::try_from(0xFF).unwrap(), NeuroMode::Hybrid);
        assert!(NeuroMode::try_from(2).is_err());
    }

    #[test]
    fn test_neurowasm_muscle_creation() {
        let muscle = NeuroWasmMuscle::<OsRng>::default();
        // Should compile and create without unsafe code
        assert!(core::mem::size_of_val(&muscle) > 0);
    }

    #[test]
    fn test_header_parsing() {
        let mut header_data = vec![0u8; 17]; // NeuroMode::PureEä
        header_data[0] = 0; // PureEä mode
        header_data[1..5].copy_from_slice(&100u32.to_le_bytes()); // wasm_offset
        header_data[5..9].copy_from_slice(&200u32.to_le_bytes()); // wasm_length
        header_data[9..13].copy_from_slice(&2u32.to_le_bytes()); // successor_count
        header_data[13..17].copy_from_slice(&300u32.to_le_bytes()); // eä_code_length

        let header = parse_neurowasm_header(&header_data).unwrap();
        assert_eq!(header.mode, NeuroMode::PureEä);
        assert_eq!(header.wasm_offset, 100);
        assert_eq!(header.wasm_length, 200);
        assert_eq!(header.successor_count, 2);
        assert_eq!(header.eä_code_length, 300);
    }

    #[test]
    fn test_hybrid_vm_organelle_spawning() {
        let wasm_blob = vec![0x01, 0x02, 0x03];
        let input = vec![0x10, 0x20, 0x30];

        let mut ctx = MuscleContext::new(
            SealedBlob::new(vec![], MuscleSalt::new([0; 16]), 1),
            [0; 32],
            OsRng,
        );
        let mut vm = HybridVm::new(wasm_blob, input, &mut ctx).unwrap();

        vm.spawn_wasm_organelle().unwrap();
        let result = vm.into_result();

        assert!(!result.output.is_empty());
        assert_eq!(result.successors.len(), 1);
        assert_eq!(
            result.successors[0].metadata.muscle_type,
            "evolved_organelle"
        );
    }
}
