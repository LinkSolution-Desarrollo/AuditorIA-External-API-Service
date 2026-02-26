from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Request, Form
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.services.s3_service import upload_fileobj_to_s3, check_file_exists_in_s3
from app.models import Task, GlobalApiKey, Campaign, CallLog
from app.middleware.auth import get_api_key, ApiKeyData
from app.core.validation import validate_file
from app.core.audio import get_audio_duration
from app.core.config import get_settings
import os
import tempfile
import shutil
import uuid
import logging
import requests as http_requests
from datetime import datetime
from app.schemas.transcription import TranscriptionConfig

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
    dependencies=[Depends(get_api_key)]
)

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


class UploadFromUrlRequest(BaseModel):
    url: str
    campaign_id: int
    username: str
    operator_id: int
    language: str = "es"
    model: str = "nova-3"


@router.post(
    "",
    summary="Upload audio file for transcription",
    description="Uploads a binary audio file (mp3, wav, ogg, m4a, flac, aac) to start a transcription task. "
                "The file is stored in S3 and a task is queued for processing. "
                "NOTE: MCP clients and AI sandboxes cannot send binary files — use POST /upload/from-url instead.",
)
@limiter.limit("10/minute")
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    campaign_id: int = Form(...),
    username: str = Form(...),
    operator_id: int = Form(...),
    config: TranscriptionConfig = Depends(TranscriptionConfig.as_form),
    db: Session = Depends(get_db),
    api_key: ApiKeyData = Depends(get_api_key),
):
    # Check if campaign exists
    campaign = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with ID {campaign_id} not found. Please create the campaign before uploading."
        )

    # Enhanced Validation
    await validate_file(file)

    file_uuid = str(uuid.uuid4())
    bucket_name = settings.S3_BUCKET

    try:
        # Create a temp file
        total_bytes_read = 0
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            await file.seek(0)  # Ensure we are at the beginning
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                tmp.write(chunk)
                total_bytes_read += len(chunk)
            tmp_path = tmp.name

        # Check size and log it
        file_size = os.path.getsize(tmp_path)
        print(f"DEBUG: Reported file size: {file.size}")
        print(f"DEBUG: Total bytes read into temp: {total_bytes_read}")
        print(f"DEBUG: Temp file size on disk: {file_size} bytes")

        if file_size == 0:
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=400, detail="The uploaded file is empty.")

        if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=413, detail=f"File too large. Max size is {settings.MAX_UPLOAD_SIZE_MB}MB")

        # Get audio duration
        audio_duration = get_audio_duration(tmp_path)
        print(f"DEBUG: Calculated audio_duration = {audio_duration}")

        object_name = f"{username}/{file.filename}"

        # Check if file already exists
        if check_file_exists_in_s3(bucket_name, object_name):
            raise HTTPException(
                status_code=409,
                detail=f"Conflict: The file '{file.filename}' has already been uploaded by user '{username}'."
            )

        # Upload to S3
        upload_success = upload_fileobj_to_s3(
            open(tmp_path, "rb"), bucket_name, object_name, content_type=file.content_type)

        if not upload_success:
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=500, detail="Failed to upload file to storage")

        # Parse suppress_tokens if provided
        parsed_suppress_tokens = None
        if config.suppress_tokens:
            try:
                parsed_suppress_tokens = [
                    int(t.strip()) for t in config.suppress_tokens.split(",") if t.strip()]
            except ValueError:
                pass

        # Prepare Task Params (match downstream transcribe payload)
        task_params = {
            "language": config.language or "es",
            "task": config.task or "transcribe",
            "model": config.model or "nova-3",
            "device": config.device or "deepgram",
            "device_index": config.device_index or 0,
            "threads": config.threads,
            "batch_size": config.batch_size,
            "compute_type": config.compute_type,
            "align_model": config.align_model,
            "interpolate_method": config.interpolate_method,
            "return_char_alignments": False,
            "asr_options": {
                "beam_size": config.beam_size,
                "patience": config.patience,
                "length_penalty": config.length_penalty,
                "temperatures": config.temperatures,
                "compression_ratio_threshold": config.compression_ratio_threshold,
                "log_prob_threshold": config.log_prob_threshold,
                "no_speech_threshold": config.no_speech_threshold,
                "initial_prompt": config.initial_prompt,
                "suppress_tokens": parsed_suppress_tokens,
                "suppress_numerals": config.suppress_numerals,
            },
            "vad_options": {
                "vad_onset": config.vad_onset,
                "vad_offset": config.vad_offset,
            },
            "min_speakers": None,
            "max_speakers": None,
            "s3_path": object_name,
            "username": username,
            "api_key_id": api_key.id,  # Store API key ID for filtering
        }

        # Clean up temp file
        os.unlink(tmp_path)

        # Create Task
        new_task = Task(
            uuid=file_uuid,
            file_name=file.filename,
            url=object_name,
            status="pending",
            task_type="full_process",
            task_params=task_params,
            language=config.language or "es",
            audio_duration=audio_duration
        )
        db.add(new_task)

        # Create Call Log Entry (New Requirement)
        new_call_log = CallLog(
            file_name=file.filename,
            date=datetime.utcnow(),
            campaign_id=campaign_id,
            call_id=file_uuid,
            operator_id=operator_id,
            upload_by=username,
            url=object_name,
            log=f"Uploaded via External API (Task UUID: {file_uuid})",
            sectot=audio_duration
        )
        db.add(new_call_log)

        db.commit()
        db.refresh(new_task)

        return {
            "task_id": new_task.uuid,
            "status": "queued",
            "message": "File uploaded successfully"
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"An error occurred: {str(e)}")


