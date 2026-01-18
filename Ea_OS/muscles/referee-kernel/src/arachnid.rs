//! PROJECT ARACHNID // Secure Hypertext Harvester
//!
//! "The web is a trap. We are the spider."
//!
//! A kernel-resident, text-mode HTTP reconnaissance tool that treats the
//! internet as a hostile raw data stream. All content passes through the
//! "Acid Bath" sanitizer which strips HTML tags, scripts, and binary data.
//!
//! ## Architecture: Split-Brain
//!
//! ```text
//! ┌──────────────────┐     BIO-STREAM      ┌──────────────────┐
//! │   THE SPIDER     │ ═══════════════════>│   THE RETINA     │
//! │   (Kernel)       │   Ring Buffer       │   (UI)           │
//! │                  │                     │                  │
//! │ - HTTP/1.0 GET   │                     │ - CRT Terminal   │
//! │ - Acid Bath      │                     │ - Green Phosphor │
//! │ - Baud Limiter   │                     │ - Auto-scroll    │
//! └──────────────────┘                     └──────────────────┘
//! ```
//!
//! ## Tactile Physics Integration
//!
//! - ENTROPY_FLUX: Radio Tuner (bookmark selection)
//! - NET_CHOKE: Baud Rate Limiter (character-by-character at 100%)
//! - MEM_ACID: Ignition (ARM + SLIDE to connect, RELEASE to RST)
//!
//! ## Safety
//!
//! - Zero-allocation streaming sanitizer
//! - No DOM, no JavaScript, no cookies
//! - Hardcoded bookmark targets only (no arbitrary URL input)

use core::sync::atomic::{AtomicU32, Ordering};

// ============================================================================
// Spider State Machine
// ============================================================================

/// Spider operational states
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum SpiderState {
    /// Idle, awaiting target designation
    Idle = 0,
    /// Simulating radio tuning delay (entropy knob feedback)
    Tuning = 1,
    /// TCP handshake in progress
    Connecting = 2,
    /// Sending HTTP request
    Requesting = 3,
    /// Streaming and sanitizing response
    Harvesting = 4,
    /// Connection teardown
    Dissolving = 5,
    /// Harvest complete
    Complete = 6,
    /// Error state
    Error = 7,
}

impl SpiderState {
    /// Convert to display string for UI
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Idle => "IDLE",
            Self::Tuning => "TUNING",
            Self::Connecting => "CONNECTING",
            Self::Requesting => "REQUESTING",
            Self::Harvesting => "HARVESTING",
            Self::Dissolving => "DISSOLVING",
            Self::Complete => "COMPLETE",
            Self::Error => "ERROR",
        }
    }
}

// ============================================================================
// Hardcoded Bookmarks (Radio Dial Positions)
// ============================================================================

/// Bookmark entry: IP address and human-readable label
#[derive(Debug, Clone, Copy)]
pub struct Bookmark {
    /// IPv4 address as bytes
    pub ip: [u8; 4],
    /// Port (usually 80)
    pub port: u16,
    /// Human-readable label
    pub label: &'static str,
    /// HTTP Host header value
    pub host: &'static str,
    /// Path to request
    pub path: &'static str,
}

/// Hardcoded bookmark table (mapped to ENTROPY_FLUX knob)
pub const BOOKMARKS: &[Bookmark] = &[
    Bookmark {
        ip: [1, 1, 1, 1],
        port: 80,
        label: "CLOUDFLARE_DNS",
        host: "1.1.1.1",
        path: "/",
    },
    Bookmark {
        ip: [93, 184, 216, 34],
        port: 80,
        label: "EXAMPLE_COM",
        host: "example.com",
        path: "/",
    },
    Bookmark {
        ip: [192, 168, 1, 1],
        port: 80,
        label: "LOCAL_GATEWAY",
        host: "192.168.1.1",
        path: "/",
    },
    Bookmark {
        ip: [10, 0, 0, 1],
        port: 80,
        label: "INTERNAL_WIKI",
        host: "10.0.0.1",
        path: "/",
    },
    Bookmark {
        ip: [127, 0, 0, 1],
        port: 8080,
        label: "LOCALHOST",
        host: "localhost",
        path: "/",
    },
];

