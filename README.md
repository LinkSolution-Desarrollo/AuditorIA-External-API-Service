# AuditorIA External API Service

Standalone service for external users to upload audio files to the AuditorIA platform.

## Features

- **Secure Uploads**: Authenticated via Global API Keys managed in the main application.
- **S3 Integration**: Uploads directly to MinIO/S3 storage.
- **Task Creation**: Automatically creates transcription tasks in the main `auditoria_db`.
- **Anura Integration**: 🆕 Receive webhooks from Anura cloud PBX and auto-transcribe calls
- **Security**:
  - Rate Limiting (SlowAPI)
  - File Type & Magic Number Validation
  - Size Limits
  - Type-safe Configuration

## Setup

1. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration**:
   Ensure the `.env` file is present (copied from the main Backend) or contains:
   - `DB_URL`
   - `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`

3. **Run**:

   ```bash
   uvicorn app.main:app --reload --port 8001
   ```

## API Usage

### Upload File (`POST /upload/`)

**Headers**:

- `X-API-Key`: Your Global API Key

**Body**:

- `file`: Audio file (@file.mp3)

**Example**:

```bash
curl -X POST "http://localhost:8001/upload/" \
  -H "X-API-Key: <YOUR_KEY>" \
  -F "file=@audio.wav"
```

### Anura Webhook (`POST /webhook/anura/`)

🆕 **New**: Receive call events from Anura PBX and automatically transcribe recordings.

See [ANURA_INTEGRATION.md](ANURA_INTEGRATION.md) for full documentation.

**Example**:

```bash
curl -X POST "http://localhost:8001/webhook/anura/" \
  -H "X-API-Key: <YOUR_KEY>" \
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
    "accounttags": "campaign_1"
  }'
```
