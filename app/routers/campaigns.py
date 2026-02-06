from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import List
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.models import Campaign, GlobalApiKey
from app.middleware.auth import get_api_key
from app.schemas.campaign import CampaignSummary

router = APIRouter(
    prefix="/campaigns",
    tags=["Campaigns"],
    dependencies=[Depends(get_api_key)]
)

limiter = Limiter(key_func=get_remote_address)

@router.get("/", response_model=List[CampaignSummary])
@limiter.limit("20/minute")
def list_campaigns(
    request: Request,
    db: Session = Depends(get_db),
    api_key: GlobalApiKey = Depends(get_api_key)
):
    """
    List all available campaigns.
    """
    return db.query(Campaign).all()
