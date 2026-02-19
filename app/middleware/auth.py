from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
import hashlib
from datetime import datetime
from typing import Optional

from app.core.database import SessionLocal
from app.models import GlobalApiKey

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

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

async def get_api_key(api_key: str = Security(api_key_header)) -> ApiKeyData:
    if not api_key:
        raise HTTPException(status_code=403, detail="Could not validate credentials")

    # Hash the key
    hashed_key = hashlib.sha256(api_key.encode()).hexdigest()

    db: Session = SessionLocal()
    try:
        key_record = db.query(GlobalApiKey).filter(
            GlobalApiKey.hashed_key == hashed_key,
            GlobalApiKey.is_active == True
        ).first()

        if not key_record:
            raise HTTPException(status_code=403, detail="Invalid API Key")

        # Store values BEFORE updating (in case of lazy loading issues)
        key_id = key_record.id
        key_name = key_record.name
        key_prefix = key_record.prefix
        key_is_active = key_record.is_active
        key_created_at = key_record.created_at

        # Update last used
        key_record.last_used_at = datetime.utcnow()
        key_last_used = key_record.last_used_at
        db.commit()

        # Return a simple data object (no SQLAlchemy dependencies)
        return ApiKeyData(
            id=key_id,
            name=key_name,
            prefix=key_prefix,
            is_active=key_is_active,
            created_at=key_created_at,
            last_used_at=key_last_used
        )
    finally:
        db.close()
