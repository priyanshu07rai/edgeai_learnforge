import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

import os
import json
import uuid
import re
import tempfile
import shutil
import http.cookiejar
import requests
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv

# Load .env variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Import custom modules
from segmenter import segment_transcript_llama, split_long_topics
from vector_db import chunk_transcript, build_and_persist_index
from notes_generator import generate_notes_for_video, generate_notes_for_single_topic
from flashcard_generator import generate_flashcards_for_video, generate_flashcards_for_single_topic
from quiz_generator import generate_quiz_for_video, generate_quiz_for_single_topic
from qa_engine import answer_question
from extractor import extract_knowledge_units, calculate_concept_density

app = FastAPI(title="LearnForge AI API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root folders
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
STORAGE_DIR = os.path.join(PROJECT_ROOT, "storage")
os.makedirs(STORAGE_DIR, exist_ok=True)

# Global variables for optimization and transcription correction
_whisper_model = None

# Real-time transcription progress tracker  { video_id: {segments, audio_pos, done} }
_transcription_progress: dict = {}

def heal_transcript_vocabulary(text: str) -> str:
    if not text:
        return text
    corrections = {
        r'\bhardness\s+engineering\b': 'harness engineering',
        r'\bhardness\s+engineers\b': 'harness engineers',
        r'\bhardness\s+engineer\b': 'harness engineer',
        r'\bhardness\s+word\b': 'harness word',
        r'\bhardness\s+term\b': 'harness term',
        r'\bwrite\s+hardness\b': 'write harness',
        r'\bwrite\s+the\s+hardness\b': 'write the harness',
        r'\bwrite\s+a\s+hardness\b': 'write a harness',
        r'\bbuilding\s+(the\s+)?hardness\b': r'building \1harness',
        r'\bcomponent\s+of\s+hardness\b': 'component of harness',
        r'\bhardness\s+around\b': 'harness around',
        r'\bthis\s+is\s+hardness\b': 'this is harness',
        r'\bwhat\s+is\s+hardness\b': 'what is harness',
        r'\bopen\s+clock\b': 'OpenAI/Claude',
        r'\bInjun\b': 'Engine',
        r'\binjun\b': 'engine',
        r'\binjuns\b': 'engines',
        r'\bClawdick\b': 'Claude',
        r'\bclawdick\b': 'claude',
        r'\bClawd\b': 'Claude',
        r'\bclawd\b': 'claude',
        r'\bsoft\s+marks\b': 'softmax',
        r'\bAP\s+I\b': 'API',
        r'\bap\s+i\b': 'api',
        r'\bJango\b': 'Django',
        r'\bjango\b': 'django',
        r'\bRunar\b': 'radar',
        r'\brunar\b': 'radar',
    }
    for pattern, replacement in corrections.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

class ProcessRequest(BaseModel):
    video_id: str

def extract_youtube_video_id(url: str) -> Optional[str]:
    """
    Extracts the 11-character video ID from various YouTube URL formats.
    """
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0].split("&")[0]
    elif "youtube.com/watch" in url:
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        if "v" in q:
            return q["v"][0]
    elif "youtube.com/embed/" in url:
        return url.split("youtube.com/embed/")[1].split("?")[0].split("&")[0]
    return None

def extract_json_from_html(html: str, var_name: str) -> Optional[str]:
    pattern = re.compile(rf'{var_name}\s*=\s*')
    match = pattern.search(html)
    if not match:
        return None
    
    start_idx = match.end()
    if html[start_idx] != '{':
        first_brace = html.find('{', start_idx)
        if first_brace == -1:
            return None
        start_idx = first_brace
        
    brace_count = 0
    in_string = False
    escape = False
    for i in range(start_idx, len(html)):
        char = html[i]
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return html[start_idx:i+1]
    return None

