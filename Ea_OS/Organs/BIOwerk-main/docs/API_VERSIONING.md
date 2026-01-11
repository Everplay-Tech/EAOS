# API Versioning Guide

## Overview

BIOwerk implements comprehensive URL path-based API versioning to ensure backward compatibility and prevent breaking changes from affecting existing clients.

**Version:** API v1 (current)
**Status:** Stable
**Last Updated:** 2025-11-17

## Key Features

- ✅ **URL path-based versioning** (`/v1/endpoint`)
- ✅ **Backward compatibility** - Legacy unversioned endpoints still work
- ✅ **Deprecation warnings** - Clear migration guidance
- ✅ **Version negotiation** - Automatic version detection
- ✅ **Multiple concurrent versions** - Support for gradual migration
- ✅ **Consistent across all services** - Mesh gateway and all microservices

## Version Format

All versioned endpoints use the format:

```
/{version}/{service}/{endpoint}
```

**Examples:**
```bash
# Mesh Gateway (routes to services)
POST /v1/osteon/draft
POST /v1/nucleus/plan
POST /v1/myocyte/ingest_table

# Direct service endpoints
POST /v1/outline         # osteon service
POST /v1/translate       # larry service
GET  /v1/check-all       # harry service
```

## Migration Guide

### For New Applications

Always use versioned endpoints:

```bash
# ✅ CORRECT - Use versioned endpoint
curl -X POST http://localhost:8080/v1/osteon/draft \
  -H 'Content-Type: application/json' \
  -d @examples/osteon_draft.json

# ❌ AVOID - Unversioned endpoint (deprecated)
curl -X POST http://localhost:8080/osteon/draft \
  -H 'Content-Type: application/json' \
  -d @examples/osteon_draft.json
```

### For Existing Applications

Legacy unversioned endpoints still work but return deprecation warnings:

**Request:**
```bash
POST /osteon/draft
```

**Response:**
```json
{
  "id": "...",
  "ok": true,
  "output": {...},
  "_deprecation_warning": {
    "message": "This unversioned endpoint is deprecated. Please use /v1/osteon/draft",
    "legacy_path": "/osteon/draft",
    "recommended_path": "/v1/osteon/draft",
    "migration_guide": "https://github.com/E-TECH-PLAYTECH/BIOwerk/blob/main/docs/API_VERSIONING.md"
  }
}
```

**Response Headers:**
```
Warning: 199 - "API version not specified, defaulting to v1. Please use /v1/... in your request path for explicit versioning."
X-API-Version: v1
X-API-Latest-Version: v1
```

## Supported Versions

### v1 (Current - Stable)

**Status:** ✅ Stable
**Released:** 2025-11-17
**Support:** Full support

All services support v1:

#### Mesh Gateway Routes
| Service | Endpoint | Description |
|---------|----------|-------------|
| osteon | `/v1/osteon/outline` | Generate document outline |
| osteon | `/v1/osteon/draft` | Generate draft content |
| osteon | `/v1/osteon/edit` | Edit and improve content |
| osteon | `/v1/osteon/summarize` | Summarize content |
| osteon | `/v1/osteon/export` | Export complete artifact |
| myocyte | `/v1/myocyte/ingest_table` | Ingest spreadsheet data |
| myocyte | `/v1/myocyte/formula_eval` | Evaluate formulas |
| myocyte | `/v1/myocyte/model_forecast` | Generate forecasts |
| myocyte | `/v1/myocyte/export` | Export spreadsheet |
| synapse | `/v1/synapse/storyboard` | Create presentation storyboard |
| synapse | `/v1/synapse/slide_make` | Generate slides |
| synapse | `/v1/synapse/visualize` | Create visualizations |
| synapse | `/v1/synapse/export` | Export presentation |
| nucleus | `/v1/nucleus/plan` | Create project plan |
| nucleus | `/v1/nucleus/route` | Route task execution |
| nucleus | `/v1/nucleus/review` | Review execution results |
| nucleus | `/v1/nucleus/finalize` | Finalize project |
| circadian | `/v1/circadian/plan_timeline` | Plan project timeline |
| circadian | `/v1/circadian/assign` | Assign tasks |
| circadian | `/v1/circadian/track` | Track task progress |
| circadian | `/v1/circadian/remind` | Send task reminders |
| chaperone | `/v1/chaperone/import_artifact` | Import external artifacts |
| chaperone | `/v1/chaperone/export_artifact` | Export to external formats |

