"""
Service for handling generated tags.
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from openai import OpenAI

from ..models.generated_tag import GeneratedTag
from ..models.task import Task

logger = logging.getLogger(__name__)

# Initialize OpenAI client
# Assuming OPENAI_API_KEY is in environment variables
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class GeneratedTagsService:
    @staticmethod
    def get_tags(db: Session, uuid: str) -> Optional[Dict[str, List[str]]]:
        """
        Get existing tags for a task UUID.
        """
        stmt = select(GeneratedTag).where(GeneratedTag.uuid == uuid)
        result = db.execute(stmt).scalar_one_or_none()
        
        if result and result.tags:
            try:
                # Parse JSON string if it's stored as string
                tags_data = json.loads(result.tags)
                return tags_data
            except json.JSONDecodeError:
                # Fallback if stored as plain comma-separated string (legacy)
                return {"tags": result.tags.split(","), "extraTags": []}
        return None

    @staticmethod
    def generate_tags(db: Session, uuid: str) -> Dict[str, List[str]]:
        """
        Generate tags for a task using OpenAI.
        """
        # 1. Fetch task transcript
        task = db.query(Task).filter(Task.uuid == uuid).first()
        if not task:
            raise ValueError(f"Task with UUID {uuid} not found")
        
        if not task.result:
            raise ValueError("Task has no result/transcript to analyze")
            
        # Extract transcript text and language from result
        result_data = task.result
        if isinstance(result_data, str):
            result_data = json.loads(result_data)
        
        language = result_data.get("language", "es")
        transcript_text = json.dumps(result_data)
        
        # Language name mapping
        language_names = {
            "es": "Spanish",
            "en": "English",
            "pt": "Portuguese",
            "fr": "French",
            "de": "German",
        }
        language_name = language_names.get(language, "Spanish")
        
        # 2. Call OpenAI
        prompt = f"""
        Generate a max of 5 relevant tags that summarize the content of the following call center call transcript while classifying the type of call by service in {language_name}. 
        Additionally, include extra tags that highlight key topics, issues, or actions taken mentioned during the call. 
        Tags must be in screaming snake case (e.g., TAG_NAME) and the words should be in {language_name}.
        
        Return ONLY a JSON object with this structure:
        {{
            "tags": ["TAG_1", "TAG_2"],
            "extraTags": ["EXTRA_TAG_1"]
        }}
        """
        
        try:
            model_name = "gpt-4.1-nano"  # Using gpt-4o-mini as efficient alternative
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": transcript_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            
            content = response.choices[0].message.content
            tags_data = json.loads(content)
            
            # Extract token usage
            input_tokens = response.usage.prompt_tokens if response.usage else None
            output_tokens = response.usage.completion_tokens if response.usage else None
            
            # Normalize tags (screaming snake case is requested but let's ensure)
            # The prompt asks for it, so we trust the model or could add post-processing
            
            # 3. Save to DB
            # Check if exists to update or create
            existing_tag = db.query(GeneratedTag).filter(GeneratedTag.uuid == uuid).first()
            tags_json = json.dumps(tags_data)
            
            if existing_tag:
                existing_tag.tags = tags_json
                existing_tag.input_tokens = input_tokens
                existing_tag.output_tokens = output_tokens
                existing_tag.model_name = model_name
            else:
                new_tag = GeneratedTag(
                    uuid=uuid, 
                    tags=tags_json,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_name=model_name
                )
                db.add(new_tag)
            
            db.commit()
            
            return tags_data
            
        except Exception as e:
            logger.error(f"Error generating tags: {e}")
            raise e
