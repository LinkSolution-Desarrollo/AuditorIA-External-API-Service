from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class TaskBase(BaseModel):
    uuid: str
    status: str
    created_at: datetime
    file_name: str
    
class TaskSummary(TaskBase):
    pass

class TaskDetail(TaskBase):
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    updated_at: datetime
    
    class Config:
        orm_mode = True
