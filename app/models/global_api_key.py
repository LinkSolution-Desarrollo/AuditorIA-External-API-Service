from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from .task import Base
import hashlib
import secrets

class GlobalApiKey(Base):
    __tablename__ = "global_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)  # User-friendly name
    hashed_key = Column(String, unique=True, index=True, nullable=False)
    prefix = Column(String, nullable=False) # To show the user part of the key
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    @staticmethod
    def verify_key(plain_key: str, hashed_key: str) -> bool:
        """Verifies if a plain key matches the hash."""
        return hashlib.sha256(plain_key.encode()).hexdigest() == hashed_key
