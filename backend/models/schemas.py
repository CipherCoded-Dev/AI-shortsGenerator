from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class JobStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float


class ClipSegment(BaseModel):
    start_time: float
    end_time: float
    virality_score: int = Field(ge=1, le=10)
    clip_title: str
    hook_reason: str


class RenderedClip(BaseModel):
    clip_id: str
    segment: ClipSegment
    filename: str
    download_url: str


class ProcessVideoRequest(BaseModel):
    youtube_url: HttpUrl
    render_mode: str = "crop"
    subtitle_enabled: bool = True


class ProcessVideoResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    progress_percent: int = Field(ge=0, le=100)
    video_title: str | None = None
    error: str | None = None


class ClipsResponse(BaseModel):
    job_id: str
    status: JobStatus
    clips: list[RenderedClip]
    metadata: dict[str, Any] = Field(default_factory=dict)
