package main

import (
	"bytes"
	"crypto/rand"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"hash/crc32"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"sort"

	"golang.org/x/crypto/chacha20poly1305"
	"golang.org/x/crypto/pbkdf2"
)

const (
	wrapperMagic = "QYN1"
	payloadMagic = "MCS\x00"
	pbkdfRounds  = 200000
)

var featureBits = map[string]uint32{
	"compression:optimisation": 0,
	"compression:extras":       1,
	"payload:source-map":       2,
	"compression:fse":          3,
}

type canonicalVersions struct {
	WrapperVersion    string `json:"wrapper_version"`
	PayloadVersion    string `json:"payload_version"`
	DictionaryVersion string `json:"dictionary_version"`
}

var canonical = mustLoadCanonicalVersions()

func mustLoadCanonicalVersions() canonicalVersions {
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		panic("unable to locate caller for canonical version load")
	}
	path := filepath.Join(filepath.Dir(filename), "..", "canonical_versions.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		panic(fmt.Sprintf("failed to read canonical versions: %v", err))
	}
	var versions canonicalVersions
	if err := json.Unmarshal(raw, &versions); err != nil {
		panic(fmt.Sprintf("failed to parse canonical versions: %v", err))
	}
	return versions
}

type version struct {
	major uint8
	minor uint8
	patch uint16
}

type descriptor struct {
	WrapperVersion  string                 `json:"wrapper_version"`
	PayloadVersion  string                 `json:"payload_version"`
	PayloadFeatures []string               `json:"payload_features,omitempty"`
	Metadata        map[string]interface{} `json:"metadata"`
	Salt            string                 `json:"salt,omitempty"`
	Nonce           string                 `json:"nonce,omitempty"`
	Sections        sections               `json:"sections"`
}

type sections struct {
	StreamHeader    streamHeader                      `json:"stream_header"`
	Compression     compression                       `json:"compression"`
	Tokens          string                            `json:"tokens"`
	StringTable     string                            `json:"string_table"`
	Payloads        map[string]interface{}            `json:"payloads"`
	PayloadChannels map[string]map[string]interface{} `json:"payload_channels,omitempty"`
	SourceMap       *string                           `json:"source_map,omitempty"`
}

type streamHeader struct {
	DictionaryVersion     string `json:"dictionary_version"`
	EncoderVersion        string `json:"encoder_version"`
	SourceLanguage        string `json:"source_language"`
	SourceLanguageVersion string `json:"source_language_version"`
	SymbolCount           uint32 `json:"symbol_count"`
	SourceHash            string `json:"source_hash"`
	HasSourceMap          bool   `json:"has_source_map"`
}

type compression struct {
	Backend     string                 `json:"backend"`
	SymbolCount uint32                 `json:"symbol_count"`
	Model       map[string]interface{} `json:"model"`
	Extras      map[string]interface{} `json:"extras"`
}

