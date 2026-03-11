"""
Enhanced test utilities for Anura integration.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import random
import string

router = APIRouter(
    prefix="/test",
    tags=["Testing"],
)


class GenerateWebhookRequest(BaseModel):
    """Request to generate test webhook payload."""
    trigger: str = "END"  # START, TALK, END
    campaign_id: Optional[int] = 1
    operator_id: Optional[int] = 300
    has_recording: bool = True
    direction: str = "inbound"
    duration: Optional[int] = 120
    phone_number: Optional[str] = "+5491167950079"


def generate_random_call_id() -> str:
    """Generate random call ID in Anura format."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    random_str = ''.join(random.choices(string.digits, k=10))
    return f"{timestamp}-{random_str}"


def generate_dialtime(offset_minutes: int = 0) -> str:
    """Generate dialtime string with optional offset."""
    dt = datetime.now() - timedelta(minutes=offset_minutes)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@router.post("/anura/generate-webhook")
async def generate_test_webhook(request: GenerateWebhookRequest):
    """
    Generate a realistic test webhook payload for Anura integration.
    
    This helps create test payloads that match Anura's real format.
    """
    call_id = generate_random_call_id()
    dialtime = generate_dialtime()
    
    # Build webhook payload
    payload = {
        # Hook metadata
        "hooktrigger": request.trigger.upper(),
        "hookid": random.randint(10000, 99999),
        "hookname": "AuditorIA Test Webhook",
        "hookdirection": "all",
        "hooktemplateid": random.randint(1, 100),
        "hooktemplatename": "Test Template",
        "hooktags": "test,auditoria",
        
        # Call metadata
        "cdrid": call_id,
        "dialtime": dialtime,
        "direction": request.direction,
        "calling": request.phone_number,
        "callingname": "Test Customer",
        "called": "+5491126888209",
        "calledname": "Support Queue",
        "status": "answered" if request.trigger == "END" else "ringing",
        
        # Duration (only for END)
        "duration": request.duration if request.trigger == "END" else None,
        "billseconds": request.duration - 5 if request.trigger == "END" and request.duration else None,
        "price": round(request.duration * 0.015, 2) if request.trigger == "END" and request.duration else None,
        
        # Recording
        "wasrecorded": request.has_recording and request.trigger == "END",
        "audio_play_mp3": f"https://anura-test.example.com/recordings/play/{call_id}.mp3" if request.has_recording and request.trigger == "END" else None,
        "audio_file_mp3": f"https://anura-test.example.com/recordings/download/{call_id}.mp3" if request.has_recording and request.trigger == "END" else None,
        
        # Campaign mapping
        "accounttags": f"campaign_{request.campaign_id}",
        "accountid": request.campaign_id * 100,
        "accountname": f"Campaign {request.campaign_id}",
        
        # Agent/operator
        "queuename": "Support Queue",
        "queuestatus": "completed" if request.trigger == "END" else "active",
        "queuetotaltime": request.duration + 10 if request.trigger == "END" and request.duration else None,
        "queuetalktime": request.duration if request.trigger == "END" and request.duration else None,
        "queuewaittime": 10,
        "queueagentname": f"Agent {request.operator_id}",
        "queueagentextension": str(request.operator_id),
        "queueagenttags": "senior_agent" if request.operator_id > 200 else "junior_agent",
        
        # Answer info
        "answeraccount": str(request.operator_id),
        "answerextension": str(request.operator_id),
        
        # Tenant
        "tenantid": 1,
        
        # Terminal
        "terminalid": request.operator_id * 10,
        "terminalname": f"Agent {request.operator_id}",
        "terminalstate": "registered",
        
        # Last action
        "lastaction": request.trigger
    }
    
    return {
        "payload": payload,
        "usage": {
            "webhook_url": "/webhook/anura/",
            "curl_command": f'curl -X POST "http://localhost:8001/webhook/anura/" \\\n  -H "X-API-Key: YOUR_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d \'{payload}\''
        },
        "notes": [
            "Copy the payload to test the webhook endpoint",
            "Replace YOUR_API_KEY with a valid API key from AuditorIA",
            f"Will map to campaign_id={request.campaign_id} and operator_id={request.operator_id}",
            "Recording URLs are fake - set has_recording=false to test without downloads"
        ]
    }


