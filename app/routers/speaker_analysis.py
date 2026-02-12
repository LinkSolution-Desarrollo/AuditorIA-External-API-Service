from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.models import GlobalApiKey
from app.middleware.auth import get_api_key
from app.schemas.speaker_analysis import SpeakerAnalysisResponse

router = APIRouter(prefix="/speaker-analysis", tags=["Speaker Analysis"], dependencies=[Depends(get_api_key)])
limiter = Limiter(key_func=get_remote_address)

@router.get("/{task_uuid}", response_model=SpeakerAnalysisResponse)
@limiter.limit("20/minute")
def get_analysis(req: Request, task_uuid: str, generate_new: bool = Query(False), db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    from app.services.speaker_analysis_service import SpeakerAnalysisService
    try:
        analysis = SpeakerAnalysisService.get_analysis(db, task_uuid)
        return {
            "success": True,
            "task_uuid": task_uuid,
            "analysis": analysis if isinstance(analysis, dict) else {}
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
