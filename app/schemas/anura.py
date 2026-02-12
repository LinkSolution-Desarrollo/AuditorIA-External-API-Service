"""
Pydantic schemas for Anura webhooks.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Any
from datetime import datetime


class AnuraWebhookPayload(BaseModel):
    """
    Schema for Anura webhook payloads.
    Matches the variables documented in:
    https://kb.anura.com.ar/es/articles/2579414-variables-eventos-templetizados
    """
    # Hook/Event metadata
    hooktrigger: str = Field(..., description="Trigger event: START, TALK, END")
    hookid: Optional[int] = None
    hookname: Optional[str] = None
    hookdirection: Optional[str] = None
    hooktemplateid: Optional[int] = None
    hooktemplatename: Optional[str] = None
    hooktags: Optional[str] = None

    # Call metadata
    cdrid: str = Field(..., description="Unique call ID")
    dialtime: str = Field(..., description="Call start datetime")
    direction: str = Field(..., description="Direction: inbound/outbound")
    calling: Optional[str] = Field(None, description="Origin phone number")
    callingname: Optional[str] = None
    called: Optional[str] = Field(None, description="Destination phone number")
    calledname: Optional[str] = None
    status: Optional[str] = None

    # Duration and pricing
    duration: Optional[int] = Field(None, description="Total duration in seconds")
    billseconds: Optional[int] = None
    price: Optional[float] = None

    # Recording
    wasrecorded: Optional[bool] = Field(None, description="Whether call was recorded")
    audio_play_mp3: Optional[str] = Field(None, description="URL to play recording (MP3)")
    audio_play_ogg: Optional[str] = None
    audio_play_wav: Optional[str] = None
    audio_file_mp3: Optional[str] = Field(None, description="URL to download recording (MP3)")
    audio_file_ogg: Optional[str] = None
    audio_file_wav: Optional[str] = None

    # Queue/Agent information
    queuename: Optional[str] = None
    queuestatus: Optional[str] = None
    queuetotaltime: Optional[int] = None
    queuetalktime: Optional[int] = None
    queuewaittime: Optional[int] = None
    queueagentname: Optional[str] = Field(None, description="Agent name")
    queueagentextension: Optional[str] = Field(None, description="Agent extension")
    queueagenttags: Optional[str] = None
    answeraccount: Optional[str] = None
    answerterminal: Optional[str] = None
    answerextension: Optional[str] = None

    # Account/Tenant information
    tenantid: Optional[int] = None
    accountid: Optional[int] = None
    accountname: Optional[str] = None
    accountextension: Optional[str] = None
    accounttags: Optional[str] = Field(None, description="Campaign/tags for mapping")

    # Click2Call custom variables
    custom1: Optional[str] = None
    custom2: Optional[str] = None
    custom3: Optional[str] = None

    # Terminal info
    terminalid: Optional[int] = None
    terminalname: Optional[str] = None
    terminalaccount: Optional[str] = None
    terminalstate: Optional[str] = None

    # Additional fields
    lastaction: Optional[str] = None

    @validator('hooktrigger')
    def validate_trigger(cls, v):
        """Validate that trigger is a known event type."""
        valid_triggers = {'START', 'TALK', 'END'}
        if v.upper() not in valid_triggers:
            raise ValueError(f"Invalid trigger: {v}. Must be one of {valid_triggers}")
        return v.upper()

    @validator('dialtime')
    def parse_dialtime(cls, v):
        """Validate dialtime format."""
        try:
            # Try to parse datetime
            datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
            return v
        except ValueError:
            # Try alternative formats
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"]:
                try:
                    datetime.strptime(v, fmt)
                    return v
                except ValueError:
                    continue
            raise ValueError(f"Invalid datetime format: {v}")

    class Config:
        extra = "allow"  # Allow extra fields from Anura


class AnuraWebhookResponse(BaseModel):
    """Response schema for Anura webhook."""
    success: bool
    message: str
    call_id: Optional[str] = None
    task_id: Optional[str] = None
    recording_downloaded: bool = False
