import { Protocol } from '@/lib/types';

export function generateProtocolId(): string {
  return `protocol-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export function generateFieldId(): string {
  return `field-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export function exportProtocolAsJSON(protocol: Protocol): string {
  return JSON.stringify(protocol, null, 2);
}

export function exportProtocolAsText(protocol: Protocol): string {
  let output = '';
  output += `Protocol: ${protocol.name}\n`;
  output += `Version: ${protocol.version}\n`;
  output += `Description: ${protocol.description}\n`;
  output += `\n`;
  output += `Fields:\n`;
  output += `${'='.repeat(80)}\n`;
  
  let bitOffset = 0;
  protocol.fields.forEach((field, index) => {
    output += `\n${index + 1}. ${field.name}\n`;
    output += `   Type: ${field.type}\n`;
    output += `   Size: ${field.sizeInBits} bits (${field.sizeInBits / 8} bytes)\n`;
    output += `   Offset: bit ${bitOffset}\n`;
    output += `   Description: ${field.description}\n`;
    bitOffset += field.sizeInBits;
  });
  
  output += `\n${'='.repeat(80)}\n`;
  output += `Total Size: ${bitOffset} bits (${bitOffset / 8} bytes)\n`;
  
  return output;
}
