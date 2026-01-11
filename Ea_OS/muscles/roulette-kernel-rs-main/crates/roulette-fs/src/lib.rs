// Copyright © 2025 [Mitchell_Burns/ Everplay-Tech]. All rights reserved.
// Proprietary and confidential. Not open source.
// Unauthorized copying, distribution, or modification prohibited.

#![no_std]
#![cfg_attr(not(test), no_main)]
#![deny(unsafe_code)]
#![deny(clippy::all)]

/// Filesystem core functionality for the Roulette Kernel
/// Provides file operations, directory management, and basic I/O
///
/// File descriptor type
pub type FileDescriptor = u32;

/// Inode number type
pub type Inode = u32;

/// File permissions
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FilePermissions {
    ReadOnly,
    WriteOnly,
    ReadWrite,
}

/// File type
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FileType {
    Regular,
    Directory,
    Symlink,
}

/// File metadata
#[derive(Debug, Clone, Copy)]
pub struct FileMetadata {
    pub inode: Inode,
    pub file_type: FileType,
    pub size: usize,
    pub permissions: FilePermissions,
    pub created_time: u64,
    pub modified_time: u64,
}

/// Directory entry
#[derive(Debug, Clone, Copy)]
pub struct DirEntry {
    pub name: [u8; 256], // Fixed size for no_std
    pub name_len: usize,
    pub inode: Inode,
    pub file_type: FileType,
}

/// Open file handle
#[derive(Debug, Clone, Copy)]
pub struct FileHandle {
    pub fd: FileDescriptor,
    pub inode: Inode,
    pub position: usize,
    pub permissions: FilePermissions,
}

/// Simple in-memory filesystem
/// In a real kernel, this would interface with disk drivers
pub struct FileSystem {
    #[cfg(not(test))]
    inodes: [Option<FileMetadata>; 1024], // Fixed size inode table
    #[cfg(test)]
    inodes: [Option<FileMetadata>; 32], // Smaller for tests

    #[cfg(not(test))]
    data_blocks: [[u8; 4096]; 1024], // Fixed size data blocks (4KB each)
    #[cfg(test)]
    data_blocks: [[u8; 256]; 32], // Smaller for tests

    #[cfg(not(test))]
    directory_entries: [[Option<DirEntry>; 16]; 128], // Fixed size directories
    #[cfg(test)]
    directory_entries: [[Option<DirEntry>; 4]; 8], // Smaller for tests

    #[cfg(not(test))]
    open_files: [Option<FileHandle>; 256], // Fixed size open file table
    #[cfg(test)]
    open_files: [Option<FileHandle>; 16], // Smaller for tests
    next_inode: Inode,
    next_fd: FileDescriptor,
}

#[allow(dead_code)]
impl FileSystem {
    /// Create a new filesystem instance
    #[must_use] 
    pub fn new() -> Self {
        #[cfg(not(test))]
        let mut fs = Self {
            #[allow(clippy::large_stack_arrays)]
            inodes: [None; 1024],
            #[allow(clippy::large_stack_arrays)]
            data_blocks: [[0; 4096]; 1024],
            #[allow(clippy::large_stack_arrays)]
            directory_entries: [[None; 16]; 128],
            open_files: [None; 256],
            next_inode: 1, // Root inode is 1
            next_fd: 0,
        };
        #[cfg(test)]
        let mut fs = Self {
            inodes: [None; 32],
            data_blocks: [[0; 256]; 32],
            directory_entries: [[None; 4]; 8],
            open_files: [None; 16],
            next_inode: 1,
            next_fd: 0,
        };
        // Create root directory
        fs.create_root_directory();
        fs
    }

    fn create_root_directory(&mut self) {
        let root_inode = 1;
        let root_metadata = FileMetadata {
            inode: root_inode,
            file_type: FileType::Directory,
            size: 0,
            permissions: FilePermissions::ReadWrite,
            created_time: 0, // Would be current time in real system
            modified_time: 0,
        };

        self.inodes[0] = Some(root_metadata);
        self.next_inode = 2;
    }

    /// Create a new file
    pub fn create_file(&mut self, parent_dir: Inode, name: &str, permissions: FilePermissions) -> Option<Inode> {
        if !self.is_directory(parent_dir) {
            return None;
        }

        // Check if file already exists
        if self.find_dir_entry(parent_dir, name).is_some() {
            return None;
        }

        let inode = self.next_inode;
        self.next_inode += 1;

        let metadata = FileMetadata {
            inode,
            file_type: FileType::Regular,
            size: 0,
            permissions,
            created_time: 0,
            modified_time: 0,
        };

        // Find free inode slot
        for slot in 0..self.inodes.len() {
            if self.inodes[slot].is_none() {
                self.inodes[slot] = Some(metadata);
                break;
            }
        }

        // Add directory entry
        self.add_dir_entry(parent_dir, name, inode, FileType::Regular)?;

        Some(inode)
    }