def parse_chapters_from_description(description: str):
    chapters = []
    lines = description.splitlines()
    pattern = re.compile(r'(?:^|\s)(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b')
    for line in lines:
        match = pattern.search(line)
        if match:
            ts_str = match.group(0).strip()
            title = line.replace(ts_str, "").strip()
            title = re.sub(r'^[-\s:._|–]+', '', title)
            title = re.sub(r'^\d+[\s.]+', '', title)
            title = title.strip()
            
            h = int(match.group(1)) if match.group(1) else 0
            m = int(match.group(2))
            s = int(match.group(3))
            total_seconds = h * 3600 + m * 60 + s
            
            if title:
                chapters.append({
                    "title": title,
                    "start_time": total_seconds
                })
    
    chapters.sort(key=lambda x: x["start_time"])
    
    filtered = []
    seen_titles = set()
    for chap in chapters:
        title_lower = chap["title"].lower()
        if title_lower in seen_titles:
            continue
        if filtered and filtered[-1]["start_time"] == chap["start_time"]:
            continue
        filtered.append(chap)
        seen_titles.add(title_lower)
        
    return filtered

def fetch_youtube_chapters(video_id: str):
    import requests
    url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8.0)
        if resp.status_code == 200:
            json_str = extract_json_from_html(resp.text, "ytInitialPlayerResponse")
            if not json_str:
                json_str = extract_json_from_html(resp.text, "var ytInitialPlayerResponse")
            if json_str:
                player_data = json.loads(json_str)
                desc = player_data.get("videoDetails", {}).get("shortDescription", "")
                if desc:
                    return parse_chapters_from_description(desc)
    except Exception as e:
        print(f"[LearnForge API] Error fetching description for chapters: {e}")
    return []

def map_chapters_to_segments(chapters, segments):
    topics = []
    num_chapters = len(chapters)
    if num_chapters == 0 or len(segments) == 0:
        return []
        
    chapters[0]["start_time"] = 0
    
    for i in range(num_chapters):
        chap = chapters[i]
        start_t = chap["start_time"]
        end_t = chapters[i+1]["start_time"] if i < num_chapters - 1 else float('inf')
        
        seg_indices = [idx for idx, seg in enumerate(segments) if start_t <= seg["start"] < end_t]
        
        if seg_indices:
            topics.append({
                "title": chap["title"],
                "start_segment": min(seg_indices),
                "end_segment": max(seg_indices)
            })
            
    seen = {}
    for topic in topics:
        title = topic["title"]
        if title in seen:
            seen[title] += 1
            topic["title"] = f"{title} (Part {seen[title]})"
        else:
            seen[title] = 1
            
    return topics

def _get_api_instance():
    # Check for cookies.txt in backend dir or project root
    cookie_paths = [
        os.path.join(BASE_DIR, "cookies.txt"),
        os.path.join(PROJECT_ROOT, "cookies.txt")
    ]
    
    session = None
    for cp in cookie_paths:
        if os.path.exists(cp):
            target_file = None
            if os.path.isdir(cp):
                # If it's a directory, scan for .txt files inside it
                for f in os.listdir(cp):
                    if f.endswith(".txt"):
                        target_file = os.path.join(cp, f)
                        break
            else:
                target_file = cp

            if target_file and os.path.exists(target_file):
                print(f"[LearnForge API] Found YouTube cookies file at {target_file}. Loading cookies...")
                try:
                    session = requests.Session()
                    cookie_jar = http.cookiejar.MozillaCookieJar(target_file)
                    cookie_jar.load(ignore_discard=True, ignore_expires=True)
                    session.cookies = cookie_jar
                    print("[LearnForge API] Successfully loaded cookies into session.")
                    break
                except Exception as ce:
                    print(f"[LearnForge API] Failed to load cookies from {target_file}: {ce}")
                    session = None
                
    if session is not None:
        return YouTubeTranscriptApi(http_client=session)
    return YouTubeTranscriptApi()

def fetch_raw_transcript_safely(yt_id: str):
    api = _get_api_instance()
    try:
        transcript_list = api.list(yt_id)
        
        # 1. Try finding native English captions
        try:
            t = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
            print(f"[LearnForge API] Found native English captions ({t.language_code}).")
            return t.fetch(), t.language_code
        except Exception:
            pass
        
        # 2. Try translating each available transcript to English (prioritize auto-generated ones)
        all_transcripts = list(transcript_list)
        # Sort: put auto-generated captions first (they are always translatable)
        all_transcripts.sort(key=lambda x: 0 if x.is_generated else 1)
        
        for t in all_transcripts:
            try:
                if t.is_translatable:
                    print(f"[LearnForge API] Translating captions from {t.language_code} → English (is_generated={t.is_generated}).")
                    translated = t.translate('en').fetch()
                    print(f"[LearnForge API] Translation succeeded. Got {len(translated)} segments in English.")
                    return translated, 'en'
                else:
                    print(f"[LearnForge API] Captions ({t.language_code}) are NOT translatable, skipping.")
            except Exception as trans_err:
                print(f"[LearnForge API] Translation of {t.language_code} captions failed: {trans_err}")
                continue

        # 3. Last resort: return raw captions in their native language
        try:
            t = all_transcripts[0] if all_transcripts else next(iter(transcript_list))
            print(f"[LearnForge API] No translatable captions found. Using raw {t.language_code} captions.")
            return t.fetch(), t.language_code
        except Exception:
            pass
            
    except Exception as e:
        print(f"[LearnForge API] Smart transcript listing failed: {e}")
        
    return api.fetch(yt_id), 'en'

