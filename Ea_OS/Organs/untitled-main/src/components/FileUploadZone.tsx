import { Card, CardContent } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FileArrowUp, Info } from '@phosphor-icons/react'
import { useState, useRef, type DragEvent } from 'react'

interface FileUploadZoneProps {
  onFileSelect: (file: File) => void
}

export function FileUploadZone({ onFileSelect }: FileUploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)

    const files = e.dataTransfer.files
    if (files.length > 0) {
      onFileSelect(files[0])
    }
  }

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      onFileSelect(files[0])
    }
  }

  const handleButtonClick = () => {
    fileInputRef.current?.click()
  }

  return (
    <div className="space-y-4">
      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>How it works</AlertTitle>
        <AlertDescription>
          This tool demonstrates file reading in the browser. Upload any file to see its byte-level contents
          in hexadecimal, decimal, or ASCII text format - similar to how Python's file reading works, but in TypeScript!
        </AlertDescription>
      </Alert>

      <Card
        className={`border-2 border-dashed transition-all ${
          isDragging
            ? 'border-accent bg-accent/10 scale-[1.02]'
            : 'border-border hover:border-accent/50'
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <CardContent className="flex flex-col items-center justify-center py-12 px-6 text-center">
          <div className={`rounded-full p-4 mb-4 transition-colors ${
            isDragging ? 'bg-accent text-accent-foreground' : 'bg-muted text-muted-foreground'
          }`}>
            <FileArrowUp size={32} weight="duotone" />
          </div>
          
          <h3 className="text-lg font-semibold mb-2">
            {isDragging ? 'Drop file here' : 'Upload a file'}
          </h3>
          
          <p className="text-sm text-muted-foreground mb-4 max-w-md">
            Drag and drop a file here, or click the button below to select a file from your computer
          </p>
          
          <Button onClick={handleButtonClick} size="lg">
            <FileArrowUp className="mr-2" />
            Choose File
          </Button>
          
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileInputChange}
            aria-label="File input"
          />
        </CardContent>
      </Card>
    </div>
  )
}
