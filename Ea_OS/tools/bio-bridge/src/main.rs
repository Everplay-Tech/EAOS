//! BIO-BRIDGE: Host-side WebSocket relay for ARACHNID BIO-STREAM
//!
//! This tool acts as the "Optic Nerve" connecting the kernel's visual cortex
//! (shared memory ring buffer) to the browser-based NEON-SYSTOLE dashboard.
//!
//! ## Architecture
//!
//! ```text
//! ┌─────────────┐     mmap      ┌─────────────┐    WebSocket    ┌─────────────┐
//! │   Kernel    │ ────────────> │  BIO-BRIDGE │ ───────────────>│   Browser   │
//! │  (ARACHNID) │  /dev/shm/    │  (This)     │   ws://3001     │  (Retina)   │
//! └─────────────┘               └─────────────┘                 └─────────────┘
//! ```
//!
//! ## Usage
//!
//! ```bash
//! bio-bridge --shm /dev/shm/eaos_biostream --port 3001
//! ```

use std::collections::HashMap;
use std::fs::OpenOptions;
use std::io::Result as IoResult;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use byteorder::{LittleEndian, ReadBytesExt};
use clap::Parser;
use futures_util::{SinkExt, StreamExt};
use memmap2::MmapOptions;
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{broadcast, RwLock};
use tokio_tungstenite::tungstenite::Message;
use tracing::{debug, error, info, warn};

// ============================================================================
// BIO-STREAM Protocol Constants (must match kernel)
// ============================================================================

/// BIO-STREAM magic number
const BIOSTREAM_MAGIC: u32 = 0xB105_73A1;

/// Ring buffer capacity
const BIOSTREAM_CAPACITY: usize = 65536;

/// Header size (before data)
const BIOSTREAM_HEADER_SIZE: usize = 32;

// Header offsets
const OFF_MAGIC: usize = 0;
const OFF_CAPACITY: usize = 4;
const OFF_WRITE_HEAD: usize = 8;
const OFF_READ_TAIL: usize = 12;
const OFF_STATE: usize = 16;
const OFF_BOOKMARK: usize = 17;
const OFF_ERROR: usize = 18;
const OFF_HARVESTED: usize = 20;
const OFF_DATA: usize = 32;

// ============================================================================
// CLI Arguments
// ============================================================================

#[derive(Parser, Debug)]
#[command(name = "bio-bridge")]
#[command(about = "Host-side WebSocket bridge for ARACHNID BIO-STREAM")]
struct Args {
    /// Path to shared memory file
    #[arg(short, long, default_value = "/dev/shm/eaos_biostream")]
    shm: PathBuf,

    /// WebSocket server port
    #[arg(short, long, default_value = "3001")]
    port: u16,

    /// Poll rate in Hz (default 60)
    #[arg(long, default_value = "60")]
    poll_rate: u32,

    /// Create shared memory file if it doesn't exist (for testing)
    #[arg(long)]
    create: bool,
}

// ============================================================================
// Bridge State
// ============================================================================

/// Shared state for the bridge
struct BridgeState {
    /// Last read tail position (bridge-local)
    read_tail: AtomicU32,
    /// Connected client count
    client_count: AtomicU32,
    /// Total bytes relayed
    bytes_relayed: AtomicU64,
}

impl BridgeState {
    fn new() -> Self {
        Self {
            read_tail: AtomicU32::new(0),
            client_count: AtomicU32::new(0),
            bytes_relayed: AtomicU64::new(0),
        }
    }
}

// ============================================================================
// Main Entry Point
// ============================================================================

