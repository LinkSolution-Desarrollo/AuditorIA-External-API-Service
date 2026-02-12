import json
import logging
import os
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ..models.task import Task
from ..models.speaker_analysis import SpeakerAnalysis

logger = logging.getLogger(__name__)

class SpeakerAnalysisService:
    """Service for managing speaker analysis."""
    
    @staticmethod
    def get_analysis(db: Session, task_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get existing analysis for a task.
        """
        analysis = db.query(SpeakerAnalysis).filter(SpeakerAnalysis.task_uuid == task_uuid).first()
        if analysis:
            return analysis.analysis
        return None

    @staticmethod
    def generate_analysis(db: Session, task_uuid: str) -> Dict[str, Any]:
        """
        Generate speaker analysis for a task using OpenAI.
        """
        # 1. Fetch task and transcription
        task = db.query(Task).filter(Task.uuid == task_uuid).first()
        if not task:
            raise ValueError("Task not found")
            
        if not task.result or 'segments' not in task.result:
            raise ValueError("No transcription segments found")
            
        segments = task.result['segments']
        
        # 2. Prepare prompt
        system_prompt = """# Role
You are an expert speaker analyzer.

# Task
From the given transcription make a thorough and deep evaluation of the profile of the speakers.

# Rules
The evaluation MUST be in spanish voseo.
The speaker key must be equal to the ones found in the transcription. If there are multiple speakers, all must be included in the final analysis.
Only add keys for the speakers found in the transcription.
The output MUST be a single JSON object where the keys are the speaker IDs (e.g., "SPEAKER_00") and the values are the description strings.
Do NOT return a list. Do NOT nest the description inside another object (like "perfil").

# Example Output
{{
  "SPEAKER_00": "Description of speaker 0...",
  "SPEAKER_01": "Description of speaker 1..."
}}

# Description characteristics
The description must contain a description of the characteristics of the speaker and their interaction in the transcription.
In the description you must identify who or which role each speaker has, and refer to them with that."""

        # Create a list of speakers found in segments to guide the model (optional but helpful)
        # The n8n node just passes the segments JSON string.
        
        transcription_text = json.dumps(segments, ensure_ascii=False)
        
        # 3. Call OpenAI
        try:
            model_name = "gpt-4.1-mini"
            model = ChatOpenAI(model=model_name, temperature=0.7)
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", "<transcription>\n{transcription}\n</transcription>")
            ])
            
            chain = prompt | model | JsonOutputParser()
            
            result = chain.invoke({"transcription": transcription_text})
            
            # Ensure result is a dict
            if isinstance(result, list):
                # If it returns a list, try to merge or convert
                if len(result) > 0 and isinstance(result[0], dict):
                    # Check if it's [{"SPEAKER_00": "..."}] or [{"SPEAKER_00": {"perfil": "..."}}]
                    new_result = {}
                    for item in result:
                        for k, v in item.items():
                            if isinstance(v, dict) and "perfil" in v:
                                new_result[k] = v["perfil"]
                            else:
                                new_result[k] = v
                    result = new_result
                else:
                    # Fallback
                    result = {}

            # Extract token usage - Note: LangChain's JsonOutputParser may not preserve response_metadata
            # We need to call the model directly to get token usage
            # Let's modify to capture the raw response first
            
            # Re-invoke without parser to get metadata
            chain_with_metadata = prompt | model
            response_msg = chain_with_metadata.invoke({"transcription": transcription_text})
            
            token_usage = response_msg.response_metadata.get('token_usage', {})
            input_tokens = token_usage.get('prompt_tokens')
            output_tokens = token_usage.get('completion_tokens')

            # 4. Save to DB
            new_analysis = SpeakerAnalysis(
                task_uuid=task_uuid,
                analysis=result,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_name=model_name
            )
            db.add(new_analysis)
            db.commit()
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating speaker analysis: {e}")
            raise e
