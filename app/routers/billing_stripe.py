"""
Stripe billing endpoints — subscription management and webhook handling.

Required environment variables:
    STRIPE_SECRET_KEY       — Stripe secret key (sk_live_... or sk_test_...)
    STRIPE_PUBLISHABLE_KEY  — Stripe publishable key (pk_live_... or pk_test_...)
    STRIPE_WEBHOOK_SECRET   — Stripe webhook signing secret (whsec_...)
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.config import get_settings
from app.core.limiter import limiter
from app.middleware.auth import get_api_key
from app.models import GlobalApiKey
from app.schemas.billing import StripeCheckoutRequest, StripePortalRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing/stripe", tags=["Billing Stripe"])

# ---------------------------------------------------------------------------
# Plans catalog (static — enriched with Stripe price IDs when available)
# ---------------------------------------------------------------------------

PLANS_CATALOG = [
    {
        "id": "starter",
        "name": "Starter",
        "audio_minutes": 500,
        "price_usd": 49,
        "overage_per_min": 0.10,
        "description": "Ideal para equipos pequeños",
    },
    {
        "id": "growth",
        "name": "Growth",
        "audio_minutes": 2000,
        "price_usd": 149,
        "overage_per_min": 0.08,
        "description": "Para operaciones en crecimiento",
    },
    {
        "id": "enterprise",
        "name": "Enterprise",
        "audio_minutes": 10000,
        "price_usd": 599,
        "overage_per_min": 0.06,
        "description": "Volumen alto, soporte prioritario",
    },
]


def _get_stripe():
    """Return the stripe module or raise if not configured."""
    settings = get_settings()
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Stripe no está configurado. Agrega STRIPE_SECRET_KEY al entorno.",
        )
    try:
        import stripe as _stripe
        _stripe.api_key = settings.STRIPE_SECRET_KEY
        return _stripe
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="La librería stripe no está instalada. Ejecuta: pip install stripe",
        )


def _get_current_subscription(db: Session) -> Optional[dict]:
    """Read BillingSubscription from DB (single-tenant)."""
    try:
        row = db.execute(
            text("""
                SELECT id, stripe_customer_id, stripe_subscription_id, stripe_price_id,
                       stripe_product_id, plan_name, plan_display_name,
                       included_audio_minutes, overage_rate_usd_per_minute,
                       status, current_period_start, current_period_end,
                       trial_end, cancel_at_period_end, metadata_json,
                       created_at, updated_at
                FROM billing_subscriptions
                ORDER BY id DESC
                LIMIT 1
            """)
        ).fetchone()
    except Exception:
        return None

    if not row:
        return None

    return {
        "id": row[0],
        "stripe_customer_id": row[1],
        "stripe_subscription_id": row[2],
        "stripe_price_id": row[3],
        "stripe_product_id": row[4],
        "plan_name": row[5],
        "plan_display_name": row[6],
        "included_audio_minutes": row[7],
        "overage_rate_usd_per_minute": row[8],
        "status": row[9],
        "current_period_start": row[10].isoformat() if row[10] else None,
        "current_period_end": row[11].isoformat() if row[11] else None,
        "trial_end": row[12].isoformat() if row[12] else None,
        "cancel_at_period_end": row[13],
        "metadata_json": json.loads(row[14]) if row[14] else None,
        "created_at": row[15].isoformat() if row[15] else None,
        "updated_at": row[16].isoformat() if row[16] else None,
    }


def _upsert_subscription(db: Session, data: dict) -> None:
    """Insert or update the billing_subscriptions row."""
    existing = db.execute(
        text("SELECT id FROM billing_subscriptions ORDER BY id DESC LIMIT 1")
    ).fetchone()

    meta_json = json.dumps(data.get("metadata_json")) if data.get("metadata_json") else None

    if existing:
        db.execute(
            text("""
                UPDATE billing_subscriptions SET
                    stripe_customer_id        = :customer_id,
                    stripe_subscription_id    = :subscription_id,
                    stripe_price_id           = :price_id,
                    stripe_product_id         = :product_id,
                    plan_name                 = :plan_name,
                    plan_display_name         = :plan_display_name,
                    included_audio_minutes    = :included_audio_minutes,
                    overage_rate_usd_per_minute = :overage_rate,
                    status                    = :status,
                    current_period_start      = :period_start,
                    current_period_end        = :period_end,
                    trial_end                 = :trial_end,
                    cancel_at_period_end      = :cancel_at_period_end,
                    metadata_json             = :metadata_json,
                    updated_at                = NOW()
                WHERE id = :id
            """),
            {
                "id": existing[0],
                "customer_id": data.get("stripe_customer_id"),
                "subscription_id": data.get("stripe_subscription_id"),
                "price_id": data.get("stripe_price_id"),
                "product_id": data.get("stripe_product_id"),
                "plan_name": data.get("plan_name", "custom"),
                "plan_display_name": data.get("plan_display_name"),
                "included_audio_minutes": data.get("included_audio_minutes"),
                "overage_rate": data.get("overage_rate_usd_per_minute"),
                "status": data.get("status", "active"),
                "period_start": data.get("current_period_start"),
                "period_end": data.get("current_period_end"),
                "trial_end": data.get("trial_end"),
                "cancel_at_period_end": data.get("cancel_at_period_end", False),
                "metadata_json": meta_json,
            },
        )
    else:
        db.execute(
            text("""
                INSERT INTO billing_subscriptions
                    (stripe_customer_id, stripe_subscription_id, stripe_price_id,
                     stripe_product_id, plan_name, plan_display_name,
                     included_audio_minutes, overage_rate_usd_per_minute,
                     status, current_period_start, current_period_end,
                     trial_end, cancel_at_period_end, metadata_json,
                     created_at, updated_at)
                VALUES
                    (:customer_id, :subscription_id, :price_id, :product_id,
                     :plan_name, :plan_display_name, :included_audio_minutes,
                     :overage_rate, :status, :period_start, :period_end,
                     :trial_end, :cancel_at_period_end, :metadata_json,
                     NOW(), NOW())
            """),
            {
                "customer_id": data.get("stripe_customer_id"),
                "subscription_id": data.get("stripe_subscription_id"),
                "price_id": data.get("stripe_price_id"),
                "product_id": data.get("stripe_product_id"),
                "plan_name": data.get("plan_name", "custom"),
                "plan_display_name": data.get("plan_display_name"),
                "included_audio_minutes": data.get("included_audio_minutes"),
                "overage_rate": data.get("overage_rate_usd_per_minute"),
                "status": data.get("status", "active"),
                "period_start": data.get("current_period_start"),
                "period_end": data.get("current_period_end"),
                "trial_end": data.get("trial_end"),
                "cancel_at_period_end": data.get("cancel_at_period_end", False),
                "metadata_json": meta_json,
            },
        )
    db.commit()


# ---------------------------------------------------------------------------
# GET /billing/stripe/config  (public — no auth)
# ---------------------------------------------------------------------------

@router.get(
    "/config",
    summary="Stripe configuration status",
    description="Returns the Stripe publishable key and whether Stripe is configured. No auth required.",
)
@limiter.limit("30/minute")
def get_stripe_config(request: Request):
    settings = get_settings()
    return {
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY or None,
        "stripe_configured": bool(settings.STRIPE_SECRET_KEY),
    }


# ---------------------------------------------------------------------------
# GET /billing/stripe/plans
# ---------------------------------------------------------------------------

@router.get(
    "/plans",
    summary="Available billing plans",
    description="Returns available plans enriched with Stripe price IDs when Stripe is configured.",
    dependencies=[Depends(get_api_key)],
)
@limiter.limit("30/minute")
def get_stripe_plans(
    request: Request,
    api_key: GlobalApiKey = Depends(get_api_key),
):
    settings = get_settings()
    plans = [p.copy() for p in PLANS_CATALOG]

    if settings.STRIPE_SECRET_KEY:
        try:
            import stripe as _stripe
            _stripe.api_key = settings.STRIPE_SECRET_KEY
            prices = _stripe.Price.list(active=True, expand=["data.product"])
            stripe_prices = {p.product.name.lower(): p.id for p in prices.data if p.product}
            for plan in plans:
                plan["stripe_price_id"] = stripe_prices.get(plan["name"].lower())
        except Exception as e:
            logger.warning("Could not fetch Stripe prices: %s", e)
            for plan in plans:
                plan["stripe_price_id"] = None
    else:
        for plan in plans:
            plan["stripe_price_id"] = None

    return {"plans": plans, "stripe_configured": bool(settings.STRIPE_SECRET_KEY)}


# ---------------------------------------------------------------------------
# GET /billing/stripe/subscription
# ---------------------------------------------------------------------------

@router.get(
    "/subscription",
    summary="Current subscription status",
    description="Returns the current billing subscription, enriched with live Stripe data if available.",
    dependencies=[Depends(get_api_key)],
)
@limiter.limit("10/minute")
def get_stripe_subscription(
    request: Request,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    settings = get_settings()
    sub = _get_current_subscription(db)

    if sub and sub.get("stripe_subscription_id") and settings.STRIPE_SECRET_KEY:
        try:
            import stripe as _stripe
            _stripe.api_key = settings.STRIPE_SECRET_KEY
            stripe_sub = _stripe.Subscription.retrieve(sub["stripe_subscription_id"])
            sub["status"] = stripe_sub.status
            sub["current_period_start"] = datetime.fromtimestamp(
                stripe_sub.current_period_start
            ).isoformat()
            sub["current_period_end"] = datetime.fromtimestamp(
                stripe_sub.current_period_end
            ).isoformat()
            sub["cancel_at_period_end"] = stripe_sub.cancel_at_period_end
        except Exception as e:
            logger.warning("Could not fetch Stripe subscription: %s", e)

    return {"subscription": sub, "stripe_configured": bool(settings.STRIPE_SECRET_KEY)}


# ---------------------------------------------------------------------------
# POST /billing/stripe/checkout
# ---------------------------------------------------------------------------

@router.post(
    "/checkout",
    summary="Create a Stripe Checkout session",
    description="Creates a Stripe Checkout session for the given price and redirects the client.",
    dependencies=[Depends(get_api_key)],
)
@limiter.limit("5/minute")
def create_stripe_checkout(
    body: StripeCheckoutRequest,
    request: Request,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    stripe = _get_stripe()

    try:
        # Find or create Stripe customer
        sub = _get_current_subscription(db)
        customer_id = sub["stripe_customer_id"] if sub else None

        if not customer_id:
            customer = stripe.Customer.create(
                metadata={"source": "auditoria_api"}
            )
            customer_id = customer.id

        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": body.price_id, "quantity": 1}],
            mode="subscription",
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={"plan_name": body.plan_name},
        )

        # Persist subscription record as "incomplete"
        plan_info = next((p for p in PLANS_CATALOG if p["id"] == body.plan_name), {})
        _upsert_subscription(
            db,
            {
                "stripe_customer_id": customer_id,
                "stripe_price_id": body.price_id,
                "plan_name": body.plan_name,
                "plan_display_name": plan_info.get("name"),
                "included_audio_minutes": plan_info.get("audio_minutes"),
                "overage_rate_usd_per_minute": plan_info.get("overage_per_min"),
                "status": "incomplete",
            },
        )

        return {"checkout_url": session.url}

    except Exception as e:
        logger.error("Stripe checkout error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /billing/stripe/customer-portal
# ---------------------------------------------------------------------------

@router.post(
    "/customer-portal",
    summary="Create a Stripe Customer Portal session",
    description="Opens the Stripe Customer Portal so the user can manage their subscription.",
    dependencies=[Depends(get_api_key)],
)
@limiter.limit("5/minute")
def create_stripe_portal(
    body: StripePortalRequest,
    request: Request,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key),
):
    stripe = _get_stripe()

    sub = _get_current_subscription(db)
    if not sub or not sub.get("stripe_customer_id"):
        raise HTTPException(
            status_code=400,
            detail="No hay suscripción activa. Contrata un plan primero.",
        )

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=sub["stripe_customer_id"],
            return_url=body.return_url,
        )
        return {"portal_url": portal_session.url}

    except Exception as e:
        logger.error("Stripe portal error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /billing/stripe/webhooks  (no auth — verified by Stripe signature)
# ---------------------------------------------------------------------------

@router.post(
    "/webhooks",
    summary="Stripe webhook endpoint",
    description=(
        "Receives and processes Stripe events. "
        "Verifies the request signature using STRIPE_WEBHOOK_SECRET."
    ),
    include_in_schema=False,  # Hidden from OpenAPI/MCP — internal Stripe endpoint
)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    try:
        import stripe as _stripe
        _stripe.api_key = settings.STRIPE_SECRET_KEY
    except ImportError:
        raise HTTPException(status_code=503, detail="stripe library not installed")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = _stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET or ""
        )
    except Exception as e:
        logger.warning("Stripe webhook signature verification failed: %s", e)
        raise HTTPException(status_code=400, detail=f"Webhook signature invalid: {e}")

    event_type = event["type"]
    data_obj = event["data"]["object"]

    logger.info("Stripe webhook received: %s", event_type)

    try:
        if event_type == "checkout.session.completed":
            _handle_checkout_completed(db, data_obj)

        elif event_type == "customer.subscription.updated":
            _handle_subscription_updated(db, data_obj)

        elif event_type == "customer.subscription.deleted":
            _handle_subscription_deleted(db, data_obj)

        elif event_type == "invoice.payment_succeeded":
            _handle_payment_succeeded(db, data_obj)

        elif event_type == "invoice.payment_failed":
            _handle_payment_failed(db, data_obj)

        else:
            logger.debug("Unhandled Stripe event: %s", event_type)

    except Exception as e:
        logger.error("Error processing Stripe event %s: %s", event_type, e)
        # Return 200 to avoid Stripe retries for non-critical errors
        return {"received": True, "error": str(e)}

    return {"received": True}


# ---------------------------------------------------------------------------
# Webhook handlers
# ---------------------------------------------------------------------------

def _handle_checkout_completed(db: Session, session_obj: dict) -> None:
    subscription_id = session_obj.get("subscription")
    customer_id = session_obj.get("customer")
    plan_name = (session_obj.get("metadata") or {}).get("plan_name", "custom")

    plan_info = next((p for p in PLANS_CATALOG if p["id"] == plan_name), {})
    _upsert_subscription(
        db,
        {
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": subscription_id,
            "plan_name": plan_name,
            "plan_display_name": plan_info.get("name"),
            "included_audio_minutes": plan_info.get("audio_minutes"),
            "overage_rate_usd_per_minute": plan_info.get("overage_per_min"),
            "status": "active",
        },
    )


def _handle_subscription_updated(db: Session, sub_obj: dict) -> None:
    import stripe as _stripe

    period_start = datetime.fromtimestamp(sub_obj["current_period_start"]) if sub_obj.get("current_period_start") else None
    period_end = datetime.fromtimestamp(sub_obj["current_period_end"]) if sub_obj.get("current_period_end") else None
    trial_end = datetime.fromtimestamp(sub_obj["trial_end"]) if sub_obj.get("trial_end") else None

    _upsert_subscription(
        db,
        {
            "stripe_customer_id": sub_obj.get("customer"),
            "stripe_subscription_id": sub_obj.get("id"),
            "stripe_price_id": (sub_obj.get("items", {}).get("data") or [{}])[0].get("price", {}).get("id"),
            "status": sub_obj.get("status", "active"),
            "current_period_start": period_start,
            "current_period_end": period_end,
            "trial_end": trial_end,
            "cancel_at_period_end": sub_obj.get("cancel_at_period_end", False),
        },
    )


def _handle_subscription_deleted(db: Session, sub_obj: dict) -> None:
    _upsert_subscription(
        db,
        {
            "stripe_customer_id": sub_obj.get("customer"),
            "stripe_subscription_id": sub_obj.get("id"),
            "status": "cancelled",
            "cancel_at_period_end": False,
        },
    )


def _handle_payment_succeeded(db: Session, invoice_obj: dict) -> None:
    try:
        row = db.execute(
            text("SELECT id, metadata_json FROM billing_subscriptions ORDER BY id DESC LIMIT 1")
        ).fetchone()
        if not row:
            return
        existing_meta = json.loads(row[1]) if row[1] else {}
        existing_meta.setdefault("payment_history", []).append(
            {
                "event": "payment_succeeded",
                "invoice_id": invoice_obj.get("id"),
                "amount_paid": invoice_obj.get("amount_paid", 0) / 100,
                "ts": datetime.utcnow().isoformat(),
            }
        )
        # Keep last 10 payments only
        existing_meta["payment_history"] = existing_meta["payment_history"][-10:]
        db.execute(
            text("UPDATE billing_subscriptions SET metadata_json = :meta WHERE id = :id"),
            {"meta": json.dumps(existing_meta), "id": row[0]},
        )
        db.commit()
    except Exception as e:
        logger.warning("Could not log payment_succeeded: %s", e)


def _handle_payment_failed(db: Session, invoice_obj: dict) -> None:
    _upsert_subscription(
        db,
        {
            "stripe_customer_id": invoice_obj.get("customer"),
            "status": "past_due",
        },
    )
