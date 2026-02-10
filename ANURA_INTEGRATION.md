# Anura Integration for AuditorIA

This module enables AuditorIA to receive webhooks from Anura cloud PBX and automatically transcribe call recordings.

## Features

- 📞 **Real-time call events**: Receives START, TALK, and END events from Anura
- 🎙️ **Automatic recording download**: Downloads MP3 recordings when calls end
- 📝 **Transcription tasks**: Automatically creates transcription tasks in AuditorIA
- 🏷️ **Campaign mapping**: Maps Anura account tags to AuditorIA campaigns
- 👤 **Agent mapping**: Maps Anura agents to AuditorIA operators

## Setup

### 1. Anura Configuration

#### Create Webhook in Anura Panel

1. Go to **Panel de Control → Eventos → Crear Plantilla**
2. Configure the event:

**Trigger (Hook):**
- Select: `END` (when call ends)
- Direction: `All` or specific (Inbound/Outbound)

**Request Settings:**
- Protocol: `HTTPS`
- Host: `your-domain.com` (e.g., `auditoria.linksolution.com.ar`)
- Port: `443`
- Route: `/webhook/anura/`
- Method: `POST`
- Content-Type: `application/json`
- Authorization: `X-API-Key: {YOUR_AUDITORIA_API_KEY}`

**Body Template (JSON):**
```json
{
  "hooktrigger": "{{ hooktrigger }}",
  "hookid": {{ hookid }},
  "hookname": "{{ hookname }}",
  "cdrid": "{{ cdrid }}",
  "dialtime": "{{ dialtime }}",
  "direction": "{{ direction }}",
  "calling": "{{ calling }}",
  "called": "{{ called }}",
  "status": "{{ status }}",
  "duration": {{ duration }},
  "billseconds": {{ billseconds }},
  "price": {{ price }},
  "wasrecorded": {{ wasrecorded }},
  "audio_file_mp3": "{{ audio_file_mp3 }}",
  "accounttags": "{{ accounttags }}",
  "queueagentname": "{{ queueagentname }}",
  "queueagentextension": "{{ queueagentextension }}",
  "tenantid": {{ tenantid }},
  "accountid": {{ accountid }}
}
```

3. **Apply to Accounts**: Select which accounts/campaigns should send webhooks

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
ANURA_DEFAULT_CAMPAIGN_ID=1  # Default campaign if not in tags
ANURA_DEFAULT_OPERATOR_ID=1  # Default operator if not detected
```

#### Create API Key

1. Access AuditorIA main application
2. Go to **Settings → API Keys**
3. Create a new Global API Key
4. Copy the key - you'll use it in Anura webhook authorization

## Webhook Payload

The endpoint accepts the following fields from Anura:

### Required Fields
- `hooktrigger`: Event type (`START`, `TALK`, `END`)
- `cdrid`: Unique call ID
- `dialtime`: Call start time (format: `YYYY-MM-DD HH:MM:SS`)

### Important Fields
- `direction`: Call direction (`inbound`/`outbound`)
- `calling`: Origin phone number
- `called`: Destination phone number
- `duration`: Call duration in seconds
- `wasrecorded`: Whether recording exists (`true`/`false`)
- `audio_file_mp3`: URL to download MP3 recording
- `accounttags`: Tags for campaign mapping (e.g., `campaign_123`)
- `queueagentextension`: Agent extension for operator mapping

Full variable list: https://kb.anura.com.ar/es/articles/2579414-variables-eventos-templetizados

## Campaign Mapping

To map Anura accounts to AuditorIA campaigns:

### Option 1: Account Tags (Recommended)

Add tags to Anura accounts in the format:
- `campaign_123` → Maps to campaign ID `123`
- `456` → Maps to campaign ID `456`

Multiple tags supported: `campaign_123, tag2, campaign_456`

### Option 2: Default Campaign

Set `ANURA_DEFAULT_CAMPAIGN_ID` in `.env` for all unmapped calls.

## Operator Mapping

### Option 1: Agent Extension

If agent extension is numeric, it's used as operator_id:
- Extension `300` → Operator ID `300`

### Option 2: Agent Name

If name contains numbers, first number is used:
- Name `Agent 123` → Operator ID `123`

### Option 3: Default Operator

Set `ANURA_DEFAULT_OPERATOR_ID` in `.env` for unmapped agents.

## API Endpoints

### POST /webhook/anura/

Main webhook endpoint. Requires `X-API-Key` header.

**Example Request:**
```bash
curl -X POST "https://auditoria.com/webhook/anura/" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "hooktrigger": "END",
    "cdrid": "1234567890",
    "dialtime": "2026-02-10 10:30:00",
    "calling": "+5491167950079",
    "called": "+5491126888209",
    "direction": "inbound",
    "duration": 120,
    "wasrecorded": true,
    "audio_file_mp3": "https://anura.com/recordings/12345.mp3",
    "accounttags": "campaign_1",
    "queueagentextension": "300"
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Webhook processed successfully: END",
  "call_id": "1234567890",
  "task_id": "abc123-def456-ghi789",
  "recording_downloaded": true
}
```

### GET /webhook/anura/health

Health check endpoint (no auth required).

**Response:**
```json
{
  "status": "ok",
  "service": "AuditorIA Anura Integration",
  "webhook_ready": true
}
```

### POST /webhook/anura/test

Test endpoint to validate payload format (no auth required).

## Workflow

```
1. Call starts in Anura
   ↓
