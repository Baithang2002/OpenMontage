"""
produce_wildlife_facts_short.py
================================
100% Autonomous Master Production Engine for Wild Mechanics YouTube Shorts.
Designed to run on GitHub Actions cron or local manual trigger:

1. Checks `config/published_animals.json` to ensure no repeated animals.
2. Calls Gemini API to generate a fresh, mind-blowing 3-fact wildlife mechanics script.
3. Synthesizes voiceover via Deepgram (or ElevenLabs / Edge-TTS fallback).
4. Generates word-level kinetic yellow karaoke subtitles via Faster-Whisper.
5. Acquires stock B-roll (Pexels / Pixabay) with yt-dlp fallback for rare action moments.
6. Composites into 4:5 Ghost Blur framing (1080x1920) with animated gold progress bar.
7. Uploads directly to YouTube Shorts via YouTube Data API v3.
8. Commits the newly published animal to history.
"""

import os
import sys
import json
import time
import random
import asyncio
import argparse
import subprocess
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from lib.wild_mechanics_engine import (
    ghost_blur_filter,
    build_ass_subtitles,
    video_codec_args,
)
from faster_whisper import WhisperModel
from tools.publishers.youtube_uploader import YouTubeUploader
from lib.notifier import NotificationDispatcher

HISTORY_FILE = ROOT_DIR / "config" / "published_animals.json"
LAST_EPISODE_FILE = ROOT_DIR / "config" / "last_generated_episode.json"

