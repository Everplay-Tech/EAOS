#!/usr/bin/env node
import fs from 'fs';
import { createCipheriv, createDecipheriv, pbkdf2Sync, randomBytes } from 'crypto';
import path from 'path';
import { fileURLToPath } from 'url';

const WRAPPER_MAGIC = Buffer.from('QYN1');
const PAYLOAD_MAGIC = Buffer.from('MCS\0');
const PBKDF2_ROUNDS = 200000;

const FEATURE_BITS = {
  'compression:optimisation': 0,
  'compression:extras': 1,
  'payload:source-map': 2,
  'compression:fse': 3,
};

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const canonicalVersions = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', 'canonical_versions.json'), 'utf8')
);

const PAYLOAD_CHANNEL_SECTIONS = {
  identifiers: 0x0101,
  strings: 0x0102,
  integers: 0x0103,
  counts: 0x0104,
  flags: 0x0105,
};

function canonicalJson(value) {
  if (typeof value === 'string' && value.startsWith('__pyfloat:')) {
    return value.slice('__pyfloat:'.length);
  }
  if (Array.isArray(value)) {
    return '[' + value.map(canonicalJson).join(',') + ']';
  }
  if (value && typeof value === 'object') {
    const keys = Object.keys(value).sort();
    return (
      '{' +
      keys.map((key) => JSON.stringify(key) + ':' + canonicalJson(value[key])).join(',') +
      '}'
    );
  }
  return JSON.stringify(value);
}

function parseVersion(text) {
  const parts = text.split('.');
  if (parts.length === 2) parts.push('0');
  if (parts.length !== 3) throw new Error(`invalid version '${text}'`);
  return [Number(parts[0]), Number(parts[1]), Number(parts[2])];
}

function crc32(buffer) {
  let crc = ~0;
  for (let i = 0; i < buffer.length; i++) {
    crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ buffer[i]) & 0xff];
  }
  return ~crc >>> 0;
}

function isDigit(ch) {
  return ch >= '0' && ch <= '9';
}

function isNumberChar(ch) {
  return isDigit(ch) || ch === '-' || ch === '+' || ch === '.' || ch === 'e' || ch === 'E';
}

function parseWithFloatSentinels(text) {
  const transformed = [];
  let inString = false;
  let escape = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      transformed.push(ch);
      if (escape) {
        escape = false;
        continue;
      }
      if (ch === '\\') {
        escape = true;
      } else if (ch === '\"') {
        inString = false;
      }
      continue;
    }
    if (ch === '\"') {
      inString = true;
      transformed.push(ch);
      continue;
    }
    if (ch === '-' || isDigit(ch)) {
      let j = i + 1;
      while (j < text.length && isNumberChar(text[j])) {
        j += 1;
      }
      const literal = text.slice(i, j);
      if (literal.includes('.')) {
        transformed.push('\"__pyfloat:' + literal + '\"');
      } else {
        transformed.push(literal);
      }
      i = j - 1;
      continue;
    }
    transformed.push(ch);
  }
  return JSON.parse(transformed.join(''));
}

function writeFrame(magic, version, features, body) {
  const header = Buffer.alloc(16);
  magic.copy(header, 0);
  header.writeUInt8(version[0], 4);
  header.writeUInt8(version[1], 5);
  header.writeUInt16BE(version[2], 6);
  header.writeUInt32BE(encodeFeatureBits(features), 8);
  header.writeUInt32BE(body.length, 12);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body), 0);
  return Buffer.concat([header, body, crc]);
}

