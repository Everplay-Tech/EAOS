#![no_std]
#![no_main]

use uefi::prelude::*;
use uefi::proto::console::gop::GraphicsOutput;

mod capability;
mod cell;
mod memory;
mod uart;
mod scheduler;
mod errors;
mod audit;
mod syscall;
mod bridge;
mod storage;
mod graphics;
mod font;
mod input;
mod outbox;
mod pci;
mod task;

use crate::uart::Uart;
use crate::capability::ChaosCapability;
use crate::cell::Cell;
use crate::scheduler::run_scheduler_with_net;
use crate::graphics::{Color, Framebuffer};
use crate::font::{VGA_FONT_8X16, FONT_HEIGHT};
use crate::virtio_phy::init_timer;

const N_CELLS: usize = 50;

/// Braid magic header bytes (0xB8AD)
#[allow(dead_code)]
const BRAID_MAGIC: [u8; 2] = [0xB8, 0xAD];

/// Block size for PermFS (4KB)
const BLOCK_SIZE: usize = 4096;

/// Total blocks in 256MB disk
const TOTAL_BLOCKS: usize = 256 * 1024 * 1024 / BLOCK_SIZE; // 65536 blocks

// ============================================================================
// Visual Constants
// ============================================================================

/// Block cell size in pixels for the lattice visualizer
const CELL_SIZE: usize = 4;
/// Gap between cells
const CELL_GAP: usize = 1;
/// Total cell pitch (size + gap)
const CELL_PITCH: usize = CELL_SIZE + CELL_GAP;
/// Lattice padding from screen edge
const LATTICE_PADDING: usize = 20;
/// Shell prompt Y position (from bottom)
const SHELL_Y_OFFSET: usize = 60;

