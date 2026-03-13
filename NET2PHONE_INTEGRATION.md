# net2phone Integration for AuditorIA

This module enables AuditorIA to receive webhooks from net2phone cloud PBX and automatically transcribe call recordings.

## Features

- **Call event processing**: Receives call_completed, call_answered, call_ringing, call_missed, call_recorded events
- **Automatic recording download**: Downloads MP3 recordings when calls complete
- **Transcription tasks**: Automatically creates transcription tasks in AuditorIA
- **Agent mapping**: Maps net2phone users to AuditorIA operators
- **HMAC-SHA256 signature verification**: Verifies webhook authenticity

## Setup

### 1. net2phone Configuration

#### Create Webhook in net2phone

1. Go to **https://app.net2phone.com**
2. Navigate to **Settings → API**
3. Click on **Webhook** tab
4. Click **Add Webhook**
5. Configure:

**Webhook Settings:**
- URL: `https://your-domain.com/webhook/net2phone/`
- Events to subscribe:
  - ✅ **call_completed** (required)
  - ✅ **call_answered** (recommended)
  - ⚪ **call_ringing** (optional)
  - ✅ **call_missed** (recommended)
  - ⚪ **call_recorded** (if available)

**Authentication:**
- Add header: `X-API-Key: {YOUR_AUDITORIA_API_KEY}`
- Headers for signature verification:
  - `x-net2phone-signature`: HMAC-SHA256 signature
  - `x-net2phone-timestamp`: Timestamp of the request (ISO 8601 format)

### 2. AuditorIA Configuration

#### Environment Variables

Add to your `.env` file:

```bash
# Existing S3/MinIO configuration (required)
S3_ENDPOINT=your-minio-endpoint
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_BUCKET=audios

# Optional: Default values for webhooks
NET2PHONE_DEFAULT_CAMPAIGN_ID=1  # Default campaign if user.account_id not found
NET2PHONE_DEFAULT_OPERATOR_ID=1  # Default operator if user.id not detected
NET2PHONE_SECRET=your-secret-key  # For HMAC signature verification
```

#### Create API Key

1. Access AuditorIA main application
2. Go to **Settings → API Keys**
3. Create a new Global API Key
4. Copy the key - you'll use it in net2phone webhook configuration

## Webhook Payload

### call_completed Event

```json
{
  "timestamp": "2021-10-27T08:58:21.66Z",
  "event": "call_completed",
  "user": {
    "id": 1,
    "name": "Jane Doe",
    "account_id": 42
  },
  "duration": 120,
  "direction": "inbound",
  "originating_number": "+5491167950079",
  "user_name": "Jane Doe",
  "id": "2836c843-96e6-4f3a-9c04-69bb0b10febf",
  "dialed_number": "+5491126888209",
  "call_source": "normal",
  "call_id": "a471d33e562b535b9ec530e1c0c3a5b2",
  "recording_url": "https://net2phone.com/recordings/call_12345.mp3"
}
```

### call_recorded Event

```json
{
  "timestamp": "2021-11-10T11:34:04.29Z",
  "event": "call_recorded",
  "user": {
    "id": 1,
    "name": "Jane Doe",
    "account_id": 42
  },
  "id": "e36573e7-5065-4c64-b8bd-31a0ee37db43",
  "audio_message_id": 89007,
  "user_name": "Jane Doe",
  "audio_message_url": "https://app.net2phone.com/api/call-record/89007",
  "direction": "inbound",
  "dialed_number": "201",
  "originating_number": "202",
  "call_source": "normal",
  "call_id": "203a4f1e0a59e36b68cd85c508573893"
}
```

**Important**: 
- **call_completed** event includes `recording_url` field
- **call_recorded** event includes `audio_message_url` and `audio_message_id` fields
- Both events are supported for recording download

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | Event timestamp (ISO 8601 format) |
| `event` | string | Event type: call_completed, call_answered, call_recorded, etc |
| `call_id` | string | Unique call ID |
| `duration` | integer | Call duration in seconds (call_completed only) |
| `direction` | string | Call direction: inbound or outbound |
| `originating_number` | string | Originating phone number |
| `dialed_number` | string | Dialed phone number |
| `user.id` | integer | User ID (not used in mapping) |
| `user.name` | string | User/Agent name |
| `user.account_id` | integer | Account ID (maps to operator_id) |
| `recording_url` | string | URL to download recording (call_completed event only) |
| `audio_message_id` | integer | Audio message ID (call_recorded event only) |
| `audio_message_url` | string | Audio message URL (call_recorded event only) |

