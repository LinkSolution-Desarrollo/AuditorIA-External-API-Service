from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, Index
from .task import Base


class AIUsageEvent(Base):
    """
    AI usage events — tracks token consumption and audio minutes per AI operation.
    """
    __tablename__ = "ai_usage_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, nullable=True, index=True)
    task_uuid = Column(String(36), nullable=True, index=True)
    event_type = Column(String(50), nullable=True)            # call_audit | chat | tags | etc.

    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)

    # Audio minutes associated with this operation (from task.audio_duration / 60)
    audio_minutes_processed = Column(
        Float, nullable=True,
        comment="Audio minutes associated with this AI operation (from task.audio_duration/60)"
    )

    model_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_ai_usage_campaign_created", "campaign_id", "created_at"),
    )