#[entry]
fn efi_main(_image: Handle, mut st: SystemTable<Boot>) -> Status {
    // Initialize UEFI services (uefi 0.24 API)
    if uefi_services::init(&mut st).is_err() {
        return Status::LOAD_ERROR;
    }

    let bt = st.boot_services();
    let mut uart = Uart::new();
    if uart.init().is_err() {
        return Status::LOAD_ERROR;
    }

    uart.log("INFO", "Ea referee v3.0 awakens - production ready");

    // ========================================================================
    // Phase 6.5: Initialize RDTSC Monotonic Timer
    // ========================================================================
    init_timer();
    uart.log("INFO", "RDTSC timer initialized - epoch set");

    // ========================================================================
    // Scan PCI Bus for Virtio Devices
    // ========================================================================
    uart.log("INFO", "Scanning PCI bus for hardware...");

    let mut net_driver: Option<virtio_modern::VirtioModern> = None;

    unsafe {
        let scan_result = pci::scan_pci_bus();
        uart.log("INFO", "PCI scan complete");

        if let Some(ref device) = scan_result.virtio_net {
            let mut bdf_buf = [0u8; 8];
            let bdf_str = device.address.format_bdf(&mut bdf_buf);
            uart.log("PCI", "Found Virtio-Net at BDF:");
            uart.log("PCI", bdf_str);

            // Parse PCI capabilities to find MMIO regions
            uart.log("PCI", "Parsing capabilities...");

            match pci_modern::parse_virtio_capabilities(&device.address) {
                Ok(caps) => {
                    if !caps.is_complete() {
                        uart.log("ERROR", "Missing required Virtio capabilities");
                    } else {
                        uart.log("PCI", "All Virtio capabilities found");

                        // Log discovered capabilities
                        if let Some(ref c) = caps.common_cfg {
                            uart.log("PCI", c.format_type());
                        }
                        if let Some(ref c) = caps.notify_cfg {
                            uart.log("PCI", c.format_type());
                        }
                        if let Some(ref c) = caps.isr_cfg {
                            uart.log("PCI", c.format_type());
                        }
                        if let Some(ref c) = caps.device_cfg {
                            uart.log("PCI", c.format_type());
                        }

                        // Resolve MMIO addresses
                        match pci_modern::resolve_mmio_regions(&device.address, &caps) {
                            Ok(regions) => {
                                uart.log("VIRTIO", "MMIO regions resolved");

                                // Initialize Modern driver
                                let mut driver = virtio_modern::VirtioModern::new(regions);

                                // UEFI is identity-mapped, phys_offset = 0
                                match driver.init(0) {
                                    Ok(()) => {
                                        uart.log("VIRTIO", "Modern driver OK");
                                        uart.log("VIRTIO", "FEATURES_OK verified");

                                        // Log MAC address
                                        let mut mac_buf = [0u8; 18];
                                        let mac_str = driver.format_mac(&mut mac_buf);
                                        uart.log("VIRTIO", "MAC:");
                                        uart.log("VIRTIO", mac_str);

                                        net_driver = Some(driver);
                                    }
                                    Err(e) => {
                                        uart.log("ERROR", "Virtio init failed:");
                                        uart.log("ERROR", e);
                                    }
                                }
                            }
                            Err(e) => {
                                uart.log("ERROR", "MMIO resolve failed:");
                                uart.log("ERROR", e);
                            }
                        }
                    }
                }
                Err(e) => {
                    uart.log("ERROR", "Capability parse failed:");
                    uart.log("ERROR", e);
                }
            }
        } else {
            uart.log("WARN", "No Virtio-Net device found");
        }

        // ========================================================================
        // Phase 4-5: Scan for IVSHMEM Device (Optic Nerve) and Ignite
        // ========================================================================
        uart.log("INFO", "Scanning for IVSHMEM device...");

        if let Some(ivshmem) = pci_ivshmem::scan_for_ivshmem() {
            let mut info_buf = [0u8; 64];
            let info_str = ivshmem.format_info(&mut info_buf);
            uart.log("IVSHMEM", info_str);

            // Phase 5: Ignite the Optic Nerve - swizzle stream pointer to IVSHMEM
            let shm_ptr = pci_ivshmem::get_biostream_ptr();
            arachnid::ignite_optic_nerve(shm_ptr);

            if arachnid::is_optic_nerve_active() {
                uart.log("IVSHMEM", "Optic Nerve ACTIVE - visual cortex bridged");
            } else {
                uart.log("WARN", "Optic Nerve failed to ignite");
            }
        } else {
            uart.log("WARN", "No IVSHMEM device found - using local stream");
            // Initialize with local fallback
            arachnid::ignite_optic_nerve(None);
        }
    };

    // Driver will be passed to scheduler

    // ========================================================================
    // Initialize Graphics (GOP)
    // ========================================================================
    uart.log("INFO", "Initializing Graphics Output Protocol...");

    let mut framebuffer: Option<Framebuffer> = None;

    // Try to get GOP handle and initialize framebuffer
    if let Ok(gop_handle) = bt.get_handle_for_protocol::<GraphicsOutput>() {
        if let Ok(gop) = bt.open_protocol_exclusive::<GraphicsOutput>(gop_handle) {
            // Set best available mode
            let mut gop = gop;
            if let Some(_mode_info) = graphics::set_best_mode(&mut gop) {
                uart.log("INFO", "GOP mode set successfully");

                // Create framebuffer
                unsafe {
                    if let Some(fb) = Framebuffer::from_gop(&mut gop) {
                        framebuffer = Some(fb);
                    }
                }
            }
        }
    }

    // Render initial UI if we have graphics
    if let Some(ref mut fb) = framebuffer {
        render_boot_screen(fb, &mut uart);
    } else {
        uart.log("WARN", "GOP not available - running in serial-only mode");
    }

    // Load master key and initialize cells
    let master_key = match crate::memory::load_master_key(bt) {
        Ok(key) => key,
        Err(_) => {
            uart.log("FATAL", "Failed to load master key");
            if let Some(ref mut fb) = framebuffer {
                render_error(fb, "FATAL: Master key load failed");
            }
            return Status::LOAD_ERROR;
        }
    };

    uart.log("INFO", "Chaos master key acquired");

    // Update status on screen
    if let Some(ref mut fb) = framebuffer {
        render_status_line(fb, "Master key acquired", Color::LIFE);
    }

    // Initialize cells array (Cell is Copy, so this works)
    let mut cells: [Option<Cell>; N_CELLS] = [None; N_CELLS];
    let mut valid_count: usize = 0;

    for i in 0..N_CELLS {
        let child_key = ChaosCapability::derive_child_key(&master_key, i as u64);
        let blob_addr = 0x9100_0000 + i as u64 * 8192;

        match Cell::load_and_validate(bt, blob_addr, &child_key) {
            Ok(cell) => {
                cells[i] = Some(cell);
                valid_count += 1;
                audit!("Muscle validated and loaded");
            }
            Err(_e) => {
                uart.log("WARN", "Muscle validation failed");
                if !audit::recoverable() {
                    uart.log("FATAL", "Unrecoverable error");
                    return Status::LOAD_ERROR;
                }
            }
        }
    }

    if valid_count > 0 {
        uart.log("INFO", "Muscles loaded - Ea breathes");
    } else {
        uart.log("WARN", "No muscles loaded");
    }

    // ========================================================================
    // Initialize PermFS Bridge
    // ========================================================================
    uart.log("INFO", "Initializing PermFS bridge...");

    let node_id: u64 = 0;
    let volume_id: u32 = 1;

    let bridge_ok = bridge::init_bridge(bt, node_id, volume_id);

    if bridge_ok {
        uart.log("INFO", "PermFS bridge connected - Braid ready");
        if let Some(ref mut fb) = framebuffer {
            render_status_line(fb, "PermFS bridge connected", Color::LIFE);
            // Render the braid lattice with simulated block states
            render_braid_lattice(fb);
        }
    } else {
        uart.log("WARN", "PermFS bridge not available - running in memory-only mode");
        if let Some(ref mut fb) = framebuffer {
            render_status_line(fb, "Memory-only mode (no storage)", Color::ALERT);
        }
    }

    // Render shell prompt
    if let Some(ref mut fb) = framebuffer {
        render_shell_prompt(fb);
    }

    // Transfer control to scheduler with network driver
    run_scheduler_with_net(bt, &cells, &mut uart, net_driver, &master_key, framebuffer.as_ref())
}

