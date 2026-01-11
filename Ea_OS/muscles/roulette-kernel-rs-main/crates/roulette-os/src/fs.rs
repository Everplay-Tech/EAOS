//! Filesystem interface: robust, enterprise-grade

use roulette_fs::{FileSystem, FsError};
use futures::future::BoxFuture;

/// Algebraic file operation
#[derive(Debug, Clone)]
pub enum FsOp {
    Read(String, usize),
    Write(String, Vec<u8>),
    Delete(String),
    ListDir(String),
}

/// Algebraic file result
#[derive(Debug, Clone)]
pub enum FsResult {
    Data(Vec<u8>),
    Written(usize),
    Deleted,
    DirList(Vec<String>),
    Error(FsError),
}

/// OS filesystem: robust, extensible, async
pub struct OSFileSystem {
    fs: FileSystem,
}

impl OSFileSystem {
    /// Create a new OS filesystem
    pub fn new() -> Self {
        Self { fs: FileSystem::new() }
    }

    /// Async file operation
    pub fn op(&mut self, op: FsOp) -> BoxFuture<'static, FsResult> {
        use futures::FutureExt;
        match op {
            FsOp::Read(path, len) => {
                let mut buf = vec![0u8; len];
                match self.fs.read(&path, &mut buf) {
                    Ok(sz) => async { FsResult::Data(buf[..sz].to_vec()) }.boxed(),
                    Err(e) => async { FsResult::Error(e) }.boxed(),
                }
            }
            FsOp::Write(path, data) => {
                match self.fs.write(&path, &data) {
                    Ok(sz) => async { FsResult::Written(sz) }.boxed(),
                    Err(e) => async { FsResult::Error(e) }.boxed(),
                }
            }
            FsOp::Delete(path) => {
                match self.fs.delete(&path) {
                    Ok(()) => async { FsResult::Deleted }.boxed(),
                    Err(e) => async { FsResult::Error(e) }.boxed(),
                }
            }
            FsOp::ListDir(path) => {
                match self.fs.list_dir(&path) {
                    Ok(list) => async { FsResult::DirList(list) }.boxed(),
                    Err(e) => async { FsResult::Error(e) }.boxed(),
                }
            }
        }
    }
}
