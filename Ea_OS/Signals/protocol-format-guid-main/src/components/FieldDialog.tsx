import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useState, useEffect } from 'react';
import { DataType, DATA_TYPE_SIZES } from '@/lib/types';

interface FieldDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: { name: string; type: DataType; sizeInBits: number; description: string }) => void;
  initialData?: { name: string; type: DataType; sizeInBits: number; description: string };
  mode: 'create' | 'edit';
}

export function FieldDialog({
  open,
  onOpenChange,
  onSave,
  initialData,
  mode,
}: FieldDialogProps) {
  const [name, setName] = useState(initialData?.name || '');
  const [type, setType] = useState<DataType>(initialData?.type || 'uint8');
  const [sizeInBits, setSizeInBits] = useState(initialData?.sizeInBits?.toString() || '8');
  const [description, setDescription] = useState(initialData?.description || '');

  useEffect(() => {
    if (initialData) {
      setName(initialData.name);
      setType(initialData.type);
      setSizeInBits(initialData.sizeInBits.toString());
      setDescription(initialData.description);
    }
  }, [initialData]);

  const handleTypeChange = (newType: DataType) => {
    setType(newType);
    const defaultSize = DATA_TYPE_SIZES[newType];
    if (defaultSize > 0) {
      setSizeInBits(defaultSize.toString());
    }
  };

  const handleSave = () => {
    if (!name.trim()) return;
    const bits = parseInt(sizeInBits);
    if (isNaN(bits) || bits <= 0) return;
    
    onSave({
      name: name.trim(),
      type,
      sizeInBits: bits,
      description: description.trim(),
    });
    
    if (mode === 'create') {
      setName('');
      setType('uint8');
      setSizeInBits('8');
      setDescription('');
    }
  };

  const dataTypes: DataType[] = [
    'uint8',
    'uint16',
    'uint32',
    'uint64',
    'int8',
    'int16',
    'int32',
    'int64',
    'float32',
    'float64',
    'string',
    'bytes',
    'custom',
  ];

  const bitsValue = parseInt(sizeInBits) || 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] border-2 border-primary/40 bg-card/95 backdrop-blur-xl card-glow">
        <DialogHeader>
          <DialogTitle className="text-2xl font-black gradient-text">
            {mode === 'create' ? '⚡ Add Field' : '⚡ Edit Field'}
          </DialogTitle>
          <DialogDescription className="text-base">
            {mode === 'create'
              ? 'Define a new field with precise data type specifications.'
              : 'Update field configuration and metadata.'}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-6 py-6">
          <div className="grid gap-3">
            <Label htmlFor="field-name" className="text-sm font-bold uppercase tracking-wider">
              Field Name
            </Label>
            <Input
              id="field-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="sourcePort"
              className="text-base font-mono font-semibold border-2 focus:border-primary bg-secondary/30"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-3">
              <Label htmlFor="field-type" className="text-sm font-bold uppercase tracking-wider">
                Data Type
              </Label>
              <Select value={type} onValueChange={handleTypeChange}>
                <SelectTrigger id="field-type" className="border-2 focus:border-primary bg-secondary/30">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-2 border-primary/30 bg-card/95 backdrop-blur-xl">
                  {dataTypes.map((dt) => (
                    <SelectItem key={dt} value={dt} className="font-mono font-semibold">
                      {dt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-3">
              <Label htmlFor="field-size" className="text-sm font-bold uppercase tracking-wider flex items-center justify-between">
                Size (bits)
                <Badge className="font-mono text-xs bg-accent/30 border border-accent/50">
                  {(bitsValue / 8).toFixed(2)} bytes
                </Badge>
              </Label>
              <Input
                id="field-size"
                type="number"
                value={sizeInBits}
                onChange={(e) => setSizeInBits(e.target.value)}
                placeholder="8"
                min="1"
                className="text-base font-mono font-semibold border-2 focus:border-primary bg-secondary/30"
              />
            </div>
          </div>
          <div className="grid gap-3">
            <Label htmlFor="field-description" className="text-sm font-bold uppercase tracking-wider">
              Description
            </Label>
            <Textarea
              id="field-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the field purpose and usage..."
              rows={3}
              className="text-base border-2 focus:border-primary bg-secondary/30 resize-none"
            />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button 
            variant="outline" 
            onClick={() => onOpenChange(false)}
            className="border-2 hover:bg-secondary/40"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={!name.trim() || !sizeInBits || parseInt(sizeInBits) <= 0}
            className="bg-primary hover:bg-primary/80 accent-glow font-bold"
          >
            {mode === 'create' ? '⚡ Add Field' : '⚡ Save Changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