/// Map entropy value (0.0-1.0) to bookmark index
pub fn entropy_to_bookmark(entropy: f32) -> usize {
    let idx = (entropy * (BOOKMARKS.len() as f32)) as usize;
    idx.min(BOOKMARKS.len() - 1)
}

// ============================================================================
// Acid Bath Sanitizer
// ============================================================================

/// Streaming HTML sanitizer state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AcidState {
    /// Normal text mode
    Text,
    /// Inside HTML tag (discard until >)
    InTag,
    /// Inside HTML entity (&xxx;)
    InEntity,
}

/// The Acid Bath: Streaming sanitizer that strips HTML in-flight
pub struct AcidBath {
    state: AcidState,
    /// Entity buffer for decoding common entities
    entity_buf: [u8; 8],
    entity_len: usize,
}

impl AcidBath {
    pub const fn new() -> Self {
        Self {
            state: AcidState::Text,
            entity_buf: [0; 8],
            entity_len: 0,
        }
    }

    /// Reset sanitizer state
    pub fn reset(&mut self) {
        self.state = AcidState::Text;
        self.entity_len = 0;
    }

    /// Process a single byte through the acid bath
    ///
    /// Returns `Some(byte)` if the byte survives sanitization,
    /// `None` if it was dissolved (tag, binary, etc.)
    pub fn dissolve(&mut self, byte: u8) -> Option<u8> {
        match self.state {
            AcidState::Text => {
                match byte {
                    // Tag start: enter discard mode
                    b'<' => {
                        self.state = AcidState::InTag;
                        None
                    }
                    // Entity start
                    b'&' => {
                        self.state = AcidState::InEntity;
                        self.entity_len = 0;
                        None
                    }
                    // Printable ASCII passes through
                    0x20..=0x7E => Some(byte),
                    // Newline and tab pass through
                    b'\n' | b'\t' => Some(byte),
                    // Carriage return converted to newline
                    b'\r' => Some(b'\n'),
                    // Everything else is dissolved
                    _ => None,
                }
            }

            AcidState::InTag => {
                if byte == b'>' {
                    self.state = AcidState::Text;
                }
                // All tag content is dissolved
                None
            }

            AcidState::InEntity => {
                if byte == b';' {
                    // Entity complete, decode it
                    self.state = AcidState::Text;
                    self.decode_entity()
                } else if self.entity_len < 8 {
                    self.entity_buf[self.entity_len] = byte;
                    self.entity_len += 1;
                    None
                } else {
                    // Entity too long, abort
                    self.state = AcidState::Text;
                    None
                }
            }
        }
    }

    /// Decode common HTML entities
    fn decode_entity(&self) -> Option<u8> {
        let entity = &self.entity_buf[..self.entity_len];
        match entity {
            b"amp" => Some(b'&'),
            b"lt" => Some(b'<'),
            b"gt" => Some(b'>'),
            b"quot" => Some(b'"'),
            b"apos" => Some(b'\''),
            b"nbsp" => Some(b' '),
            // Numeric entities
            _ if entity.starts_with(b"#") => {
                self.decode_numeric_entity(&entity[1..])
            }
            // Unknown entity dissolved
            _ => None,
        }
    }

    /// Decode numeric entities (&#65; or &#x41;)
    fn decode_numeric_entity(&self, digits: &[u8]) -> Option<u8> {
        if digits.is_empty() {
            return None;
        }

        let (radix, start) = if digits[0] == b'x' || digits[0] == b'X' {
            (16, 1)
        } else {
            (10, 0)
        };

        let mut value: u32 = 0;
        for &d in &digits[start..] {
            let digit = match d {
                b'0'..=b'9' => d - b'0',
                b'a'..=b'f' if radix == 16 => d - b'a' + 10,
                b'A'..=b'F' if radix == 16 => d - b'A' + 10,
                _ => return None,
            };
            value = value * radix + digit as u32;
        }

        // Only pass through printable ASCII
        if (0x20..=0x7E).contains(&value) || value == 0x0A || value == 0x09 {
            Some(value as u8)
        } else {
            None
        }
    }
}

// ============================================================================
// BIO-STREAM: Lock-Free Ring Buffer
// ============================================================================

