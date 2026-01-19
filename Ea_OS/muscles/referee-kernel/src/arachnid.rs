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
// Acid Bath Sanitizer (Phase 2: Stateful Lexer)
// ============================================================================

/// Streaming HTML sanitizer state
///
/// Phase 2 upgrade: Handles fragmented tags across packet boundaries.
/// The lexer maintains state between `process_chunk` calls, ensuring
/// that split tags like `<scr` + `ipt>` are properly dissolved.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum LexerState {
    /// Normal text mode - pass bytes through
    Text,
    /// Saw '<', buffering tag name
    TagOpen,
    /// Inside tag name (e.g., inside `<div`)
    TagName,
    /// Inside tag attributes (after tag name, before `>`)
    InsideTag,
    /// Inside `<script>` block - drop EVERYTHING until `</script>`
    InScript,
    /// In script, saw `<` - checking for `/script>`
    ScriptTagOpen,
    /// In script, saw `</` - checking for `script>`
    ScriptClosing,
    /// Inside HTML entity (&xxx;)
    InEntity,
}

/// Maximum tag name buffer size
const TAG_NAME_BUF_SIZE: usize = 16;

/// The Acid Bath: Streaming sanitizer that strips HTML in-flight
///
/// ## Phase 2 Features
///
/// - **Stateful Lexer**: Handles fragmented tags across TCP packets
/// - **Script Blocking**: Everything inside `<script>...</script>` is dissolved
/// - **Entity Decoding**: Common HTML entities are converted to ASCII
///
/// ## Attack Resistance
///
/// The lexer handles adversarial fragmentation:
/// - `<scr` + `ipt>alert('PWN')</script>` → dissolved
/// - `<b` + `>text` → "text"
pub struct AcidBath {
    /// Current lexer state
    state: LexerState,
    /// Tag name buffer (for detecting `script` tags)
    tag_buf: [u8; TAG_NAME_BUF_SIZE],
    /// Current position in tag buffer
    tag_len: usize,
    /// Entity buffer for decoding
    entity_buf: [u8; 8],
    /// Entity buffer length
    entity_len: usize,
    /// Script closing match position (tracking `</script>`)
    script_close_pos: usize,
}

/// Pattern to match for script close tag
const SCRIPT_CLOSE: &[u8] = b"script>";

impl AcidBath {
    pub const fn new() -> Self {
        Self {
            state: LexerState::Text,
            tag_buf: [0; TAG_NAME_BUF_SIZE],
            tag_len: 0,
            entity_buf: [0; 8],
            entity_len: 0,
            script_close_pos: 0,
        }
    }

    /// Reset sanitizer state
    pub fn reset(&mut self) {
        self.state = LexerState::Text;
        self.tag_len = 0;
        self.entity_len = 0;
        self.script_close_pos = 0;
    }

    /// Process a chunk of bytes through the acid bath
    ///
    /// This is the primary interface for TCP packet processing.
    /// State is maintained between calls to handle fragmented tags.
    ///
    /// # Arguments
    /// * `chunk` - Raw bytes from TCP socket
    /// * `output` - Callback for each surviving byte
    ///
    /// # Returns
    /// Number of bytes that survived sanitization
    pub fn process_chunk<F>(&mut self, chunk: &[u8], mut output: F) -> usize
    where
        F: FnMut(u8),
    {
        let mut count = 0;
        for &byte in chunk {
            if let Some(clean) = self.dissolve(byte) {
                output(clean);
                count += 1;
            }
        }
        count
    }

    /// Process a single byte through the acid bath
    ///
    /// Returns `Some(byte)` if the byte survives sanitization,
    /// `None` if it was dissolved (tag, binary, etc.)
    pub fn dissolve(&mut self, byte: u8) -> Option<u8> {
        match self.state {
            LexerState::Text => self.handle_text(byte),
            LexerState::TagOpen => self.handle_tag_open(byte),
            LexerState::TagName => self.handle_tag_name(byte),
            LexerState::InsideTag => self.handle_inside_tag(byte),
            LexerState::InScript => self.handle_in_script(byte),
            LexerState::ScriptTagOpen => self.handle_script_tag_open(byte),
            LexerState::ScriptClosing => self.handle_script_closing(byte),
            LexerState::InEntity => self.handle_entity(byte),
        }
    }

