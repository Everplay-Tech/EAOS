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
import { useState } from 'react';

interface ProtocolDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: { name: string; version: string; description: string }) => void;
  initialData?: { name: string; version: string; description: string };
  mode: 'create' | 'edit';
}

export function ProtocolDialog({
  open,
  onOpenChange,
  onSave,
  initialData,
  mode,
}: ProtocolDialogProps) {
  const [name, setName] = useState(initialData?.name || '');
  const [version, setVersion] = useState(initialData?.version || '1.0');
  const [description, setDescription] = useState(initialData?.description || '');

  const handleSave = () => {
    if (!name.trim()) return;
    onSave({ name: name.trim(), version: version.trim(), description: description.trim() });
    if (mode === 'create') {
      setName('');
      setVersion('1.0');
      setDescription('');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] border-2 border-accent/40 bg-card/95 backdrop-blur-xl card-glow">
        <DialogHeader>
          <DialogTitle className="text-2xl font-black gradient-text">
            {mode === 'create' ? '✦ New Protocol' : '✦ Edit Protocol'}
          </DialogTitle>
          <DialogDescription className="text-base">
            {mode === 'create'
              ? 'Create a new protocol specification with comprehensive details.'
              : 'Update protocol details and metadata.'}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-6 py-6">
          <div className="grid gap-3">
            <Label htmlFor="protocol-name" className="text-sm font-bold uppercase tracking-wider">
              Protocol Name
            </Label>
            <Input
              id="protocol-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="HTTP Header"
              className="text-base font-semibold border-2 focus:border-accent bg-secondary/30"
            />
          </div>
          <div className="grid gap-3">
            <Label htmlFor="protocol-version" className="text-sm font-bold uppercase tracking-wider">
              Version
            </Label>
            <Input
              id="protocol-version"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="1.0"
              className="text-base font-mono font-semibold border-2 focus:border-accent bg-secondary/30"
            />
          </div>
          <div className="grid gap-3">
            <Label htmlFor="protocol-description" className="text-sm font-bold uppercase tracking-wider">
              Description
            </Label>
            <Textarea
              id="protocol-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the protocol format in detail..."
              rows={4}
              className="text-base border-2 focus:border-accent bg-secondary/30 resize-none"
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
            disabled={!name.trim()}
            className="bg-accent hover:bg-accent/80 text-accent-foreground accent-glow font-bold"
          >
            {mode === 'create' ? '✦ Create Protocol' : '✦ Save Changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
