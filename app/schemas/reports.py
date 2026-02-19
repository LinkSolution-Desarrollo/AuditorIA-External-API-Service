from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TaskStatsResponse(BaseModel):
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    period_days: int

class AuditStatsResponse(BaseModel):
    total_audits: int
    average_score: float
    failure_count: int
    failure_rate: float

class ReportSummaryResponse(BaseModel):
    tasks: TaskStatsResponse
    audits: AuditStatsResponse
    generated_at: datetime
