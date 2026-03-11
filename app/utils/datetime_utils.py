"""Helpers to parse timestamps emitted by Anura."""
from datetime import datetime, timezone
from typing import Iterable


def parse_anura_datetime(value: str) -> datetime:
    """Normalize Anura time strings into naive UTC datetimes."""
    if not isinstance(value, str):
        raise ValueError("datetime must be a string")

    text = value.strip()
    if not text:
        raise ValueError("datetime cannot be empty")

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        pass

    formats: Iterable[str] = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
    )

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    raise ValueError(f"Invalid datetime format: {value}")
