import logging
import time

from faster_whisper import WhisperModel

from .config import Settings
from .schemas import Segment, TranscribeResponse

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """Raised when the audio cannot be transcribed."""


class WhisperTranscriber:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: WhisperModel | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        kwargs: dict[str, object] = {}
        if self._settings.model_cache_dir:
            kwargs["download_root"] = self._settings.model_cache_dir

        started = time.perf_counter()
        self._model = WhisperModel(
            self._settings.model,
            device=self._settings.device,
            compute_type=self._settings.compute_type,
            **kwargs,
        )
        logger.info(
            "whisper model loaded model=%s device=%s compute_type=%s elapsed_ms=%.0f",
            self._settings.model,
            self._settings.device,
            self._settings.compute_type,
            (time.perf_counter() - started) * 1000,
        )

    def transcribe(self, audio_path: str, language: str | None) -> TranscribeResponse:
        if self._model is None:
            raise TranscriptionError("Whisper model is not loaded")

        started = time.perf_counter()
        try:
            segments_iter, info = self._model.transcribe(
                audio_path,
                beam_size=self._settings.beam_size,
                language=language,
                vad_filter=self._settings.vad_filter,
            )
            segments = [
                Segment(
                    id=index,
                    start=float(segment.start),
                    end=float(segment.end),
                    text=segment.text.strip(),
                )
                for index, segment in enumerate(segments_iter)
            ]
        except Exception as exc:
            raise TranscriptionError("Failed to transcribe audio") from exc

        duration_sec = float(info.duration or 0.0)
        if duration_sec <= 0 and segments:
            duration_sec = segments[-1].end

        text = " ".join(segment.text for segment in segments).strip()
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "transcription completed language=%s language_probability=%.4f "
            "duration_sec=%.2f segments=%d inference_ms=%.0f",
            info.language,
            info.language_probability,
            duration_sec,
            len(segments),
            elapsed_ms,
        )

        return TranscribeResponse(
            language=info.language,
            language_probability=float(info.language_probability),
            duration_sec=duration_sec,
            model=self._settings.model,
            compute_type=self._settings.compute_type,
            text=text,
            segments=segments,
        )
