# Quick Start - API Token y Uso

## ✅ External-API Rebuildeado y Corriendo

El servicio External-API está corriendo en **http://localhost:8001**

---

## 🔑 Tu API Key de Producción

```
Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4
```

**Nombre:** Automatizacion_Produccion
**ID:** 1
**Creado:** 2026-02-12

---

## 🚀 Uso Inmediato

### 1. Test Simple

```bash
curl -H "X-API-Key: Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4" \
  http://localhost:8001/campaigns/
```

### 2. Subir Audio

```bash
curl -X POST "http://localhost:8001/upload/" \
  -H "X-API-Key: Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4" \
  -F "file=@tu_audio.mp3" \
  -F "campaign_id=1" \
  -F "username=tu_usuario" \
  -F "operator_id=123"
```

**Response:**
```json
{
  "task_id": "uuid-de-la-tarea",
  "status": "queued",
  "message": "File uploaded successfully"
}
```

### 3. Consultar Status

```bash
TASK_ID="uuid-de-la-tarea"

curl -H "X-API-Key: Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4" \
  "http://localhost:8001/tasks/$TASK_ID"
```

### 4. Obtener Análisis (cuando status = "completed")

```bash
# Identificación de agentes
curl -H "X-API-Key: Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4" \
  "http://localhost:8001/agent-identification/$TASK_ID"

# Análisis de speakers
curl -H "X-API-Key: Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4" \
  "http://localhost:8001/speaker-analysis/$TASK_ID"

# Tags
curl -H "X-API-Key: Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4" \
  "http://localhost:8001/tags/$TASK_ID"

# Generar auditoría
curl -X POST "http://localhost:8001/audit/generate" \
  -H "X-API-Key: Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4" \
  -H "Content-Type: application/json" \
  -d "{\"task_uuid\": \"$TASK_ID\", \"is_call\": true}"
```

---

## 🐍 Python (Uso Simple)

```python
import requests

API_KEY = "Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4"
BASE_URL = "http://localhost:8001"

headers = {'X-API-Key': API_KEY}

# Subir audio
with open('audio.mp3', 'rb') as f:
    files = {'file': f}
    data = {
        'campaign_id': 1,
        'username': 'automation',
        'operator_id': 999
    }
    response = requests.post(
        f"{BASE_URL}/upload/",
        headers=headers,
        files=files,
        data=data
    )
    task_id = response.json()['task_id']

print(f"Task ID: {task_id}")

# Esperar y consultar
import time
while True:
    response = requests.get(
        f"{BASE_URL}/tasks/{task_id}",
        headers=headers
    )
    task = response.json()

    if task['status'] == 'completed':
        print("Transcripción completa!")
        print(task['result']['text'][:200])
        break
    elif task['status'] == 'failed':
        print(f"Error: {task['error']}")
        break

    print(f"Status: {task['status']}, esperando...")
    time.sleep(5)

# Obtener análisis
response = requests.get(
    f"{BASE_URL}/agent-identification/{task_id}",
    headers=headers
)
print("Identificación:", response.json())
```

---

## 🔧 Gestión de API Keys

### Crear nuevo API Key

```bash
cd External-API-Service
python create_api_key.py create "Nombre_Descriptivo"
```

### Listar API Keys

```bash
python create_api_key.py list
```

### Revocar API Key

```bash
python create_api_key.py revoke <ID>
```

---

## 📊 Endpoints Disponibles

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/upload/` | POST | Subir audio |
| `/tasks/` | GET | Listar tareas |
| `/tasks/{uuid}` | GET | Detalle de tarea |
| `/tasks/{uuid}/audio` | GET | Descargar audio |
| `/agent-identification/{uuid}` | GET | Identificar agente/cliente |
| `/speaker-analysis/{uuid}` | GET | Análisis psicológico |
| `/tags/{uuid}` | GET | Generar tags |
| `/tasks/{uuid}/chat` | POST | Chat con IA |
| `/audit/generate` | POST | Generar auditoría |
| `/reports/summary` | GET | Estadísticas |
| `/campaigns/` | GET | Listar campañas |

---

## 📚 Documentación Completa

- **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)** - Documentación completa de endpoints
- **[python_sdk_example.py](python_sdk_example.py)** - SDK Python completo con ejemplos
- **[COMO_GENERAR_TOKEN.md](COMO_GENERAR_TOKEN.md)** - Guía detallada de API keys

---

## 🎯 Workflow Típico

```
1. Subir audio → Obtener task_id
2. Polling de status hasta "completed"
3. Obtener transcripción completa
4. Obtener análisis (identificación, speaker analysis, tags)
5. Generar auditoría de calidad
6. (Opcional) Chat con IA sobre la transcripción
```

---

## ⚙️ Estado del Servicio

```bash
# Ver logs
docker-compose logs -f external-api

# Ver status
docker-compose ps external-api

# Restart si es necesario
docker-compose restart external-api
```

---

## 🚨 Troubleshooting

### No conecta al API
```bash
# Verificar que está corriendo
docker-compose ps external-api

# Ver logs
docker-compose logs external-api --tail 50
```

### Error de autenticación
- Verifica que usas el header `X-API-Key` (no `Authorization`)
- Verifica que copiaste la key completa
- Lista los keys activos: `python create_api_key.py list`

### Rate limit (429)
- Espera 1 minuto
- El límite de upload es 10/min
- Para otros endpoints: 20-60/min

---

## 💡 Tips

1. **Guarda el API key en una variable de entorno:**
   ```bash
   export AUDITORIA_API_KEY="Vhr7CRb0_HlEdPRmEL_l6GNJYzVGr6Wl-1Sg-vzaWk4"
   curl -H "X-API-Key: $AUDITORIA_API_KEY" http://localhost:8001/campaigns/
   ```

2. **Para producción:** Usa el External-API (puerto 8001), NO el Backend (puerto 8000)

3. **Polling inteligente:**
   - Primeros 30s: cada 5s
   - Después: cada 10-15s
   - Timeout recomendado: 10 minutos

4. **Batch processing:** Sube múltiples archivos en paralelo para mejor throughput

---

**¿Listo para usar?** Tu API key está activa y el servicio está corriendo. ¡Comienza a integrarlo en tu automatización!
