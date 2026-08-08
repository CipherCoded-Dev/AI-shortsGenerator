"""Robust YouTube video/audio downloader with anti-bot bypass controls."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import yt_dlp

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def auto_update_ytdlp() -> None:
    """Ensures yt-dlp is always running its latest version to prevent 403s."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception as err:
        logger.warning("Auto-update check for yt-dlp failed: %s", err)


def download_youtube_video(url: str, output_dir: Path) -> tuple[Path, dict[str, Any]]:
    """
    Downloads YouTube MP4 video using robust client fallback strategies.
    Returns (file_path, metadata).
    """
    # 1. Attempt silent auto-update before download
    auto_update_ytdlp()

    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / "source.%(ext)s")
    ffmpeg_exe = BACKEND_DIR / "ffmpeg.exe"

    ydl_opts: dict[str, Any] = {
    # Force highest resolution (1080p+) stream before falling back to standard best
    "format": "bestvideo[height>=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=1080]+bestaudio/bestvideo+bestaudio/best",
    "outtmpl": output_template,
    "merge_output_format": "mp4",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "retries": 5,
    "fragment_retries": 5,
    # Browser Spoofing Headers
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    },
    # Rotate Player Clients if default web client triggers 403
    "extractor_args": {
        "youtube": {
            "player_client": ["mweb", "android", "ios", "web"],
            "player_skip": ["webpage", "configs"],
        }
    },
}

    if ffmpeg_exe.exists():
        ydl_opts["ffmpeg_location"] = str(BACKEND_DIR)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError("yt-dlp returned no video information.")

        prepared = ydl.prepare_filename(info)
        video_path = Path(prepared)

        if video_path.suffix != ".mp4":
            mp4_candidate = video_path.with_suffix(".mp4")
            if mp4_candidate.exists():
                video_path = mp4_candidate

        if not video_path.exists():
            raise RuntimeError(f"Download finished but output file missing: {video_path}")

        metadata = {
            "title": info.get("title", "Untitled Video"),
            "duration": float(info.get("duration") or 0.0),
            "uploader": info.get("uploader", "Unknown"),
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url", url),
        }

        logger.info("Successfully downloaded video to %s", video_path)
        return video_path, metadata