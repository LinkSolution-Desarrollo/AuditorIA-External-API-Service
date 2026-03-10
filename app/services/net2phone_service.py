"""
Service for handling net2phone integration.
Downloads recordings and creates transcription tasks.
"""
import os
import hmac
import hashlib
import requests
import tempfile
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models import Task, CallLog, Campaign, GlobalApiKey
from app.schemas.net2phone import Net2PhoneWebhookPayload
from app.services.s3_service import upload_fileobj_to_s3
from app.core.config import get_settings
from mutagen import File as MutagenFile


class Net2PhoneIntegrationError(Exception):
    """Base exception for net2phone integration errors."""
    pass


class Net2PhoneDownloadError(Net2PhoneIntegrationError):
    """Exception raised when recording download fails."""
    pass


def verify_webhook_signature(
    raw_body: bytes,
    signature: str,
    timestamp: str,
    secret: str
) -> bool:
    """
    Verify net2phone webhook signature.
    
    Args:
        raw_body: Raw request body as bytes
        signature: Value from x-net2phone-signature header
        timestamp: Value from x-net2phone-timestamp header
        secret: Secret key for HMAC
        
    Returns:
        True if signature is valid
    """
    try:
        # Concatenate signature:raw_body
        message = f"{signature}:{raw_body.decode('utf-8')}"
        
        # Compute HMAC-SHA256
        hmac_hash = hmac.new(
            timestamp.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare with provided signature
        return hmac.compare_digest(hmac_hash, signature)
    except Exception:
        return False


def extract_campaign_id_from_user(
    user_account_id: Optional[int],
    db: Session,
    default_campaign_id: Optional[int] = None
) -> Optional[int]:
    """
    Extract campaign_id from user account_id.
    
    Since net2phone doesn't have accounttags like Anura,
    we map user.account_id to campaign_id.
    
    Args:
        user_account_id: Account ID from user object
        db: Database session
        default_campaign_id: Default campaign fallback
        
    Returns:
        Campaign ID or None
    """
    if user_account_id:
        # Try to find campaign with matching account_id
        campaign = db.query(Campaign).filter(
            Campaign.campaign_id == user_account_id
        ).first()
        
        if campaign:
            return user_account_id
    
    return default_campaign_id


def extract_operator_id_from_user(
    user_id: Optional[int],
    user_name: Optional[str]
) -> Optional[int]:
    """
    Extract operator_id from user information.
    
    Args:
        user_id: User ID from net2phone
        user_name: User name
        
    Returns:
        Operator ID as integer or None
    """
    if user_id:
        return user_id
    
    # Fallback: try to extract number from name
    if user_name:
        import re
        numbers = re.findall(r'\d+', user_name)
        if numbers:
            return int(numbers[0])
    
    return None


def download_recording(recording_url: str) -> Tuple[bytes, str]:
    """
    Download recording from net2phone URL.
    
    Args:
        recording_url: URL to download recording from
        
    Returns:
        Tuple of (file_content, content_type)
        
    Raises:
        Net2PhoneDownloadError: If download fails
    """
    try:
        response = requests.get(
            recording_url,
            timeout=30,
            headers={'Accept': 'audio/*'}
        )
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', 'audio/mpeg')
        
        return response.content, content_type
        
    except requests.RequestException as e:
        raise Net2PhoneDownloadError(f"Failed to download recording: {str(e)}") from e


def determine_file_extension(content_type: str) -> str:
    """
    Determine file extension from content type.
    
    Args:
        content_type: MIME type
        
    Returns:
        File extension with dot (e.g., '.mp3')
    """
    mapping = {
        'audio/mpeg': '.mp3',
        'audio/mp3': '.mp3',
        'audio/ogg': '.ogg',
        'audio/wav': '.wav',
        'audio/x-wav': '.wav',
        'audio/m4a': '.m4a',
        'audio/mp4': '.m4a',
        'audio/aac': '.aac',
        'audio/flac': '.flac',
    }
    
    return mapping.get(content_type.lower(), '.mp3')


def process_net2phone_webhook(
    payload: Net2PhoneWebhookPayload,
    db: Session,
    default_campaign_id: Optional[int] = None,
    default_operator_id: Optional[int] = None,
    api_key_record: Optional[GlobalApiKey] = None
) -> dict:
    """
    Process net2phone webhook and create transcription task if applicable.
    
    Args:
        payload: Validated webhook payload
        db: Database session
        default_campaign_id: Default campaign if not in user data
        default_operator_id: Default operator if not detected
        api_key_record: API key record for username
        
    Returns:
        Dictionary with processing results
        
    Raises:
        Net2PhoneIntegrationError: If processing fails
    """
    result = {
        'call_id': payload.call_id,
        'event': payload.event,
        'recording_downloaded': False,
        'task_created': False,
        'call_log_created': False,
        'task_id': None,
        'errors': []
    }
    
    try:
        # Parse call start time from timestamp
        call_start = payload.timestamp
        
        # Calculate call end time
        call_end = None
        if payload.duration:
            call_end = call_start + timedelta(seconds=payload.duration)
        
        # Extract campaign_id from user.account_id
        campaign_id = extract_campaign_id_from_user(
            payload.user.account_id if payload.user else None,
            db,
            default_campaign_id
        )
        
        # Extract operator_id from user.id
        operator_id = extract_operator_id_from_user(
            payload.user.id if payload.user else None,
            payload.user.name if payload.user else None
        )
        if not operator_id:
            operator_id = default_operator_id
        
        # Generate username from API key
        username = "net2phone_webhook"
        if api_key_record and hasattr(api_key_record, 'name'):
            username = f"net2phone_{api_key_record.name}"
        
        # Create or update CallLog
        call_log = db.query(CallLog).filter(
            CallLog.call_id == payload.call_id
        ).first()
        
        if not call_log:
            # Generate provisional filename
            provisional_filename = f"pending_{payload.call_id}_{uuid.uuid4().hex[:8]}.tmp"
            call_log = CallLog(
                call_id=payload.call_id,
                file_name=provisional_filename,
                date=call_start,
                campaign_id=campaign_id or 1,
                operator_id=operator_id or 1,
                direction=payload.direction,
                call_start_date=call_start,
                call_end_date=call_end,
                sectot=payload.duration,
                ani_tel=payload.originating_number,
                url=payload.recording_url,
                log=f"Received net2phone webhook: {payload.event}",
                upload_by=username,
                created_at=datetime.utcnow()
            )
            db.add(call_log)
            result['call_log_created'] = True
        else:
            # Update existing log
            call_log.call_end_date = call_end
            call_log.sectot = payload.duration
            if payload.recording_url:
                call_log.url = payload.recording_url
        
        db.commit()
        
        # Process recording if available and call completed
        if payload.event == 'call_completed' and payload.recording_url:
            try:
                # Download recording
                file_content, content_type = download_recording(payload.recording_url)
                
                # Determine file extension
                file_ext = determine_file_extension(content_type)
                
                # Generate filename
                file_uuid = str(uuid.uuid4())
                timestamp = call_start.strftime("%Y%m%d_%H%M%S")
                originating_clean = (payload.originating_number or "unknown").replace('+', '').replace(' ', '')
                file_name = f"{timestamp}_{originating_clean}_{file_uuid[:8]}{file_ext}"
                
                # Upload to S3
                object_name = f"{username}/{file_name}"
                
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name
                
                try:
                    # Upload to S3
                    settings = get_settings()
                    upload_success = upload_fileobj_to_s3(
                        open(tmp_path, "rb"),
                        settings.S3_BUCKET,
                        object_name,
                        content_type=content_type
                    )
                    
                    if not upload_success:
                        raise Net2PhoneIntegrationError("Failed to upload to S3")
                    
                    # Get audio duration
                    audio_duration = None
                    try:
                        audio_info = MutagenFile(tmp_path)
                        if audio_info and hasattr(audio_info, 'info'):
                            audio_duration = getattr(audio_info.info, 'length', None)
                    except Exception:
                        pass
                    
                    # Create transcription task
                    task_params = {
                        "language": "es",
                        "task": "transcribe",
                        "model": "nova-3",
                        "device": "deepgram",
                        "s3_path": object_name,
                        "username": username,
                    }
                    
                    new_task = Task(
                        uuid=file_uuid,
                        file_name=file_name,
                        url=object_name,
                        status="pending",
                        task_type="full_process",
                        task_params=task_params,
                        language="es",
                        audio_duration=audio_duration,
                    )
                    db.add(new_task)
                    
                    # Update call log
                    call_log.file_name = file_name
                    call_log.url = object_name
                    
                    db.commit()
                    db.refresh(new_task)
                    
                    result['recording_downloaded'] = True
                    result['task_created'] = True
                    result['task_id'] = new_task.uuid
                    result['file_name'] = file_name
                    
                finally:
                    # Clean up temp file
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                
            except Net2PhoneDownloadError as e:
                result['errors'].append(f"Download failed: {str(e)}")
            except Net2PhoneIntegrationError as e:
                result['errors'].append(f"Integration error: {str(e)}")
        
        return result
        
    except Exception as e:
        db.rollback()
        raise Net2PhoneIntegrationError(f"Failed to process webhook: {str(e)}") from e
