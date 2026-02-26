from app.core.limiter import limiter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional


from app.core.database import get_db
from app.models import GlobalApiKey
from app.middleware.auth import get_api_key
# Removed schema import
from app.services.reports_service import ReportsService

router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(get_api_key)])


@router.get(
    "/tasks",
    summary="Get task processing statistics",
    description="Returns counts of tasks by status (pending, processing, completed, failed) "
                "for the last N days. Useful for monitoring pipeline health and throughput.",
)
@limiter.limit("30/minute")
def get_task_stats(request: Request, days: int = Query(30), db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    try:
        return ReportsService.get_task_stats(db, days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/audits",
    summary="Get audit quality statistics",
    description="Returns aggregate quality metrics for audits performed in the last N days: "
                "total audits, average score, failure count, and failure rate.",
)
@limiter.limit("30/minute")
def get_audit_stats(request: Request, days: int = Query(30), db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    try:
        return ReportsService.get_audit_stats(db, days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/summary",
    summary="Get combined platform summary report",
    description="Returns a single combined report with both task processing stats and audit quality metrics "
                "for the last N days. Use this for a quick platform health overview.",
)
@limiter.limit("10/minute")
def get_summary(request: Request, days: int = Query(30), db: Session = Depends(get_db), api_key: GlobalApiKey = Depends(get_api_key)):
    try:
        from datetime import datetime
        task_stats = ReportsService.get_task_stats(db, days)
        audit_stats = ReportsService.get_audit_stats(db, days)
        return {"tasks": task_stats, "audits": audit_stats, "generated_at": datetime.utcnow()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
