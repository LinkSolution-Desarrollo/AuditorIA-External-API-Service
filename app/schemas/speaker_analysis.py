from pydantic import BaseModel
from typing import Dict

class SpeakerAnalysisResponse(BaseModel):
    success: bool
    task_uuid: str
    analysis: Dict[str, str]
