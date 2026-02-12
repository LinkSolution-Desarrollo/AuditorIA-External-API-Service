"""
Additional endpoints for Anura integration helpers.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.limiter import limiter
from app.middleware.auth import get_api_key
from app.models import Campaign, GlobalApiKey
from app.schemas.anura import AnuraWebhookResponse

router = APIRouter(
    prefix="/anura",
    tags=["Anura Integration"],
)


@router.get("/campaigns")
@limiter.limit("20/minute")
async def list_campaigns(
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    """
    List all available campaigns for mapping Anura accounts.
    
    Use this to find campaign_id values to configure in Anura account tags.
    Example: Tag account with "campaign_123" to map to campaign ID 123.
    """
    campaigns = db.query(Campaign).all()
    
    return {
        "total": len(campaigns),
        "campaigns": [
            {
                "campaign_id": c.campaign_id,
                "name": c.name,
                "description": c.description if hasattr(c, 'description') else None,
                "anura_tag_format": f"campaign_{c.campaign_id}",
                "example_webhook_payload": {
                    "accounttags": f"campaign_{c.campaign_id}",
                    "campaign_id": c.campaign_id
                }
            }
            for c in campaigns
        ]
    }


@router.get("/mapping-guide")
@limiter.limit("10/minute")
async def get_mapping_guide(
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    """
    Get a complete guide for mapping Anura data to AuditorIA.
    
    Returns:
    - Available campaigns with tag format
    - Available operators with extension mapping
    - Example webhook payloads for testing
    """
    campaigns = db.query(Campaign).all()
    
    return {
        "campaign_mapping": {
            "description": "Map Anura accounts to campaigns using account tags",
            "tag_format": "campaign_{campaign_id}",
            "examples": [
                {
                    "campaign_id": c.campaign_id,
                    "campaign_name": c.campaign_name,
                    "anura_account_tag": f"campaign_{c.campaign_id}",
                    "webhook_value": f"campaign_{c.campaign_id}"
                }
                for c in campaigns
            ]
        },
        "operator_mapping": {
            "description": "Map Anura agent extensions to operators",
            "mapping_options": [
                {
                    "option": "Agent Extension (numeric)",
                    "description": "If agent extension is numeric (e.g., '300'), it's used as operator_id",
                    "example": {
                        "queueagentextension": "300",
                        "mapped_to_operator_id": 300
                    }
                },
                {
                    "option": "Agent Name (with number)",
                    "description": "If name contains number (e.g., 'Agent 123'), first number is used",
                    "example": {
                        "queueagentname": "Agent 456 - Sales",
                        "mapped_to_operator_id": 456
                    }
                },
                {
                    "option": "Default Operator",
                    "description": "Set ANURA_DEFAULT_OPERATOR_ID in .env as fallback",
                    "env_variable": "ANURA_DEFAULT_OPERATOR_ID=1"
                }
            ]
        },
        "example_webhook": {
            "hooktrigger": "END",
            "cdrid": "20260210-103045-1234567890",
            "dialtime": "2026-02-10 10:30:45",
            "calling": "+5491167950079",
            "called": "+5491126888209",
            "direction": "inbound",
            "duration": 125,
            "wasrecorded": True,
            "audio_file_mp3": "https://anura.example.com/recordings/12345.mp3",
            "accounttags": f"campaign_{campaigns[0].campaign_id if campaigns else '1'}",
            "queueagentextension": "300"
        }
    }


@router.get("/stats")
@limiter.limit("20/minute")
async def get_integration_stats(
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    """
    Get statistics about Anura integration activity.
    
    Returns:
    - Total webhooks received (from call_logs created by anura_webhook)
    - Recordings downloaded
    - Tasks created
    - Recent activity
    """
    from app.models import CallLog, Task
    from datetime import datetime, timedelta
    
    # Get call logs uploaded by anura
    anura_logs = db.query(CallLog).filter(
        CallLog.upload_by.like('anura%')
    ).all()
    
    # Get tasks created from anura webhooks
    anura_tasks = db.query(Task).filter(
        Task.task_params.isnot(None)
    ).all()
    
    # Filter tasks created by anura (check if username in params)
    anura_tasks = [t for t in anura_tasks if t.task_params and t.task_params.get('username', '').startswith('anura')]
    
    # Recent activity (last 24h)
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_logs = [log for log in anura_logs if log.created_at and log.created_at > yesterday]
    
    return {
        "total_webhooks_received": len(anura_logs),
        "total_recordings_downloaded": len([log for log in anura_logs if log.file_name]),
        "total_tasks_created": len(anura_tasks),
        "recent_activity_24h": {
            "webhooks": len(recent_logs),
            "recordings": len([log for log in recent_logs if log.file_name])
        },
        "latest_webhooks": [
            {
                "call_id": log.call_id,
                "date": log.date.isoformat() if log.date else None,
                "file_name": log.file_name,
                "campaign_id": log.campaign_id,
                "direction": log.direction,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in sorted(anura_logs, key=lambda x: x.created_at or datetime.min, reverse=True)[:10]
        ]
    }


@router.post("/validate-mapping")
@limiter.limit("10/minute")
async def validate_mapping(
    mapping: dict,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    """
    Validate if Anura tags/extensions will map correctly to AuditorIA.
    
    Request body:
    {
        "accounttags": "campaign_1, support_queue",
        "queueagentextension": "300",
        "queueagentname": "Agent 456"
    }
    """
    from app.services.anura_service import extract_campaign_id_from_tags, extract_operator_id_from_agent
    
    accounttags = mapping.get('accounttags')
    queueagentextension = mapping.get('queueagentextension')
    queueagentname = mapping.get('queueagentname')
    
    # Extract campaign_id
    campaign_id = extract_campaign_id_from_tags(accounttags)
    campaign_exists = False
    campaign_name = None
    
    if campaign_id:
        campaign = db.query(Campaign).filter(
            Campaign.campaign_id == campaign_id
        ).first()
        if campaign:
            campaign_exists = True
            campaign_name = campaign.campaign_name
    
    # Extract operator_id
    operator_id = extract_operator_id_from_agent(queueagentextension, queueagentname)
    
    result = {
        "input": {
            "accounttags": accounttags,
            "queueagentextension": queueagentextension,
            "queueagentname": queueagentname
        },
        "mapping": {
            "campaign": {
                "tag": accounttags,
                "extracted_id": campaign_id,
                "exists": campaign_exists,
                "campaign_name": campaign_name,
                "valid": campaign_exists if campaign_id else None
            },
            "operator": {
                "extension": queueagentextension,
                "name": queueagentname,
                "extracted_id": operator_id,
                "valid": operator_id is not None
            }
        },
        "recommendations": []
    }
    
    # Add recommendations
    if not campaign_exists:
        if campaign_id:
            result["recommendations"].append(
                f"Campaign ID {campaign_id} does not exist. Create it or use a different tag."
            )
        else:
            result["recommendations"].append(
                "No campaign ID extracted from tags. Use format 'campaign_123' or set ANURA_DEFAULT_CAMPAIGN_ID"
            )
    
    if not operator_id:
        result["recommendations"].append(
            "No operator ID extracted. Use numeric extension or set ANURA_DEFAULT_OPERATOR_ID"
        )
    
    result["valid"] = (
        (campaign_exists if campaign_id else True) and
        (operator_id is not None)
    )
    
    return result