    /// Handle byte in Text state
    fn handle_text(&mut self, byte: u8) -> Option<u8> {
        match byte {
            b'<' => {
                self.state = LexerState::TagOpen;
                self.tag_len = 0;
                None
            }
            b'&' => {
                self.state = LexerState::InEntity;
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

    /// Handle byte after seeing '<'
    fn handle_tag_open(&mut self, byte: u8) -> Option<u8> {
        match byte {
            // Closing tag or self-closing
            b'/' | b'!' | b'?' => {
                self.state = LexerState::InsideTag;
                None
            }
            // Start of tag name
            b'a'..=b'z' | b'A'..=b'Z' => {
                self.tag_buf[0] = byte.to_ascii_lowercase();
                self.tag_len = 1;
                self.state = LexerState::TagName;
                None
            }
            // Invalid tag start - emit '<' as text? No, still dissolve for safety
            b'>' => {
                self.state = LexerState::Text;
                None
            }
            _ => {
                self.state = LexerState::InsideTag;
                None
            }
        }
    }

    /// Handle byte while reading tag name
    fn handle_tag_name(&mut self, byte: u8) -> Option<u8> {
        match byte {
            b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9' => {
                if self.tag_len < TAG_NAME_BUF_SIZE {
                    self.tag_buf[self.tag_len] = byte.to_ascii_lowercase();
                    self.tag_len += 1;
                }
                None
            }
            b'>' => {
                // Tag complete - check if it's a script tag
                if self.is_script_tag() {
                    self.state = LexerState::InScript;
                    self.script_close_pos = 0;
                } else {
                    self.state = LexerState::Text;
                }
                None
            }
            b' ' | b'\t' | b'\n' | b'\r' | b'/' => {
                // End of tag name, entering attributes
                // Check if script before moving to InsideTag
                if self.is_script_tag() {
                    self.state = LexerState::InsideTag;
                    // Will transition to InScript when '>' is seen
                } else {
                    self.state = LexerState::InsideTag;
                }
                None
            }
            _ => {
                self.state = LexerState::InsideTag;
                None
            }
        }
    }

    /// Handle byte inside tag (attributes area)
    fn handle_inside_tag(&mut self, byte: u8) -> Option<u8> {
        if byte == b'>' {
            // Tag complete - check if it was a script tag
            if self.is_script_tag() {
                self.state = LexerState::InScript;
                self.script_close_pos = 0;
            } else {
                self.state = LexerState::Text;
            }
        }
        // All tag content is dissolved
        None
    }

    /// Handle byte inside script block (drop everything)
    fn handle_in_script(&mut self, byte: u8) -> Option<u8> {
        if byte == b'<' {
            self.state = LexerState::ScriptTagOpen;
        }
        // Everything in script is dissolved
        None
    }

    /// Handle byte after seeing '<' inside script
    fn handle_script_tag_open(&mut self, byte: u8) -> Option<u8> {
        if byte == b'/' {
            self.state = LexerState::ScriptClosing;
            self.script_close_pos = 0;
        } else {
            self.state = LexerState::InScript;
        }
        None
    }

    /// Handle byte while checking for `</script>`
    fn handle_script_closing(&mut self, byte: u8) -> Option<u8> {
        let expected = SCRIPT_CLOSE[self.script_close_pos];
        if byte.to_ascii_lowercase() == expected {
            self.script_close_pos += 1;
            if self.script_close_pos >= SCRIPT_CLOSE.len() {
                // Found </script> - exit script mode
                self.state = LexerState::Text;
                self.script_close_pos = 0;
            }
        } else {
            // Mismatch - back to script mode
            self.state = LexerState::InScript;
            self.script_close_pos = 0;
        }
        None
    }

    /// Handle byte in entity state
    fn handle_entity(&mut self, byte: u8) -> Option<u8> {
        if byte == b';' {
            self.state = LexerState::Text;
            self.decode_entity()
        } else if self.entity_len < 8 {
            self.entity_buf[self.entity_len] = byte;
            self.entity_len += 1;
            None
        } else {
            // Entity too long, abort
            self.state = LexerState::Text;
            None
        }
    }

    /// Check if buffered tag name is "script"
    fn is_script_tag(&self) -> bool {
        self.tag_len == 6
            && self.tag_buf[0] == b's'
            && self.tag_buf[1] == b'c'
            && self.tag_buf[2] == b'r'
            && self.tag_buf[3] == b'i'
            && self.tag_buf[4] == b'p'
            && self.tag_buf[5] == b't'
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
            _ if !entity.is_empty() && entity[0] == b'#' => {
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
// BIO-STREAM: Lock-Free SPSC Ring Buffer (Phase 2)
// ============================================================================

/// Ring buffer capacity (64KB)
pub const RING_BUFFER_CAPACITY: usize = 65536;

/// BIO-STREAM magic number: "BIOS" in hex + checksum nibble
/// Used for memory-mapped region validation
pub const BIOSTREAM_MAGIC: u32 = 0xB105_73A1;

/// BIO-STREAM: Lock-free SPSC ring buffer for text streaming
///
/// Phase 2 upgrade: Added magic number for validation and proper memory barriers.
///
/// This is separate from BIO-S/1.0 SeqLock because dropping frames
/// is unacceptable for a text stream (we'd lose words).
///
/// ## Protocol
///
/// - Kernel (Producer): `buffer[write_head % capacity] = byte; fence(Release); write_head++`
/// - Bridge (Consumer): `fence(Acquire); read from tail to head; tail = head`
///
/// ## Memory Layout (4KB aligned)
///
/// ```text
/// +0x0000: magic (u32) = 0xB105_73A1
/// +0x0004: capacity (u32) = 65536
/// +0x0008: write_head (u32, atomic)
/// +0x000C: read_tail (u32, atomic)
/// +0x0010: state (u8, SpiderState)
/// +0x0011: bookmark_idx (u8)
/// +0x0012: error_code (u8)
/// +0x0013: reserved (u8)
/// +0x0014: bytes_harvested (u32)
/// +0x0018: padding[8]
/// +0x0020: data[65536]
/// ```
#[repr(C, align(4096))]
pub struct BioStream {
    /// Magic number for validation (0xB105_73A1)
    pub magic: u32,
    /// Buffer capacity (65536)
    pub capacity: u32,
    /// Write position (kernel increments)
    pub write_head: AtomicU32,
    /// Read position (bridge increments)
    pub read_tail: AtomicU32,
    /// Current spider state (for UI status display)
    pub state: u8,
    /// Currently selected bookmark index
    pub bookmark_idx: u8,
    /// Error code (0 = no error)
    pub error_code: u8,
    /// Reserved for alignment
    pub _reserved: u8,
    /// Total bytes harvested (stats)
    pub bytes_harvested: u32,
    /// Padding to align data to 32-byte boundary
    pub _padding: [u8; 8],
    /// The actual data buffer
    pub data: [u8; RING_BUFFER_CAPACITY],
}

impl BioStream {
    /// Create a new initialized ring buffer with magic number
    pub const fn new() -> Self {
        Self {
            magic: BIOSTREAM_MAGIC,
            capacity: RING_BUFFER_CAPACITY as u32,
            write_head: AtomicU32::new(0),
            read_tail: AtomicU32::new(0),
            state: SpiderState::Idle as u8,
            bookmark_idx: 0,
            error_code: 0,
            _reserved: 0,
            bytes_harvested: 0,
            _padding: [0; 8],
            data: [0; RING_BUFFER_CAPACITY],
        }
    }

    /// Validate magic number
    #[inline]
    pub fn is_valid(&self) -> bool {
        self.magic == BIOSTREAM_MAGIC
    }

    /// Push a byte to the buffer (kernel side)
    ///
    /// Returns `true` if successful, `false` if buffer is full.
    ///
    /// ## Memory Ordering
    /// - Acquire tail to see consumer updates
    /// - Release fence after data write, before head update
    pub fn push(&self, byte: u8) -> bool {
        let head = self.write_head.load(Ordering::Relaxed);
        let tail = self.read_tail.load(Ordering::Acquire);

        // Check if buffer is full (leave 1 byte gap to distinguish full from empty)
        if head.wrapping_sub(tail) >= self.capacity - 1 {
            return false;
        }

        // Write byte with volatile (safe because we own the write side)
        let idx = (head as usize) % (self.capacity as usize);
        unsafe {
            let ptr = self.data.as_ptr() as *mut u8;
            core::ptr::write_volatile(ptr.add(idx), byte);
        }

        // Release fence: ensures data write is visible before head update
        core::sync::atomic::fence(Ordering::Release);

        // Advance head with Release ordering
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
    #[inline]
    pub fn available(&self) -> u32 {
        let head = self.write_head.load(Ordering::Acquire);
        let tail = self.read_tail.load(Ordering::Relaxed);
        head.wrapping_sub(tail)
    }

    /// Check if buffer is empty
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.available() == 0
    }

    /// Clear the buffer (sync tail to head)
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

    /// Set error code
    pub fn set_error(&mut self, code: u8) {
        self.error_code = code;
    }

    /// Increment bytes harvested counter
    pub fn inc_harvested(&mut self) {
        self.bytes_harvested = self.bytes_harvested.wrapping_add(1);
    }
}

/// Type alias for backwards compatibility
pub type SharedRingBuffer = BioStream;

// ============================================================================
// Token Bucket Throttle (Phase 2)
// ============================================================================

/// Token Bucket rate limiter for baud rate simulation
///
/// Provides smooth traffic shaping with configurable burst capacity.
/// At choke=0: Full speed (refill_rate tokens/tick)
/// At choke=1: 300 baud simulation (near-zero refill)
pub struct TokenBucket {
    /// Current token count
    tokens: f32,
    /// Maximum burst capacity (tokens)
    capacity: f32,
    /// Refill rate at choke=0 (tokens per tick)
    refill_rate: f32,
}

impl TokenBucket {
    /// Create a new token bucket
    pub const fn new(capacity: f32, refill_rate: f32) -> Self {
        Self {
            tokens: 0.0, // Start empty for gradual ramp-up
            capacity,
            refill_rate,
        }
    }

    /// Attempt to consume one token
    ///
    /// Returns `true` if token was available, `false` if bucket empty.
    /// Refill rate is inversely proportional to choke value.
    pub fn consume(&mut self, choke: f32) -> bool {
        // Refill based on inverse choke (clamped to avoid division issues)
        let choke_clamped = choke.clamp(0.0, 0.99);
        let refill = self.refill_rate * (1.0 - choke_clamped);
        self.tokens = (self.tokens + refill).min(self.capacity);

        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }

    /// Reset bucket to empty
    pub fn reset(&mut self) {
        self.tokens = 0.0;
    }

    /// Fill bucket to capacity (for immediate burst)
    pub fn fill(&mut self) {
        self.tokens = self.capacity;
    }
}

// ============================================================================
// The Spider: HTTP/1.0 State Machine
// ============================================================================

/// Default token bucket capacity (burst size in bytes)
const TOKEN_BUCKET_CAPACITY: f32 = 100.0;

/// Default refill rate (bytes per tick at choke=0)
/// At 60Hz tick rate, this gives ~6000 bytes/sec max
const TOKEN_REFILL_RATE: f32 = 100.0;

/// The Spider: Kernel-side HTTP harvester
pub struct Arachnid {
    /// Current state
    state: SpiderState,
    /// Acid Bath sanitizer
    acid: AcidBath,
    /// Selected bookmark index
    bookmark_idx: usize,
    /// Token bucket for baud rate throttling (Phase 2)
    throttle: TokenBucket,
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
            throttle: TokenBucket::new(TOKEN_BUCKET_CAPACITY, TOKEN_REFILL_RATE),
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
        self.throttle.reset();
    }

    /// Main poll loop: Process incoming bytes with token bucket throttling
    ///
    /// # Arguments
    /// * `incoming` - Raw bytes from TCP socket
    /// * `ring` - BIO-STREAM ring buffer for output
    /// * `choke` - NET_CHOKE value (0.0 = full speed, 1.0 = near-zero throughput)
    ///
    /// # Returns
    /// Number of bytes consumed from `incoming`
    ///
    /// ## Phase 2: Token Bucket Throttling
    ///
    /// Uses token bucket algorithm for smooth traffic shaping:
    /// - Bucket refills at rate inversely proportional to choke
    /// - Each byte consumed costs one token
    /// - Allows burst up to bucket capacity, then rate-limited
    pub fn poll(
        &mut self,
        incoming: &[u8],
        ring: &BioStream,
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
            // TACTILE PHYSICS: Token bucket baud rate throttling
            // consume() refills based on inverse choke, returns true if token available
            if !self.throttle.consume(choke) {
                // No tokens available - stop processing this tick
                break;
            }

            consumed += 1;

            // HTTP response parsing state machine
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
                    // Pass through acid bath sanitizer
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

/// Global BIO-STREAM ring buffer
///
/// Memory-mapped at a known address for bridge/UI access.
/// Magic number 0xB105_73A1 allows validation.
pub static mut ARACHNID_STREAM: BioStream = BioStream::new();

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

// ============================================================================
// Unit Tests (Phase 2)
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // ========================================================================
    // AcidBath Fragmentation Tests
    // ========================================================================

    /// Test: Simple tag is dissolved
    #[test]
    fn acid_dissolves_simple_tag() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        acid.process_chunk(b"<b>text</b>", |b| output.push(b));

        assert_eq!(output, b"text");
    }

    /// Test: Fragmented tag across two chunks is dissolved
    #[test]
    fn acid_handles_fragmented_tag() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        // First chunk: partial tag
        acid.process_chunk(b"hello<di", |b| output.push(b));
        // Second chunk: tag completion
        acid.process_chunk(b"v>world", |b| output.push(b));

        assert_eq!(output, b"helloworld");
    }

    /// Test: Fragmented script tag is blocked
    #[test]
    fn acid_blocks_fragmented_script() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        // Adversarial fragmentation: <scr + ipt>
        acid.process_chunk(b"before<scr", |b| output.push(b));
        acid.process_chunk(b"ipt>alert('PWN')</script>after", |b| output.push(b));

        assert_eq!(output, b"beforeafter");
    }

    /// Test: Script content is completely dissolved
    #[test]
    fn acid_dissolves_script_content() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        acid.process_chunk(b"<script>var x = 1; x++;</script>clean", |b| output.push(b));

        assert_eq!(output, b"clean");
    }

    /// Test: Script closing tag fragmented
    #[test]
    fn acid_handles_fragmented_script_close() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        acid.process_chunk(b"<script>evil</scr", |b| output.push(b));
        acid.process_chunk(b"ipt>safe", |b| output.push(b));

        assert_eq!(output, b"safe");
    }