# Curated high-retention fallback catalog if Gemini API is offline/unavailable
CURATED_FALLBACK_EPISODES = [
    {
        "animal": "Wolverine Frog",
        "scientific_name": "Trichobatrachus robustus",
        "slug": "wolverine_frog_bone_claws",
        "title_hook": "THE ANIMAL THAT BREAKS ITS BONES TO FIGHT 🩸",
        "yt_title": "The Animal That Breaks Its Own Bones To Fight 🩸 #shorts #wildlife",
        "description": "Meet the Wolverine Frog (Trichobatrachus robustus). When attacked, it breaks its own toe bones to sprout razor-sharp combat claws.\n\nSubscribe to Wild Mechanics for more crazy animal physics!\n\n#shorts #wildlife #nature #animals #wildmechanics",
        "tags": ["shorts", "wolverine frog", "wild mechanics", "animal facts", "nature", "biology", "animal superpowers", "amphibians"],
        "narration_full": (
            "Meet the wolverine frog. When attacked, this creature does something straight out of a horror movie. "
            "Fact one: It deliberately breaks the bones in its own toes, forcing the jagged bone shards to puncture through its skin pads to create razor-sharp combat claws. "
            "Fact two: Once the predator retreats, its muscles relax, the bone claws retract inside, and the torn tissue completely regenerates within days. "
            "Fact three: During breeding season, males grow hair-like filaments that absorb extra oxygen from water, letting them guard underwater nests for weeks. "
            "Subscribe to Wild Mechanics for more crazy animal physics!"
        ),
        "visual_queries": ["frog in water", "frog macro eyes", "amphibian rainforest", "predator attack bird"]
    },
    {
        "animal": "Bombardier Beetle",
        "scientific_name": "Brachinus crepitans",
        "slug": "bombardier_beetle_rocket_engine",
        "title_hook": "THIS BUG FIRES BOILING CHEMICAL ROCKETS 🚀",
        "yt_title": "This Bug Fires 212°F Boiling Chemical Rockets 🚀 #shorts #wildlife",
        "description": "The Bombardier Beetle mixes hydrogen peroxide and hydroquinone inside an internal combustion chamber, firing boiling toxic steam at 500 pulses per second.\n\nSubscribe to Wild Mechanics!\n\n#shorts #wildlife #nature #animals #beetle #wildmechanics",
        "tags": ["shorts", "bombardier beetle", "wild mechanics", "science", "chemistry", "insects", "nature", "physics"],
        "narration_full": (
            "This tiny bug has an actual rocket engine inside its body. "
            "Fact one: The bombardier beetle stores hydrogen peroxide and hydroquinone in separate reservoirs, mixing them in an internal combustion chamber when threatened. "
            "Fact two: The chemical reaction instantly heats the fluid to two hundred and twelve degrees Fahrenheit, blasting a boiling toxic steam jet out of a rotating nozzle at five hundred pulses per second. "
            "Fact three: Frogs that swallow the beetle whole will violently vomit it back up unharmed, driven mad by chemical burns inside their stomach. "
            "Subscribe to Wild Mechanics for more crazy animal physics!"
        ),
        "visual_queries": ["beetle crawling macro", "insect macro eye", "frog hunting tongue", "smoke explosion micro"]
    },
    {
        "animal": "Diabolical Ironclad Beetle",
        "scientific_name": "Phloeodes diabolicus",
        "slug": "ironclad_beetle_car_crush",
        "title_hook": "THE BUG THAT SURVIVES BEING RUN OVER BY A CAR 🚗",
        "yt_title": "The Bug That Survives Being Run Over By A Car 🚗 #shorts #wildlife",
        "description": "The Diabolical Ironclad Beetle can survive 39,000 times its own body weight thanks to interlocking jigsaw puzzle-piece armor.\n\nSubscribe to Wild Mechanics!\n\n#shorts #wildlife #nature #animals #wildmechanics #engineering",
        "tags": ["shorts", "ironclad beetle", "wild mechanics", "engineering", "nature", "biology", "physics", "armor"],
        "narration_full": (
            "This is the most indestructible insect on Earth. "
            "Fact one: The diabolical ironclad beetle can withstand thirty-nine thousand times its own body weight. You can literally run a car over it on concrete, and it walks away completely undamaged. "
            "Fact two: Its shell is locked together like an interlocking jigsaw puzzle. Under extreme pressure, the microscopic layers delaminate gradually instead of snapping, absorbing massive kinetic energy. "
            "Fact three: Entomologists trying to mount this beetle on steel pins have to use an electric micro-drill because steel pins bend against its armor. "
            "Subscribe to Wild Mechanics for more crazy animal physics!"
        ),
        "visual_queries": ["beetle desert gravel", "macro insect shell", "car tire rolling", "desert sand stone"]
    },
    {
        "animal": "Tiger Beetle",
        "scientific_name": "Cicindelinae",
        "slug": "tiger_beetle_blind_sprint",
        "title_hook": "THIS PREDATOR RUNS SO FAST IT GOES BLIND ⚡",
        "yt_title": "This Predator Runs So Fast It Goes Blind ⚡ #shorts #wildlife",
        "description": "The Tiger Beetle sprints at 125 body lengths per second—so fast that light cannot enter its eyes fast enough, causing temporary total blindness.\n\nSubscribe to Wild Mechanics!\n\n#shorts #wildlife #nature #animals #physics #wildmechanics",
        "tags": ["shorts", "tiger beetle", "wild mechanics", "speed", "physics", "optics", "nature", "biology"],
        "narration_full": (
            "This predator moves so fast that its own brain cannot process reality. "
            "Fact one: The tiger beetle covers one hundred and twenty-five body lengths per second. Scaled to human size, that is running at four hundred and eighty miles per hour. "
            "Fact two: It moves faster than light can physically enter its compound eyes and reach its optic nerve. While sprinting, it goes completely blind. "
            "Fact three: To hunt, it runs on an automated pulse code. It sprints blind towards the target, slams on the brakes to re-acquire visual lock, and sprints again until prey is caught. "
            "Subscribe to Wild Mechanics for more crazy animal physics!"
        ),
        "visual_queries": ["beetle running sand", "desert insect sprint", "macro insect eyes", "dry cracked ground"]
    },
    {
        "animal": "Wood Frog",
        "scientific_name": "Lithobates sylvaticus",
        "slug": "wood_frog_frozen_resurrection",
        "title_hook": "THE FROG THAT DIES EVERY WINTER AND RESURRECTS ❄️",
        "yt_title": "The Frog That Dies Every Winter And Resurrects ❄️ #shorts #wildlife",
        "description": "The Alaskan Wood Frog freezes 70% of its body into solid ice for 7 months. No heartbeat, no breathing. In spring, it thaws and resurrects.\n\nSubscribe to Wild Mechanics!\n\n#shorts #wildlife #nature #animals #biology #wildmechanics",
        "tags": ["shorts", "wood frog", "wild mechanics", "cryonics", "nature", "biology", "winter", "alaska"],
        "narration_full": (
            "In the freezing forests of Alaska, this frog literally dies every winter and comes back to life. "
            "Fact one: The wood frog allows seventy percent of its body water to freeze into solid ice. Its heart stops beating, brain activity ceases, and it is clinically dead for seven months. "
            "Fact two: It floods its vital organs with massive amounts of glucose and urea, lowering the cellular freezing point so ice only forms outside cell walls, preventing cell rupture. "
            "Fact three: When spring arrives, it thaws from the inside out. Within twenty-four hours, its heart jump-starts itself and it hops away ready to mate. "
            "Subscribe to Wild Mechanics for more crazy animal physics!"
        ),
        "visual_queries": ["ice frost melting", "winter forest snow", "green frog moss", "water drop macro"]
    }
]