func main() {
	command := flag.String("command", "", "encode or decode a framed package")
	passphrase := flag.String("passphrase", "", "passphrase to derive encryption key")
	inputPath := flag.String("input", "", "input path (default stdin)")
	outputPath := flag.String("output", "", "output path (default stdout)")
	flag.Usage = func() {
		fmt.Fprintf(flag.CommandLine.Output(), "Usage: mcs-reference --command <encode|decode> --passphrase <value> [--input path] [--output path]\n")
		fmt.Fprintf(flag.CommandLine.Output(), "Features: framed packages with CRC-32 validation, payload channels, deterministic canonical JSON. Limitations: legacy wrapper layouts and unknown feature bits are rejected.\n")
		flag.PrintDefaults()
	}
	flag.Parse()

	if *command != "encode" && *command != "decode" {
		fmt.Fprintln(os.Stderr, "command must be encode or decode")
		os.Exit(1)
	}
	if *passphrase == "" {
		fmt.Fprintln(os.Stderr, "--passphrase is required")
		os.Exit(1)
	}

	input, err := readInput(*inputPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	switch *command {
	case "encode":
		var desc descriptor
		if err := json.Unmarshal(input, &desc); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		encoded, err := encodeDescriptor(desc, *passphrase)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		writeOutput(*outputPath, []byte(base64.StdEncoding.EncodeToString(encoded)))
	case "decode":
		raw, err := base64.StdEncoding.DecodeString(string(bytes.TrimSpace(input)))
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		desc, err := decodeDescriptor(raw, *passphrase)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		output, _ := json.Marshal(desc)
		writeOutput(*outputPath, output)
	}
}

func encodeDescriptor(desc descriptor, passphrase string) ([]byte, error) {
	if desc.WrapperVersion == "" {
		desc.WrapperVersion = canonical.WrapperVersion
	}
	if desc.PayloadVersion == "" {
		desc.PayloadVersion = canonical.PayloadVersion
	}
	if desc.Metadata == nil {
		desc.Metadata = map[string]interface{}{}
	}
	if desc.Sections.StreamHeader.DictionaryVersion == "" {
		desc.Sections.StreamHeader.DictionaryVersion = canonical.DictionaryVersion
	}
	if desc.Sections.StreamHeader.EncoderVersion == "" {
		desc.Sections.StreamHeader.EncoderVersion = ""
	}
	wrapperVersion, err := parseVersion(desc.WrapperVersion)
	if err != nil {
		return nil, err
	}
	payloadVersion, err := parseVersion(desc.PayloadVersion)
	if err != nil {
		return nil, err
	}

	streamPayload := bytes.Buffer{}
	streamPayload.Write(writeUTF8(desc.Sections.StreamHeader.DictionaryVersion))
	streamPayload.Write(writeUTF8(desc.Sections.StreamHeader.EncoderVersion))
	streamPayload.Write(writeUTF8(desc.Sections.StreamHeader.SourceLanguage))
	streamPayload.Write(writeUTF8(desc.Sections.StreamHeader.SourceLanguageVersion))
	binary.Write(&streamPayload, binary.LittleEndian, desc.Sections.StreamHeader.SymbolCount)
	streamPayload.WriteByte(0)
	hashBytes := make([]byte, 32)
	if desc.Sections.StreamHeader.SourceHash != "" {
		decoded, err := hexDecode(desc.Sections.StreamHeader.SourceHash)
		if err != nil || len(decoded) != 32 {
			return nil, fmt.Errorf("invalid source hash")
		}
		copy(hashBytes, decoded)
	}
	streamPayload.Write(hashBytes)
	streamSection := writeSection(0x0001, boolToFlag(desc.Sections.StreamHeader.HasSourceMap), streamPayload.Bytes())

	compPayload := bytes.Buffer{}
	compPayload.Write(writeUTF8(desc.Sections.Compression.Backend))
	binary.Write(&compPayload, binary.LittleEndian, desc.Sections.Compression.SymbolCount)
	if desc.Sections.Compression.Model == nil {
		desc.Sections.Compression.Model = map[string]interface{}{}
	}
	compPayload.Write(writeLengthPrefixed([]byte(canonicalJSON(desc.Sections.Compression.Model))))
	if desc.Sections.Compression.Extras == nil {
		desc.Sections.Compression.Extras = map[string]interface{}{}
	}
	compPayload.Write(writeLengthPrefixed([]byte(canonicalJSON(desc.Sections.Compression.Extras))))
	compSection := writeSection(0x0002, 0, compPayload.Bytes())

	tokens, err := base64.StdEncoding.DecodeString(desc.Sections.Tokens)
	if err != nil {
		return nil, err
	}
	tokensSection := writeSection(0x0003, 0, writeLengthPrefixed(tokens))

	table, err := base64.StdEncoding.DecodeString(desc.Sections.StringTable)
	if err != nil {
		return nil, err
	}
	stringSection := writeSection(0x0004, 0, writeLengthPrefixed(table))

	if desc.Sections.Payloads == nil {
		desc.Sections.Payloads = map[string]interface{}{}
	}
	payloadSection := writeSection(0x0005, 0, writeLengthPrefixed([]byte(canonicalJSON(desc.Sections.Payloads))))

	channelSections := [][]byte{}
	channelIDs := map[string]uint16{
		"identifiers": 0x0101,
		"strings":     0x0102,
		"integers":    0x0103,
		"counts":      0x0104,
		"flags":       0x0105,
	}
	for name, sid := range channelIDs {
		payload := desc.Sections.PayloadChannels[name]
		if payload == nil {
			continue
		}
		channelSections = append(channelSections, writeSection(sid, 0, writeLengthPrefixed([]byte(canonicalJSON(payload)))))
	}

	var sourceMapSection []byte
	if desc.Sections.SourceMap != nil {
		blob, err := base64.StdEncoding.DecodeString(*desc.Sections.SourceMap)
		if err != nil {
			return nil, err
		}
		sourceMapSection = writeSection(0x0006, 0, writeLengthPrefixed(blob))
	}

	metadataJSON := canonicalJSON(desc.Metadata)
	metadataSection := writeSection(0x0007, 0, writeLengthPrefixed([]byte(metadataJSON)))

	payloadBody := bytes.Join([][]byte{
		streamSection,
		compSection,
		tokensSection,
		stringSection,
		payloadSection,
		bytes.Join(channelSections, nil),
		sourceMapSection,
		metadataSection,
	}, nil)

	features := desc.PayloadFeatures
	if len(features) == 0 {
		if len(desc.Sections.Compression.Extras) > 0 {
			features = append(features, "compression:extras")
			if _, ok := desc.Sections.Compression.Extras["optimisation"]; ok {
				features = append(features, "compression:optimisation")
			}
		}
		if desc.Sections.Compression.Backend == "fse" {
			features = append(features, "compression:fse")
		}
		if sourceMapSection != nil {
			features = append(features, "payload:source-map")
		}
	}

	payloadFrame := writeFrame([]byte(payloadMagic), payloadVersion, features, payloadBody)

	salt, err := decodeOptionalBase64(desc.Salt, 16)
	if err != nil {
		return nil, fmt.Errorf("salt: %w", err)
	}
	nonce, err := decodeOptionalBase64(desc.Nonce, 12)
	if err != nil {
		return nil, fmt.Errorf("nonce: %w", err)
	}
	if salt == nil {
		salt = randomBytes(16)
	}
	if nonce == nil {
		nonce = randomBytes(12)
	}
	key := pbkdf2.Key([]byte(passphrase), salt, pbkdfRounds, 32, nil)
	aead, err := chacha20poly1305.New(key)
	if err != nil {
		return nil, err
	}
	aad := []byte("QYN1-METADATA-v1:" + metadataJSON)
	sealed := aead.Seal(nil, nonce, payloadFrame, aad)
	ciphertext := sealed[:len(payloadFrame)]
	tag := sealed[len(payloadFrame):]

	wrapper := map[string]interface{}{
		"version":          desc.WrapperVersion,
		"payload_version":  desc.PayloadVersion,
		"payload_features": features,
		"metadata":         desc.Metadata,
		"salt":             base64.StdEncoding.EncodeToString(salt),
		"nonce":            base64.StdEncoding.EncodeToString(nonce),
		"ciphertext":       base64.StdEncoding.EncodeToString(ciphertext),
		"tag":              base64.StdEncoding.EncodeToString(tag),
	}
	wrapperJSON := []byte(canonicalJSON(wrapper))
	return writeFrame([]byte(wrapperMagic), wrapperVersion, features, wrapperJSON), nil
}

func decodeDescriptor(data []byte, passphrase string) (descriptor, error) {
	wrapperHeader, wrapperBody, remainder, err := readFrame(data, []byte(wrapperMagic))
	if err != nil {
		return descriptor{}, err
	}
	if len(remainder) != 0 {
		return descriptor{}, fmt.Errorf("unexpected trailing data after wrapper")
	}

	var wrapper map[string]interface{}
	if err := json.Unmarshal(wrapperBody, &wrapper); err != nil {
		return descriptor{}, err
	}
	wrapperFeatures := toStringSlice(wrapper["payload_features"])
	if len(wrapperFeatures) > 0 && !featureSetsMatch(wrapperFeatures, wrapperHeader.features) {
		return descriptor{}, fmt.Errorf("wrapper feature bitset mismatch")
	}

	metadata, _ := wrapper["metadata"].(map[string]interface{})
	aad := []byte("QYN1-METADATA-v1:" + canonicalJSON(metadata))

	salt, err := base64.StdEncoding.DecodeString(wrapper["salt"].(string))
	if err != nil {
		return descriptor{}, err
	}
	nonce, err := base64.StdEncoding.DecodeString(wrapper["nonce"].(string))
	if err != nil {
		return descriptor{}, err
	}
	ciphertext, err := base64.StdEncoding.DecodeString(wrapper["ciphertext"].(string))
	if err != nil {
		return descriptor{}, err
	}
	tag, err := base64.StdEncoding.DecodeString(wrapper["tag"].(string))
	if err != nil {
		return descriptor{}, err
	}

	key := pbkdf2.Key([]byte(passphrase), salt, pbkdfRounds, 32, nil)
	aead, err := chacha20poly1305.New(key)
	if err != nil {
		return descriptor{}, err
	}
	payloadFrameBytes, err := aead.Open(nil, nonce, append(ciphertext, tag...), aad)
	if err != nil {
		return descriptor{}, err
	}

	payloadHeader, payloadBody, remainder, err := readFrame(payloadFrameBytes, []byte(payloadMagic))
	if err != nil {
		return descriptor{}, err
	}
	if len(remainder) != 0 {
		return descriptor{}, fmt.Errorf("unexpected trailing data after payload")
	}
	if !featureSetsMatch(wrapperFeatures, payloadHeader.features) {
		return descriptor{}, fmt.Errorf("payload feature set mismatch with wrapper")
	}

	sections, err := decodeSections(payloadBody)
	if err != nil {
		return descriptor{}, err
	}
	sectionMap := map[uint16]section{}
	for _, sec := range sections {
		sectionMap[sec.id] = sec
	}

	stream := sectionMap[0x0001]
	streamReader := bytes.NewReader(stream.payload)
	dictionaryVersion, _ := readUTF8(streamReader)
	encoderVersion, _ := readUTF8(streamReader)
	sourceLanguage, _ := readUTF8(streamReader)
	sourceLanguageVersion, _ := readUTF8(streamReader)
	var symbolCount uint32
	binary.Read(streamReader, binary.LittleEndian, &symbolCount)
	streamReader.Read(make([]byte, 1))
	hash := make([]byte, 32)
	streamReader.Read(hash)
	sourceHash := ""
	if !bytes.Equal(hash, make([]byte, 32)) {
		sourceHash = fmt.Sprintf("%x", hash)
	}

	comp := sectionMap[0x0002]
	compReader := bytes.NewReader(comp.payload)
	backend, _ := readUTF8(compReader)
	var compSymbolCount uint32
	binary.Read(compReader, binary.LittleEndian, &compSymbolCount)
	modelBlob := readLengthPrefixed(compReader)
	extrasBlob := readLengthPrefixed(compReader)
	var model map[string]interface{}
	var extras map[string]interface{}
	json.Unmarshal(modelBlob, &model)
	if len(extrasBlob) > 0 {
		json.Unmarshal(extrasBlob, &extras)
	} else {
		extras = map[string]interface{}{}
	}

	tokens := readLengthPrefixed(bytes.NewReader(sectionMap[0x0003].payload))
	stringTable := readLengthPrefixed(bytes.NewReader(sectionMap[0x0004].payload))
	payloadsBlob := readLengthPrefixed(bytes.NewReader(sectionMap[0x0005].payload))
	payloads := map[string]interface{}{}
	json.Unmarshal(payloadsBlob, &payloads)

	channelPayloads := map[string]map[string]interface{}{}
	channelIDs := map[uint16]string{
		0x0101: "identifiers",
		0x0102: "strings",
		0x0103: "integers",
		0x0104: "counts",
		0x0105: "flags",
	}
	for sid, name := range channelIDs {
		sec, ok := sectionMap[sid]
		if !ok {
			continue
		}
		var payload map[string]interface{}
		json.Unmarshal(readLengthPrefixed(bytes.NewReader(sec.payload)), &payload)
		channelPayloads[name] = payload
	}

	var sourceMap *string
	if sec, ok := sectionMap[0x0006]; ok {
		blob := readLengthPrefixed(bytes.NewReader(sec.payload))
		encoded := base64.StdEncoding.EncodeToString(blob)
		sourceMap = &encoded
	}

	metadataBlob := readLengthPrefixed(bytes.NewReader(sectionMap[0x0007].payload))
	var metadataInner map[string]interface{}
	json.Unmarshal(metadataBlob, &metadataInner)

	desc := descriptor{
		WrapperVersion:  wrapperHeader.version.text(),
		PayloadVersion:  payloadHeader.version.text(),
		PayloadFeatures: payloadHeader.features,
		Metadata:        metadataInner,
		Salt:            base64.StdEncoding.EncodeToString(salt),
		Nonce:           base64.StdEncoding.EncodeToString(nonce),
		Sections: sections{
			StreamHeader: streamHeader{
				DictionaryVersion:     dictionaryVersion,
				EncoderVersion:        encoderVersion,
				SourceLanguage:        sourceLanguage,
				SourceLanguageVersion: sourceLanguageVersion,
				SymbolCount:           symbolCount,
				SourceHash:            sourceHash,
				HasSourceMap:          stream.flags&0x0001 != 0,
			},
			Compression: compression{
				Backend:     backend,
				SymbolCount: compSymbolCount,
				Model:       model,
				Extras:      extras,
			},
			Tokens:          base64.StdEncoding.EncodeToString(tokens),
			StringTable:     base64.StdEncoding.EncodeToString(stringTable),
			Payloads:        payloads,
			PayloadChannels: channelPayloads,
			SourceMap:       sourceMap,
		},
	}
	if len(channelPayloads) == 0 {
		desc.Sections.PayloadChannels = nil
	}
	if sourceMap == nil {
		desc.Sections.SourceMap = nil
	}
	return desc, nil
}

func parseVersion(text string) (version, error) {
	parts := splitAndPad(text, ".")
	if len(parts) != 3 {
		return version{}, fmt.Errorf("invalid version %q", text)
	}
	vals := make([]uint64, 3)
	for i, part := range parts {
		var v uint64
		for _, ch := range part {
			if ch < '0' || ch > '9' {
				return version{}, fmt.Errorf("invalid version %q", text)
			}
			v = v*10 + uint64(ch-'0')
		}
		vals[i] = v
	}
	return version{major: uint8(vals[0]), minor: uint8(vals[1]), patch: uint16(vals[2])}, nil
}

func (v version) text() string {
	return fmt.Sprintf("%d.%d.%d", v.major, v.minor, v.patch)
}

type frameHeader struct {
	version  version
	features []string
	length   uint32
}

func writeFrame(magic []byte, v version, features []string, body []byte) []byte {
	header := make([]byte, 16)
	copy(header, magic)
	header[4] = v.major
	header[5] = v.minor
	binary.BigEndian.PutUint16(header[6:], v.patch)
	binary.BigEndian.PutUint32(header[8:], encodeFeatureBits(features))
	binary.BigEndian.PutUint32(header[12:], uint32(len(body)))
	crc := make([]byte, 4)
	binary.BigEndian.PutUint32(crc, crc32.ChecksumIEEE(body))
	return append(append(header, body...), crc...)
}

func readFrame(data []byte, expectedMagic []byte) (frameHeader, []byte, []byte, error) {
	if len(data) < 20 {
		return frameHeader{}, nil, nil, fmt.Errorf("frame too small")
	}
	if !bytes.Equal(data[:4], expectedMagic) {
		return frameHeader{}, nil, nil, fmt.Errorf("unexpected frame magic")
	}
	v := version{
		major: data[4],
		minor: data[5],
		patch: binary.BigEndian.Uint16(data[6:8]),
	}
	featureBits := binary.BigEndian.Uint32(data[8:12])
	length := binary.BigEndian.Uint32(data[12:16])
	bodyStart := 16
	bodyEnd := int(bodyStart + length)
	crcEnd := bodyEnd + 4
	if crcEnd > len(data) {
		return frameHeader{}, nil, nil, fmt.Errorf("frame truncated")
	}
	body := data[bodyStart:bodyEnd]
	expected := binary.BigEndian.Uint32(data[bodyEnd:crcEnd])
	if crc32.ChecksumIEEE(body) != expected {
		return frameHeader{}, nil, nil, fmt.Errorf("frame CRC mismatch")
	}
	features, err := decodeFeatureBits(featureBits)
	if err != nil {
		return frameHeader{}, nil, nil, err
	}
	header := frameHeader{
		version:  v,
		features: features,
		length:   length,
	}
	return header, body, data[crcEnd:], nil
}

type section struct {
	id      uint16
	flags   uint16
	payload []byte
}

func writeSection(id uint16, flags uint16, payload []byte) []byte {
	buf := make([]byte, 8+len(payload))
	binary.LittleEndian.PutUint16(buf, id)
	binary.LittleEndian.PutUint16(buf[2:], flags)
	binary.LittleEndian.PutUint32(buf[4:], uint32(len(payload)))
	copy(buf[8:], payload)
	return buf
}

func decodeSections(buffer []byte) ([]section, error) {
	var sections []section
	offset := 0
	for offset < len(buffer) {
		if offset+8 > len(buffer) {
			return nil, fmt.Errorf("truncated section header")
		}
		id := binary.LittleEndian.Uint16(buffer[offset : offset+2])
		flags := binary.LittleEndian.Uint16(buffer[offset+2 : offset+4])
		length := binary.LittleEndian.Uint32(buffer[offset+4 : offset+8])
		offset += 8
		end := offset + int(length)
		if end > len(buffer) {
			return nil, fmt.Errorf("truncated section payload")
		}
		sections = append(sections, section{id: id, flags: flags, payload: buffer[offset:end]})
		offset = end
	}
	return sections, nil
}

func writeUTF8(text string) []byte {
	data := []byte(text)
	buf := make([]byte, 2+len(data))
	binary.LittleEndian.PutUint16(buf, uint16(len(data)))
	copy(buf[2:], data)
	return buf
}

func writeLengthPrefixed(data []byte) []byte {
	buf := make([]byte, 4+len(data))
	binary.LittleEndian.PutUint32(buf, uint32(len(data)))
	copy(buf[4:], data)
	return buf
}

func readUTF8(r *bytes.Reader) (string, error) {
	var length uint16
	if err := binary.Read(r, binary.LittleEndian, &length); err != nil {
		return "", err
	}
	data := make([]byte, length)
	if _, err := io.ReadFull(r, data); err != nil {
		return "", err
	}
	return string(data), nil
}

func readLengthPrefixed(r *bytes.Reader) []byte {
	var length uint32
	binary.Read(r, binary.LittleEndian, &length)
	data := make([]byte, length)
	io.ReadFull(r, data)
	return data
}

func canonicalJSON(value interface{}) string {
	switch val := value.(type) {
	case map[string]interface{}:
		keys := make([]string, 0, len(val))
		for k := range val {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		var buf bytes.Buffer
		buf.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				buf.WriteByte(',')
			}
			buf.WriteString(fmt.Sprintf("%q:", k))
			buf.WriteString(canonicalJSON(val[k]))
		}
		buf.WriteByte('}')
		return buf.String()
	case map[string]any:
		tmp := map[string]interface{}{}
		for k, v := range val {
			tmp[k] = v
		}
		return canonicalJSON(tmp)
	case []interface{}:
		var buf bytes.Buffer
		buf.WriteByte('[')
		for i, item := range val {
			if i > 0 {
				buf.WriteByte(',')
			}
			buf.WriteString(canonicalJSON(item))
		}
		buf.WriteByte(']')
		return buf.String()
	case []map[string]interface{}:
		tmp := make([]interface{}, len(val))
		for i := range val {
			tmp[i] = val[i]
		}
		return canonicalJSON(tmp)
	case nil:
		return "null"
	case string:
		encoded, _ := json.Marshal(val)
		return string(encoded)
	case bool:
		if val {
			return "true"
		}
		return "false"
	default:
		encoded, _ := json.Marshal(val)
		return string(encoded)
	}
}

