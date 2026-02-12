from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.database import get_db
from app.models import GlobalApiKey
from app.middleware.auth import get_api_key
from app.schemas.reports import TaskStatsResponse, AuditStatsResponse, ReportSummaryResponse
from app.services.reports_service import ReportsService

router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(get_api_key)])
limiter = Limiter(key_func=get_remote_address)

@router.get("/tasks", response_model=TaskStatsResponse)
@limiter.limit("30/minute")
def get_task_stats(request: Request, days: int = Query(30), db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    try:
        return ReportsService.get_task_stats(db, days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/audits", response_model=AuditStatsResponse)
@limiter.limit("30/minute")
def get_audit_stats(request: Request, days: int = Query(30), db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    try:
        return ReportsService.get_audit_stats(db, days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary", response_model=ReportSummaryResponse)
@limiter.limit("10/minute")
def get_summary(request: Request, days: int = Query(30), db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    try:
        from datetime import datetime
        task_stats = ReportsService.get_task_stats(db, days)
        audit_stats = ReportsService.get_audit_stats(db, days)
        return {"tasks": task_stats, "audits": audit_stats, "generated_at": datetime.utcnow()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