## Campaign Mapping

Since net2phone doesn't have account tags like Anura, we use `user.account_id` for campaign mapping:

### Mapping Method

- **user.account_id**: Maps directly to `campaign_id`
- Example: `user.account_id: 42` → `campaign_id: 42`
- Fallback: `NET2PHONE_DEFAULT_CAMPAIGN_ID` env variable

### Example

```json
{
  "user": {
    "id": 1,
    "name": "Jane Doe",
    "account_id": 42
  }
}
```

This will map to `campaign_id: 42` in AuditorIA.

## Operator Mapping

### Mapping Method

- **user.id**: Maps directly to `operator_id`
- Example: `user.id: 1` → `operator_id: 1`
- Fallback: `NET2PHONE_DEFAULT_OPERATOR_ID` env variable

### Example

```json
{
  "user": {
    "id": 1,
    "name": "Jane Doe"
  }
}
```

This will map to `operator_id: 1` in AuditorIA.

## API Endpoints

### POST /webhook/net2phone/

Main webhook endpoint. Requires `X-API-Key` header.

**Example Request:**
```bash
curl -X POST "https://auditoria.com/webhook/net2phone/" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "call_completed",
    "call_id": "a471d33e562b535b9ec530e1c0c3a5b2",
    "timestamp": "2021-10-27T08:58:21.66Z",
    "duration": 120,
    "direction": "inbound",
    "originating_number": "+5491167950079",
    "dialed_number": "+5491126888209",
    "user": {
      "id": 1,
      "name": "Jane Doe",
      "account_id": 42
    },
    "recording_url": "https://net2phone.com/recordings/call_12345.mp3"
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Webhook processed successfully: call_completed",
  "call_id": "a471d33e562b535b9ec530e1c0c3a5b2",
  "task_id": "abc123-def456-ghi789",
  "recording_downloaded": true,
  "event_type": "call_completed"
}
```

### GET /webhook/net2phone/health

Health check endpoint (no auth required).

**Response:**
```json
{
  "status": "ok",
  "service": "AuditorIA net2phone Integration",
  "webhook_ready": true
}
```

### POST /webhook/net2phone/test

Test endpoint to validate payload format (no auth required).

### GET /net2phone/campaigns

List all available campaigns for mapping.

**Response:**
```json
{
  "total": 5,
  "campaigns": [
    {
      "campaign_id": 1,
      "name": "Sales Campaign",
      "net2phone_mapping": "Use user.account_id as campaign_id"
    }
  ]
}
```

### GET /net2phone/mapping-guide

Get complete guide for mapping net2phone data to AuditorIA.

**Response:**
```json
{
  "campaign_mapping": {
    "method": "NET2PHONE_DEFAULT_CAMPAIGN_ID",
    "description": "Always uses NET2PHONE_DEFAULT_CAMPAIGN_ID env variable",
    "example": {
      "env_variable": "NET2PHONE_DEFAULT_CAMPAIGN_ID=1"
    },
    "maps_to": "campaign_id: 1"
  },
  "operator_mapping": {
    "method": "user.account_id",
    "description": "net2phone uses user.account_id to identify operators/agents",
    "example": {
      "user": {
        "id": 1,
        "account_id": 42,
        "name": "Jane Doe"
      },
      "maps_to": "operator_id: 42"
    }
  }
}
```

### POST /net2phone/validate-mapping

Validate if net2phone user data will map correctly.

**Request:**
```json
{
  "user_id": 1,
  "account_id": 42
}
```

**Response:**
```json
{
  "valid": true,
  "mapping": {
    "campaign": {
      "extracted_id": 42,
      "exists": true,
      "campaign_name": "Sales Campaign"
    },
    "operator": {
      "extracted_id": 1,
      "valid": true
    }
  }
}
```

### GET /net2phone/stats

Get integration statistics.

**Response:**
```json
{
  "total_webhooks_received": 150,
  "total_recordings_downloaded": 142,
  "total_tasks_created": 142,
  "recent_activity_24h": {
    "webhooks": 45,
    "recordings": 43
  }
}
```

## Workflow

