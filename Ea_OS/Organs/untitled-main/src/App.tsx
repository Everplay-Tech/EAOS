import { useState } from 'react'
import { FileUploadZone } from '@/components/FileUploadZone'
import { FileInfoCard } from '@/components/FileInfoCard'
import { ByteDisplay } from '@/components/ByteDisplay'
import { BraidViewer } from '@/components/BraidViewer'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { readFileAsBytes } from '@/lib/fileUtils'
import type { FileData } from '@/types/file'
import { FileCode, X, WarningCircle, Dna, FileArrowUp } from '@phosphor-icons/react'
import { motion, AnimatePresence } from 'framer-motion'

type AppMode = 'file' | 'braid'

function App() {
  const [mode, setMode] = useState<AppMode>('braid')
  const [fileData, setFileData] = useState<FileData | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFileSelect = async (file: File) => {
    setIsLoading(true)
    setError(null)

    try {
      const bytes = await readFileAsBytes(file)
      
      setFileData({
        name: file.name,
        size: file.size,
        type: file.type,
        lastModified: file.lastModified,
        bytes,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read file')
    } finally {
      setIsLoading(false)
    }
  }

  const handleClear = () => {
    setFileData(null)
    setError(null)
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <header className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-primary p-2">
                {mode === 'braid' ? (
                  <Dna size={28} className="text-primary-foreground" weight="duotone" />
                ) : (
                  <FileCode size={28} className="text-primary-foreground" weight="duotone" />
                )}
              </div>
              <h1 className="text-3xl font-bold tracking-tight">
                {mode === 'braid' ? 'EAOS Braided Skeleton' : 'File Byte Reader'}
              </h1>
            </div>
            <div className="flex items-center gap-2">
              {mode === 'file' && fileData && (
                <Button variant="outline" onClick={handleClear}>
                  <X className="mr-2" />
                  Clear
                </Button>
              )}
            </div>
          </div>

          {/* Mode Tabs */}
          <Tabs value={mode} onValueChange={(v) => setMode(v as AppMode)} className="mb-4">
            <TabsList>
              <TabsTrigger value="braid" className="flex items-center gap-2">
                <Dna size={16} />
                Braid Viewer
              </TabsTrigger>
              <TabsTrigger value="file" className="flex items-center gap-2">
                <FileArrowUp size={16} />
                File Reader
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <p className="text-muted-foreground text-lg">
            {mode === 'braid'
              ? 'Real-time visualization of EAOS braid transformations, Gödel numbers, and system health'
              : 'Upload any file and view its contents as a byte array'}
          </p>
        </header>

        {error && (
          <Alert variant="destructive" className="mb-6">
            <WarningCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <AnimatePresence mode="wait">
          {mode === 'braid' ? (
            <motion.div
              key="braid"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              <BraidViewer />
            </motion.div>
          ) : (
            <>
              {!fileData && !isLoading && (
                <motion.div
                  key="upload"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.3 }}
                >
                  <FileUploadZone onFileSelect={handleFileSelect} />
                </motion.div>
              )}

              {isLoading && (
                <motion.div
                  key="loading"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="text-center py-12"
                >
                  <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent" />
                  <p className="mt-4 text-muted-foreground">Reading file...</p>
                </motion.div>
              )}

              {fileData && !isLoading && (
                <motion.div
                  key="content"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.3 }}
                  className="space-y-6"
                >
                  <FileInfoCard fileData={fileData} />
                  <ByteDisplay fileData={fileData} />
                </motion.div>
              )}
            </>
          )}
        </AnimatePresence>

        <footer className="mt-12 pt-6 border-t text-center text-sm text-muted-foreground">
          {mode === 'braid' ? (
            <p>
              EAOS Sovereign Health Pod • Braid Magic: <code className="font-mono bg-muted px-2 py-1 rounded">0xB8AD</code> • Compression: 7.9%
            </p>
          ) : (
            <p>
              This demonstrates the TypeScript equivalent of Python's file reading:{' '}
              <code className="font-mono bg-muted px-2 py-1 rounded">
                with open(filename, 'rb') as f: bytes = f.read()
              </code>
            </p>
          )}
        </footer>
      </div>
    </div>
  )
}

export default App