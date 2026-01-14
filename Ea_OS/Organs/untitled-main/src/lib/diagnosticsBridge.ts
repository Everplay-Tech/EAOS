/**
 * EAOS Diagnostics Bridge
 *
 * Connects the ByteDisplay dashboard to the Nucleus Director's diagnostics.json
 * Provides real-time updates of braid transformations and Gödel numbers.
 */

export interface BraidDiagnostic {
  block_id: number
  godel_number: string
  godel_hex: string
  original_size: number
  compressed_size: number
  compression_ratio: number
  timestamp: number
  has_valid_header: boolean
}

export interface BlockDiagnostic {
  address: number
  braid_info: BraidDiagnostic | null
  patient_id: string | null
  record_type: string
}

export interface SystemHealth {
  biowerk_ready: boolean
  storage_ready: boolean
  dr_lex_enabled: boolean
  sefirot_chaos_mode: boolean
  pending_tasks: number
  total_blocks_stored: number
  total_bytes_compressed: number
  average_compression_ratio: number
}

export interface AuditSummary {
  total_audits: number
  approved: number
  blocked: number
  violations_by_type: Array<{ violation_type: string; count: number }>
}

export interface DiagnosticsReport {
  version: string
  generated_at: number
  system_health: SystemHealth
  godel_numbers: BraidDiagnostic[]
  stored_blocks: BlockDiagnostic[]
  audit_summary: AuditSummary
}

// Default diagnostics path
const DEFAULT_DIAGNOSTICS_PATH = '/tmp/eaos_diagnostics.json'

// Mock diagnostics for development
export function getMockDiagnostics(): DiagnosticsReport {
  return {
    version: "1.0.0",
    generated_at: Date.now() / 1000,
    system_health: {
      biowerk_ready: true,
      storage_ready: true,
      dr_lex_enabled: true,
      sefirot_chaos_mode: false,
      pending_tasks: 0,
      total_blocks_stored: 3,
      total_bytes_compressed: 966,
      average_compression_ratio: 0.079
    },
    godel_numbers: [
      {
        block_id: 1,
        godel_number: "340282366920938463463374607431768211455",
        godel_hex: "0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",
        original_size: 4096,
        compressed_size: 322,
        compression_ratio: 0.079,
        timestamp: Date.now() / 1000,
        has_valid_header: true
      },
      {
        block_id: 2,
        godel_number: "123456789012345678901234567890",
        godel_hex: "0x0000005E3B4B6E3A7C9FA5D2",
        original_size: 4096,
        compressed_size: 410,
        compression_ratio: 0.100,
        timestamp: Date.now() / 1000 - 60,
        has_valid_header: true
      }
    ],
    stored_blocks: [
      {
        address: 4096,
        braid_info: null,
        patient_id: "PAT-2025-001",
        record_type: "PatientRecord"
      },
      {
        address: 8192,
        braid_info: null,
        patient_id: "PAT-2025-002",
        record_type: "VitalSigns"
      }
    ],
    audit_summary: {
      total_audits: 10,
      approved: 9,
      blocked: 1,
      violations_by_type: [
        { violation_type: "UnencryptedPii", count: 1 }
      ]
    }
  }
}

// Diagnostics watcher class
export class DiagnosticsWatcher {
  private intervalId: number | null = null
  private callbacks: Set<(data: DiagnosticsReport) => void> = new Set()
  private lastData: DiagnosticsReport | null = null

  constructor(private pollInterval: number = 1000) {}

  subscribe(callback: (data: DiagnosticsReport) => void): () => void {
    this.callbacks.add(callback)

    // Immediately call with last data if available
    if (this.lastData) {
      callback(this.lastData)
    }

    // Return unsubscribe function
    return () => {
      this.callbacks.delete(callback)
    }
  }

  async start(): Promise<void> {
    // Initial fetch
    await this.poll()

    // Start polling
    this.intervalId = window.setInterval(() => {
      this.poll()
    }, this.pollInterval)
  }

  stop(): void {
    if (this.intervalId !== null) {
      window.clearInterval(this.intervalId)
      this.intervalId = null
    }
  }

  private async poll(): Promise<void> {
    try {
      // In a real implementation, this would fetch from a local server
      // For now, we use mock data or try to fetch from the file system
      const data = await this.fetchDiagnostics()
      this.lastData = data

      this.callbacks.forEach(cb => cb(data))
    } catch (error) {
      console.error('Failed to fetch diagnostics:', error)
    }
  }

  private async fetchDiagnostics(): Promise<DiagnosticsReport> {
    // Try to fetch from local API endpoint
    try {
      const response = await fetch('/api/diagnostics')
      if (response.ok) {
        return await response.json()
      }
    } catch {
      // Fall through to mock data
    }

    // Return mock data for development
    return getMockDiagnostics()
  }
}

// Singleton watcher instance
let watcherInstance: DiagnosticsWatcher | null = null

export function getDiagnosticsWatcher(): DiagnosticsWatcher {
  if (!watcherInstance) {
    watcherInstance = new DiagnosticsWatcher()
  }
  return watcherInstance
}

// Utility functions for braid visualization
export function formatGodelNumber(godel: string): string {
  // Shorten very long Gödel numbers for display
  if (godel.length > 20) {
    return `${godel.slice(0, 10)}...${godel.slice(-10)}`
  }
  return godel
}

export function compressionRatioToPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`
}

export function formatTimestamp(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString()
}

// Braid magic header constant
export const BRAID_MAGIC = [0xB8, 0xAD]
export const BRAID_MAGIC_HEX = 'B8AD'

export function hasBraidHeader(bytes: Uint8Array): boolean {
  return bytes.length >= 2 && bytes[0] === 0xB8 && bytes[1] === 0xAD
}

// Extract braid info from raw block data
export function extractBraidInfo(bytes: Uint8Array): {
  hasBraid: boolean
  compressedLen?: number
  godelLow?: bigint
} {
  if (!hasBraidHeader(bytes)) {
    return { hasBraid: false }
  }

  const compressedLen = (bytes[2] << 8) | bytes[3]

  // Extract lower 64 bits of Gödel number (bytes 4-11)
  let godelLow = 0n
  for (let i = 0; i < 8; i++) {
    godelLow |= BigInt(bytes[4 + i]) << BigInt(i * 8)
  }

  return {
    hasBraid: true,
    compressedLen,
    godelLow
  }
}
