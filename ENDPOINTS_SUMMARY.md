# 🎯 Anura Integration - Endpoints Summary

## 📡 Webhook Endpoints

### POST /webhook/anura/
**Main webhook receiver for Anura events**
- Authentication: API Key required
- Rate limit: 30 req/min
- Triggers: START, TALK, END
- Downloads recordings on END events
- Creates transcription tasks automatically

### GET /webhook/anura/health
**Health check** (no auth)
- Returns: service status and webhook readiness

### POST /webhook/anura/test
**Validate webhook payload** (no auth)
- Test payload format without creating records

---

## 🛠️ Helper Endpoints (API Key required)

### GET /anura/campaigns
**List all campaigns for mapping**
```json
{
  "campaigns": [
    {
      "campaign_id": 1,
      "name": "Sales Campaign",
      "anura_tag_format": "campaign_1"
    }
  ]
}
```
**Use case**: Find campaign IDs to configure in Anura account tags

### GET /anura/mapping-guide
**Complete mapping documentation**
- Campaign mapping examples
- Operator mapping options
- Example webhook payloads

### POST /anura/validate-mapping
**Test if tags/extensions map correctly**
```json
{
  "accounttags": "campaign_1",
  "queueagentextension": "300"
}
```
**Use case**: Validate configuration before deploying webhooks

### GET /anura/stats
**Integration statistics**
- Total webhooks received
- Recordings downloaded
- Tasks created
- Recent activity (24h)

---

## 🧪 Testing Endpoints

### POST /test/anura/generate-webhook
**Generate realistic test payload**
```json
{
  "trigger": "END",
  "campaign_id": 1,
  "operator_id": 300,
  "has_recording": true,
  "duration": 120
}
```
**Returns**: Complete webhook payload + curl command

### GET /test/anura/scenarios
**Predefined test scenarios**
- successful_inbound_call
- outbound_call
- call_without_recording
- call_start_only
- call_talk_event
- short_call
- long_call
- unknown_campaign

### GET /test/anura/cheatsheet
**Quick reference guide**
- All endpoints
- Account tag formats
- Agent mapping rules
- Troubleshooting tips

---

## 📊 Usage Examples

### 1. Configure Campaign Mapping
```bash
# Step 1: List available campaigns
curl -H "X-API-Key: YOUR_KEY" \
  http://localhost:8001/anura/campaigns

# Step 2: Validate mapping
curl -X POST http://localhost:8001/anura/validate-mapping \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"accounttags": "campaign_1"}'
```

### 2. Test Webhook (without recording download)
```bash
# Generate test payload
curl -X POST http://localhost:8001/test/anura/generate-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "trigger": "END",
    "campaign_id": 1,
    "has_recording": false
  }'

# Test with generated payload
curl -X POST http://localhost:8001/webhook/anura/test \
  -H "Content-Type: application/json" \
  -d '{GENERATED_PAYLOAD}'
```

### 3. Monitor Integration
```bash
# Check statistics
curl -H "X-API-Key: YOUR_KEY" \
  http://localhost:8001/anura/stats

# Health check
curl http://localhost:8001/webhook/anura/health
```

---

## 🔧 Anura Configuration

### In Anura Panel de Control:

**1. Create Event Template:**
- Trigger: `END`
- URL: `https://your-domain.com/webhook/anura/`
- Method: `POST`
- Auth: `X-API-Key: {YOUR_AUDITORIA_API_KEY}`

**2. Configure Account Tags:**
- Add tag to accounts: `campaign_1` (or any campaign_id)
- Multiple tags: `campaign_1, support_queue, tag3`

**3. Agent Extensions:**
- Use numeric extensions (e.g., `300`, `301`)
- Agent names with numbers also work (e.g., `Agent 456`)

---

## 🚀 Quick Start

```bash
# 1. Test health
curl http://localhost:8001/webhook/anura/health

# 2. Get mapping guide
curl -H "X-API-Key: YOUR_KEY" \
  http://localhost:8001/anura/mapping-guide

# 3. Validate your mapping
curl -X POST http://localhost:8001/anura/validate-mapping \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"accounttags": "campaign_1", "queueagentextension": "300"}'

# 4. Generate test webhook
curl -X POST http://localhost:8001/test/anura/generate-webhook \
  -H "Content-Type: application/json" \
  -d '{"trigger": "END", "campaign_id": 1, "has_recording": true}'

# 5. Send test webhook
curl -X POST http://localhost:8001/webhook/anura/ \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{TEST_PAYLOAD}'

# 6. Check stats
curl -H "X-API-Key: YOUR_KEY" \
  http://localhost:8001/anura/stats
```

---

## 📚 Full Documentation

See `ANURA_INTEGRATION.md` for:
- Detailed setup instructions
- Anura Panel configuration
- Troubleshooting guide
- Advanced configuration options
