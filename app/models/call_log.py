from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, Float
from .task import Base


class CallLog(Base):
    """
    CallLogs table - stores metadata for each audio file uploaded.
    """
    __tablename__ = "call_logs"

    file_name = Column(String(255), primary_key=True)
    date = Column(DateTime)
    campaign_id = Column(Integer, index=True)
    call_id = Column(String(255))
    ani_tel = Column(String(50))
    operator_id = Column(Integer, index=True)
    ctot = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)
    url = Column(String(255))
    log = Column(Text)
    upload_by = Column(String(255))
