"""
Service for handling Anura integration.
Downloads recordings and creates transcription tasks.
"""
import os
import requests
import tempfile
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from app.models import Task, CallLog, Campaign, GlobalApiKey
from app.schemas.anura import AnuraWebhookPayload
from app.schemas.transcription import TranscriptionConfig
from app.services.s3_service import upload_fileobj_to_s3
from app.core.config import get_settings
from mutagen import File as MutagenFile

settings = get_settings()


class AnuraIntegrationError(Exception):
    """Base exception for Anura integration errors."""
    pass


class AnuraDownloadError(AnuraIntegrationError):
    """Exception raised when recording download fails."""
    pass


def extract_campaign_id_from_tags(accounttags: Optional[str]) -> Optional[int]:
    """
    Extract campaign_id from Anura account tags.
    
    Expected format: "campaign_123" or just "123"
    
    Args:
        accounttags: Tags string from Anura
        
    Returns:
        Campaign ID as integer or None
    """
    if not accounttags:
        return None
    
    tags = accounttags.split(',')
    for tag in tags:
        tag = tag.strip().lower()
        if tag.startswith('campaign_'):
            try:
                return int(tag.replace('campaign_', ''))
            except ValueError:
                continue
        elif tag.isdigit():
            try:
                return int(tag)
            except ValueError:
                continue
    
    return None


def extract_operator_id_from_agent(
    queueagentextension: Optional[str],
    queueagentname: Optional[str]
) -> Optional[int]:
    """
    Extract operator_id from agent information.
    
    Args:
        queueagentextension: Agent extension from Anura
        queueagentname: Agent name from Anura
        
    Returns:
        Operator ID as integer or None
    """
    # Try extension first
    if queueagentextension and queueagentextension.isdigit():
        return int(queueagentextension)
    
    # Try to extract from name if it contains numbers
    if queueagentname:
        import re
        numbers = re.findall(r'\d+', queueagentname)
        if numbers:
            return int(numbers[0])
    
    return None


def download_recording(recording_url: str) -> Tuple[bytes, str]:
    """
    Download recording from Anura URL.
    
    Args:
        recording_url: URL to download recording from
        
    Returns:
        Tuple of (file_content, content_type)
        
    Raises:
        AnuraDownloadError: If download fails
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
        raise AnuraDownloadError(f"Failed to download recording: {str(e)}")


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


def process_anura_webhook(
    payload: AnuraWebhookPayload,
    db: Session,
    default_campaign_id: Optional[int] = None,
    default_operator_id: Optional[int] = None,
    api_key_record: Optional[GlobalApiKey] = None
) -> dict:
    """
    Process Anura webhook and create transcription task if applicable.
    
    Args:
        payload: Validated webhook payload
        db: Database session
        default_campaign_id: Default campaign if not in tags
        default_operator_id: Default operator if not detected
        api_key_record: API key record for username
        
    Returns:
        Dictionary with processing results
        
    Raises:
        AnuraIntegrationError: If processing fails
    """
    result = {
        'call_id': payload.cdrid,
        'trigger': payload.hooktrigger,
        'recording_downloaded': False,
        'task_created': False,
        'call_log_created': False,
        'task_id': None,
        'errors': []
    }
    
    try:
        # Parse call start time
        try:
            call_start = datetime.strptime(payload.dialtime, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                call_start = datetime.strptime(payload.dialtime, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                raise AnuraIntegrationError(f"Invalid dialtime format: {payload.dialtime}")
        
        # Calculate call end time
        call_end = None
        if payload.duration:
            call_end = call_start + timedelta(seconds=payload.duration)
        
        # Extract campaign_id
        campaign_id = extract_campaign_id_from_tags(payload.accounttags)
        if not campaign_id:
            campaign_id = default_campaign_id
        
        # Verify campaign exists
        if campaign_id:
            campaign = db.query(Campaign).filter(
                Campaign.campaign_id == campaign_id
            ).first()
            if not campaign:
                result['errors'].append(f"Campaign {campaign_id} not found")
                campaign_id = None
        
        # Extract operator_id
        operator_id = extract_operator_id_from_agent(
            payload.queueagentextension,
            payload.queueagentname
        )
        if not operator_id:
            operator_id = default_operator_id
        
        # Generate username from API key or default
        username = "anura_webhook"
        if api_key_record and hasattr(api_key_record, 'name'):
            username = f"anura_{api_key_record.name}"
        
        # Create or update CallLog
        call_log = db.query(CallLog).filter(
            CallLog.call_id == payload.cdrid
        ).first()
        
        if not call_log:
            call_log = CallLog(
                call_id=payload.cdrid,
                file_name=None,  # Will be set if recording downloaded
                date=call_start,
                campaign_id=campaign_id,
                operator_id=operator_id or 1,  # Default to 1 if not set
                direction=payload.direction,
                call_start_date=call_start,
                call_end_date=call_end,
                sectot=payload.duration,
                ani_tel=payload.calling,
                url=payload.audio_file_mp3,
                log=f"Received Anura webhook: {payload.hooktrigger}",
                upload_by=username,
                created_at=datetime.utcnow()
            )
            db.add(call_log)
            result['call_log_created'] = True
        else:
            # Update existing log
            call_log.call_end_date = call_end
            call_log.sectot = payload.duration
            call_log.status = payload.status
            if payload.audio_file_mp3:
                call_log.url = payload.audio_file_mp3
        
        db.commit()
        
        # Process recording if available and call ended
        if payload.hooktrigger == 'END' and payload.wasrecorded and payload.audio_file_mp3:
            try:
                # Download recording
                file_content, content_type = download_recording(payload.audio_file_mp3)
                
                # Determine file extension
                file_ext = determine_file_extension(content_type)
                
                # Generate filename
                file_uuid = str(uuid.uuid4())
                timestamp = call_start.strftime("%Y%m%d_%H%M%S")
                calling_clean = (payload.calling or "unknown").replace('+', '').replace(' ', '')
                file_name = f"{timestamp}_{calling_clean}_{file_uuid[:8]}{file_ext}"
                
                # Upload to S3
                object_name = f"{username}/{file_name}"
                
                # Save to temp file first
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name
                
                try:
                    # Upload to S3
                    upload_success = upload_fileobj_to_s3(
                        open(tmp_path, "rb"),
                        settings.S3_BUCKET,
                        object_name,
                        content_type=content_type
                    )
                    
                    if not upload_success:
                        raise AnuraIntegrationError("Failed to upload to S3")
                    
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
                    
                    # Update call log with filename
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
                
            except AnuraDownloadError as e:
                result['errors'].append(f"Download failed: {str(e)}")
            except AnuraIntegrationError as e:
                result['errors'].append(f"Integration error: {str(e)}")
        
        return result
        
    except Exception as e:
        db.rollback()
        raise AnuraIntegrationError(f"Failed to process webhook: {str(e)}")
