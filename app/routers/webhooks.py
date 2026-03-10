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


@router.post("/net2phone/", response_model=Net2PhoneWebhookResponse)
@limiter.limit("30/minute")
async def net2phone_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    """
    Receive webhooks from net2phone.
    
    This endpoint processes call events from net2phone:
    - call_completed: Call ended (downloads recording if available)
    - call_answered: Call answered
    - call_ringing: Call initiated
    - call_missed: Call missed
    - call_recorded: Recording available
    
    Authentication:
    - X-API-Key header (API Key authentication)
    - x-net2phone-signature header (HMAC-SHA256 signature)
    
    Expected payload format:
    {
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
    }
    """
    try:
        # Get raw body for signature verification
        raw_body = await request.body()
        
        # Verify signature if present
        signature = request.headers.get('x-net2phone-signature')
        timestamp = request.headers.get('x-net2phone-timestamp')
        
        if signature and timestamp:
            secret = getattr(settings, 'NET2PHONE_WEBHOOK_SECRET', '')
            
            if secret and not verify_webhook_signature(raw_body, signature, timestamp, secret):
                raise HTTPException(
                    status_code=401,
                    detail="Invalid webhook signature"
                )
        
        # Parse payload
        payload_dict = await request.json()
        payload = Net2PhoneWebhookPayload(**payload_dict)
        
        # Process webhook
        result = process_net2phone_webhook(
            payload=payload,
            db=db,
            api_key_record=api_key
        )
        
        # Build response
        response = Net2PhoneWebhookResponse(
            success=True,
            message=f"Webhook processed successfully: {payload.event}",
            call_id=result['call_id'],
            task_id=result.get('task_id'),
            recording_downloaded=result['recording_downloaded'],
            event_type=payload.event
        )
        
        # Log any warnings
        if result['errors']:
            response.message += f" (Warnings: {'; '.join(result['errors'])})"
        
        return response
        
    except Net2PhoneIntegrationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Integration error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@router.get("/net2phone/health")
@limiter.limit("10/minute")
async def net2phone_webhook_health(request: Request):
    """
    Health check endpoint for net2phone webhook.
    Can be used to verify webhook URL is accessible.
    """
    return {
        "status": "ok",
        "service": "AuditorIA net2phone Integration",
        "webhook_ready": True
    }


@router.post("/net2phone/test")
@limiter.limit("5/minute")
async def net2phone_webhook_test(
    request: Request,
    payload: dict,
):
    """
    Test endpoint for net2phone webhook (for development/testing).
    Does not require authentication.
    """
    try:
        # Validate payload
        validated_payload = Net2PhoneWebhookPayload(**payload)
        
        return {
            "status": "validated",
            "message": "Payload is valid",
            "event": validated_payload.event,
            "call_id": validated_payload.call_id,
            "has_recording": validated_payload.recording_url is not None,
            "recording_url": validated_payload.recording_url
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Validation error: {str(e)}"
        )