/// Ring buffer capacity (64KB)
pub const RING_BUFFER_CAPACITY: usize = 65536;

/// BIO-STREAM: Lock-free shared ring buffer for text streaming
///
/// This is separate from BIO-S/1.0 SeqLock because dropping frames
/// is unacceptable for a text stream (we'd lose words).
///
/// ## Protocol
///
/// - Kernel (Producer): `buffer[write_head % capacity] = byte; write_head++`
/// - UI (Consumer): Read from `read_tail` to `write_head`, update `read_tail`
///
/// ## Memory Layout (4KB aligned)
///
/// ```text
/// +0x0000: write_head (u32, atomic)
/// +0x0004: read_tail (u32, atomic)
/// +0x0008: capacity (u32)
/// +0x000C: state (u8, SpiderState)
/// +0x000D: bookmark_idx (u8)
/// +0x000E: reserved (u16)
/// +0x0010: data[65536]
/// ```
#[repr(C, align(4096))]
pub struct SharedRingBuffer {
    /// Write position (kernel increments)
    pub write_head: AtomicU32,
    /// Read position (UI increments)
    pub read_tail: AtomicU32,
    /// Buffer capacity
    pub capacity: u32,
    /// Current spider state (for UI status display)
    pub state: u8,
    /// Currently selected bookmark index
    pub bookmark_idx: u8,
    /// Reserved for alignment
    pub _reserved: u16,
    /// The actual data buffer
    pub data: [u8; RING_BUFFER_CAPACITY],
}

impl SharedRingBuffer {
    /// Create a new zeroed ring buffer
    pub const fn new() -> Self {
        Self {
            write_head: AtomicU32::new(0),
            read_tail: AtomicU32::new(0),
            capacity: RING_BUFFER_CAPACITY as u32,
            state: SpiderState::Idle as u8,
            bookmark_idx: 0,
            _reserved: 0,
            data: [0; RING_BUFFER_CAPACITY],
        }
    }

    /// Push a byte to the buffer (kernel side)
    ///
    /// Returns `true` if successful, `false` if buffer is full.
    pub fn push(&self, byte: u8) -> bool {
        let head = self.write_head.load(Ordering::Relaxed);
        let tail = self.read_tail.load(Ordering::Acquire);

        // Check if buffer is full
        if head.wrapping_sub(tail) >= self.capacity {
            return false;
        }

        // Write byte (safe because we own the write side)
        let idx = (head as usize) % (self.capacity as usize);
        unsafe {
            let ptr = self.data.as_ptr() as *mut u8;
            core::ptr::write_volatile(ptr.add(idx), byte);
        }

        // Memory barrier ensures write is visible before head update
        core::sync::atomic::fence(Ordering::Release);

        // Advance head
        self.write_head.store(head.wrapping_add(1), Ordering::Release);
        true
    }

    /// Push a string slice to the buffer
    pub fn push_str(&self, s: &str) -> usize {
        let mut written = 0;
        for byte in s.bytes() {
            if self.push(byte) {
                written += 1;
            } else {
                break;
            }
        }
        written
    }

    /// Get number of bytes available to read
    pub fn available(&self) -> u32 {
        let head = self.write_head.load(Ordering::Acquire);
        let tail = self.read_tail.load(Ordering::Relaxed);
        head.wrapping_sub(tail)
    }

    /// Clear the buffer
    pub fn clear(&self) {
        let head = self.write_head.load(Ordering::Relaxed);
        self.read_tail.store(head, Ordering::Release);
    }

    /// Update spider state (for UI polling)
    pub fn set_state(&mut self, state: SpiderState) {
        self.state = state as u8;
    }

    /// Update bookmark index
    pub fn set_bookmark(&mut self, idx: u8) {
        self.bookmark_idx = idx;
    }
}

// ============================================================================
// The Spider: HTTP/1.0 State Machine
// ============================================================================

/// Baud rate simulation accumulator threshold
const BAUD_THRESHOLD: f32 = 1.0;

