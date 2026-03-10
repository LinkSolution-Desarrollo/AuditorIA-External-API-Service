"""
Additional endpoints for net2phone integration helpers.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

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
            "method": "user.account_id",
            "description": "net2phone uses user.account_id to identify campaigns",
            "example": {
                "user": {
                    "id": 1,
                    "account_id": 42,
                    "name": "Jane Doe"
                },
                "maps_to": "campaign_id: 42"
            },
            "fallback": "NET2PHONE_DEFAULT_CAMPAIGN_ID env variable"
        },
        "operator_mapping": {
            "method": "user.id",
            "description": "net2phone uses user.id to identify operators/agents",
            "example": {
                "user": {
                    "id": 1,
                    "name": "Jane Doe"
                },
                "maps_to": "operator_id: 1"
            },
            "fallback": "NET2PHONE_DEFAULT_OPERATOR_ID env variable"
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


@router.post("/validate-mapping")
@limiter.limit("20/minute")
async def validate_mapping(
    request: Request,
    payload: dict,
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
    user_id = payload.get('user_id')
    account_id = payload.get('account_id')
    
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
    # Get call logs uploaded by net2phone
    net2phone_logs = db.query(CallLog).filter(
        CallLog.upload_by.like('net2phone%')
    ).all()
    
    # Get tasks created from net2phone webhooks
    net2phone_tasks = db.query(Task).filter(
        Task.task_params.isnot(None)
    ).all()
    
    # Filter tasks created by net2phone
    net2phone_tasks = [t for t in net2phone_tasks if t.task_params and t.task_params.get('username', '').startswith('net2phone')]
    
    # Recent activity (last 24h)
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_logs = [log for log in net2phone_logs if log.created_at and log.created_at > yesterday]
    
    return {
        "total_webhooks_received": len(net2phone_logs),
        "total_recordings_downloaded": len([log for log in net2phone_logs if log.file_name]),
        "total_tasks_created": len(net2phone_tasks),
        "recent_activity_24h": {
            "webhooks": len(recent_logs),
            "recordings": len([log for log in recent_logs if log.file_name])
        }
    }
