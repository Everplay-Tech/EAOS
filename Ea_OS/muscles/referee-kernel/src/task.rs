extern crate alloc;
use alloc::vec::Vec;
use alloc::vec;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TaskId(pub u64);

/// Task Control Block
pub struct Task {
    pub id: TaskId,
    pub rsp: u64, // Saved Stack Pointer
    pub stack: Vec<u8>,
    pub is_alive: bool,
    pub priority: u8,
    pub budget: u8,
}

impl Task {
    pub fn new(id: u64, entry: u64, arg: u64, trampoline: u64, priority: u8) -> Self {
        let stack_size = 32 * 1024; // 32KB
        let mut stack = vec![0u8; stack_size];
        
        // Setup initial stack frame
        let stack_top = stack.as_ptr() as u64 + stack_size as u64;
        // Align to 16 bytes
        let mut sp = stack_top & !0xF;
        
        unsafe {
            // Context Layout:
            // High Addr
            // [RIP] -> trampoline
            // [RBP]
            // [RBX]
            // [R12] -> entry point
            // [R13] -> argument (BootParameters)
            // [R14]
            // [R15]
            // Low Addr <- SP
            
            // 1. Push Trampoline (RIP)
            sp -= 8;
            *(sp as *mut u64) = trampoline;
            
            // 2. Push RBP (0)
            sp -= 8;
            *(sp as *mut u64) = 0;
            
            // 3. Push RBX (0)
            sp -= 8;
            *(sp as *mut u64) = 0;
            
            // 4. Push R12 (Entry)
            sp -= 8;
            *(sp as *mut u64) = entry;
            
            // 5. Push R13 (Arg)
            sp -= 8;
            *(sp as *mut u64) = arg;
            
            // 6. Push R14 (0)
            sp -= 8;
            *(sp as *mut u64) = 0;
            
            // 7. Push R15 (0)
            sp -= 8;
            *(sp as *mut u64) = 0;
        }

        Self {
            id: TaskId(id),
            rsp: sp,
            stack,
            is_alive: true,
            priority,
            budget: priority,
        }
    }
}