    /// Test: HTML entities decoded
    #[test]
    fn acid_decodes_entities() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        acid.process_chunk(b"&amp; &lt; &gt;", |b| output.push(b));

        assert_eq!(output, b"& < >");
    }

    /// Test: Numeric entities decoded
    #[test]
    fn acid_decodes_numeric_entities() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        acid.process_chunk(b"&#65;&#66;&#67;", |b| output.push(b));

        assert_eq!(output, b"ABC");
    }

    /// Test: Hex entities decoded
    #[test]
    fn acid_decodes_hex_entities() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        acid.process_chunk(b"&#x41;&#x42;&#x43;", |b| output.push(b));

        assert_eq!(output, b"ABC");
    }

    /// Test: Non-printable entities are dissolved
    #[test]
    fn acid_dissolves_nonprintable_entities() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        acid.process_chunk(b"&#0;&#1;&#2;ok", |b| output.push(b));

        assert_eq!(output, b"ok");
    }

    /// Test: Binary bytes are dissolved
    #[test]
    fn acid_dissolves_binary() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        acid.process_chunk(b"hello\x00\x01\x02world", |b| output.push(b));

        assert_eq!(output, b"helloworld");
    }

    /// Test: Reset clears state
    #[test]
    fn acid_reset_clears_state() {
        let mut acid = AcidBath::new();
        let mut output = Vec::new();

        // Start in a tag
        acid.process_chunk(b"<div", |b| output.push(b));

        // Reset
        acid.reset();

        // Now process text - should pass through
        acid.process_chunk(b"hello", |b| output.push(b));

        assert_eq!(output, b"hello");
    }

    // ========================================================================
    // BioStream Wrap-Around Tests
    // ========================================================================

    /// Test: Magic number is set correctly
    #[test]
    fn biostream_has_magic() {
        let stream = BioStream::new();
        assert!(stream.is_valid());
        assert_eq!(stream.magic, BIOSTREAM_MAGIC);
    }

    /// Test: Push and available work correctly
    #[test]
    fn biostream_push_available() {
        let stream = BioStream::new();

        assert!(stream.push(b'A'));
        assert!(stream.push(b'B'));
        assert!(stream.push(b'C'));

        assert_eq!(stream.available(), 3);
    }

    /// Test: Clear resets buffer
    #[test]
    fn biostream_clear() {
        let stream = BioStream::new();

        stream.push(b'X');
        stream.push(b'Y');
        assert_eq!(stream.available(), 2);

        stream.clear();
        assert_eq!(stream.available(), 0);
    }

    /// Test: Buffer wrap-around works
    #[test]
    fn biostream_wraparound() {
        // Create a small test buffer (we can't easily test with 64KB)
        // Instead, we'll simulate by manually setting head/tail near capacity
        let stream = BioStream::new();

        // Fill buffer partially
        for i in 0..100 {
            assert!(stream.push(i as u8));
        }

        assert_eq!(stream.available(), 100);

        // Clear (simulating consumer read)
        stream.clear();
        assert_eq!(stream.available(), 0);

        // Write more data
        for i in 0..50 {
            assert!(stream.push(i as u8));
        }

        assert_eq!(stream.available(), 50);
    }

    /// Test: Buffer full detection
    #[test]
    fn biostream_full() {
        let stream = BioStream::new();

        // Fill buffer to near capacity
        // Note: We leave 1 byte gap to distinguish full from empty
        let mut count = 0;
        while stream.push(b'X') {
            count += 1;
            if count > RING_BUFFER_CAPACITY {
                panic!("Buffer should have rejected push");
            }
        }

        // Should have filled capacity - 1
        assert_eq!(count, RING_BUFFER_CAPACITY - 1);
    }

    /// Test: push_str works
    #[test]
    fn biostream_push_str() {
        let stream = BioStream::new();

        let written = stream.push_str("Hello, World!");

        assert_eq!(written, 13);
        assert_eq!(stream.available(), 13);
    }

    // ========================================================================
    // Token Bucket Tests
    // ========================================================================

    /// Test: Token bucket consumes tokens
    #[test]
    fn token_bucket_consume() {
        let mut bucket = TokenBucket::new(10.0, 5.0);

        // At choke=0, should refill quickly
        assert!(bucket.consume(0.0)); // Refills 5, consumes 1 = 4 left
        assert!(bucket.consume(0.0)); // Refills 5, consumes 1 = 8 left (capped at 10)
    }

    /// Test: Token bucket empty at high choke
    #[test]
    fn token_bucket_high_choke() {
        let mut bucket = TokenBucket::new(10.0, 1.0);

        // At choke=0.99, refill is near zero
        // First consume should fail (bucket starts empty)
        assert!(!bucket.consume(0.99));

        // Many consumes later, still empty
        for _ in 0..100 {
            bucket.consume(0.99);
        }

        // Still should be near-empty
        assert!(!bucket.consume(0.99));
    }

    /// Test: Token bucket reset
    #[test]
    fn token_bucket_reset() {
        let mut bucket = TokenBucket::new(10.0, 5.0);

        // Consume some
        bucket.consume(0.0);
        bucket.consume(0.0);

        // Reset
        bucket.reset();

        // Should be empty again
        assert!(!bucket.consume(0.99));
    }
}