/// The Spider: Kernel-side HTTP harvester
pub struct Arachnid {
    /// Current state
    state: SpiderState,
    /// Acid Bath sanitizer
    acid: AcidBath,
    /// Selected bookmark index
    bookmark_idx: usize,
    /// Baud rate throttle accumulator
    throttle_accum: f32,
    /// Tuning delay counter (for radio dial feel)
    tuning_delay: u32,
    /// HTTP response state
    http_state: HttpParseState,
    /// Bytes harvested counter
    bytes_harvested: u32,
}

/// HTTP response parsing state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum HttpParseState {
    /// Reading status line
    StatusLine,
    /// Reading headers
    Headers,
    /// Found \r\n, looking for another
    HeadersCr,
    /// Found \r\n\r, looking for \n
    HeadersCrLf,
    /// Reading body (pass to acid bath)
    Body,
}

impl Arachnid {
    /// Create a new idle spider
    pub const fn new() -> Self {
        Self {
            state: SpiderState::Idle,
            acid: AcidBath::new(),
            bookmark_idx: 0,
            throttle_accum: 0.0,
            tuning_delay: 0,
            http_state: HttpParseState::StatusLine,
            bytes_harvested: 0,
        }
    }

    /// Get current state
    pub fn state(&self) -> SpiderState {
        self.state
    }

