from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ChatRequest(BaseModel):
    chat_input: str

class ChatMessage(BaseModel):
    role: str
    content: str
    created_at: datetime
    
    class Config:
        orm_mode = True

class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessage]