    /// Create a new directory
    pub fn create_directory(&mut self, parent_dir: Inode, name: &str) -> Option<Inode> {
        if !self.is_directory(parent_dir) {
            return None;
        }

        // Check if directory already exists
        if self.find_dir_entry(parent_dir, name).is_some() {
            return None;
        }

        let inode = self.next_inode;
        self.next_inode += 1;

        let metadata = FileMetadata {
            inode,
            file_type: FileType::Directory,
            size: 0,
            permissions: FilePermissions::ReadWrite,
            created_time: 0,
            modified_time: 0,
        };

        // Find free inode slot
        for slot in 0..self.inodes.len() {
            if self.inodes[slot].is_none() {
                self.inodes[slot] = Some(metadata);
                break;
            }
        }

        // Add directory entry
        self.add_dir_entry(parent_dir, name, inode, FileType::Directory)?;

        Some(inode)
    }

    /// Open a file
    pub fn open_file(&mut self, inode: Inode, permissions: FilePermissions) -> Option<FileDescriptor> {
        let metadata = self.get_metadata(inode)?;

        // Check permissions
        if !Self::check_permissions(metadata.permissions, permissions) {
            return None;
        }

        let fd = self.next_fd;
        self.next_fd += 1;

        let handle = FileHandle {
            fd,
            inode,
            position: 0,
            permissions,
        };

        // Find free file handle slot
        for slot in 0..self.open_files.len() {
            if self.open_files[slot].is_none() {
                self.open_files[slot] = Some(handle);
                return Some(fd);
            }
        }

        None
    }

    /// Close a file
    pub fn close_file(&mut self, fd: FileDescriptor) -> bool {
        for slot in 0..self.open_files.len() {
            if let Some(handle) = &self.open_files[slot] {
                if handle.fd == fd {
                    self.open_files[slot] = None;
                    return true;
                }
            }
        }
        false
    }

    /// Read from a file
    pub fn read_file(&self, fd: FileDescriptor, buffer: &mut [u8]) -> Option<usize> {
        let handle = self.get_file_handle(fd)?;
        let metadata = self.get_metadata(handle.inode)?;

        if !Self::check_permissions(metadata.permissions, FilePermissions::ReadOnly) &&
           !Self::check_permissions(metadata.permissions, FilePermissions::ReadWrite) {
            return None;
        }

        let remaining = metadata.size.saturating_sub(handle.position);
        let to_read = core::cmp::min(buffer.len(), remaining);

        if to_read == 0 {
            return Some(0);
        }

        // Simple block-based read (would be more complex in real FS)
        let start_block = handle.position / 4096;
        let end_block = (handle.position + to_read) / 4096;
        let mut bytes_read = 0;

        for block_idx in start_block..=end_block {
            if block_idx >= self.data_blocks.len() {
                break;
            }

            let block_start = block_idx * 4096;
            let block_offset = handle.position.saturating_sub(block_start);
            let block_remaining = 4096 - block_offset;
            let copy_len = core::cmp::min(block_remaining, to_read - bytes_read);

            buffer[bytes_read..bytes_read + copy_len]
                .copy_from_slice(&self.data_blocks[block_idx][block_offset..block_offset + copy_len]);

            bytes_read += copy_len;
        }

        Some(bytes_read)
    }

    /// Write to a file
    pub fn write_file(&mut self, fd: FileDescriptor, data: &[u8]) -> Option<usize> {
        // Get handle index first to avoid borrowing conflicts
        let handle_idx = self.open_files.iter().position(|h| h.as_ref().is_some_and(|handle| handle.fd == fd))?;
        let inode = self.open_files[handle_idx].as_ref()?.inode;

        // Check permissions first
        let metadata = self.get_metadata(inode)?;
        let has_write_permission = Self::check_permissions(metadata.permissions, FilePermissions::WriteOnly) ||
                                   Self::check_permissions(metadata.permissions, FilePermissions::ReadWrite);
        if !has_write_permission {
            return None;
        }

        // Get metadata index
        let metadata_idx = self.inodes.iter().position(|m| m.as_ref().is_some_and(|meta| meta.inode == inode))?;

        // Now get mutable references
        let handle = self.open_files[handle_idx].as_mut()?;
        let metadata = self.inodes[metadata_idx].as_mut()?;

        let new_size = core::cmp::max(metadata.size, handle.position + data.len());
        metadata.size = new_size;
        metadata.modified_time = 0; // Would be current time

        // Simple block-based write
        let start_block = handle.position / 4096;
        let end_block = (handle.position + data.len()) / 4096;
        let mut bytes_written = 0;

        for block_idx in start_block..=end_block {
            if block_idx >= self.data_blocks.len() {
                break;
            }

            let block_start = block_idx * 4096;
            let block_offset = handle.position.saturating_sub(block_start);
            let block_remaining = 4096 - block_offset;
            let copy_len = core::cmp::min(block_remaining, data.len() - bytes_written);

            self.data_blocks[block_idx][block_offset..block_offset + copy_len]
                .copy_from_slice(&data[bytes_written..bytes_written + copy_len]);

            bytes_written += copy_len;
        }

        handle.position += bytes_written;
        Some(bytes_written)
    }

