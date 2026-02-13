import subprocess
import json
import logging
from mutagen import File

logger = logging.getLogger(__name__)


def get_audio_duration(file_path: str) -> float:
    """
    Get the duration of an audio file in seconds.
    Tries ffprobe first, then mutagen as fallback.
    Returns 0.0 if the duration cannot be determined.
    """
    # 1. Try ffprobe (more reliable)
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        duration = None
        if "format" in data and "duration" in data["format"]:
            duration = float(data["format"]["duration"])
        elif "streams" in data:
            for stream in data["streams"]:
                if "duration" in stream:
                    duration = float(stream["duration"])
                    break

        if duration is not None:
            logger.info(f"FFprobe duration: {duration}s for {file_path}")
            return duration

    except Exception as e:
        logger.warning(f"FFprobe failed for {file_path}: {e}")

    # 2. Fallback to mutagen
    try:
        audio = File(file_path)
        if audio is not None and audio.info is not None:
            duration = float(audio.info.length)
            logger.info(f"Mutagen duration: {duration}s for {file_path}")
            return duration
    except Exception as e:
        logger.error(f"Mutagen failed for {file_path}: {e}")

    return 0.0
