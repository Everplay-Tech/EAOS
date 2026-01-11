import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { FileData, DisplayMode } from '@/types/file'
import { byteToHex, byteToDecimal, byteToChar, MAX_DISPLAY_BYTES, downloadByteArray } from '@/lib/fileUtils'
import { Info, Download } from '@phosphor-icons/react'
import { useState } from 'react'
import { toast } from 'sonner'

interface ByteDisplayProps {
  fileData: FileData
}

export function ByteDisplay({ fileData }: ByteDisplayProps) {
  const [mode, setMode] = useState<DisplayMode>('hex')
  const displayBytes = fileData.bytes.slice(0, MAX_DISPLAY_BYTES)
  const isTruncated = fileData.size > MAX_DISPLAY_BYTES
  const bytesPerRow = 16

  const handleDownload = () => {
    downloadByteArray(fileData.bytes, fileData.name)
    toast.success(`Downloaded ${fileData.name}`)
  }

  const renderByteGrid = () => {
    const rows: React.ReactElement[] = []
    
    for (let i = 0; i < displayBytes.length; i += bytesPerRow) {
      const rowBytes = displayBytes.slice(i, i + bytesPerRow)
      const offset = i.toString(16).padStart(8, '0').toUpperCase()
      
      rows.push(
        <div key={i} className="flex gap-4 font-mono text-sm leading-relaxed">
          <div className="text-muted-foreground w-20 flex-shrink-0">
            {offset}
          </div>
          <div className="flex gap-1 flex-wrap flex-1">
            {Array.from(rowBytes).map((byte, idx) => (
              <span
                key={idx}
                className={`${
                  mode === 'hex' ? 'w-6' : mode === 'decimal' ? 'w-8' : 'w-3'
                } text-center hover:bg-accent hover:text-accent-foreground rounded transition-colors`}
              >
                {mode === 'hex' && byteToHex(byte)}
                {mode === 'decimal' && byteToDecimal(byte)}
                {mode === 'text' && byteToChar(byte)}
              </span>
            ))}
          </div>
        </div>
      )
    }
    
    return rows
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>Byte Array Contents</CardTitle>
            <CardDescription>
              {mode === 'hex' && 'Hexadecimal representation of file bytes'}
              {mode === 'decimal' && 'Decimal representation of file bytes'}
              {mode === 'text' && 'ASCII character representation of file bytes'}
            </CardDescription>
          </div>
          <Button onClick={handleDownload} variant="secondary" size="sm">
            <Download className="mr-2" />
            Download
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs value={mode} onValueChange={(v) => setMode(v as DisplayMode)}>
          <TabsList className="grid w-full grid-cols-3 mb-4">
            <TabsTrigger value="hex">Hexadecimal</TabsTrigger>
            <TabsTrigger value="decimal">Decimal</TabsTrigger>
            <TabsTrigger value="text">ASCII Text</TabsTrigger>
          </TabsList>
          
          {isTruncated && (
            <Alert className="mb-4">
              <Info className="h-4 w-4" />
              <AlertDescription>
                Displaying first {MAX_DISPLAY_BYTES.toLocaleString()} of {fileData.size.toLocaleString()} bytes
              </AlertDescription>
            </Alert>
          )}

          <TabsContent value={mode} className="mt-0">
            <ScrollArea className="h-[400px] w-full rounded-md border bg-muted/30 p-4">
              <div className="space-y-1">
                {renderByteGrid()}
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
        
        <div className="mt-4 text-sm text-muted-foreground">
          <p>
            <span className="font-medium">Format Guide:</span>
            {mode === 'hex' && ' Each byte shown as two hexadecimal digits (00-FF)'}
            {mode === 'decimal' && ' Each byte shown as a decimal number (0-255)'}
            {mode === 'text' && ' Printable ASCII characters shown, non-printable as "."'}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
