"""FFmpeg helpers for vertical clip rendering and subtitle burn-in."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    """Raised when an FFmpeg command fails."""


def _ensure_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FFmpegError(
            "FFmpeg is not installed or not on PATH. "
            "Install from https://ffmpeg.org/download.html and restart the server."
        )
    return ffmpeg


def _run_ffmpeg(args: list[str], *, timeout: int | None = None) -> None:
    ffmpeg = _ensure_ffmpeg()
    command = [ffmpeg, *args]
    logger.info("Running FFmpeg: %s", " ".join(command))

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout or settings.ffmpeg_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"FFmpeg timed out after {timeout or settings.ffmpeg_timeout_seconds}s") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise FFmpegError(stderr or "FFmpeg command failed with no stderr output")


def format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp H:MM:SS.cc"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds == 100:
        secs += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def generate_ass_subtitles(
    words: list[dict[str, float | str]],
    output_path: Path,
    *,
    clip_start: float,
    clip_end: float,
    render_mode: str = "crop",
    play_res_x: int = 1080,
    play_res_y: int = 1920,
) -> Path:
    """
    Build an ASS subtitle file using native Karaoke (\\kf) tags.
    Emits exactly ONE Dialogue event per phrase to prevent text repetition and stacking.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    clip_words = [
        w for w in words
        if float(w["end"]) > clip_start and float(w["start"]) < clip_end
    ]

    alignment = 2
    margin_v = 180

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,52,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,{alignment},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []

    if not clip_words:
        events.append("Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,")
    else:
        # Group words into 3 words per line phrase
        chunk_size = 3
        for i in range(0, len(clip_words), chunk_size):
            chunk = clip_words[i : i + chunk_size]

            c_start = max(float(chunk[0]["start"]), clip_start) - clip_start
            c_end = min(float(chunk[-1]["end"]), clip_end) - clip_start
            if c_end <= c_start:
                c_end = c_start + 0.5

            karaoke_tokens = []
            curr_pos = c_start

            for w in chunk:
                w_start = max(float(w["start"]), clip_start) - clip_start
                w_end = min(float(w["end"]), clip_end) - clip_start

                gap = w_start - curr_pos
                if gap > 0:
                    gap_cs = int(round(gap * 100))
                    if gap_cs > 0:
                        karaoke_tokens.append(f"{{\\k{gap_cs}}}")

                w_dur = max(w_end - w_start, 0.1)
                dur_cs = max(1, int(round(w_dur * 100)))

                text = str(w["word"]).strip()
                if text:
                    # \kf sweeps SecondaryColour (&H0000FFFF - Cyan/Yellow) over word text
                    karaoke_tokens.append(f"{{\\kf{dur_cs}}}{text}")

                curr_pos = w_end

            line = " ".join(karaoke_tokens)
            events.append(
                f"Dialogue: 0,{format_ass_time(c_start)},{format_ass_time(c_end)},"
                f"Default,,0,0,0,,{line}"
            )

    output_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return output_path


def cut_and_crop_vertical(
    input_path: Path,
    output_path: Path,
    *,
    start_time: float,
    end_time: float,
    render_mode: str = "crop",
    ass_path: Path | None = None,
) -> Path:
    """
    Cut segment and construct layout filter:
    - 'crop': Full 9:16 vertical zoom fill (No black space)
    - 'fit' : 16:9 video centered with top/bottom black padding
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(end_time - start_time, 0.5)
    mode = (render_mode or "crop").lower().strip()

    # Windows-safe path escaping for ASS subtitle filter
    ass_filter_str = ""
    if ass_path is not None:
        ass_escaped = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
        ass_filter_str = f"ass='{ass_escaped}'"

    # Linear filter chains for crop and fit
    vf_parts: list[str] = []

    if mode == "fit":
        # FIT (BLACK BARS): Centered 16:9 frame on 1080x1920 black canvas
        vf_parts = [
            "scale=1080:-1:flags=lanczos",
            "pad=1080:1920:0:(1920-ih)/2:black",
            "unsharp=5:5:1.0:5:5:0.0",
        ]
    else:
        # FULL 9:16 CROP: Scale height to 1920, center-crop width to 1080. ZERO black space.
        vf_parts = [
            "scale=-1:1920:flags=lanczos",
            "crop=1080:1920:(iw-1080)/2:0",
            "unsharp=5:5:1.0:5:5:0.0",
        ]

    if ass_filter_str:
        vf_parts.append(ass_filter_str)

    filter_args = ["-vf", ",".join(vf_parts)]

    args = [
        "-y",
        "-ss", str(start_time),
        "-i", str(input_path),
        "-t", str(duration),
        *filter_args,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-b:v", "8M",
        "-maxrate", "10M",
        "-bufsize", "12M",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    _run_ffmpeg(args)
    return output_path


def render_vertical_clip(
    input_path: Path,
    output_path: Path,
    *,
    start_time: float,
    end_time: float,
    render_mode: str = "crop",
    words: list[dict[str, float | str]] | None = None,
    subtitle_enabled: bool = True,
) -> Path:
    """High-level helper: generate ASS subtitles and render the clip.

    When ``subtitle_enabled`` is False, the clip is rendered without any
    burned-in captions, even if transcript ``words`` are available.
    """
    ass_path: Path | None = None
    if words and subtitle_enabled:
        ass_path = output_path.with_suffix(".ass")
        generate_ass_subtitles(
            words,
            ass_path,
            clip_start=start_time,
            clip_end=end_time,
            render_mode=render_mode,
        )

    return cut_and_crop_vertical(
        input_path,
        output_path,
        start_time=start_time,
        end_time=end_time,
        render_mode=render_mode,
        ass_path=ass_path,
    )