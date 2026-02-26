from app.core.limiter import limiter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session


from app.core.database import get_db
from app.models import GlobalApiKey
from app.middleware.auth import get_api_key
# Removed schema import

router = APIRouter(prefix="/agent-identification", tags=["Agent ID"], dependencies=[Depends(get_api_key)])


@router.get(
    "/{task_uuid}",
    summary="Identify the agent in a call recording",
    description="Analyzes the call transcription to identify which agent (operator) handled the interaction, "
                "matching voice/text patterns against known agent profiles stored in the platform.",
)
@limiter.limit("20/minute")
def get_identification(request: Request, task_uuid: str, db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
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