    /// Get selected bookmark
    pub fn bookmark(&self) -> &'static Bookmark {
        &BOOKMARKS[self.bookmark_idx]
    }

    /// Tune to a bookmark (ENTROPY_FLUX knob)
    ///
    /// Returns the newly selected bookmark.
    pub fn tune(&mut self, entropy: f32) -> &'static Bookmark {
        let new_idx = entropy_to_bookmark(entropy);
        if new_idx != self.bookmark_idx && self.state == SpiderState::Idle {
            self.bookmark_idx = new_idx;
            self.state = SpiderState::Tuning;
            // Tuning delay proportional to dial movement
            self.tuning_delay = 30; // ~500ms at 60Hz
        }
        self.bookmark()
    }

    /// Arm and initiate connection (MEM_ACID deadman switch)
    ///
    /// Returns `true` if connection was initiated.
    pub fn ignite(&mut self, armed: bool, slide_value: f32) -> bool {
        if !armed {
            // Deadman released: immediate abort
            if self.state != SpiderState::Idle && self.state != SpiderState::Complete {
                self.abort();
            }
            return false;
        }

        // Slide must be > 0.5 to ignite
        if slide_value > 0.5 && self.state == SpiderState::Idle {
            self.state = SpiderState::Connecting;
            self.acid.reset();
            self.http_state = HttpParseState::StatusLine;
            self.bytes_harvested = 0;
            return true;
        }

        false
    }

    /// Abort current operation (RST)
    pub fn abort(&mut self) {
        self.state = SpiderState::Dissolving;
    }

    /// Reset to idle
    pub fn reset(&mut self) {
        self.state = SpiderState::Idle;
        self.acid.reset();
        self.http_state = HttpParseState::StatusLine;
        self.bytes_harvested = 0;
        self.throttle_accum = 0.0;
    }

    /// Main poll loop: Process incoming bytes with baud throttling
    ///
    /// # Arguments
    /// * `incoming` - Raw bytes from TCP socket
    /// * `ring` - Shared ring buffer for output
    /// * `choke` - NET_CHOKE value (0.0 = full speed, 1.0 = 300 baud)
    ///
    /// # Returns
    /// Number of bytes consumed from `incoming`
    pub fn poll(
        &mut self,
        incoming: &[u8],
        ring: &SharedRingBuffer,
        choke: f32,
    ) -> usize {
        // Handle tuning delay
        if self.state == SpiderState::Tuning {
            if self.tuning_delay > 0 {
                self.tuning_delay -= 1;
                return 0;
            }
            self.state = SpiderState::Idle;
        }

        // Only process in harvesting state
        if self.state != SpiderState::Harvesting {
            return 0;
        }

        let mut consumed = 0;

        for &byte in incoming {
            // TACTILE PHYSICS: Baud rate throttling
            // Higher choke = slower accumulation = fewer bytes per tick
            let speed = 1.0 - choke.clamp(0.0, 0.99);
            self.throttle_accum += speed;

            if self.throttle_accum < BAUD_THRESHOLD {
                // Skip this byte (will process next tick)
                break;
            }
            self.throttle_accum -= BAUD_THRESHOLD;

            consumed += 1;

            // HTTP response parsing
            match self.http_state {
                HttpParseState::StatusLine => {
                    if byte == b'\n' {
                        self.http_state = HttpParseState::Headers;
                    }
                }
                HttpParseState::Headers => {
                    if byte == b'\r' {
                        self.http_state = HttpParseState::HeadersCr;
                    }
                }
                HttpParseState::HeadersCr => {
                    if byte == b'\n' {
                        self.http_state = HttpParseState::HeadersCrLf;
                    } else {
                        self.http_state = HttpParseState::Headers;
                    }
                }
                HttpParseState::HeadersCrLf => {
                    if byte == b'\r' {
                        // Potential end of headers
                        self.http_state = HttpParseState::Body;
                    } else {
                        self.http_state = HttpParseState::Headers;
                    }
                }
                HttpParseState::Body => {
                    // Pass through acid bath
                    if let Some(clean_byte) = self.acid.dissolve(byte) {
                        if ring.push(clean_byte) {
                            self.bytes_harvested += 1;
                        }
                    }
                }
            }
        }

        consumed
    }

    /// Transition to requesting state (after TCP connect)
    pub fn connected(&mut self) {
        if self.state == SpiderState::Connecting {
            self.state = SpiderState::Requesting;
        }
    }

    /// Transition to harvesting state (after request sent)
    pub fn request_sent(&mut self) {
        if self.state == SpiderState::Requesting {
            self.state = SpiderState::Harvesting;
        }
    }

    /// Mark harvest as complete
    pub fn complete(&mut self) {
        self.state = SpiderState::Complete;
    }

    /// Mark error state
    pub fn error(&mut self) {
        self.state = SpiderState::Error;
    }

    /// Build HTTP/1.0 request for current bookmark
    ///
    /// Returns the request as a static byte slice.
    pub fn build_request(&self) -> ([u8; 256], usize) {
        let bm = self.bookmark();
        let mut buf = [0u8; 256];
        let mut len = 0;

        // GET /path HTTP/1.0\r\n
        len += copy_slice(&mut buf[len..], b"GET ");
        len += copy_slice(&mut buf[len..], bm.path.as_bytes());
        len += copy_slice(&mut buf[len..], b" HTTP/1.0\r\n");

        // Host: hostname\r\n
        len += copy_slice(&mut buf[len..], b"Host: ");
        len += copy_slice(&mut buf[len..], bm.host.as_bytes());
        len += copy_slice(&mut buf[len..], b"\r\n");

        // User-Agent (minimal fingerprint)
        len += copy_slice(&mut buf[len..], b"User-Agent: EAOS/ARACHNID\r\n");

        // Connection: close (HTTP/1.0 style)
        len += copy_slice(&mut buf[len..], b"Connection: close\r\n");

        // End of headers
        len += copy_slice(&mut buf[len..], b"\r\n");

        (buf, len)
    }

    /// Get bytes harvested count
    pub fn bytes_harvested(&self) -> u32 {
        self.bytes_harvested
    }
}

/// Helper: Copy slice to destination, return bytes written
fn copy_slice(dst: &mut [u8], src: &[u8]) -> usize {
    let len = dst.len().min(src.len());
    dst[..len].copy_from_slice(&src[..len]);
    len
}

// ============================================================================
// Global Instances
// ============================================================================

/// Global shared ring buffer for BIO-STREAM
pub static mut ARACHNID_STREAM: SharedRingBuffer = SharedRingBuffer::new();

/// Global spider instance
pub static mut SPIDER: Arachnid = Arachnid::new();

// ============================================================================
// Integration Functions
// ============================================================================

/// Update spider state in ring buffer (call after state changes)
pub unsafe fn sync_state() {
    ARACHNID_STREAM.state = SPIDER.state() as u8;
    ARACHNID_STREAM.bookmark_idx = SPIDER.bookmark_idx as u8;
}

/// Push system message to stream
pub unsafe fn push_system_message(msg: &str) {
    ARACHNID_STREAM.push_str("> ");
    ARACHNID_STREAM.push_str(msg);
    ARACHNID_STREAM.push(b'\n');
}
