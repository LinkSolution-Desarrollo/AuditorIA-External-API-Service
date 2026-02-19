"""
Schemas for audit generation endpoints.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class AuditRequest(BaseModel):
    """Request to generate an audit for a call or chat."""
    task_uuid: str = Field(..., description="UUID of the task or chat to audit")
    is_call: bool = Field(..., description="True for call, False for chat")

    class Config:
        json_schema_extra = {
            "example": {
                "task_uuid": "075bcc8c-8fe5-11f0-b36d-0242ac110007",
                "is_call": True
            }
        }


class AuditItem(BaseModel):
    """Single audit criterion result."""
    id: Optional[int] = None
    criterion: str
    target_score: float
    score: float
    observations: Optional[str] = None


class AuditResponse(BaseModel):
    """Response from audit generation."""
    success: bool
    task_uuid: str
    campaign_id: Optional[int] = None
    user_id: Optional[str] = None
    score: Optional[float] = None
    is_audit_failure: Optional[bool] = None
    audit: Optional[List[AuditItem]] = None
    generated_by_user: Optional[str] = None
    message: Optional[str] = None
    code: Optional[str] = None
