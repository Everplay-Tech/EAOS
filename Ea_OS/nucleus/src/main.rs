#![cfg_attr(target_os = "uefi", no_std)]
#![cfg_attr(target_os = "uefi", no_main)]

extern crate alloc;

#[cfg(target_os = "uefi")]
use core::panic::PanicInfo;
#[cfg(target_os = "uefi")]
use linked_list_allocator::LockedHeap;
#[cfg(target_os = "uefi")]
use nucleus::kernel::MuscleNucleus;

#[cfg(target_os = "uefi")]
#[global_allocator]
static ALLOCATOR: LockedHeap = LockedHeap::empty();

#[cfg(target_os = "uefi")]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

#[cfg(target_os = "uefi")]
#[no_mangle]
pub extern "C" fn _start() -> ! {
    // Initialize heap
    unsafe {
        ALLOCATOR.lock().init(0x4000_0000 as *mut u8, 1024 * 1024); // 1MB Heap
    }

    // Initialize the biological kernel
    let mut nucleus = MuscleNucleus::new();

    // Execute boot rule - this never returns
    nucleus.execute_boot_rule();
}

#[cfg(not(target_os = "uefi"))]
fn main() {}
