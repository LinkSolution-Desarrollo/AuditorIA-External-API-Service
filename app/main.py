from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import AuthConfig, FastApiMCP
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.routers import (
    oauth_router,
    upload_router, tasks_router, chat_router, campaigns_router,
    webhooks_router, anura_helpers_router, test_utils_router,
    tags_router, speaker_analysis_router, agent_identification_router,
    audit_router, reports_router,
)
from app.core.config import get_settings
from app.core.limiter import limiter
from app.middleware.auth import get_api_key

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="API Service for external users to upload files.",
    version="1.0.0"
)

# Rate Limiting — middleware omitido intencionalmente: SlowAPIMiddleware y
# SlowAPIASGIMiddleware rompen SSE (MCP). Los decoradores @limiter.limit() en
# cada endpoint siguen activos; las excepciones las captura el handler de abajo.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
origins = settings.CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth 2.0 endpoints — sin auth dependency
app.include_router(oauth_router)

app.include_router(upload_router)
app.include_router(tasks_router)
app.include_router(chat_router)
app.include_router(campaigns_router)
app.include_router(webhooks_router)
app.include_router(anura_helpers_router)
app.include_router(tags_router)
app.include_router(speaker_analysis_router)
app.include_router(agent_identification_router)
app.include_router(audit_router)
app.include_router(reports_router)

# Only include test endpoints in DEBUG mode
if settings.DEBUG:
    app.include_router(test_utils_router)

@app.get("/")
@limiter.limit("5/minute")
def read_root(request: Request):
    return {"message": f"{settings.APP_NAME} is running."}


@app.get("/health")
def health():
    return {"status": "ok"}


# MCP server - expone todos los endpoints como herramientas MCP en /mcp
# Auth: requiere Bearer JWT (via OAuth) o X-API-Key para acceder al endpoint /mcp.
# El header authorization se forwardea automáticamente a cada tool call.
# Excluimos el endpoint binario (POST /upload) — usar upload_audio_from_url en su lugar.
mcp = FastApiMCP(
    app,
    auth_config=AuthConfig(
        dependencies=[Depends(get_api_key)],
    ),
    headers=["authorization", "x-api-key"],
    exclude_operations=["upload_file_upload_post"],
)
mcp.mount()
