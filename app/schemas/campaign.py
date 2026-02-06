from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CampaignSummary(BaseModel):
    campaign_id: int
    campaign_name: str
    description: Optional[str] = None
    
    class Config:
        orm_mode = True
