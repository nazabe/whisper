from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WHISPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "es"
    beam_size: int = 5
    vad_filter: bool = True
    condition_on_previous_text: bool = False
    hotwords: str = (
        "Android Kotlin Java WebView APK HTML CSS JavaScript "
        "manifest Activity Service"
    )
    cpu_threads: int = 0
    max_concurrency: int = 1
    queue_timeout_sec: float = 30.0
    max_upload_mb: int = 100
    model_cache_dir: str | None = None
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
