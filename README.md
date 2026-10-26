# Whisper Transcription Service

FastAPI microservice that receives an audio upload and returns a transcript.
It does **not** call an LLM and does **not** persist data: the Bun/Fastify
backend owns job orchestration, analysis, and MongoDB.

## Requirements

- Python 3.14 (see `.python-version`)
- [uv](https://docs.astral.sh/uv/)
- Network access on the first run to download the Whisper model, unless the
  model is already cached

## Setup

```bash
uv sync
cp .env.example .env
```

## Run

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`--workers 1` is mandatory. Every Uvicorn worker loads its own copy of the
model, multiplying RAM usage. Scale with more containers, not more workers.

## API

### `GET /health`

```bash
curl http://127.0.0.1:8000/health
```

```json
{
  "status": "ok",
  "model": "small",
  "device": "cpu",
  "compute_type": "int8",
  "model_loaded": true
}
```

Returns `503` while the model is not loaded.

### `POST /transcribe`

`multipart/form-data` with:

- `file` (required): audio file.
- `language` (optional): language code; `auto` lets Whisper detect it.
  Defaults to `WHISPER_LANGUAGE` (`es`).

```bash
curl -F "file=@tests/fixtures/sample_20s.mp3;type=audio/mpeg" \
  http://127.0.0.1:8000/transcribe
```

```json
{
  "language": "es",
  "language_probability": 1.0,
  "duration_sec": 20.0,
  "model": "small",
  "compute_type": "int8",
  "text": "full transcript",
  "segments": [
    { "id": 0, "start": 0.0, "end": 4.0, "text": "..." }
  ]
}
```

Errors:

| Status | Cause |
|---|---|
| `400` | Empty file, unsupported content type, or undecodable audio |
| `413` | Upload exceeds `WHISPER_MAX_UPLOAD_MB` |
| `422` | Missing or invalid form fields |
| `503` | Model not ready or transcription queue busy |
| `500` | Unexpected inference failure |

## Configuration

All variables use the `WHISPER_` prefix and are loaded from the environment or
`.env`.

| Variable | Default | Purpose |
|---|---|---|
| `WHISPER_MODEL` | `small` | Model size or name |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` on CPU, `float16` on GPU |
| `WHISPER_LANGUAGE` | `es` | Default language; `auto` detects |
| `WHISPER_BEAM_SIZE` | `5` | Decoding beam size |
| `WHISPER_VAD_FILTER` | `false` | Skip silence with VAD |
| `WHISPER_MAX_CONCURRENCY` | `1` | Simultaneous transcriptions |
| `WHISPER_QUEUE_TIMEOUT_SEC` | `30` | Max wait for a free slot |
| `WHISPER_MAX_UPLOAD_MB` | `100` | Upload size limit |
| `WHISPER_MODEL_CACHE_DIR` | unset | Custom HuggingFace cache directory |
| `WHISPER_LOG_LEVEL` | `INFO` | Log level |

## Tests

Fast contract tests (no model download, no network):

```bash
uv run pytest
```

Real-model integration test (uses `tests/fixtures/sample_20s.mp3`):

```bash
RUN_WHISPER_INTEGRATION=1 uv run pytest -m integration
```

## Layout

```
app/
├── config.py       # environment-driven settings
├── schemas.py      # Pydantic response models
├── transcriber.py  # model lifecycle and inference
└── main.py         # FastAPI app, routes, upload handling
tests/
├── fixtures/       # short audio fixture
├── test_api.py     # contract tests with a fake transcriber
└── test_integration.py
legacy/
└── main_batch.py   # previous batch script, not used by the service
```

## Notes

- `av<19` is pinned because `faster-whisper 1.2.1` calls
  `av.open(..., metadata_errors=...)`, which PyAV 19 no longer accepts.
- Uploads are streamed to a temporary file and deleted after every request.
  Audio is never persisted by this service.
- `legacy/main_batch.py` is kept for reference only. If you ever re-enable its
  LLM block, it reads `DEEPSEEK_API_KEY` from the environment. Rotate any key
  that was previously committed or hardcoded.
