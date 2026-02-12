from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime

class Response(BaseModel):
    """Standard response model for task operations."""
    identifier: str
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "identifier": "abc-123-def-456",
                "message": "Task created successfully"
            }
        }

class Metadata(BaseModel):
    """Task metadata including parameters and file information."""
    task_type: str
    task_params: Optional[dict]
    language: Optional[str]
    file_name: Optional[str]
    url: Optional[str]
    duration: Optional[float]
    audio_duration: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "task_type": "transcription",
                "task_params": {"enable_diarization": True},
                "language": "es",
                "file_name": "audio_call.mp3",
                "url": "https://example.com/audio_call.mp3",
                "duration": 12.5,
                "audio_duration": 180.3
            }
        }

class TaskSimple(BaseModel):
    """Simplified task information for list views."""
    identifier: str
    status: str
    task_type: str
    file_name: Optional[str]
    language: Optional[str]
    audio_duration: Optional[float]
    created_at: datetime
    
    # Validation alias to map from DB model fields if names differ
    # But here names are mostly same, except identifier -> uuid
    class Config:
        orm_mode = True

class ResultTasks(BaseModel):
    """Collection of tasks for list endpoints."""
    tasks: List[TaskSimple]

class Result(BaseModel):
    """Complete task result including status, data, and metadata."""
    status: str
    result: Any
    metadata: Metadata
    error: Optional[str]

    class Config:
        json_schema_extra = {
            "example": {
                "status": "completed",
                "result": {
                    "segments": [
                        {"start": 0.0, "end": 5.2, "text": "Hola, ¿cómo estás?", "speaker": "SPEAKER_00"}
                    ]
                },
                "metadata": {
                    "task_type": "transcription",
                    "language": "es",
                    "file_name": "audio_call.mp3",
                    "duration": 12.5
                },
                "error": None
            }
        }

class TaskUpdate(BaseModel):
    """Schema for updating task status and result."""
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    duration: Optional[float] = None