// ============================================================================
// Rendering Functions
// ============================================================================

/// Render the initial boot screen
fn render_boot_screen(fb: &mut Framebuffer, uart: &mut Uart) {
    // Clear to VOID
    fb.clear(Color::VOID);

    // Draw title
    let title = "EAOS v1.0 Sovereign";
    let title_x = (fb.width - title.len() * 8) / 2;
    fb.draw_string(title_x, 10, title, &VGA_FONT_8X16, Color::LIFE, Some(Color::VOID));

    // Draw subtitle
    let subtitle = "The Braid Lattice";
    let sub_x = (fb.width - subtitle.len() * 8) / 2;
    fb.draw_string(sub_x, 30, subtitle, &VGA_FONT_8X16, Color::TEXT_DIM, Some(Color::VOID));

    // Draw separator line
    fb.draw_hline(LATTICE_PADDING, 50, fb.width - LATTICE_PADDING * 2, Color::TEXT_DIM);

    uart.log("INFO", "Boot screen rendered");
}

/// Render the braid lattice visualization
///
/// This displays the 256MB PermFS disk as a grid of small squares.
/// Each square represents a 4KB block:
/// - DORMANT (gray): Empty/unallocated block
/// - LIFE (green): Block with valid 0xB8AD braid header
/// - ALERT (red): Blocked by governance
fn render_braid_lattice(fb: &mut Framebuffer) {
    let lattice_y = 60;
    let available_width = fb.width - LATTICE_PADDING * 2;
    let available_height = fb.height - lattice_y - SHELL_Y_OFFSET - 40;

    // Calculate grid dimensions
    let cols = available_width / CELL_PITCH;
    let rows = available_height / CELL_PITCH;
    let visible_blocks = cols * rows;

    // Draw lattice header
    fb.draw_string(
        LATTICE_PADDING,
        lattice_y - 20,
        "Storage Lattice (4KB blocks)",
        &VGA_FONT_8X16,
        Color::TEXT_DIM,
        Some(Color::VOID),
    );

    // Render block grid
    // In real implementation, this would query actual block states
    // For now, simulate a pattern showing some braided blocks
    for i in 0..visible_blocks.min(TOTAL_BLOCKS) {
        let col = i % cols;
        let row = i / cols;

        let x = LATTICE_PADDING + col * CELL_PITCH;
        let y = lattice_y + row * CELL_PITCH;

        // Simulate block states:
        // - Most blocks empty (DORMANT)
        // - Some blocks braided (LIFE) - use a pattern for demo
        // - Very few blocked (ALERT)
        let color = simulate_block_state(i);

        fb.draw_rect(x, y, CELL_SIZE, CELL_SIZE, color);
    }
}

/// Simulate block state for visualization demo
/// In production, this would read actual block headers
fn simulate_block_state(block_index: usize) -> Color {
    // Create a visual pattern:
    // - Blocks 0-100: Some are "braided" (every 3rd block)
    // - Block 50: "blocked" by governance (red)
    // - Rest: empty

    if block_index == 50 {
        Color::ALERT // Governance blocked
    } else if block_index < 100 && block_index % 3 == 0 {
        Color::LIFE // Braided (0xB8AD header)
    } else if block_index < 200 && block_index % 7 == 0 {
        Color::SYNAPSE // Active/processing
    } else {
        Color::DORMANT // Empty
    }
}

/// Render a status line in the info area
fn render_status_line(fb: &mut Framebuffer, message: &str, color: Color) {
    let y = fb.height - SHELL_Y_OFFSET - 30;

    // Clear the line first
    fb.draw_rect(LATTICE_PADDING, y, fb.width - LATTICE_PADDING * 2, FONT_HEIGHT, Color::VOID);

    // Draw status indicator
    fb.draw_rect(LATTICE_PADDING, y + 4, 8, 8, color);

    // Draw message
    fb.draw_string(LATTICE_PADDING + 16, y, message, &VGA_FONT_8X16, Color::TEXT, Some(Color::VOID));
}

/// Render the shell prompt at the bottom
fn render_shell_prompt(fb: &mut Framebuffer) {
    let prompt_y = fb.height - SHELL_Y_OFFSET;

    // Draw separator
    fb.draw_hline(
        LATTICE_PADDING,
        prompt_y - 10,
        fb.width - LATTICE_PADDING * 2,
        Color::TEXT_DIM,
    );

    // Draw prompt
    let prompt = "EAOS Sovereign > _";
    fb.draw_string(
        LATTICE_PADDING,
        prompt_y,
        prompt,
        &VGA_FONT_8X16,
        Color::LIFE,
        Some(Color::VOID),
    );
}

/// Render an error message
fn render_error(fb: &mut Framebuffer, message: &str) {
    let y = fb.height / 2;
    let x = (fb.width - message.len() * 8) / 2;

    // Draw error background
    fb.draw_rect(x - 10, y - 10, message.len() * 8 + 20, FONT_HEIGHT + 20, Color::ALERT);

    // Draw message
    fb.draw_string(x, y, message, &VGA_FONT_8X16, Color::VOID, Some(Color::ALERT));
}
