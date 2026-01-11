import { ProtocolField } from '@/lib/types';
import { motion } from 'framer-motion';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

interface ByteLayoutProps {
  fields: ProtocolField[];
}

interface FieldSegment {
  field: ProtocolField;
  fieldIndex: number;
  startBit: number;
  endBit: number;
  widthPercent: number;
}

export function ByteLayout({ fields }: ByteLayoutProps) {
  if (fields.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-foreground text-base border-2 border-dashed border-border rounded-xl bg-secondary/20">
        No fields to visualize
      </div>
    );
  }

  const totalBits = fields.reduce((sum, field) => sum + field.sizeInBits, 0);
  const BITS_PER_ROW = 32;

  const calculateSegments = () => {
    const rowSegments: FieldSegment[][] = [];
    let currentBit = 0;

    fields.forEach((field, fieldIndex) => {
      let remainingBits = field.sizeInBits;

      while (remainingBits > 0) {
        const bitPositionInRow = currentBit % BITS_PER_ROW;
        const bitsToEndOfRow = BITS_PER_ROW - bitPositionInRow;
        const bitsInThisSegment = Math.min(remainingBits, bitsToEndOfRow);
        const widthPercent = (bitsInThisSegment / BITS_PER_ROW) * 100;

        const rowIndex = Math.floor(currentBit / BITS_PER_ROW);

        if (!rowSegments[rowIndex]) {
          rowSegments[rowIndex] = [];
        }

        rowSegments[rowIndex].push({
          field,
          fieldIndex,
          startBit: currentBit,
          endBit: currentBit + bitsInThisSegment - 1,
          widthPercent,
        });

        remainingBits -= bitsInThisSegment;
        currentBit += bitsInThisSegment;
      }
    });

    return rowSegments;
  };

  const rowSegments = calculateSegments();

  const colors = [
    { bg: 'from-blue-500/40 to-blue-600/60', border: 'border-blue-400', text: 'text-blue-100', glow: 'shadow-blue-500/50' },
    { bg: 'from-purple-500/40 to-purple-600/60', border: 'border-purple-400', text: 'text-purple-100', glow: 'shadow-purple-500/50' },
    { bg: 'from-green-500/40 to-green-600/60', border: 'border-green-400', text: 'text-green-100', glow: 'shadow-green-500/50' },
    { bg: 'from-orange-500/40 to-orange-600/60', border: 'border-orange-400', text: 'text-orange-100', glow: 'shadow-orange-500/50' },
    { bg: 'from-pink-500/40 to-pink-600/60', border: 'border-pink-400', text: 'text-pink-100', glow: 'shadow-pink-500/50' },
    { bg: 'from-cyan-500/40 to-cyan-600/60', border: 'border-cyan-400', text: 'text-cyan-100', glow: 'shadow-cyan-500/50' },
    { bg: 'from-yellow-500/40 to-yellow-600/60', border: 'border-yellow-400', text: 'text-yellow-100', glow: 'shadow-yellow-500/50' },
    { bg: 'from-red-500/40 to-red-600/60', border: 'border-red-400', text: 'text-red-100', glow: 'shadow-red-500/50' },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-5"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-bold uppercase tracking-wider flex items-center gap-2">
          <span className="text-accent">◆</span>
          Byte Layout Visualization
        </h3>
        <div className="flex items-center gap-3">
          <Badge className="text-base font-mono font-black px-4 py-2 bg-gradient-to-r from-primary/40 to-accent/40 border-2 border-accent/50">
            {totalBits} bits
          </Badge>
          <Badge className="text-base font-mono font-black px-4 py-2 bg-gradient-to-r from-accent/40 to-primary/40 border-2 border-primary/50">
            {(totalBits / 8).toFixed(2)} bytes
          </Badge>
        </div>
      </div>
      
      <div className="border-2 border-accent/40 rounded-2xl overflow-hidden bg-secondary/30 shadow-2xl">
        <div className="bg-gradient-to-r from-primary/30 via-accent/30 to-primary/30 px-4 py-3 border-b-2 border-accent/40">
          <div className="flex items-center justify-between text-xs font-bold uppercase tracking-widest">
            <span className="text-muted-foreground">Bit Position</span>
            <span className="text-muted-foreground">Field Structure</span>
          </div>
        </div>
        {rowSegments.map((segments, rowIndex) => (
          <motion.div
            key={rowIndex}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: rowIndex * 0.05 }}
            className="flex border-b-2 border-border/50 last:border-b-0 hover:bg-secondary/20 transition-colors"
          >
            <div className="w-24 flex-shrink-0 flex items-center justify-center text-sm text-accent font-mono font-bold border-r-2 border-accent/40 bg-secondary/40">
              {rowIndex * BITS_PER_ROW}
            </div>
            <div className="flex-1 flex min-h-[80px]">
              {segments.map((segment, segIdx) => {
                const colorScheme = colors[segment.fieldIndex % colors.length];
                const isFirstSegmentOfField = segment.startBit % segment.field.sizeInBits === 0;
                const segmentWidth = segment.endBit - segment.startBit + 1;

                return (
                  <TooltipProvider key={segIdx}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <motion.div
                          whileHover={{ scale: 1.05, zIndex: 10 }}
                          className={`bg-gradient-to-br ${colorScheme.bg} ${colorScheme.border} ${colorScheme.text} border-2 flex flex-col items-center justify-center text-xs font-mono font-bold px-2 py-2 transition-all cursor-pointer hover:shadow-lg ${colorScheme.glow} relative`}
                          style={{ width: `${segment.widthPercent}%` }}
                        >
                          {isFirstSegmentOfField && segmentWidth >= 4 && (
                            <span className="truncate text-center font-black text-sm">
                              {segment.field.name}
                            </span>
                          )}
                          <span className="text-[10px] opacity-80 mt-1">
                            {segment.startBit}-{segment.endBit}
                          </span>
                        </motion.div>
                      </TooltipTrigger>
                      <TooltipContent className="max-w-sm bg-card/95 backdrop-blur-sm border-2 border-accent/40 p-4">
                        <div className="space-y-2">
                          <div className="font-black text-base text-accent">{segment.field.name}</div>
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            <div>
                              <span className="text-muted-foreground">Type:</span>
                              <span className="ml-2 font-mono font-bold">{segment.field.type}</span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">Size:</span>
                              <span className="ml-2 font-mono font-bold">{segment.field.sizeInBits} bits</span>
                            </div>
                          </div>
                          <div className="text-sm">
                            <span className="text-muted-foreground">Bit Range:</span>
                            <span className="ml-2 font-mono font-bold text-accent">
                              {segment.startBit} → {segment.endBit}
                            </span>
                          </div>
                          {segment.field.description && (
                            <div className="pt-2 border-t border-border/50">
                              <p className="text-xs text-muted-foreground leading-relaxed">
                                {segment.field.description}
                              </p>
                            </div>
                          )}
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                );
              })}
            </div>
          </motion.div>
        ))}
      </div>
      
      <div className="flex flex-wrap gap-2 p-4 bg-secondary/20 rounded-xl border-2 border-border">
        <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground mr-2">Legend:</span>
        {fields.map((field, index) => {
          const colorScheme = colors[index % colors.length];
          return (
            <Badge 
              key={field.id}
              className={`text-xs font-mono font-bold px-3 py-1.5 bg-gradient-to-r ${colorScheme.bg} ${colorScheme.border} ${colorScheme.text} border-2`}
            >
              {field.name}
            </Badge>
          );
        })}
      </div>
    </motion.div>
  );
}
