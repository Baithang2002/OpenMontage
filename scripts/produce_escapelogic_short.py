"""
produce_escapelogic_short.py
============================
Master Autonomous Production & Cloud Publishing Engine for EscapeLogic YouTube Shorts.
Can run locally or 100% headless on GitHub Actions (even when user's PC is turned off).

Workflow:
1. Picks the next survival science scenario from config/escapelogic_scenarios.json
   (filters against config/published_escapelogic.json).
2. Synthesizes dramatic voiceover via Deepgram Aura (deep documentary narrator).
3. Transcribes word-level timestamps using Faster-Whisper (with graceful fallback).
4. Generates word-level kinetic karaoke subtitles & EscapeLogic emerald branding header.
5. Acquires or generates 9:16 vertical visual sequence with 4:5 Ghost Blur.
6. Encodes master video with emerald progress bar and ducked suspense BGM.
7. Uploads directly to YouTube Shorts via YouTube Data API v3 (Category: 28 Science & Tech).
8. Supports cloud-scheduled release (publishAt: 14:00 UTC / 7:30 PM IST).
9. Records published episode history to config/published_escapelogic.json.
"""

import os
import sys
import json
import time
import argparse
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from lib.escapelogic_engine import (
    video_codec_args,
    build_escapelogic_header_ass,
    build_ass_karaoke_subtitles,
    ghost_blur_filter,
    extract_high_ctr_thumbnail,
)
from tools.publishers.youtube_uploader import YouTubeUploader

SCENARIOS_FILE = ROOT_DIR / "config" / "escapelogic_scenarios.json"
PUBLISHED_FILE = ROOT_DIR / "config" / "published_escapelogic.json"


def load_scenarios() -> List[Dict[str, Any]]:
    if not SCENARIOS_FILE.exists():
        raise FileNotFoundError(f"Missing scenarios catalog: {SCENARIOS_FILE}")
    with open(SCENARIOS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("scenarios", [])


def load_published() -> List[Dict[str, Any]]:
    if not PUBLISHED_FILE.exists():
        return []
    try:
        with open(PUBLISHED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_published(published: List[Dict[str, Any]]):
    PUBLISHED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PUBLISHED_FILE, "w", encoding="utf-8") as f:
        json.dump(published, f, indent=2)


def get_next_scenario(override_id: Optional[str] = None) -> Dict[str, Any]:
    scenarios = load_scenarios()
    published = load_published()
    published_ids = {p.get("id") for p in published}

    if override_id:
        for sc in scenarios:
            if sc.get("id") == override_id or override_id.lower() in sc.get("topic", "").lower():
                return sc
        raise ValueError(f"Scenario override '{override_id}' not found in catalog.")

    for sc in scenarios:
        if sc.get("id") not in published_ids and sc.get("status") != "published":
            return sc

    print("[WARN] All catalog scenarios have been published! Cycling to first non-elevator scenario.")
    for sc in scenarios:
        if sc.get("id") != "elevator_freefall":
            return sc
    return scenarios[0]


def synthesize_voiceover(text: str, output_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY")

    if deepgram_key:
        print("🎙️ Synthesizing Voiceover with Deepgram Aura (Aura-2 Arcas, Deep Documentary)...")
        url = "https://api.deepgram.com/v1/speak?model=aura-2-arcas-en"
        headers = {
            "Authorization": f"Token {deepgram_key}",
            "Content-Type": "application/json"
        }
        try:
            res = requests.post(url, json={"text": text}, headers=headers, timeout=25)
            if res.status_code == 200 and len(res.content) > 1000:
                output_path.write_bytes(res.content)
                print(f"✅ Deepgram Voiceover saved to {output_path.name} ({len(res.content):,} bytes)")
                return True
            else:
                print(f"[WARN] Deepgram status {res.status_code}: {res.text[:100]}")
        except Exception as e:
            print(f"[WARN] Deepgram synthesis failed: {e}")

    # Fallback: ElevenLabs
    eleven_key = os.environ.get("ELEVENLABS_API_KEY")
    if eleven_key:
        print("🎙️ Fallback: ElevenLabs...")
        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": eleven_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.55, "similarity_boost": 0.85}
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=25)
            if res.status_code == 200 and len(res.content) > 1000:
                output_path.write_bytes(res.content)
                print(f"✅ ElevenLabs Voiceover saved to {output_path.name}")
                return True
        except Exception as e:
            print(f"[WARN] ElevenLabs synthesis failed: {e}")

    return False


def get_audio_duration(file_path: Path) -> float:
    res = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", str(file_path)
    ], capture_output=True, text=True, check=True)
    return float(json.loads(res.stdout)["format"]["duration"])


