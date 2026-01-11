# Planning Guide

A web-based file reader that allows users to upload files and view their contents as byte arrays, demonstrating file reading concepts in a browser environment.

**Experience Qualities**:
1. **Educational** - Clear visualization of file data transformation from upload to bytes
2. **Interactive** - Immediate feedback when files are selected and processed
3. **Informative** - Detailed breakdown of file metadata and byte representation

**Complexity Level**: Micro Tool (single-purpose)
  - Focused on a single task: reading files and displaying byte contents with metadata

## Essential Features

### File Upload & Reading
- **Functionality**: Accept file uploads via drag-drop or file picker, read file contents into byte array
- **Purpose**: Demonstrate how file reading works in web applications
- **Trigger**: User selects or drops a file
- **Progression**: File selection → Read file contents → Convert to byte array → Display bytes and metadata
- **Success criteria**: File successfully read, bytes displayed in hex and decimal format, file metadata shown

### Byte Array Display
- **Functionality**: Show byte contents in multiple formats (hex, decimal) with offset information
- **Purpose**: Provide clear visualization of file byte structure
- **Trigger**: File successfully read
- **Progression**: Bytes extracted → Format as hex/decimal → Display in structured grid
- **Success criteria**: Bytes displayed clearly with offsets, multiple format options available

### File Metadata
- **Functionality**: Display file name, size, type, and last modified date
- **Purpose**: Provide context about the uploaded file
- **Trigger**: File selected
- **Progression**: File metadata extracted → Display in info panel
- **Success criteria**: All relevant metadata displayed accurately

## Edge Case Handling
- **Large Files**: Limit display to first N bytes with indication of truncation
- **Empty Files**: Show clear message when file has zero bytes
- **Binary vs Text**: Handle all file types gracefully regardless of content
- **No File Selected**: Show helpful empty state with instructions

## Design Direction
The design should feel educational and technical yet approachable - like a developer tool that teaches rather than intimidates, with a clean interface that emphasizes the data visualization.

## Color Selection
Custom palette with a technical, code-editor aesthetic using cool tones

- **Primary Color**: Deep blue-gray (oklch(0.35 0.05 250)) - Represents technical precision and trust
- **Secondary Colors**: Light gray backgrounds for data display areas
- **Accent Color**: Bright cyan (oklch(0.75 0.15 200)) - Highlights interactive elements and important data
- **Foreground/Background Pairings**:
  - Background (White oklch(0.98 0 0)): Dark gray text (oklch(0.25 0 0)) - Ratio 12.6:1 ✓
  - Card (Light gray oklch(0.96 0 0)): Dark text (oklch(0.25 0 0)) - Ratio 11.8:1 ✓
  - Primary (Deep blue-gray oklch(0.35 0.05 250)): White text (oklch(0.98 0 0)) - Ratio 8.2:1 ✓
  - Accent (Cyan oklch(0.75 0.15 200)): Dark text (oklch(0.25 0 0)) - Ratio 5.1:1 ✓

## Font Selection
Use JetBrains Mono for byte display to ensure monospace alignment, and Inter for UI elements to maintain modern clarity.

- **Typographic Hierarchy**:
  - H1 (Page Title): Inter Bold/32px/tight tracking
  - H2 (Section Headers): Inter Semibold/20px/normal tracking
  - Body (Instructions): Inter Regular/16px/relaxed line height
  - Byte Data: JetBrains Mono Regular/14px/fixed width for alignment
  - Metadata Labels: Inter Medium/14px/normal tracking

## Animations
Minimal and purposeful - smooth transitions when file is loaded, subtle hover states on interactive elements to confirm responsiveness.

- **Purposeful Meaning**: Animations guide attention to newly loaded data and confirm interactions
- **Hierarchy of Movement**: File upload area responds to drag events, byte display fades in when ready

## Component Selection
- **Components**: 
  - Card for file info and byte display containers
  - Tabs for switching between hex/decimal/text views
  - Badge for file type indicators
  - ScrollArea for byte content display
  - Button for file picker trigger
  - Alert for instructions and error states
- **Customizations**: Custom byte grid layout component for displaying bytes in rows with offsets
- **States**: Upload area has distinct states for default, drag-over, and file-loaded
- **Icon Selection**: FileArrowUp for upload, FileCode for byte view, Info for metadata
- **Spacing**: Consistent 4-unit (1rem) spacing between major sections, 2-unit within cards
- **Mobile**: Single column layout with full-width cards, collapsible sections for metadata
