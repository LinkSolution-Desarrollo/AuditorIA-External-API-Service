from pydantic import BaseModel, Field
from typing import Optional, List
from fastapi import Form


class TranscriptionConfig(BaseModel):
    """
    Configuration parameters for the transcription process.
    Matches the parameters of the /transcribe endpoint in AuditorIA-App.
    """
    language: Optional[str] = "es"
    task: Optional[str] = "transcribe"
    model: Optional[str] = "nova-3"
    device: Optional[str] = "deepgram"
    device_index: Optional[int] = 0
    beam_size: Optional[int] = 5
    patience: Optional[float] = 1.0
    length_penalty: Optional[float] = 1.0
    temperatures: Optional[float] = 0.0
    compression_ratio_threshold: Optional[float] = 2.4
    log_prob_threshold: Optional[float] = -1.0
    no_speech_threshold: Optional[float] = 0.6
    initial_prompt: Optional[str] = None
    suppress_tokens: Optional[str] = Field(
        None, description="Comma-separated list of token ids")
    suppress_numerals: Optional[bool] = False
    vad_onset: Optional[float] = 0.5
    vad_offset: Optional[float] = 0.363

    # Inference configurations
    threads: int = 0
    batch_size: int = 8
    compute_type: str = "float16"
    align_model: Optional[str] = None
    interpolate_method: str = "nearest"

    @classmethod
    def as_form(
        cls,
        language: Optional[str] = Form("es"),
        task: Optional[str] = Form("transcribe"),
        model: Optional[str] = Form("nova-3"),
        device: Optional[str] = Form("deepgram"),
        device_index: Optional[int] = Form(0),
        beam_size: Optional[int] = Form(5),
        patience: Optional[float] = Form(1.0),
        length_penalty: Optional[float] = Form(1.0),
        temperatures: Optional[float] = Form(0.0),
        compression_ratio_threshold: Optional[float] = Form(2.4),
        log_prob_threshold: Optional[float] = Form(-1.0),
        no_speech_threshold: Optional[float] = Form(0.6),
        initial_prompt: Optional[str] = Form(None),
        suppress_tokens: Optional[str] = Form(None),
        suppress_numerals: Optional[bool] = Form(False),
        vad_onset: Optional[float] = Form(0.5),
        vad_offset: Optional[float] = Form(0.363),
        threads: int = Form(0),
        batch_size: int = Form(8),
        compute_type: str = Form("float16"),
        align_model: Optional[str] = Form(None),
        interpolate_method: str = Form("nearest")
    ):
        return cls(
            language=language,
            task=task,
            model=model,
            device=device,
            device_index=device_index,
            beam_size=beam_size,
            patience=patience,
            length_penalty=length_penalty,
            temperatures=temperatures,
            compression_ratio_threshold=compression_ratio_threshold,
            log_prob_threshold=log_prob_threshold,
            no_speech_threshold=no_speech_threshold,
            initial_prompt=initial_prompt,
            suppress_tokens=suppress_tokens,
            suppress_numerals=suppress_numerals,
            vad_onset=vad_onset,
            vad_offset=vad_offset,
            threads=threads,
            batch_size=batch_size,
            compute_type=compute_type,
            align_model=align_model,
            interpolate_method=interpolate_method
        )