@router.get("/anura/scenarios")
async def get_test_scenarios():
    """
    Get predefined test scenarios for Anura integration testing.
    """
    scenarios = {
        "successful_inbound_call": {
            "description": "Standard inbound call with recording",
            "trigger": "END",
            "direction": "inbound",
            "has_recording": True,
            "duration": 180,
            "campaign_id": 1,
            "operator_id": 300
        },
        "outbound_call": {
            "description": "Outbound call made by agent",
            "trigger": "END",
            "direction": "outbound",
            "has_recording": True,
            "duration": 95,
            "campaign_id": 2,
            "operator_id": 301
        },
        "call_without_recording": {
            "description": "Call that wasn't recorded",
            "trigger": "END",
            "direction": "inbound",
            "has_recording": False,
            "duration": 45,
            "campaign_id": 1,
            "operator_id": 300
        },
        "call_start_only": {
            "description": "Call initiated (not answered yet)",
            "trigger": "START",
            "direction": "inbound",
            "has_recording": False,
            "campaign_id": 1,
            "operator_id": 300
        },
        "call_talk_event": {
            "description": "Call answered (conversation started)",
            "trigger": "TALK",
            "direction": "inbound",
            "has_recording": False,
            "campaign_id": 1,
            "operator_id": 300
        },
        "short_call": {
            "description": "Very short call (under 1 minute)",
            "trigger": "END",
            "direction": "inbound",
            "has_recording": True,
            "duration": 35,
            "campaign_id": 3,
            "operator_id": 302
        },
        "long_call": {
            "description": "Long call (over 10 minutes)",
            "trigger": "END",
            "direction": "inbound",
            "has_recording": True,
            "duration": 720,
            "campaign_id": 1,
            "operator_id": 300
        },
        "unknown_campaign": {
            "description": "Call with non-existent campaign (tests fallback)",
            "trigger": "END",
            "direction": "inbound",
            "has_recording": True,
            "duration": 120,
            "campaign_id": 99999,
            "operator_id": 300
        }
    }
    
    return {
        "scenarios": scenarios,
        "usage": "POST /test/anura/generate-webhook with scenario parameters"
    }


@router.get("/anura/cheatsheet")
async def get_anura_cheatsheet():
    """
    Get a quick reference guide for Anura integration.
    """
    return {
        "endpoints": {
            "webhook": "POST /webhook/anura/",
            "health": "GET /webhook/anura/health",
            "test_validation": "POST /webhook/anura/test",
            "generate_payload": "POST /test/anura/generate-webhook",
            "list_campaigns": "GET /anura/campaigns",
            "mapping_guide": "GET /anura/mapping-guide",
            "validate_mapping": "POST /anura/validate-mapping",
            "stats": "GET /anura/stats"
        },
        "account_tag_formats": {
            "campaign": "campaign_{id} - Example: campaign_1",
            "multiple": "campaign_1, tag2, campaign_2",
            "numeric": "123 - Maps to campaign ID 123"
        },
        "agent_mapping": {
            "extension": "Numeric extension (e.g., '300') → operator_id",
            "name": "Name with number (e.g., 'Agent 123') → operator_id 123",
            "fallback": "ANURA_DEFAULT_OPERATOR_ID env variable"
        },
        "webhook_triggers": {
            "START": "Call initiated (creates CallLog)",
            "TALK": "Call answered (updates CallLog)",
            "END": "Call ended (downloads recording + creates Task)"
        },
        "example_curl": {
            "webhook": 'curl -X POST "http://localhost:8001/webhook/anura/" \\\n  -H "X-API-Key: YOUR_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d \'{"hooktrigger":"END","cdrid":"123","dialtime":"2026-02-10 10:30:00","calling":"+5491167950079","called":"+5491126888209","direction":"inbound","duration":120,"wasrecorded":true,"audio_file_mp3":"https://example.com/rec.mp3","accounttags":"campaign_1","queueagentextension":"300"}\'',
            "health": 'curl http://localhost:8001/webhook/anura/health',
            "campaigns": 'curl -H "X-API-Key: YOUR_KEY" http://localhost:8001/anura/campaigns'
        },
        "troubleshooting": {
            "no_campaign_found": "Check accounttags format (campaign_123) or set ANURA_DEFAULT_CAMPAIGN_ID",
            "no_operator_found": "Check agent extension is numeric or set ANURA_DEFAULT_OPERATOR_ID",
            "recording_download_failed": "Verify audio_file_mp3 URL is accessible from server",
            "webhook_not_received": "Test health endpoint and check firewall/rate limiting"
        }
    }


class Net2PhoneGenerateWebhookRequest(BaseModel):
    """Request to generate test net2phone webhook payload."""
    event: str = "call_completed"
    user_id: Optional[int] = 1
    account_id: Optional[int] = 42
    has_recording: bool = True
    direction: str = "inbound"
    duration: Optional[int] = 120
    phone_number: Optional[str] = "+5491167950079"


def generate_net2phone_call_id() -> str:
    """Generate random call ID in net2phone format."""
    return str(uuid.uuid4()).replace('-', '')


