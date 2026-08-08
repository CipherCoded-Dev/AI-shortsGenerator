"""Transcription service supporting Groq Free API & OpenAI Whisper API with fallback handling."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

import httpx
from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)


def extract_and_compress_audio(video_path: Path) -> Path:
    """
    Extracts audio from video and compresses it to a lightweight 16kHz mono MP3
    to prevent API upload timeouts.
    """
    audio_path = video_path.with_suffix(".temp.mp3")
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",                  # Disable video
        "-ac", "1",              # Convert to mono
        "-ar", "16000",          # 16kHz sample rate (optimal for speech)
        "-b:a", "64k",           # Low compressed bitrate
        str(audio_path),
    ]
    
    logger.info("Extracting and compressing audio for Whisper API...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.warning("Audio extraction failed, falling back to raw file: %s", result.stderr)
        return video_path
        
    return audio_path


def transcribe_audio(video_path: Path) -> list[dict[str, float | str]]:
    """
    Transcribe video/audio and return word-level timestamps using Groq or OpenAI.
    """
    groq_key = os.getenv("GROQ_API_KEY") or getattr(settings, "groq_api_key", None)
    openai_key = getattr(settings, "openai_api_key", None) or os.getenv("OPENAI_API_KEY")

    client: OpenAI | None = None
    model_name: str = ""
    extra_params: dict = {}

    # 1. Prefer Groq Free Whisper
    if groq_key and str(groq_key).strip():
        logger.info("Initializing Groq Free Transcription Engine (whisper-large-v3)...")
        client = OpenAI(
            api_key=str(groq_key).strip(),
            base_url="https://api.groq.com/openai/v1",
            timeout=httpx.Timeout(600.0, connect=60.0),
        )
        model_name = os.getenv("GROQ_TRANSCRIPTION_MODEL", "whisper-large-v3")

    # 2. Fall back to OpenAI Whisper
    elif openai_key and str(openai_key).strip():
        logger.info("Initializing OpenAI Transcription Engine (%s)...", settings.openai_transcription_model)
        client = OpenAI(
            api_key=str(openai_key).strip(),
            timeout=httpx.Timeout(600.0, connect=60.0),
        )
        model_name = settings.openai_transcription_model
        extra_params["timestamp_granularities"] = ["word", "segment"]

    # 3. No keys -> raise RuntimeError to trigger local fallback in pipeline.py
    else:
        raise RuntimeError("No transcription API key found (GROQ_API_KEY / OPENAI_API_KEY missing)")

    audio_file_path = extract_and_compress_audio(video_path)

    try:
        with audio_file_path.open("rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=model_name,
                file=audio_file,
                response_format="verbose_json",
                **extra_params,
            )
    except Exception as exc:
        logger.error("Transcription API request failed: %s", exc)
        raise RuntimeError(f"Transcription API failure: {exc}") from exc
    finally:
        if audio_file_path != video_path and audio_file_path.exists():
            audio_file_path.unlink(missing_ok=True)

    words: list[dict[str, float | str]] = []

    if getattr(response, "words", None):
        for item in response.words:
            words.append({
                "word": item.word,
                "start": float(item.start),
                "end": float(item.end),
            })
    elif getattr(response, "segments", None):
        for segment in response.segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            for token in text.split():
                words.append({
                    "word": token,
                    "start": float(segment.start),
                    "end": float(segment.end),
                })

    if not words and getattr(response, "text", None):
        words.append({"word": response.text.strip(), "start": 0.0, "end": 1.0})

    logger.info("Transcribed %d word timestamps", len(words))
    return words