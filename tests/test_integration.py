import os
from pathlib import Path

import pytest

from app.config import Settings
from app.transcriber import WhisperTranscriber

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent / "fixtures" / "sample_20s.mp3"


@pytest.mark.skipif(
    os.getenv("RUN_WHISPER_INTEGRATION") != "1",
    reason="set RUN_WHISPER_INTEGRATION=1 to run the real-model test",
)
def test_real_transcription_returns_segments() -> None:
    transcriber = WhisperTranscriber(
        Settings(model="small", device="cpu", compute_type="int8")
    )
    transcriber.load()

    result = transcriber.transcribe(str(FIXTURE), "es")

    assert result.language == "es"
    assert result.duration_sec > 0
    assert result.text
    assert result.segments
    assert result.segments[0].start >= 0
    assert result.segments[-1].end <= result.duration_sec + 1
