from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    groq_api_key: str = ""
    groq_analysis_model: str = "llama-3.1-70b-versatile"
    openai_api_key: str = ""
    openai_transcription_model: str = "whisper-1"
    openai_analysis_model: str = "gpt-4o"

    data_dir: Path = Path("data")
    jobs_dir: Path = Path("data/jobs")
    clips_dir: Path = Path("data/clips")

    ffmpeg_timeout_seconds: int = 600
    max_clips_per_job: int = 3


settings = Settings()

# Ensure runtime directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.jobs_dir.mkdir(parents=True, exist_ok=True)
settings.clips_dir.mkdir(parents=True, exist_ok=True)