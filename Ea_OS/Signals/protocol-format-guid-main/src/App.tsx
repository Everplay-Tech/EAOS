import { useState, useMemo } from 'react';
import { useKV } from '@github/spark/hooks';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Plus,
  Pencil,
  Trash,
  Download,
  ArrowUp,
  ArrowDown,
  ChartBar,
  Clock,
  Database,
  Sparkle,
  Lightning,
} from '@phosphor-icons/react';
import { Protocol, ProtocolField } from '@/lib/types';
import {
  generateProtocolId,
  generateFieldId,
  exportProtocolAsJSON,
  exportProtocolAsText,
} from '@/lib/protocol-utils';
import { ProtocolDialog } from '@/components/ProtocolDialog';
import { FieldDialog } from '@/components/FieldDialog';
import { ByteLayout } from '@/components/ByteLayout';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

function App() {
  const [protocols, setProtocols] = useKV<Protocol[]>('protocols', []);
  const [selectedProtocolId, setSelectedProtocolId] = useState<string | null>(null);
  const [protocolDialogOpen, setProtocolDialogOpen] = useState(false);
  const [fieldDialogOpen, setFieldDialogOpen] = useState(false);
  const [editingProtocol, setEditingProtocol] = useState<Protocol | null>(null);
  const [editingField, setEditingField] = useState<ProtocolField | null>(null);
  const [deleteProtocolId, setDeleteProtocolId] = useState<string | null>(null);
  const [deleteFieldId, setDeleteFieldId] = useState<string | null>(null);

  const selectedProtocol = protocols?.find((p) => p.id === selectedProtocolId);

  const stats = useMemo(() => {
    const totalProtocols = protocols?.length || 0;
    const totalFields = protocols?.reduce((sum, p) => sum + p.fields.length, 0) || 0;
    const totalBits = protocols?.reduce(
      (sum, p) => sum + p.fields.reduce((s, f) => s + f.sizeInBits, 0),
      0
    ) || 0;
    const avgFieldsPerProtocol = totalProtocols > 0 ? (totalFields / totalProtocols).toFixed(1) : '0';
    
    return {
      totalProtocols,
      totalFields,
      totalBits,
      totalBytes: (totalBits / 8).toFixed(1),
      avgFieldsPerProtocol,
    };
  }, [protocols]);

  const selectedStats = useMemo(() => {
    if (!selectedProtocol) return null;
    
    const totalBits = selectedProtocol.fields.reduce((sum, f) => sum + f.sizeInBits, 0);
    const typeDistribution = selectedProtocol.fields.reduce((acc, f) => {
      acc[f.type] = (acc[f.type] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);
    
    const largestField = selectedProtocol.fields.reduce(
      (max, f) => f.sizeInBits > max.sizeInBits ? f : max,
      selectedProtocol.fields[0] || { name: 'N/A', sizeInBits: 0 }
    );
    
    return {
      totalBits,
      totalBytes: (totalBits / 8).toFixed(2),
      fieldCount: selectedProtocol.fields.length,
      typeDistribution,
      largestField,
      alignment: totalBits % 8 === 0 ? 'Byte-aligned' : `${totalBits % 8} bits padding needed`,
    };
  }, [selectedProtocol]);

  const handleCreateProtocol = (data: {
    name: string;
    version: string;
    description: string;
  }) => {
    const newProtocol: Protocol = {
      id: generateProtocolId(),
      ...data,
      fields: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    setProtocols((current) => [...(current || []), newProtocol]);
    setSelectedProtocolId(newProtocol.id);
    setProtocolDialogOpen(false);
    toast.success('Protocol created');
  };

  const handleEditProtocol = (data: { name: string; version: string; description: string }) => {
    if (!editingProtocol) return;

    setProtocols((current) =>
      (current || []).map((p) =>
        p.id === editingProtocol.id
          ? { ...p, ...data, updatedAt: Date.now() }
          : p
      )
    );
    setProtocolDialogOpen(false);
    setEditingProtocol(null);
    toast.success('Protocol updated');
  };

  const handleDeleteProtocol = () => {
    if (!deleteProtocolId) return;

    setProtocols((current) => (current || []).filter((p) => p.id !== deleteProtocolId));
    if (selectedProtocolId === deleteProtocolId) {
      setSelectedProtocolId(null);
    }
    setDeleteProtocolId(null);
    toast.success('Protocol deleted');
  };

  const handleAddField = (data: {
    name: string;
    type: any;
    sizeInBits: number;
    description: string;
  }) => {
    if (!selectedProtocolId) return;

    const newField: ProtocolField = {
      id: generateFieldId(),
      ...data,
    };

    setProtocols((current) =>
      (current || []).map((p) =>
        p.id === selectedProtocolId
          ? { ...p, fields: [...p.fields, newField], updatedAt: Date.now() }
          : p
      )
    );
    setFieldDialogOpen(false);
    toast.success('Field added');
  };

  const handleEditField = (data: {
    name: string;
    type: any;
    sizeInBits: number;
    description: string;
  }) => {
    if (!editingField || !selectedProtocolId) return;

    setProtocols((current) =>
      (current || []).map((p) =>
        p.id === selectedProtocolId
          ? {
              ...p,
              fields: p.fields.map((f) =>
                f.id === editingField.id ? { ...f, ...data } : f
              ),
              updatedAt: Date.now(),
            }
          : p
      )
    );
    setFieldDialogOpen(false);
    setEditingField(null);
    toast.success('Field updated');
  };

  const handleDeleteField = () => {
    if (!deleteFieldId || !selectedProtocolId) return;

    setProtocols((current) =>
      (current || []).map((p) =>
        p.id === selectedProtocolId
          ? {
              ...p,
              fields: p.fields.filter((f) => f.id !== deleteFieldId),
              updatedAt: Date.now(),
            }
          : p
      )
    );
    setDeleteFieldId(null);
    toast.success('Field deleted');
  };

  const handleMoveField = (fieldId: string, direction: 'up' | 'down') => {
    if (!selectedProtocolId) return;

    setProtocols((current) =>
      (current || []).map((p) => {
        if (p.id !== selectedProtocolId) return p;

        const fieldIndex = p.fields.findIndex((f) => f.id === fieldId);
        if (fieldIndex === -1) return p;

        const newIndex = direction === 'up' ? fieldIndex - 1 : fieldIndex + 1;
        if (newIndex < 0 || newIndex >= p.fields.length) return p;

        const newFields = [...p.fields];
        [newFields[fieldIndex], newFields[newIndex]] = [
          newFields[newIndex],
          newFields[fieldIndex],
        ];

        return { ...p, fields: newFields, updatedAt: Date.now() };
      })
    );
  };

  const handleExport = (format: 'json' | 'text') => {
    if (!selectedProtocol) return;

    const content =
      format === 'json'
        ? exportProtocolAsJSON(selectedProtocol)
        : exportProtocolAsText(selectedProtocol);

    navigator.clipboard.writeText(content);
    toast.success(`Protocol exported as ${format.toUpperCase()} and copied to clipboard`);
  };

  return (
    <div className="min-h-screen">
      <motion.header 
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="border-b-2 border-primary/30 bg-gradient-to-r from-card/80 via-card/60 to-card/80 backdrop-blur-xl"
      >
        <div className="container mx-auto px-8 py-6">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-4xl font-black gradient-text mb-2 flex items-center gap-3">
                <Sparkle className="text-accent" weight="fill" size={40} />
                Protocol Format Designer
              </h1>
              <p className="text-base text-muted-foreground">
                Create and visualize protocol specifications with extravagant detail
              </p>
            </div>
            <div className="flex gap-6">
              <motion.div 
                whileHover={{ scale: 1.05 }}
                className="text-center px-6 py-3 bg-primary/20 rounded-xl border-2 border-primary/40"
              >
                <div className="text-3xl font-black text-accent">{stats.totalProtocols}</div>
                <div className="text-xs uppercase tracking-widest text-muted-foreground">Protocols</div>
              </motion.div>
              <motion.div 
                whileHover={{ scale: 1.05 }}
                className="text-center px-6 py-3 bg-accent/20 rounded-xl border-2 border-accent/40"
              >
                <div className="text-3xl font-black text-primary">{stats.totalFields}</div>
                <div className="text-xs uppercase tracking-widest text-muted-foreground">Fields</div>
              </motion.div>
              <motion.div 
                whileHover={{ scale: 1.05 }}
                className="text-center px-6 py-3 bg-secondary/40 rounded-xl border-2 border-border"
              >
                <div className="text-3xl font-black gradient-text">{stats.totalBytes}</div>
                <div className="text-xs uppercase tracking-widest text-muted-foreground">Total KB</div>
              </motion.div>
            </div>
          </div>
        </div>
      </motion.header>

      <div className="container mx-auto px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-4">
            <motion.div
              initial={{ x: -20, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              transition={{ delay: 0.1 }}
            >
              <Card className="card-glow border-2 border-primary/30 bg-card/80 backdrop-blur-sm">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-2xl font-bold flex items-center gap-2">
                        <Database className="text-accent" weight="fill" />
                        Protocols
                      </CardTitle>
                      <CardDescription className="text-base">
                        {stats.totalProtocols} definitions • Avg {stats.avgFieldsPerProtocol} fields
                      </CardDescription>
                    </div>
                    <Button
                      size="lg"
                      className="bg-primary hover:bg-primary/80 accent-glow font-bold"
                      onClick={() => {
                        setEditingProtocol(null);
                        setProtocolDialogOpen(true);
                      }}
                    >
                      <Plus className="mr-2" weight="bold" />
                      New
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-[600px] pr-4">
                    {!protocols || protocols.length === 0 ? (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="text-center py-16 px-6"
                      >
                        <Lightning className="mx-auto mb-4 text-accent" weight="fill" size={64} />
                        <p className="text-lg font-semibold mb-2">No protocols yet</p>
                        <p className="text-sm text-muted-foreground">
                          Create your first protocol to unlock the power of structured data visualization
                        </p>
                      </motion.div>
                    ) : (
                      <div className="space-y-3">
                        <AnimatePresence mode="popLayout">
                          {protocols.map((protocol, index) => (
                            <motion.div
                              key={protocol.id}
                              initial={{ opacity: 0, x: -20 }}
                              animate={{ opacity: 1, x: 0 }}
                              exit={{ opacity: 0, x: 20 }}
                              transition={{ delay: index * 0.05 }}
                              whileHover={{ scale: 1.02, x: 4 }}
                              className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                                selectedProtocolId === protocol.id
                                  ? 'border-accent bg-accent/20 shadow-lg shadow-accent/30'
                                  : 'border-border bg-secondary/20 hover:border-accent/50 hover:bg-secondary/40'
                              }`}
                              onClick={() => setSelectedProtocolId(protocol.id)}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1 min-w-0">
                                  <div className="font-bold text-base truncate mb-1">
                                    {protocol.name}
                                  </div>
                                  <div className="flex items-center gap-2 mb-2">
                                    <Badge variant="secondary" className="text-xs font-mono font-semibold">
                                      v{protocol.version}
                                    </Badge>
                                    <Badge className="text-xs bg-accent/30 text-accent-foreground font-bold">
                                      {protocol.fields.length} fields
                                    </Badge>
                                  </div>
                                </div>
                              </div>
                              {protocol.description && (
                                <p className="text-sm text-muted-foreground mt-2 line-clamp-2 leading-relaxed">
                                  {protocol.description}
                                </p>
                              )}
                              <div className="flex items-center gap-3 mt-3 text-xs text-muted-foreground">
                                <div className="flex items-center gap-1">
                                  <Clock size={14} />
                                  {new Date(protocol.updatedAt).toLocaleDateString()}
                                </div>
                                <div className="flex items-center gap-1 font-mono">
                                  {protocol.fields.reduce((s, f) => s + f.sizeInBits, 0)} bits
                                </div>
                              </div>
                            </motion.div>
                          ))}
                        </AnimatePresence>
                      </div>
                    )}
                  </ScrollArea>
                </CardContent>
              </Card>
            </motion.div>
          </div>

          <div className="lg:col-span-8">
            {!selectedProtocol ? (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2 }}
              >
                <Card className="h-[750px] flex items-center justify-center card-glow border-2 border-primary/30 bg-card/80 backdrop-blur-sm">
                  <div className="text-center px-8">
                    <motion.div
                      animate={{ 
                        rotate: [0, 5, -5, 0],
                        scale: [1, 1.05, 1]
                      }}
                      transition={{ 
                        duration: 3,
                        repeat: Infinity,
                        ease: "easeInOut"
                      }}
                    >
                      <ChartBar className="mx-auto mb-6 text-accent" weight="duotone" size={96} />
                    </motion.div>
                    <p className="text-2xl font-bold mb-3">Select a protocol to reveal its secrets</p>
                    <p className="text-base text-muted-foreground max-w-md mx-auto">
                      Choose from your collection or create a new one to explore detailed visualizations and comprehensive statistics
                    </p>
                  </div>
                </Card>
              </motion.div>
            ) : (
              <motion.div
                key={selectedProtocol.id}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3 }}
              >
                <Card className="card-glow border-2 border-accent/40 bg-card/80 backdrop-blur-sm">
                  <CardHeader>
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-3">
                          <CardTitle className="text-3xl font-black">{selectedProtocol.name}</CardTitle>
                          <Badge variant="outline" className="text-base font-mono font-bold px-3 py-1 border-2">
                            v{selectedProtocol.version}
                          </Badge>
                        </div>
                        {selectedProtocol.description && (
                          <CardDescription className="text-base leading-relaxed">
                            {selectedProtocol.description}
                          </CardDescription>
                        )}
                        <div className="flex items-center gap-4 mt-4 text-sm">
                          <div className="flex items-center gap-2 px-3 py-1.5 bg-primary/20 rounded-lg border border-primary/30">
                            <Clock className="text-accent" size={16} />
                            <span className="text-muted-foreground">Created:</span>
                            <span className="font-semibold">
                              {new Date(selectedProtocol.createdAt).toLocaleString()}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 px-3 py-1.5 bg-accent/20 rounded-lg border border-accent/30">
                            <Clock className="text-primary" size={16} />
                            <span className="text-muted-foreground">Updated:</span>
                            <span className="font-semibold">
                              {new Date(selectedProtocol.updatedAt).toLocaleString()}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="lg"
                          variant="outline"
                          className="border-2 hover:border-accent hover:bg-accent/10"
                          onClick={() => {
                            setEditingProtocol(selectedProtocol);
                            setProtocolDialogOpen(true);
                          }}
                        >
                          <Pencil weight="bold" />
                        </Button>
                        <Button
                          size="lg"
                          variant="outline"
                          className="border-2 hover:border-destructive hover:bg-destructive/10"
                          onClick={() => setDeleteProtocolId(selectedProtocol.id)}
                        >
                          <Trash weight="bold" />
                        </Button>
                        <Button
                          size="lg"
                          className="bg-accent hover:bg-accent/80 text-accent-foreground accent-glow font-bold"
                          onClick={() => handleExport('json')}
                        >
                          <Download className="mr-2" weight="bold" />
                          JSON
                        </Button>
                        <Button
                          size="lg"
                          className="bg-primary hover:bg-primary/80 accent-glow font-bold"
                          onClick={() => handleExport('text')}
                        >
                          <Download className="mr-2" weight="bold" />
                          Text
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-8">
                    {selectedStats && (
                      <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="grid grid-cols-2 lg:grid-cols-4 gap-4"
                      >
                        <div className="p-4 bg-gradient-to-br from-primary/30 to-primary/10 rounded-xl border-2 border-primary/40">
                          <div className="text-3xl font-black gradient-text mb-1">
                            {selectedStats.totalBits}
                          </div>
                          <div className="text-xs uppercase tracking-widest text-muted-foreground">Total Bits</div>
                        </div>
                        <div className="p-4 bg-gradient-to-br from-accent/30 to-accent/10 rounded-xl border-2 border-accent/40">
                          <div className="text-3xl font-black text-accent mb-1">
                            {selectedStats.totalBytes}
                          </div>
                          <div className="text-xs uppercase tracking-widest text-muted-foreground">Total Bytes</div>
                        </div>
                        <div className="p-4 bg-gradient-to-br from-secondary/40 to-secondary/20 rounded-xl border-2 border-border">
                          <div className="text-3xl font-black text-foreground mb-1">
                            {selectedStats.fieldCount}
                          </div>
                          <div className="text-xs uppercase tracking-widest text-muted-foreground">Fields</div>
                        </div>
                        <div className="p-4 bg-gradient-to-br from-muted/40 to-muted/20 rounded-xl border-2 border-border">
                          <div className="text-sm font-bold text-foreground mb-1 truncate">
                            {selectedStats.largestField.name}
                          </div>
                          <div className="text-xs uppercase tracking-widest text-muted-foreground">Largest Field</div>
                        </div>
                      </motion.div>
                    )}

                    {selectedStats && (
                      <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.1 }}
                        className="p-5 bg-secondary/30 rounded-xl border-2 border-border"
                      >
                        <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-3 flex items-center gap-2">
                          <ChartBar className="text-accent" weight="bold" />
                          Type Distribution
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(selectedStats.typeDistribution).map(([type, count]) => (
                            <Badge 
                              key={type} 
                              className="text-sm font-mono font-bold px-3 py-1.5 bg-primary/30 hover:bg-primary/40 border-2 border-primary/40"
                            >
                              {type} <span className="ml-2 text-accent">×{count}</span>
                            </Badge>
                          ))}
                        </div>
                        <div className="mt-4 pt-4 border-t border-border/50">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground font-semibold">Alignment Status:</span>
                            <span className={`font-bold ${selectedStats.alignment === 'Byte-aligned' ? 'text-accent' : 'text-primary'}`}>
                              {selectedStats.alignment}
                            </span>
                          </div>
                        </div>
                      </motion.div>
                    )}

                    <ByteLayout fields={selectedProtocol.fields} />

                    <Separator className="bg-border/50" />

                    <div className="space-y-5">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xl font-bold uppercase tracking-wider flex items-center gap-2">
                          <Lightning className="text-accent" weight="fill" />
                          Fields Specification
                        </h3>
                        <Button
                          size="lg"
                          className="bg-accent hover:bg-accent/80 text-accent-foreground accent-glow font-bold"
                          onClick={() => {
                            setEditingField(null);
                            setFieldDialogOpen(true);
                          }}
                        >
                          <Plus className="mr-2" weight="bold" />
                          Add Field
                        </Button>
                      </div>

                      {selectedProtocol.fields.length === 0 ? (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="text-center py-12 px-6 bg-secondary/20 rounded-xl border-2 border-dashed border-border"
                        >
                          <Database className="mx-auto mb-4 text-muted-foreground" size={48} />
                          <p className="text-base font-semibold text-muted-foreground">
                            No fields yet. Add your first field to define the protocol structure.
                          </p>
                        </motion.div>
                      ) : (
                        <div className="space-y-3">
                          <AnimatePresence mode="popLayout">
                            {selectedProtocol.fields.map((field, index) => (
                              <motion.div
                                key={field.id}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 20 }}
                                transition={{ delay: index * 0.03 }}
                                whileHover={{ scale: 1.01, x: 4 }}
                                className="p-5 rounded-xl border-2 border-border bg-secondary/20 hover:border-accent/50 hover:bg-secondary/40 transition-all"
                              >
                                <div className="flex items-start justify-between gap-4">
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-3 mb-2">
                                      <span className="font-mono font-bold text-lg text-foreground">
                                        {field.name}
                                      </span>
                                      <Badge className="text-xs font-mono font-bold bg-primary/30 border-2 border-primary/40">
                                        {field.type}
                                      </Badge>
                                      <Badge className="text-xs font-mono font-bold bg-accent/30 border-2 border-accent/40 text-accent-foreground">
                                        {field.sizeInBits} bits
                                      </Badge>
                                      <Badge variant="outline" className="text-xs font-mono border-2">
                                        {(field.sizeInBits / 8).toFixed(2)} bytes
                                      </Badge>
                                    </div>
                                    {field.description && (
                                      <p className="text-sm text-muted-foreground leading-relaxed">
                                        {field.description}
                                      </p>
                                    )}
                                  </div>
                                  <div className="flex gap-1">
                                    <Button
                                      size="lg"
                                      variant="ghost"
                                      className="hover:bg-primary/20 hover:text-accent"
                                      onClick={() => handleMoveField(field.id, 'up')}
                                      disabled={index === 0}
                                    >
                                      <ArrowUp weight="bold" />
                                    </Button>
                                    <Button
                                      size="lg"
                                      variant="ghost"
                                      className="hover:bg-primary/20 hover:text-accent"
                                      onClick={() => handleMoveField(field.id, 'down')}
                                      disabled={index === selectedProtocol.fields.length - 1}
                                    >
                                      <ArrowDown weight="bold" />
                                    </Button>
                                    <Button
                                      size="lg"
                                      variant="ghost"
                                      className="hover:bg-accent/20 hover:text-accent"
                                      onClick={() => {
                                        setEditingField(field);
                                        setFieldDialogOpen(true);
                                      }}
                                    >
                                      <Pencil weight="bold" />
                                    </Button>
                                    <Button
                                      size="lg"
                                      variant="ghost"
                                      className="hover:bg-destructive/20 hover:text-destructive"
                                      onClick={() => setDeleteFieldId(field.id)}
                                    >
                                      <Trash weight="bold" />
                                    </Button>
                                  </div>
                                </div>
                              </motion.div>
                            ))}
                          </AnimatePresence>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}
          </div>
        </div>
      </div>

      <ProtocolDialog
        open={protocolDialogOpen}
        onOpenChange={setProtocolDialogOpen}
        onSave={editingProtocol ? handleEditProtocol : handleCreateProtocol}
        initialData={
          editingProtocol
            ? {
                name: editingProtocol.name,
                version: editingProtocol.version,
                description: editingProtocol.description,
              }
            : undefined
        }
        mode={editingProtocol ? 'edit' : 'create'}
      />

      <FieldDialog
        open={fieldDialogOpen}
        onOpenChange={setFieldDialogOpen}
        onSave={editingField ? handleEditField : handleAddField}
        initialData={
          editingField
            ? {
                name: editingField.name,
                type: editingField.type,
                sizeInBits: editingField.sizeInBits,
                description: editingField.description,
              }
            : undefined
        }
        mode={editingField ? 'edit' : 'create'}
      />

      <AlertDialog open={!!deleteProtocolId} onOpenChange={() => setDeleteProtocolId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Protocol?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete the protocol and all its
              fields.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteProtocol}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!deleteFieldId} onOpenChange={() => setDeleteFieldId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Field?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete the field.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteField}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default App;