2. START webhook received (creates CallLog)
   ↓
3. Call answered
   ↓
4. TALK webhook received (updates CallLog)
   ↓
5. Call ends
   ↓
6. END webhook received
   ↓
7. Download recording from Anura URL
   ↓
8. Upload to S3/MinIO
   ↓
9. Create transcription Task
   ↓
10. AuditorIA processes audio
```

## Troubleshooting

### Webhook not received

1. Check Anura Panel → Eventos → Verify webhook is configured
2. Check firewall allows incoming connections
3. Test health endpoint: `curl https://your-domain/webhook/anura/health`
4. Check Anura webhook logs in Panel de Control

### Recording download failed

1. Verify `audio_file_mp3` URL is accessible
2. Check AuditorIA server can reach Anura URLs
3. Verify S3/MinIO credentials in `.env`
4. Check storage space available

### Campaign not found

1. Verify `accounttags` format in Anura
2. Check campaign exists in AuditorIA
3. Set `ANURA_DEFAULT_CAMPAIGN_ID` as fallback

### Operator mapping issues

1. Verify agent extension is numeric
2. Check operator exists in AuditorIA
3. Set `ANURA_DEFAULT_OPERATOR_ID` as fallback

## Testing

### Manual Webhook Test

```bash
curl -X POST "http://localhost:8001/webhook/anura/test" \
  -H "Content-Type: application/json" \
  -d '{
    "hooktrigger": "END",
    "cdrid": "test123",
    "dialtime": "2026-02-10 10:30:00",
    "calling": "+5491167950079",
    "called": "+5491126888209",
    "direction": "inbound",
    "duration": 60,
    "wasrecorded": false
  }'
```

### Simulate Anura Webhook

```bash
curl -X POST "http://localhost:8001/webhook/anura/" \
  -H "X-API-Key: your-test-api-key" \
  -H "Content-Type: application/json" \
  -d @test_webhook_payload.json
```

## Security

- ✅ API Key authentication required
- ✅ Rate limiting (30 requests/minute)
- ✅ Payload validation (Pydantic schemas)
- ✅ HTTPS recommended for production
- ✅ No sensitive data logged

## Monitoring

Check webhook activity in AuditorIA:
- **Call Logs**: View all received webhooks
- **Tasks**: View transcription tasks created
- **API Keys**: Monitor webhook API key usage

## Support

For issues or questions:
- Anura Docs: https://kb.anura.com.ar/es/
- AuditorIA Docs: (internal documentation)
- Anura Support: +54911xxxxxxx or soporte@anura.com.ar