def transcribe_and_build_subtitles(
    audio_path: Path,
    output_ass_path: Path,
    title_hook: str,
    raw_text: str
) -> Path:
    """Uses Faster-Whisper to extract word-level timestamps, or falls back to text pacing."""
    print("📝 Transcribing Voiceover for Kinetic Karaoke Subtitles...")
    segments_data = []

    try:
        from faster_whisper import WhisperModel
        # Use tiny.en on CPU for universal cross-platform alignment (Ubuntu Actions / Windows)
        model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        segments_gen, _ = model.transcribe(str(audio_path), word_timestamps=True)
        for seg in segments_gen:
            words = []
            if seg.words:
                for w in seg.words:
                    words.append({
                        "word": w.word.strip(),
                        "start": w.start,
                        "end": w.end
                    })
            segments_data.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words": words
            })
        print(f"✅ Transcribed {len(segments_data)} subtitle segments via Faster-Whisper.")
    except Exception as e:
        print(f"[WARN] Faster-Whisper failed ({e}). Using mathematical word timing fallback...")
        total_dur = get_audio_duration(audio_path)
        words_raw = raw_text.split()
        if words_raw:
            per_word = total_dur / len(words_raw)
            cur = 0.0
            words = []
            for w in words_raw:
                words.append({
                    "word": w,
                    "start": cur,
                    "end": cur + per_word
                })
                cur += per_word
            segments_data.append({
                "start": 0.0,
                "end": total_dur,
                "text": raw_text,
                "words": words
            })

    return build_ass_karaoke_subtitles(segments_data, output_ass_path, title_hook=title_hook)


