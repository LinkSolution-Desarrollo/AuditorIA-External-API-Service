"""Pydantic schemas for Anura webhooks."""
import uuid
from datetime import datetime
from typing import Optional, Any, Dict

from pydantic import BaseModel, Field, validator

from app.utils.datetime_utils import parse_anura_datetime


class AnuraWebhookPayload(BaseModel):
    """Schema for Anura webhook payloads."""
    hooktrigger: str = Field("END", description="Trigger event: START, TALK, END")
    hookid: Optional[int] = None
    hookname: Optional[str] = None
    hookdirection: Optional[str] = None
    hooktemplateid: Optional[int] = None
    hooktemplatename: Optional[str] = None
    hooktags: Optional[str] = None

    cdrid: str = Field(default_factory=lambda: uuid.uuid4().hex, description="Unique call ID")
    dialtime: str = Field(
        default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        description="Call start datetime",
    )
    direction: str = Field("inbound", description="Direction: inbound/outbound")
    calling: Optional[str] = Field(None, description="Origin phone number")
    callingname: Optional[str] = None
    called: Optional[str] = Field(None, description="Destination phone number")
    calledname: Optional[str] = None
    status: Optional[str] = None

    duration: Optional[int] = Field(None, description="Total duration in seconds")
    billseconds: Optional[int] = None
    price: Optional[float] = None

    wasrecorded: bool = Field(False, description="Whether call was recorded")
    audio_play_mp3: Optional[str] = Field(None, description="URL to play recording (MP3)")
    audio_play_ogg: Optional[str] = None
    audio_play_wav: Optional[str] = None
    audio_file_mp3: Optional[str] = Field(None, description="URL to download recording (MP3)")
    audio_file_ogg: Optional[str] = None
    audio_file_wav: Optional[str] = None

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

    tenantid: Optional[int] = None
    accountid: Optional[int] = None
    accountname: Optional[str] = None
    accountextension: Optional[str] = None
    accounttags: Optional[str] = Field(None, description="Campaign/tags for mapping")

    custom1: Optional[str] = None
    custom2: Optional[str] = None
    custom3: Optional[str] = None

    terminalid: Optional[int] = None
    terminalname: Optional[str] = None
    terminalaccount: Optional[str] = None
    terminalstate: Optional[str] = None

    lastaction: Optional[str] = None

    @validator("hooktrigger")
    def validate_trigger(cls, v: str) -> str:
        valid = {"START", "TALK", "END"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid trigger: {v}. Must be one of {valid}")
        return v.upper()

    @validator("dialtime")
    def parse_dialtime(cls, v: str) -> str:
        dt = parse_anura_datetime(v)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    class Config:
        extra = "allow"


class AnuraWebhookResponse(BaseModel):
    success: bool
    message: str
    call_id: Optional[str] = None
    task_id: Optional[str] = None
    recording_downloaded: bool = False
    payload: Optional[Dict[str, Any]] = None
    call_event: Optional[Dict[str, Any]] = None
