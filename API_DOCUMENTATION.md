# External API Service - Complete Documentation

## Architecture Overview

**External-API-Service (Port 8001)** - Complete external connection point for third-party integrations
**Backend (Port 8000)** - Internal service for Frontend only

## Authentication

All endpoints require API Key authentication via `X-API-Key` header.

```bash
curl -H "X-API-Key: your-api-key-here" http://localhost:8001/tasks/
```

---

## Complete API Endpoints

### 1. Upload Audio (`/upload/`)

Upload audio files for transcription and analysis.

**Endpoint:** `POST /upload/`

**Request (multipart/form-data):**
- `file`: Audio file (required)
- `campaign_id`: Campaign ID (required)
- `username`: Username (required)
- `operator_id`: Operator ID (required)
- `language`: Language code (default: "es")
- `task`: Task type (default: "transcribe")
- `model`: Model name (default: "nova-3")
- `device`: Device type (default: "deepgram")

**Response:**
```json
{
  "task_id": "uuid",
  "status": "queued",
  "message": "File uploaded successfully"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/upload/" \
  -H "X-API-Key: your-key" \
  -F "file=@audio.mp3" \
  -F "campaign_id=1" \
  -F "username=john" \
  -F "operator_id=123"
```

---

### 2. Task Management (`/tasks/`)

#### 2.1 List Tasks
**Endpoint:** `GET /tasks/?skip=0&limit=10`

**Response:**
```json
[
  {
    "identifier": "task-uuid",
    "status": "completed",
    "task_type": "full_process",
    "file_name": "audio.mp3",
    "language": "es",
    "audio_duration": 120.5,
    "created_at": "2026-02-12T10:00:00"
  }
]
```

#### 2.2 Get Task Details
**Endpoint:** `GET /tasks/{task_uuid}`

**Response:**
```json
{
  "status": "completed",
  "result": {
    "text": "Transcription text...",
    "segments": [...],
    "language": "es"
  },
  "metadata": {
    "task_type": "full_process",
    "file_name": "audio.mp3",
    "language": "es",
    "duration": 3.5,
    "audio_duration": 120.5
  },
  "error": null
}
```

#### 2.3 Get Audio File
**Endpoint:** `GET /tasks/{task_uuid}/audio`

**Response:** Audio file stream (audio/mpeg)

#### 2.4 Delete Task
**Endpoint:** `DELETE /tasks/{task_uuid}`

**Response:** 204 No Content

---

### 3. Agent Identification (`/agent-identification/`)

Identify which speaker is the agent and which is the customer.

**Endpoint:** `GET /agent-identification/{task_uuid}`

**Response:**
```json
{
  "success": true,
  "task_uuid": "uuid",
  "identification": {
    "SPEAKER_00": "Agente",
    "SPEAKER_01": "Cliente"
  }
}
```

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8001/agent-identification/task-uuid"
```

---

### 4. Speaker Analysis (`/speaker-analysis/`)

Get detailed psychological and behavioral analysis of each speaker.

**Endpoint:** `GET /speaker-analysis/{task_uuid}?generate_new=false`

**Response:**
```json
{
  "success": true,
  "task_uuid": "uuid",
  "analysis": {
    "SPEAKER_00": "El agente demuestra profesionalismo y empatía...",
    "SPEAKER_01": "El cliente muestra frustración inicial pero..."
  }
}
```

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8001/speaker-analysis/task-uuid?generate_new=true"
```

---

### 5. Tags Generation (`/tags/`)

Generate descriptive tags for the conversation.

**Endpoint:** `GET /tags/{task_uuid}?generate_new=false`

**Response:**
```json
{
  "success": true,
  "tags": ["CONSULTA_TECNICA", "RESOLUCION_EXITOSA"],
  "extraTags": ["PRODUCTO_X", "GARANTIA"]
}
```

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8001/tags/task-uuid"
```

---

### 6. AI Chat (`/tasks/{uuid}/chat`)

Chat with AI about the transcription content.

#### 6.1 Send Chat Message
**Endpoint:** `POST /tasks/{uuid}/chat`

**Request:**
```json
{
  "chat_input": "¿Cuál fue el motivo principal de la llamada?"
}
```

**Response:**
```json
{
  "response": "El motivo principal fue una consulta sobre..."
}
```

#### 6.2 Get Chat History
**Endpoint:** `GET /tasks/{uuid}/chat`

**Response:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "¿Cuál fue el motivo?",
      "timestamp": "2026-02-12T10:00:00"
    },
    {
      "role": "assistant",
      "content": "El motivo fue...",
      "timestamp": "2026-02-12T10:00:01"
    }
  ]
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/tasks/task-uuid/chat" \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"chat_input": "Resume la llamada"}'
```

