#![no_std]
#![cfg_attr(feature = "uefi", crate_type = "cdylib")]

extern crate alloc;

pub mod errors;
pub mod muscle_loader;
pub mod uart;
