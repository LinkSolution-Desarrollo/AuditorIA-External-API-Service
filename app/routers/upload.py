from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Request, Form
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.services.s3_service import upload_fileobj_to_s3, check_file_exists_in_s3
from app.models import Task, GlobalApiKey, Campaign, CallLog
from app.middleware.auth import get_api_key
from app.core.validation import validate_file
from app.core.config import get_settings
import os
import tempfile
import shutil
import uuid
from datetime import datetime
from app.schemas.transcription import TranscriptionConfig

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
    dependencies=[Depends(get_api_key)]
)

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


@router.post("/")
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
    api_key: GlobalApiKey = Depends(get_api_key)
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
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        # Check size
        file_size = os.path.getsize(tmp_path)
        if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=413, detail=f"File too large. Max size is {settings.MAX_UPLOAD_SIZE_MB}MB")

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

        # Clean up temp file
        os.unlink(tmp_path)

        if not upload_success:
            raise HTTPException(
                status_code=500, detail="Failed to upload file to storage")

        # Prepare Task Params (Internal logic remains here)
        task_params = {
            "source": "external_api",
            "api_key_id": api_key.id
        }

        # Parse suppress_tokens if provided
        parsed_suppress_tokens = None
        if config.suppress_tokens:
            try:
                parsed_suppress_tokens = [
                    int(t.strip()) for t in config.suppress_tokens.split(",") if t.strip()]
            except ValueError:
                pass

        # Add all transcription parameters to task_params
        task_params["transcription_config"] = config.dict(
            exclude={"suppress_tokens"})
        task_params["transcription_config"]["suppress_tokens"] = parsed_suppress_tokens

        # Create Task
        new_task = Task(
            uuid=file_uuid,
            file_name=file.filename,
            url=object_name,
            status="pending",
            task_type="transcription",
            task_params=task_params,
            language=config.language or "es"
        )
        db.add(new_task)

        # Create Call Log Entry (New Requirement)
        new_call_log = CallLog(
            file_name=file.filename,
            date=datetime.utcnow(),
            campaign_id=campaign_id,
            operator_id=operator_id,
            upload_by=username,
            url=object_name,
            log=f"Uploaded via External API (Task UUID: {file_uuid})"
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
