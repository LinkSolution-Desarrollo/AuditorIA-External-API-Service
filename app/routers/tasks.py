from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, cast, Text
from typing import List, Optional
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.models import Task, GlobalApiKey
from app.middleware.auth import get_api_key
from app.schemas import TaskSummary, TaskDetail

router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
    dependencies=[Depends(get_api_key)]
)

limiter = Limiter(key_func=get_remote_address)

@router.get("/", response_model=List[TaskSummary])
@limiter.limit("20/minute")
def list_tasks(
    request: Request, # Required for limiter
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key)
):
    """
    List tasks created by this API Key.
    """
    # Filtering by JSON in SQLAlchemy
    # We want tasks where task_params -> 'api_key_id' == api_key.id
    # Note: We cast to text because JSON comparison requires text conversion

    tasks = db.query(Task).filter(
        cast(Task.task_params['api_key_id'], Text) == str(api_key.id)
    ).order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    
    return tasks

@router.get("/{task_uuid}", response_model=TaskDetail)
@limiter.limit("60/minute")
def get_task(
    request: Request,
    task_uuid: str,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key)
):
    """
    Get detailed status and result of a specific task.
    """
    task = db.query(Task).filter(
        Task.uuid == task_uuid,
        cast(Task.task_params['api_key_id'], Text) == str(api_key.id)
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task

@router.get("/{task_uuid}/audio")
@limiter.limit("5/minute")
async def get_task_audio(
    request: Request,
    task_uuid: str,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key)
):
    """
    Stream audio file for a given task.
    """
    task = db.query(Task).filter(
        Task.uuid == task_uuid,
        cast(Task.task_params['api_key_id'], Text) == str(api_key.id)
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    settings = get_settings()
    bucket_name = settings.S3_BUCKET
    
    # We stored 'external_uploads/uuid_file' in task.url
    # or sometimes full url? In External API, we save object key in task.url in upload.py
    object_key = task.url 
    
    try:
        from app.services.s3_service import get_s3_object
        s3_obj = get_s3_object(bucket_name, object_key)
        
        if not s3_obj:
             raise HTTPException(status_code=404, detail="Audio file not found in storage")
             
        from fastapi.responses import StreamingResponse
        
        return StreamingResponse(
            s3_obj['Body'],
            media_type=s3_obj.get('ContentType', 'audio/mpeg'),
            headers={
                "Content-Disposition": f"attachment; filename={task.file_name}"
            }
        )
    except Exception as e:
        # If headers already sent, this might fail, but for now...
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{task_uuid}", status_code=204)
@limiter.limit("5/minute")
def delete_task(
    request: Request,
    task_uuid: str,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key)
):
    """
    Delete a task reference from the database.
    WARNING: This currently Soft Deletes or Hard Deletes depending on requirements.
    For now, we will perform a hard delete of the record for 'cleanup'.
    """
    task = db.query(Task).filter(
        Task.uuid == task_uuid,
        cast(Task.task_params['api_key_id'], Text) == str(api_key.id)
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    # TODO: Ideally delete from S3 as well, but that requires importing s3_service
    # and handling potential errors. For now, strict DB cleanup.
    
    db.delete(task)
    db.commit()
    return None
