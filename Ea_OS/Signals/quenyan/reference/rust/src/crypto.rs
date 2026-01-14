use std::collections::BTreeMap;
use std::fmt;
use std::path::Path;

use anyhow::{anyhow, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use chacha20poly1305::aead::{AeadInPlace, KeyInit};
use chacha20poly1305::ChaCha20Poly1305;
use hkdf::Hkdf;
use pbkdf2::pbkdf2_hmac;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::Sha256;

use crate::encoder::EntropyMaterial;

const MASTER_PBKDF2_ROUNDS: u32 = 200_000;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RotationMetadata {
    pub project_id: String,
    pub generation: u32,
    pub project_salt: String,
    pub previous_generation: Option<u32>,
    pub rotated_at: String,
}

impl RotationMetadata {
    pub fn new(
        project_id: impl Into<String>,
        generation: u32,
        project_salt: Vec<u8>,
        rotated_at: impl Into<String>,
        previous_generation: Option<u32>,
    ) -> Self {
        Self {
            project_id: project_id.into(),
            generation,
            project_salt: STANDARD.encode(project_salt),
            previous_generation,
            rotated_at: rotated_at.into(),
        }
    }

    pub fn project_salt_bytes(&self) -> Result<Vec<u8>> {
        Ok(STANDARD.decode(&self.project_salt)?)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Provenance {
    pub created: String,
    #[serde(default)]
    pub commit: Option<String>,
    #[serde(default)]
    pub inputs: BTreeMap<String, String>,
    #[serde(default)]
    pub manifest: Option<Value>,
}

impl Provenance {
    pub fn canonical_json(&self) -> Result<Vec<u8>> {
        let mut map = BTreeMap::new();
        map.insert("created", Value::String(self.created.clone()));
        if let Some(commit) = &self.commit {
            map.insert("commit", Value::String(commit.clone()));
        }
        if !self.inputs.is_empty() {
            let mut inputs = Map::new();
            for (k, v) in &self.inputs {
                inputs.insert(k.clone(), Value::String(v.clone()));
            }
            map.insert("inputs", Value::Object(inputs));
        }
        if let Some(manifest) = &self.manifest {
            map.insert("manifest", manifest.clone());
        }
        let mut ordered = Map::new();
        for (k, v) in map {
            ordered.insert(k.to_string(), v);
        }
        Ok(serde_json::to_vec(&Value::Object(ordered))?)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Metadata {
    pub project_id: String,
    pub file_path: String,
    pub rotation: RotationMetadata,
    pub provenance: Provenance,
}

impl Metadata {
    pub fn key_id(&self) -> String {
        format!(
            "{}/{}/gen{}",
            self.project_id, self.file_path, self.rotation.generation
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Archive {
    pub metadata: Metadata,
    pub file_salt: String,
    pub nonce: String,
    pub ciphertext: String,
    pub tag: String,
}

impl Archive {
    pub fn to_writer<W: std::io::Write>(&self, mut w: W) -> Result<()> {
        let data = serde_json::to_vec(self)?;
        w.write_all(&data)?;
        Ok(())
    }

    pub fn from_reader<R: std::io::Read>(mut r: R) -> Result<Self> {
        let mut buf = Vec::new();
        r.read_to_end(&mut buf)?;
        Ok(serde_json::from_slice(&buf)?)
    }
}

pub struct KeyHierarchy {
    master_key: [u8; 32],
    rotation: RotationMetadata,
}

impl fmt::Debug for KeyHierarchy {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("KeyHierarchy")
            .field("project_id", &self.rotation.project_id)
            .field("generation", &self.rotation.generation)
            .finish()
    }
}

impl KeyHierarchy {
    pub fn from_passphrase(passphrase: &str, rotation: RotationMetadata) -> Result<Self> {
        let salt = rotation.project_salt_bytes()?;
        let mut master_key = [0u8; 32];
        pbkdf2_hmac::<Sha256>(
            passphrase.as_bytes(),
            &salt,
            MASTER_PBKDF2_ROUNDS,
            &mut master_key,
        );
        Ok(Self {
            master_key,
            rotation,
        })
    }

    pub fn rotation(&self) -> &RotationMetadata {
        &self.rotation
    }

    pub fn derive_file_key(&self, file_path: &str, entropy: &EntropyMaterial) -> Result<[u8; 32]> {
        let project_key = {
            let hk =
                Hkdf::<Sha256>::new(Some(&self.rotation.project_salt_bytes()?), &self.master_key);
            let mut okm = [0u8; 32];
            hk.expand(self.rotation.project_id.as_bytes(), &mut okm)
                .map_err(|_| anyhow!("hkdf expand failed"))?;
            okm
        };

        let hk = Hkdf::<Sha256>::new(Some(&entropy.salt), &project_key);
        let mut okm = [0u8; 32];
        hk.expand(file_path.as_bytes(), &mut okm)
            .map_err(|_| anyhow!("hkdf expand failed"))?;
        Ok(okm)
    }

    pub fn encrypt(
        &self,
        plaintext: &[u8],
        metadata: Metadata,
        entropy: EntropyMaterial,
    ) -> Result<Archive> {
        let file_key = self.derive_file_key(&metadata.file_path, &entropy)?;
        let cipher = ChaCha20Poly1305::new((&file_key).into());

        let aad = metadata.provenance.canonical_json()?;
        let mut buffer = plaintext.to_vec();
        let tag = cipher
            .encrypt_in_place_detached(
                (&entropy.nonce as &[u8]).into(),
                &aad,
                &mut buffer,
            )
            .map_err(|_| anyhow!("encryption failed"))?;

        Ok(Archive {
            metadata,
            file_salt: STANDARD.encode(entropy.salt),
            nonce: STANDARD.encode(entropy.nonce),
            ciphertext: STANDARD.encode(&buffer),
            tag: STANDARD.encode(tag.as_slice()),
        })
    }
}

pub fn decrypt_archive(passphrase: &str, archive: &Archive) -> Result<Vec<u8>> {
    let hierarchy = KeyHierarchy::from_passphrase(passphrase, archive.metadata.rotation.clone())?;
    let entropy = EntropyMaterial {
        salt: STANDARD.decode(&archive.file_salt)?,
        nonce: STANDARD.decode(&archive.nonce)?,
        deterministic: false,
    };
    let file_key = hierarchy.derive_file_key(&archive.metadata.file_path, &entropy)?;
    let cipher = ChaCha20Poly1305::new((&file_key).into());
    let mut buffer = STANDARD.decode(&archive.ciphertext)?;
    let aad = archive.metadata.provenance.canonical_json()?;
    let tag = STANDARD.decode(&archive.tag)?;
    cipher
        .decrypt_in_place_detached(
            (&entropy.nonce as &[u8]).into(),
            &aad,
            &mut buffer,
            (&tag as &[u8]).into(),
        )
        .map_err(|_| anyhow!("decryption failed"))?;
    Ok(buffer)
}

pub fn load_rotation_state(path: &Path) -> Result<RotationMetadata> {
    if path.exists() {
        let file = std::fs::File::open(path)?;
        Ok(serde_json::from_reader(file)?)
    } else {
        Err(anyhow!("rotation state not found"))
    }
}

pub fn store_rotation_state(path: &Path, state: &RotationMetadata) -> Result<()> {
    let file = std::fs::File::create(path)?;
    serde_json::to_writer_pretty(file, state)?;
    Ok(())
}

pub fn roll_rotation_state(
    path: &Path,
    project_id: &str,
    created: &str,
) -> Result<RotationMetadata> {
    let previous = if path.exists() {
        Some(serde_json::from_reader::<_, RotationMetadata>(
            std::fs::File::open(path)?,
        )?)
    } else {
        None
    };

    let generation = previous.as_ref().map(|p| p.generation + 1).unwrap_or(1);
    if let Some(prev) = &previous {
        if prev.project_id != project_id {
            return Err(anyhow!("project mismatch"));
        }
    }

    let project_salt = random_bytes(32)?;
    let state = RotationMetadata::new(
        project_id.to_string(),
        generation,
        project_salt,
        created.to_string(),
        previous.map(|p| p.generation),
    );
    store_rotation_state(path, &state)?;
    Ok(state)
}

fn random_bytes(len: usize) -> Result<Vec<u8>> {
    let mut buf = vec![0u8; len];
    getrandom::getrandom(&mut buf)?;
    Ok(buf)
}