---

### 7. Audit Generation (`/audit/`)

Generate quality audit based on campaign criteria.

**Endpoint:** `POST /audit/generate`

**Request:**
```json
{
  "task_uuid": "uuid",
  "is_call": true
}
```

**Response:**
```json
{
  "success": true,
  "task_uuid": "uuid",
  "campaign_id": 1,
  "user_id": "operator123",
  "score": 85.5,
  "is_audit_failure": false,
  "audit": [
    {
      "id": 1,
      "criterion": "Saludo inicial",
      "target_score": 10,
      "score": 9,
      "observations": "El agente saludó apropiadamente..."
    }
  ],
  "generated_by_user": "external_api"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/audit/generate" \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"task_uuid": "uuid", "is_call": true}'
```

---

### 8. Reports (`/reports/`)

#### 8.1 Task Statistics
**Endpoint:** `GET /reports/tasks?days=30`

**Response:**
```json
{
  "total_tasks": 150,
  "completed": 145,
  "failed": 5,
  "processing": 0,
  "average_duration": 125.5,
  "period_days": 30
}
```

#### 8.2 Audit Statistics
**Endpoint:** `GET /reports/audits?days=30`

**Response:**
```json
{
  "total_audits": 100,
  "average_score": 82.3,
  "failures": 15,
  "success_rate": 85.0,
  "period_days": 30
}
```

#### 8.3 Combined Summary
**Endpoint:** `GET /reports/summary?days=30`

**Response:**
```json
{
  "tasks": {...},
  "audits": {...},
  "generated_at": "2026-02-12T10:00:00"
}
```

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8001/reports/summary?days=7"
```

---

### 9. Campaigns (`/campaigns/`)

List available campaigns for task assignment.

**Endpoint:** `GET /campaigns/`

**Response:**
```json
[
  {
    "campaign_id": 1,
    "campaign_name": "Soporte Técnico",
    "approval_score": 70.0
  }
]
```

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8001/campaigns/"
```

---

### 10. Webhook Integration (`/webhook/`)

#### 10.1 Anura PBX Webhook
**Endpoint:** `POST /webhook/anura/`

Receive call events from Anura cloud PBX system.

**Request:**
```json
{
  "hooktrigger": "END",
  "cdrid": "1234567890",
  "dialtime": "2026-02-10 10:30:00",
  "calling": "+5491167950079",
  "called": "+5491126888209",
  "direction": "inbound",
  "duration": 120,
  "wasrecorded": true,
  "audio_file_mp3": "https://anura.com/recordings/12345.mp3",
  "accounttags": "campaign_123",
  "queueagentextension": "300"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Webhook processed successfully: END",
  "call_id": "1234567890",
  "task_id": "task-uuid",
  "recording_downloaded": true
}
```

#### 10.2 Webhook Health Check
**Endpoint:** `GET /webhook/anura/health`

**Response:**
```json
{
  "status": "ok",
  "service": "AuditorIA Anura Integration",
  "webhook_ready": true
}
```

---

## Complete Workflow Example

### 1. Upload Audio
```bash
TASK_ID=$(curl -X POST "http://localhost:8001/upload/" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@call.mp3" \
  -F "campaign_id=1" \
  -F "username=john" \
  -F "operator_id=123" | jq -r '.task_id')
```

### 2. Poll Task Status
```bash
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8001/tasks/$TASK_ID"
```

### 3. Get Agent Identification
```bash
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8001/agent-identification/$TASK_ID"
```

### 4. Get Speaker Analysis
```bash
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8001/speaker-analysis/$TASK_ID"
```

### 5. Generate Tags
```bash
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8001/tags/$TASK_ID"
```

### 6. Generate Audit
```bash
curl -X POST "http://localhost:8001/audit/generate" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"task_uuid\": \"$TASK_ID\", \"is_call\": true}"
```

### 7. Chat with AI
```bash
curl -X POST "http://localhost:8001/tasks/$TASK_ID/chat" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"chat_input": "Resume esta llamada"}'
```

### 8. Download Audio
```bash
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8001/tasks/$TASK_ID/audio" -o audio.mp3
```