function readFrame(data, expectedMagic) {
  if (data.length < 20) throw new Error('frame too small');
  if (!data.subarray(0, 4).equals(expectedMagic)) throw new Error('unexpected frame magic');
  const version = [data.readUInt8(4), data.readUInt8(5), data.readUInt16BE(6)];
  const featureBits = data.readUInt32BE(8);
  const length = data.readUInt32BE(12);
  const bodyStart = 16;
  const bodyEnd = bodyStart + length;
  const crcEnd = bodyEnd + 4;
  if (crcEnd > data.length) throw new Error('frame truncated');
  const body = data.subarray(bodyStart, bodyEnd);
  const stored = data.readUInt32BE(bodyEnd);
  if (crc32(body) !== stored) throw new Error('frame CRC mismatch');
  const features = decodeFeatureBits(featureBits);
  return [{ version, features, length }, body, data.subarray(crcEnd)];
}

function encodeFeatureBits(features) {
  const sorted = [...new Set(features)].sort();
  let bits = 0;
  for (const feature of sorted) {
    const idx = FEATURE_BITS[feature];
    if (idx === undefined) throw new Error(`unknown feature '${feature}'`);
    bits |= 1 << idx;
  }
  return bits >>> 0;
}

function decodeFeatureBits(bits) {
  const features = [];
  for (const [name, idx] of Object.entries(FEATURE_BITS)) {
    if (bits & (1 << idx)) features.push(name);
  }
  const unknown = bits & ~encodeFeatureBits(features);
  if (unknown) throw new Error(`frame advertises unknown feature bits 0x${unknown.toString(16)}`);
  return features.sort();
}

function writeUtf8(text) {
  const encoded = Buffer.from(text, 'utf8');
  const out = Buffer.alloc(2 + encoded.length);
  out.writeUInt16LE(encoded.length, 0);
  encoded.copy(out, 2);
  return out;
}

function readUtf8(buffer, offsetObj) {
  const length = buffer.readUInt16LE(offsetObj.value);
  offsetObj.value += 2;
  const value = buffer.toString('utf8', offsetObj.value, offsetObj.value + length);
  offsetObj.value += length;
  return value;
}

function writeLengthPrefixed(buf) {
  const out = Buffer.alloc(4 + buf.length);
  out.writeUInt32LE(buf.length, 0);
  buf.copy(out, 4);
  return out;
}

function readLengthPrefixed(buffer, offsetObj) {
  const length = buffer.readUInt32LE(offsetObj.value);
  offsetObj.value += 4;
  const slice = buffer.subarray(offsetObj.value, offsetObj.value + length);
  offsetObj.value += length;
  return slice;
}

function writeSection(id, flags, payload) {
  const header = Buffer.alloc(8);
  header.writeUInt16LE(id, 0);
  header.writeUInt16LE(flags, 2);
  header.writeUInt32LE(payload.length, 4);
  return Buffer.concat([header, payload]);
}

function readSections(body) {
  const sections = new Map();
  let offset = 0;
  while (offset < body.length) {
    const sid = body.readUInt16LE(offset);
    const flags = body.readUInt16LE(offset + 2);
    const length = body.readUInt32LE(offset + 4);
    offset += 8;
    const payload = body.subarray(offset, offset + length);
    offset += length;
    sections.set(sid, { flags, payload });
  }
  return sections;
}

function metadataAAD(metadata) {
  return Buffer.from('QYN1-METADATA-v1:' + canonicalJson(metadata), 'utf8');
}

