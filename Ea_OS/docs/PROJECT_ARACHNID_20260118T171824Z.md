# PROJECT ARACHNID
## Implementation Documentation
**Timestamp:** 2026-01-18T17:18:24Z
**Status:** IMPLEMENTED / PENDING INTEGRATION

---

## I. Executive Summary

PROJECT ARACHNID is a kernel-resident, text-mode HTTP reconnaissance tool that treats the internet as a hostile raw data stream. It harvests HTTP content, passes it through an "Acid Bath" sanitizer (stripping HTML tags, scripts, and binary data), and streams pure ASCII text to the NEON-SYSTOLE dashboard.

**Design Philosophy:** The web is a trap. We are the spider.

---

## II. Architecture: Split-Brain

```
┌──────────────────────┐     BIO-STREAM      ┌──────────────────────┐
│     THE SPIDER       │ ═══════════════════>│     THE RETINA       │
│     (Kernel)         │   Ring Buffer       │     (UI)             │
│                      │   (64KB)            │                      │
│ - HTTP/1.0 GET       │                     │ - CRT Terminal       │
│ - Acid Bath Filter   │                     │ - Green Phosphor     │
│ - Baud Limiter       │                     │ - Auto-scroll        │
└──────────────────────┘                     └──────────────────────┘
```

### Rationale for Split-Brain

The existing BIO-S/1.0 protocol uses a **SeqLock** which is excellent for telemetry snapshots (dropping old frames is acceptable), but **catastrophic for text streams** (dropped frames = missing words).

PROJECT ARACHNID implements **BIO-STREAM**: a lock-free ring buffer that guarantees no data loss.

---

## III. Kernel Implementation

**File:** `muscles/referee-kernel/src/arachnid.rs`

### A. Spider State Machine

```rust
pub enum SpiderState {
    Idle,       // Awaiting target designation
    Tuning,     // Radio dial feedback delay
    Connecting, // TCP handshake
    Requesting, // Sending HTTP request
    Harvesting, // Streaming & sanitizing
    Dissolving, // Connection teardown
    Complete,   // Harvest finished
    Error,      // Error state
}
```

### B. Acid Bath Sanitizer

Zero-allocation streaming lexer that filters bytes in-flight:

- **DISCARD:** `<` to `>` (HTML tags), non-printable chars
- **PASS:** Alphanumeric, punctuation, whitespace, newlines
- **DECODE:** HTML entities (`&amp;` → `&`, `&#65;` → `A`)

```rust
pub fn dissolve(&mut self, byte: u8) -> Option<u8> {
    match self.state {
        AcidState::Text => match byte {
            b'<' => { self.state = AcidState::InTag; None }
            0x20..=0x7E => Some(byte),  // Printable ASCII
            b'\n' | b'\t' => Some(byte),
            _ => None,  // Dissolved
        },
        AcidState::InTag => {
            if byte == b'>' { self.state = AcidState::Text; }
            None  // All tag content dissolved
        }
        // ...
    }
}
```

### C. BIO-STREAM Ring Buffer

```rust
#[repr(C, align(4096))]
pub struct SharedRingBuffer {
    pub write_head: AtomicU32,  // Kernel increments
    pub read_tail: AtomicU32,   // UI increments
    pub capacity: u32,          // 65536 bytes
    pub state: u8,              // SpiderState
    pub bookmark_idx: u8,       // Current target
    pub _reserved: u16,
    pub data: [u8; 65536],      // Ring buffer
}
```

**Protocol:**
- **Producer (Kernel):** `buffer[head % cap] = byte; head++`
- **Consumer (UI):** Read from `tail` to `head`, update `tail`

### D. Tactile Physics Integration

The `NET_CHOKE` sovereign knob controls baud rate:

```rust
pub fn poll(&mut self, incoming: &[u8], ring: &SharedRingBuffer, choke: f32) -> usize {
    // Higher choke = slower accumulation = fewer bytes per tick
    let speed = 1.0 - choke.clamp(0.0, 0.99);
    self.throttle_accum += speed;

    if self.throttle_accum < 1.0 {
        return 0;  // Skip this cycle
    }
    self.throttle_accum -= 1.0;
    // Process one byte...
}
```

---

## IV. UI Implementation

**File:** `web/neon-systole.html`

### A. Visual Cortex Pane

CRT-styled terminal with:
- Green phosphor text (`#39ff14`)
- Scanline overlay (4px repeating gradient)
- Auto-scroll to bottom
- System message formatting

### B. Bookmark Table

```javascript
const BOOKMARKS = [
    { ip: '1.1.1.1', label: 'CLOUDFLARE_DNS', ... },
    { ip: '93.184.216.34', label: 'EXAMPLE_COM', ... },
    { ip: '192.168.1.1', label: 'LOCAL_GATEWAY', ... },
    { ip: '10.0.0.1', label: 'INTERNAL_WIKI', ... },
    { ip: '127.0.0.1:8080', label: 'LOCALHOST', ... },
];
```

### C. Context-Aware Sovereign Knobs

