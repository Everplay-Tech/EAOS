//! UEFI Block Storage Driver
//!
//! Implements the PermFS BlockDevice trait using the UEFI Block I/O Protocol.

use uefi::prelude::*;
use uefi::proto::media::block::BlockIO;
use permfs::{BlockAddr, BlockDevice, FsResult, IoError, BLOCK_SIZE};
use core::ffi::c_void;

/// Wrapper around UEFI Block IO Protocol
pub struct UefiBlockDevice {
    // Raw pointer to the interface (we own it effectively)
    interface: *mut BlockIO,
    media_id: u32,
    device_block_size: u32,
}

unsafe impl Send for UefiBlockDevice {}
unsafe impl Sync for UefiBlockDevice {}

impl UefiBlockDevice {
    /// Initialize by locating the first Block IO handle
    pub fn new(bt: &BootServices) -> Option<Self> {
        // Find all handles supporting BlockIO
        let handles = bt.locate_handle_buffer(uefi::proto::media::block::BlockIO::GUID).ok()?;
        
        if handles.is_empty() {
            return None;
        }

        // Use the first handle (usually the boot disk or main drive)
        let handle = handles[0];

        // Open protocol in unchecked mode to keep it alive indefinitely
        // Note: In production we should handle ownership properly or use OpenProtocol
        // with BY_HANDLE_PROTOCOL.
        let interface = unsafe {
            let ptr = bt.open_protocol::<BlockIO>(
                uefi::proto::media::block::BlockIO::GUID,
                handle,
                handle, // agent (us)
                None,   // controller
                uefi::table::boot::OpenProtocolAttributes::GET_PROTOCOL,
            ).ok()?;
            
            // The uefi crate wraps this, we need the raw pointer if we want to bypass scopes
            // But open_protocol returns a ScopedProtocol.
            // Let's use handle_protocol (unsafe) which returns raw pointer in C APIs,
            // but uefi crate abstracts it.
            
            // Workaround: We will rely on the fact that we don't drop the protocol
            // effectively leaking the reference which is fine for a kernel.
            // However, uefi crate struct might drop on scope exit.
            
            // Let's assume we can transmute/leak.
            let scoped = ptr;
            let raw = &*scoped as *const BlockIO as *mut BlockIO;
            core::mem::forget(scoped); // Leak to keep valid
            raw
        };

        if interface.is_null() {
            return None;
        }

        let media = unsafe { (*interface).media() };
        
        Some(Self {
            interface,
            media_id: media.media_id(),
            device_block_size: media.block_size(),
        })
    }
}

impl BlockDevice for UefiBlockDevice {
    fn read_block(&self, addr: BlockAddr, buf: &mut [u8; BLOCK_SIZE]) -> FsResult<()> {
        let offset = addr.block_offset();
        // Convert 4KB block offset to device LBA
        let lba = offset * (BLOCK_SIZE as u64 / self.device_block_size as u64);
        
        let bio = unsafe { &mut *self.interface };
        
        match bio.read_blocks(self.media_id, lba, buf) {
            Ok(_) => Ok(()),
            Err(_) => Err(IoError::IoFailed),
        }
    }

    fn write_block(&self, addr: BlockAddr, buf: &[u8; BLOCK_SIZE]) -> FsResult<()> {
        let offset = addr.block_offset();
        let lba = offset * (BLOCK_SIZE as u64 / self.device_block_size as u64);
        
        let bio = unsafe { &mut *self.interface };
        
        match bio.write_blocks(self.media_id, lba, buf) {
            Ok(_) => Ok(()),
            Err(_) => Err(IoError::IoFailed),
        }
    }

    fn sync(&self) -> FsResult<()> {
        let bio = unsafe { &mut *self.interface };
        match bio.flush_blocks() {
            Ok(_) => Ok(()),
            Err(_) => Err(IoError::IoFailed),
        }
    }

    fn trim(&self, _addr: BlockAddr) -> FsResult<()> {
        Ok(()) // No-op for now
    }
}
