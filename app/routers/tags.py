from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.limiter import limiter
from app.middleware.auth import get_api_key

router = APIRouter(prefix="/tags", tags=["Tags"])

@router.get("/{task_uuid}")
@limiter.limit("20/minute")
def get_tags(request: Request, task_uuid: str, generate_new: bool = Query(False), db: Session = Depends(get_db), api_key = Depends(get_api_key)):
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
