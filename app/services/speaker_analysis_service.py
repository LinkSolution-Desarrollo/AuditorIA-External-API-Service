"""
Service for speaker analysis (simplified for External API).
"""
import os
import json
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SpeakerAnalysisService:
    """Service for speaker analysis via External API."""

    @staticmethod
    def get_analysis(db: Session, task_uuid: str) -> Dict[str, Any]:
        """Get or generate speaker analysis."""
        # 1. Check if exists
        existing = SpeakerAnalysisService._get_existing_analysis(db, task_uuid)
        if existing:
            return existing

        # 2. Get task
        task = SpeakerAnalysisService._get_task(db, task_uuid)
        if not task:
            raise ValueError("Task not found")

        if not task.get('result') or 'segments' not in task['result']:
            raise ValueError("No transcription segments found")

        segments = task['result']['segments']

        # 3. Generate analysis
        analysis = SpeakerAnalysisService._generate_with_openai(segments)

        # 4. Save
        SpeakerAnalysisService._save_analysis(db, task_uuid, analysis)

        return analysis

    @staticmethod
    def _get_existing_analysis(db: Session, task_uuid: str) -> Dict[str, Any] | None:
        """Get existing analysis."""
        query = text("""
            SELECT analysis
            FROM speaker_analysis
            WHERE task_uuid = :uuid
            LIMIT 1
        """)
        result = db.execute(query, {"uuid": task_uuid}).scalar()
        if result:
            if isinstance(result, str):
                return json.loads(result)
            return result
        return None

    @staticmethod
    def _get_task(db: Session, task_uuid: str) -> Dict | None:
        """Get task data."""
        query = text("""
            SELECT uuid, result
            FROM tasks
            WHERE uuid = :uuid
            LIMIT 1
        """)
        result = db.execute(query, {"uuid": task_uuid}).fetchone()
        if result:
            result_data = result[1]
            if isinstance(result_data, str):
                result_data = json.loads(result_data)
            return {
                "uuid": result[0],
                "result": result_data
            }
        return None

    @staticmethod
    def _generate_with_openai(segments: list) -> Dict[str, Any]:
        """Generate analysis using OpenAI via LangChain."""
        try:
            system_prompt = """# Role
You are an expert speaker analyzer.

# Task
From the given transcription make a thorough evaluation of speakers.

# Rules
Evaluation MUST be in Spanish (voseo).
Speaker keys must match those in transcription.
Output MUST be a JSON object with speaker IDs as keys (e.g., "SPEAKER_00").
Do NOT return a list.
Identify roles (Agent, Customer) and refer to them as such.

# Example Output
{
  "SPEAKER_00": "Description...",
  "SPEAKER_01": "Description..."
}"""

            transcription_text = json.dumps(segments, ensure_ascii=False)

            model = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.7,
                api_key=settings.OPENAI_API_KEY
            )

            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", "<transcription>\n{transcription}\n</transcription>")
            ])

            chain = prompt | model | JsonOutputParser()
            result = chain.invoke({"transcription": transcription_text})

            # Ensure result is dict
            if isinstance(result, list):
                new_result = {}
                for item in result:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            if isinstance(v, dict) and "perfil" in v:
                                new_result[k] = v["perfil"]
                            else:
                                new_result[k] = v
                result = new_result

            return result

        except Exception as e:
            logger.error(f"Error generating analysis: {e}", exc_info=True)
            raise ValueError(f"Error: {str(e)}")

    @staticmethod
    def _save_analysis(db: Session, task_uuid: str, analysis: Dict[str, Any]):
        """Save analysis to database."""
        query = text("""
            INSERT INTO speaker_analysis (task_uuid, analysis, created_at)
            VALUES (:uuid, :analysis::jsonb, NOW())
            ON CONFLICT (task_uuid) DO UPDATE
            SET analysis = :analysis::jsonb, updated_at = NOW()
        """)
        db.execute(query, {"uuid": task_uuid, "analysis": json.dumps(analysis)})
        db.commit()