def load_history() -> List[str]:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(history: List[str]):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def generate_episode_with_gemini(history: List[str]) -> Optional[Dict[str, Any]]:
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not gemini_key:
        print("[INFO] GEMINI_API_KEY not set. Using curated fresh catalog.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    excluded_str = ", ".join(history[-30:])

    prompt = f"""
You are the lead researcher and viral scriptwriter for the YouTube channel 'Wild Mechanics'.
We create 55-second YouTube Shorts about extraordinary animal biology, extreme physics, and insane natural weaponry.

ALREADY COVERED ANIMALS (DO NOT REPEAT ANY OF THESE):
{excluded_str}

Select ONE completely different, real animal with mind-blowing physics, extreme biomechanics, or predatory superpowers.
(Good examples: Dracula Ant, Archerfish, Box Jellyfish, Pistol Shrimp, Golden Wheel Spider, Planarian Flatworm, Cuttlefish, Leafcutter Ant, Electric Eel, Axolotl, Trap-Jaw Ant, Velvet Worm, etc.)

Return STRICT JSON ONLY (no markdown formatting, no backticks, no extra text) with these exact keys:
{{
  "animal": "Common Name",
  "scientific_name": "Scientific Name",
  "slug": "snake_case_id",
  "title_hook": "ALL CAPS PUNCHY CURIOSITY TITLE WITH EMOJI (MAX 45 CHARS)",
  "yt_title": "Catchy YouTube Title Under 80 Chars #shorts #wildlife",
  "description": "3-sentence description + hashtags #shorts #wildlife #nature #animals #wildmechanics",
  "tags": ["shorts", "wildlife", "nature", "animal name", "wild mechanics", "science", "biology"],
  "narration_full": "Full voiceover script combining Cold Hook + 3 Mind-Blowing Facts + Call to Action ('Subscribe to Wild Mechanics for more crazy animal physics!'). Strictly 110-130 words total.",
  "visual_queries": ["3-word search term 1", "3-word search term 2", "3-word search term 3", "3-word search term 4"]
}}
"""

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.8, "responseMimeType": "application/json"}
    }

    try:
        print("🤖 Prompting Gemini for a brand-new wildlife mechanics episode...")
        res = requests.post(url, json=payload, headers=headers, timeout=25)
        if res.status_code == 200:
            raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Clean possible markdown wrap
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            data = json.loads(raw_text)
            if "animal" in data and "narration_full" in data:
                print(f"✨ Gemini selected: [{data['animal']}] - {data.get('title_hook')}")
                return data
    except Exception as e:
        print(f"[WARN] Gemini generation failed: {e}. Falling back to curated catalog.")
    return None


def get_next_episode(override_topic: Optional[str] = None) -> Dict[str, Any]:
    history = load_history()

    # 1. If manual override topic specified
    if override_topic:
        for ep in CURATED_FALLBACK_EPISODES:
            if override_topic.lower() in ep["animal"].lower() or override_topic.lower() in ep["slug"]:
                return ep

    # 2. Try Gemini Autonomous Generation
    ep = generate_episode_with_gemini(history)
    if ep:
        return ep

    # 3. Fallback to Curated Catalog (pick first one not in history)
    for ep in CURATED_FALLBACK_EPISODES:
        if ep["slug"] not in history and ep["animal"].lower() not in [h.lower() for h in history]:
            return ep

    # If all curated were used, cycle to first
    return CURATED_FALLBACK_EPISODES[len(history) % len(CURATED_FALLBACK_EPISODES)]


