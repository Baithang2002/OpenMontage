"""
escapelogic_engine.py
=====================
Core production engine and FFmpeg filter utilities for EscapeLogic YouTube Shorts:
- 4:5 Ghost Blur Framing (1080x1920) with high-contrast cinematic color grading
- Top Emerald/Titanium EscapeLogic Branding Header
- Word-Level Kinetic Karaoke Subtitles in YouTube Shorts Safe Zone (MarginV=440)
- Animated Top Progress Bar (Emerald #00FF88)
- High-CTR mobile thumbnail extractor
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent

_NVENC_OK = None

def _nvenc_works() -> bool:
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=0.5",
             "-c:v", "h264_nvenc", "-preset", "p4", "-f", "mp4", "NUL" if os.name == "nt" else "/dev/null"],
            capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False

def video_codec_args() -> List[str]:
    """Universal high-performance encoding using NVENC if available, falling back to libx264."""
    global _NVENC_OK
    if _NVENC_OK is None:
        if _nvenc_works():
            _NVENC_OK = "nvenc"
        else:
            _NVENC_OK = "x264"
    if _NVENC_OK == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "19", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p"]


def build_escapelogic_header_ass(
    title_hook: str,
    output_ass_path: Path,
    duration: float = 60.0
) -> Path:
    """
    Builds the top header banner ASS overlay:
    - TopBrand: ESCAPELOGIC in clean titanium white
    - TopTitle: Specific hook title in emerald neon (&H0088FF00)
    """
    output_ass_path.parent.mkdir(parents=True, exist_ok=True)
    # Format times
    m, s = divmod(int(duration), 60)
    end_time_str = f"0:{m:02d}:{s:02d}.00"

    ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TopBrand,Impact,32,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,2,2,8,40,40,120,1
Style: TopTitle,Impact,46,&H0088FF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,3,2,8,40,40,175,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 1,0:00:00.00,{end_time_str},TopBrand,,0,0,0,,{{\\fad(200,200)}}ESCAPELOGIC
Dialogue: 1,0:00:00.00,{end_time_str},TopTitle,,0,0,0,,{{\\fad(200,200)}}{title_hook.upper()}
"""
    output_ass_path.write_text(ass, encoding="utf-8")
    return output_ass_path