    /// List directory contents
    #[must_use] 
    pub fn list_directory(&self, dir_inode: Inode) -> Option<&[Option<DirEntry>]> {
        if !self.is_directory(dir_inode) {
            return None;
        }

        let dir_idx = (dir_inode - 1) as usize;
        if dir_idx >= self.directory_entries.len() {
            return None;
        }

        Some(&self.directory_entries[dir_idx])
    }

    // Helper methods

    fn is_directory(&self, inode: Inode) -> bool {
        self.get_metadata(inode)
            .is_some_and(|m| m.file_type == FileType::Directory)
    }

    fn get_metadata(&self, inode: Inode) -> Option<&FileMetadata> {
        self.inodes.iter().find_map(|m| m.as_ref().filter(|meta| meta.inode == inode))
    }

    fn get_metadata_mut(&mut self, inode: Inode) -> Option<&mut FileMetadata> {
        self.inodes.iter_mut().find_map(|m| m.as_mut().filter(|meta| meta.inode == inode))
    }

    fn get_file_handle(&self, fd: FileDescriptor) -> Option<&FileHandle> {
        self.open_files.iter().find_map(|h| h.as_ref().filter(|handle| handle.fd == fd))
    }

    fn get_file_handle_mut(&mut self, fd: FileDescriptor) -> Option<&mut FileHandle> {
        self.open_files.iter_mut().find_map(|h| h.as_mut().filter(|handle| handle.fd == fd))
    }

    fn check_permissions(file_perms: FilePermissions, requested: FilePermissions) -> bool {
        matches!((file_perms, requested), (FilePermissions::ReadOnly, FilePermissions::ReadOnly) | (FilePermissions::WriteOnly, FilePermissions::WriteOnly) | (FilePermissions::ReadWrite, _))
    }

    fn find_dir_entry(&self, dir_inode: Inode, name: &str) -> Option<&DirEntry> {
        let dir_idx = (dir_inode - 1) as usize;
        if dir_idx >= self.directory_entries.len() {
            return None;
        }

        self.directory_entries[dir_idx].iter().find_map(|entry| {
            entry.as_ref().filter(|e| {
                e.name_len == name.len() &&
                &e.name[..name.len()] == name.as_bytes()
            })
        })
    }

    fn add_dir_entry(&mut self, dir_inode: Inode, name: &str, inode: Inode, file_type: FileType) -> Option<()> {
        let dir_idx = (dir_inode - 1) as usize;
        if dir_idx >= self.directory_entries.len() {
            return None;
        }

        let name_bytes = name.as_bytes();
        if name_bytes.len() > 256 {
            return None;
        }

        for entry in &mut self.directory_entries[dir_idx] {
            if entry.is_none() {
                let mut name_array = [0u8; 256];
                name_array[..name_bytes.len()].copy_from_slice(name_bytes);

                *entry = Some(DirEntry {
                    name: name_array,
                    name_len: name_bytes.len(),
                    inode,
                    file_type,
                });
                return Some(());
            }
        }

        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fs_creation() {
        let fs = FileSystem::new();
        assert!(fs.get_metadata(1).is_some()); // Root directory exists
    }

    #[test]
    fn test_file_creation() {
        let mut fs = FileSystem::new();
        let file_inode = fs.create_file(1, "test.txt", FilePermissions::ReadWrite).unwrap();
        assert!(fs.get_metadata(file_inode).is_some());
    }

    #[test]
    fn test_file_operations() {
        let mut fs = FileSystem::new();
        let file_inode = fs.create_file(1, "test.txt", FilePermissions::ReadWrite).unwrap();
        let fd = fs.open_file(file_inode, FilePermissions::ReadWrite).unwrap();

        let data = b"Hello, World!";
        assert_eq!(fs.write_file(fd, data), Some(data.len()));

        // Reset file position to 0 before reading
        if let Some(handle) = fs.open_files.iter_mut().find(|h| h.as_ref().map(|f| f.fd == fd).unwrap_or(false)) {
            if let Some(h) = handle.as_mut() {
                h.position = 0;
            }
        }
        let mut buffer = [0u8; 13];
        assert_eq!(fs.read_file(fd, &mut buffer), Some(data.len()));
        assert_eq!(&buffer, data);

        assert!(fs.close_file(fd));
    }
}

impl Default for FileSystem {
    fn default() -> Self {
        Self::new()
    }
}
