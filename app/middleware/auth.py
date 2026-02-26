from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import GlobalApiKey

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


class ApiKeyData:
    """Simple data class to hold API key information without SQLAlchemy session dependency."""
    def __init__(self, id: int, name: str, prefix: str, is_active: bool,
                 created_at: datetime, last_used_at: Optional[datetime]):
        self.id = id
        self.name = name
        self.prefix = prefix
        self.is_active = is_active
        self.created_at = created_at
        self.last_used_at = last_used_at


def _load_key_by_id(key_id: int) -> ApiKeyData:
    """Carga un API key desde la DB por ID y actualiza last_used_at."""
    db: Session = SessionLocal()
    try:
        key_record = db.query(GlobalApiKey).filter(
            GlobalApiKey.id == key_id,
            GlobalApiKey.is_active == True,
        ).first()
        if not key_record:
            raise HTTPException(status_code=401, detail="Invalid token")

        key_record.last_used_at = datetime.utcnow()
        db.commit()

        return ApiKeyData(
            id=key_record.id,
            name=key_record.name,
            prefix=key_record.prefix,
            is_active=key_record.is_active,
            created_at=key_record.created_at,
            last_used_at=key_record.last_used_at,
        )
    finally:
        db.close()


def _settings_auth_header(issuer: str) -> dict:
    return {"WWW-Authenticate": f'Bearer realm="{issuer}", resource_metadata="{issuer}/.well-known/oauth-authorization-server"'}


async def get_api_key(
    api_key: Optional[str] = Security(api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> ApiKeyData:
    settings = get_settings()

    # 1. Intentar Bearer JWT (emitido por /oauth/token)
    if bearer and bearer.credentials:
        try:
            payload = jwt.decode(
                bearer.credentials,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_aud": False},
            )
            key_id = int(payload["sub"])
            return _load_key_by_id(key_id)
        except (JWTError, ValueError, KeyError):
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token",
                headers=_settings_auth_header(settings.OAUTH_ISSUER),
            )

    # 2. Fallback: X-API-Key header (compatibilidad hacia atrás)
    if api_key:
        import hashlib
        hashed_key = hashlib.sha256(api_key.encode()).hexdigest()
        db: Session = SessionLocal()
        try:
            key_record = db.query(GlobalApiKey).filter(
                GlobalApiKey.hashed_key == hashed_key,
                GlobalApiKey.is_active == True,
            ).first()

            if not key_record:
                raise HTTPException(status_code=403, detail="Invalid API Key")

            key_id = key_record.id
            key_name = key_record.name
            key_prefix = key_record.prefix
            key_is_active = key_record.is_active
            key_created_at = key_record.created_at

            key_record.last_used_at = datetime.utcnow()
            key_last_used = key_record.last_used_at
            db.commit()

            return ApiKeyData(
                id=key_id,
                name=key_name,
                prefix=key_prefix,
                is_active=key_is_active,
                created_at=key_created_at,
                last_used_at=key_last_used,
            )
        finally:
            db.close()

    # 3. Sin credenciales → 401 con WWW-Authenticate para trigger OAuth
    raise HTTPException(
        status_code=401,
        detail="Authentication required",
        headers=_settings_auth_header(settings.OAUTH_ISSUER),
    )
