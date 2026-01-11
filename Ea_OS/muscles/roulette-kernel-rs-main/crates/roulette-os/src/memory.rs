//! Memory management: robust, enterprise-grade

use roulette_vm::{EnhancedAllocator, VirtAddr};
use futures::future::BoxFuture;

/// Algebraic memory operation
#[derive(Debug, Clone)]
pub enum MemOp {
    Allocate(usize, usize), // size, align
    Deallocate(VirtAddr, usize, usize), // addr, size, align
    Stats,
}

/// Algebraic memory result
#[derive(Debug, Clone)]
pub enum MemResult {
    Allocated(VirtAddr),
    Deallocated,
    Stats { used: usize, free: usize },
    Error(String),
}

/// OS memory manager: dynamic allocation, deallocation, stats, async
pub struct MemoryManager {
    allocator: EnhancedAllocator,
}

impl MemoryManager {
    /// Create a new memory manager
    pub fn new(heap_start: VirtAddr, heap_size: usize) -> Self {
        let mut allocator = EnhancedAllocator::new(heap_start, heap_size);
        allocator.initialize();
        Self { allocator }
    }

    /// Async memory operation
    pub fn op(&mut self, op: MemOp) -> BoxFuture<'static, MemResult> {
        use futures::FutureExt;
        match op {
            MemOp::Allocate(size, align) => {
                let layout = core::alloc::Layout::from_size_align(size, align).ok();
                if let Some(layout) = layout {
                    if let Some(addr) = self.allocator.allocate(layout) {
                        if addr < self.allocator.heap_start || addr + size > self.allocator.heap_end {
                            async { MemResult::Error("Out of bounds".to_string()) }.boxed()
                        } else {
                            async { MemResult::Allocated(addr) }.boxed()
                        }
                    } else {
                        async { MemResult::Error("Allocation failed".to_string()) }.boxed()
                    }
                } else {
                    async { MemResult::Error("Invalid layout".to_string()) }.boxed()
                }
            }
            MemOp::Deallocate(addr, size, align) => {
                if addr < self.allocator.heap_start || addr + size > self.allocator.heap_end {
                    async { MemResult::Error("Out of bounds".to_string()) }.boxed()
                } else {
                    let layout = core::alloc::Layout::from_size_align(size, align).unwrap();
                    self.allocator.deallocate(addr, layout);
                    async { MemResult::Deallocated }.boxed()
                }
            }
            MemOp::Stats => {
                let free = self.allocator.free_memory();
                let total = self.allocator.heap_end - self.allocator.heap_start;
                let used = total - free;
                async { MemResult::Stats { used, free } }.boxed()
            }
        }
    }
}
