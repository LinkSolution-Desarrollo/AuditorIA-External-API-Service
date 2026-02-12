"""
Service for generating tags (simplified for External API).
"""
import os
import json
import logging
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = OpenAI(api_key=settings.OPENAI_API_KEY)


class TagsService:
    """Service for generating tags via External API."""

    @staticmethod
    def get_tags(db: Session, task_uuid: str, force_generate: bool = False) -> Dict[str, List[str]]:
        """Get or generate tags for a task."""
        # 1. Check if tags exist
        if not force_generate:
            existing = TagsService._get_existing_tags(db, task_uuid)
            if existing:
                return existing

        # 2. Get task
        task = TagsService._get_task(db, task_uuid)
        if not task:
            raise ValueError(f"Task {task_uuid} not found")

        if not task.get('result'):
            raise ValueError("Task has no transcription")

        # 3. Generate tags
        tags_data = TagsService._generate_tags_with_openai(task['result'])

        # 4. Save
        TagsService._save_tags(db, task_uuid, tags_data)

        return tags_data

    @staticmethod
    def _get_existing_tags(db: Session, task_uuid: str) -> Dict[str, List[str]] | None:
        """Get existing tags."""
        query = text("""
            SELECT tags
            FROM generated_tags
            WHERE uuid = :uuid
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
            SELECT uuid, result, status
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
                "result": result_data,
                "status": result[2]
            }
        return None

    @staticmethod
    def _truncate_for_context(result_data: Dict, max_chars: int = 50000) -> str:
        """Truncate transcription to fit within OpenAI context limits."""
        segments = result_data.get("segments", [])

        # If we have segments, sample from beginning, middle, and end
        if segments and len(segments) > 100:
            # Take first 40, middle 20, last 40 segments
            sampled = segments[:40] + segments[len(segments)//2 - 10:len(segments)//2 + 10] + segments[-40:]
            result_data_truncated = {**result_data, "segments": sampled}
        else:
            result_data_truncated = result_data

        transcript_text = json.dumps(result_data_truncated, ensure_ascii=False)

        # If still too long, truncate the text itself
        if len(transcript_text) > max_chars:
            transcript_text = transcript_text[:max_chars] + '..."}'

        return transcript_text

    @staticmethod
    def _generate_tags_with_openai(result_data: Dict) -> Dict[str, List[str]]:
        """Generate tags using OpenAI."""
        try:
            language = result_data.get("language", "es")

            # Truncate to avoid context length errors
            transcript_text = TagsService._truncate_for_context(result_data)

            language_names = {
                "es": "Spanish", "en": "English", "pt": "Portuguese",
                "fr": "French", "de": "German"
            }
            language_name = language_names.get(language, "Spanish")

            prompt = f"""
Generate max 5 tags that summarize the call center transcript in {language_name}.
Also include extra tags for key topics.
Tags must be in SCREAMING_SNAKE_CASE (e.g., TAG_NAME) in {language_name}.

Return ONLY JSON:
{{
  "tags": ["TAG_1", "TAG_2"],
  "extraTags": ["EXTRA_TAG_1"]
}}
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": transcript_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )

            tags_data = json.loads(response.choices[0].message.content)
            tags_data.setdefault("tags", [])
            tags_data.setdefault("extraTags", [])
            return tags_data

        except Exception as e:
            logger.error(f"Error generating tags: {e}", exc_info=True)
            raise ValueError(f"Error generating tags: {str(e)}")

    @staticmethod
    def _save_tags(db: Session, task_uuid: str, tags_data: Dict[str, List[str]]):
        """Save tags to database."""
        query = text("""
            INSERT INTO generated_tags (uuid, tags, created_at)
            VALUES (:uuid, :tags, NOW())
            ON CONFLICT (uuid) DO UPDATE
            SET tags = :tags
        """)
        db.execute(query, {"uuid": task_uuid, "tags": json.dumps(tags_data)})
        db.commit()
