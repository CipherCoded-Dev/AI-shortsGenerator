"""FastAPI Application Entrypoint for Video Shorts Generator Pipeline."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from jobs.store import job_store
from models.schemas import JobStatus, ProcessVideoRequest
from services.pipeline import run_processing_pipeline

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Shorts Generator API",
    description="Transforms long YouTube videos into vertical short clips.",
    version="1.0.0",
)

# 1. Enable CORS for Next.js Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Ensure Directories Exist and Mount Static Clip Serving
settings.clips_dir.mkdir(parents=True, exist_ok=True)
app.mount("/clips", StaticFiles(directory=settings.clips_dir), name="clips")


@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "ok", "service": "AI Shorts Generator Backend"}


@app.post("/api/process-video")
def process_video(payload: ProcessVideoRequest):
    """
    Initiates video processing for a given YouTube URL.
    Runs the pipeline in a background thread to prevent blocking HTTP requests.
    """
    url = str(payload.youtube_url) if payload.youtube_url else None
    if not url:
        raise HTTPException(status_code=400, detail="Missing YouTube URL in request body.")

    # Create new job in thread-safe memory store, carrying selected render mode and subtitle preference
    record = job_store.create(
        url,
        render_mode=payload.render_mode,
        subtitle_enabled=payload.subtitle_enabled,
    )
    job_id = record.job_id

    # Spawn background thread to run pipeline asynchronously
    thread = threading.Thread(
        target=run_processing_pipeline,
        args=(job_id,),
        daemon=True,
    )
    thread.start()

    logger.info("Queued job %s for processing URL: %s", job_id, url)
    return {"job_id": job_id, "status": JobStatus.QUEUED}


@app.get("/api/status/{job_id}")
def get_job_status(job_id: str):
    """
    Polls processing status, progress percentage, and rendered clip results.
    """
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return record


@app.get("/api/clips/{job_id}")
def list_clips(job_id: str):
    """
    Lists rendered clips for a given job.
    """
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return {
        "job_id": job_id,
        "status": record.status,
        "clips": record.clips,
        "metadata": record.metadata,
    }


@app.get("/api/clips/{job_id}/download/{filename}")
def download_clip(job_id: str, filename: str):
    """
    Direct FileResponse endpoint to stream/download rendered MP4 clips.
    """
    file_path = settings.clips_dir / job_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Requested clip file does not exist.")

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=filename,
        headers={"Accept-Ranges": "bytes"},
    )