#### Direct Service Endpoints

**GDPR Service:**
- `/v1/request/access` - Data subject access request
- `/v1/export/generate` - Generate data export
- `/v1/export/data` - Export user data
- `/v1/request/erasure` - Right to be forgotten
- `/v1/anonymize` - Anonymize user data
- `/v1/consent/record` - Record consent
- `/v1/consent/withdraw` - Withdraw consent
- `/v1/consent/check` - Check consent status
- `/v1/privacy/settings/get` - Get privacy settings
- `/v1/privacy/settings/update` - Update privacy settings
- `/v1/retention/enforce` - Enforce retention policies

**Larry Service (Conversational):**
- `/v1/translate` - Translate natural language to service calls
- `/v1/chat` - Conversational interface

**Moe Service (Orchestration):**
- `/v1/plan` - Create workflow plan
- `/v1/execute` - Execute workflow

**Harry Service (Monitoring):**
- `/v1/check/{service}` - Check service health
- `/v1/check-all` - Check all services
- `/v1/analyze` - AI-powered health analysis
- `/v1/history/{service}` - Get health check history

## API Models

### Request Model (Msg)

All mesh gateway requests use the `Msg` model with `api_version` field:

```json
{
  "id": "unique-message-id",
  "ts": 1700000000.0,
  "origin": "client",
  "target": "osteon",
  "intent": "draft",
  "input": {
    "goal": "Write a blog post",
    "audience": "developers"
  },
  "api_version": "v1"
}
```

**Fields:**
- `id` (string): Unique message identifier (auto-generated if not provided)
- `ts` (float): Unix timestamp (auto-generated if not provided)
- `origin` (string): Request origin identifier
- `target` (string): Target service name
- `intent` (string): Action/endpoint name
- `input` (object): Input parameters for the endpoint
- `api_version` (string, optional): API version, defaults to "v1"

### Response Model (Reply)

All responses include the `api_version` field:

```json
{
  "id": "unique-message-id",
  "ts": 1700000000.0,
  "agent": "osteon",
  "ok": true,
  "output": {
    "sections": [...],
    "toc": [...]
  },
  "state_hash": "abc123...",
  "api_version": "v1"
}
```

**Fields:**
- `id` (string): Message ID (matches request)
- `ts` (float): Response timestamp
- `agent` (string): Service that generated the response
- `ok` (boolean): Success status
- `output` (object): Response data
- `state_hash` (string): State hash for caching/validation
- `api_version` (string): API version used

## Version Negotiation

The versioning middleware automatically:

1. **Extracts version from URL path**
   ```
   /v1/osteon/draft → version = "v1"
   /osteon/draft → version = null (defaults to latest)
   ```

2. **Validates version**
   - Returns 400 error for unsupported versions
   - Defaults to latest version if not specified

3. **Adds version headers to response**
   ```
   X-API-Version: v1
   X-API-Latest-Version: v1
   ```

4. **Adds deprecation warnings**
   - For deprecated versions: `Warning: 299 - "Deprecated API Version: ..."`
   - For unversioned requests: `Warning: 199 - "API version not specified..."`

## Best Practices

### 1. Always Specify Version

```bash
# ✅ GOOD - Explicit version
POST /v1/osteon/draft

# ❌ BAD - No version (works but deprecated)
POST /osteon/draft
```

### 2. Include api_version in Request Body

```json
{
  "origin": "my-app",
  "target": "osteon",
  "intent": "draft",
  "input": {...},
  "api_version": "v1"  ← Include this
}
```

### 3. Check Response Headers

Monitor deprecation warnings:

```python
response = requests.post("/v1/osteon/draft", ...)
if "Warning" in response.headers:
    logger.warning(f"API Warning: {response.headers['Warning']}")
```

### 4. Update URLs in Stages

When migrating:

1. Test with new versioned endpoint
2. Update development environment
3. Update staging environment
4. Update production environment
5. Monitor for any legacy endpoint usage