#[tokio::main]
async fn main() -> IoResult<()> {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("bio_bridge=info".parse().unwrap())
        )
        .init();

    let args = Args::parse();

    info!("BIO-BRIDGE starting...");
    info!("  Shared memory: {:?}", args.shm);
    info!("  WebSocket port: {}", args.port);
    info!("  Poll rate: {} Hz", args.poll_rate);

    // Open or create shared memory
    let mmap = if args.create {
        create_shm(&args.shm)?
    } else {
        open_shm(&args.shm)?
    };

    let mmap = Arc::new(tokio::sync::RwLock::new(mmap));
    let state = Arc::new(BridgeState::new());

    // Validate magic number (with retry for kernel boot)
    info!("Waiting for kernel to initialize BIO-STREAM...");
    let mut retries = 0;
    loop {
        let magic = {
            let guard = mmap.read().await;
            read_u32(&guard, OFF_MAGIC)
        };

        if magic == BIOSTREAM_MAGIC {
            info!("BIO-STREAM magic validated: 0x{:08X}", magic);
            break;
        }

        if args.create && retries == 0 {
            info!("Initializing shared memory with magic number");
            let mut guard = mmap.write().await;
            write_u32(&mut guard, OFF_MAGIC, BIOSTREAM_MAGIC);
            write_u32(&mut guard, OFF_CAPACITY, BIOSTREAM_CAPACITY as u32);
            break;
        }

        retries += 1;
        if retries > 100 {
            error!("Timeout waiting for kernel (magic=0x{:08X})", magic);
            return Err(std::io::Error::new(
                std::io::ErrorKind::TimedOut,
                "Kernel did not initialize BIO-STREAM",
            ));
        }

        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    // Create broadcast channel for sending to clients
    let (tx, _rx) = broadcast::channel::<Vec<u8>>(64);
    let tx = Arc::new(tx);

    // Start the poll loop
    let poll_mmap = Arc::clone(&mmap);
    let poll_state = Arc::clone(&state);
    let poll_tx = Arc::clone(&tx);
    let poll_interval = Duration::from_micros(1_000_000 / args.poll_rate as u64);

    tokio::spawn(async move {
        poll_loop(poll_mmap, poll_state, poll_tx, poll_interval).await;
    });

    // Start WebSocket server
    let addr = SocketAddr::from(([127, 0, 0, 1], args.port));
    let listener = TcpListener::bind(&addr).await?;
    info!("WebSocket server listening on ws://{}", addr);

    while let Ok((stream, peer)) = listener.accept().await {
        info!("New connection from: {}", peer);
        let client_tx = tx.subscribe();
        let client_state = Arc::clone(&state);

        tokio::spawn(async move {
            if let Err(e) = handle_client(stream, client_tx, client_state).await {
                warn!("Client {} error: {}", peer, e);
            }
            info!("Client {} disconnected", peer);
        });
    }

    Ok(())
}

// ============================================================================
// Shared Memory Operations
// ============================================================================

/// Open existing shared memory file (read-write for SPSC tail updates)
fn open_shm(path: &PathBuf) -> IoResult<memmap2::MmapMut> {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .open(path)?;

    unsafe { MmapOptions::new().map_mut(&file) }
}

/// Create shared memory file (for testing)
fn create_shm(path: &PathBuf) -> IoResult<memmap2::MmapMut> {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .open(path)?;

    // Set file size
    file.set_len((BIOSTREAM_HEADER_SIZE + BIOSTREAM_CAPACITY) as u64)?;

    unsafe { MmapOptions::new().map_mut(&file) }
}

/// Read u32 from mmap at offset (little-endian)
fn read_u32(mmap: &[u8], offset: usize) -> u32 {
    if offset + 4 <= mmap.len() {
        let mut cursor = std::io::Cursor::new(&mmap[offset..offset + 4]);
        cursor.read_u32::<LittleEndian>().unwrap_or(0)
    } else {
        0
    }
}

/// Read u8 from mmap at offset
fn read_u8(mmap: &[u8], offset: usize) -> u8 {
    if offset < mmap.len() {
        mmap[offset]
    } else {
        0
    }
}