```
1. Call occurs in net2phone
   ↓
2. Webhook received (call_completed or call_recorded)
   ↓
3. Verify recording URL exists (recording_url or audio_message_url)
   ↓
4. Download recording from net2phone URL
   ↓
5. Upload to S3/MinIO
   ↓
6. Create transcription Task
   ↓
7. Create CallLog with call_id = Task.uuid
   ↓
8. AuditorIA processes audio
```

**Important**: CallLog is created ONLY after successful recording processing. This prevents orphaned records in call_logs when no recording is available.

## Supported Events

| Event | Description | Recording Field | Action |
|-------|-------------|-----------------|--------|
| `call_completed` | Call ended | `recording_url` | Downloads recording + creates Task |
| `call_answered` | Call answered | N/A | Updates CallLog |
| `call_ringing` | Call initiated | N/A | Creates CallLog |
| `call_missed` | Call missed | N/A | Logs missed call |
| `call_recorded` | Recording available | `audio_message_url` | Downloads recording + creates Task |

**Note**: Both `call_completed` and `call_recorded` events can trigger recording download, but they use different field names for the recording URL.

## Troubleshooting

### Webhook not received

1. Check net2phone webhook configuration
2. Test health endpoint: `curl https://your-domain/webhook/net2phone/health`
3. Check firewall allows incoming connections
4. Verify API Key is correct

### Recording download failed

1. Verify `recording_url` is accessible
2. Check AuditorIA server can reach net2phone URLs
3. Verify S3/MinIO credentials in `.env`
4. Check storage space available

### Signature verification failed

1. Verify `NET2PHONE_SECRET` is correct
2. Check `x-net2phone-signature` and `x-net2phone-timestamp` headers
3. Ensure UTF-8 encoding is used
4. Verify timestamp is not too old (replay attack protection)

### Campaign not found

1. Verify `user.account_id` exists as `campaign_id` in AuditorIA
2. Check campaign exists in AuditorIA
3. Set `NET2PHONE_DEFAULT_CAMPAIGN_ID` as fallback

### Operator mapping issues

1. Verify `user.id` is not None
2. Check operator exists in AuditorIA
3. Set `NET2PHONE_DEFAULT_OPERATOR_ID` as fallback

## Testing

### Manual Webhook Test

```bash
curl -X POST "http://localhost:8001/webhook/net2phone/test" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "call_completed",
    "call_id": "test123",
    "timestamp": "2021-10-27T08:58:21.66Z",
    "duration": 60,
    "direction": "inbound"
  }'
```

### Generate Test Webhook

```bash
curl -X POST "http://localhost:8001/test/net2phone/generate-webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "call_completed",
    "user_id": 1,
    "account_id": 42,
    "has_recording": true,
    "duration": 120
  }'
```

### Get Test Scenarios

```bash
curl http://localhost:8001/test/net2phone/scenarios
```

### Get Cheatsheet

```bash
curl http://localhost:8001/test/net2phone/cheatsheet
```

## Security

- ✅ API Key authentication required
- ✅ HMAC-SHA256 signature verification
- ✅ Rate limiting (30 requests/minute)
- ✅ Payload validation (Pydantic schemas)
- ✅ HTTPS recommended for production
- ✅ No sensitive data logged

## Monitoring

Check webhook activity in AuditorIA:
- **Call Logs**: View all received webhooks
- **Tasks**: View transcription tasks created
- **API Keys**: Monitor webhook API key usage

## Signature Verification

net2phone uses HMAC-SHA256 for webhook signature verification.

### Verification Process

1. Retrieve raw request body
2. Compute HMAC-SHA256 over raw body using shared secret key
3. Compare result with `x-net2phone-signature` header using constant-time comparison

### Example

```python
import hmac
import hashlib

raw_body = b'{"event":"call_completed",...}'
signature = "fe4aad021345e9c6506e163ba62aea8a0f15047712618482a2423cc008dd2fb2"
secret = "your-shared-secret-key"

# Compute HMAC-SHA256 over raw body using shared secret
hmac_hash = hmac.new(
    secret.encode('utf-8'),
    raw_body,
    hashlib.sha256
).hexdigest()

# Constant-time comparison to prevent timing attacks
if hmac.compare_digest(hmac_hash, signature):
    # Signature is valid
    pass
```

## Support

For issues or questions:
- net2phone Docs: https://developer.net2phone.com/
- net2phone Support: https://support.net2phone.com/
- AuditorIA Docs: (internal documentation)
