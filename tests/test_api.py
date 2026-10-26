import asyncio
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.schemas import Segment, TranscribeResponse
from app.transcriber import TranscriptionError


class FakeTranscriber:
    def __init__(self, loaded: bool = True, error: Exception | None = None) -> None:
        self.loaded = loaded
        self.error = error
        self.calls: list[str | None] = []
        self.last_path: str | None = None

    def transcribe(self, audio_path: str, language: str | None) -> TranscribeResponse:
        self.calls.append(language)
        self.last_path = audio_path
        if self.error is not None:
            raise self.error
        return TranscribeResponse(
            language="es",
            language_probability=1.0,
            duration_sec=2.0,
            model="small",
            compute_type="int8",
            text="hola mundo",
            segments=[Segment(id=0, start=0.0, end=2.0, text="hola mundo")],
        )


def build_app(
    *, loaded: bool = True, error: Exception | None = None
) -> tuple[object, FakeTranscriber, Settings]:
    app = create_app()
    settings = Settings()
    fake = FakeTranscriber(loaded=loaded, error=error)
    app.state.settings = settings
    app.state.transcriber = fake
    app.state.semaphore = asyncio.Semaphore(1)
    return app, fake, settings


def build_client(app: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


async def test_health_ok() -> None:
    app, _, _ = build_app()
    async with build_client(app) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["model_loaded"] is True
    assert response.json()["status"] == "ok"


async def test_health_reports_model_not_loaded() -> None:
    app, _, _ = build_app(loaded=False)
    async with build_client(app) as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["model_loaded"] is False


async def test_missing_file_returns_422() -> None:
    app, _, _ = build_app()
    async with build_client(app) as client:
        response = await client.post("/transcribe")

    assert response.status_code == 422


async def test_success_response_contract() -> None:
    app, fake, _ = build_app()
    async with build_client(app) as client:
        response = await client.post(
            "/transcribe",
            files={"file": ("audio.mp3", b"fake-audio", "audio/mpeg")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "es"
    assert body["duration_sec"] == 2.0
    assert body["text"] == "hola mundo"
    assert body["segments"] == [
        {"id": 0, "start": 0.0, "end": 2.0, "text": "hola mundo"}
    ]
    assert fake.calls == ["es"]


async def test_language_override_is_forwarded() -> None:
    app, fake, _ = build_app()
    async with build_client(app) as client:
        response = await client.post(
            "/transcribe",
            files={"file": ("audio.mp3", b"fake-audio", "audio/mpeg")},
            data={"language": "fr"},
        )

    assert response.status_code == 200
    assert fake.calls == ["fr"]


async def test_language_auto_maps_to_none() -> None:
    app, fake, _ = build_app()
    async with build_client(app) as client:
        response = await client.post(
            "/transcribe",
            files={"file": ("audio.mp3", b"fake-audio", "audio/mpeg")},
            data={"language": "auto"},
        )

    assert response.status_code == 200
    assert fake.calls == [None]


async def test_empty_file_is_rejected() -> None:
    app, _, _ = build_app()
    async with build_client(app) as client:
        response = await client.post(
            "/transcribe",
            files={"file": ("audio.mp3", b"", "audio/mpeg")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Empty audio file"


async def test_unsupported_content_type_is_rejected() -> None:
    app, _, _ = build_app()
    async with build_client(app) as client:
        response = await client.post(
            "/transcribe",
            files={"file": ("audio.txt", b"not-audio", "text/plain")},
        )

    assert response.status_code == 400


async def test_oversized_upload_is_rejected() -> None:
    app, _, settings = build_app()
    settings.max_upload_mb = 1
    async with build_client(app) as client:
        response = await client.post(
            "/transcribe",
            files={"file": ("audio.mp3", b"x" * (2 * 1024 * 1024), "audio/mpeg")},
        )

    assert response.status_code == 413


async def test_transcription_error_is_mapped_to_400() -> None:
    app, _, _ = build_app(error=TranscriptionError("bad audio"))
    async with build_client(app) as client:
        response = await client.post(
            "/transcribe",
            files={"file": ("audio.mp3", b"fake-audio", "audio/mpeg")},
        )

    assert response.status_code == 400


async def test_queue_timeout_returns_503() -> None:
    app, _, settings = build_app()
    settings.queue_timeout_sec = 0.01
    await app.state.semaphore.acquire()
    try:
        async with build_client(app) as client:
            response = await client.post(
                "/transcribe",
                files={"file": ("audio.mp3", b"fake-audio", "audio/mpeg")},
            )
    finally:
        app.state.semaphore.release()

    assert response.status_code == 503
    assert response.json()["detail"] == "Transcription queue is busy"


async def test_temporary_file_is_removed_after_request() -> None:
    app, fake, _ = build_app()
    async with build_client(app) as client:
        response = await client.post(
            "/transcribe",
            files={"file": ("audio.mp3", b"fake-audio", "audio/mpeg")},
        )

    assert response.status_code == 200
    assert fake.last_path is not None
    assert not Path(fake.last_path).exists()
