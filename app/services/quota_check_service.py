"""
QuotaCheckService — verifica cuotas de campaña antes de operaciones AI.

Uso:
    allowed, reason = QuotaCheckService.check_quota(db, campaign_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)
"""
from datetime import datetime
import calendar
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class QuotaCheckService:

    @staticmethod
    def get_campaign_usage_current_month(db: Session, campaign_id: int) -> dict:
        """
        Returns audio_minutes_used, tokens_used, usd_used for the current month.
        """
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        last_day = calendar.monthrange(now.year, now.month)[1]
        month_end = datetime(now.year, now.month, last_day, 23, 59, 59)

        # Audio minutes from audits + tasks join
        audio_query = text("""
            SELECT COALESCE(SUM(t.audio_duration / 60.0), 0) as audio_minutes
            FROM audits a
            LEFT JOIN tasks t ON a.task_uuid = t.uuid
            WHERE a.campaign_id = :campaign_id
              AND a.created_at >= :month_start
              AND a.created_at <= :month_end
              AND t.audio_duration IS NOT NULL
              AND t.audio_duration > 0
        """)
        try:
            audio_row = db.execute(
                audio_query,
                {"campaign_id": campaign_id, "month_start": month_start, "month_end": month_end},
            ).fetchone()
            audio_minutes = float(audio_row[0] or 0)
        except Exception:
            audio_minutes = 0.0

        # Tokens and USD from ai_usage_events
        tokens = 0
        usd = 0.0
        try:
            token_query = text("""
                SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(estimated_cost_usd), 0)
                FROM ai_usage_events
                WHERE campaign_id = :campaign_id
                  AND created_at >= :month_start
                  AND created_at <= :month_end
            """)
            token_row = db.execute(
                token_query,
                {"campaign_id": campaign_id, "month_start": month_start, "month_end": month_end},
            ).fetchone()
            tokens = int(token_row[0] or 0)
            usd = float(token_row[1] or 0)
        except Exception:
            pass

        return {"audio_minutes": audio_minutes, "tokens": tokens, "usd": usd}

    @staticmethod
    def check_quota(db: Session, campaign_id: int) -> tuple[bool, str | None]:
        """
        Returns (allowed, reason).
        - No limit configured → (True, None)
        - enforcement_mode="soft" → (True, None)  [alert only, never blocks]
        - enforcement_mode="hard" and exceeded → (False, "reason message")
        """
        try:
            limit_query = text("""
                SELECT monthly_audio_minutes_limit, monthly_token_limit, monthly_usd_limit,
                       enforcement_mode
                FROM campaign_billing_limits
                WHERE campaign_id = :campaign_id
                LIMIT 1
            """)
            limit_row = db.execute(limit_query, {"campaign_id": campaign_id}).fetchone()
        except Exception:
            return True, None

        if not limit_row:
            return True, None

        audio_limit, token_limit, usd_limit, enforcement_mode = limit_row

        if enforcement_mode != "hard":
            return True, None

        usage = QuotaCheckService.get_campaign_usage_current_month(db, campaign_id)

        if audio_limit is not None and usage["audio_minutes"] >= audio_limit:
            return False, (
                f"Límite de minutos de audio excedido "
                f"({usage['audio_minutes']:.1f}/{audio_limit:.1f} min)"
            )

        if token_limit is not None and usage["tokens"] >= token_limit:
            return False, (
                f"Límite de tokens excedido "
                f"({usage['tokens']}/{token_limit})"
            )

        if usd_limit is not None and usage["usd"] >= usd_limit:
            return False, (
                f"Límite de USD excedido "
                f"(${usage['usd']:.2f}/${usd_limit:.2f})"
            )

        return True, None
