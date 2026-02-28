"""
Billing Usage endpoints — audio minutes summary and campaign limits.
"""
import calendar
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.limiter import limiter
from app.middleware.auth import get_api_key
from app.models import GlobalApiKey
from app.schemas.billing import CampaignLimitUpdate

router = APIRouter(
    prefix="/billing-usage",
    tags=["Billing Usage"],
    dependencies=[Depends(get_api_key)],
)

# Approximate GPT-4o-mini cost rate
_COST_PER_1K_TOKENS = 0.002


def _current_month_range() -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    last_day = calendar.monthrange(now.year, now.month)[1]
    month_end = datetime(now.year, now.month, last_day, 23, 59, 59)
    return month_start, month_end


# ---------------------------------------------------------------------------
# GET /billing-usage/audio-minutes-summary
# ---------------------------------------------------------------------------

@router.get(
    "/audio-minutes-summary",
    summary="Audio minutes processed per campaign",
    description=(
        "Returns audio minutes processed (from call audits) per campaign for a given period. "
        "period_from / period_to accept YYYY-MM-DD; defaults to the current calendar month."
    ),
)
@limiter.limit("30/minute")
def get_audio_minutes_summary(
    request: Request,
    period_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    period_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    try:
        now = datetime.utcnow()
        if period_from:
            pf = datetime.strptime(period_from, "%Y-%m-%d")
        else:
            pf = datetime(now.year, now.month, 1)

        if period_to:
            pt = datetime.strptime(period_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
        else:
            last_day = calendar.monthrange(now.year, now.month)[1]
            pt = datetime(now.year, now.month, last_day, 23, 59, 59)

        query = text("""
            SELECT
                a.campaign_id,
                COALESCE(c.campaign_name, 'Sin campaña') AS campaign_name,
                COALESCE(SUM(t.audio_duration / 60.0), 0) AS audio_minutes,
                COUNT(a.id) AS call_audits,
                COALESCE(SUM(a.input_tokens), 0) AS input_tokens,
                COALESCE(SUM(a.output_tokens), 0) AS output_tokens
            FROM audits a
            LEFT JOIN tasks t ON a.task_uuid = t.uuid
            LEFT JOIN campaigns c ON a.campaign_id = c.campaign_id
            WHERE a.created_at >= :period_from
              AND a.created_at <= :period_to
              AND t.audio_duration IS NOT NULL
              AND t.audio_duration > 0
            GROUP BY a.campaign_id, c.campaign_name
            ORDER BY audio_minutes DESC
        """)

        rows = db.execute(query, {"period_from": pf, "period_to": pt}).fetchall()

        items = []
        for row in rows:
            campaign_id = row[0]
            campaign_name = row[1]
            audio_minutes = float(row[2] or 0)
            call_audits = int(row[3] or 0)
            input_tokens = int(row[4] or 0)
            output_tokens = int(row[5] or 0)
            total_tokens = input_tokens + output_tokens
            estimated_cost = total_tokens / 1000 * _COST_PER_1K_TOKENS

            items.append(
                {
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "audio_minutes": round(audio_minutes, 2),
                    "call_audits": call_audits,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "estimated_cost_usd": round(estimated_cost, 4),
                    "tokens_per_audio_minute": (
                        round(total_tokens / audio_minutes, 2) if audio_minutes > 0 else 0
                    ),
                    "cost_per_audio_minute": (
                        round(estimated_cost / audio_minutes, 4) if audio_minutes > 0 else 0
                    ),
                }
            )

        return {
            "items": items,
            "period_from": pf.isoformat(),
            "period_to": pt.isoformat(),
            "total_audio_minutes": round(sum(i["audio_minutes"] for i in items), 2),
            "total_call_audits": sum(i["call_audits"] for i in items),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /billing-usage/campaign-limits
# ---------------------------------------------------------------------------

@router.get(
    "/campaign-limits",
    summary="Campaign billing limits with current month usage",
    description=(
        "Lists all campaigns with their configured billing limits and "
        "audio-minutes / tokens / USD consumed in the current calendar month."
    ),
)
@limiter.limit("30/minute")
def get_campaign_limits(
    request: Request,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    try:
        now = datetime.utcnow()
        month_start, month_end = _current_month_range()
        period_month = now.strftime("%Y-%m")

        # All campaigns + left join with limits
        camps_query = text("""
            SELECT
                c.campaign_id,
                c.campaign_name,
                cbl.monthly_audio_minutes_limit,
                cbl.monthly_token_limit,
                cbl.monthly_usd_limit,
                cbl.enforcement_mode,
                cbl.alert_threshold_pct
            FROM campaigns c
            LEFT JOIN campaign_billing_limits cbl ON cbl.campaign_id = c.campaign_id
            ORDER BY c.campaign_name
        """)
        campaigns = db.execute(camps_query).fetchall()

        # Audio minutes per campaign for current month
        audio_query = text("""
            SELECT
                a.campaign_id,
                COALESCE(SUM(t.audio_duration / 60.0), 0) AS audio_minutes
            FROM audits a
            LEFT JOIN tasks t ON a.task_uuid = t.uuid
            WHERE a.created_at >= :month_start
              AND a.created_at <= :month_end
              AND t.audio_duration IS NOT NULL
              AND t.audio_duration > 0
            GROUP BY a.campaign_id
        """)
        audio_rows = db.execute(
            audio_query, {"month_start": month_start, "month_end": month_end}
        ).fetchall()
        audio_by_campaign = {row[0]: float(row[1] or 0) for row in audio_rows}

        # Tokens + USD per campaign from ai_usage_events (best-effort — table may not exist)
        tokens_by_campaign: dict = {}
        try:
            token_query = text("""
                SELECT
                    campaign_id,
                    COALESCE(SUM(total_tokens), 0) AS tokens_used,
                    COALESCE(SUM(estimated_cost_usd), 0) AS usd_used
                FROM ai_usage_events
                WHERE created_at >= :month_start
                  AND created_at <= :month_end
                GROUP BY campaign_id
            """)
            token_rows = db.execute(
                token_query, {"month_start": month_start, "month_end": month_end}
            ).fetchall()
            tokens_by_campaign = {
                row[0]: {"tokens": int(row[1] or 0), "usd": float(row[2] or 0)}
                for row in token_rows
            }
        except Exception:
            pass

        results = []
        for row in campaigns:
            campaign_id = row[0]
            campaign_name = row[1]
            audio_limit = row[2]
            token_limit = row[3]
            usd_limit = row[4]
            enforcement_mode = row[5] or "soft"
            alert_threshold_pct = row[6] if row[6] is not None else 80

            audio_used = audio_by_campaign.get(campaign_id, 0.0)
            td = tokens_by_campaign.get(campaign_id, {"tokens": 0, "usd": 0.0})
            tokens_used = td["tokens"]
            usd_used = td["usd"]

            pct_audio = round(audio_used / audio_limit * 100, 1) if audio_limit else None
            pct_tokens = round(tokens_used / token_limit * 100, 1) if token_limit else None
            pct_usd = round(usd_used / usd_limit * 100, 1) if usd_limit else None

            max_pct = max(pct_audio or 0, pct_tokens or 0, pct_usd or 0)
            if max_pct >= 100:
                quota_status = "exceeded"
            elif max_pct >= alert_threshold_pct:
                quota_status = "warning"
            else:
                quota_status = "ok"

            has_limit = any(v is not None for v in (audio_limit, token_limit, usd_limit, row[5]))
            limit_config = (
                {
                    "monthly_audio_minutes_limit": audio_limit,
                    "monthly_token_limit": token_limit,
                    "monthly_usd_limit": usd_limit,
                    "enforcement_mode": enforcement_mode,
                    "alert_threshold_pct": alert_threshold_pct,
                }
                if has_limit
                else None
            )

            results.append(
                {
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "limit": limit_config,
                    "usage": {
                        "audio_minutes_used": round(audio_used, 2),
                        "tokens_used": tokens_used,
                        "usd_used": round(usd_used, 4),
                        "pct_audio_minutes": pct_audio,
                        "pct_tokens": pct_tokens,
                        "pct_usd": pct_usd,
                    },
                    "quota_status": quota_status,
                    "period_month": period_month,
                }
            )

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# PUT /billing-usage/campaign-limits/{campaign_id}
# ---------------------------------------------------------------------------

@router.put(
    "/campaign-limits/{campaign_id}",
    summary="Create or update billing limits for a campaign",
    description=(
        "Upserts the billing limits for the given campaign. "
        "Pass null for any limit to make it unlimited."
    ),
)
@limiter.limit("10/minute")
def update_campaign_limit(
    campaign_id: int,
    body: CampaignLimitUpdate,
    request: Request,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    try:
        # Verify campaign exists
        camp_check = db.execute(
            text("SELECT campaign_id FROM campaigns WHERE campaign_id = :cid"),
            {"cid": campaign_id},
        ).fetchone()
        if not camp_check:
            raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

        upsert_query = text("""
            INSERT INTO campaign_billing_limits
                (campaign_id, monthly_audio_minutes_limit, monthly_token_limit,
                 monthly_usd_limit, enforcement_mode, alert_threshold_pct,
                 created_at, updated_at)
            VALUES
                (:campaign_id, :audio_limit, :token_limit, :usd_limit,
                 :enforcement_mode, :alert_pct, NOW(), NOW())
            ON CONFLICT (campaign_id) DO UPDATE SET
                monthly_audio_minutes_limit = EXCLUDED.monthly_audio_minutes_limit,
                monthly_token_limit         = EXCLUDED.monthly_token_limit,
                monthly_usd_limit           = EXCLUDED.monthly_usd_limit,
                enforcement_mode            = EXCLUDED.enforcement_mode,
                alert_threshold_pct         = EXCLUDED.alert_threshold_pct,
                updated_at                  = NOW()
        """)
        db.execute(
            upsert_query,
            {
                "campaign_id": campaign_id,
                "audio_limit": body.monthly_audio_minutes_limit,
                "token_limit": body.monthly_token_limit,
                "usd_limit": body.monthly_usd_limit,
                "enforcement_mode": body.enforcement_mode,
                "alert_pct": body.alert_threshold_pct,
            },
        )
        db.commit()

        return {
            "success": True,
            "campaign_id": campaign_id,
            "message": "Campaign billing limits updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
