//! EAOS Round-Robin Scheduler with ARACHNID Network Integration
//!
//! ## Phase 6: THE IRON LUNG - Persistent Physiology
//!
//! The smoltcp Interface and SocketSet are created ONCE before entering the
//! main loop. This prevents "Cardiac Arrest" where TCP state was being wiped
//! every tick, causing the Spider to forget its SYN packets.
//!
//! ## Control Wiring
//!
//! - ENTROPY_FLUX: Maps to bookmark selection (Spider::tune)
//! - MEM_ACID + ARMED: Ignition control (Spider::ignite)
//! - NET_CHOKE: Baud rate throttling (passed to Spider::poll)

extern crate alloc;

use alloc::vec;
use uefi::table::boot::BootServices;
use crate::cell::Cell;
use crate::uart::Uart;
use muscle_contract::BootParameters;
use crate::arachnid::{
    SPIDER, NETWORK, sync_state, get_stream, SpiderState,
    create_interface, BOOKMARKS,
};
use crate::virtio_modern::{KERNEL_OVERRIDES, RX_BUFFERS, VirtioModern};
use crate::virtio_phy::{VirtioPhy, get_timestamp_ms, get_rx_count, get_tx_count};

use smoltcp::iface::{Config, Interface, SocketSet, SocketHandle, SocketStorage};
use smoltcp::socket::tcp::{Socket as TcpSocket, SocketBuffer as TcpSocketBuffer};
use smoltcp::wire::{EthernetAddress, IpEndpoint, Ipv4Address};
use smoltcp::time::Instant;
use crate::task::{Task, TaskId};

/// TCP socket buffer sizes
const TCP_RX_BUFFER_SIZE: usize = 4096;
const TCP_TX_BUFFER_SIZE: usize = 1024;

// Multitasking Globals
static mut TASKS: Vec<Task> = Vec::new();
static mut CURRENT_TASK_IDX: usize = 0;
static mut SCHEDULER_RSP: u64 = 0;

