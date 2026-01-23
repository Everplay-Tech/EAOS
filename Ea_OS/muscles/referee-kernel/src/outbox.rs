extern crate alloc;
use alloc::collections::VecDeque;
use muscle_contract::abi::SynapticVesicle;

/// Global Network Outbox
/// Stores signed intents waiting for transmission.
pub static mut NET_OUTBOX: Option<VecDeque<SynapticVesicle>> = None;

/// Initialize the outbox
pub fn init() {
    unsafe {
        if NET_OUTBOX.is_none() {
            NET_OUTBOX = Some(VecDeque::with_capacity(32));
        }
    }
}

/// Push a vesicle to the outbox
pub fn push(packet: SynapticVesicle) {
    unsafe {
        if let Some(q) = NET_OUTBOX.as_mut() {
            q.push_back(packet);
        }
    }
}

/// Pop a vesicle from the outbox
pub fn pop() -> Option<SynapticVesicle> {
    unsafe {
        if let Some(q) = NET_OUTBOX.as_mut() {
            q.pop_front()
        } else {
            None
        }
    }
}
