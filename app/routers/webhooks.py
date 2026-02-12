"""
Router for Anura webhook integration.
"""
from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.limiter import limiter
from app.middleware.auth import get_api_key
from app.models import GlobalApiKey
from app.schemas.anura import AnuraWebhookPayload, AnuraWebhookResponse
from app.services.anura_service import process_anura_webhook, AnuraIntegrationError
from app.core.config import get_settings

router = APIRouter(
    prefix="/webhook",
    tags=["Webhooks"],
)

settings = get_settings()


@router.post("/anura/", response_model=AnuraWebhookResponse)
@limiter.limit("30/minute")
async def anura_webhook(
    request: Request,
    payload: AnuraWebhookPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    """
    Receive webhooks from Anura PBX.
    
    This endpoint processes call events from Anura cloud PBX:
    - START: Call initiated
    - TALK: Call answered
    - END: Call ended (downloads recording if available)
    
    Authentication: X-API-Key header (same as upload endpoint)
    
    Expected payload format:
    {
      "hooktrigger": "END",
      "cdrid": "1234567890",
      "dialtime": "2026-02-10 10:30:00",
      "calling": "+5491167950079",
      "called": "+5491126888209",
      "direction": "inbound",
      "duration": 120,
      "wasrecorded": true,
      "audio_file_mp3": "https://anura.com/recordings/12345.mp3",
      "accounttags": "campaign_123",
      "queueagentextension": "300"
    }
    
    For full variable list:
    https://kb.anura.com.ar/es/articles/2579414-variables-eventos-templetizados
    """
    try:
        # Process webhook
        result = process_anura_webhook(
            payload=payload,
            db=db,
            api_key_record=api_key
        )
        
        # Build response
        response = AnuraWebhookResponse(
            success=True,
            message=f"Webhook processed successfully: {payload.hooktrigger}",
            call_id=result['call_id'],
            task_id=result.get('task_id'),
            recording_downloaded=result['recording_downloaded']
        )
        
        # Log any warnings
        if result['errors']:
            response.message += f" (Warnings: {'; '.join(result['errors'])})"
        
        return response
        
    except AnuraIntegrationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Integration error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@router.get("/anura/health")
@limiter.limit("10/minute")
async def anura_webhook_health(request: Request):
    """
    Health check endpoint for Anura webhook.
    Can be used to verify webhook URL is accessible.
    """
    return {
        "status": "ok",
        "service": "AuditorIA Anura Integration",
        "webhook_ready": True
    }


@router.post("/anura/test")
@limiter.limit("5/minute")
async def anura_webhook_test(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    Test endpoint for Anura webhook (for development/testing).
    Does not require authentication.
    """
    try:
        # Validate payload
        validated_payload = AnuraWebhookPayload(**payload)
        
        return {
            "status": "validated",
            "message": "Payload is valid",
            "trigger": validated_payload.hooktrigger,
            "call_id": validated_payload.cdrid,
            "has_recording": validated_payload.wasrecorded,
            "recording_url": validated_payload.audio_file_mp3
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Validation error: {str(e)}"
        )
