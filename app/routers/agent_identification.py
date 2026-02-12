from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.models import GlobalApiKey
from app.middleware.auth import get_api_key
from app.schemas.agent_identification import AgentIdentificationResponse

router = APIRouter(prefix="/agent-identification", tags=["Agent ID"], dependencies=[Depends(get_api_key)])
limiter = Limiter(key_func=get_remote_address)

@router.get("/{task_uuid}", response_model=AgentIdentificationResponse)
@limiter.limit("20/minute")
def get_identification(req: Request, task_uuid: str, db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    from app.services.agent_identification_service import AgentIdentificationService
    try:
        ident = AgentIdentificationService.get_identification(db, task_uuid)
        return {
            "success": True,
            "task_uuid": task_uuid,
            "identification": ident if isinstance(ident, dict) else {}
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
