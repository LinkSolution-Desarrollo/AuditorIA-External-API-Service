import magic
from fastapi import UploadFile, HTTPException
from app.core.config import get_settings

settings = get_settings()

VALID_MIME_TYPES = [
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav", 
    "audio/ogg",
    "audio/x-m4a",
    "audio/mp4",
    "audio/flac",
    "audio/aac",
    "application/octet-stream" # Sometimes uploads come as this
]

async def validate_file(file: UploadFile):
    # 1. Check extension
    filename = file.filename.lower()
    if not any(filename.endswith(ext) for ext in settings.ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file extension. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # 2. Check Magic Numbers (Read first 2KB)
    file_header = await file.read(2048)
    await file.seek(0) # Reset position
    
    mime_type = magic.from_buffer(file_header, mime=True)
    
    # Basic check - Magic can be tricky with audio, but usually identifies audio/xy
    if not mime_type.startswith("audio/") and mime_type != "application/octet-stream":
         raise HTTPException(
            status_code=400, 
            detail=f"Invalid file content detected: {mime_type}. Please upload a valid audio file."
        )
    
    return True
