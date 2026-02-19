# Colección de Postman - AuditorIA External API

## 📥 Importar la Colección

1. Abrir Postman
2. Click en "Import" (esquina superior izquierda)
3. Seleccionar el archivo `postman_collection.json`
4. Click en "Upload" y luego "Import"

## ⚙️ Configurar Variables

Antes de usar los endpoints, configura las variables de la colección:

1. En Postman, seleccionar la colección "AuditorIA External API"
2. Ir a la tab "Variables"
3. Configurar los siguientes valores:

| Variable | Valor | Descripción |
|----------|-------|-------------|
| `base_url` | `http://localhost:8001` | URL de la API (cambiar si está en otro host) |
| `api_key` | `TU_API_KEY` | Tu Global API Key de AuditorIA |
| `task_uuid` | `uuid-ejemplo` | UUID de una tarea para probar |

### Obtener API Key

1. Iniciar sesión en AuditorIA-App
2. Ir a Settings > API Keys
3. Crear una nueva "Global API Key"
4. Copiar el valor y pegarlo en la variable `api_key`

### Obtener Task UUID

1. Usar el endpoint "List Tasks"
2. Copiar el `uuid` de cualquier tarea
3. Pegarlo en la variable `task_uuid`

## 📚 Endpoints Disponibles

### 🔍 Auditoría

#### Generar Auditoría de Llamada
```
POST /audit/generate
Body: {
  "task_uuid": "{{task_uuid}}",
  "is_call": true
}
```

#### Generar Auditoría de Chat
```
POST /audit/generate
Body: {
  "task_uuid": "{{task_uuid}}",
  "is_call": false
}
```

### 🏷️ Tags

#### Obtener Tags
```
GET /tags/{task_uuid}
```

#### Regenerar Tags
```
GET /tags/{task_uuid}?generate_new=true
```

### 🎤 Análisis de Hablantes

```
GET /speaker-analysis/{task_uuid}
```

### 👤 Identificación de Agentes

```
GET /agent-identification/{task_uuid}
```

### 📊 Reportes

#### Estadísticas de Tareas
```
GET /reports/tasks?days=30
```

#### Estadísticas de Auditorías
```
GET /reports/audits?days=30
```

#### Reporte Resumido
```
GET /reports/summary?days=30
```

## 🧪 Ejemplo de Uso

### Flujo Completo de Auditoría

1. **Listar tareas** para obtener un UUID
   - Request: `GET /tasks/?limit=5`
   - Copiar el UUID de una tarea

2. **Verificar tarea** tiene transcripción
   - Request: `GET /tasks/{copied_uuid}`
   - Ver que `status` sea "completed"

3. **Generar auditoría**
   - Request: `POST /audit/generate`
   - Body: `{"task_uuid": "{copied_uuid}", "is_call": true}`

4. **Obtener tags** de la misma tarea
   - Request: `GET /tags/{copied_uuid}`

5. **Análisis de hablantes**
   - Request: `GET /speaker-analysis/{copied_uuid}`

6. **Identificar agentes**
   - Request: `GET /agent-identification/{copied_uuid}`

7. **Ver reportes** globales
   - Request: `GET /reports/summary?days=30`

## 📝 Respuestas Esperadas

### Auditoría Exitosa
```json
{
  "success": true,
  "task_uuid": "075bcc8c-8fe5-11f0-b36d-0242ac110007",
  "campaign_id": 1,
  "user_id": "user123",
  "score": 85.5,
  "is_audit_failure": false,
  "audit": [
    {
      "id": 1,
      "criterion": "Cortesía y profesionalismo",
      "target_score": 10.0,
      "score": 9.5,
      "observations": "El agente fue muy cordial"
    }
  ],
  "generated_by_user": "external_api_key_1"
}
```

### Tags
```json
{
  "success": true,
  "tags": ["VENTA", "TECNICO", "RECLAMO"],
  "extraTags": ["problema_de_pago", "actualizacion_de_datos"]
}
```

### Análisis de Hablantes
```json
{
  "success": true,
  "task_uuid": "075bcc8c-8fe5-11f0-b36d-0242ac110007",
  "analysis": {
    "SPEAKER_00": "Agente de soporte técnico, profesional y empático.",
    "SPEAKER_01": "Cliente interesado en actualizar su plan."
  }
}
```

## 🔥 Tips

- Usa **environments** de Postman para不同的 entornos (dev, staging, prod)
- Activa **"Automatically follow redirects"** en Settings
- Usa **tests** en Postman para automatizar validaciones
- Guarda **ejemplos de respuesta** para documentación

## ❌ Errores Comunes

### 401 Unauthorized
- Verifica que `api_key` sea correcta
- La API Key debe ser de tipo "Global API Key"

### 404 Not Found
- El `task_uuid` no existe
- La tarea no tiene transcripción

### 400 Bad Request
- La tarea no tiene campaña asignada
- No hay criterios de auditoría para la campaña
- La transcripción está vacía

## 📖 Documentación Adicional

- [API Documentation](http://localhost:8001/docs) - Swagger UI
- [README](../README.md) - Documentación general
