export type DataType = 
  | 'uint8'
  | 'uint16'
  | 'uint32'
  | 'uint64'
  | 'int8'
  | 'int16'
  | 'int32'
  | 'int64'
  | 'float32'
  | 'float64'
  | 'string'
  | 'bytes'
  | 'custom';

export interface ProtocolField {
  id: string;
  name: string;
  type: DataType;
  sizeInBits: number;
  description: string;
}

export interface Protocol {
  id: string;
  name: string;
  version: string;
  description: string;
  fields: ProtocolField[];
  createdAt: number;
  updatedAt: number;
}

export const DATA_TYPE_SIZES: Record<DataType, number> = {
  uint8: 8,
  uint16: 16,
  uint32: 32,
  uint64: 64,
  int8: 8,
  int16: 16,
  int32: 32,
  int64: 64,
  float32: 32,
  float64: 64,
  string: 0,
  bytes: 0,
  custom: 0,
};