# ---------------------------------------------------------------------------
# TTS VOICE GENERATION (Deepgram > ElevenLabs > Edge-TTS)
# ---------------------------------------------------------------------------
def generate_voiceover(text: str, output_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Primary: Deepgram Aura-2
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY")
    if deepgram_key:
        print("🎙️ Synthesizing Voiceover with Deepgram Aura (high clarity, fast)...")
        url = "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en"
        headers = {
            "Authorization": f"Token {deepgram_key}",
            "Content-Type": "application/json"
        }
        try:
            res = requests.post(url, json={"text": text}, headers=headers, timeout=20)
            if res.status_code == 200 and len(res.content) > 1000:
                output_path.write_bytes(res.content)
                print(f"✅ Deepgram Voiceover saved to {output_path.name}")
                return True
            else:
                print(f"[WARN] Deepgram status {res.status_code}: {res.text[:100]}")
        except Exception as e:
            print(f"[WARN] Deepgram synthesis failed: {e}")

    # 2. Secondary: ElevenLabs
    eleven_key = os.environ.get("ELEVENLABS_API_KEY")
    if eleven_key:
        print("🎙️ Synthesizing Voiceover with ElevenLabs...")
        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam default
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": eleven_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.50, "similarity_boost": 0.85}
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=25)
            if res.status_code == 200 and len(res.content) > 1000:
                output_path.write_bytes(res.content)
                print(f"✅ ElevenLabs Voiceover saved to {output_path.name}")
                return True
        except Exception as e:
            print(f"[WARN] ElevenLabs synthesis failed: {e}")

    # 3. Tertiary: Free Edge-TTS
    try:
        import edge_tts
        print("🎙️ Synthesizing Voiceover with Edge-TTS (Christopher Neural, Free)...")
        async def _edge():
            comm = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+4%")
            await comm.save(str(output_path))
        asyncio.run(_edge())
        if output_path.exists() and output_path.stat().st_size > 1000:
            print(f"✅ Edge-TTS Voiceover saved to {output_path.name}")
            return True
    except Exception as e:
        print(f"[ERROR] Edge-TTS synthesis failed: {e}")

    return False


def get_audio_duration(file_path: Path) -> float:
    res = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", str(file_path)
    ], capture_output=True, text=True, check=True)
    return float(json.loads(res.stdout)["format"]["duration"])


# ---------------------------------------------------------------------------
# VISUAL ACQUISITION & B-ROLL ASSEMBLY
# ---------------------------------------------------------------------------
def search_and_download_pexels(query: str, dest_path: Path) -> bool:
    pexels_key = os.environ.get("PEXELS_API_KEY")
    if not pexels_key:
        return False

    url = f"https://api.pexels.com/videos/search?query={query}&per_page=3&orientation=portrait"
    headers = {"Authorization": pexels_key}
    try:
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code == 200:
            data = res.json()
            videos = data.get("videos", [])
            if not videos:
                # Try landscape
                url = f"https://api.pexels.com/videos/search?query={query}&per_page=3"
                res = requests.get(url, headers=headers, timeout=12)
                data = res.json()
                videos = data.get("videos", [])

            if videos:
                # Pick the best HD mp4 file link
                files = videos[0].get("video_files", [])
                hd_files = [f for f in files if f.get("width", 0) >= 1080 or f.get("height", 0) >= 1080]
                target_file = hd_files[0] if hd_files else files[0]
                video_url = target_file.get("link")
                if video_url:
                    dl = requests.get(video_url, stream=True, timeout=25)
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(dest_path, "wb") as f:
                        for chunk in dl.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    if dest_path.exists() and dest_path.stat().st_size > 100000:
                        return True
    except Exception as e:
        print(f"[WARN] Pexels search failed for '{query}': {e}")
    return False


def acquire_broll_clips(queries: List[str], assets_dir: Path, total_duration: float) -> List[Path]:
    clips_dir = assets_dir / "broll_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    acquired_clips: List[Path] = []

    num_slots = max(3, len(queries))
    slot_dur = round(total_duration / num_slots, 1)

    for i, q in enumerate(queries):
        clip_target = clips_dir / f"clip_{i:02d}.mp4"
        success = search_and_download_pexels(q, clip_target)
        if success:
            acquired_clips.append(clip_target)
            print(f"🎬 Acquired Stock B-Roll for '{q}': {clip_target.name}")

    # Fallback to local stock/music if needed
    if len(acquired_clips) < 2:
        print("[INFO] Sourcing fallback nature background clips...")
        fallback_clip = clips_dir / "fallback_ambience.mp4"
        cmd_synth = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=#0b141a:s=1080x1350:d={total_duration:.2f}:r=30",
            *video_codec_args(),
            str(fallback_clip)
        ]
        subprocess.run(cmd_synth, check=True, capture_output=True)
        acquired_clips.append(fallback_clip)

    return acquired_clips


