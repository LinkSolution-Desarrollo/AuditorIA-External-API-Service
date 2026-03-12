"""
Router for Anura and net2phone webhook integrations.
"""
import json
import logging
from json import JSONDecodeError
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.limiter import limiter
from app.middleware.auth import get_api_key
from app.models import GlobalApiKey
from app.schemas.anura import AnuraWebhookPayload, AnuraWebhookResponse
from app.schemas.net2phone import Net2PhoneWebhookPayload, Net2PhoneWebhookResponse
from app.services.anura_service import process_anura_webhook, AnuraIntegrationError
from app.services.net2phone_service import process_net2phone_webhook, verify_webhook_signature, Net2PhoneIntegrationError
from app.core.config import get_settings

router = APIRouter(
    prefix="/webhook",
    tags=["Webhooks"],
)

logger = logging.getLogger("uvicorn.error")

INT_FIELDS = {
    "hookid",
    "hooktemplateid",
    "duration",
    "billseconds",
    "queuetotaltime",
    "queuetalktime",
    "queuewaittime",
    "tenantid",
    "accountid",
    "terminalid",
}
FLOAT_FIELDS = {"price"}
BOOL_FIELDS = {"wasrecorded"}
SENSITIVE_FIELDS = {
    "calling",
    "called",
    "callingname",
    "calledname",
    "queueagentname",
    "accountname",
}


def _to_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "si", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _redact_payload_for_logs(payload: Dict[str, Any]) -> Dict[str, Any]:
    redacted: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in SENSITIVE_FIELDS and value is not None:
            redacted[key] = "***REDACTED***"
            continue
        redacted[key] = value
    return redacted


def _coerce_payload_types(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}

    for key, value in payload.items():
        # Webhook form-data may send empty strings for optional values.
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                normalized[key] = None
                continue

        if key in BOOL_FIELDS:
            normalized[key] = _to_bool(value)
            continue

        if key in INT_FIELDS and isinstance(value, str):
            try:
                normalized[key] = int(value)
            except ValueError:
                # Some senders provide decimal strings for integer fields (e.g. "120.0")
                try:
                    normalized[key] = int(float(value))
                except ValueError:
                    normalized[key] = value
            continue

        if key in FLOAT_FIELDS and isinstance(value, str):
            try:
                normalized[key] = float(value)
            except ValueError:
                normalized[key] = value
            continue

        normalized[key] = value

    return normalized


async def _extract_webhook_payload(request: Request) -> Dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()

    if content_type == "application/json":
        try:
            raw_payload = await request.json()
        except JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
        if not isinstance(raw_payload, dict):
            raise HTTPException(status_code=400, detail="JSON payload must be an object")
        return _coerce_payload_types(raw_payload)

    if content_type in {"application/x-www-form-urlencoded", "multipart/form-data"}:
        form_data = await request.form()
        raw_payload = {k: v for k, v in form_data.items()}
        return _coerce_payload_types(raw_payload)

    raise HTTPException(
        status_code=415,
        detail="Unsupported Content-Type. Use application/json, application/x-www-form-urlencoded, or multipart/form-data.",
    )


@router.post("/anura/", response_model=AnuraWebhookResponse)
@limiter.limit("30/minute")
async def anura_webhook(
    request: Request,
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
        payload_dict = await _extract_webhook_payload(request)
        try:
            call_event = CallEvent.from_anura_payload(payload_dict)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": f"Normalización fallida: {str(exc)}",
                    "payload": payload_dict,
                },
            )
        logger.info("Anura webhook raw payload=%s", payload_dict)
        logger.info(
            "Anura webhook payload received content_type=%s payload=%s",
            request.headers.get("content-type"),
            _redact_payload_for_logs(payload_dict),
        )
        logger.info("CallEvent normalized=%s", call_event.dict())

        payload = AnuraWebhookPayload(**payload_dict)

        if payload.hooktrigger != "END":
            return AnuraWebhookResponse(
                success=True,
                message=f"Webhook received (ignored until END): {payload.hooktrigger}",
                call_id=payload.cdrid,
                recording_downloaded=False,
                payload=payload_dict,
                call_event=call_event.dict(),
            )

        # Process webhook
        result = process_anura_webhook(
            payload=payload,
            db=db,
            api_key_record=api_key,
            call_event=call_event,
        )
        
        # Build response
        response = AnuraWebhookResponse(
            success=True,
            message=f"Webhook processed successfully: {payload.hooktrigger}",
            call_id=result['call_id'],
            task_id=result.get('task_id'),
            recording_downloaded=result['recording_downloaded'],
            payload=payload_dict,
            call_event=call_event.dict(),
        )
        
        # Log any warnings
        if result['errors']:
            response.message += f" (Warnings: {'; '.join(result['errors'])})"
        
        return response
        
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": f"Validation error: {str(e)}",
                "payload": payload_dict if 'payload_dict' in locals() else None,
            },
        )
    except AnuraIntegrationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": f"Integration error: {str(e)}",
                "payload": payload_dict if 'payload_dict' in locals() else None,
            },
        )
    except Exception as e:
        logger.exception("Unexpected error while processing Anura webhook")
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
        # Get raw body for signature verification and JSON parsing
        raw_body = await request.body()
        
        # Verify signature if present
        signature = request.headers.get('x-net2phone-signature')
        timestamp = request.headers.get('x-net2phone-timestamp')
        
        if signature and timestamp:
            secret = settings.NET2PHONE_SECRET
            
            if secret and not verify_webhook_signature(raw_body, signature, timestamp, secret):
                raise HTTPException(
                    status_code=401,
                    detail="Invalid webhook signature"
                )
        
        # Parse payload from raw_body to avoid duplicate body reads
        payload_dict = json.loads(raw_body.decode('utf-8'))
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
