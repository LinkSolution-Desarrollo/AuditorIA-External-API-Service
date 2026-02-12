from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.routers import (
    upload_router, tasks_router, chat_router, campaigns_router,
    webhooks_router, anura_helpers_router, test_utils_router,
    audit_router, tags_router, speaker_analysis_router,
    agent_identification_router, reports_router
)
from app.core.config import get_settings
from app.core.limiter import limiter

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="API Service for external users to upload files.",
    version="1.0.0"
)

# Rate Limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS configuration
origins = settings.CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(tasks_router)
app.include_router(chat_router)
app.include_router(campaigns_router)
app.include_router(webhooks_router)
app.include_router(anura_helpers_router)
app.include_router(audit_router)
app.include_router(tags_router)
app.include_router(speaker_analysis_router)
app.include_router(agent_identification_router)
app.include_router(reports_router)

# Only include test endpoints in DEBUG mode
if settings.DEBUG:
    app.include_router(test_utils_router)

@app.get("/")
@limiter.limit("5/minute")
def read_root(request: Request):
    return {"message": f"{settings.APP_NAME} is running."}
