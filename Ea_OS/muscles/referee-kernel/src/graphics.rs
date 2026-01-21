//! EAOS Graphics Driver - The Retina
//!
//! Software framebuffer implementation for UEFI GOP (Graphics Output Protocol).
//! No GPU acceleration - all rendering is CPU-bound with dirty rectangle optimization.

use uefi::prelude::*;
use uefi::proto::console::gop::{GraphicsOutput, ModeInfo, PixelFormat};

// ============================================================================
// Bioluminescent Palette - The Visual Language of EAOS
// ============================================================================

/// Color representation (BGRA format for UEFI GOP)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(C)]
pub struct Color {
    pub blue: u8,
    pub green: u8,
    pub red: u8,
    pub reserved: u8,
}

impl Color {
    pub const fn new(red: u8, green: u8, blue: u8) -> Self {
        Self { blue, green, red, reserved: 0 }
    }

    /// Convert to u32 for direct framebuffer write
    #[inline]
    pub const fn to_u32(self) -> u32 {
        (self.reserved as u32) << 24
            | (self.red as u32) << 16
            | (self.green as u32) << 8
            | (self.blue as u32)
    }
}

// The Manifesto Palette
impl Color {
    /// VOID - The primordial darkness (0x050505)
    pub const VOID: Color = Color::new(0x05, 0x05, 0x05);

    /// LIFE - Bioluminescent green, the color of living data (0x00FF41)
    pub const LIFE: Color = Color::new(0x00, 0xFF, 0x41);

    /// ALERT - Warning/rejection color (0xFF3333)
    pub const ALERT: Color = Color::new(0xFF, 0x33, 0x33);

    /// DORMANT - Unallocated/empty blocks (0x1A1A1A)
    pub const DORMANT: Color = Color::new(0x1A, 0x1A, 0x1A);

    /// SYNAPSE - Active process/communication (0x00BFFF)
    pub const SYNAPSE: Color = Color::new(0x00, 0xBF, 0xFF);

    /// TEXT - Primary text color (0xCCCCCC)
    pub const TEXT: Color = Color::new(0xCC, 0xCC, 0xCC);

    /// TEXT_DIM - Secondary/dimmed text (0x666666)
    pub const TEXT_DIM: Color = Color::new(0x66, 0x66, 0x66);
}

// ============================================================================
// Framebuffer - The Retina
// ============================================================================

/// Dirty rectangle for optimized redraws
#[derive(Clone, Copy, Debug)]
pub struct DirtyRect {
    pub x: usize,
    pub y: usize,
    pub width: usize,
    pub height: usize,
}

/// The UEFI GOP Framebuffer wrapper
pub struct Framebuffer {
    /// Raw pointer to video memory
    base: *mut u32,
    /// Screen width in pixels
    pub width: usize,
    /// Screen height in pixels
    pub height: usize,
    /// Stride (pixels per scanline, may differ from width)
    pub stride: usize,
    /// Pixel format
    pub format: PixelFormat,
}

impl Framebuffer {
    /// Initialize framebuffer from UEFI GOP
    ///
    /// # Safety
    /// This function obtains raw access to video memory. The caller must ensure
    /// the GOP protocol remains valid for the lifetime of the Framebuffer.
    pub unsafe fn from_gop(gop: &mut GraphicsOutput) -> Option<Self> {
        let mode_info = gop.current_mode_info();
        let mut fb = gop.frame_buffer();

        let base = fb.as_mut_ptr() as *mut u32;
        let (width, height) = mode_info.resolution();
        let stride = mode_info.stride();
        let format = mode_info.pixel_format();

        Some(Self {
            base,
            width,
            height,
            stride,
            format,
        })
    }

    /// Get the total size of the framebuffer in bytes
    pub fn size_bytes(&self) -> usize {
        self.stride * self.height * 4
    }

    /// Get raw base pointer
    pub fn base(&self) -> *mut u32 {
        self.base
    }

    // ========================================================================
    // Primitive Drawing Operations
    // ========================================================================

    /// Draw a single pixel (unsafe, no bounds checking for speed)
    ///
    /// # Safety
    /// Caller must ensure (x, y) is within framebuffer bounds.
    #[inline]
    pub unsafe fn draw_pixel_unsafe(&mut self, x: usize, y: usize, color: Color) {
        let offset = y * self.stride + x;
        *self.base.add(offset) = color.to_u32();
    }

    /// Draw a single pixel with bounds checking
    #[inline]
    pub fn draw_pixel(&mut self, x: usize, y: usize, color: Color) {
        if x < self.width && y < self.height {
            unsafe { self.draw_pixel_unsafe(x, y, color) }
        }
    }

    /// Fill a rectangle with a solid color (optimized for block rendering)
    pub fn draw_rect(&mut self, x: usize, y: usize, width: usize, height: usize, color: Color) {
        let color_val = color.to_u32();

        // Clamp to screen bounds
        let x_end = (x + width).min(self.width);
        let y_end = (y + height).min(self.height);

        if x >= self.width || y >= self.height {
            return;
        }

        for row in y..y_end {
            let row_start = row * self.stride + x;
            for col in 0..(x_end - x) {
                unsafe {
                    *self.base.add(row_start + col) = color_val;
                }
            }
        }
    }