function encodeDescriptor(descriptor, passphrase) {
  const wrapperVersionText = descriptor.wrapper_version || canonicalVersions.wrapper_version;
  const payloadVersionText = descriptor.payload_version || canonicalVersions.payload_version;
  const wrapperVersion = parseVersion(wrapperVersionText);
  const payloadVersion = parseVersion(payloadVersionText);

  const stream = descriptor.sections.stream_header;
  const dictionaryVersion = stream.dictionary_version || canonicalVersions.dictionary_version;
  const streamParts = [];
  streamParts.push(writeUtf8(dictionaryVersion));
  streamParts.push(writeUtf8(stream.encoder_version || ''));
  streamParts.push(writeUtf8(stream.source_language || ''));
  streamParts.push(writeUtf8(stream.source_language_version || ''));
  const countBuf = Buffer.alloc(4);
  countBuf.writeUInt32LE(stream.symbol_count || 0);
  streamParts.push(countBuf);
  streamParts.push(Buffer.from([0]));
  if (stream.source_hash) {
    streamParts.push(Buffer.from(stream.source_hash, 'hex'));
  } else {
    streamParts.push(Buffer.alloc(32));
  }
  const streamSection = writeSection(
    0x0001,
    stream.has_source_map ? 0x0001 : 0,
    Buffer.concat(streamParts)
  );

  const compression = descriptor.sections.compression;
  const compParts = [];
  compParts.push(writeUtf8(compression.backend));
  const compCount = Buffer.alloc(4);
  compCount.writeUInt32LE(compression.symbol_count);
  compParts.push(compCount);
  compParts.push(writeLengthPrefixed(Buffer.from(canonicalJson(compression.model || {}), 'utf8')));
  const extras = compression.extras || {};
  const extrasBlob = Object.keys(extras).length
    ? Buffer.from(canonicalJson(extras), 'utf8')
    : Buffer.alloc(0);
  compParts.push(writeLengthPrefixed(extrasBlob));
  const compressionSection = writeSection(0x0002, 0, Buffer.concat(compParts));

  const tokens = Buffer.from(descriptor.sections.tokens, 'base64');
  const tokensSection = writeSection(0x0003, 0, writeLengthPrefixed(tokens));

  const stringTable = Buffer.from(descriptor.sections.string_table, 'base64');
  const stringSection = writeSection(0x0004, 0, writeLengthPrefixed(stringTable));

  const payloadSection = writeSection(
    0x0005,
    0,
    writeLengthPrefixed(Buffer.from(canonicalJson(descriptor.sections.payloads || {}), 'utf8'))
  );

  const channelSections = [];
  const payloadChannels = descriptor.sections.payload_channels || {};
  for (const [name, sid] of Object.entries(PAYLOAD_CHANNEL_SECTIONS)) {
    const payload = payloadChannels[name];
    if (!payload) continue;
    channelSections.push(
      writeSection(sid, 0, writeLengthPrefixed(Buffer.from(canonicalJson(payload), 'utf8')))
    );
  }

  let sourceMapSection = Buffer.alloc(0);
  if (descriptor.sections.source_map) {
    const sourceMap = Buffer.from(descriptor.sections.source_map, 'base64');
    sourceMapSection = writeSection(0x0006, 0, writeLengthPrefixed(sourceMap));
  }

  const metadataJson = canonicalJson(descriptor.metadata);
  const metadataSection = writeSection(
    0x0007,
    0,
    writeLengthPrefixed(Buffer.from(metadataJson, 'utf8'))
  );

  const payloadBody = Buffer.concat([
    streamSection,
    compressionSection,
    tokensSection,
    stringSection,
    payloadSection,
    ...channelSections,
    sourceMapSection,
    metadataSection,
  ]);

  let features = descriptor.payload_features || [];
  if (!features.length) {
    if (Object.keys(extras).length) {
      features.push('compression:extras');
      if (extras.optimisation) features.push('compression:optimisation');
    }
    if (compression.backend === 'fse') features.push('compression:fse');
    if (sourceMapSection.length) features.push('payload:source-map');
  }

  const payloadFrame = writeFrame(PAYLOAD_MAGIC, payloadVersion, features, payloadBody);

  const salt = descriptor.salt ? Buffer.from(descriptor.salt, 'base64') : randomBytes(16);
  const nonce = descriptor.nonce ? Buffer.from(descriptor.nonce, 'base64') : randomBytes(12);
  const key = pbkdf2Sync(passphrase, salt, PBKDF2_ROUNDS, 32, 'sha256');
  const cipher = createCipheriv('chacha20-poly1305', key, nonce, { authTagLength: 16 });
  cipher.setAAD(metadataAAD(descriptor.metadata), { plaintextLength: payloadFrame.length });
  const ciphertext = Buffer.concat([cipher.update(payloadFrame), cipher.final()]);
  const tag = cipher.getAuthTag();

  const wrapper = {
    version: wrapperVersionText,
    payload_version: payloadVersionText,
    payload_features: features.sort(),
    metadata: descriptor.metadata,
    salt: salt.toString('base64'),
    nonce: nonce.toString('base64'),
    ciphertext: ciphertext.toString('base64'),
    tag: tag.toString('base64'),
  };
  const wrapperBytes = Buffer.from(canonicalJson(wrapper), 'utf8');
  return writeFrame(WRAPPER_MAGIC, wrapperVersion, features, wrapperBytes);
}

