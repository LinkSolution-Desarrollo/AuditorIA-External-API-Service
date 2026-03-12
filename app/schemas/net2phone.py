"""
Pydantic schemas for net2phone webhooks.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Union
from datetime import datetime


class Net2PhoneWebhookUser(BaseModel):
    """User information in webhook."""
    id: int = Field(..., description="User ID")
    name: str = Field(..., description="User full name")
    account_id: int = Field(..., description="Account ID", ge=1)
    email: Optional[str] = None


class Net2PhoneWebhookPayload(BaseModel):
    """
    Schema for net2phone webhook payloads.
    Events: call_completed, call_answered, call_ringing, call_missed, call_recorded
    """
    # Event metadata
    event: str = Field(..., description="Event type: call_completed, call_answered, etc")
    id: str = Field(..., description="Webhook event ID")
    timestamp: datetime = Field(..., description="Event timestamp (ISO 8601)")
    
    # Call metadata
    call_id: str = Field(..., description="Unique call ID")
    duration: Optional[int] = Field(None, description="Call duration in seconds", ge=0)
    direction: str = Field(..., description="Direction: inbound or outbound")
    originating_number: Optional[Union[str, int]] = Field(None, description="Originating phone number")
    dialed_number: Optional[Union[str, int]] = Field(None, description="Dialed phone number")
    call_source: Optional[str] = Field(None, description="Call source: normal, click2call")
    
    # User/Agent information
    user: Optional[Net2PhoneWebhookUser] = Field(None, description="User who handled the call")
    user_name: Optional[str] = Field(None, description="User name (deprecated, use user.name)")
    
    # Recording (if available)
    recording_url: Optional[str] = Field(None, description="URL to download recording")
    voice_mail: Optional[bool] = Field(None, description="True if voicemail recorded")
    
    # Click to Call (if applicable)
    click_to_call_info: Optional[dict] = Field(None, description="Click to call info")
    
    @validator('event')
    def validate_event(cls, v):
        """Validate that event is a known type."""
        valid_events = {
            'call_completed', 'call_answered', 'call_ringing', 
            'call_missed', 'call_recorded'
        }
        if v not in valid_events:
            raise ValueError(f"Invalid event: {v}. Must be one of {valid_events}")
        return v
    
    @validator('direction')
    def validate_direction(cls, v):
        """Validate direction."""
        valid_directions = {'inbound', 'outbound'}
        if v.lower() not in valid_directions:
            raise ValueError(f"Invalid direction: {v}. Must be one of {valid_directions}")
        return v.lower()
    
    @validator('originating_number', 'dialed_number', pre=True)
    def convert_phone_to_string(cls, v):
        """Convert phone numbers to strings."""
        if v is None:
            return None
        return str(v)
    
    class Config:
        extra = "allow"  # Allow extra fields from net2phone


class Net2PhoneWebhookResponse(BaseModel):
    """Response schema for net2phone webhook."""
    success: bool
    message: str
    call_id: Optional[str] = None
    task_id: Optional[str] = None
    recording_downloaded: bool = False
    event_type: Optional[str] = None
