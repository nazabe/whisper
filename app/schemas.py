from pydantic import BaseModel, Field


class Segment(BaseModel):
    id: int = Field(description="Zero-based segment index")
    start: float = Field(description="Segment start in seconds")
    end: float = Field(description="Segment end in seconds")
    text: str = Field(description="Segment text in the detected language")


class TranscribeResponse(BaseModel):
    language: str = Field(description="Detected or requested language code")
    language_probability: float = Field(
        description="Language detection probability between 0 and 1"
    )
    duration_sec: float = Field(description="Audio duration in seconds")
    model: str = Field(description="Whisper model used for transcription")
    compute_type: str = Field(description="CTranslate2 compute type")
    text: str = Field(description="Full transcript with segments joined by spaces")
    segments: list[Segment] = Field(description="Ordered transcription segments")


class HealthResponse(BaseModel):
    status: str = Field(description="Service status")
    model: str = Field(description="Configured Whisper model")
    device: str = Field(description="Configured inference device")
    compute_type: str = Field(description="Configured compute type")
    model_loaded: bool = Field(description="Whether the model is ready to transcribe")
