//! Process management: robust, enterprise-grade

use roulette_vm::{Process, Pid, ProcessState, VirtualMachine};
use std::collections::HashMap;
use async_channel::{Sender, Receiver, bounded};

/// Algebraic IPC message kind
#[derive(Debug, Clone)]
pub enum MessageKind {
    Data(Vec<u8>),
    Signal(SignalType),
    Exit,
    Custom(String),
}

#[derive(Debug, Clone)]
pub enum SignalType {
    Interrupt,
    Terminate,
    User(u8),
}

/// IPC message
#[derive(Debug, Clone)]
pub struct Message {
    pub from: Pid,
    pub to: Pid,
    pub kind: MessageKind,
}

/// Algebraic scheduling operation
#[derive(Debug, Clone)]
pub enum SchedOp {
    Next,
    ByPriority,
    ByPid(Pid),
}

/// Algebraic scheduling result
#[derive(Debug, Clone)]
pub enum SchedResult {
    Scheduled(Pid),
    None,
    Error(String),
}

/// OS process manager: advanced scheduling, async IPC, algebraic scheduling
pub struct ProcessManager {
    vm: VirtualMachine,
    priorities: HashMap<Pid, u8>, // 0 = highest
    msg_channels: HashMap<Pid, (Sender<Message>, Receiver<Message>)>,
}

impl ProcessManager {
    /// Create a new process manager
    pub fn new(heap_start: usize, heap_size: usize) -> Self {
        Self {
            vm: VirtualMachine::new(heap_start, heap_size),
            priorities: HashMap::new(),
            msg_channels: HashMap::new(),
        }
    }

    /// Create a process with entry point, stack size, and priority
    pub fn create_process(&mut self, entry_point: usize, stack_size: usize, priority: u8) -> Option<Pid> {
        let pid = self.vm.create_process(entry_point, stack_size)?;
        self.priorities.insert(pid, priority);
        let (tx, rx) = bounded(32);
        self.msg_channels.insert(pid, (tx, rx));
        Some(pid)
    }

    /// Async algebraic scheduler
    pub async fn schedule(&mut self, op: SchedOp) -> SchedResult {
        match op {
            SchedOp::Next | SchedOp::ByPriority => {
                let mut candidates: Vec<(Pid, u8)> = self.vm.processes.iter()
                    .filter_map(|p| p.as_ref().map(|proc| (proc.id, *self.priorities.get(&proc.id).unwrap_or(&10))))
                    .collect();
                candidates.sort_by_key(|&(_, prio)| prio);
                for (pid, _) in candidates {
                    if let Some(proc) = self.vm.get_process(pid) {
                        if proc.state == ProcessState::Ready {
                            if let Some(proc_mut) = self.vm.get_process_mut(pid) {
                                proc_mut.state = ProcessState::Running;
                            }
                            return SchedResult::Scheduled(pid);
                        }
                    }
                }
                SchedResult::None
            }
            SchedOp::ByPid(pid) => {
                if let Some(proc) = self.vm.get_process(pid) {
                    if proc.state == ProcessState::Ready {
                        if let Some(proc_mut) = self.vm.get_process_mut(pid) {
                            proc_mut.state = ProcessState::Running;
                        }
                        return SchedResult::Scheduled(pid);
                    }
                }
                SchedResult::None
            }
        }
    }

    /// Terminate a process
    pub fn terminate_process(&mut self, pid: Pid) -> bool {
        self.priorities.remove(&pid);
        self.msg_channels.remove(&pid);
        self.vm.terminate_process(pid)
    }

    /// Get process by PID
    pub fn get_process(&self, pid: Pid) -> Option<&Process> {
        self.vm.get_process(pid)
    }

    /// Get all active processes
    pub fn active_processes(&self) -> impl Iterator<Item = &Process> {
        self.vm.processes.iter().filter_map(|p| p.as_ref())
    }

    /// Async send IPC message
    pub async fn send_message(&self, from: Pid, to: Pid, kind: MessageKind) -> Result<(), &'static str> {
        if let Some((tx, _)) = self.msg_channels.get(&to) {
            let msg = Message { from, to, kind };
            tx.send(msg).await.map_err(|_| "Send failed")
        } else {
            Err("Target PID not found")
        }
    }

    /// Async receive IPC message
    pub async fn receive_message(&self, pid: Pid) -> Option<Message> {
        self.msg_channels.get(&pid).and_then(|(_, rx)| rx.recv().now_or_never().flatten())
    }
}
