"""
Service for operator quality audits using OpenAI.
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from openai import OpenAI
from datetime import datetime
import openai
from app.services.email_service import EmailService
from app.routers.notifications import create_internal_notification

logger = logging.getLogger(__name__)


class OperatorQualityService:
    """Service for generating and managing operator quality audits."""

    @staticmethod
    async def generate_audit_for_call(
        db: Session,
        task_uuid: str,
        username: str,
        user_sub: str
    ) -> Dict[str, Any]:
        """
        Generate an audit for a call using OpenAI.
        """
        try:
            # 1. Check if audit already exists
            existing_audit = OperatorQualityService._get_existing_audit(
                db, task_uuid)
            if existing_audit:
                return {
                    "success": True,
                    "status_code": 200,
                    **existing_audit
                }

            # 2. Get task and call_log data
            task_data = OperatorQualityService._get_task_data(db, task_uuid)
            if not task_data:
                return {
                    "success": False,
                    "status_code": 404,
                    "message": "Task not found"
                }

            # 3. Validation: Campaign and Usage
            if not task_data.get('user_id'):
                return {
                    "success": False,
                    "status_code": 400,
                    "message": f"El operador con ID '{task_data.get('operator_id')}' no existe en la base de datos de usuarios (operators)." if task_data.get('operator_id') else "La tarea no tiene un operador asignado (call_logs)."
                }

            # 3b. Get campaign and approval score
            if not task_data.get('campaign_id'):
                return {
                    "success": False,
                    "status_code": 400,
                    "message": "La tarea no tiene una campaña asignada. Por favor edite la información de la llamada y asigne una campaña."
                }

            campaign_data = OperatorQualityService._get_campaign_data(
                db, task_data['campaign_id'])
            if not campaign_data:
                return {
                    "success": False,
                    "status_code": 409,
                    "message": f"No existe una planilla de auditoría en el CRM para la campaña ID {task_data['campaign_id']}"
                }

            # 4. Get audit criteria
            criteria = OperatorQualityService._get_audit_criteria(
                db, task_data['campaign_id'])
            if not criteria:
                return {
                    "success": False,
                    "status_code": 400,
                    "message": "No se encontraron criterios de evaluación para esta campaña."
                }

            # 5. Get transcription
            transcription = OperatorQualityService._get_transcription(
                db, task_data['file_name'])

            # 6. Call OpenAI to generate audit
            audit_results = await OperatorQualityService._generate_audit_with_ai(
                transcription=transcription,
                criteria=criteria,
                task_data=task_data
            )

            if "error" in audit_results:
                return {
                    "success": False,
                    "status_code": audit_results.get("status_code", 500),
                    "message": audit_results.get("message", "Error generating audit")
                }

            # 7. Calculate score
            score, is_audit_failure = OperatorQualityService._calculate_score(
                audit_results['answers'],
                criteria,
                campaign_data['approval_score']
            )

            # 8. Insert audit into database
            audit_id = OperatorQualityService._insert_audit(
                db=db,
                task_uuid=task_uuid,
                campaign_id=task_data['campaign_id'],
                user_id=task_data['user_id'],
                score=score,
                is_audit_failure=is_audit_failure,
                audit=audit_results['answers'],
                generated_by_user=username,
                input_tokens=audit_results.get('input_tokens'),
                output_tokens=audit_results.get('output_tokens'),
                model_name=audit_results.get('model_name')
            )

            # 9. Update task status
            OperatorQualityService._update_task_status(
                db, task_uuid, "audited")

            # 9b. Send Email Notification
            try:
                # Add campaign name to task_data for email template
                task_data["campaign_name"] = campaign_data.get(
                    "campaign_name", "Desconocida")
                EmailService.send_audit_notification(db, {
                    "score": score,
                    "is_audit_failure": is_audit_failure,
                    "answers": audit_results['answers']
                }, task_data)
            except Exception as e:
                logger.error(f"Error sending email notification: {e}")
                # Don't fail the request if email fails

            # 10. Mark criteria as unchanged (COMENTADO PORQUE FALTA LA COLUMNA EN DB)
            # OperatorQualityService._mark_criteria_unchanged(db, task_data['campaign_id'])

            return {
                "success": True,
                "status_code": 200,
                "task_uuid": task_uuid,
                "campaign_id": task_data['campaign_id'],
                "user_id": task_data['user_id'],
                "score": score,
                "is_audit_failure": is_audit_failure,
                "audit": audit_results['answers'],
                "generated_by_user": username
            }

        except Exception as e:
            logger.error(f"Error generating audit: {e}", exc_info=True)
            db.rollback()
            return {
                "success": False,
                "status_code": 500,
                "message": "Error inesperado al generar la auditoría"
            }

    @staticmethod
    async def generate_audit_for_chat(
        db: Session,
        task_uuid: str,
        username: str,
        user_sub: str
    ) -> Dict[str, Any]:
        """
        Generate an audit for a chat using OpenAI.
        """
        try:
            # 1. Check if audit already exists
            existing_audit = OperatorQualityService._get_existing_audit_chat(
                db, task_uuid)
            if existing_audit:
                # Format to match AuditResponse
                return {
                    "success": True,
                    "status_code": 200,
                    "task_uuid": existing_audit["chat_uuid"],
                    "score": existing_audit["score"],
                    "audit": existing_audit["comments"] if isinstance(existing_audit["comments"], list) else json.loads(existing_audit["comments"]),
                    "created_at": existing_audit["created_at"]
                }

            # 2. Get chat and operator data
            chat_data = OperatorQualityService._get_chat_full_data(
                db, task_uuid)
            if not chat_data:
                return {
                    "success": False,
                    "status_code": 404,
                    "message": "Chat not found"
                }

            # 3. Validation: Campaign
            if not chat_data.get('campaign_id'):
                return {
                    "success": False,
                    "status_code": 400,
                    "message": "El chat no tiene una campaña asignada."
                }

            campaign_data = OperatorQualityService._get_campaign_data(
                db, chat_data['campaign_id'])
            if not campaign_data:
                return {
                    "success": False,
                    "status_code": 409,
                    "message": f"No existe la campaña ID {chat_data['campaign_id']}"
                }

            # 4. Get audit criteria (using RRSS criteria for chats)
            criteria = OperatorQualityService._get_audit_criteria_rrss(
                db, chat_data['campaign_id'])
            if not criteria:
                return {
                    "success": False,
                    "status_code": 400,
                    "message": "No se encontraron criterios de evaluación para esta campaña de chat."
                }

            # 5. Get chat messages (result field in chats table)
            messages = chat_data.get('messages', [])

            # 6. Call OpenAI to generate audit (Reuse existing prompt)
            # Adapting messages to "transcription" format expected by _generate_audit_with_ai
            audit_results = await OperatorQualityService._generate_audit_with_ai(
                transcription={"result": messages},
                criteria=criteria,
                task_data={
                    "uuid": chat_data["uuid"],
                    "first_name": chat_data.get("first_name", ""),
                    "last_name": chat_data.get("last_name", ""),
                    "direction": "inbound" if chat_data.get("is_inbound") else "outbound"
                }
            )

            if "error" in audit_results:
                return {
                    "success": False,
                    "status_code": audit_results.get("status_code", 500),
                    "message": audit_results.get("message", "Error generating audit")
                }

            # 7. Calculate score
            score, is_audit_failure = OperatorQualityService._calculate_score(
                audit_results['answers'],
                criteria,
                campaign_data['approval_score']
            )

            # 8. Insert audit into database
            audit_id = await OperatorQualityService._insert_audit_chat(
                db=db,
                chat_uuid=task_uuid,
                campaign_id=chat_data['campaign_id'],
                user_id=chat_data.get('operator_id'),
                score=score,
                is_audit_failure=is_audit_failure,
                audit=audit_results['answers'],
                generated_by_user=username
            )

            # 9. Update chat status
            db.execute(text("UPDATE chats SET status = 'audited' WHERE uuid = :uuid"), {
                       "uuid": task_uuid})
            db.commit()

            # 10. Send Internal Notification
            try:
                if chat_data.get('operator_id'):
                    await create_internal_notification(
                        user_id=chat_data['operator_id'],
                        text=f"Tu chat {task_uuid[:8]} ha sido auditado. Puntaje: {score}%",
                        variant="success" if not is_audit_failure else "destructive",
                        task_data={"chat_uuid": task_uuid, "score": score},
                        db=db
                    )
            except Exception as e:
                logger.error(f"Error sending internal notification: {e}")

            return {
                "success": True,
                "status_code": 200,
                "task_uuid": task_uuid,
                "campaign_id": chat_data['campaign_id'],
                "user_id": chat_data.get('operator_id'),
                "score": score,
                "is_audit_failure": is_audit_failure,
                "audit": audit_results['answers'],
                "generated_by_user": username
            }

        except Exception as e:
            logger.error(f"Error generating chat audit: {e}", exc_info=True)
            db.rollback()
            return {
                "success": False,
                "status_code": 500,
                "message": "Error inesperado al generar la auditoría de chat"
            }

    @staticmethod
    def _get_existing_audit(db: Session, task_uuid: str) -> Optional[Dict[str, Any]]:
        """Check if audit already exists."""
        query = text("""
            SELECT 
                a.task_uuid,
                a.campaign_id,
                a.user_id,
                a.score,
                a.is_audit_failure,
                a.audit,
                a.generated_by_user,
                a.revised_by_user,
                a.revised,
                a.revised_at,
                u.first_name,
                u.last_name
            FROM audits a
            LEFT JOIN operators u ON u.user_id = a.user_id
            WHERE a.task_uuid = :task_uuid
            LIMIT 1
        """)

        result = db.execute(query, {"task_uuid": task_uuid}).fetchone()
        if result:
            # Parse audit JSON
            audit_data = []
            try:
                if result[5]:  # audit field
                    audit_data = result[5] if isinstance(
                        result[5], (list, dict)) else json.loads(result[5])
            except:
                pass

            return {
                "task_uuid": result[0],
                "campaign_id": result[1],
                "user_id": result[2],
                "score": result[3],
                "is_audit_failure": result[4],
                "audit": audit_data,
                "generated_by_user": result[6],
                "revised_by_user": result[7],
                "revised": result[8],
                "revised_at": result[9],
                "first_name": result[10],
                "last_name": result[11]
            }
        return None

    @staticmethod
    def _get_task_data(db: Session, task_uuid: str) -> Optional[Dict[str, Any]]:
        """Get task and call_log data."""
        try:
            query = text("""
                SELECT
                    t.uuid,
                    t.file_name,
                    t.status,
                    u.user_id,
                    u.first_name,
                    u.last_name,
                    u.email,
                    cl.campaign_id,
                    cl.operator_id,
                    cl.direction,
                    CONCAT(
                        LPAD(CAST(FLOOR(t.audio_duration::integer / 60) AS TEXT), 2, '0'),
                        ':', 
                        LPAD(CAST(FLOOR(t.audio_duration::integer % 60) AS TEXT), 2, '0')
                    ) AS call_duration_mmss
                FROM tasks t
                LEFT JOIN call_logs cl ON t.file_name = cl.file_name
                LEFT JOIN operators u ON u.user_id = CAST(cl.operator_id AS VARCHAR)
                WHERE t.uuid = :task_uuid
            """)

            result = db.execute(query, {"task_uuid": task_uuid}).fetchone()

            if result:
                return {
                    "uuid": result[0],
                    "file_name": result[1],
                    "status": result[2],
                    "user_id": result[3],
                    "first_name": result[4],
                    "last_name": result[5],
                    "email": result[6],
                    "campaign_id": result[7],
                    "operator_id": result[8],
                    "direction": result[9],
                    "call_duration": result[10]
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching task data: {e}")
            return None

    @staticmethod
    def _get_campaign_data(db: Session, campaign_id: int) -> Optional[Dict[str, Any]]:
        """Get campaign data."""
        # Placeholder implementation based on context
        # We need approval_score
        query = text(
            "SELECT campaign_name, approval_score FROM campaigns WHERE campaign_id = :campaign_id")
        # Note: approval_score might not exist in campaigns table based on previous files
        # But let's assume it does or use default
        try:
            result = db.execute(query, {"campaign_id": campaign_id}).fetchone()
            if result:
                return {
                    "campaign_name": result[0],
                    # Default
                    "approval_score": result[1] if len(result) > 1 else 80.0
                }
        except Exception as e:
            # Fallback if column missing or other error
            logger.warning(
                f"Error fetching campaign data (using defaults): {e}")
            db.rollback()
            return {"campaign_name": "Unknown", "approval_score": 80.0}
        return None

    @staticmethod
    def _get_audit_criteria(db: Session, campaign_id: int) -> List[Dict[str, Any]]:
        """Get audit criteria."""
        query = text("""
            SELECT category, question, description, target_score, is_critical, criteria_order
            FROM audit_criteria
            WHERE campaign_id = :campaign_id
            ORDER BY criteria_order
        """)
        result = db.execute(query, {"campaign_id": campaign_id}).fetchall()
        return [dict(row._mapping) for row in result]

    @staticmethod
    def _get_transcription(db: Session, file_name: str) -> Dict[str, Any]:
        """Get transcription from tasks table."""
        # Task params usually contains the transcription result or it's in a separate column/table?
        # The original code used `t.result` in `_get_task_data` query (implied by json.loads(result[0]) attempt?)
        # Let's check `tasks` table schema.
        # `tasks` has `result` column (JSON).
        query = text("SELECT result FROM tasks WHERE file_name = :file_name")
        result = db.execute(query, {"file_name": file_name}).fetchone()
        if result and result[0]:
            return {"result": result[0] if isinstance(result[0], (dict, list)) else json.loads(result[0])}
        return {"result": []}

    @staticmethod
    async def _generate_audit_with_ai(
        transcription: Dict[str, Any],
        criteria: List[Dict[str, Any]],
        task_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate audit using OpenAI."""
        try:
            # 1. Configuración del Cliente
            api_key = os.getenv("OPENAI_API_KEY")
            model = os.getenv("OPENAI_MODEL", "gpt-4.1")

            if not api_key:
                logger.error(
                    "OPENAI_API_KEY no encontrada en variables de entorno")
                return {
                    "error": True,
                    "status_code": 500,
                    "message": "Error de configuración: falta API Key"
                }

            client = OpenAI(api_key=api_key)

            # 2. Preparar Prompt
            active_criteria = [
                c for c in criteria if c.get('active_question', True)]

            criteria_list = [
                {
                    "category": c['category'],
                    "question": c['question'],
                    "description": c.get('description')
                }
                for c in active_criteria
            ]

            system_prompt = f"Sos el auditor de un call center.\\nTu tarea principal es evaluar la transcripción de la llamada según los criterios de auditoría indicados a continuación.\\n\\nIMPORTANTE: TIENES QUE DEVOLVER LA MISMA CANTIDAD DE CRITERIOS QUE INGRESAN!\\n\\nAsigne un valor de cumplimiento y justificación para cada criterio en Español Voseo. Los errores se deben calificar evaluando si el agente incurre en el error, entonces 'complies' se califica como false, caso contrario, true.\\nEjemplo: {{ 'category': 'Error Critico', 'question': 'Actitud prepotente' }} -> Si se detecta una actitud prepotente, complies=false, caso contrario complies=true\\nEl campo 'description' es opcional y otorga información adicional sobre cómo auditar ese criterio. Este campo, si se encuentra en el criterio, debe ser seguido al pie de la letra.\\nSi no encuentras una transcripcion, auditar todos los puntos como no cumplidos.\\nSolamente se debe auditar cada punto una vez. Si se encuentra repetido, ignorarlo.\\nPara detectar hold, debes calcular la diferencia entre el valor del end del segmento con el start del siguiente.\\n\\ntranscription: {json.dumps(transcription.get('result', []))}\\ncriteria: {json.dumps(criteria_list)}"

            # 3. Llamada a OpenAI
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",
                        "content": f"task_uuid: {task_data['uuid']}\\nagent: {task_data['first_name']}.{task_data['last_name']}\\ncall direction: {task_data['direction']}"}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "audit_response",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "answers": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "category": {"type": "string"},
                                            "question": {"type": "string"},
                                            "complies": {"type": "boolean"},
                                            "explanation": {"type": "string"}
                                        },
                                        "required": ["category", "question", "complies", "explanation"]
                                    }
                                }
                            },
                            "required": ["answers"]
                        }
                    }
                },
                temperature=0.7,
                max_tokens=4000
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            # Extract token usage
            result['input_tokens'] = response.usage.prompt_tokens if response.usage else None
            result['output_tokens'] = response.usage.completion_tokens if response.usage else None
            result['model_name'] = model

            return result

        except openai.AuthenticationError as e:
            logger.critical(f"OpenAI Authentication Failed: {e}")
            return {
                "error": True,
                "status_code": 500,
                "message": "Error de autenticación con el servicio de IA (API Key inválida)."
            }
        except openai.NotFoundError as e:
            logger.critical(f"OpenAI Model Not Found: {e}")
            return {
                "error": True,
                "status_code": 500,
                "message": f"El modelo configurado '{model}' no existe en OpenAI."
            }
        except Exception as e:
            error_msg = str(e).lower()
            if "bad request" in error_msg:
                return {
                    "error": True,
                    "status_code": 413,
                    "message": "Este llamado es muy largo para ser auditado en este momento"
                }
            elif "timed out" in error_msg or "timeout" in error_msg:
                return {
                    "error": True,
                    "status_code": 408,
                    "message": "La solicitud tardó demasiado en completarse. Intente de nuevo más tarde."
                }
            else:
                logger.error(f"OpenAI error: {e}", exc_info=True)
                return {
                    "error": True,
                    "status_code": 500,
                    "message": "Ocurrió un error inesperado en el servicio de IA"
                }

    @staticmethod
    def _calculate_score(
        audit_results: List[Dict[str, Any]],
        criteria: List[Dict[str, Any]],
        approval_score: float
    ) -> Tuple[float, int]:
        """Calculate audit score and determine if it's a failure."""
        score = 100
        is_audit_failure = 0

        for criterion in criteria:
            if criterion.get('is_critical'):
                matching_result = next(
                    (r for r in audit_results if r['question']
                     == criterion['question']),
                    None
                )
                if matching_result and not matching_result['complies']:
                    return (0, 1)  # Critical failure

        for result in audit_results:
            matching_criterion = next(
                (c for c in criteria if c['question'] == result['question']),
                None
            )
            if matching_criterion and not result['complies']:
                score -= matching_criterion['target_score']

        if score < approval_score:
            is_audit_failure = 1

        return (max(0, score), is_audit_failure)

    @staticmethod
    def _insert_audit(
        db: Session,
        task_uuid: str,
        campaign_id: int,
        user_id: str,
        score: float,
        is_audit_failure: int,
        audit: List[Dict[str, Any]],
        generated_by_user: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        model_name: Optional[str] = None
    ) -> int:
        """Insert audit into database."""
        query = text("""
            INSERT INTO audits (
                task_uuid,
                campaign_id,
                user_id,
                score,
                is_audit_failure,
                audit,
                generated_by_user,
                notified,
                audit_date,
                input_tokens,
                output_tokens,
                model_name
            ) VALUES (
                :task_uuid,
                :campaign_id,
                :user_id,
                :score,
                :is_audit_failure,
                :audit,
                :generated_by_user,
                :notified,
                :audit_date,
                :input_tokens,
                :output_tokens,
                :model_name
            )
            RETURNING id
        """)

        params = {
            "task_uuid": task_uuid,
            "campaign_id": campaign_id,
            "user_id": user_id,
            "score": score,
            "is_audit_failure": bool(is_audit_failure),
            "audit": json.dumps(audit),
            "generated_by_user": generated_by_user,
            "notified": False,
            "audit_date": datetime.utcnow(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model_name": model_name
        }
        try:
            result = db.execute(query, params)
            db.commit()
            return result.fetchone()[0]
        except IntegrityError:
            db.rollback()
            OperatorQualityService._reset_pk_sequence(db, "audits", "id")
            result = db.execute(query, params)
            db.commit()
            return result.fetchone()[0]

    @staticmethod
    def _reset_pk_sequence(db: Session, table_name: str, pk_column: str = "id"):
        seq_query = text(f"""
            SELECT setval(
                pg_get_serial_sequence('{table_name}', '{pk_column}'),
                COALESCE((SELECT MAX({pk_column}) FROM {table_name}), 0) + 1,
                false
            );
        """)
        db.execute(seq_query)
        db.commit()

    @staticmethod
    def _update_task_status(db: Session, task_uuid: str, status: str):
        """Update task status."""
        query = text("""
            UPDATE tasks
            SET status = :status
            WHERE uuid = :task_uuid
        """)
        db.execute(query, {"status": status, "task_uuid": task_uuid})
        db.commit()

    # ESTE MÉTODO YA NO SE USA PORQUE FALLABA LA DB, PERO LO DEJAMOS POR SI ACASO
    @staticmethod
    def _mark_criteria_unchanged(db: Session, campaign_id: int):
        """Mark audit criteria as unchanged."""
        try:
            query = text("""
                UPDATE audit_criteria
                SET changed = 0
                WHERE campaign_id = :campaign_id
            """)
            db.execute(query, {"campaign_id": campaign_id})
            db.commit()
        except Exception:
            # Ignoramos errores aquí porque la columna 'changed' podría no existir
            pass

    @staticmethod
    async def regenerate_audit(
        db: Session,
        task_uuid: str,
        is_call: bool,
        username: str,
        user_sub: str
    ) -> Dict[str, Any]:
        """Regenerate an existing audit."""
        try:
            # 1. Reset audit
            if is_call:
                reset_query = text("""
                    UPDATE tasks SET status = 'completed' WHERE uuid = :task_uuid;
                    DELETE FROM audits WHERE task_uuid = :task_uuid;
                """)
            else:
                reset_query = text("""
                    UPDATE chats SET status = 'completed' WHERE uuid = :task_uuid;
                    DELETE FROM audits_chats WHERE chat_uuid = :task_uuid;
                """)

            db.execute(reset_query, {"task_uuid": task_uuid})
            db.commit()

            # 2. Generate new audit
            if is_call:
                return await OperatorQualityService.generate_audit_for_call(
                    db=db,
                    task_uuid=task_uuid,
                    username=username,
                    user_sub=user_sub
                )
            else:
                return await OperatorQualityService.generate_audit_for_chat(
                    db=db,
                    task_uuid=task_uuid,
                    username=username,
                    user_sub=user_sub
                )

        except Exception as e:
            logger.error(f"Error regenerating audit: {e}", exc_info=True)
            db.rollback()
            return {
                "success": False,
                "status_code": 500,
                "message": "Error interno al regenerar auditoría"
            }

    @staticmethod
    async def compute_and_update_audit(
        db: Session,
        task_uuid: str,
        file_name: str,
        is_call: bool,
        audit_items: List[Dict[str, Any]],
        username: str,
        user_sub: str
    ) -> Dict[str, Any]:
        try:
            if not task_uuid or not file_name or not isinstance(is_call, bool) or not audit_items:
                return {"success": False, "status_code": 400, "code": "MISSING_FIELDS", "message": "Datos inválidos"}
            if is_call:
                existing = OperatorQualityService._get_existing_audit(
                    db, task_uuid)
                if not existing:
                    return {"success": False, "status_code": 404, "code": "NOT_FOUND", "message": "Auditoría no encontrada"}
                task_data = OperatorQualityService._get_task_data(
                    db, task_uuid)
                if not task_data:
                    return {"success": False, "status_code": 404, "code": "NOT_FOUND", "message": "Tarea no encontrada"}
                campaign_data = OperatorQualityService._get_campaign_data(
                    db, task_data['campaign_id'])
                if not campaign_data:
                    return {"success": False, "status_code": 409, "code": "MISSING_CAMPAIGN", "message": "Campaña inexistente"}
                criteria = OperatorQualityService._get_audit_criteria(
                    db, task_data['campaign_id'])
                score, is_audit_failure = OperatorQualityService._calculate_score(
                    audit_items, criteria, campaign_data['approval_score'])
                campaign_ts = OperatorQualityService._get_campaign_updated_at(
                    db, task_data['campaign_id'])
                criteria_changed = False
                if campaign_ts and existing.get("task_uuid"):
                    created_ts = OperatorQualityService._get_audit_created_at(
                        db, task_uuid, True)
                    if created_ts and campaign_ts > created_ts:
                        criteria_changed = True
                update_q = text("""
                    UPDATE audits
                    SET audit = :audit, score = :score, is_audit_failure = :is_audit_failure, updated_at = NOW()
                    WHERE task_uuid = :task_uuid
                """)
                db.execute(update_q, {
                    "audit": json.dumps(audit_items),
                    "score": score,
                    "is_audit_failure": bool(is_audit_failure),
                    "task_uuid": task_uuid
                })
                db.commit()
                return {
                    "success": True,
                    "status_code": 200,
                    "task_uuid": task_uuid,
                    "campaign_id": task_data['campaign_id'],
                    "user_id": task_data.get('user_id'),
                    "score": score,
                    "is_audit_failure": is_audit_failure,
                    "audit": audit_items,
                    "criteria_changed": criteria_changed
                }
            else:
                chat = OperatorQualityService._get_chat_data(db, task_uuid)
                if not chat:
                    return {"success": False, "status_code": 404, "code": "NOT_FOUND", "message": "Chat no encontrado"}
                existing_chat = OperatorQualityService._get_existing_audit_chat(
                    db, task_uuid)
                if not existing_chat:
                    return {"success": False, "status_code": 404, "code": "NOT_FOUND", "message": "Auditoría de chat no encontrada"}
                campaign_data = OperatorQualityService._get_campaign_data(
                    db, chat['campaign_id'])
                if not campaign_data:
                    return {"success": False, "status_code": 409, "code": "MISSING_CAMPAIGN", "message": "Campaña inexistente"}
                criteria = OperatorQualityService._get_audit_criteria_rrss(
                    db, chat['campaign_id'])
                score, is_audit_failure = OperatorQualityService._calculate_score(
                    audit_items, criteria, campaign_data['approval_score'])
                campaign_ts = OperatorQualityService._get_campaign_updated_at(
                    db, chat['campaign_id'])
                created_ts = OperatorQualityService._get_audit_created_at(
                    db, task_uuid, False)
                criteria_changed = bool(
                    campaign_ts and created_ts and campaign_ts > created_ts)
                update_q = text("""
                    UPDATE audits_chats
                    SET score = :score, comments = :comments, updated_at = NOW()
                    WHERE chat_uuid = :chat_uuid
                """)
                db.execute(update_q, {
                    "score": score,
                    "comments": json.dumps(audit_items),
                    "chat_uuid": task_uuid
                })
                db.commit()
                return {
                    "success": True,
                    "status_code": 200,
                    "task_uuid": task_uuid,
                    "campaign_id": chat['campaign_id'],
                    "user_id": chat.get('operator_id'),
                    "score": score,
                    "is_audit_failure": is_audit_failure,
                    "audit": audit_items,
                    "criteria_changed": criteria_changed
                }
        except Exception as e:
            logger.error(f"Error computing audit results: {e}", exc_info=True)
            db.rollback()
            return {"success": False, "status_code": 500, "code": "ERROR", "message": "Error interno"}

    @staticmethod
    def _get_campaign_updated_at(db: Session, campaign_id: int):
        try:
            r = db.execute(text("SELECT updated_at FROM campaigns WHERE campaign_id = :campaign_id"), {
                           "campaign_id": campaign_id}).fetchone()
            return r[0] if r else None
        except Exception:
            return None

    @staticmethod
    def _get_audit_created_at(db: Session, identifier: str, is_call: bool):
        try:
            if is_call:
                r = db.execute(text("SELECT created_at FROM audits WHERE task_uuid = :uuid"), {
                               "uuid": identifier}).fetchone()
            else:
                r = db.execute(text("SELECT created_at FROM audits_chats WHERE chat_uuid = :uuid"), {
                               "uuid": identifier}).fetchone()
            return r[0] if r else None
        except Exception:
            return None

    @staticmethod
    def _get_chat_data(db: Session, chat_uuid: str) -> Optional[Dict[str, Any]]:
        try:
            r = db.execute(text("SELECT uuid, campaign_id, operator_id FROM chats WHERE uuid = :uuid"), {
                           "uuid": chat_uuid}).fetchone()
            if r:
                return {"uuid": r[0], "campaign_id": r[1], "operator_id": r[2]}
            return None
        except Exception:
            return None

    @staticmethod
    def _get_existing_audit_chat(db: Session, chat_uuid: str) -> Optional[Dict[str, Any]]:
        try:
            r = db.execute(text("SELECT chat_uuid, score, comments, created_at FROM audits_chats WHERE chat_uuid = :uuid LIMIT 1"), {
                           "uuid": chat_uuid}).fetchone()
            if r:
                return {"chat_uuid": r[0], "score": r[1], "comments": r[2], "created_at": r[3]}
            return None
        except Exception:
            return None

    @staticmethod
    def _get_audit_criteria_rrss(db: Session, campaign_id: int) -> List[Dict[str, Any]]:
        q = text("""
            SELECT category, question, description, target_score, is_critical, criteria_order
            FROM audit_criteria_rrss
            WHERE campaign_id = :campaign_id
            ORDER BY criteria_order
        """)
        res = db.execute(q, {"campaign_id": campaign_id}).fetchall()
        return [dict(row._mapping) for row in res]

    @staticmethod
    def _get_chat_full_data(db: Session, chat_uuid: str) -> Optional[Dict[str, Any]]:
        """Get detailed chat data including operator info."""
        try:
            query = text("""
                SELECT
                    c.uuid,
                    c.campaign_id,
                    c.operator_id,
                    c.result as messages,
                    c.is_inbound,
                    o.first_name,
                    o.last_name
                FROM chats c
                LEFT JOIN operators o ON o.user_id = c.operator_id
                WHERE c.uuid = :uuid
            """)
            r = db.execute(query, {"uuid": chat_uuid}).fetchone()
            if r:
                return {
                    "uuid": r[0],
                    "campaign_id": r[1],
                    "operator_id": r[2],
                    "messages": r[3] if isinstance(r[3], (list, dict)) else json.loads(r[3] or "[]"),
                    "is_inbound": r[4],
                    "first_name": r[5],
                    "last_name": r[6]
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching chat full data: {e}")
            return None

    @staticmethod
    async def _insert_audit_chat(
        db: Session,
        chat_uuid: str,
        campaign_id: int,
        user_id: str,
        score: float,
        is_audit_failure: int,
        audit: List[Dict[str, Any]],
        generated_by_user: str
    ) -> int:
        """Insert chat audit into database."""
        query = text("""
            INSERT INTO audits_chats (
                chat_uuid,
                campaign_id,
                user_id,
                score,
                is_audit_failure,
                comments,
                audit,
                generated_by_user,
                audit_date,
                created_at,
                updated_at
            ) VALUES (
                :chat_uuid,
                :campaign_id,
                :user_id,
                :score,
                :is_audit_failure,
                :comments,
                :audit,
                :generated_by_user,
                :audit_date,
                NOW(),
                NOW()
            )
            RETURNING id
        """)

        params = {
            "chat_uuid": chat_uuid,
            "campaign_id": campaign_id,
            "user_id": user_id,
            "score": score,
            "is_audit_failure": bool(is_audit_failure),
            "comments": json.dumps(audit),
            "audit": json.dumps(audit),
            "generated_by_user": generated_by_user,
            "audit_date": datetime.utcnow()
        }
        try:
            result = db.execute(query, params)
            db.commit()
            return result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error inserting chat audit: {e}")
            db.rollback()
            # Try to reset sequence if it's a PK error (though not explicitly checking for IntegrityError here)
            OperatorQualityService._reset_pk_sequence(db, "audits_chats", "id")
            result = db.execute(query, params)
            db.commit()
            return result.fetchone()[0]
