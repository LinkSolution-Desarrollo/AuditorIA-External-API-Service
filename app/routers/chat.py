from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import cast, String
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.models import GlobalApiKey, Task
from app.middleware.auth import get_api_key
from app.services.ai_chat_service import AIChatService
from app.schemas.chat import ChatRequest, ChatHistoryResponse, ChatMessage

router = APIRouter(
    prefix="/tasks",
    tags=["AI Chat"],
    dependencies=[Depends(get_api_key)]
)

limiter = Limiter(key_func=get_remote_address)

def verify_task_ownership(db: Session, uuid: str, api_key_id: int):
    task = db.query(Task).filter(
        Task.uuid == uuid,
        cast(Task.task_params['api_key_id'], String) == str(api_key_id)
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or access denied")
    return task

@router.post("/{uuid}/chat")
@limiter.limit("5/minute")
async def chat_with_transcription(
    request: Request,
    uuid: str,
    chat_req: ChatRequest,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key)
):
    """
    Chat with the AI about the transcription.
    """
    verify_task_ownership(db, uuid, api_key.id)
    
    try:
        response_text = AIChatService.process_chat(db, uuid, chat_req.chat_input)
        return {"response": response_text}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{uuid}/chat", response_model=ChatHistoryResponse)
@limiter.limit("10/minute")
def get_chat_history(
    request: Request,
    uuid: str,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key)
):
    """
    Get chat history for a task.
    """
    verify_task_ownership(db, uuid, api_key.id)
    
    records = AIChatService.get_history(db, uuid)
    return {"messages": records}
