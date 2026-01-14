use std::path::Path;

use anyhow::Result;

use super::{resolve_store_path, FileBackedVault, KeyManagement, KeyMetadata, Provider};

pub fn connect(metadata_path: Option<&Path>) -> Result<Box<dyn KeyManagement>> {
    let path = resolve_store_path(Provider::Aws, metadata_path)?;
    Ok(Box::new(AwsVault(FileBackedVault::new("aws", path))))
}

struct AwsVault(FileBackedVault);

impl KeyManagement for AwsVault {
    fn describe_key(&self, key_id: &str) -> Result<KeyMetadata> {
        self.0.describe_key(key_id)
    }

    fn rotate_key(&self, key_id: &str) -> Result<KeyMetadata> {
        self.0.rotate_key(key_id)
    }
}
