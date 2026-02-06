from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Request, Form
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.services.s3_service import upload_fileobj_to_s3
from app.models import Task, GlobalApiKey
from app.middleware.auth import get_api_key
from app.core.validation import validate_file
from app.core.config import get_settings
import os
import tempfile
import shutil
import uuid

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
    campaign_id: int = Form(None), # Optional Campaign ID
    username: str = Form(None),    # Optional Username
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key)
):
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
            raise HTTPException(status_code=413, detail=f"File too large. Max size is {settings.MAX_UPLOAD_SIZE_MB}MB")
        
        object_name = f"external_uploads/{file_uuid}_{file.filename}"
        
        # Upload to S3
        upload_success = upload_fileobj_to_s3(open(tmp_path, "rb"), bucket_name, object_name, content_type=file.content_type)
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        if not upload_success:
            raise HTTPException(status_code=500, detail="Failed to upload file to storage")

        # Prepare Task Params
        task_params = {
            "source": "external_api", 
            "api_key_id": api_key.id
        }
        if campaign_id:
            task_params["campaign_id"] = campaign_id
        if username:
            task_params["username"] = username

        # Create Task
        new_task = Task(
            uuid=file_uuid,
            file_name=file.filename,
            url=object_name, 
            status="pending",
            task_type="transcription",
            task_params=task_params,
            language="es" 
        )
        db.add(new_task)
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
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

