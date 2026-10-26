import asyncio
import logging
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .schemas import HealthResponse, TranscribeResponse
from .transcriber import TranscriptionError, WhisperTranscriber

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/x-m4a",
    "video/webm",
}

router = APIRouter()


def _resolve_language(requested: str | None, settings: Settings) -> str | None:
    if requested is not None:
        value = requested.strip()
        if value.lower() == "auto":
            return None
        if value:
            return value
    if settings.language.lower() == "auto":
        return None
    return settings.language


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    transcriber = WhisperTranscriber(settings)
    app.state.settings = settings
    app.state.transcriber = transcriber
    app.state.semaphore = asyncio.Semaphore(settings.max_concurrency)

    await asyncio.to_thread(transcriber.load)
    yield


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    transcriber: WhisperTranscriber = request.app.state.transcriber
    payload = HealthResponse(
        status="ok" if transcriber.loaded else "loading",
        model=settings.model,
        device=settings.device,
        compute_type=settings.compute_type,
        model_loaded=transcriber.loaded,
    )
    return JSONResponse(
        status_code=200 if transcriber.loaded else 503,
        content=payload.model_dump(),
    )


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
) -> TranscribeResponse:
    settings: Settings = request.app.state.settings
    transcriber: WhisperTranscriber = request.app.state.transcriber
    semaphore: asyncio.Semaphore = request.app.state.semaphore

    if not transcriber.loaded:
        raise HTTPException(status_code=503, detail="Whisper model is not ready")

    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type: {content_type or 'unknown'}",
        )

    request_id = uuid.uuid4().hex
    suffix = Path(file.filename or "").suffix or ".audio"
    limit_bytes = settings.max_upload_mb * 1024 * 1024
    tmp_path: Path | None = None
    acquired = False
    started = time.perf_counter()

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            total_bytes = 0
            while chunk := await file.read(CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > limit_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Audio exceeds the {settings.max_upload_mb} MB limit",
                    )
                tmp.write(chunk)

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")

        try:
            await asyncio.wait_for(
                semaphore.acquire(), timeout=settings.queue_timeout_sec
            )
            acquired = True
        except TimeoutError as exc:
            raise HTTPException(
                status_code=503, detail="Transcription queue is busy"
            ) from exc

        resolved_language = _resolve_language(language, settings)
        try:
            result = await asyncio.to_thread(
                transcriber.transcribe, str(tmp_path), resolved_language
            )
        except TranscriptionError as exc:
            logger.warning(
                "transcription failed request_id=%s error=%s", request_id, exc
            )
            raise HTTPException(
                status_code=400, detail="Could not transcribe the audio file"
            ) from exc
        except Exception as exc:
            logger.exception("unexpected transcription error request_id=%s", request_id)
            raise HTTPException(
                status_code=500, detail="Unexpected transcription failure"
            ) from exc

        logger.info(
            "request completed request_id=%s bytes=%d language=%s elapsed_ms=%.0f",
            request_id,
            total_bytes,
            result.language,
            (time.perf_counter() - started) * 1000,
        )
        return result
    finally:
        if acquired:
            semaphore.release()
        await file.close()
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Whisper Transcription Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