func encodeFeatureBits(features []string) uint32 {
	sort.Strings(features)
	var bits uint32
	for _, feature := range features {
		if idx, ok := featureBits[feature]; ok {
			bits |= 1 << idx
		} else {
			panic(fmt.Sprintf("unknown feature %q", feature))
		}
	}
	return bits
}

func decodeFeatureBits(bits uint32) ([]string, error) {
	var features []string
	for name, idx := range featureBits {
		if bits&(1<<idx) != 0 {
			features = append(features, name)
		}
	}
	sort.Strings(features)
	unknownMask := bits &^ encodeFeatureBits(features)
	if unknownMask != 0 {
		return nil, fmt.Errorf("frame advertises unknown feature bits 0x%x", unknownMask)
	}
	return features, nil
}

func boolToFlag(v bool) uint16 {
	if v {
		return 0x0001
	}
	return 0
}

func decodeOptionalBase64(value string, expected int) ([]byte, error) {
	if value == "" {
		return nil, nil
	}
	data, err := base64.StdEncoding.DecodeString(value)
	if err != nil {
		return nil, err
	}
	if len(data) != expected {
		return nil, fmt.Errorf("expected %d bytes, got %d", expected, len(data))
	}
	return data, nil
}

func randomBytes(n int) []byte {
	buf := make([]byte, n)
	if _, err := rand.Read(buf); err != nil {
		panic(err)
	}
	return buf
}

