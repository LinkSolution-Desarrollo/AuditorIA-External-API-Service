from mutagen import File
import logging

logger = logging.getLogger(__name__)


def get_audio_duration(file_path: str) -> float:
    """
    Get the duration of an audio file in seconds.
    Returns 0.0 if the duration cannot be determined.
    """
    try:
        audio = File(file_path)
        if audio is not None and audio.info is not None:
            duration = float(audio.info.length)
            logger.info(
                f"Calculated audio duration: {duration} seconds for {file_path}")
            return duration
    except Exception as e:
        logger.error(f"Error calculating audio duration for {file_path}: {e}")

    return 0.0
