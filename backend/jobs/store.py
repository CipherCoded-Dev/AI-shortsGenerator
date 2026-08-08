"""In-memory job store for Phase 1. Replace with Redis/DB for production."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from models.schemas import ClipSegment, JobStatus, RenderedClip


@dataclass
class JobRecord:
    job_id: str
    youtube_url: str
    render_mode: str = "crop"
    subtitle_enabled: bool = True
    status: JobStatus = JobStatus.QUEUED
    message: str = "Job queued"
    progress_percent: int = 0
    video_title: str | None = None
    error: str | None = None
    source_video_path: str | None = None
    transcript_words: list[dict[str, Any]] = field(default_factory=list)
    segments: list[ClipSegment] = field(default_factory=list)
    clips: list[RenderedClip] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create(
        self,
        youtube_url: str,
        render_mode: str = "crop",
        subtitle_enabled: bool = True,
    ) -> JobRecord:
        job_id = str(uuid.uuid4())
        record = JobRecord(
            job_id=job_id,
            youtube_url=youtube_url,
            render_mode=render_mode,
            subtitle_enabled=subtitle_enabled,
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        message: str | None = None,
        progress_percent: int | None = None,
        **fields: Any,
    ) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            if status is not None:
                record.status = status
            if message is not None:
                record.message = message
            if progress_percent is not None:
                record.progress_percent = progress_percent
            for key, value in fields.items():
                setattr(record, key, value)
            return record


job_store = JobStore()