@router.post(
    "/from-url",
    summary="Upload audio from a public URL for transcription",
    description=(
        "Downloads an audio file from a publicly accessible URL and queues it for transcription. "
        "Use this endpoint from MCP clients, AI agents, and sandbox environments that cannot send binary files. "
        "Supported formats: mp3, wav, ogg, m4a, flac, aac. Max size: 50MB. "
        "The URL must be publicly accessible (no auth required to download). "
        "Example sources: S3 presigned URLs, CDN links, direct download links."
    ),
)
@limiter.limit("10/minute")
async def upload_from_url(
    request: Request,
    body: UploadFromUrlRequest,
    db: Session = Depends(get_db),
    api_key: ApiKeyData = Depends(get_api_key),
):
    settings = get_settings()

    # Validate campaign exists
    campaign = db.query(Campaign).filter(Campaign.campaign_id == body.campaign_id).first()
    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with ID {body.campaign_id} not found."
        )

    # Download file from URL
    try:
        response = http_requests.get(body.url, stream=True, timeout=60)
        response.raise_for_status()
    except http_requests.exceptions.Timeout:
        raise HTTPException(status_code=422, detail="Timed out downloading file from URL.")
    except http_requests.exceptions.RequestException as e:
        raise HTTPException(status_code=422, detail=f"Could not download file from URL: {str(e)}")

    # Determine filename from URL or Content-Disposition header
    file_name = None
    content_disposition = response.headers.get("Content-Disposition", "")
    if "filename=" in content_disposition:
        file_name = content_disposition.split("filename=")[-1].strip().strip('"')
    if not file_name:
        file_name = body.url.split("?")[0].split("/")[-1] or "audio_upload"

    # Ensure it has an extension
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        file_name = f"{os.path.splitext(file_name)[0]}.mp3"
        ext = ".mp3"

    file_uuid = str(uuid.uuid4())
    bucket_name = settings.S3_BUCKET

    try:
        # Write to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                tmp.write(chunk)
            tmp_path = tmp.name

        file_size = os.path.getsize(tmp_path)

        if file_size == 0:
            os.unlink(tmp_path)
            raise HTTPException(status_code=400, detail="Downloaded file is empty.")

        if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max size is {settings.MAX_UPLOAD_SIZE_MB}MB."
            )

        audio_duration = get_audio_duration(tmp_path)
        object_name = f"{body.username}/{file_name}"

        if check_file_exists_in_s3(bucket_name, object_name):
            raise HTTPException(
                status_code=409,
                detail=f"Conflict: file '{file_name}' already uploaded by user '{body.username}'."
            )

        upload_success = upload_fileobj_to_s3(
            open(tmp_path, "rb"), bucket_name, object_name,
            content_type=response.headers.get("Content-Type", "audio/mpeg")
        )
        os.unlink(tmp_path)

        if not upload_success:
            raise HTTPException(status_code=500, detail="Failed to upload file to storage.")

        task_params = {
            "language": body.language,
            "task": "transcribe",
            "model": body.model,
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
            "s3_path": object_name,
            "username": body.username,
            "api_key_id": api_key.id,
            "source_url": body.url,
        }

        new_task = Task(
            uuid=file_uuid,
            file_name=file_name,
            url=object_name,
            status="pending",
            task_type="full_process",
            task_params=task_params,
            language=body.language,
            audio_duration=audio_duration,
        )
        db.add(new_task)

        new_call_log = CallLog(
            file_name=file_name,
            date=datetime.utcnow(),
            campaign_id=body.campaign_id,
            call_id=file_uuid,
            operator_id=body.operator_id,
            upload_by=body.username,
            url=object_name,
            log=f"Uploaded via External API from URL (Task UUID: {file_uuid})",
            sectot=audio_duration,
        )
        db.add(new_call_log)

        db.commit()
        db.refresh(new_task)

        return {
            "task_id": new_task.uuid,
            "status": "queued",
            "message": "File downloaded and queued successfully",
            "file_name": file_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
