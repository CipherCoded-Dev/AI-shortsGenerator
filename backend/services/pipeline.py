"""End-to-end video processing pipeline with automated Groq/OpenAI/Local fallback routing."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from config import settings
from ffmpeg_utils import FFmpegError, render_vertical_clip
from jobs.store import job_store
from models.schemas import JobStatus, RenderedClip
from services.analyzer import analyze_viral_segments, fallback_segments
from services.downloader import download_youtube_video
from services.transcriber import transcribe_audio

logger = logging.getLogger(__name__)


def _set_status(job_id: str, status: JobStatus, message: str, progress: int) -> None:
    job_store.update(job_id, status=status, message=message, progress_percent=progress)


def run_processing_pipeline(job_id: str) -> None:
    record = job_store.get(job_id)
    if record is None:
        return

    # Extract user-selected framing mode and subtitle preference
    # Accepts a dictionary or pydantic model safely
    if isinstance(record, dict):
        render_mode = record.get("render_mode", "crop")
        subtitle_enabled = record.get("subtitle_enabled", True)
        youtube_url = record.get("youtube_url")
    else:
        render_mode = getattr(record, "render_mode", "crop")
        subtitle_enabled = getattr(record, "subtitle_enabled", True)
        youtube_url = getattr(record, "youtube_url", "")

    job_dir = settings.jobs_dir / job_id
    clips_dir = settings.clips_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Download YouTube Video
        _set_status(job_id, JobStatus.DOWNLOADING, "Downloading video from YouTube...", 10)
        video_path, metadata = download_youtube_video(youtube_url, job_dir)
        job_store.update(
            job_id,
            source_video_path=str(video_path),
            video_title=metadata.get("title"),
            metadata=metadata,
        )

        words: list[dict[str, float | str]] = []
        segments = []

        # Step 2: Transcribe & Analyze with AI (Groq / OpenAI) with automatic local fallback
        try:
            _set_status(job_id, JobStatus.TRANSCRIBING, "Generating transcript with AI...", 35)
            words = transcribe_audio(video_path)
            job_store.update(job_id, transcript_words=words)

            _set_status(job_id, JobStatus.ANALYZING, "Analyzing viral segments with AI...", 55)
            segments = analyze_viral_segments(
                words,
                video_title=metadata.get("title"),
                max_clips=settings.max_clips_per_job,
            )
        except RuntimeError as api_error:
            logger.warning("AI step skipped (%s). Using fallback segment selection.", api_error)
            _set_status(
                job_id,
                JobStatus.ANALYZING,
                f"AI unavailable ({api_error}). Switching to local fallback...",
                55,
            )
            segments = fallback_segments(words, video_duration=metadata.get("duration"))

        # Safety catch if AI returned an empty array
        if not segments:
            logger.warning("No clips returned from AI. Generating fallback segment.")
            segments = fallback_segments(words, video_duration=metadata.get("duration"))

        job_store.update(job_id, segments=segments)

        # Step 3: Render Clips using FFmpeg
        rendered: list[RenderedClip] = []
        total = len(segments)
        for index, segment in enumerate(segments):
            progress = 60 + int((index / max(total, 1)) * 35)
            _set_status(
                job_id,
                JobStatus.RENDERING,
                f"Rendering vertical clip {index + 1} of {total} ({render_mode} mode)...",
                progress,
            )

            clip_id = str(uuid.uuid4())[:8]
            filename = f"clip_{index + 1}_{clip_id}.mp4"
            output_path = clips_dir / filename

            # Access segment start/end whether Pydantic object or Dict
            start_time = getattr(segment, "start_time", None) or segment.get("start_time", 0.0)
            end_time = getattr(segment, "end_time", None) or segment.get("end_time", 10.0)

            # Pass render_mode, transcript words, and subtitle_enabled for ASS subtitle burn-in
            render_vertical_clip(
                Path(video_path),
                output_path,
                start_time=start_time,
                end_time=end_time,
                render_mode=render_mode,
                words=words,
                subtitle_enabled=subtitle_enabled,
            )

            rendered.append(
                RenderedClip(
                    clip_id=clip_id,
                    segment=segment,
                    filename=filename,
                    download_url=f"/api/clips/{job_id}/download/{filename}",
                )
            )

        # Step 4: Complete Job
        job_store.update(
            job_id,
            clips=rendered,
            status=JobStatus.COMPLETED,
            message=f"Successfully rendered {len(rendered)} clip(s).",
            progress_percent=100,
        )

    except FFmpegError as exc:
        logger.exception("FFmpeg failed for job %s", job_id)
        job_store.update(
            job_id,
            status=JobStatus.FAILED,
            message="Video rendering failed.",
            error=str(exc),
        )
    except Exception as exc:
        logger.exception("Pipeline failed for job %s", job_id)
        job_store.update(
            job_id,
            status=JobStatus.FAILED,
            message="Processing failed.",
            error=str(exc),
        )

