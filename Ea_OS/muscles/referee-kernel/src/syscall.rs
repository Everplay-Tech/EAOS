//! System call interface for EAOS Referee Kernel.
//!
//! This module defines the syscall ABI used to communicate between
//! user-space muscles and the kernel. The 256-bit BlockAddr from PermFS
//! is preserved across all syscall boundaries.

use core::sync::atomic::{AtomicU64, Ordering};
use crate::bridge;

/// 256-bit block address matching PermFS layout.
/// Structure: [node_id: 64][volume_id: 32][shard_id: 16][block_offset: 48 + reserved: 96]
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BlockAddr {
    /// High 128 bits: node_id (64) + volume_id (32) + shard_id (16) + flags (16)
    pub high: u128,
    /// Low 128 bits: block_offset (48) + reserved (80)
    pub low: u128,
}

impl BlockAddr {
    pub const fn new(node_id: u64, volume_id: u32, shard_id: u16, block_offset: u64) -> Self {
        let high = ((node_id as u128) << 64)
            | ((volume_id as u128) << 32)
            | ((shard_id as u128) << 16);
        let low = (block_offset as u128) << 80;
        Self { high, low }
    }

    pub const fn node_id(&self) -> u64 {
        (self.high >> 64) as u64
    }

    pub const fn volume_id(&self) -> u32 {
        ((self.high >> 32) & 0xFFFF_FFFF) as u32
    }

    pub const fn shard_id(&self) -> u16 {
        ((self.high >> 16) & 0xFFFF) as u16
    }

    pub const fn block_offset(&self) -> u64 {
        (self.low >> 80) as u64
    }
}

use muscle_contract::abi::SynapticVesicle;

// ...

/// System call numbers for EAOS kernel interface.
#[repr(u64)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SyscallNumber {
    /// Read a 4KB block from storage
    ReadBlock = 0,
    /// Write a 4KB block to storage
    WriteBlock = 1,
    /// Spawn a new task/muscle
    SpawnTask = 2,
    /// Yield CPU to scheduler
    Yield = 3,
    /// Exit current task
    Exit = 4,
    /// Allocate memory pages
    AllocPages = 5,
    /// Free memory pages
    FreePages = 6,
    /// Get system time (TSC-based)
    GetTime = 7,
    /// Log message to audit trail
    AuditLog = 8,
    /// Submit network request (Hive Mind)
    SubmitRequest = 9,
    /// Poll network input (Arachnid)
    PollNetwork = 10,
    /// Read system statistics (Antibody)
    ReadStats = 11,
}

impl SyscallNumber {
    pub fn from_u64(n: u64) -> Option<Self> {
        match n {
            0 => Some(Self::ReadBlock),
            1 => Some(Self::WriteBlock),
            2 => Some(Self::SpawnTask),
            3 => Some(Self::Yield),
            4 => Some(Self::Exit),
            5 => Some(Self::AllocPages),
            6 => Some(Self::FreePages),
            7 => Some(Self::GetTime),
            8 => Some(Self::AuditLog),
            9 => Some(Self::SubmitRequest),
            10 => Some(Self::PollNetwork),
            11 => Some(Self::ReadStats),
            _ => None,
        }
    }
}

/// Syscall result codes.
#[repr(i64)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SyscallResult {
    Success = 0,
    InvalidSyscall = -1,
    InvalidAddress = -2,
    IoError = -3,
    PermissionDenied = -4,
    OutOfMemory = -5,
    InvalidBuffer = -6,
    TaskNotFound = -7,
}

/// 4KB block buffer for I/O operations.
pub const BLOCK_SIZE: usize = 4096;

/// Syscall statistics for monitoring.
pub struct SyscallStats {
    pub total_calls: AtomicU64,
    pub read_calls: AtomicU64,
    pub write_calls: AtomicU64,
    pub spawn_calls: AtomicU64,
}

impl SyscallStats {
    pub const fn new() -> Self {
        Self {
            total_calls: AtomicU64::new(0),
            read_calls: AtomicU64::new(0),
            write_calls: AtomicU64::new(0),
            spawn_calls: AtomicU64::new(0),
        }
    }

    pub fn record_call(&self, syscall: SyscallNumber) {
        self.total_calls.fetch_add(1, Ordering::Relaxed);
        match syscall {
            SyscallNumber::ReadBlock => self.read_calls.fetch_add(1, Ordering::Relaxed),
            SyscallNumber::WriteBlock => self.write_calls.fetch_add(1, Ordering::Relaxed),
            SyscallNumber::SpawnTask => self.spawn_calls.fetch_add(1, Ordering::Relaxed),
            _ => 0,
        };
    }
}

/// Global syscall statistics.
pub static SYSCALL_STATS: SyscallStats = SyscallStats::new();

/// Syscall handler trait - implemented by the kernel to process syscalls.
pub trait SyscallHandler {
    /// Handle a ReadBlock syscall.
    fn read_block(&self, addr: BlockAddr, buffer: *mut u8) -> SyscallResult;

    /// Handle a WriteBlock syscall.
    fn write_block(&self, addr: BlockAddr, buffer: *const u8) -> SyscallResult;

    /// Handle a SpawnTask syscall.
    fn spawn_task(&self, task_id: u64, entry_point: u64) -> SyscallResult;
}

