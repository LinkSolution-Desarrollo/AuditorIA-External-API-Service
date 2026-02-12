from app.core.limiter import limiter
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.models import GlobalApiKey
from app.middleware.auth import get_api_key

class AuditRequest(BaseModel):
    task_uuid: str
    is_call: bool = True

router = APIRouter(prefix="/audit", tags=["Audit"])

@router.post("/generate")
@limiter.limit("10/minute")
def generate_audit(audit_req: AuditRequest, request: Request, db: Session = Depends(get_db), api_key = Depends(get_api_key)):
    from app.services.audit_service import AuditService
    try:
        if audit_req.is_call:
            result = AuditService.generate_audit_for_call(db, audit_req.task_uuid)
        else:
            result = AuditService.generate_audit_for_chat(db, audit_req.task_uuid)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "ERROR", "message": str(e)})