@app.post("/transcript")
async def generate_transcript(
    youtube_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    video_id: Optional[str] = Form(None),   # optional client-supplied ID for progress polling
):
    # Use client-supplied ID if valid, else generate a new one
    if not video_id or len(video_id) < 8:
        video_id = str(uuid.uuid4())
    transcript = ""
    duration = 0.0
    segments = []
    youtube_video_id = None
    youtube_url_val = None
    chapters = []
    language_code = "en"

    if file:
        filename = file.filename
        if not filename.lower().endswith(".mp4"):
            raise HTTPException(status_code=400, detail="Unsupported file. Only .mp4 files are supported.")

        print(f"[LearnForge API] Local MP4 upload detected: {filename}")
        print(f"[LearnForge API] Saving uploaded file to temp storage...")

        # Save uploaded file to a temporary location
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, filename)
        try:
            file_bytes = await file.read()
            with open(tmp_path, "wb") as f_out:
                f_out.write(file_bytes)
            print(f"[LearnForge API] File saved ({len(file_bytes) // 1024} KB).")

            # ── PPT Best Practice #1: Use bundled ffmpeg from imageio-ffmpeg ──
            ffmpeg_exe = None
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                os.environ["PATH"] = os.path.dirname(ffmpeg_exe) + os.pathsep + os.environ.get("PATH", "")
                print(f"[LearnForge API] Bundled ffmpeg located: {ffmpeg_exe}")
            except Exception as ffmpeg_err:
                print(f"[LearnForge API] Warning: bundled ffmpeg unavailable: {ffmpeg_err}")

            # ── PPT Best Practice #2: Preprocess to 16kHz mono WAV before Whisper ──
            # Convert: -vn (no video), -ar 16000 (16kHz), -ac 1 (mono), pcm_s16le codec
            # This reduces I/O, speeds loading, and matches Whisper's native sample rate.
            wav_path = os.path.join(tmp_dir, "audio.wav")
            try:
                import subprocess
                exe = ffmpeg_exe or "ffmpeg"
                result = subprocess.run(
                    [exe, "-y", "-i", tmp_path, "-vn", "-ar", "16000", "-ac", "1",
                     "-c:a", "pcm_s16le", wav_path],
                    capture_output=True, timeout=300
                )
                if result.returncode == 0 and os.path.exists(wav_path):
                    audio_path = wav_path
                    print(f"[LearnForge API] FFmpeg preprocessing complete → 16kHz mono WAV.")
                else:
                    audio_path = tmp_path  # fallback to original
                    print(f"[LearnForge API] FFmpeg preprocessing failed, using original MP4.")
            except Exception as conv_err:
                audio_path = tmp_path
                print(f"[LearnForge API] FFmpeg conversion error: {conv_err}. Using original.")

            global _whisper_model
            if _whisper_model is None:
                from faster_whisper import WhisperModel
                print("[LearnForge API] Loading Whisper Model into memory for the first time...")
                _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=8)
            whisper_model = _whisper_model
            print(f"[LearnForge API] Whisper model retrieved from cache. Transcribing audio...")

            # ── Language detection then single-pass transcription ─────────────────
            # Step 1: Use detect_language() — runs in ~1s on first 30s of audio
            # Step 2: if non-English → task="translate" → clean English output
            #         if English     → task="transcribe" → fastest path
            #
            # WHY: task="transcribe" on Hindi with tiny model produces garbled
            # transliterated text ("Roto nation op l ko h") that causes the
            # segmenter to hallucinate random topic names like "Frontend React".
            # task="translate" produces coherent English for any source language.

            try:
                lang_code_raw, lang_prob, _ = whisper_model.detect_language(
                    audio_path,
                    vad_filter=True,
                    language_detection_segments=3,     # sample 3 × 30s windows
                )
                language_code = lang_code_raw if lang_code_raw else "en"
                print(f"[LearnForge API] Detected language: {language_code} (prob={lang_prob:.2f})")
            except Exception as lang_err:
                print(f"[LearnForge API] Language detection failed: {lang_err}. Defaulting to English.")
                language_code = "en"

            # Choose task based on detected language
            whisper_task = "transcribe" if language_code == "en" else "translate"
            print(f"[LearnForge API] Whisper task='{whisper_task}' for source language '{language_code}'")

            # Initialise live progress tracking
            _transcription_progress[video_id] = {"segments": 0, "audio_pos": 0.0, "done": False}

            segments_iter, info = whisper_model.transcribe(
                audio_path,
                beam_size=1,                      # greedy — fastest on CPU
                best_of=1,                        # no sampling hypotheses
                language=language_code,           # pin detected language (avoids re-detection)
                task=whisper_task,                # translate non-English → clean English
                vad_filter=True,                  # skip silence & background noise
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200
                ),
                condition_on_previous_text=False, # prevents hallucination loops
            )

            full_text_parts = []
            for seg in segments_iter:
                seg_start = seg.start
                seg_end = seg.end
                seg_text = seg.text.strip()
                if not seg_text:
                    continue  # skip empty VAD-filtered segments

                segments.append({
                    "start": seg_start,
                    "end": seg_end,
                    "text": seg_text
                })

                m, s = divmod(int(seg_start), 60)
                h, m = divmod(m, 60)
                timestamp = f"[{h:02d}:{m:02d}:{s:02d}]" if h > 0 else f"[{m:02d}:{s:02d}]"
                full_text_parts.append(f"{timestamp} {seg_text}")

                # Update live progress
                _transcription_progress[video_id]["segments"] = len(segments)
                _transcription_progress[video_id]["audio_pos"] = seg_end

            transcript = "\n".join(full_text_parts)
            duration = segments[-1]["end"] if segments else 0.0
            print(f"[LearnForge API] Whisper transcription complete. {len(segments)} segments, {duration:.1f}s.")
            if video_id in _transcription_progress:
                _transcription_progress[video_id]["done"] = True

        except Exception as whisper_err:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            print(f"[LearnForge API] Whisper transcription failed: {whisper_err}")
            raise HTTPException(
                status_code=500,
                detail=f"Audio transcription failed: {str(whisper_err)}. Make sure the file contains valid audio."
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        
    elif youtube_url:
        yt_id = extract_youtube_video_id(youtube_url)
        if not yt_id:
            raise HTTPException(status_code=400, detail="Unsupported file.")
        
        youtube_video_id = yt_id
        youtube_url_val = youtube_url
        print(f"[LearnForge API] YouTube URL detected. Video ID: {yt_id}")
        print(f"[LearnForge API] Requesting captions from youtube-transcript-api...")
        
        try:
            raw_transcript, lang_code = fetch_raw_transcript_safely(yt_id)
            language_code = lang_code
            full_text_parts = []
            
            for idx, item in enumerate(raw_transcript):
                start_time = item.start
                duration_time = item.duration if hasattr(item, 'duration') else 0.0
                end_time = start_time + duration_time
                text_content = item.text.strip().replace("\n", " ")
                
                segments.append({
                    "start": start_time,
                    "end": end_time,
                    "text": text_content
                })
                
                # Create timestamp tag: [HH:MM:SS] or [MM:SS]
                m, s = divmod(int(start_time), 60)
                h, m = divmod(m, 60)
                timestamp = f"[{h:02d}:{m:02d}:{s:02d}]" if h > 0 else f"[{m:02d}:{s:02d}]"
                full_text_parts.append(f"{timestamp} {text_content}")
            
            transcript = "\n".join(full_text_parts)
            duration = segments[-1]["end"] if segments else 0.0
            
            print(f"[LearnForge API] Successfully fetched {len(segments)} transcript segments from YouTube.")
            
            try:
                # Fetch YouTube chapters/timestamps
                chapters = fetch_youtube_chapters(yt_id)
                print(f"[LearnForge API] Extracted {len(chapters)} chapters from description.")
            except Exception as e:
                print(f"[LearnForge API] Failed to extract chapters: {e}")
            
        except Exception as e:
            err_msg = str(e)
            print(f"[LearnForge API] youtube-transcript-api failed: {err_msg}")
            if "cookies" in err_msg.lower() or "blocking" in err_msg.lower() or "blocked" in err_msg.lower() or "ip" in err_msg.lower():
                raise HTTPException(status_code=400, detail="YouTube is rate-limiting or blocking requests. To bypass this, download cookies from your browser using an extension and save them as 'cookies.txt' in the project root folder.")
            if "subtitles are disabled" in err_msg.lower() or "no transcripts" in err_msg.lower():
                raise HTTPException(status_code=400, detail="No captions available for this video. The creator has disabled subtitles.")
            raise HTTPException(status_code=400, detail="Unable to fetch transcript. The video may be private, age-restricted, or unavailable. If blocked, save a browser 'cookies.txt' in the project root.")
    else:
        raise HTTPException(status_code=400, detail="Unable to fetch transcript.")

    # Heal vocabulary mistakes in the transcript
    transcript = heal_transcript_vocabulary(transcript)
    for seg in segments:
        if "text" in seg:
            seg["text"] = heal_transcript_vocabulary(seg["text"])

    payload = {
        "video_id": video_id,
        "youtube_video_id": youtube_video_id,
        "youtube_url": youtube_url_val,
        "transcript": transcript,
        "duration": duration,
        "segments": segments,
        "chapters": chapters,
        "language_code": language_code
    }

    # Write files to disk storage/<video_id>/transcript.json
    video_dir = os.path.join(STORAGE_DIR, video_id)
    os.makedirs(video_dir, exist_ok=True)
    with open(os.path.join(video_dir, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload


@app.get("/transcript/progress/{video_id}")
async def get_transcription_progress(video_id: str):
    """
    Returns real-time Whisper transcription progress.
    Frontend can poll this while /transcript is running.
    """
    prog = _transcription_progress.get(video_id)
    if prog is None:
        return {"active": False, "segments": 0, "audio_pos": 0.0, "done": False}
    return {
        "active": not prog["done"],
        "segments": prog["segments"],
        "audio_pos": prog["audio_pos"],
        "done": prog["done"],
    }


_active_prefetches = set()

def prefetch_video_assets(video_id: str, storage_dir: str):
    if video_id in _active_prefetches:
        return
    _active_prefetches.add(video_id)
    try:
        print(f"[LearnForge Prefetch] Starting background pre-generation for video {video_id}...")
        video_dir = os.path.join(storage_dir, video_id)
        topics_path = os.path.join(video_dir, "topics.json")
        if not os.path.exists(topics_path):
            print(f"[LearnForge Prefetch] topics.json not found for video {video_id}.")
            return
        with open(topics_path, encoding='utf-8') as f:
            topics = json.load(f)
        
        from notes_generator import generate_notes_for_single_topic
        from flashcard_generator import generate_flashcards_for_single_topic
        from quiz_generator import generate_quiz_for_single_topic
        
        for i in range(len(topics)):
            try:
                generate_notes_for_single_topic(video_id, i, storage_dir)
            except Exception as e:
                print(f"[LearnForge Prefetch] Notes failed for topic {i}: {e}")
            
            try:
                generate_flashcards_for_single_topic(video_id, i, storage_dir)
            except Exception as e:
                print(f"[LearnForge Prefetch] Flashcards failed for topic {i}: {e}")
                
            try:
                generate_quiz_for_single_topic(video_id, i, storage_dir)
            except Exception as e:
                print(f"[LearnForge Prefetch] Quiz failed for topic {i}: {e}")
                
        print(f"[LearnForge Prefetch] Completed background pre-generation for video {video_id}.")
    except Exception as e:
        print(f"[LearnForge Prefetch] Error in prefetch task: {e}")
    finally:
        _active_prefetches.discard(video_id)


@app.post("/process")
async def process_transcript(req: ProcessRequest, background_tasks: BackgroundTasks):
    video_id = req.video_id
    video_dir = os.path.join(STORAGE_DIR, video_id)
    transcript_path = os.path.join(video_dir, "transcript.json")

    if not os.path.exists(transcript_path):
        raise HTTPException(status_code=404, detail="Unable to process transcript.")

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Heal on loading to cover pre-existing or fallback transcripts
        if "transcript" in data:
            data["transcript"] = heal_transcript_vocabulary(data["transcript"])
        if "segments" in data:
            for seg in data["segments"]:
                if "text" in seg:
                    seg["text"] = heal_transcript_vocabulary(seg["text"])
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to process transcript.")

    # 1. Topic Segmentation
    try:
        topics = []
        chapters = data.get("chapters", [])
        lang_code = data.get("language_code", "en")
        
        if chapters:
            print(f"[LearnForge API] Priority 1: Found creator timestamps. Using YouTube Chapters.")
            topics = map_chapters_to_segments(chapters, data.get("segments", []))
            for t in topics:
                t["original_language"] = lang_code
            
        if not topics:
            print(f"[LearnForge API] Priority 2/3: Chapters unavailable. Running LLM/Semantic segmentation.")
            topics = segment_transcript_llama(data.get("transcript", ""), data.get("segments", []), lang_code)
            
        if not topics:
            raise Exception("No topics returned")

        # Always run subtopic splitting to partition coarse segments further
        topics = split_long_topics(topics, data.get("segments", []), lang_code, "http://localhost:11434/api/generate")

        # Enrich topics with actual transcript content (for generators and debug viewer)
        segments_list = data.get("segments", [])
        for i, topic in enumerate(topics):
            s_start = topic.get("start_segment", 0)
            s_end = topic.get("end_segment", 0)
            seg_texts = []
            for s in segments_list[s_start:s_end + 1]:
                text = s.get("text", "").strip()
                if text:
                    # Clean trailing hyphens/separators
                    text = re.sub(r'\s*[-\s:._|–/]+$', '', text).strip()
                    if text:
                        seg_texts.append(text)
            
            joined_content = " ".join(seg_texts).strip()
            # Ensure it ends with a period if missing ending punctuation
            if joined_content and joined_content[-1] not in '.!?।':
                joined_content += '.'
            topic["content"] = joined_content

        with open(os.path.join(video_dir, "topics.json"), "w", encoding="utf-8") as f:
            json.dump(topics, f, indent=2, ensure_ascii=False)

        print(f"[LearnForge API] Saved topics.json with content for {len(topics)} topics.")
        
        # Merge topics with identical notes
        from notes_generator import merge_topics_with_identical_notes
        topics = merge_topics_with_identical_notes(video_id, STORAGE_DIR)

        # Merge consecutive introduction topics
        from notes_generator import merge_introduction_topics
        topics = merge_introduction_topics(video_id, STORAGE_DIR)

        # Enrich final topics list with concept density badges
        corpus = [t.get("content", "") for t in topics if t.get("content", "")]
        for topic in topics:
            knowledge = extract_knowledge_units(topic.get("content", ""), topic.get("title", ""), corpus=corpus)
            density_info = calculate_concept_density(knowledge, topic.get("title", ""))
            topic["density"] = density_info["density"]
            topic["density_badge"] = density_info["badge"]

        # Write final enriched topics back to topics.json
        with open(os.path.join(video_dir, "topics.json"), "w", encoding="utf-8") as f:
            json.dump(topics, f, indent=2, ensure_ascii=False)
        # Print audit summary for first 3 topics
        for t in topics[:3]:
            content_preview = t.get('content', '')[:200].encode('ascii', errors='replace').decode('ascii')
            print(f"[LearnForge API]  TITLE: {t.get('title')}")
            print(f"[LearnForge API]  CONTENT LEN: {len(t.get('content', ''))}")
            print(f"[LearnForge API]  CONTENT PREVIEW: {content_preview}")

    except Exception as e:
        print(f"[LearnForge API] Topic extraction error: {e}")
        raise HTTPException(status_code=500, detail="Topic extraction failed.")

    # 2. Chunk & Vector DB Indexing
    try:
        chunks = chunk_transcript(data.get("segments", []), topics)
        build_and_persist_index(chunks, video_dir)

        metadata = {
            "video_id": video_id,
            "chunk_count": len(chunks),
            "embedding_model": "all-MiniLM-L6-v2",
            "index_type": "faiss-flat-ip"  # L2-normalized IndexFlatIP = cosine similarity
        }
        with open(os.path.join(video_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        print(f"[LearnForge API] FAISS indexing error: {e}")
        raise HTTPException(status_code=500, detail="Index creation failed.")

    # Trigger asynchronous background prefetch of all notes/flashcards/quiz assets
    background_tasks.add_task(prefetch_video_assets, video_id, STORAGE_DIR)

    return {
        "topic_count": len(topics),
        "topics": topics
    }


@app.get("/debug/{video_id}")
async def debug_video(video_id: str):
    """Debug endpoint: returns raw pipeline data for a video — topics, chunks, notes, flashcards, quiz."""
    video_dir = os.path.join(STORAGE_DIR, video_id)
    if not os.path.exists(video_dir):
        raise HTTPException(status_code=404, detail="Video not found.")

    def load_json(path):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return None

    topics = load_json(os.path.join(video_dir, "topics.json")) or []
    chunks = load_json(os.path.join(video_dir, "chunks.json")) or []
    notes = load_json(os.path.join(video_dir, "notes.json")) or {}
    flashcards = load_json(os.path.join(video_dir, "flashcards.json")) or {}
    quiz = load_json(os.path.join(video_dir, "quiz.json")) or {}

    # Build per-topic debug view
    debug_topics = []
    for i, topic in enumerate(topics):
        topic_id = f"topic_{i}"
        topic_chunks = [c for c in chunks if c.get("topic_id") == topic_id]
        topic_notes = (notes.get("topics") or [{}])[i] if i < len(notes.get("topics", [])) else {}
        topic_cards = (flashcards.get("topics") or [{}])[i] if i < len(flashcards.get("topics", [])) else {}
        topic_quiz = (quiz.get("topics") or [{}])[i] if i < len(quiz.get("topics", [])) else {}

        debug_topics.append({
            "index": i,
            "title": topic.get("title", ""),
            "content": topic.get("content", ""),
            "content_length": len(topic.get("content", "")),
            "chunk_count": len(topic_chunks),
            "notes": topic_notes,
            "flashcards": topic_cards,
            "quiz": topic_quiz,
        })

    return {
        "video_id": video_id,
        "topic_count": len(topics),
        "topics": debug_topics,
    }

@app.post("/notes/generate")
async def get_notes(req: ProcessRequest):
    video_id = req.video_id
    video_dir = os.path.join(STORAGE_DIR, video_id)
    if not os.path.exists(video_dir):
        raise HTTPException(status_code=404, detail="Video directory not found.")
    try:
        notes = generate_notes_for_video(video_id, STORAGE_DIR)
        return notes
    except Exception as e:
        print(f"[LearnForge API] Notes generation error: {e}")
        raise HTTPException(status_code=500, detail="Notes generation failed.")

@app.post("/flashcards/generate")
async def get_flashcards(req: ProcessRequest):
    video_id = req.video_id
    video_dir = os.path.join(STORAGE_DIR, video_id)
    if not os.path.exists(video_dir):
        raise HTTPException(status_code=404, detail="Video directory not found.")
    try:
        flashcards = generate_flashcards_for_video(video_id, STORAGE_DIR)
        return flashcards
    except Exception as e:
        print(f"[LearnForge API] Flashcards generation error: {e}")
        raise HTTPException(status_code=500, detail="Flashcards generation failed.")

@app.post("/quiz/generate")
async def get_quiz(req: ProcessRequest):
    video_id = req.video_id
    video_dir = os.path.join(STORAGE_DIR, video_id)
    if not os.path.exists(video_dir):
        raise HTTPException(status_code=404, detail="Video directory not found.")
    try:
        quiz = generate_quiz_for_video(video_id, STORAGE_DIR)
        return quiz
    except Exception as e:
        print(f"[LearnForge API] Quiz generation error: {e}")
        raise HTTPException(status_code=500, detail="Quiz generation failed.")


# ── Per-topic streaming endpoints (progressive loading) ───────────────────────

class TopicRequest(BaseModel):
    video_id: str
    topic_index: int

@app.post("/notes/topic")
async def get_notes_for_topic(req: TopicRequest, background_tasks: BackgroundTasks):
    """Generate notes for ONE topic. Returns { topic, topic_index, detailed, revision }."""
    video_dir = os.path.join(STORAGE_DIR, req.video_id)
    if not os.path.exists(video_dir):
        raise HTTPException(status_code=404, detail="Video not found.")
    
    # Ensure remaining assets are prefetched in the background
    background_tasks.add_task(prefetch_video_assets, req.video_id, STORAGE_DIR)
    
    try:
        result = generate_notes_for_single_topic(req.video_id, req.topic_index, STORAGE_DIR)
        return result
    except Exception as e:
        import traceback
        print(f"[LearnForge API] Notes/topic error [{req.topic_index}]: {e}\n{traceback.format_exc()}")
        # Graceful fallback — never 500 to client
        return {
            "topic": f"Topic {req.topic_index + 1}",
            "topic_index": req.topic_index,
            "detailed": {
                "summary": "Notes are still being generated. Please try again shortly.",
                "key_points": [],
                "important_terms": [],
                "examples": []
            },
            "revision": {"one_liner": "", "bullets": [], "terms": []}
        }

@app.post("/flashcards/topic")
async def get_flashcards_for_topic(req: TopicRequest, background_tasks: BackgroundTasks):
    """Generate flashcards for ONE topic."""
    video_dir = os.path.join(STORAGE_DIR, req.video_id)
    if not os.path.exists(video_dir):
        raise HTTPException(status_code=404, detail="Video not found.")
    
    background_tasks.add_task(prefetch_video_assets, req.video_id, STORAGE_DIR)
    
    try:
        result = generate_flashcards_for_single_topic(req.video_id, req.topic_index, STORAGE_DIR)
        return result
    except Exception as e:
        print(f"[LearnForge API] Flashcards/topic error [{req.topic_index}]: {e}")
        raise HTTPException(status_code=500, detail=f"Flashcards failed for topic {req.topic_index}.")

@app.post("/quiz/topic")
async def get_quiz_for_topic(req: TopicRequest, background_tasks: BackgroundTasks):
    """Generate quiz for ONE topic."""
    video_dir = os.path.join(STORAGE_DIR, req.video_id)
    if not os.path.exists(video_dir):
        raise HTTPException(status_code=404, detail="Video not found.")
    
    background_tasks.add_task(prefetch_video_assets, req.video_id, STORAGE_DIR)
    
    try:
        result = generate_quiz_for_single_topic(req.video_id, req.topic_index, STORAGE_DIR)
        return result
    except Exception as e:
        print(f"[LearnForge API] Quiz/topic error [{req.topic_index}]: {e}")
        raise HTTPException(status_code=500, detail=f"Quiz failed for topic {req.topic_index}.")


# ── Ask AI (RAG Q&A) ────────────────────────────────────────────────────────────────────────────────

class QARequest(BaseModel):
    video_id: str
    question: str
    topic_index: int = -1  # -1 = search all topics
    mode: str = "teacher"  # teacher | transcript | knowledge | hybrid

@app.post("/qa/ask")
async def ask_question_endpoint(req: QARequest):
    """RAG-based Q&A: answers come only from video transcript chunks."""
    video_dir = os.path.join(STORAGE_DIR, req.video_id)
    if not os.path.exists(video_dir):
        raise HTTPException(status_code=404, detail="Video not found.")
    try:
        result = answer_question(
            video_id=req.video_id,
            storage_dir=STORAGE_DIR,
            question=req.question,
            topic_index=req.topic_index,
            mode=req.mode,
        )
        return result
    except Exception as e:
        print(f"[LearnForge API] QA error: {e}")
        raise HTTPException(status_code=500, detail="Q&A failed.")


# ── Overall Video Summary (MapReduce) ─────────────────────────────────────────

@app.get("/summary/{video_id}")
async def get_overall_video_summary(video_id: str):
    """
    Returns the high-level MapReduce summary for the entire video.
    """
    video_dir = os.path.join(STORAGE_DIR, video_id)
    if not os.path.exists(video_dir):
        raise HTTPException(status_code=404, detail="Video directory not found.")
    try:
        from summarizer import generate_overall_summary
        result = generate_overall_summary(video_id, STORAGE_DIR)
        return result
    except Exception as e:
        print(f"[LearnForge API] Summary generation error: {e}")
        raise HTTPException(status_code=500, detail="Overall summary generation failed.")




