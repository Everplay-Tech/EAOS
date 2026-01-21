//! PermFS Bridge Interface
//!
//! This module provides the interface to the permfs-bridge crate,
//! enabling the referee-kernel to perform storage operations through the
//! PermFS layer with T9-Braid compression.

use uefi::table::boot::BootServices;
use permfs_bridge::{PermFsBridge, BridgeResult, SyscallBlockAddr};
use crate::storage::UefiBlockDevice;

/// Global bridge instance
static mut BRIDGE: Option<PermFsBridge<UefiBlockDevice>> = None;

/// Initialize the global bridge.
pub fn init_bridge(bt: &BootServices, node_id: u64, volume_id: u32) -> bool {
    if let Some(device) = UefiBlockDevice::new(bt) {
        unsafe {
            BRIDGE = Some(PermFsBridge::new(device, node_id, volume_id));
        }
        true
    } else {
        false
    }
}

/// Check if bridge is initialized.
pub fn bridge_ready() -> bool {
    unsafe { BRIDGE.is_some() }
}

/// Read a block through the bridge.
///
/// # Safety
/// Buffer must point to at least 4096 bytes of valid memory.
pub unsafe fn read_block(addr_high: u128, addr_low: u128, buffer: *mut u8) -> BridgeResult {
    if let Some(bridge) = BRIDGE.as_ref() {
        let addr = SyscallBlockAddr { high: addr_high, low: addr_low };
        bridge.handle_read(addr, buffer)
    } else {
        BridgeResult::IoError
    }
}

/// Write a block through the bridge.
///
/// # Safety
/// Buffer must point to at least 4096 bytes of valid memory.
pub unsafe fn write_block(addr_high: u128, addr_low: u128, buffer: *const u8) -> BridgeResult {
    if let Some(bridge) = BRIDGE.as_ref() {
        let addr = SyscallBlockAddr { high: addr_high, low: addr_low };
        bridge.handle_write(addr, buffer)
    } else {
        BridgeResult::IoError
    }
}

/// Shutdown the bridge.
pub fn shutdown_bridge() {
    unsafe {
        // Sync before shutdown
        if let Some(bridge) = BRIDGE.as_ref() {
            let _ = bridge.sync();
        }
        BRIDGE = None;
    }
}
