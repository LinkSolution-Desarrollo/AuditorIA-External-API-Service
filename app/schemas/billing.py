"""
Schemas for billing usage and campaign limits endpoints.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal


class CampaignLimitUpdate(BaseModel):
    """Body for PUT /billing-usage/campaign-limits/{campaign_id}"""
    monthly_audio_minutes_limit: Optional[float] = Field(
        None, description="Monthly audio minutes limit (null = unlimited)"
    )
    monthly_token_limit: Optional[int] = Field(
        None, description="Monthly token limit (null = unlimited)"
    )
    monthly_usd_limit: Optional[float] = Field(
        None, description="Monthly USD limit in dollars (null = unlimited)"
    )
    enforcement_mode: Literal["soft", "hard"] = Field(
        "soft", description="soft: alert only | hard: block when exceeded"
    )
    alert_threshold_pct: int = Field(
        80, ge=0, le=100, description="Alert threshold percentage (0-100)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "monthly_audio_minutes_limit": 500.0,
                "monthly_token_limit": None,
                "monthly_usd_limit": 50.0,
                "enforcement_mode": "soft",
                "alert_threshold_pct": 80,
            }
        }


class StripeCheckoutRequest(BaseModel):
    """Body for POST /billing/stripe/checkout"""
    price_id: str = Field(..., description="Stripe Price ID")
    plan_name: str = Field(..., description="Plan name (starter|growth|enterprise)")
    success_url: str = Field(..., description="Redirect URL on successful payment")
    cancel_url: str = Field(..., description="Redirect URL when payment is cancelled")


class StripePortalRequest(BaseModel):
    """Body for POST /billing/stripe/customer-portal"""
    return_url: str = Field(..., description="Redirect URL after portal session")
