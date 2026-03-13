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
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models import Task, CallLog, Campaign, GlobalApiKey
from app.schemas.net2phone import Net2PhoneWebhookPayload
from app.services.s3_service import upload_fileobj_to_s3
from app.core.config import get_settings
from app.core.audio import get_audio_duration

logger = logging.getLogger("uvicorn.error")


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
    Verify net2phone webhook signature and timestamp.
    
    Validates both the HMAC signature and the timestamp to prevent replay attacks.
    Timestamp must be within ±5 minutes of current UTC time.
    
    Args:
        raw_body: Raw request body as bytes
        signature: Value from x-net2phone-signature header
        timestamp: Value from x-net2phone-timestamp header (ISO 8601 or RFC3339)
        secret: Secret key for HMAC
        
    Returns:
        True if signature is valid and timestamp is within acceptable window
    """
    logger.debug("="*60)
    logger.debug("Starting webhook signature verification")
    logger.debug("Received signature: %s", signature)
    logger.debug("Received timestamp: %s", timestamp)
    logger.debug("Secret configured: %s (length: %d)", "YES" if secret else "NO", len(secret) if secret else 0)
    logger.debug("Raw body length: %d bytes", len(raw_body))
    logger.debug("Raw body (first 200 chars): %s", raw_body[:200])
    
    try:
        # Validate timestamp format and window
        try:
            # Handle timestamps with 7-digit fractional seconds (e.g., 2026-03-12T20:31:36.3502036Z)
            # Python's fromisoformat only supports up to 6 digits (microseconds)
            timestamp_cleaned = timestamp.replace('Z', '+00:00')
            
            # If timestamp has 7+ digits after decimal, truncate to 6
            if '.' in timestamp_cleaned:
                parts = timestamp_cleaned.split('.')
                if len(parts) == 2:
                    fractional = parts[1]
                    # Extract only digits before timezone
                    if '+' in fractional:
                        digits, tz = fractional.split('+', 1)
                        if len(digits) > 6:
                            # Truncate to 6 digits
                            timestamp_cleaned = f"{parts[0]}.{digits[:6]}+{tz}"
                            logger.debug("Truncated fractional seconds from %d to 6 digits", len(digits))
                    elif '-' in fractional:
                        digits, tz = fractional.split('-', 1)
                        if len(digits) > 6:
                            timestamp_cleaned = f"{parts[0]}.{digits[:6]}-{tz}"
                            logger.debug("Truncated fractional seconds from %d to 6 digits", len(digits))
                    elif len(fractional) > 6:
                        timestamp_cleaned = f"{parts[0]}.{fractional[:6]}"
                        logger.debug("Truncated fractional seconds from %d to 6 digits", len(fractional))
            
            logger.debug("Cleaned timestamp: %s", timestamp_cleaned)
            webhook_time = datetime.fromisoformat(timestamp_cleaned)
            logger.debug("Parsed webhook_time: %s", webhook_time)
        except (ValueError, AttributeError) as e:
            logger.error("Failed to parse timestamp '%s': %s", timestamp, e)
            return False
        
        # Check timestamp is within ±5 minutes of current UTC time
        current_utc = datetime.utcnow()
        time_difference = (current_utc - webhook_time.replace(tzinfo=None)).total_seconds()
        
        logger.debug("Current UTC time: %s", current_utc)
        logger.debug("Time difference: %f seconds", time_difference)
        
        if abs(time_difference) > 300:
            logger.warning("Timestamp validation failed: difference of %f seconds exceeds 300 seconds", abs(time_difference))
            return False
        
        logger.debug("Timestamp validation passed")
        
        # Compute HMAC-SHA256 over timestamp:body using shared secret
        # According to net2phone docs: signature = HMAC-SHA256(secret, timestamp + ":" + body)
        payload_to_sign = f"{timestamp}:{raw_body.decode('utf-8')}"
        logger.debug("Payload to sign: %s", payload_to_sign[:200])
        
        hmac_hash = hmac.new(
            secret.encode('utf-8') if secret else b'',
            payload_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        logger.debug("Computed HMAC hash: %s", hmac_hash)
        logger.debug("Expected signature: %s", signature)
        logger.debug("Signature match: %s", hmac.compare_digest(hmac_hash, signature))
        
        # Compare with provided signature using constant-time comparison
        result = hmac.compare_digest(hmac_hash, signature)
        logger.debug("Signature verification result: %s", "VALID" if result else "INVALID")
        logger.debug("="*60)
        return result
    except Exception as e:
        logger.exception("Exception during signature verification: %s", e)
        logger.debug("="*60)
        return False


def extract_campaign_id_from_user(
    user_id: Optional[int],
    db: Session,
    default_campaign_id: Optional[int] = None
) -> Optional[int]:
    """
    Extract campaign_id from user.id or use default.
    
    Since net2phone uses user.account_id for operator mapping,
    we use user.id for campaign mapping if available,
    otherwise use default_campaign_id.
    
    Args:
        user_id: User ID from net2phone
        db: Database session
        default_campaign_id: Default campaign fallback
        
    Returns:
        Campaign ID or None
    """
    if user_id:
        # Try to find campaign with matching user_id
        campaign = db.query(Campaign).filter(
            Campaign.campaign_id == user_id
        ).first()
        
        if campaign:
            return user_id
    
    return default_campaign_id


def extract_operator_id_from_user(
    user_account_id: Optional[int]
) -> Optional[int]:
    """
    Extract operator_id from user.account_id.
    
    net2phone uses user.account_id to identify operators/agents.
    
    Args:
        user_account_id: Account ID from user object
        
    Returns:
        Operator ID as integer or None
    """
    return user_account_id


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


def process_net2phone_recording(
    recording_url: str,
    call_start: datetime,
    originating_number: Optional[str],
    username: str,
    db: Session,
    api_key_record: Optional[GlobalApiKey] = None
) -> dict:
    """
    Process net2phone recording: download, upload to S3, extract metadata.
    
    This follows the same pattern as upload.py endpoints.
    
    Args:
        recording_url: URL to download recording from
        call_start: Call start timestamp for filename generation
        originating_number: Phone number for filename
        username: Username for S3 path
        db: Database session
        api_key_record: API key record for api_key_id
        
    Returns:
        Dictionary with:
            - task_uuid: Generated UUID for the task
            - file_name: Generated filename
            - object_name: S3 object path
            - audio_duration: Audio duration in seconds
            - content_type: MIME type
            
    Raises:
        Net2PhoneDownloadError: If download fails
        Net2PhoneIntegrationError: If upload or processing fails
    """
    logger.debug("Processing net2phone recording: url=%s, call_start=%s", recording_url, call_start)
    
    try:
        # Download recording
        logger.debug("Downloading recording from: %s", recording_url)
        file_content, content_type = download_recording(recording_url)
        logger.info("Recording downloaded successfully, size=%d bytes, content_type=%s", len(file_content), content_type)
        
        # Determine file extension
        file_ext = determine_file_extension(content_type)
        logger.debug("Determined file extension: %s", file_ext)
        
        # Generate UUID for the task
        task_uuid = str(uuid.uuid4())
        logger.debug("Generated task_uuid: %s", task_uuid)
        
        # Generate filename (same pattern as upload.py)
        timestamp = call_start.strftime("%Y%m%d_%H%M%S")
        originating_clean = (originating_number or "unknown").replace('+', '').replace(' ', '')
        file_name = f"{timestamp}_{originating_clean}_{task_uuid[:8]}{file_ext}"
        logger.debug("Generated filename: %s", file_name)
        
        # Generate S3 object name
        object_name = f"{username}/{file_name}"
        logger.debug("S3 object name: %s", object_name)
        
        # Save to temp file for upload and duration extraction
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        logger.debug("Saved to temp file: %s", tmp_path)
        
        try:
            # Get audio duration using app.core.audio.get_audio_duration
            logger.debug("Extracting audio duration...")
            audio_duration = get_audio_duration(tmp_path)
            logger.debug("Audio duration: %s seconds", audio_duration)
            
            # Upload to S3
            logger.debug("Starting S3 upload...")
            settings = get_settings()
            with open(tmp_path, "rb") as fh:
                upload_success = upload_fileobj_to_s3(
                    fh,
                    settings.S3_BUCKET,
                    object_name,
                    content_type=content_type
                )
            
            logger.info("S3 upload result: %s", "SUCCESS" if upload_success else "FAILED")
            if not upload_success:
                raise Net2PhoneIntegrationError("Failed to upload to S3")
            
            return {
                'task_uuid': task_uuid,
                'file_name': file_name,
                'object_name': object_name,
                'audio_duration': audio_duration,
                'content_type': content_type
            }
            
        finally:
            # Clean up temp file
            logger.debug("Cleaning up temp file: %s", tmp_path)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
    except Net2PhoneDownloadError as e:
        logger.error("Download failed: %s", e)
        raise
    except Net2PhoneIntegrationError as e:
        logger.error("Integration error: %s", e)
        raise
    except Exception as e:
        logger.exception("Unexpected error processing recording: %s", e)
        raise Net2PhoneIntegrationError(f"Failed to process recording: {str(e)}") from e


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
    
    # Determine which recording URL to use
    # - call_completed: uses recording_url
    # - call_recorded: uses audio_message_url
    recording_url = None
    if payload.recording_url:
        recording_url = payload.recording_url
    elif hasattr(payload, 'audio_message_url') and payload.audio_message_url:
        recording_url = payload.audio_message_url
    
    logger.info("Processing net2phone webhook: call_id=%s, event=%s, recording_url=%s, audio_message_url=%s", 
                payload.call_id, payload.event, payload.recording_url, 
                getattr(payload, 'audio_message_url', None))
    logger.debug("Webhook payload: %s", payload.dict())
    
    try:
        # Parse call start time from timestamp
        call_start = payload.timestamp
        logger.debug("Call start time: %s", call_start)
        
        # Calculate call end time
        call_end = None
        if payload.duration:
            call_end = call_start + timedelta(seconds=payload.duration)
            logger.debug("Call end time: %s (duration: %s seconds)", call_end, payload.duration)
        
        # Extract campaign_id - always use default
        campaign_id = default_campaign_id
        logger.debug("Using campaign_id: %s", campaign_id)
        
        # Extract operator_id from user.account_id
        operator_id = extract_operator_id_from_user(
            payload.user.account_id if payload.user else None
        )
        logger.debug("Extracted operator_id: %s", operator_id)
        
        # Generate username from API key
        username = "net2phone_webhook"
        if api_key_record and hasattr(api_key_record, 'name'):
            username = f"net2phone_{api_key_record.name}"
        logger.debug("Generated username: %s", username)
        
        # Check if recording is available BEFORE creating any records
        # This prevents orphaned call_logs when no recording exists
        should_process_recording = False
        
        if payload.event == 'call_completed' and recording_url:
            logger.info("call_completed event with recording_url - will process recording")
            should_process_recording = True
        elif payload.event == 'call_recorded' and recording_url:
            logger.info("call_recorded event with audio_message_url - will process recording")
            should_process_recording = True
        elif payload.event in ('call_completed', 'call_recorded'):
            logger.info("Event %s received but no recording URL available - skipping to avoid orphaned data", payload.event)
            logger.debug("Event details: call_id=%s, recording_url=%s, audio_message_url=%s", 
                        payload.call_id, payload.recording_url, getattr(payload, 'audio_message_url', None))
            return result  # Return early without creating any records
        else:
            logger.debug("Skipping recording processing: event=%s (not call_completed or call_recorded)", payload.event)
            return result  # Return early for non-recording events
        
        # PROCESS RECORDING FIRST, THEN CREATE TASK AND CALLLOG
        # This order ensures data integrity: no orphaned call_logs if recording fails
        if should_process_recording:
            logger.info("Processing recording for net2phone call_id=%s, url=%s", payload.call_id, recording_url)
            try:
                # Use helper function to process recording (download, upload, extract metadata)
                recording_data = process_net2phone_recording(
                    recording_url=recording_url,
                    call_start=call_start,
                    originating_number=payload.originating_number,
                    username=username,
                    db=db,
                    api_key_record=api_key_record
                )
                
                task_uuid = recording_data['task_uuid']
                logger.info("Recording processed successfully, task_uuid=%s", task_uuid)
                
                # Create task_params following the same pattern as upload.py
                task_params = {
                    "language": "es",
                    "task": "transcribe",
                    "model": "nova-3",
                    "device": "deepgram",
                    "device_index": 0,
                    "threads": None,
                    "batch_size": None,
                    "compute_type": None,
                    "align_model": None,
                    "interpolate_method": None,
                    "return_char_alignments": False,
                    "asr_options": {},
                    "vad_options": {},
                    "min_speakers": None,
                    "max_speakers": None,
                    "s3_path": recording_data['object_name'],
                    "username": username,
                    "api_key_id": api_key_record.id if api_key_record else None,
                    "source_url": recording_url,
                    "net2phone_call_id": payload.call_id,  # Store original Net2Phone call_id
                    "net2phone_event": payload.event,
                    "net2phone_direction": payload.direction,
                    "net2phone_audio_message_id": getattr(payload, 'audio_message_id', None),
                }
                logger.debug("Creating task with params: %s", task_params)
                
                # Create Task
                new_task = Task(
                    uuid=task_uuid,
                    file_name=recording_data['file_name'],
                    url=recording_data['object_name'],
                    status="pending",
                    task_type="full_process",
                    task_params=task_params,
                    language="es",
                    audio_duration=recording_data['audio_duration']
                )
                db.add(new_task)
                logger.debug("Task added to database, uuid=%s", task_uuid)
                
                # Create CallLog AFTER Task is created (data integrity)
                # CallLog.call_id = Task.uuid (correct relationship)
                new_call_log = CallLog(
                    call_id=task_uuid,  # RELACIÓN CORRECTA: CallLog.call_id = Task.uuid
                    file_name=recording_data['file_name'],
                    date=call_start,
                    campaign_id=campaign_id or 1,
                    operator_id=operator_id or 1,
                    direction=payload.direction,
                    call_start_date=call_start,
                    call_end_date=call_end,
                    sectot=payload.duration,
                    ani_tel=payload.originating_number,
                    url=recording_data['object_name'],
                    log=f"Net2Phone webhook processed: call_id={payload.call_id}, event={payload.event}, Task UUID={task_uuid}",
                    upload_by=username,
                    created_at=datetime.utcnow()
                )
                db.add(new_call_log)
                logger.debug("CallLog added to database, call_id=%s", task_uuid)
                
                # Commit both Task and CallLog together
                db.commit()
                db.refresh(new_task)
                logger.info("Created task_uuid=%s and CallLog for net2phone call_id=%s", task_uuid, payload.call_id)
                
                result['recording_downloaded'] = True
                result['task_created'] = True
                result['call_log_created'] = True
                result['task_id'] = task_uuid
                result['call_log_id'] = task_uuid  # Same as task_id
                result['file_name'] = recording_data['file_name']
                
            except Net2PhoneDownloadError as e:
                logger.error("Download failed for net2phone call_id=%s: %s", payload.call_id, e)
                result['errors'].append(f"Download failed: {str(e)}")
            except Net2PhoneIntegrationError as e:
                logger.error("Integration error for net2phone call_id=%s: %s", payload.call_id, e)
                result['errors'].append(f"Integration error: {str(e)}")
        
        logger.info("Webhook processing completed for call_id=%s: recording_downloaded=%s, task_created=%s, errors=%s",
                    payload.call_id, result['recording_downloaded'], result['task_created'], result['errors'])
        return result
        
    except Exception as e:
        logger.exception("Unexpected error processing net2phone webhook for call_id=%s", payload.call_id)
        db.rollback()
        raise Net2PhoneIntegrationError(f"Failed to process webhook: {str(e)}") from e
