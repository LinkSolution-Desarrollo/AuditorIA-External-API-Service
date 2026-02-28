from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .task import Base


class CampaignBillingLimit(Base):
    """
    Billing limits per campaign — monthly audio minutes, tokens, and USD caps.
    """
    __tablename__ = "campaign_billing_limits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(
        Integer,
        ForeignKey("campaigns.campaign_id"),
        unique=True,
        index=True,
        nullable=False,
    )

    # Primary limit: audio minutes per month (None = unlimited)
    monthly_audio_minutes_limit = Column(
        Float, nullable=True,
        comment="Monthly audio minutes limit (None = unlimited)"
    )

    # Secondary limits (optional)
    monthly_token_limit = Column(
        Integer, nullable=True,
        comment="Monthly token limit (None = unlimited)"
    )
    monthly_usd_limit = Column(
        Float, nullable=True,
        comment="Monthly USD limit (None = unlimited)"
    )

    # Enforcement: soft = alert only | hard = block when exceeded
    enforcement_mode = Column(
        String(10), default="soft", server_default="soft",
        comment="soft: alert only, hard: block when exceeded"
    )
    alert_threshold_pct = Column(
        Integer, default=80, server_default="80",
        comment="Alert threshold percentage (0-100)"
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="billing_limit")