## Error Handling

### Unsupported Version

**Request:**
```bash
POST /v99/osteon/draft
```

**Response:** `400 Bad Request`
```json
{
  "error": "Unsupported API Version",
  "message": "API version 'v99' is not supported",
  "requested_version": "v99",
  "supported_versions": ["v1"],
  "latest_version": "v1"
}
```

### Missing Version (Auto-Default)

**Request:**
```bash
POST /osteon/draft
```

**Response:** `200 OK` (with warning)
```json
{
  "id": "...",
  "ok": true,
  "output": {...},
  "_deprecation_warning": {
    "message": "This unversioned endpoint is deprecated. Please use /v1/osteon/draft",
    "legacy_path": "/osteon/draft",
    "recommended_path": "/v1/osteon/draft"
  }
}
```

**Headers:**
```
Warning: 199 - "API version not specified, defaulting to v1. Please use /v1/... in your request path for explicit versioning."
X-API-Version: v1
X-API-Latest-Version: v1
```

## Testing

### Version Negotiation Tests

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_versioned_endpoint(client: AsyncClient):
    """Test that v1 endpoint works correctly."""
    response = await client.post(
        "/v1/osteon/draft",
        json={
            "origin": "test",
            "target": "osteon",
            "intent": "draft",
            "input": {"goal": "Test"},
            "api_version": "v1"
        }
    )
    assert response.status_code == 200
    assert response.headers["X-API-Version"] == "v1"

@pytest.mark.asyncio
async def test_legacy_endpoint_deprecated(client: AsyncClient):
    """Test that legacy endpoint shows deprecation warning."""
    response = await client.post(
        "/osteon/draft",
        json={
            "origin": "test",
            "target": "osteon",
            "intent": "draft",
            "input": {"goal": "Test"}
        }
    )
    assert response.status_code == 200
    assert "_deprecation_warning" in response.json()
    assert "Warning" in response.headers

@pytest.mark.asyncio
async def test_unsupported_version(client: AsyncClient):
    """Test that unsupported version returns 400."""
    response = await client.post(
        "/v99/osteon/draft",
        json={
            "origin": "test",
            "target": "osteon",
            "intent": "draft",
            "input": {"goal": "Test"}
        }
    )
    assert response.status_code == 400
    assert "Unsupported API Version" in response.json()["error"]
```

## Future Versions

### Planned: v2 (Future)

When v2 is released:

1. v1 will be marked as deprecated
2. v1 will continue to work with deprecation warnings
3. v2 will become the default for unversioned requests
4. Migration guide will be provided

**Example v2 deprecation:**
```json
{
  "warning": {
    "code": "deprecated_version",
    "message": "API v1 is deprecated and will be removed in 2026-Q2. Please migrate to v2.",
    "deprecated_version": "v1",
    "current_version": "v2"
  }
}
```

## FAQ

### Q: Do I need to update my existing code immediately?

**A:** No. Legacy unversioned endpoints still work. However, you should plan migration to avoid issues when older versions are eventually sunset.

### Q: What happens if I don't specify a version?

**A:** The API defaults to the latest version (currently v1) and returns a warning header.

### Q: How long will v1 be supported?

**A:** v1 has full support indefinitely until v2 is released. Even then, v1 will be supported for at least 12 months with deprecation warnings.

### Q: Can I use different versions for different services?

**A:** No. The version applies to the entire request. All services must use the same API version.

### Q: How do I know which version I'm using?

**A:** Check the `X-API-Version` response header or the `api_version` field in the response body.

## Support

For questions or issues:
- **Documentation:** [BIOwerk Docs](https://github.com/E-TECH-PLAYTECH/BIOwerk/tree/main/docs)
- **Issues:** [GitHub Issues](https://github.com/E-TECH-PLAYTECH/BIOwerk/issues)
- **Migration Help:** See [Migration Guide](#migration-guide)

## Changelog

### 2025-11-17 - v1 Released
- ✅ Initial API versioning implementation
- ✅ All endpoints support /v1/ prefix
- ✅ Backward compatibility for legacy endpoints
- ✅ Deprecation warnings for unversioned requests
- ✅ Version negotiation middleware
- ✅ Comprehensive documentation
