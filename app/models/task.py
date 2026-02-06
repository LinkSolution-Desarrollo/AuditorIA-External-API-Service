"""  
SQLAlchemy models base and Task model.

This module defines the declarative base for all models and the Task model
for tracking audio transcription tasks and their results.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, Float, JSON, Integer, DateTime, Text, Index, CheckConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()



class Task(Base):
    """
    Tasks table - stores transcription task information and results.
    
    This table tracks all audio transcription tasks processed by WhisperX,
    including their status, results, metadata, and error information.

    Attributes:
        id: Unique identifier (auto-increment primary key)
        uuid: Universally unique identifier for external references
        status: Current task status (pending, processing, completed, failed)
        result: JSON data with transcription results
        file_name: Name of the audio file
        url: URL or path to the audio file
        audio_duration: Duration of the audio in seconds
        language: Detected or specified language
        task_type: Type of task (transcription, translation, etc.)
        task_params: JSON with task parameters
        duration: Processing time in seconds
        error: Error message if task failed
        created_at: Task creation timestamp
        updated_at: Last update timestamp
    
    Indexes:
        - uuid: For external lookups (unique)
        - (status, created_at): For dashboard queries and filtering
    """

    __tablename__ = "tasks"
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier for each task (Primary Key)",
    )
    uuid = Column(
        String(36),
        default=lambda: str(uuid4()),
        unique=True,
        comment="Universally unique identifier for each task",
    )
    status = Column(String(50), comment="Current status of the task")  # Length added
    result = Column(
        JSON, comment="JSON data representing the result of the task"
    )
    file_name = Column(
        String(255), comment="Name of the file associated with the task"  # Length added
    )
    url = Column(String(255), comment="URL of the file associated with the task")  # Length added
    audio_duration = Column(Float, comment="Duration of the audio in seconds")
    language = Column(
        String(50), comment="Language of the file associated with the task"  # Length added
    )
    task_type = Column(String(50), comment="Type/category of the task")  # Length added
    task_params = Column(JSON, comment="Parameters of the task")
    duration = Column(Float, comment="Duration of the task execution")
    error = Column(
        Text, comment="Error message, if any, associated with the task"
    )
    created_at = Column(
        DateTime, default=datetime.utcnow, comment="Date and time of creation"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Date and time of last update",
    )

    # Composite index for dashboard queries (filter by status, sort by date)
    __table_args__ = (
        Index('idx_task_status_created', 'status', 'created_at'),
        Index('idx_tasks_created_at', 'created_at'),
    )
