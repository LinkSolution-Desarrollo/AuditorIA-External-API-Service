from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.models import GlobalApiKey
from app.middleware.auth import get_api_key
from app.schemas.tags import TagsResponse

router = APIRouter(prefix="/tags", tags=["Tags"], dependencies=[Depends(get_api_key)])
limiter = Limiter(key_func=get_remote_address)

@router.get("/{task_uuid}", response_model=TagsResponse)
@limiter.limit("20/minute")
def get_tags(req: Request, task_uuid: str, generate_new: bool = Query(False), db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    from app.services.tags_service import TagsService
    try:
        tags_data = TagsService.get_tags(db, task_uuid, generate_new)
        return {
            "success": True,
            "tags": tags_data.get("tags", []),
            "extraTags": tags_data.get("extraTags", [])
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
