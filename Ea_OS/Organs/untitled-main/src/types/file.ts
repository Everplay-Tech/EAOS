export interface FileData {
  name: string
  size: number
  type: string
  lastModified: number
  bytes: Uint8Array
}

export type DisplayMode = 'hex' | 'decimal' | 'text'
