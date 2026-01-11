//! TLS exporter key extraction for IHP.
//!
//! Provides types and utilities for handling TLS exporter keys in Axum request extensions.
//! The TLS exporter key should be extracted from the TLS connection by TLS-aware middleware
//! and stored in request extensions for use by handlers.

use crate::KEY_BYTES;

/// TLS exporter key stored in Axum request extensions.
///
/// This type wraps the TLS exporter key bytes and is stored in Axum request extensions
/// by TLS middleware. Handlers extract this to derive session keys.
///
/// In production, the TLS exporter key should be extracted from the actual TLS connection
/// using RFC 5705 keying material export. For development/testing without TLS, a fallback
/// middleware can generate random keys.
#[derive(Clone, Copy, Debug)]
pub struct TlsExporterKey(pub [u8; KEY_BYTES]);
