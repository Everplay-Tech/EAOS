/**
 * BraidViewer Component
 *
 * Visualizes the "Braided Skeleton" - real-time display of EAOS braid transformations,
 * Gödel numbers, and system health from the Nucleus Director's diagnostics.
 */

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  getDiagnosticsWatcher,
  DiagnosticsReport,
  BraidDiagnostic,
  formatGodelNumber,
  compressionRatioToPercent,
  formatTimestamp,
  BRAID_MAGIC_HEX
} from '@/lib/diagnosticsBridge'
import { Activity, CheckCircle, XCircle, Shield, Database, Cpu } from '@phosphor-icons/react'
import { motion, AnimatePresence } from 'framer-motion'

export function BraidViewer() {
  const [diagnostics, setDiagnostics] = useState<DiagnosticsReport | null>(null)
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    const watcher = getDiagnosticsWatcher()

    const unsubscribe = watcher.subscribe((data) => {
      setDiagnostics(data)
      setIsConnected(true)
    })

    watcher.start()

    return () => {
      unsubscribe()
      watcher.stop()
    }
  }, [])

  if (!diagnostics) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-primary border-t-transparent mb-4" />
          <p className="text-muted-foreground">Connecting to EAOS Nucleus...</p>
        </CardContent>
      </Card>
    )
  }

  const { system_health, godel_numbers, stored_blocks, audit_summary } = diagnostics

  return (
    <div className="space-y-6">
      {/* System Health Banner */}
      <Card className="border-2 border-primary/20">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity size={24} className="text-primary" weight="duotone" />
              <CardTitle>EAOS Organism Status</CardTitle>
            </div>
            <Badge variant={isConnected ? "default" : "secondary"}>
              {isConnected ? "Connected" : "Disconnected"}
            </Badge>
          </div>
          <CardDescription>
            Braid Magic: 0x{BRAID_MAGIC_HEX} | Compression: {compressionRatioToPercent(system_health.average_compression_ratio)}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatusIndicator
              icon={<Cpu size={20} />}
              label="BIOwerk"
              status={system_health.biowerk_ready}
            />
            <StatusIndicator
              icon={<Database size={20} />}
              label="PermFS"
              status={system_health.storage_ready}
            />
            <StatusIndicator
              icon={<Shield size={20} />}
              label="Dr-Lex"
              status={system_health.dr_lex_enabled}
              variant="enforced"
            />
            <div className="flex flex-col">
              <span className="text-sm text-muted-foreground">Blocks Stored</span>
              <span className="text-2xl font-bold">{system_health.total_blocks_stored}</span>
            </div>
          </div>

          {/* Compression Progress */}
          <div className="mt-4">
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">Compression Efficiency</span>
              <span className="font-mono">{compressionRatioToPercent(system_health.average_compression_ratio)}</span>
            </div>
            <Progress value={system_health.average_compression_ratio * 100} className="h-2" />
          </div>
        </CardContent>
      </Card>

      {/* Main Content Tabs */}
      <Tabs defaultValue="godel" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="godel">Gödel Numbers</TabsTrigger>
          <TabsTrigger value="blocks">Stored Blocks</TabsTrigger>
          <TabsTrigger value="audit">Audit Trail</TabsTrigger>
        </TabsList>

        {/* Gödel Numbers Tab */}
        <TabsContent value="godel">
          <Card>
            <CardHeader>
              <CardTitle>Braid Transformations</CardTitle>
              <CardDescription>
                Each block is transformed into a unique Gödel number via T9-Braid encoding
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px]">
                <AnimatePresence>
                  {godel_numbers.map((braid, index) => (
                    <motion.div
                      key={braid.block_id}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 20 }}
                      transition={{ delay: index * 0.1 }}
                    >
                      <GodelCard braid={braid} />
                    </motion.div>
                  ))}
                </AnimatePresence>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Stored Blocks Tab */}
        <TabsContent value="blocks">
          <Card>
            <CardHeader>
              <CardTitle>PermFS Block Storage</CardTitle>
              <CardDescription>
                Healthcare records stored with 0xB8AD braid headers
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px]">
                <div className="space-y-2">
                  {stored_blocks.map((block, index) => (
                    <div
                      key={block.address}
                      className="flex items-center justify-between p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded bg-primary/10 flex items-center justify-center font-mono text-sm">
                          {index + 1}
                        </div>
                        <div>
                          <div className="font-mono text-sm">
                            Address: 0x{block.address.toString(16).toUpperCase().padStart(8, '0')}
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {block.patient_id || 'System Block'} • {block.record_type}
                          </div>
                        </div>
                      </div>
                      <Badge variant="outline" className="font-mono">
                        0xB8AD
                      </Badge>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Audit Trail Tab */}
        <TabsContent value="audit">
          <Card>
            <CardHeader>
              <CardTitle>Dr-Lex Governance Audit</CardTitle>
              <CardDescription>
                Healthcare Constitution enforcement activity
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="text-center p-4 rounded-lg bg-muted/50">
                  <div className="text-3xl font-bold text-primary">{audit_summary.total_audits}</div>
                  <div className="text-sm text-muted-foreground">Total Audits</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-green-500/10">
                  <div className="text-3xl font-bold text-green-600">{audit_summary.approved}</div>
                  <div className="text-sm text-muted-foreground">Approved</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-red-500/10">
                  <div className="text-3xl font-bold text-red-600">{audit_summary.blocked}</div>
                  <div className="text-sm text-muted-foreground">Blocked</div>
                </div>
              </div>

              {audit_summary.violations_by_type.length > 0 && (
                <div>
                  <h4 className="font-medium mb-2">Violation Types</h4>
                  <div className="space-y-2">
                    {audit_summary.violations_by_type.map((v) => (
                      <div
                        key={v.violation_type}
                        className="flex items-center justify-between p-2 rounded bg-red-500/5"
                      >
                        <span className="text-sm">{v.violation_type}</span>
                        <Badge variant="destructive">{v.count}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

// Sub-components

function StatusIndicator({
  icon,
  label,
  status,
  variant = "default"
}: {
  icon: React.ReactNode
  label: string
  status: boolean
  variant?: "default" | "enforced"
}) {
  const isEnforced = variant === "enforced" && status

  return (
    <div className="flex items-center gap-2">
      <div className={`p-2 rounded ${status ? (isEnforced ? 'bg-amber-500/10 text-amber-600' : 'bg-green-500/10 text-green-600') : 'bg-red-500/10 text-red-600'}`}>
        {icon}
      </div>
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-muted-foreground">
          {status ? (isEnforced ? 'Enforced' : 'Running') : 'Stopped'}
        </div>
      </div>
    </div>
  )
}

function GodelCard({ braid }: { braid: BraidDiagnostic }) {
  return (
    <div className="mb-4 p-4 rounded-lg border bg-card hover:border-primary/50 transition-colors">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline">Block #{braid.block_id}</Badge>
          {braid.has_valid_header ? (
            <Badge variant="default" className="bg-green-600">
              <CheckCircle size={12} className="mr-1" />
              Valid Header
            </Badge>
          ) : (
            <Badge variant="destructive">
              <XCircle size={12} className="mr-1" />
              Invalid
            </Badge>
          )}
        </div>
        <span className="text-xs text-muted-foreground">
          {formatTimestamp(braid.timestamp)}
        </span>
      </div>

      <div className="space-y-2">
        {/* Gödel Number */}
        <div>
          <div className="text-xs text-muted-foreground mb-1">Gödel Number</div>
          <div className="font-mono text-sm bg-muted/50 p-2 rounded break-all">
            {formatGodelNumber(braid.godel_number)}
          </div>
        </div>

        {/* Hex representation */}
        <div>
          <div className="text-xs text-muted-foreground mb-1">Hex</div>
          <div className="font-mono text-sm text-primary">
            {braid.godel_hex}
          </div>
        </div>

        {/* Compression stats */}
        <div className="flex gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Original:</span>{' '}
            <span className="font-mono">{braid.original_size} bytes</span>
          </div>
          <div>
            <span className="text-muted-foreground">Compressed:</span>{' '}
            <span className="font-mono">{braid.compressed_size} bytes</span>
          </div>
          <div>
            <span className="text-muted-foreground">Ratio:</span>{' '}
            <span className="font-mono text-primary">
              {compressionRatioToPercent(braid.compression_ratio)}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default BraidViewer
