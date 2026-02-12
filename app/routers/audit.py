from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.models import GlobalApiKey
from app.middleware.auth import get_api_key
from app.schemas.audit import AuditRequest, AuditResponse

router = APIRouter(prefix="/audit", tags=["Audit"], dependencies=[Depends(get_api_key)])
limiter = Limiter(key_func=get_remote_address)

@router.post("/generate", response_model=AuditResponse)
@limiter.limit("10/minute")
def generate_audit(request: AuditRequest, req: Request, db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    from app.services.audit_service import AuditService
    try:
        if request.is_call:
            result = AuditService.generate_audit_for_call(db, request.task_uuid)
        else:
            result = AuditService.generate_audit_for_chat(db, request.task_uuid)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "ERROR", "message": str(e)})