/// Write u32 to mmap at offset (little-endian)
fn write_u32(mmap: &mut [u8], offset: usize, value: u32) {
    if offset + 4 <= mmap.len() {
        mmap[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
    }
}

// ============================================================================
// Poll Loop
// ============================================================================

/// Main poll loop - reads ring buffer and broadcasts to clients
///
/// Implements proper SPSC (Single Producer Single Consumer) ring buffer protocol:
/// - Kernel (producer) writes to write_head
/// - Bridge (consumer) reads data, then commits by writing read_tail
async fn poll_loop(
    mmap: Arc<RwLock<memmap2::MmapMut>>,
    state: Arc<BridgeState>,
    tx: Arc<broadcast::Sender<Vec<u8>>>,
    interval: Duration,
) {
    let mut interval_timer = tokio::time::interval(interval);
    let mut last_log = std::time::Instant::now();

    loop {
        interval_timer.tick().await;

        // Phase 1: Read with shared lock
        let (write_head, capacity, spider_state, read_tail, frame_opt) = {
            let guard = mmap.read().await;

            let write_head = read_u32(&guard, OFF_WRITE_HEAD);
            let capacity = read_u32(&guard, OFF_CAPACITY) as usize;
            let spider_state = read_u8(&guard, OFF_STATE);
            let _bookmark = read_u8(&guard, OFF_BOOKMARK);
            let _error = read_u8(&guard, OFF_ERROR);
            let _harvested = read_u32(&guard, OFF_HARVESTED);

            // Get our local read tail
            let read_tail = state.read_tail.load(Ordering::Acquire);

            // Calculate available bytes
            let available = write_head.wrapping_sub(read_tail);

            let frame_opt = if available > 0 && capacity > 0 {
                // Build binary frame to send (include header for client parsing)
                let mut frame = Vec::with_capacity(BIOSTREAM_HEADER_SIZE + available as usize);

                // Copy header (32 bytes)
                frame.extend_from_slice(&guard[..BIOSTREAM_HEADER_SIZE]);

                // Copy ring buffer data (handling wrap-around)
                let cap = capacity.min(BIOSTREAM_CAPACITY);
                for i in 0..available {
                    let idx = ((read_tail + i) as usize) % cap;
                    let byte = guard.get(OFF_DATA + idx).copied().unwrap_or(0);
                    frame.push(byte);
                }

                Some((frame, available))
            } else {
                None
            };

            (write_head, capacity, spider_state, read_tail, frame_opt)
        };

        // Phase 2: Process and commit
        if let Some((frame, available)) = frame_opt {
            // Update our local tail
            state.read_tail.store(write_head, Ordering::Release);

            // Phase 3: Write read_tail back to shared memory (SPSC commit)
            {
                let mut guard = mmap.write().await;
                write_u32(&mut guard, OFF_READ_TAIL, write_head);
                // Ensure write is visible to kernel
                std::sync::atomic::fence(Ordering::Release);
            }

            // Update stats
            state.bytes_relayed.fetch_add(available as u64, Ordering::Relaxed);

            // Broadcast to all connected clients
            let _ = tx.send(frame);

            debug!("Relayed {} bytes (state={})", available, spider_state);
        }

        // Periodic status log
        if last_log.elapsed() > Duration::from_secs(10) {
            let clients = state.client_count.load(Ordering::Relaxed);
            let relayed = state.bytes_relayed.load(Ordering::Relaxed);
            info!(
                "Status: {} clients, {} bytes relayed, spider_state={}",
                clients, relayed, spider_state
            );
            last_log = std::time::Instant::now();
        }
    }
}

// ============================================================================
// WebSocket Client Handler
// ============================================================================

/// Handle a single WebSocket client connection
async fn handle_client(
    stream: TcpStream,
    mut rx: broadcast::Receiver<Vec<u8>>,
    state: Arc<BridgeState>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // Upgrade to WebSocket
    let ws_stream = tokio_tungstenite::accept_async(stream).await?;
    let (mut write, mut read) = ws_stream.split();

    // Track client
    state.client_count.fetch_add(1, Ordering::Relaxed);

    // Main loop: relay broadcast messages to this client
    loop {
        tokio::select! {
            // Receive data from broadcast channel
            result = rx.recv() => {
                match result {
                    Ok(data) => {
                        // Send as binary WebSocket frame
                        if let Err(e) = write.send(Message::Binary(data)).await {
                            debug!("Send error: {}", e);
                            break;
                        }
                    }
                    Err(broadcast::error::RecvError::Lagged(n)) => {
                        warn!("Client lagged {} messages", n);
                    }
                    Err(broadcast::error::RecvError::Closed) => {
                        break;
                    }
                }
            }

            // Handle client messages (for future bidirectional control)
            msg = read.next() => {
                match msg {
                    Some(Ok(Message::Close(_))) | None => {
                        break;
                    }
                    Some(Ok(Message::Ping(data))) => {
                        let _ = write.send(Message::Pong(data)).await;
                    }
                    Some(Ok(_)) => {
                        // Ignore other messages for now
                    }
                    Some(Err(e)) => {
                        debug!("Receive error: {}", e);
                        break;
                    }
                }
            }
        }
    }

    // Cleanup
    state.client_count.fetch_sub(1, Ordering::Relaxed);

    Ok(())
}
