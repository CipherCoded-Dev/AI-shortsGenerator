"""LLM virality analysis for clip segment selection supporting Groq & OpenAI."""

from __future__ import annotations

import json
import logging
import os

from openai import OpenAI

from config import settings
from models.schemas import ClipSegment

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """You are a short-form video editor for YouTube Shorts, TikTok, and Reels.
Given a timestamped transcript, identify the most viral 30-60 second segments.

Return ONLY valid JSON with this shape:
{
  "clips": [
    {
      "start_time": 12.5,
      "end_time": 52.0,
      "virality_score": 9,
      "clip_title": "Short catchy title",
      "hook_reason": "Why this moment will perform well"
    }
  ]
}

Rules:
- Each clip must be between 30 and 60 seconds.
- Return up to 3 clips, sorted by virality_score descending.
- Use seconds as floats matching the transcript timestamps.
- Prefer strong hooks, emotional peaks, surprising statements, and actionable advice.
"""


def _format_transcript_for_llm(words: list[dict[str, float | str]], max_words: int = 800) -> str:
    lines: list[str] = []
    for word in words[:max_words]:
        lines.append(f"[{float(word['start']):.2f}-{float(word['end']):.2f}] {word['word']}")
    return "\n".join(lines)


def analyze_viral_segments(
    words: list[dict[str, float | str]],
    *,
    video_title: str | None = None,
    max_clips: int = 3,
) -> list[ClipSegment]:
    groq_key = os.getenv("GROQ_API_KEY") or getattr(settings, "groq_api_key", None)
    openai_key = getattr(settings, "openai_api_key", None) or os.getenv("OPENAI_API_KEY")

    client: OpenAI | None = None
    model_name: str = ""

    # 1. Prefer Groq API
    if groq_key and str(groq_key).strip():
        groq_model = (
            getattr(settings, "groq_analysis_model", None)
            or os.getenv("GROQ_ANALYSIS_MODEL")
            or "openai/gpt-oss-120b"
        )
        logger.info("Analyzing viral segments with Groq API (%s)...", groq_model)
        client = OpenAI(
            api_key=str(groq_key).strip(),
            base_url="https://api.groq.com/openai/v1",
        )
        model_name = groq_model

    # 2. Fall back to OpenAI
    elif openai_key and str(openai_key).strip():
        logger.info("Analyzing viral segments with OpenAI (%s)...", settings.openai_analysis_model)
        client = OpenAI(api_key=str(openai_key).strip())
        model_name = settings.openai_analysis_model

    # 3. No keys -> raise RuntimeError to trigger local fallback in pipeline.py
    else:
        raise RuntimeError("No LLM API key set (GROQ_API_KEY / OPENAI_API_KEY missing)")

    transcript = _format_transcript_for_llm(words)
    user_prompt = f"Video title: {video_title or 'Unknown'}\n\nTranscript:\n{transcript}"

    try:
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content or "{}"
    except Exception as exc:
        logger.error("LLM Analysis API request failed: %s", exc)
        raise RuntimeError(f"LLM Analysis failure: {exc}") from exc

    payload = json.loads(content)
    raw_clips = payload.get("clips", [])

    segments: list[ClipSegment] = []
    for item in raw_clips[:max_clips]:
        start = float(item["start_time"])
        end = float(item["end_time"])
        duration = end - start
        if duration < 25 or duration > 65:
            continue
        segments.append(
            ClipSegment(
                start_time=start,
                end_time=end,
                virality_score=int(item.get("virality_score", 5)),
                clip_title=str(item.get("clip_title", "Untitled Clip")),
                hook_reason=str(item.get("hook_reason", "")),
            )
        )

    segments.sort(key=lambda s: s.virality_score, reverse=True)
    logger.info("LLM selected %d viral segments", len(segments))
    return segments


def fallback_segments(
    words: list[dict[str, float | str]],
    *,
    video_duration: float | None = None,
) -> list[ClipSegment]:
    """Deterministic fallback when LLM is unavailable (dev/demo mode)."""
    if not words:
        end = min(video_duration or 45.0, 45.0)
        return [
            ClipSegment(
                start_time=0.0,
                end_time=max(end, 30.0),
                virality_score=5,
                clip_title="Opening Highlight",
                hook_reason="Fallback segment (no transcript available).",
            )
        ]

    start = float(words[0]["start"])
    last_end = float(words[-1]["end"])
    end = min(start + 45.0, last_end)
    if end - start < 30.0:
        end = min(start + 30.0, last_end)

    snippet = " ".join(str(w["word"]) for w in words[:12])
    return [
        ClipSegment(
            start_time=start,
            end_time=end,
            virality_score=6,
            clip_title="Auto-selected Highlight",
            hook_reason=f"Fallback segment from transcript: {snippet[:120]}...",
        )
    ]