---

## Rate Limits

- Upload: 10 requests/minute
- Task List: 20 requests/minute
- Task Details: 60 requests/minute
- Audio Download: 5 requests/minute
- Analysis Endpoints: 20 requests/minute
- AI Chat: 5 requests/minute
- Audit Generation: 10 requests/minute
- Reports: 30 requests/minute

---

## Error Responses

All endpoints return standard HTTP status codes:

- `200 OK` - Success
- `201 Created` - Resource created
- `204 No Content` - Success with no response body
- `400 Bad Request` - Invalid request parameters
- `401 Unauthorized` - Missing or invalid API key
- `404 Not Found` - Resource not found
- `409 Conflict` - Duplicate resource
- `413 Payload Too Large` - File too large
- `422 Unprocessable Entity` - Validation error
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

**Error Format:**
```json
{
  "detail": "Error message description"
}
```

---

## Environment Configuration

Required environment variables in `.env`:

```env
# OpenAI for AI features
OPENAI_API_KEY=sk-...
DEEPGRAM_API_KEY=...

# Database
DB_URL=postgresql://user:pass@localhost:5432/db

# S3/MinIO Storage
S3_BUCKET=audios
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# External endpoint for presigned URLs
S3_EXTERNAL_ENDPOINT=http://localhost:9000

# App Settings
APP_NAME="AuditorIA External API"
DEBUG=false
CORS_ORIGINS=["*"]
MAX_UPLOAD_SIZE_MB=100
```

---

## Architecture

```
External Client
     |
     | HTTP + API Key Auth
     v
External-API-Service (Port 8001)
     |
     |-- Database (PostgreSQL)
     |-- S3/MinIO (Audio Storage)
     |-- OpenAI API (AI Features)
     |-- Task Queue (Tasks Table)
     |
     v
Worker-Deepgram (Polls tasks)
     |
     |-- Deepgram API (Transcription)
     |-- Database (Updates results)
```

**Frontend Users:**
```
Frontend (React)
     |
     | HTTP + JWT Auth
     v
Backend (Port 8000) - Internal Only
     |
     |-- Same Database
     |-- Same S3/MinIO
```

---

## Service Implementation Status

### ✅ Fully Implemented Services

1. **upload_router** - File upload with S3 storage
2. **tasks_router** - Task CRUD and audio streaming
3. **agent_identification_router** - AI-powered speaker role identification
4. **speaker_analysis_router** - AI-powered psychological analysis
5. **tags_router** - AI-powered tag generation
6. **chat_router** - AI chat about transcriptions
7. **audit_router** - AI-powered quality auditing
8. **reports_router** - Statistical reporting
9. **campaigns_router** - Campaign listing
10. **webhooks_router** - Anura PBX integration
11. **anura_helpers_router** - Anura utility endpoints
12. **test_utils_router** - Testing utilities (DEBUG mode only)

### 🔧 Backend Services (Port 8000)

All Backend services are for **Frontend use only** and should NOT be accessed by external clients.

---

## Security

1. **API Key Authentication** - All endpoints require valid API key
2. **Rate Limiting** - Prevents abuse with per-endpoint limits
3. **CORS Protection** - Configurable allowed origins
4. **File Validation** - Size and type checks for uploads
5. **S3 Presigned URLs** - Secure temporary audio access
6. **SQL Injection Protection** - Parameterized queries
7. **Input Validation** - Pydantic schemas for all requests

---

## Testing

```bash
# Health check
curl http://localhost:8001/

# Test with invalid API key (should fail)
curl -H "X-API-Key: invalid" http://localhost:8001/tasks/

# Test with valid API key
curl -H "X-API-Key: your-key" http://localhost:8001/campaigns/
```

---

## Deployment

### Docker Compose

The service runs as part of the docker-compose stack:

```yaml
external-api:
  build: ./External-API-Service
  ports:
    - "8001:8000"
  environment:
    - DB_URL=postgresql://...
    - S3_ENDPOINT=http://minio:9000
    - OPENAI_API_KEY=...
```

### Rebuild and Deploy

```bash
# Rebuild service
docker-compose build external-api --no-cache

# Recreate container
docker-compose up -d --force-recreate external-api

# View logs
docker-compose logs -f external-api
```

---

## Support

For issues or questions, contact the development team or refer to the main project repository.

**API Version:** 1.0.0
**Last Updated:** 2026-02-12
