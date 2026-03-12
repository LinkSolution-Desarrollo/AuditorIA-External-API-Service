"""
Additional endpoints for net2phone integration helpers.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.limiter import limiter
from app.middleware.auth import get_api_key
from app.models import Campaign, GlobalApiKey, CallLog, Task
from datetime import datetime, timedelta

router = APIRouter(
    prefix="/net2phone",
    tags=["Net2phone Integration"],
)


@router.get("/campaigns")
@limiter.limit("20/minute")
async def get_campaigns(
    request: Request,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    """
    List all available campaigns for mapping.
    
    Since net2phone uses user.account_id for campaign mapping,
    this endpoint helps identify which account_id maps to which campaign.
    """
    campaigns = db.query(Campaign).all()
    
    return {
        "total": len(campaigns),
        "campaigns": [
            {
                "campaign_id": c.campaign_id,
                "name": c.name,
                "net2phone_mapping": "Use user.account_id as campaign_id"
            }
            for c in campaigns
        ]
    }


@router.get("/mapping-guide")
@limiter.limit("10/minute")
async def get_mapping_guide(request: Request):
    """
    Get complete guide for mapping net2phone data to AuditorIA.
    """
    return {
        "campaign_mapping": {
            "method": "NET2PHONE_DEFAULT_CAMPAIGN_ID",
            "description": "Always uses NET2PHONE_DEFAULT_CAMPAIGN_ID env variable",
            "example": {
                "env_variable": "NET2PHONE_DEFAULT_CAMPAIGN_ID=1"
            },
            "maps_to": "campaign_id: 1"
        },
        "operator_mapping": {
            "method": "user.account_id",
            "description": "net2phone uses user.account_id to identify operators/agents",
            "example": {
                "user": {
                    "id": 1,
                    "account_id": 42,
                    "name": "Jane Doe"
                },
                "maps_to": "operator_id: 42"
            }
        },
        "example_webhook": {
            "event": "call_completed",
            "call_id": "a471d33e562b535b9ec530e1c0c3a5b2",
            "timestamp": "2021-10-27T08:58:21.66Z",
            "duration": 120,
            "direction": "inbound",
            "originating_number": "+5491167950079",
            "dialed_number": "+5491126888209",
            "user": {
                "id": 1,
                "name": "Jane Doe",
                "account_id": 42
            },
            "recording_url": "https://net2phone.com/recordings/call_12345.mp3"
        },
        "supported_events": [
            "call_completed",
            "call_answered",
            "call_ringing",
            "call_missed",
            "call_recorded"
        ]
    }


class ValidateMappingRequest(BaseModel):
    user_id: Optional[int] = None
    account_id: Optional[int] = None


@router.post("/validate-mapping")
@limiter.limit("20/minute")
async def validate_mapping(
    request: Request,
    payload: ValidateMappingRequest,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    """
    Validate if net2phone user data will map correctly.
    
    Request:
    {
      "user_id": 1,
      "account_id": 42
    }
    """
    user_id = payload.user_id
    account_id = payload.account_id
    
    result = {
        "valid": True,
        "mapping": {}
    }
    
    # Validate campaign
    if account_id:
        campaign = db.query(Campaign).filter(
            Campaign.campaign_id == account_id
        ).first()
        
        result['mapping']['campaign'] = {
            "extracted_id": account_id,
            "exists": campaign is not None,
            "campaign_name": campaign.name if campaign else None
        }
        
        if not campaign:
            result['valid'] = False
    
    # Validate operator
    if user_id:
        result['mapping']['operator'] = {
            "extracted_id": user_id,
            "valid": True
        }
    
    return result


@router.get("/stats")
@limiter.limit("20/minute")
async def get_integration_stats(
    request: Request,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    """
    Get statistics about net2phone integration activity.
    """
    yesterday = datetime.utcnow() - timedelta(days=1)
    
    # Total webhooks received - SQL COUNT
    total_webhooks = db.query(func.count(CallLog.file_name)).filter(
        CallLog.upload_by.like('net2phone%')
    ).scalar()
    
    # Total recordings downloaded - SQL COUNT with file_name filter
    total_recordings = db.query(func.count(CallLog.file_name)).filter(
        CallLog.upload_by.like('net2phone%'),
        CallLog.file_name.isnot(None)
    ).scalar()
    
    # Recent webhooks (last 24h) - SQL COUNT with date filter
    recent_webhooks = db.query(func.count(CallLog.file_name)).filter(
        CallLog.upload_by.like('net2phone%'),
        CallLog.created_at > yesterday
    ).scalar()
    
    # Recent recordings (last 24h) - SQL COUNT with date and file_name filters
    recent_recordings = db.query(func.count(CallLog.file_name)).filter(
        CallLog.upload_by.like('net2phone%'),
        CallLog.file_name.isnot(None),
        CallLog.created_at > yesterday
    ).scalar()
    
    # Total tasks created by net2phone - SQL COUNT with JSON filter
    # Using text() for JSON path extraction for cross-database compatibility
    total_tasks = db.query(func.count(Task.id)).filter(
        Task.task_params.isnot(None),
        text("json_extract(task_params, '$.username') LIKE 'net2phone%'")
    ).scalar()
    
    return {
        "total_webhooks_received": total_webhooks or 0,
        "total_recordings_downloaded": total_recordings or 0,
        "total_tasks_created": total_tasks or 0,
        "recent_activity_24h": {
            "webhooks": recent_webhooks or 0,
            "recordings": recent_recordings or 0
        }
    }
