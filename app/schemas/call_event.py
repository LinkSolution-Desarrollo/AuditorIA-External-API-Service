"""Normalized representation for Anura call events."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.utils.datetime_utils import parse_anura_datetime

REQUIRED_FIELDS = [
    "accountname",
    "accountextension",
    "direction",
    "calling",
    "called",
    "status",
    "duration",
    "billseconds",
    "dialtime",
]


def _to_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        raise ValueError("Numeric value missing")
    text = str(value).strip()
    if not text:
        raise ValueError("Numeric value empty")
    return float(text)


def _ensure_str(value: Any) -> str:
    if value is None:
        raise ValueError("String value missing")
    text = str(value).strip()
    if not text:
        raise ValueError("String value empty")
    return text


class CallEvent(BaseModel):
    agent_name: str
    agent_extension: str
    direction: str
    phone_from: str
    phone_to: str
    call_status: str
    duration_seconds: float
    bill_seconds: float
    call_started_at: datetime
    recording_url: Optional[str] = None

    @classmethod
    def from_anura_payload(cls, payload: Dict[str, Any]) -> "CallEvent":
        missing: List[str] = [field for field in REQUIRED_FIELDS if not payload.get(field)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")

        return cls(
            agent_name=_ensure_str(payload["accountname"]),
            agent_extension=_ensure_str(payload["accountextension"]),
            direction=_ensure_str(payload["direction"]),
            phone_from=_ensure_str(payload["calling"]),
            phone_to=_ensure_str(payload["called"]),
            call_status=_ensure_str(payload["status"]),
            duration_seconds=_to_float(payload["duration"]),
            bill_seconds=_to_float(payload["billseconds"]),
            call_started_at=parse_anura_datetime(_ensure_str(payload["dialtime"])),
            recording_url=payload.get("audio_file_mp3"),
        )