func hexDecode(text string) ([]byte, error) {
	if len(text)%2 != 0 {
		return nil, fmt.Errorf("odd length hex")
	}
	out := make([]byte, len(text)/2)
	for i := 0; i < len(out); i++ {
		a := fromHex(text[2*i])
		b := fromHex(text[2*i+1])
		if a < 0 || b < 0 {
			return nil, fmt.Errorf("invalid hex digit")
		}
		out[i] = byte(a<<4 | b)
	}
	return out, nil
}

func fromHex(b byte) int {
	switch {
	case '0' <= b && b <= '9':
		return int(b - '0')
	case 'a' <= b && b <= 'f':
		return int(b-'a') + 10
	case 'A' <= b && b <= 'F':
		return int(b-'A') + 10
	default:
		return -1
	}
}

func readInput(path string) ([]byte, error) {
	if path == "" {
		return io.ReadAll(os.Stdin)
	}
	return os.ReadFile(path)
}

func writeOutput(path string, data []byte) {
	if path == "" {
		os.Stdout.Write(data)
		return
	}
	os.WriteFile(path, data, 0o644)
}

func splitAndPad(text string, sep string) []string {
	parts := []string{}
	for _, p := range bytes.Split([]byte(text), []byte(sep)) {
		parts = append(parts, string(p))
	}
	if len(parts) == 2 {
		parts = append(parts, "0")
	}
	return parts
}

func toStringSlice(value interface{}) []string {
	items, ok := value.([]interface{})
	if !ok {
		return nil
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		if s, ok := item.(string); ok {
			out = append(out, s)
		}
	}
	return out
}

func featureSetsMatch(wrapper []string, payload []string) bool {
	if len(wrapper) == 0 {
		return true
	}
	if len(wrapper) != len(payload) {
		return false
	}
	a := append([]string{}, wrapper...)
	b := append([]string{}, payload...)
	sort.Strings(a)
	sort.Strings(b)
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
