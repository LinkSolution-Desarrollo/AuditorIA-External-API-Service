# Cómo Generar y Usar API Tokens

## 📋 Resumen

El External-API usa API Keys para autenticación. Cada request debe incluir el header `X-API-Key` con tu token.

---

## 🔑 Método 1: Script Python (Recomendado)

### 1. Crear un nuevo API Key

```bash
cd External-API-Service
python create_api_key.py create "Mi Automatización"
```

**Output:**
```
🔑 Creando API Key 'Mi Automatización'...

✅ API Key creado exitosamente!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ID:       1
Nombre:   Mi Automatización
Prefijo:  abc123...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  GUARDA ESTE API KEY - NO SE MOSTRARÁ NUEVAMENTE:

abc123xyz789DEF456ghi789JKL012mno345PQR678

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 Uso en tus requests:
   curl -H "X-API-Key: abc123xyz789..." http://localhost:8001/campaigns/
```

### 2. Listar API Keys existentes

```bash
python create_api_key.py list
```

**Output:**
```
📋 API Keys activos:

ID: 1
  Nombre:     Mi Automatización
  Prefijo:    abc123...
  Creado:     2026-02-12 10:30:00
  Último uso: 2026-02-12 11:45:00
```

### 3. Revocar un API Key

```bash
python create_api_key.py revoke 1
```

---

## 🔑 Método 2: Usando el Backend (vía Frontend)

Si tienes acceso al Backend en http://localhost:8000:

### 1. Crear API Key via REST

```bash
curl -X POST "http://localhost:8000/api/api-keys/?name=Mi%20Automatizacion"
```

**Response:**
```json
{
  "id": 1,
  "name": "Mi Automatizacion",
  "prefix": "abc123",
  "created_at": "2026-02-12T10:30:00",
  "is_active": true,
  "last_used_at": null,
  "raw_key": "abc123xyz789DEF456ghi789JKL012mno345PQR678"
}
```

⚠️ **IMPORTANTE:** Guarda el `raw_key` - solo se muestra una vez!

### 2. Listar API Keys

```bash
curl "http://localhost:8000/api/api-keys/"
```

### 3. Revocar API Key

```bash
curl -X DELETE "http://localhost:8000/api/api-keys/1"
```

---

## 🔑 Método 3: SQL Directo (Avanzado)

Si tienes acceso directo a PostgreSQL:

```sql
-- Generar una key manualmente (en Python o terminal)
-- raw_key = "tu-key-secreta-aleatoria"
-- hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()

INSERT INTO global_api_keys (name, hashed_key, prefix, is_active, created_at)
VALUES (
    'Mi Automatización',
    '<hash_sha256_de_tu_key>',
    '<primeros_8_caracteres>',
    true,
    NOW()
);
```

**No recomendado** - usa los métodos 1 o 2 en su lugar.

---

## 💻 Usar el API Key en tus Automatizaciones

### cURL

```bash
export API_KEY="abc123xyz789DEF456ghi789JKL012mno345PQR678"

# Subir audio
curl -X POST "http://localhost:8001/upload/" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@audio.mp3" \
  -F "campaign_id=1" \
  -F "username=automation" \
  -F "operator_id=999"

# Consultar task
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8001/tasks/{task_uuid}"

# Listar campañas
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8001/campaigns/"
```

### Python

```python
import requests

API_KEY = "abc123xyz789DEF456ghi789JKL012mno345PQR678"
BASE_URL = "http://localhost:8001"

headers = {
    'X-API-Key': API_KEY
}

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
    result = response.json()
    task_id = result['task_id']

# Consultar status
response = requests.get(
    f"{BASE_URL}/tasks/{task_id}",
    headers=headers
)
task = response.json()
print(f"Status: {task['status']}")
```

### JavaScript/Node.js

```javascript
const API_KEY = 'abc123xyz789DEF456ghi789JKL012mno345PQR678';
const BASE_URL = 'http://localhost:8001';

// Subir audio
const formData = new FormData();
formData.append('file', fs.createReadStream('audio.mp3'));
formData.append('campaign_id', '1');
formData.append('username', 'automation');
formData.append('operator_id', '999');

const response = await fetch(`${BASE_URL}/upload/`, {
  method: 'POST',
  headers: {
    'X-API-Key': API_KEY
  },
  body: formData
});

const result = await response.json();
console.log('Task ID:', result.task_id);

// Consultar status
const taskResponse = await fetch(
  `${BASE_URL}/tasks/${result.task_id}`,
  {
    headers: { 'X-API-Key': API_KEY }
  }
);

const task = await taskResponse.json();
console.log('Status:', task.status);
```

### PowerShell

```powershell
$API_KEY = "abc123xyz789DEF456ghi789JKL012mno345PQR678"
$BASE_URL = "http://localhost:8001"

$headers = @{
    "X-API-Key" = $API_KEY
}

# Listar campañas
$response = Invoke-RestMethod -Uri "$BASE_URL/campaigns/" -Headers $headers
$response

# Subir audio
$filePath = "C:\path\to\audio.mp3"
$form = @{
    file = Get-Item -Path $filePath
    campaign_id = "1"
    username = "automation"
    operator_id = "999"
}

$response = Invoke-RestMethod -Uri "$BASE_URL/upload/" `
    -Method Post `
    -Headers $headers `
    -Form $form

Write-Host "Task ID: $($response.task_id)"
```

---

## 🔒 Seguridad

### Mejores Prácticas

1. **Nunca compartas tus API Keys** - Son como contraseñas
2. **Guarda las keys en variables de entorno**, no en código:
   ```bash
   export AUDITORIA_API_KEY="tu-key-aqui"
   ```
3. **Usa nombres descriptivos** para identificar el uso:
   - ✅ "Automatización Anura PBX"
   - ✅ "Script de Migración"
   - ❌ "test"
   - ❌ "key1"

4. **Revoca keys inmediatamente** si sospechas que fueron comprometidas

5. **Rota las keys periódicamente** (cada 90 días)

### Rate Limits

El API tiene los siguientes límites por minuto:

- Upload: 10 requests/min
- Task queries: 60 requests/min
- Analysis endpoints: 20 requests/min
- AI Chat: 5 requests/min
- Audit generation: 10 requests/min

Si excedes el límite, recibirás HTTP 429 (Too Many Requests).

---

## 🧪 Verificar que tu API Key funciona

```bash
# Test simple
curl -H "X-API-Key: TU_KEY_AQUI" http://localhost:8001/campaigns/

# Deberías ver la lista de campañas
# Si ves 401 Unauthorized, tu key es inválida
# Si ves 200 OK con JSON, ¡funciona!
```

---

## 🚨 Troubleshooting

### Error: "Invalid API Key"
- Verifica que copiaste la key completa (sin espacios)
- Asegúrate de usar el header correcto: `X-API-Key`
- Verifica que la key no fue revocada

### Error: "Connection refused"
- Verifica que External-API está corriendo:
  ```bash
  docker-compose ps external-api
  ```
- Verifica el puerto (debería ser 8001)

### Error: "Too Many Requests (429)"
- Estás excediendo el rate limit
- Espera 1 minuto y vuelve a intentar
- Considera espaciar tus requests

---

## 📚 Más Información

- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - Documentación completa de endpoints
- [python_sdk_example.py](python_sdk_example.py) - Ejemplos completos en Python

---

## 🆘 Soporte

Si tienes problemas:
1. Verifica los logs: `docker-compose logs external-api`
2. Verifica que la base de datos está corriendo: `docker-compose ps postgres`
3. Contacta al equipo de desarrollo