| Control | Telemetry Mode | ARACHNID Mode |
|---------|----------------|---------------|
| **ENTROPY_FLUX** | Entropy harvest rate | Radio Tuner (bookmark select) |
| **NET_CHOKE** | RX queue limit | Baud Rate Limiter |
| **MEM_ACID** | Page poisoning | Ignition (ARM + SLIDE to harvest) |

### D. Mode Switching

```javascript
// ARACHNID mode activates when MEM_ACID is armed and slid > 50%
if (slideValue > 0.5 && arachnid.spiderState === SpiderState.IDLE) {
    arachnid.mode = 'arachnid';
    arachnid.spiderState = SpiderState.CONNECTING;
    // Begin harvest...
}

// Deadman switch: releasing finger aborts connection
if (!armed) {
    arachnid.spiderState = SpiderState.IDLE;
}
```

---

## V. Files Modified/Created

| File | Action | Description |
|------|--------|-------------|
| `arachnid.rs` | **CREATED** | Spider state machine, Acid Bath, Ring Buffer |
| `main.rs` | **MODIFIED** | Added `mod arachnid;` declaration |
| `scheduler.rs` | **MODIFIED** | Phase 2: Added tick_arachnid() integration |
| `virtio_modern.rs` | **MODIFIED** | Phase 2: Made RX_BUFFERS public for Spider |
| `neon-systole.html` | **MODIFIED** | Visual Cortex pane, ARACHNID JS, mode switching |

---

## VI. Integration Status

### Phase 1 (COMPLETE)
- [x] Spider state machine
- [x] Acid Bath sanitizer (basic)
- [x] SharedRingBuffer (BIO-STREAM)
- [x] Visual Cortex pane (CSS/HTML)
- [x] ARACHNID JavaScript controller
- [x] Context-aware knob mapping
- [x] Demo mode simulation

### Phase 2 (COMPLETE)
- [x] BioStream with magic number (0xB105_73A1)
- [x] Proper memory barriers (fence(Acquire/Release))
- [x] Stateful AcidBath lexer (handles fragmented tags)
- [x] Script tag detection and blocking
- [x] Token Bucket throttle algorithm
- [x] Unit tests for fragmentation
- [x] Unit tests for ring buffer wrap-around
- [x] Spider poll wired into scheduler tick
- [x] JavaScript BIO-STREAM consumer
- [x] Demo/Live mode switching

### Pending Integration (Phase 3)
- [ ] Wire smoltcp TCP socket to Spider
- [ ] Implement actual HTTP request/response
- [ ] WebSocket bridge endpoint for BIO-STREAM

---

## VII. Security Considerations

1. **No arbitrary URLs:** Targets are hardcoded bookmarks only
2. **Acid Bath:** All HTML/JS stripped before reaching UI
3. **Script Blocking:** `<script>` tags dissolved across packet boundaries
4. **Deadman Switch:** Connection aborts immediately on release
5. **No cookies/storage:** Stateless HTTP/1.0 only
6. **Minimal fingerprint:** `User-Agent: EAOS/ARACHNID`
7. **Magic Validation:** BIO-STREAM frames validated with 0xB105_73A1

---

## VIII. Usage Instructions

1. **Select Target:** Rotate ENTROPY_FLUX to tune to a bookmark
2. **Arm System:** Flip the ARM toggle on MEM_ACID
3. **Ignite Harvest:** Slide MEM_ACID past 50% threshold
4. **Control Speed:** Adjust NET_CHOKE to slow down text stream
5. **Abort:** Release MEM_ACID slider (spring return = instant abort)

---

## IX. Phase 2 Technical Details

### BioStream Protocol

```rust
#[repr(C, align(4096))]
pub struct BioStream {
    pub magic: u32,            // 0xB105_73A1
    pub capacity: u32,         // 65536
    pub write_head: AtomicU32, // Kernel increments
    pub read_tail: AtomicU32,  // Bridge increments
    pub state: u8,             // SpiderState
    pub bookmark_idx: u8,      // Current target
    pub error_code: u8,        // Error (0 = OK)
    pub _reserved: u8,
    pub bytes_harvested: u32,  // Stats
    pub _padding: [u8; 8],
    pub data: [u8; 65536],     // Ring buffer
}
```

### Token Bucket Algorithm

```rust
pub struct TokenBucket {
    tokens: f32,       // Current tokens
    capacity: f32,     // Max burst (100)
    refill_rate: f32,  // Tokens/tick at choke=0 (100)
}

// Refill inversely proportional to choke
let refill = rate * (1.0 - choke);
tokens = (tokens + refill).min(capacity);
```

### Stateful Lexer States

```rust
enum LexerState {
    Text,          // Pass bytes
    TagOpen,       // Saw '<'
    TagName,       // Inside tag name
    InsideTag,     // Inside <...>
    InScript,      // Drop everything
    ScriptTagOpen, // In script, saw '<'
    ScriptClosing, // Checking </script>
    InEntity,      // Inside &xxx;
}
```

---

**END OF DOCUMENT**