    /// Fill a rectangle using horizontal line optimization
    /// Faster for larger rectangles due to better cache utilization
    pub fn fill_rect_fast(&mut self, x: usize, y: usize, width: usize, height: usize, color: Color) {
        let color_val = color.to_u32();

        let x_end = (x + width).min(self.width);
        let y_end = (y + height).min(self.height);
        let actual_width = x_end.saturating_sub(x);

        if actual_width == 0 || x >= self.width || y >= self.height {
            return;
        }

        for row in y..y_end {
            let row_offset = row * self.stride + x;
            // Write entire row at once
            for col in 0..actual_width {
                unsafe {
                    *self.base.add(row_offset + col) = color_val;
                }
            }
        }
    }

    /// Clear the entire screen to a color
    pub fn clear(&mut self, color: Color) {
        self.fill_rect_fast(0, 0, self.width, self.height, color);
    }

    /// Draw a horizontal line
    #[inline]
    pub fn draw_hline(&mut self, x: usize, y: usize, length: usize, color: Color) {
        self.draw_rect(x, y, length, 1, color);
    }

    /// Draw a vertical line
    #[inline]
    pub fn draw_vline(&mut self, x: usize, y: usize, length: usize, color: Color) {
        self.draw_rect(x, y, 1, length, color);
    }

    /// Draw a rectangle outline (unfilled)
    pub fn draw_rect_outline(&mut self, x: usize, y: usize, width: usize, height: usize, color: Color) {
        // Top
        self.draw_hline(x, y, width, color);
        // Bottom
        self.draw_hline(x, y + height.saturating_sub(1), width, color);
        // Left
        self.draw_vline(x, y, height, color);
        // Right
        self.draw_vline(x + width.saturating_sub(1), y, height, color);
    }

    // ========================================================================
    // Text Rendering (requires font module)
    // ========================================================================

    /// Draw a character at position using bitmap font
    pub fn draw_char(&mut self, x: usize, y: usize, c: char, font: &[u8], color: Color, bg: Option<Color>) {
        const FONT_WIDTH: usize = 8;
        const FONT_HEIGHT: usize = 16;

        let char_index = c as usize;
        if char_index >= 256 {
            return; // Only ASCII supported
        }

        let glyph_offset = char_index * FONT_HEIGHT;

        for row in 0..FONT_HEIGHT {
            if glyph_offset + row >= font.len() {
                break;
            }
            let glyph_row = font[glyph_offset + row];

            for col in 0..FONT_WIDTH {
                let px = x + col;
                let py = y + row;

                if px >= self.width || py >= self.height {
                    continue;
                }

                let bit = (glyph_row >> (7 - col)) & 1;
                if bit == 1 {
                    unsafe { self.draw_pixel_unsafe(px, py, color) }
                } else if let Some(bg_color) = bg {
                    unsafe { self.draw_pixel_unsafe(px, py, bg_color) }
                }
            }
        }
    }

    /// Draw a string at position
    pub fn draw_string(&mut self, x: usize, y: usize, s: &str, font: &[u8], color: Color, bg: Option<Color>) {
        const FONT_WIDTH: usize = 8;

        let mut cursor_x = x;
        for c in s.chars() {
            if c == '\n' {
                // Newline not supported in single-line draw
                continue;
            }
            self.draw_char(cursor_x, y, c, font, color, bg);
            cursor_x += FONT_WIDTH;

            if cursor_x >= self.width {
                break;
            }
        }
    }

    /// Draw a string with line wrapping
    pub fn draw_text(&mut self, x: usize, y: usize, s: &str, font: &[u8], color: Color, bg: Option<Color>) {
        const FONT_WIDTH: usize = 8;
        const FONT_HEIGHT: usize = 16;

        let mut cursor_x = x;
        let mut cursor_y = y;

        for c in s.chars() {
            if c == '\n' {
                cursor_x = x;
                cursor_y += FONT_HEIGHT;
                continue;
            }

            if cursor_x + FONT_WIDTH > self.width {
                cursor_x = x;
                cursor_y += FONT_HEIGHT;
            }

            if cursor_y + FONT_HEIGHT > self.height {
                break;
            }

            self.draw_char(cursor_x, cursor_y, c, font, color, bg);
            cursor_x += FONT_WIDTH;
        }
    }
}

// ============================================================================
// GOP Initialization Helper
// ============================================================================

/// Find and set the best available graphics mode
pub fn init_gop(bt: &BootServices) -> Option<uefi::Handle> {
    // Locate GOP protocol
    let gop_handle = bt.get_handle_for_protocol::<GraphicsOutput>().ok()?;
    Some(gop_handle)
}

/// Set the highest resolution mode available
pub fn set_best_mode(gop: &mut GraphicsOutput) -> Option<ModeInfo> {
    let mut best_mode = None;
    let mut best_area = 0usize;

    for mode in gop.modes() {
        let info = mode.info();
        let (w, h) = info.resolution();
        let area = w * h;

        // Prefer larger resolutions
        if area > best_area {
            best_area = area;
            best_mode = Some(mode);
        }
    }

    if let Some(mode) = best_mode {
        let info = mode.info();
        if gop.set_mode(&mode).is_ok() {
            return Some(info.clone());
        }
    }

    // Fallback to current mode
    Some(gop.current_mode_info())
}
