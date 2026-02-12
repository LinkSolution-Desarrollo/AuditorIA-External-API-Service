"""
Service for agent identification (simplified for External API).
"""
import os
import json
import logging
from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy import text
from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = OpenAI(api_key=settings.OPENAI_API_KEY)


class AgentIdentificationService:
    """Service for agent identification via External API."""

    @staticmethod
    def get_identification(db: Session, task_uuid: str) -> Dict[str, str]:
        """Get or identify agents."""
        # 1. Check if exists
        existing = AgentIdentificationService._get_existing_identification(db, task_uuid)
        if existing:
            return existing

        # 2. Get task
        task = AgentIdentificationService._get_task(db, task_uuid)
        if not task:
            raise ValueError(f"Task {task_uuid} not found")

        if not task.get('result'):
            raise ValueError("Task has no transcription")

        # 3. Identify agents
        identification = AgentIdentificationService._identify_with_openai(task['result'])

        # 4. Save
        AgentIdentificationService._save_identification(db, task_uuid, identification)

        return identification

    @staticmethod
    def _get_existing_identification(db: Session, task_uuid: str) -> Dict[str, str] | None:
        """Get existing identification."""
        query = text("""
            SELECT agent_identification
            FROM agent_identification
            WHERE original_uuid = :uuid
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
    def _identify_with_openai(result_data: Dict) -> Dict[str, str]:
        """Identify agents using OpenAI."""
        try:
            segments = result_data.get("segments", [])
            if not segments:
                raise ValueError("No segments found")

            language = result_data.get("language", "es")

            # Truncate segments if too many (sample from beginning, middle, end)
            if len(segments) > 100:
                sampled_segments = segments[:40] + segments[len(segments)//2 - 10:len(segments)//2 + 10] + segments[-40:]
            else:
                sampled_segments = segments

            formatted_segments = [
                {
                    "text": s.get("text", "").strip(),
                    "start": s.get("start"),
                    "end": s.get("end"),
                    "speaker": s.get("speaker")
                }
                for s in sampled_segments
            ]
            segments_json = json.dumps(formatted_segments, ensure_ascii=False)

            # Final safety check
            if len(segments_json) > 50000:
                segments_json = segments_json[:50000] + '...]'

            language_labels = {
                "es": {"agent": "Agente", "client": "Cliente"},
                "en": {"agent": "Agent", "client": "Customer"},
                "pt": {"agent": "Agente", "client": "Cliente"}
            }
            labels = language_labels.get(language, language_labels["es"])

            prompt = f"""
Identify speakers in the transcription (language: {language}).
Format: SPEAKER_(number) from segments.
Agent = "{labels['agent']}", Customer = "{labels['client']}".
Max 5 words per role.

Return ONLY JSON:
{{
  "SPEAKER_00": "{labels['agent']}",
  "SPEAKER_01": "{labels['client']}"
}}

Segments:
{segments_json}
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a speaker identification JSON generator."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            identification = json.loads(response.choices[0].message.content)
            return identification

        except Exception as e:
            logger.error(f"Error identifying agents: {e}", exc_info=True)
            raise ValueError(f"Error: {str(e)}")

    @staticmethod
    def _save_identification(db: Session, task_uuid: str, identification: Dict[str, str]):
        """Save identification to database."""
        query = text("""
            INSERT INTO agent_identification (original_uuid, agent_identification, created_at)
            VALUES (:uuid, :identification::jsonb, NOW())
            ON CONFLICT (original_uuid) DO UPDATE
            SET agent_identification = :identification::jsonb, updated_at = NOW()
        """)
        db.execute(query, {"uuid": task_uuid, "identification": json.dumps(identification)})
        db.commit()
