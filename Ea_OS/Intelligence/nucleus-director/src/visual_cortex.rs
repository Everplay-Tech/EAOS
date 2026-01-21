#![cfg_attr(not(feature = "std"), no_std)]

use muscle_contract::BootParameters;
use crate::font::{get_font, FONT_WIDTH, FONT_HEIGHT};

#[derive(Clone, Copy, Debug)]
pub struct Color {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl Color {
    pub const VOID: Color = Color { r: 5, g: 5, b: 5 };
    pub const LIFE: Color = Color { r: 0, g: 255, b: 65 }; // Matrix Green
    pub const ALERT: Color = Color { r: 255, g: 51, b: 51 };
    pub const TEXT: Color = Color { r: 204, g: 204, b: 204 };
    pub const SYNAPSE: Color = Color { r: 0, g: 191, b: 255 }; // Deep Sky Blue
    pub const DORMANT: Color = Color { r: 26, g: 26, b: 26 };

    pub fn to_u32(&self) -> u32 {
        ((self.r as u32) << 16) | ((self.g as u32) << 8) | (self.b as u32)
    }
}

/// The Visual Cortex - Handles rendering to the framebuffer
pub struct VisualCortex {
    base: *mut u32,
    pub width: u32,
    pub height: u32,
    pub stride: u32,
}

impl VisualCortex {
    /// Initialize the visual cortex from boot parameters
    pub fn new(params: &BootParameters) -> Option<Self> {
        if params.framebuffer_addr == 0 {
            return None;
        }
        
        Some(Self {
            base: params.framebuffer_addr as *mut u32,
            width: params.framebuffer_width,
            height: params.framebuffer_height,
            stride: params.framebuffer_stride,
        })
    }

    /// Clear screen to a color
    pub fn clear(&mut self, color: Color) {
        self.draw_rect(0, 0, self.width, self.height, color);
    }

    /// Draw a filled rectangle
    pub fn draw_rect(&mut self, x: u32, y: u32, w: u32, h: u32, color: Color) {
        let x_end = (x + w).min(self.width);
        let y_end = (y + h).min(self.height);
        let color_u32 = color.to_u32();

        for row in y..y_end {
            for col in x..x_end {
                unsafe {
                    let offset = (row * self.stride + col) as usize;
                    *self.base.add(offset) = color_u32;
                }
            }
        }
    }

    /// Draw a character using the embedded font
    pub fn draw_char(&mut self, x: u32, y: u32, c: char, color: Color) {
        let font = get_font();
        let char_idx = c as usize;
        if char_idx >= 256 { return; }

        let glyph_offset = char_idx * FONT_HEIGHT;
        let color_u32 = color.to_u32();

        for row in 0..FONT_HEIGHT {
            if glyph_offset + row >= font.len() { break; }
            let bits = font[glyph_offset + row];

            for col in 0..FONT_WIDTH {
                if (bits >> (7 - col)) & 1 == 1 {
                    let px = x + col as u32;
                    let py = y + row as u32;
                    if px < self.width && py < self.height {
                        unsafe {
                            let offset = (py * self.stride + px) as usize;
                            *self.base.add(offset) = color_u32;
                        }
                    }
                }
            }
        }
    }

    /// Draw a string
    pub fn draw_text(&mut self, x: u32, y: u32, text: &str, color: Color) {
        let mut cx = x;
        let mut cy = y;

        for c in text.chars() {
            if c == '\n' {
                cx = x;
                cy += FONT_HEIGHT as u32;
                continue;
            }
            
            if cx + (FONT_WIDTH as u32) > self.width {
                cx = x;
                cy += FONT_HEIGHT as u32;
            }
            
            if cy + (FONT_HEIGHT as u32) > self.height {
                break;
            }

            self.draw_char(cx, cy, c, color);
            cx += FONT_WIDTH as u32;
        }
    }
}
