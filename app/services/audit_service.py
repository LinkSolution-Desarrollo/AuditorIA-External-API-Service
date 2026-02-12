"""
Service for audit generation (simplified for External API).
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = OpenAI(api_key=settings.OPENAI_API_KEY)


class AuditService:
    """Service for generating audits via External API."""

    @staticmethod
    def generate_audit_for_call(
        db: Session,
        task_uuid: str,
        username: str = "external_api"
    ) -> Dict[str, Any]:
        """
        Generate an audit for a call using OpenAI.
        """
        try:
            # 1. Check if audit already exists
            existing = AuditService._get_existing_audit(db, task_uuid, is_call=True)
            if existing:
                return {
                    "success": True,
                    "task_uuid": task_uuid,
                    "score": existing.get("score"),
                    "is_audit_failure": existing.get("is_audit_failure"),
                    "audit": existing.get("audit"),
                    "generated_by_user": existing.get("generated_by_user")
                }

            # 2. Get task data
            task_data = AuditService._get_task_with_call_log(db, task_uuid)
            if not task_data:
                return {
                    "success": False,
                    "message": "Task not found or no campaign/operator assigned"
                }

            # 3. Get campaign and criteria
            campaign_id = task_data.get('campaign_id')
            if not campaign_id:
                return {"success": False, "message": "No campaign assigned"}

            criteria = AuditService._get_audit_criteria(db, campaign_id)
            if not criteria:
                return {"success": False, "message": "No audit criteria found for campaign"}

            # 4. Get campaign approval score
            approval_score = AuditService._get_campaign_approval_score(db, campaign_id)

            # 5. Get transcription
            transcription = AuditService._get_transcription(db, task_uuid)
            if not transcription:
                return {"success": False, "message": "No transcription found"}

            # 6. Generate audit with OpenAI
            audit_results = AuditService._generate_audit_with_ai(
                transcription=transcription,
                criteria=criteria,
                task_data=task_data
            )

            if "error" in audit_results:
                return {
                    "success": False,
                    "message": audit_results.get("message", "Error generating audit")
                }

            # 7. Calculate score
            score, is_failure = AuditService._calculate_score(
                audit_results['answers'],
                criteria,
                approval_score
            )

            # 8. Insert audit
            AuditService._insert_audit(
                db=db,
                task_uuid=task_uuid,
                campaign_id=campaign_id,
                user_id=task_data.get('user_id', 'unknown'),
                score=score,
                is_audit_failure=is_failure,
                audit=audit_results['answers'],
                generated_by_user=username
            )

            # 9. Update task status
            AuditService._update_task_status(db, task_uuid, "audited")

            return {
                "success": True,
                "task_uuid": task_uuid,
                "campaign_id": campaign_id,
                "user_id": task_data.get('user_id'),
                "score": score,
                "is_audit_failure": is_failure,
                "audit": audit_results['answers'],
                "generated_by_user": username
            }

        except Exception as e:
            logger.error(f"Error generating audit: {e}", exc_info=True)
            db.rollback()
            return {
                "success": False,
                "message": f"Error generating audit: {str(e)}"
            }

    @staticmethod
    def generate_audit_for_chat(
        db: Session,
        task_uuid: str,
        username: str = "external_api"
    ) -> Dict[str, Any]:
        """Generate audit for chat - simplified version."""
        try:
            # For now, return not implemented
            return {
                "success": False,
                "message": "Chat audit not yet implemented in External API"
            }
        except Exception as e:
            logger.error(f"Error generating chat audit: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    # ========== HELPER METHODS ==========

    @staticmethod
    def _get_existing_audit(db: Session, task_uuid: str, is_call: bool = True) -> Optional[Dict]:
        """Check if audit already exists."""
        if is_call:
            query = text("""
                SELECT task_uuid, score, is_audit_failure, generated_by_user,
                       jsonb_array_elements(audit) as audit_item
                FROM operator_quality
                WHERE task_uuid = :uuid
                LIMIT 1
            """)
        else:
            query = text("""
                SELECT chat_uuid, score, is_audit_failure, generated_by_user
                FROM chats_quality
                WHERE chat_uuid = :uuid
                LIMIT 1
            """)
        result = db.execute(query, {"uuid": task_uuid}).fetchone()
        if result:
            return {
                "task_uuid": result[0],
                "score": result[1],
                "is_audit_failure": result[2],
                "generated_by_user": result[3]
            }
        return None

    @staticmethod
    def _get_task_with_call_log(db: Session, task_uuid: str) -> Optional[Dict]:
        """Get task and call_log data."""
        query = text("""
            SELECT t.uuid, t.file_name, t.status, t.result,
                   cl.campaign_id, cl.operator_id, cl.user_id
            FROM tasks t
            LEFT JOIN call_logs cl ON cl.file_name = t.file_name
            WHERE t.uuid = :uuid
            LIMIT 1
        """)
        result = db.execute(query, {"uuid": task_uuid}).fetchone()
        if result:
            return {
                "uuid": result[0],
                "file_name": result[1],
                "status": result[2],
                "result": result[3],
                "campaign_id": result[4],
                "operator_id": result[5],
                "user_id": result[6]
            }
        return None

    @staticmethod
    def _get_audit_criteria(db: Session, campaign_id: int) -> List[Dict]:
        """Get audit criteria for campaign."""
        query = text("""
            SELECT id, criterion, target_score
            FROM audit_criteria
            WHERE campaign_id = :campaign_id
            ORDER BY id
        """)
        results = db.execute(query, {"campaign_id": campaign_id}).fetchall()
        return [
            {"id": r[0], "criterion": r[1], "target_score": r[2]}
            for r in results
        ]

    @staticmethod
    def _get_campaign_approval_score(db: Session, campaign_id: int) -> float:
        """Get campaign approval score."""
        query = text("""
            SELECT approval_score
            FROM campaigns
            WHERE id = :campaign_id
            LIMIT 1
        """)
        result = db.execute(query, {"campaign_id": campaign_id}).scalar()
        return result or 70.0

    @staticmethod
    def _get_transcription(db: Session, task_uuid: str) -> Optional[str]:
        """Get transcription text from task."""
        query = text("""
            SELECT result
            FROM tasks
            WHERE uuid = :uuid
            LIMIT 1
        """)
        result = db.execute(query, {"uuid": task_uuid}).scalar()
        if result:
            if isinstance(result, str):
                result = json.loads(result)
            return json.dumps(result, ensure_ascii=False)
        return None

    @staticmethod
    def _generate_audit_with_ai(
        transcription: str,
        criteria: List[Dict],
        task_data: Dict
    ) -> Dict[str, Any]:
        """Generate audit using OpenAI."""
        try:
            criteria_text = "\n".join([
                f"- {c['criterion']} (Puntaje máximo: {c['target_score']})"
                for c in criteria
            ])

            system_prompt = f"""Eres un experto en calidad de atención al cliente.