/// Syscall entry point (called from interrupt/trap handler).
/// 
/// ABI: x86_64 syscall convention
/// - rax: syscall number
/// - rdi: arg1 (BlockAddr high for I/O)
/// - rsi: arg2 (BlockAddr low for I/O)
/// - rdx: arg3 (buffer pointer for I/O)
/// - r10: arg4
/// - r8:  arg5
/// - r9:  arg6
/// 
/// Returns result in rax.
#[cfg(target_arch = "x86_64")]
pub fn syscall_dispatch(
    syscall_num: u64,
    arg1: u64,
    arg2: u64,
    arg3: u64,
    _arg4: u64,
    _arg5: u64,
) -> i64 {
    let syscall = match SyscallNumber::from_u64(syscall_num) {
        Some(s) => s,
        None => return SyscallResult::InvalidSyscall as i64,
    };

    SYSCALL_STATS.record_call(syscall);

    match syscall {
        SyscallNumber::ReadBlock => {
            // Construct 256-bit address from syscall arguments
            // arg1 = high 64 bits, arg2 = next 64 bits, arg3 = buffer
            let addr_high = ((arg1 as u128) << 64) | (arg2 as u128);
            let addr_low = 0u128; // Reserved for future expansion
            let buffer = arg3 as *mut u8;

            if buffer.is_null() {
                return SyscallResult::InvalidBuffer as i64;
            }

            // Dispatch to PermFS bridge with braid decompression
            let result = unsafe { bridge::read_block(addr_high, addr_low, buffer) };
            match result {
                bridge::BridgeResult::Success => SyscallResult::Success as i64,
                bridge::BridgeResult::InvalidAddress => SyscallResult::InvalidAddress as i64,
                bridge::BridgeResult::IoError => SyscallResult::IoError as i64,
                bridge::BridgeResult::InvalidBuffer => SyscallResult::InvalidBuffer as i64,
                _ => SyscallResult::IoError as i64,
            }
        }
        SyscallNumber::WriteBlock => {
            // Construct 256-bit address from syscall arguments
            let addr_high = ((arg1 as u128) << 64) | (arg2 as u128);
            let addr_low = 0u128;
            let buffer = arg3 as *const u8;

            if buffer.is_null() {
                return SyscallResult::InvalidBuffer as i64;
            }

            // Dispatch to PermFS bridge with braid compression + Dr-Lex audit
            let result = unsafe { bridge::write_block(addr_high, addr_low, buffer) };
            match result {
                bridge::BridgeResult::Success => SyscallResult::Success as i64,
                bridge::BridgeResult::InvalidAddress => SyscallResult::InvalidAddress as i64,
                bridge::BridgeResult::IoError => SyscallResult::IoError as i64,
                bridge::BridgeResult::InvalidBuffer => SyscallResult::InvalidBuffer as i64,
                bridge::BridgeResult::AuditBlocked => SyscallResult::PermissionDenied as i64,
                _ => SyscallResult::IoError as i64,
            }
        }
        SyscallNumber::SpawnTask => {
            // Dispatch to scheduler
            let entry = arg1;
            let arg = arg2;
            crate::scheduler::spawn(entry, arg, 1); // Default Priority 1
            SyscallResult::Success as i64
        }
        SyscallNumber::Yield => {
            // Return to scheduler
            crate::scheduler::yield_task();
            SyscallResult::Success as i64
        }
        SyscallNumber::Exit => {
            // Mark task as exited
            SyscallResult::Success as i64
        }
        SyscallNumber::GetTime => {
            // Return TSC value (simplified)
            SyscallResult::Success as i64
        }
        SyscallNumber::AuditLog => {
            // Placeholder for audit logging
            SyscallResult::Success as i64
        }
        SyscallNumber::SubmitRequest => {
            let vesicle_ptr = arg1 as *const SynapticVesicle;
            if vesicle_ptr.is_null() {
                return SyscallResult::InvalidBuffer as i64;
            }
            
            // Safety: Read vesicle from user space
            let vesicle = unsafe { *vesicle_ptr };
            
            // Push to outbox for scheduler to transmit
            crate::outbox::push(vesicle);
            
            SyscallResult::Success as i64
        }
        SyscallNumber::PollNetwork => {
            let buf_ptr = arg1 as *mut u8;
            let buf_len = arg2 as usize;
            
            if buf_ptr.is_null() || buf_len == 0 {
                return SyscallResult::InvalidBuffer as i64;
            }
            
            let stream = unsafe { crate::arachnid::get_stream() };
            let available = stream.available() as usize;
            
            if available == 0 {
                return 0;
            }
            
            let to_read = available.min(buf_len);
            let tail = stream.read_tail.load(Ordering::Acquire);
            let capacity = stream.capacity as usize;
            
            let user_slice = unsafe { core::slice::from_raw_parts_mut(buf_ptr, to_read) };
            
            for i in 0..to_read {
                let idx = (tail as usize + i) % capacity;
                user_slice[i] = unsafe { core::ptr::read_volatile(stream.data.as_ptr().add(idx)) };
            }
            
            stream.read_tail.store(tail.wrapping_add(to_read as u32), Ordering::Release);
            
            to_read as i64
        }
        SyscallNumber::ReadStats => {
            let buf_ptr = arg1 as *mut u64;
            if buf_ptr.is_null() {
                return SyscallResult::InvalidBuffer as i64;
            }
            
            unsafe {
                *buf_ptr.add(0) = SYSCALL_STATS.total_calls.load(Ordering::Relaxed);
                *buf_ptr.add(1) = SYSCALL_STATS.read_calls.load(Ordering::Relaxed);
                *buf_ptr.add(2) = SYSCALL_STATS.write_calls.load(Ordering::Relaxed);
                *buf_ptr.add(3) = SYSCALL_STATS.spawn_calls.load(Ordering::Relaxed);
            }
            SyscallResult::Success as i64
        }
        _ => SyscallResult::InvalidSyscall as i64,
    }
}