def generate_motion_graphic_background(duration: float, output_path: Path) -> Path:
    """Generates a high-tension animated dark sci-fi background in 1080x1920."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Generates a subtle dark slate pulsing background with grid pattern
    filter_graph = (
        f"color=c=0x0a0e14:s=1080x1920:d={duration:.2f},"
        "drawgrid=w=120:h=120:t=2:c=0x15202b@0.35,"
        "eq=contrast=1.15:saturation=1.10"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", filter_graph,
        "-t", f"{duration:.2f}",
        *video_codec_args(),
        str(output_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path


def source_or_create_visuals(scenario: Dict[str, Any], duration: float, work_dir: Path) -> Path:
    """
    Acquires action B-roll or generates clean dynamic visuals.
    Attempts Pexels API if key is present, otherwise builds sleek procedural visuals.
    """
    pexels_key = os.environ.get("PEXELS_API_KEY")
    broll_dir = work_dir / "broll"
    broll_dir.mkdir(parents=True, exist_ok=True)
    downloaded_clip = broll_dir / "pexels_clip.mp4"

    if pexels_key and scenario.get("visual_queries"):
        query = scenario["visual_queries"][0]
        try:
            print(f"🔍 Searching Pexels for B-roll: '{query}'...")
            res = requests.get(
                f"https://api.pexels.com/videos/search?query={query}&per_page=3&orientation=portrait",
                headers={"Authorization": pexels_key},
                timeout=12
            )
            if res.status_code == 200:
                videos = res.json().get("videos", [])
                if videos:
                    files = videos[0].get("video_files", [])
                    hd = [f for f in files if f.get("width", 0) >= 1080 or f.get("height", 0) >= 1080]
                    link = (hd[0] if hd else files[0]).get("link")
                    if link:
                        r = requests.get(link, stream=True, timeout=25)
                        with open(downloaded_clip, "wb") as f:
                            for chunk in r.iter_content(chunk_size=65536):
                                f.write(chunk)
                        if downloaded_clip.stat().st_size > 100000:
                            print(f"✅ Downloaded B-roll clip ({downloaded_clip.stat().st_size:,} bytes)")
                            return downloaded_clip
        except Exception as e:
            print(f"[WARN] Pexels search failed: {e}")

    # Procedural dynamic visual generation
    print("🎨 Generating procedural dark cinematic motion background...")
    proc_clip = broll_dir / "procedural_background.mp4"
    return generate_motion_graphic_background(duration, proc_clip)


def calculate_next_optimal_publish_time() -> str:
    """
    Calculates the next optimal publish window for 2x/day cadence:
    Slot 1: 09:00 UTC (2:30 PM IST / 10:00 AM CET / 4:00 AM EST)
    Slot 2: 15:00 UTC (8:30 PM IST / 4:00 PM CET / 10:00 AM EST)
    """
    now = datetime.now(timezone.utc)
    slot1_today = now.replace(hour=9, minute=0, second=0, microsecond=0)
    slot2_today = now.replace(hour=15, minute=0, second=0, microsecond=0)

    # Allow at least 30 minutes processing buffer before the target release
    if now < slot1_today - timedelta(minutes=30):
        target = slot1_today
    elif now < slot2_today - timedelta(minutes=30):
        target = slot2_today
    else:
        target = slot1_today + timedelta(days=1)

    return target.strftime("%Y-%m-%dT%H:%M:%SZ")


def produce_episode(
    scenario_id: Optional[str] = None,
    upload: bool = False,
    schedule: bool = True,
    privacy: str = "private"
) -> Dict[str, Any]:
    scenario = get_next_scenario(scenario_id)
    slug = scenario["id"]
    print(f"\n=======================================================")
    print(f"🎬 PRODUCING ESCAPELOGIC EPISODE: [{scenario.get('topic')}]")
    print(f"   Hook: {scenario.get('title_hook')}")
    print(f"   Slug: {slug}")
    print(f"=======================================================\n")

    work_dir = ROOT_DIR / "build" / f"escapelogic_{slug}"
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Voiceover
    vo_path = work_dir / "narration.mp3"
    if not vo_path.exists() or vo_path.stat().st_size < 1000:
        success = synthesize_voiceover(scenario["narration_full"], vo_path)
        if not success:
            raise RuntimeError("Failed to synthesize voiceover.")

    vo_duration = get_audio_duration(vo_path)
    total_duration = vo_duration + 0.6  # breathing room
    print(f"⏱️ Voiceover Duration: {vo_duration:.2f}s (Total master duration: {total_duration:.2f}s)")

    # 2. Subtitles
    ass_path = work_dir / "subtitles.ass"
    transcribe_and_build_subtitles(
        audio_path=vo_path,
        output_ass_path=ass_path,
        title_hook=scenario.get("title_hook", "ESCAPELOGIC"),
        raw_text=scenario["narration_full"]
    )

    # 3. Visuals
    raw_visual = source_or_create_visuals(scenario, total_duration, work_dir)

    # 4. Master Composite Render
    final_output = work_dir / "escapelogic_short.mp4"
    print(f"⚡ Rendering Master Composite Short with Emerald Progress Bar & Ghost Blur...")

    filter_complex = ghost_blur_filter(
        ass_file=str(ass_path),
        hflip=True,
        progress_bar=True,
        duration=total_duration
    )

    # Mix narration with subtle ambient tone
    cmd_render = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(raw_visual),
        "-i", str(vo_path),
        "-f", "lavfi", "-i", f"anoisesrc=c=pink:r=48000:a=0.015,lowpass=f=400,volume=0.08",
        "-filter_complex",
        f"{filter_complex};[1:a]volume=1.0[vo];[2:a]volume=0.08[amb];[vo][amb]amix=inputs=2:duration=first[aout]",
        "-map", "[v]",
        "-map", "[aout]",
        "-t", f"{total_duration:.2f}",
        *video_codec_args(),
        "-c:a", "aac", "-b:a", "192k",
        str(final_output)
    ]
    subprocess.run(cmd_render, check=True)
    print(f"🎉 Master Short successfully rendered: {final_output.name} ({final_output.stat().st_size:,} bytes)")

    # 5. Extract Thumbnail
    thumb_path = work_dir / "thumbnail.jpg"
    extract_high_ctr_thumbnail(final_output, thumb_path, timestamp_s=min(2.5, total_duration / 2))
    print(f"🖼️ High-CTR Thumbnail generated: {thumb_path.name}")

    # 6. YouTube Upload
    upload_result = None
    if upload:
        print("\n🚀 Uploading directly to YouTube Shorts via YouTube Data API v3...")
        uploader = YouTubeUploader()
        publish_time = calculate_next_optimal_publish_time() if schedule else None

        params = {
            "video_path": str(final_output),
            "thumbnail_path": str(thumb_path),
            "title": scenario["yt_title"][:100],
            "description": scenario["description"],
            "tags": scenario.get("tags", ["EscapeLogic", "shorts", "physics", "survival"]),
            "category_id": "28",  # Science & Technology
            "privacy_status": "private" if schedule else privacy,
        }
        if schedule and publish_time:
            params["publish_at"] = publish_time
            print(f"📅 Cloud Scheduled Publication configured for: {publish_time}")

        res = uploader.execute(params)
        if res.success:
            upload_result = res.data
            print(f"✅ Video Uploaded! Direct URL: {upload_result.get('video_url')}")

            # Record in published history
            published = load_published()
            published.append({
                "id": slug,
                "episode_num": scenario.get("episode_num", len(published) + 1),
                "title": scenario["yt_title"],
                "video_id": upload_result.get("video_id"),
                "video_url": upload_result.get("video_url"),
                "status": "scheduled" if schedule else "published",
                "published_at": publish_time or datetime.now(timezone.utc).isoformat(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            save_published(published)

            # Update scenario status in catalog
            scenarios = load_scenarios()
            for sc in scenarios:
                if sc.get("id") == slug:
                    sc["status"] = "published"
                    sc["youtube_video_id"] = upload_result.get("video_id")
                    sc["youtube_video_url"] = upload_result.get("video_url")
            with open(SCENARIOS_FILE, "w", encoding="utf-8") as f:
                json.dump({"version": "1.0", "channel": "EscapeLogic", "tagline": "Survival by Physics", "scenarios": scenarios}, f, indent=2)
        else:
            print(f"❌ YouTube upload failed: {res.error}")

    return {
        "scenario": scenario,
        "video_path": str(final_output),
        "thumbnail_path": str(thumb_path),
        "duration": total_duration,
        "upload_result": upload_result
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EscapeLogic Master Autonomous Engine")
    parser.add_argument("--scenario", type=str, help="Specific scenario slug to produce")
    parser.add_argument("--upload", action="store_true", help="Upload to YouTube Shorts")
    parser.add_argument("--schedule", action="store_true", default=True, help="Schedule release at optimal viewing time")
    parser.add_argument("--privacy", type=str, default="private", choices=["public", "private", "unlisted"])
    parser.add_argument("--dry-run", action="store_true", help="Render video without uploading")

    args = parser.parse_args()
    do_upload = args.upload and not args.dry_run

    produce_episode(
        scenario_id=args.scenario,
        upload=do_upload,
        schedule=args.schedule,
        privacy=args.privacy
    )
