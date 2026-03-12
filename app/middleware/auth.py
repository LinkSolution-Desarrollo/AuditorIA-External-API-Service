from datetime import datetime
from typing import Optional

from argon2 import PasswordHasher
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


def _load_key_by_raw_value(raw_key: str) -> Optional[ApiKeyData]:
    """Carga un API key desde la DB por su valor crudo (hashing) y actualiza last_used_at."""
    ph = PasswordHasher()
    db: Session = SessionLocal()
    try:
        key_records = db.query(GlobalApiKey).filter(
            GlobalApiKey.is_active == True,
        ).all()

        for key_record in key_records:
            try:
                if ph.verify(key_record.hashed_key, raw_key):
                    key_record.last_used_at = datetime.utcnow()
                    data = ApiKeyData(
                        id=key_record.id,
                        name=key_record.name,
                        prefix=key_record.prefix,
                        is_active=key_record.is_active,
                        created_at=key_record.created_at,
                        last_used_at=key_record.last_used_at,
                    )
                    db.commit()
                    return data
            except Exception:
                continue

        return None
    finally:
        db.close()


def _settings_auth_header(issuer: str) -> dict:
    return {"WWW-Authenticate": f'Bearer realm="{issuer}", resource_metadata="{issuer}/.well-known/oauth-authorization-server"'}


async def get_api_key(
    api_key: Optional[str] = Security(api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> ApiKeyData:
    settings = get_settings()

    # 1. Intentar Bearer token (JWT o API Key)
    if bearer and bearer.credentials:
        # 1a. Intentar como JWT (emitido por /oauth/token)
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
            # 1b. Fallback: Intentar como Global API Key cruda (enviada en header Authorization)
            key_data = _load_key_by_raw_value(bearer.credentials)
            if key_data:
                return key_data
            
            # Si no es ni JWT ni API Key válida
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token",
                headers=_settings_auth_header(settings.OAUTH_ISSUER),
            )

    # 2. Fallback: X-API-Key header (compatibilidad hacia atrás)
    if api_key:
        key_data = _load_key_by_raw_value(api_key)
        if key_data:
            return key_data
        
        raise HTTPException(status_code=403, detail="Invalid API Key")

    # 3. Sin credenciales → 401 con WWW-Authenticate para trigger OAuth
    raise HTTPException(
        status_code=401,
        detail="Authentication required",
        headers=_settings_auth_header(settings.OAUTH_ISSUER),
    )