def build_ass_karaoke_subtitles(
    segments: List[Dict[str, Any]],
    output_ass_path: Path,
    title_hook: Optional[str] = None
) -> Path:
    """
    Builds word-level kinetic karaoke subtitles (.ass) for YouTube Shorts:
    - Primary active highlight: Emerald Green (&H0088FF00) or Yellow (&H0000FFFF)
    - Inactive / Base text: Pure White (&H00FFFFFF)
    - Strong black outline (4px) + soft shadow (2px)
    - Safe Zone Alignment: Center bottom at MarginV=440
    """
    output_ass_path.parent.mkdir(parents=True, exist_ok=True)
    
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KaraokeWord,Impact,52,&H00FFFFFF,&H0088FF00,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,4,2,2,40,40,440,1
Style: TopBrand,Impact,32,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,2,2,8,40,40,120,1
Style: TopTitle,Impact,46,&H0088FF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,3,2,8,40,40,175,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    
    # If title hook provided, keep it pinned at the top
    if title_hook:
        max_t = 0.0
        for seg in segments:
            max_t = max(max_t, seg.get("end", 0.0))
        m, s = divmod(int(max_t + 2), 60)
        end_time_str = f"0:{m:02d}:{s:02d}.00"
        events.append(f"Dialogue: 1,0:00:00.00,{end_time_str},TopBrand,,0,0,0,,{{\\fad(200,200)}}ESCAPELOGIC")
        events.append(f"Dialogue: 1,0:00:00.00,{end_time_str},TopTitle,,0,0,0,,{{\\fad(200,200)}}{title_hook.upper()}")

    def format_ts(sec: float) -> str:
        hours = int(sec // 3600)
        minutes = int((sec % 3600) // 60)
        seconds = sec % 60
        return f"{hours}:{minutes:02d}:{seconds:05.2f}"

    for seg in segments:
        words = seg.get("words", [])
        if not words:
            # Fallback for plain sentence segment
            start_str = format_ts(seg["start"])
            end_str = format_ts(seg["end"])
            text = seg["text"].strip().upper()
            events.append(f"Dialogue: 2,{start_str},{end_str},KaraokeWord,,0,0,0,,{text}")
            continue

        # Group words into short punchy 3-5 word lines
        chunk_size = 4
        for i in range(0, len(words), chunk_size):
            chunk = words[i:i + chunk_size]
            line_start = chunk[0]["start"]
            line_end = chunk[-1]["end"]
            start_str = format_ts(line_start)
            end_str = format_ts(line_end)

            # Generate ASS \k karaoke tags (duration in centiseconds)
            karaoke_text = ""
            for w in chunk:
                dur_cs = max(1, int((w["end"] - w["start"]) * 100))
                clean_w = w["word"].strip().upper()
                karaoke_text += f"{{\\k{dur_cs}}}{clean_w} "

            events.append(f"Dialogue: 2,{start_str},{end_str},KaraokeWord,,0,0,0,,{karaoke_text.strip()}")

    full_ass = header + "\n".join(events) + "\n"
    output_ass_path.write_text(full_ass, encoding="utf-8")
    return output_ass_path


def ghost_blur_filter(
    ass_file: Optional[str] = None,
    hflip: bool = True,
    progress_bar: bool = True,
    duration: float = 60.0
) -> str:
    """
    Standard OpenMontage 4:5 Ghost Blur Filtergraph with OLED color boost:
    - [bg]: 1080x1920 background, boxblurred + hflipped
    - [fg]: 1080x1350 centered 4:5 sharp foreground with subtle OLED vibrance
    - [pbar]: Emerald green #00FF88 kinetic animated progress bar along the top
    - [sub]: Word-level subtitles burned via libass
    """
    flip_filter = ",hflip" if hflip else ""
    ass_filter = ""
    if ass_file:
        escaped_ass = str(Path(ass_file).resolve()).replace("\\", "/").replace(":", "\\:")
        ass_filter = f",subtitles='{escaped_ass}'"

    fg_pipeline = (
        "[0:v]scale=1080:1350:force_original_aspect_ratio=increase,"
        "crop=1080:1350,"
        "eq=contrast=1.06:saturation=1.18:brightness=-0.01[fg]"
    )
    bg_pipeline = (
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920{flip_filter},"
        f"boxblur=luma_radius=35:luma_power=3,"
        f"eq=brightness=-0.14:saturation=1.20[bg]"
    )
    blend_pipeline = "[bg][fg]overlay=0:285[v_comp]"

    if progress_bar and duration > 0:
        bar_pipeline = (
            f"color=c=black@0.45:s=1080x14:d={duration:.2f}[pbg];"
            f"[v_comp][pbg]overlay=0:0[v_bar_bg];"
            f"color=c=0x00FF88:s=1080x14:d={duration:.2f}[pbar];"
            f"[v_bar_bg][pbar]overlay=x='min(0,-1080+1080*(t/{duration:.2f}))':y=0{ass_filter}[v]"
        )
        return f"{fg_pipeline};{bg_pipeline};{blend_pipeline};{bar_pipeline}"
    else:
        return f"{fg_pipeline};{bg_pipeline};{blend_pipeline};[v_comp]copy{ass_filter}[v]"


def extract_high_ctr_thumbnail(
    video_path: Path,
    output_thumb_path: Path,
    timestamp_s: float = 2.0
) -> Path:
    """
    Extracts a high-impact 1080x1920 JPEG thumbnail:
    - High contrast (+10%) & saturation boost (+25%)
    - Unsharp mask filter for razor-sharp display on mobile Shorts feeds
    """
    output_thumb_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp_s),
        "-i", str(video_path),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.10:saturation=1.25,unsharp=5:5:0.8:5:5:0.0",
        "-vframes", "1",
        "-q:v", "2",
        str(output_thumb_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_thumb_path