@router.post("/net2phone/generate-webhook")
async def generate_net2phone_webhook(request: Net2PhoneGenerateWebhookRequest):
    """
    Generate a realistic test webhook payload for net2phone integration.
    
    This helps create test payloads that match net2phone's real format.
    """
    call_id = generate_net2phone_call_id()
    event_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    webhook = {
        "timestamp": timestamp,
        "event": request.event,
        "user": {
            "id": request.user_id,
            "name": f"Agent {request.user_id}",
            "account_id": request.account_id
        },
        "duration": request.duration if request.event == "call_completed" else 0,
        "direction": request.direction,
        "originating_number": request.phone_number if request.direction == "inbound" else "201",
        "user_name": f"Agent {request.user_id}",
        "id": event_id,
        "dialed_number": request.phone_number if request.direction == "outbound" else "201",
        "call_source": "normal",
        "call_id": call_id
    }
    
    if request.has_recording and request.event == "call_completed":
        webhook["recording_url"] = f"https://example.com/recordings/{call_id}.mp3"
    
    return webhook


@router.get("/net2phone/scenarios")
async def get_net2phone_test_scenarios():
    """
    Get predefined test scenarios for net2phone integration testing.
    """
    scenarios = {
        "successful_inbound_call": {
            "description": "Standard inbound call with recording",
            "event": "call_completed",
            "direction": "inbound",
            "duration": 180,
            "user_id": 1,
            "account_id": 42,
            "has_recording": True
        },
        "outbound_call": {
            "description": "Outbound call made by agent",
            "event": "call_completed",
            "direction": "outbound",
            "duration": 95,
            "user_id": 2,
            "account_id": 42,
            "has_recording": True
        },
        "call_without_recording": {
            "description": "Call without recording",
            "event": "call_completed",
            "direction": "inbound",
            "duration": 45,
            "user_id": 1,
            "account_id": 42,
            "has_recording": False
        },
        "missed_call": {
            "description": "Missed call",
            "event": "call_missed",
            "direction": "inbound",
            "duration": 0,
            "user_id": None,
            "account_id": 42,
            "has_recording": False
        },
        "call_answered": {
            "description": "Call answered (not completed yet)",
            "event": "call_answered",
            "direction": "inbound",
            "duration": None,
            "user_id": 1,
            "account_id": 42,
            "has_recording": False
        },
        "call_ringing": {
            "description": "Call initiated (ringing)",
            "event": "call_ringing",
            "direction": "inbound",
            "duration": None,
            "user_id": 1,
            "account_id": 42,
            "has_recording": False
        }
    }
    
    return scenarios


@router.get("/net2phone/cheatsheet")
async def get_net2phone_cheatsheet():
    """
    Get a quick reference guide for net2phone integration.
    """
    return {
        "endpoints": {
            "webhook": "POST /webhook/net2phone/",
            "health": "GET /webhook/net2phone/health",
            "test_validation": "POST /webhook/net2phone/test",
            "generate_payload": "POST /test/net2phone/generate-webhook",
            "list_campaigns": "GET /net2phone/campaigns",
            "mapping_guide": "GET /net2phone/mapping-guide",
            "validate_mapping": "POST /net2phone/validate-mapping",
            "stats": "GET /net2phone/stats"
        },
        "authentication": {
            "api_key": "X-API-Key header (same as upload endpoint)",
            "signature": "x-net2phone-signature header (HMAC-SHA256)",
            "timestamp": "x-net2phone-timestamp header"
        },
        "campaign_mapping": {
            "method": "NET2PHONE_DEFAULT_CAMPAIGN_ID",
            "example": "Always uses NET2PHONE_DEFAULT_CAMPAIGN_ID env variable"
        },
        "operator_mapping": {
            "method": "user.account_id",
            "example": "user.account_id: 42 → operator_id: 42"
        },
        "supported_events": {
            "call_completed": "Call ended (downloads recording + creates Task)",
            "call_answered": "Call answered (updates CallLog)",
            "call_ringing": "Call initiated (creates CallLog)",
            "call_missed": "Call missed (logs missed call)",
            "call_recorded": "Recording available"
        },
        "example_curl": {
            "webhook": 'curl -X POST "http://localhost:8001/webhook/net2phone/" \\\n  -H "X-API-Key: YOUR_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d \'{"event":"call_completed","call_id":"abc123","timestamp":"2021-10-27T08:58:21.66Z","duration":120,"direction":"inbound","originating_number":"+5491167950079","user":{"id":1,"name":"Jane Doe","account_id":42},"recording_url":"https://example.com/rec.mp3"}\'',
            "health": 'curl http://localhost:8001/webhook/net2phone/health',
            "campaigns": 'curl -H "X-API-Key: YOUR_KEY" http://localhost:8001/net2phone/campaigns'
        },
        "troubleshooting": {
            "no_campaign_found": "Check user.account_id exists as campaign_id or set NET2PHONE_DEFAULT_CAMPAIGN_ID",
            "no_operator_found": "Check user.id exists or set NET2PHONE_DEFAULT_OPERATOR_ID",
            "recording_download_failed": "Verify recording_url is accessible from server",
            "webhook_not_received": "Test health endpoint and check firewall/rate limiting",
            "signature_verification_failed": "Check NET2PHONE_WEBHOOK_SECRET env variable"
        }
    }