function decodeDescriptor(data, passphrase) {
  const [wrapperFrame, wrapperBody, wrapperRemainder] = readFrame(data, WRAPPER_MAGIC);
  if (wrapperRemainder.length) throw new Error('unexpected trailing data after wrapper');
  const wrapper = JSON.parse(wrapperBody.toString('utf8'));
  const advertised = (wrapper.payload_features || []).sort();
  if (advertised.length && !sameFeatures(advertised, wrapperFrame.features)) {
    throw new Error('wrapper feature bitset mismatch');
  }

  const salt = Buffer.from(wrapper.salt, 'base64');
  const nonce = Buffer.from(wrapper.nonce, 'base64');
  const ciphertext = Buffer.from(wrapper.ciphertext, 'base64');
  const tag = Buffer.from(wrapper.tag, 'base64');
  const aad = metadataAAD(wrapper.metadata);
  const key = pbkdf2Sync(passphrase, salt, PBKDF2_ROUNDS, 32, 'sha256');
  const decipher = createDecipheriv('chacha20-poly1305', key, nonce, { authTagLength: 16 });
  decipher.setAAD(aad, { plaintextLength: ciphertext.length });
  decipher.setAuthTag(tag);
  const payloadFrameBytes = Buffer.concat([decipher.update(ciphertext), decipher.final()]);

  const [payloadFrame, payloadBody, payloadRemainder] = readFrame(payloadFrameBytes, PAYLOAD_MAGIC);
  if (payloadRemainder.length) throw new Error('unexpected trailing data after payload');
  if (!sameFeatures(wrapperFrame.features, payloadFrame.features)) {
    throw new Error('payload feature set mismatch with wrapper');
  }

  const sections = readSections(payloadBody);

  const stream = sections.get(0x0001);
  const streamOffset = { value: 0 };
  const dictionaryVersion = readUtf8(stream.payload, streamOffset);
  const encoderVersion = readUtf8(stream.payload, streamOffset);
  const sourceLanguage = readUtf8(stream.payload, streamOffset);
  const sourceLanguageVersion = readUtf8(stream.payload, streamOffset);
  const symbolCount = stream.payload.readUInt32LE(streamOffset.value);
  streamOffset.value += 5; // symbol count + hash type
  const sourceHashBytes = stream.payload.subarray(streamOffset.value, streamOffset.value + 32);
  const sourceHash = sourceHashBytes.every((b) => b === 0) ? '' : sourceHashBytes.toString('hex');

  const compression = sections.get(0x0002);
  const compOffset = { value: 0 };
  const backend = readUtf8(compression.payload, compOffset);
  const compSymbolCount = compression.payload.readUInt32LE(compOffset.value);
  compOffset.value += 4;
  const modelBlob = readLengthPrefixed(compression.payload, compOffset);
  const extrasBlob = readLengthPrefixed(compression.payload, compOffset);
  const model = JSON.parse(modelBlob.toString('utf8') || '{}');
  const extras = extrasBlob.length ? JSON.parse(extrasBlob.toString('utf8')) : {};

  const tokens = readLengthPrefixed(sections.get(0x0003).payload, { value: 0 });
  const stringTable = readLengthPrefixed(sections.get(0x0004).payload, { value: 0 });
  const payloads = JSON.parse(
    readLengthPrefixed(sections.get(0x0005).payload, { value: 0 }).toString('utf8')
  );

  const payloadChannels = {};
  for (const [name, sid] of Object.entries(PAYLOAD_CHANNEL_SECTIONS)) {
    if (!sections.has(sid)) continue;
    payloadChannels[name] = JSON.parse(
      readLengthPrefixed(sections.get(sid).payload, { value: 0 }).toString('utf8')
    );
  }

  let sourceMap;
  if (sections.has(0x0006)) {
    const mapBytes = readLengthPrefixed(sections.get(0x0006).payload, { value: 0 });
    sourceMap = mapBytes.toString('base64');
  }
  const metadataInner = JSON.parse(
    readLengthPrefixed(sections.get(0x0007).payload, { value: 0 }).toString('utf8')
  );

  const descriptor = {
    wrapper_version: versionText(wrapperFrame.version),
    payload_version: versionText(payloadFrame.version),
    payload_features: payloadFrame.features,
    metadata: metadataInner,
    salt: wrapper.salt,
    nonce: wrapper.nonce,
    sections: {
      stream_header: {
        dictionary_version: dictionaryVersion,
        encoder_version: encoderVersion,
        source_language: sourceLanguage,
        source_language_version: sourceLanguageVersion,
        symbol_count: symbolCount,
        source_hash: sourceHash,
        has_source_map: Boolean(stream.flags & 0x0001),
      },
      compression: {
        backend,
        symbol_count: compSymbolCount,
        model,
        extras,
      },
      tokens: tokens.toString('base64'),
      string_table: stringTable.toString('base64'),
      payloads,
    },
  };
  if (Object.keys(payloadChannels).length) {
    descriptor.sections.payload_channels = payloadChannels;
  }
  if (sourceMap) descriptor.sections.source_map = sourceMap;
  return descriptor;
}

