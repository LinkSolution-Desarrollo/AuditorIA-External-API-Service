from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
import hashlib
from datetime import datetime

from app.core.database import SessionLocal
from app.models import GlobalApiKey

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
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
        
        # Update last used
        key_record.last_used_at = datetime.utcnow()
        db.commit()
        
        return key_record
    finally:
        db.close()
