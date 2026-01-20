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

/// TCP socket buffer sizes
const TCP_RX_BUFFER_SIZE: usize = 4096;
const TCP_TX_BUFFER_SIZE: usize = 1024;

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

// ============================================================================
// Scheduler Entry Points
// ============================================================================

/// Round-robin scheduler that executes muscle cells in sequence.
pub fn run_scheduler(bt: &BootServices, cells: &[Option<Cell>], uart: &mut Uart) -> ! {
    run_scheduler_with_net(bt, cells, uart, None)
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
) -> ! {
    let mut index = 0;
    let mut execution_count: u64 = 0;

    uart.log("INFO", "Scheduler starting round-robin execution");
    uart.log("INFO", "ARACHNID Spider: ARMED");

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

    uart.log("INFO", "Phase 6: Ready for First Breath. Awaiting ignition...");

    // ========================================================================
    // THE LIFE LOOP (EVERY TICK)
    // ========================================================================
    loop {
        // ================================================================
        // PHASE 6: Poll ARACHNID with Persistent Organs
        // ================================================================
        if let Some(ref mut driver) = net_driver {
            if let Some(ref mut iface) = iface {
                unsafe {
                    tick_arachnid_tcp(driver, &mut sockets, iface, socket_handle);
                }
            }
        } else {
            unsafe {
                tick_arachnid_sync_only();
            }
        }

        // ================================================================
        // Execute muscle cells
        // ================================================================
        if let Some(cell) = &cells[index % cells.len()] {
            if !cell.validate_canary() {
                uart.log("FATAL", "Stack canary corrupted - system halted");
                break;
            }

            execution_count += 1;

            // Phase 6.5: VASCULAR INSTRUMENTATION - periodic stats
            if execution_count % 5000 == 0 {
                let rx = get_rx_count();
                let tx = get_tx_count();
                if rx > 0 || tx > 0 {
                    uart.log("VASCULAR", "RX/TX packet pulse detected");
                }
            }

            unsafe {
                let func: extern "C" fn() = core::mem::transmute(cell.entry_point);
                func();
            }
        }

        index += 1;

        // Small delay to prevent busyloop (1ms)
        bt.stall(1000);
    }

    uart.log("FATAL", "Scheduler halted due to error");

    loop {
        bt.stall(10_000_000);
    }
}