Evalúa la siguiente llamada según estos criterios:
{criteria_text}

Instrucciones:
- Evalúa CADA criterio de 0 a {max(c['target_score'] for c in criteria)}
- Sé objetivo y basado solo en la transcripción
- Responde SOLO con JSON válido:
{{
  "answers": [
    {{
      "id": <criterion_id>,
      "criterion": "<nombre>",
      "target_score": <max>,
      "score": <dado>,
      "observations": "<justificación>"
    }}
  ]
}}"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcription}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            return {
                "answers": result.get("answers", []),
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "model_name": "gpt-4o-mini"
            }

        except Exception as e:
            logger.error(f"Error calling OpenAI: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Error con OpenAI: {str(e)}"
            }

    @staticmethod
    def _calculate_score(
        answers: List[Dict],
        criteria: List[Dict],
        approval_score: float
    ) -> tuple[float, bool]:
        """Calculate score and determine failure."""
        total_score = sum(a.get('score', 0) for a in answers)
        max_score = sum(c['target_score'] for c in criteria)
        normalized = (total_score / max_score * 100) if max_score > 0 else 0
        is_failure = normalized < approval_score
        return round(normalized, 2), is_failure

    @staticmethod
    def _insert_audit(
        db: Session,
        task_uuid: str,
        campaign_id: int,
        user_id: str,
        score: float,
        is_audit_failure: bool,
        audit: List[Dict],
        generated_by_user: str
    ) -> int:
        """Insert audit into database."""
        query = text("""
            INSERT INTO operator_quality
            (task_uuid, campaign_id, user_id, score, is_audit_failure,
             audit, generated_by_user, created_at)
            VALUES (:task_uuid, :campaign_id, :user_id, :score, :is_audit_failure,
                    :audit::jsonb, :generated_by_user, NOW())
            RETURNING id
        """)
        result = db.execute(query, {
            "task_uuid": task_uuid,
            "campaign_id": campaign_id,
            "user_id": user_id,
            "score": score,
            "is_audit_failure": is_audit_failure,
            "audit": json.dumps(audit),
            "generated_by_user": generated_by_user
        })
        db.commit()
        return result.scalar()

    @staticmethod
    def _update_task_status(db: Session, task_uuid: str, status: str):
        """Update task status."""
        query = text("""
            UPDATE tasks
            SET status = :status, updated_at = NOW()
            WHERE uuid = :uuid
        """)
        db.execute(query, {"status": status, "uuid": task_uuid})
        db.commit()
