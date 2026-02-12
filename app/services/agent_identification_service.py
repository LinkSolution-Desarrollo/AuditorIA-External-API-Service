"""
Service for handling agent identification.
"""
import os
import json
import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from openai import OpenAI

from ..models.agent_identification import AgentIdentification
from ..models.task import Task

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class AgentIdentificationService:
    @staticmethod
    def get_identification(db: Session, task_uuid: str) -> Optional[Dict[str, str]]:
        """
        Get existing agent identification for a task UUID.
        """
        stmt = select(AgentIdentification).where(AgentIdentification.original_uuid == task_uuid)
        result = db.execute(stmt).scalar_one_or_none()
        
        if result and result.agent_identification:
            # If stored as string, parse it. If JSON type in DB, it comes as dict.
            if isinstance(result.agent_identification, str):
                try:
                    return json.loads(result.agent_identification)
                except json.JSONDecodeError:
                    return None
            return result.agent_identification
        return None

    @staticmethod
    def identify_agent(db: Session, task_uuid: str) -> Dict[str, str]:
        """
        Identify agent and other speakers in a task using OpenAI.
        """
        # 1. Fetch task transcript
        task = db.query(Task).filter(Task.uuid == task_uuid).first()
        if not task:
            raise ValueError(f"Task with UUID {task_uuid} not found")
        
        if not task.result:
            raise ValueError("Task has no result/transcript to analyze")
            
        # Extract segments for the prompt
        # Assuming task.result has 'segments' list
        result_data = task.result
        if isinstance(result_data, str):
            result_data = json.loads(result_data)
            
        segments = result_data.get("segments", [])
        if not segments:
             raise ValueError("No segments found in task result")
        
        # Extract language from transcription result
        language = result_data.get("language", "es")

        # Format segments for LLM
        formatted_segments = [
            {
                "text": s.get("text", "").strip(),
                "start": s.get("start"),
                "end": s.get("end"),
                "speaker": s.get("speaker")
            }
            for s in segments
        ]
        segments_json = json.dumps(formatted_segments)
        
        # Language-specific labels
        language_labels = {
            "es": {"agent": "Agente", "client": "Cliente", "ivr": "IVR", "voicemail": "Buzón de Voz"},
            "en": {"agent": "Agent", "client": "Customer", "ivr": "IVR", "voicemail": "Voicemail"},
            "pt": {"agent": "Agente", "client": "Cliente", "ivr": "URA", "voicemail": "Caixa Postal"},
            "fr": {"agent": "Agent", "client": "Client", "ivr": "SVI", "voicemail": "Messagerie"},
            "de": {"agent": "Agent", "client": "Kunde", "ivr": "IVR", "voicemail": "Voicemail"},
        }
        labels = language_labels.get(language, language_labels["es"])
        
        # 2. Call OpenAI
        prompt = f"""
        You are an expert speaker identification algorithm.
        You will identify who is talking in the provided transcription segments.
        The transcription is in language code: {language}.
        Only identify a speaker once.
        The format of the speaker must be: "SPEAKER_(number)" with the number that's present in the segments.
        This format and the numbers MUST be kept when generating the JSON output.
        Maximum description length is 5 words. Minimum is 1.
        The call center agent should always be called "{labels['agent']}".
        The client should always be called "{labels['client']}".
        There can also be other speakers present in the transcription (e.g., "{labels['ivr']}", "{labels['voicemail']}").
        
        Return ONLY a JSON object where keys are SPEAKER_XX and values are the identified role.
        Example:
        {{
            "SPEAKER_00": "{labels['agent']}",
            "SPEAKER_01": "{labels['client']}"
        }}
        """
        
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"segments: {segments_json}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            content = response.choices[0].message.content
            identification_data = json.loads(content)
            
            # 3. Save to DB
            # Check if exists to update or create
            existing_ident = db.query(AgentIdentification).filter(AgentIdentification.original_uuid == task_uuid).first()
            
            if existing_ident:
                existing_ident.agent_identification = identification_data
            else:
                new_ident = AgentIdentification(original_uuid=task_uuid, agent_identification=identification_data)
                db.add(new_ident)
            
            db.commit()
            
            return identification_data
            
        except Exception as e:
            logger.error(f"Error identifying agent: {e}")
            raise e
