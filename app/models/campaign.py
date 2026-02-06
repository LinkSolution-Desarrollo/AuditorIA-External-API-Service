from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from .task import Base


class Campaign(Base):
    """
    Campaigns table - stores campaign information for organizing call logs and tasks.
    """
    __tablename__ = "campaigns"

    campaign_id = Column(
        Integer, 
        primary_key=True, 
        autoincrement=True,
        comment="Unique campaign identifier"
    )
    campaign_name = Column(
        String(255), 
        nullable=False, 
        unique=True,
        index=True,
        comment="Campaign name (unique)"
    )
    description = Column(
        Text,
        nullable=True,
        comment="Campaign description"
    )
    supervisor_emails = Column(
        String,
        nullable=True,
        comment="Comma-separated list of supervisor emails"
    )
    approval_score = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Minimum approval score required"
    )
    created_at = Column(
        DateTime, 
        default=datetime.utcnow, 
        nullable=False,
        comment="Creation timestamp"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Last update timestamp"
    )
