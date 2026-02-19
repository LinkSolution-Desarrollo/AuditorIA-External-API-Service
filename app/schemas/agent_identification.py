from pydantic import BaseModel
from typing import Dict

class AgentIdentificationResponse(BaseModel):
    success: bool
    task_uuid: str
    identification: Dict[str, str]
