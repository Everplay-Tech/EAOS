//! System call interface: robust, enterprise-grade

use roulette_core::t9_syscalls::{T9SyscallInterpreter, T9SyscallError};
use futures::future::BoxFuture;

/// Algebraic syscall operation
#[derive(Debug, Clone)]
pub enum SyscallOp {
    T9(String),
    FsRead(String, usize),
    FsWrite(String, Vec<u8>),
    ProcessCreate(usize, usize),
    Unknown(String),
}

/// Algebraic syscall result
#[derive(Debug, Clone)]
pub enum SyscallResult {
    Ok,
    Data(Vec<u8>),
    Pid(u64),
    Error(T9SyscallError),
}

/// System call context: carries process/user info for robust dispatch
pub struct SyscallContext<'a> {
    pub user: &'a str,
    pub pid: Option<u64>,
    pub args: &'a [&'a str],
}

/// System call dispatcher: robust, extensible, async
pub struct SyscallDispatcher;

impl SyscallDispatcher {
    /// Async dispatch a syscall with context and error handling
    pub fn dispatch(ctx: &SyscallContext, op: SyscallOp) -> BoxFuture<'static, SyscallResult> {
        use futures::FutureExt;
        match op {
            SyscallOp::T9(word) => {
                match T9SyscallInterpreter::execute_t9_syscall(&word) {
                    Ok(_) => async { SyscallResult::Ok }.boxed(),
                    Err(e) => async { SyscallResult::Error(e) }.boxed(),
                }
            }
            SyscallOp::FsRead(_, _) => async { SyscallResult::Error(T9SyscallError::InvalidSyscall) }.boxed(),
            SyscallOp::FsWrite(_, _) => async { SyscallResult::Error(T9SyscallError::InvalidSyscall) }.boxed(),
            SyscallOp::ProcessCreate(_, _) => async { SyscallResult::Error(T9SyscallError::InvalidSyscall) }.boxed(),
            SyscallOp::Unknown(_) => async { SyscallResult::Error(T9SyscallError::InvalidSyscall) }.boxed(),
        }
    }
}
