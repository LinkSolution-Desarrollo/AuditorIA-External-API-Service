
import json
import logging
import os
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from app.models.task import Task
from app.models.ai_chat_message import AIChatMessage
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Basic system prompt (simplified version of the main app's prompt)
SYSTEM_PROMPT = """You are Linky, an AI assistant for AuditorIA.
Analyze the following transcription of a contact center call.
Differentiate between Agent and Client.
Use backticks when quoting exact phrases and include the approximate minute/timestamp if available.
If you lack information, say "I'm sorry".
Respond in Markdown.

Transcription: {transcription}
"""

class AIChatService:
    """Service for AI Agent (Linky) chat."""
    
    @staticmethod
    def get_history(db: Session, session_id: str) -> List[AIChatMessage]:
        return db.query(AIChatMessage).filter(
            AIChatMessage.session_id == session_id
        ).order_by(AIChatMessage.created_at.asc()).all()

    @staticmethod
    def add_message(
        db: Session, 
        session_id: str, 
        role: str, 
        content: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        model_name: Optional[str] = None
    ) -> AIChatMessage:
        message = AIChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=model_name
        )
        db.add(message)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # In a real scenario, handle sequence sync here if using Identity column issues
            # For now, just retry once or fail
            db.add(message)
            db.commit()
            
        db.refresh(message)
        return message

    @staticmethod
    def process_chat(db: Session, uuid: str, chat_input: str) -> str:
        # 1. Fetch Task
        task = db.query(Task).filter(Task.uuid == uuid).first()
        if not task:
            raise ValueError("Task not found")
            
        transcription_json = "[]"
        if task.result and 'segments' in task.result:
            transcription_json = json.dumps(task.result['segments'], ensure_ascii=False)

        # 2. Fetch History
        history_records = AIChatService.get_history(db, uuid)
        history_messages = []
        for record in history_records:
            if record.role == "user":
                history_messages.append(HumanMessage(content=record.content))
            elif record.role == "assistant":
                history_messages.append(AIMessage(content=record.content))
            
        # 3. Call OpenAI
        try:
            settings = get_settings()
            # Ensure OpenAI Key is present (loaded via env)
            
            model = ChatOpenAI(model="gpt-4o", temperature=0.5, max_tokens=1000)
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}")
            ])
            
            chain = prompt | model
            
            response_msg = chain.invoke({
                "history": history_messages,
                "input": chat_input,
                "transcription": transcription_json
            })
            
            response_text = response_msg.content
            
            # Simple token tracking if available in metadata
            token_usage = response_msg.response_metadata.get('token_usage', {})
            input_tokens = token_usage.get('prompt_tokens')
            output_tokens = token_usage.get('completion_tokens')
            model_name = "gpt-4o"
            
            # 4. Save to DB
            AIChatService.add_message(db, uuid, "user", chat_input)
            AIChatService.add_message(
                db, uuid, "assistant", response_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_name=model_name
            )
            
            return response_text
            
        except Exception as e:
            logger.error(f"Error in AI Chat: {e}")
            raise e