function versionText(version) {
  return `${version[0]}.${version[1]}.${version[2]}`;
}

function sameFeatures(a, b) {
  const left = [...a].sort();
  const right = [...b].sort();
  if (left.length !== right.length) return false;
  return left.every((val, idx) => val === right[idx]);
}

function readInput(path) {
  return path ? fs.readFileSync(path) : fs.readFileSync(0);
}

function writeOutput(path, data) {
  if (path) {
    fs.writeFileSync(path, data);
  } else {
    process.stdout.write(data);
  }
}

function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error(
      'Usage: mcs.js <encode|decode> --passphrase <value> [--input path] [--output path]'
    );
    console.error(
      'Features: framed packages with CRC-32 validation and payload channels. Limitations: legacy payload formats are not supported.'
    );
    process.exit(1);
  }
  const command = args[0];
  const passIdx = args.indexOf('--passphrase');
  if (passIdx === -1 || passIdx + 1 >= args.length) {
    console.error('Missing --passphrase');
    process.exit(1);
  }
  const passphrase = args[passIdx + 1];
  const inputIdx = args.indexOf('--input');
  const inputPath = inputIdx !== -1 ? args[inputIdx + 1] : null;
  const outputIdx = args.indexOf('--output');
  const outputPath = outputIdx !== -1 ? args[outputIdx + 1] : null;

  if (command === 'encode') {
    const rawInput = readInput(inputPath).toString();
    const descriptor = parseWithFloatSentinels(rawInput);
    const encoded = encodeDescriptor(descriptor, passphrase);
    writeOutput(outputPath, Buffer.from(encoded.toString('base64')));
  } else if (command === 'decode') {
    const data = readInput(inputPath).toString().trim();
    const bytes = Buffer.from(data, 'base64');
    const descriptor = decodeDescriptor(bytes, passphrase);
    writeOutput(outputPath, Buffer.from(JSON.stringify(descriptor)));
  } else {
    console.error('Unknown command');
    process.exit(1);
  }
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) {
      c = (c & 1) ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c >>> 0;
  }
  return table;
})();

main();
