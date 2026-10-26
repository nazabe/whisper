from types import SimpleNamespace

from app.config import Settings
from app.transcriber import WhisperTranscriber


class FakeModel:
    def __init__(self) -> None:
        self.captured: dict[str, object] = {}

    def transcribe(self, audio_path: str, **kwargs: object):
        self.captured = {"audio_path": audio_path, **kwargs}
        info = SimpleNamespace(
            language="es",
            language_probability=1.0,
            duration=2.0,
        )
        segment = SimpleNamespace(
            start=0.0,
            end=2.0,
            text=" hola mundo ",
            avg_logprob=-0.2,
            no_speech_prob=0.1,
            compression_ratio=1.2,
        )
        return [segment], info


def test_transcribe_forwards_decoding_options() -> None:
    settings = Settings(
        vad_filter=True,
        condition_on_previous_text=False,
        hotwords="Kotlin WebView",
        beam_size=5,
    )
    transcriber = WhisperTranscriber(settings)
    model = FakeModel()
    transcriber._model = model

    result = transcriber.transcribe("audio.webm", "es")

    assert model.captured["audio_path"] == "audio.webm"
    assert model.captured["language"] == "es"
    assert model.captured["vad_filter"] is True
    assert model.captured["condition_on_previous_text"] is False
    assert model.captured["hotwords"] == "Kotlin WebView"
    assert result.text == "hola mundo"
    assert result.segments[0].text == "hola mundo"


def test_empty_hotwords_are_not_forwarded() -> None:
    settings = Settings(hotwords="")
    transcriber = WhisperTranscriber(settings)
    model = FakeModel()
    transcriber._model = model

    transcriber.transcribe("audio.webm", "es")

    assert "hotwords" not in model.captured