core::arch::global_asm!(r#"
.global context_switch
context_switch:
    push rbp
    push rbx
    push r12
    push r13
    push r14
    push r15
    mov [rdi], rsp
    mov rsp, rsi
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret

.global task_trampoline
task_trampoline:
    mov rdi, r13
    call r12
    mov rax, 4
    syscall
"#);

extern "C" {
    fn context_switch(old_rsp: *mut u64, new_rsp: u64);
    pub fn task_trampoline();
}

pub fn spawn(entry: u64, arg: u64) {
    unsafe {
        let id = TASKS.len() as u64;
        let trampoline = task_trampoline as usize as u64;
        TASKS.push(Task::new(id, entry, arg, trampoline));
    }
}

pub fn yield_task() {
    unsafe {
        if TASKS.is_empty() { return; }
        let current = &mut TASKS[CURRENT_TASK_IDX];
        context_switch(&mut current.rsp, SCHEDULER_RSP);
    }
}

pub fn current_task_id() -> u64 {
    unsafe {
        if TASKS.is_empty() { return 0; }
        TASKS[CURRENT_TASK_IDX].id.0
    }
}

// ============================================================================
// Phase 6: Tick Functions with Persistent Organs
// ============================================================================

/// Tick the ARACHNID spider with full TCP integration
///
/// This is the "Iron Lung" version - Interface and SocketSet are passed in,
/// NOT created here. This preserves ARP cache and TCP sequence numbers.
///
/// # Safety
/// Accesses global mutable statics. Must only be called from single-threaded scheduler.
unsafe fn tick_arachnid_tcp(
    driver: &mut VirtioModern,
    sockets: &mut SocketSet<'_>,
    iface: &mut Interface,
    socket_handle: SocketHandle,
) {
    // ========================================================================
    // Read Control Overrides from Tactile Deck
    // ========================================================================
    let entropy = KERNEL_OVERRIDES.entropy_flux;
    let choke = KERNEL_OVERRIDES.net_choke;
    let mem_acid = KERNEL_OVERRIDES.mem_acid;
    let armed = KERNEL_OVERRIDES.is_armed();

    // ========================================================================
    // CONTROL WIRING: ENTROPY_FLUX -> Bookmark Selection
    // ========================================================================
    SPIDER.tune(entropy);

    // ========================================================================
    // CONTROL WIRING: MEM_ACID + ARMED -> Ignition / Deadman Switch
    // ========================================================================
    let ignited = SPIDER.ignite(armed, mem_acid);

    // If just ignited, initiate TCP connection
    if ignited {
        let bookmark = SPIDER.bookmark();
        let endpoint = IpEndpoint::new(
            Ipv4Address::new(bookmark.ip[0], bookmark.ip[1], bookmark.ip[2], bookmark.ip[3]).into(),
            bookmark.port,
        );

        let socket = sockets.get_mut::<TcpSocket>(socket_handle);

        // Close any existing connection first
        if socket.is_active() {
            socket.abort();
        }

        // Initiate new connection with ephemeral port
        let local_port = 49152 + ((get_timestamp_ms() % 16384) as u16);
        let local_endpoint = IpEndpoint::new(
            Ipv4Address::new(10, 0, 2, 15).into(),
            local_port,
        );

        if socket.connect(iface.context(), endpoint, local_endpoint).is_err() {
            SPIDER.reset();
        } else {
            // Store socket handle in NETWORK for tracking
            NETWORK.socket_handle = Some(socket_handle);
        }
    }

    // ========================================================================
    // Poll Network with VirtioPhy (THE HEARTBEAT)
    // ========================================================================
    {
        let mut phy = VirtioPhy::new(driver);
        let timestamp = Instant::from_millis(get_timestamp_ms() as i64);

        // Poll the interface - this processes ARP, IP, TCP
        let _ = iface.poll(timestamp, &mut phy, sockets);
    }

    // ========================================================================
    // Drive Spider State Machine
    // ========================================================================
    let socket = sockets.get_mut::<TcpSocket>(socket_handle);
    let stream = get_stream();

    match SPIDER.state() {
        SpiderState::Connecting => {
            // Check if TCP connection established
            if socket.may_send() && socket.may_recv() {
                SPIDER.set_state(SpiderState::Requesting);
                NETWORK.mark_connected();
            } else if !socket.is_open() {
                SPIDER.set_state(SpiderState::Error);
            }
        }

        SpiderState::Requesting => {
            // Send HTTP request (THE VENOM)
            if socket.can_send() {
                let (req_buf, len) = SPIDER.build_request();

                match socket.send_slice(&req_buf[..len]) {
                    Ok(_) => {
                        SPIDER.set_state(SpiderState::Harvesting);
                        NETWORK.mark_request_sent();
                    }
                    Err(_) => { /* Retry next tick */ }
                }
            }
        }

        SpiderState::Harvesting => {
            // Receive and process data through Acid Bath
            if socket.can_recv() {
                let mut buf = [0u8; 512];

                // Limit based on choke (baud rate throttling)
                let max_bytes = if choke > 0.99 {
                    1  // Extreme choke: 1 byte at a time
                } else {
                    let speed = 1.0 - choke;
                    ((512.0 * speed) as usize).max(1)
                };

                match socket.recv_slice(&mut buf[..max_bytes]) {
                    Ok(len) if len > 0 => {
                        // Feed through Spider's Acid Bath into ring buffer
                        SPIDER.poll(&buf[..len], stream, choke);
                        NETWORK.add_bytes(len as u32);
                    }
                    Ok(_) => {}
                    Err(_) => {}
                }
            }

            // Check for completion (remote closed)
            if !socket.may_recv() {
                SPIDER.set_state(SpiderState::Complete);
            }
        }

        SpiderState::Dissolving => {
            // Close the socket
            socket.abort();
            SPIDER.reset();
        }

        _ => {}
    }

    // Sync spider state to ring buffer (for UI polling)
    sync_state();
}

/// Tick for state sync only (no network driver - demo mode)
unsafe fn tick_arachnid_sync_only() {
    let entropy = KERNEL_OVERRIDES.entropy_flux;
    let mem_acid = KERNEL_OVERRIDES.mem_acid;
    let armed = KERNEL_OVERRIDES.is_armed();

    SPIDER.tune(entropy);
    SPIDER.ignite(armed, mem_acid);

    sync_state();
}

use uefi::proto::console::gop::PixelFormat;
use crate::graphics::Framebuffer;

// ...

// ============================================================================
// Scheduler Entry Points
// ============================================================================

/// Round-robin scheduler that executes muscle cells in sequence.
pub fn run_scheduler(
    bt: &BootServices,
    cells: &[Option<Cell>],
    uart: &mut Uart,
    master_key: &[u8; 32],
    framebuffer: Option<&Framebuffer>,
) -> ! {
    run_scheduler_with_net(bt, cells, uart, None, master_key, framebuffer)
}

/// Scheduler with optional network driver
///
/// ## Phase 6: THE IRON LUNG
///
/// The vital organs (Interface, SocketSet) are initialized ONCE before the
/// main loop. This preserves TCP state across ticks.
pub fn run_scheduler_with_net(
    bt: &BootServices,
    cells: &[Option<Cell>],
    uart: &mut Uart,
    mut net_driver: Option<VirtioModern>,
    master_key: &[u8; 32],
    framebuffer: Option<&Framebuffer>,
) -> ! {
    uart.log("INFO", "Scheduler starting Multitasking Execution");
    uart.log("INFO", "ARACHNID Spider: ARMED");

    // Extract framebuffer info if available
    let (fb_addr, fb_size, fb_width, fb_height, fb_stride, fb_format) = if let Some(fb) = framebuffer {
        let fmt = match fb.format {
            PixelFormat::Rgb => 0,
            PixelFormat::Bgr => 1,
            _ => 2, // Bitmask/Unsupported
        };
        (fb.base() as u64, fb.size_bytes() as u64, fb.width as u32, fb.height as u32, fb.stride as u32, fmt)
    } else {
        (0, 0, 0, 0, 0, 0)
    };

    // Construct BootParameters for trusted handoff
    let boot_params = BootParameters {
        magic: 0xEA05_B007,
        nucleus_addr: 0x9100_2000, // Cell 1 (0x9100_0000 + 8192)
        nucleus_size: 8192,
        master_key: *master_key,
        framebuffer_addr: fb_addr,
        framebuffer_size: fb_size,
        framebuffer_width: fb_width,
        framebuffer_height: fb_height,
        framebuffer_stride: fb_stride,
        framebuffer_format: fb_format,
        entry_point: 0,
        nucleus_hash: [0u8; 32],
        afferent_signal_addr: &crate::uart::AFFERENT_SIGNAL as *const _ as u64,
    };


    // ========================================================================
    // Phase 6: INITIALIZE VITAL ORGANS (ONCE, OUTSIDE LOOP)
    // ========================================================================

    // Create socket storage (The Lungs)
    let mut socket_storage: [SocketStorage; 8] = Default::default();
    let mut sockets = SocketSet::new(&mut socket_storage[..]);

    // Create TCP socket with buffers
    let mut tcp_rx_buffer = vec![0u8; TCP_RX_BUFFER_SIZE];
    let mut tcp_tx_buffer = vec![0u8; TCP_TX_BUFFER_SIZE];

    let tcp_socket = TcpSocket::new(
        TcpSocketBuffer::new(&mut tcp_rx_buffer[..]),
        TcpSocketBuffer::new(&mut tcp_tx_buffer[..]),
    );
    let socket_handle = sockets.add(tcp_socket);

    // Initialize the Network Interface (The Heart)
    let mut iface: Option<Interface> = None;

    if let Some(ref driver) = net_driver {
        // Construct config from driver MAC
        let hardware_addr = EthernetAddress(driver.mac);
        let config = Config::new(hardware_addr.into());

        // Create persistent interface
        iface = Some(create_interface(config));

        // Initialize NETWORK manager
        unsafe {
            NETWORK.init(driver.mac);
            NETWORK.socket_handle = Some(socket_handle);
        }

        uart.log("INFO", "Phase 6: Vital organs initialized");
        uart.log("INFO", "Phase 6: Interface persisted (ARP cache active)");
        uart.log("INFO", "Phase 6: SocketSet persisted (TCP state active)");
    } else {
        uart.log("WARN", "No network driver - ARACHNID in demo mode");
    }

    // Log optic nerve status
    if crate::arachnid::is_optic_nerve_active() {
        uart.log("IVSHMEM", "Optic Nerve ACTIVE");
    }

    // Spawn Nucleus
    if let Some(cell) = &cells[0] {
        spawn(cell.entry_point, &boot_params as *const _ as u64);
        uart.log("SCHEDULER", "Nucleus spawned as Task 0");
    }

    uart.log("INFO", "Phase 6: Ready for First Breath. Awaiting ignition...");

    // ========================================================================
    // THE LIFE LOOP (EVERY TICK)
    // ========================================================================
    loop {
        // Poll Somatic Nerve (UART)
        uart.poll();
        
        // Poll Atlas (Keyboard)
        if let Some(scancode) = crate::input::Ps2Controller::poll() {
            if let Some(ascii) = crate::input::Ps2Controller::to_ascii(scancode) {
                uart.inject(ascii);
                // Local Echo
                uart.write_byte(ascii);
            }
        }

        // ================================================================
        // PHASE 6: Poll ARACHNID with Persistent Organs
        // ================================================================
        if let Some(ref mut driver) = net_driver {
            if let Some(ref mut iface) = iface {
                unsafe {
                    tick_arachnid_tcp(driver, &mut sockets, iface, socket_handle);
                }
                
                // Poll Outbox (Hive Mind Transmission)
                if let Some(vesicle) = crate::outbox::pop() {
                     uart.log("HIVE", "Transmitting...");
                     let socket = sockets.get_mut::<TcpSocket>(socket_handle);
                     if socket.can_send() {
                         // Send payload
                         let _ = socket.send_slice(&vesicle.payload[..vesicle.payload_size as usize]);
                     }
                }
            }
        } else {
            unsafe {
                tick_arachnid_sync_only();
            }
        }

        // ================================================================
        // Multitasking: Switch to Current Task
        // ================================================================
        unsafe {
            if !TASKS.is_empty() {
                let current = &TASKS[CURRENT_TASK_IDX];
                
                // Switch Context (Save Scheduler, Load Task)
                context_switch(&mut SCHEDULER_RSP, current.rsp);
                
                // Returned from Task (Yield)
                // Select Next
                CURRENT_TASK_IDX = (CURRENT_TASK_IDX + 1) % TASKS.len();
            }
        }

        // Small delay to prevent busyloop
        bt.stall(100);
    }
}
