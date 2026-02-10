from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from .task import Base


class CallLog(Base):
    """
    CallLogs table - stores metadata for each audio file uploaded.
    """
    __tablename__ = "call_logs"

    file_name = Column(String(255), primary_key=True)
    date = Column(DateTime, index=True)
    campaign_id = Column(Integer, index=True, nullable=False)
    call_id = Column(String(36), index=True)
    ani_tel = Column(String(30))
    operator_id = Column(Integer, index=True, nullable=False)
    direction = Column(String(50))
    call_start_date = Column(DateTime)
    call_end_date = Column(DateTime)
    sectot = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    url = Column(String(500))
    log = Column(String(5000))
    upload_by = Column(String(255), index=True)