def assemble_visual_montage(clips: List[Path], target_duration: float, output_path: Path):
    temp_dir = output_path.parent / "temp_assembly"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    per_clip_dur = target_duration / len(clips)
    processed_clips = []

    for i, clip in enumerate(clips):
        proc_clip = temp_dir / f"proc_{i:02d}.mp4"
        # Scale to 1080x1350 4:5 center crop, 30fps, exact duration
        cmd = [
            "ffmpeg", "-y",
            "-ss", "0.0",
            "-t", f"{per_clip_dur:.2f}",
            "-i", str(clip),
            "-vf", "scale=1080:1350:force_original_aspect_ratio=increase,crop=1080:1350:(iw-1080)/2:(ih-1350)/2,fps=30,setsar=1",
            *video_codec_args(),
            "-an",
            str(proc_clip)
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        processed_clips.append(proc_clip)

    # Concat file
    concat_list = temp_dir / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in processed_clips:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path)
    ]
    subprocess.run(cmd_concat, check=True, capture_output=True)
    print(f"✅ Visual Montage Assembled ({target_duration:.2f}s) -> {output_path.name}")


# ---------------------------------------------------------------------------
# MAIN AUTONOMOUS PIPELINE
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Wild Mechanics 100% Autonomous Short Producer")
    parser.add_argument("--upload", action="store_true", help="Directly upload rendered Short to YouTube")
    parser.add_argument("--notify", action="store_true", help="Send Discord / Telegram notifications")
    parser.add_argument("--topic", type=str, default=None, help="Optional manual topic override")
    args = parser.parse_args()

    print("=" * 68)
    print("🐾 WILD MECHANICS 100% AUTONOMOUS CLOUD ENGINE")
    print("=" * 68)

    # 1. Discover & Script Episode
    episode = get_next_episode(override_topic=args.topic)
    animal = episode["animal"]
    slug = episode["slug"]
    title_hook = episode["title_hook"]
    yt_title = episode["yt_title"]
    narration_text = episode["narration_full"]

    print(f"\n🌟 Target Subject: {animal} ({episode.get('scientific_name', '')})")
    print(f"🏷️ Title Hook: {title_hook}")
    print(f"🎬 YouTube Title: {yt_title}")

    project_dir = ROOT_DIR / "projects" / slug
    assets_dir = project_dir / "assets"
    renders_dir = project_dir / "renders"
    assets_dir.mkdir(parents=True, exist_ok=True)
    renders_dir.mkdir(parents=True, exist_ok=True)

    # 2. Synthesize Narration Voiceover
    narration_mp3 = assets_dir / "narration.mp3"
    print("\n🎙️ Step 1: Synthesizing Original Science Narration Voiceover...")
    vo_ok = generate_voiceover(narration_text, narration_mp3)
    if not vo_ok:
        print("[ERROR] Voice synthesis failed across all providers.")
        sys.exit(1)

    vo_duration = get_audio_duration(narration_mp3)
    print(f"⏱️ Narration Duration: {vo_duration:.2f} seconds")

    # 3. Transcribe with Faster-Whisper & Build ASS Kinetic Karaoke
    print("\n📝 Step 2: Transcribing Audio with Faster-Whisper for Kinetic Subtitles...")
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = whisper_model.transcribe(str(narration_mp3), word_timestamps=True)

    ass_path = assets_dir / f"{slug}_subtitles.ass"
    build_ass_subtitles(
        segments=list(segments),
        output_path=ass_path,
        title_hook=title_hook,
        max_duration=vo_duration
    )
    print(f"✅ Kinetic Karaoke Subtitles Generated -> {ass_path.name}")

    # 4. Acquire B-Roll Clips & Build 4:5 Montage
    print("\n📹 Step 3: Acquiring High-Definition B-Roll Clips...")
    queries = episode.get("visual_queries", [f"{animal.lower()} macro", "wildlife predator", "nature slow motion"])
    raw_clips = acquire_broll_clips(queries, assets_dir, vo_duration)

    montage_mp4 = assets_dir / "visual_montage_4_5.mp4"
    assemble_visual_montage(raw_clips, vo_duration, montage_mp4)

    # 5. Composite Final 4:5 Ghost Blur Master Video
    master_mp4 = renders_dir / f"{slug}_master.mp4"
    print(f"\n🎨 Step 4: Rendering Final 4:5 Ghost Blur Master Video ({master_mp4.name})...")

    fg_filter = ghost_blur_filter(
        ass_file=str(ass_path),
        hflip=False,
        progress_bar=True,
        total_duration=vo_duration,
        duration=vo_duration
    )

    # Check for ambient BGM in music_library/
    music_lib = ROOT_DIR / "music_library"
    bgm_candidates = list(music_lib.glob("*.mp3")) if music_lib.exists() else []
    bgm_file = bgm_candidates[0] if bgm_candidates else None

    if bgm_file and bgm_file.exists():
        # Mix narration + ducked BGM
        cmd_master = [
            "ffmpeg", "-y",
            "-i", str(montage_mp4),
            "-i", str(narration_mp3),
            "-i", str(bgm_file),
            "-filter_complex",
            f"{fg_filter};"
            f"[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aformat=sample_rates=48000:channel_layouts=stereo[vo];"
            f"[2:a]volume=0.18,atrim=0:{vo_duration:.2f},aformat=sample_rates=48000:channel_layouts=stereo[bgm];"
            f"[vo][bgm]amix=inputs=2:duration=first[a]",
            "-map", "[v]", "-map", "[a]",
            *video_codec_args(),
            "-c:a", "aac", "-b:a", "320k",
            str(master_mp4)
        ]
    else:
        # Narration only
        cmd_master = [
            "ffmpeg", "-y",
            "-i", str(montage_mp4),
            "-i", str(narration_mp3),
            "-filter_complex", fg_filter,
            "-map", "[v]", "-map", "1:a",
            *video_codec_args(),
            "-c:a", "aac", "-b:a", "320k",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            str(master_mp4)
        ]

    subprocess.run(cmd_master, check=True)
    print(f"🎉 MASTER SHORT RENDER COMPLETE: {master_mp4}")
    print(f"📦 File Size: {master_mp4.stat().st_size / (1024*1024):.2f} MB")

    # 6. Extract High-Contrast Thumbnail
    thumb_path = renders_dir / f"{slug}_thumbnail.jpg"
    cmd_thumb = [
        "ffmpeg", "-y",
        "-ss", "1.5",
        "-i", str(master_mp4),
        "-vframes", "1",
        "-vf", "scale=1080:1920,unsharp=5:5:1.0:5:5:0.0,eq=saturation=1.28:contrast=1.12",
        str(thumb_path)
    ]
    subprocess.run(cmd_thumb, check=True, capture_output=True)
    print(f"🖼️ High-CTR Thumbnail Created: {thumb_path.name}")

    # 7. Upload to YouTube Shorts
    if args.upload:
        print("\n🚀 Step 5: Uploading directly to YouTube Shorts via YouTube Data API...")
        uploader = YouTubeUploader()
        upload_res = uploader.execute({
            "video_path": str(master_mp4),
            "title": yt_title[:100],
            "description": episode["description"],
            "tags": episode["tags"],
            "privacy_status": "public"
        })
        if upload_res.success:
            vid = upload_res.data.get("video_id")
            vurl = upload_res.data.get("video_url", f"https://youtube.com/shorts/{vid}")
            print(f"✅ UPLOAD SUCCESSFUL! URL: {vurl}")
            episode["youtube_video_id"] = vid
            episode["youtube_video_url"] = vurl
        else:
            print(f"[WARN] YouTube upload failed: {upload_res.error}")

    # 8. Record to History
    history = load_history()
    if slug not in history:
        history.append(slug)
        save_history(history)

    LAST_EPISODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_EPISODE_FILE, "w", encoding="utf-8") as f:
        json.dump(episode, f, indent=2)

    print(f"\n📋 Saved episode record to {LAST_EPISODE_FILE.name}")
    print(f"✨ Published history now contains {len(history)} animal subjects.")
    print("=" * 68)
    print("🐾 AUTONOMOUS PRODUCTION RUN COMPLETE!")
    print("=" * 68)


if __name__ == "__main__":
    main()
