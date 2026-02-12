from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

class ReportsService:
    @staticmethod
    def get_task_stats(db: Session, days: int = 30) -> dict:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        query = text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM tasks
            WHERE created_at >= :start_date AND created_at <= :end_date
        """)
        result = db.execute(query, {"start_date": start_date, "end_date": end_date}).fetchone()
        return {
            "total": result[0] or 0,
            "pending": result[1] or 0,
            "processing": result[2] or 0,
            "completed": result[3] or 0,
            "failed": result[4] or 0,
            "period_days": days
        }

    @staticmethod
    def get_audit_stats(db: Session, days: int = 30) -> dict:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        query = text("""
            SELECT
                COUNT(*) as total,
                AVG(score) as avg_score,
                SUM(CASE WHEN is_audit_failure = true THEN 1 ELSE 0 END) as failures
            FROM audits
            WHERE created_at >= :start_date AND created_at <= :end_date
        """)
        result = db.execute(query, {"start_date": start_date, "end_date": end_date}).fetchone()
        total = result[0] or 0
        failures = result[2] or 0
        return {
            "total_audits": total,
            "average_score": round(float(result[1] or 0), 2),
            "failure_count": failures,
            "failure_rate": round(failures / total, 2) if total > 0 else 0.0
        }
