from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, Text
from .task import Base


class BillingSubscription(Base):
    """
    Billing subscription — Stripe subscription data (single-tenant for now).
    """
    __tablename__ = "billing_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Stripe IDs (nullable for manual/trial subscriptions)
    stripe_customer_id = Column(
        String(100), nullable=True, unique=True, index=True
    )
    stripe_subscription_id = Column(
        String(100), nullable=True, unique=True, index=True
    )
    stripe_price_id = Column(String(100), nullable=True)
    stripe_product_id = Column(String(100), nullable=True)

    # Plan info
    plan_name = Column(String(50), default="custom")          # starter|growth|enterprise|custom
    plan_display_name = Column(String(100), nullable=True)

    # Plan quotas
    included_audio_minutes = Column(Float, nullable=True)
    overage_rate_usd_per_minute = Column(Float, nullable=True)

    # Stripe status
    status = Column(String(20), default="active")             # active|trialing|past_due|cancelled|incomplete
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)

    metadata_json = Column(Text, nullable=True)               # Free JSON for internal notes
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
