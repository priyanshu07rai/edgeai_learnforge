"""
summarizer.py — MapReduce Overall Summarizer Pipeline

Pre-processes transcripts, splits them into overlapping chunks,
generates parallel chunk bullet summaries using Llama 1B threads,
and aggregates (reduces) them into a cohesive structured overall summary.
"""
import os
import json
import re
from typing import List
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from ollama_health import check_ollama_available
from cleaner import clean_transcript_spacy
from notes_generator import _call_gemini_raw, _call_ollama_raw

# Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:1b"


def chunk_text_overlapping(text: str, chunk_size: int = 600, overlap: int = 100) -> List[str]:
    """Splits text into overlapping parts for safe parallel processing."""
    words = text.split()
    total_words = len(words)
    if total_words <= chunk_size:
        return [text]
        
    chunks = []
    start = 0
    while start < total_words:
        end = min(total_words, start + chunk_size)
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        if end >= total_words:
            break
        # Shift back by overlap
        start = end - overlap
        # Prevent infinite loops if overlap is configured incorrectly
        if start >= end:
            start = end - 1
            
    return chunks


def summarize_chunk(chunk_text: str, ollama_url: str = OLLAMA_URL, gemini_key: str = None) -> str:
    """Summarizes a single transcript chunk to key bullet points."""
    prompt = f"""You are an expert technical writer.
Analyze this segment of an educational video transcript.
Generate 2-3 detailed, factual bullet points summarizing the technical concepts, steps, or code implementations discussed.
Use objective, third-person voice. Do NOT include greetings, pleasantries, or filler.

Transcript Segment:
{chunk_text}

Bullet Points:"""

    if gemini_key:
        return _call_gemini_raw(prompt, gemini_key, json_mode=False)
    else:
        return _call_ollama_raw(prompt, ollama_url, json_mode=False)


def _parse_json_safely(raw: str) -> dict:
    """Finds, parses, and validates the JSON object from LLM response."""
    # Find JSON block
    for match in re.finditer(r'\{', raw):
        try:
            candidate = raw[match.start():]
            end = candidate.rfind('}')
            if end < 0:
                continue
            data = json.loads(candidate[:end + 1])
            
            # Enforce schema structure
            title = data.get("title", "Video Course Summary").strip()
            summary = data.get("cohesive_summary", "Summary is being processed.").strip()
            takeaways = data.get("key_takeaways", [])
            if not isinstance(takeaways, list):
                takeaways = [str(takeaways)]
                
            return {
                "title": title,
                "cohesive_summary": summary,
                "key_takeaways": [t.strip() for t in takeaways if t.strip()]
            }
        except Exception:
            continue
            
    # Heuristic fallback if json parsing fails completely
    bullets = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("-") or line.startswith("*") or (line and line[0].isdigit() and "." in line):
            cleaned_line = re.sub(r'^[-\d.*\s+]+', '', line).strip()
            if cleaned_line:
                bullets.append(cleaned_line)
                
    return {
        "title": "Video Course Summary",
        "cohesive_summary": raw[:300] + "..." if len(raw) > 300 else raw,
        "key_takeaways": bullets[:6] if bullets else ["Key technical concepts discussed in this course."]
    }


def reduce_summaries(bullet_points: List[str], ollama_url: str = OLLAMA_URL, gemini_key: str = None) -> dict:
    """Combines chunk summaries into a single cohesive overall structured JSON summary."""
    combined_bullets = "\n".join(bullet_points)
    
    prompt = f"""# Role and Objective
You are the lead technical editor for a premium educational platform. Your task is to combine these section summaries into a single, cohesive, high-level summary of the entire video.

# Instructions
1. Organize the technical content into a professional, textbook-quality summary.
2. Structure the response into three distinct fields:
   - "title": A professional, high-level title for the entire video.
   - "cohesive_summary": A detailed, 3-4 sentence paragraph synthesizing the overall objective, core technology stack, and outcomes.
   - "key_takeaways": A list of 5-6 structured, technical bullet points highlighting main concepts, architecture decisions, or implementation steps.
3. Use strict third-person objective voice. Do NOT include conversational leakage, first-person pronouns, or empty placeholders.

Section Summaries:
{combined_bullets}

Return ONLY a JSON object with this exact structure (no markdown wrapper, no other text):
{{
  "title": "Overall Video Title",
  "cohesive_summary": "Detailed paragraph summary...",
  "key_takeaways": [
    "Takeaway 1...",
    "Takeaway 2..."
  ]
}}"""

    if gemini_key:
        raw_json = _call_gemini_raw(prompt, gemini_key, json_mode=True)
    else:
        raw_json = _call_ollama_raw(prompt, ollama_url, json_mode=True)
        
    return _parse_json_safely(raw_json)


def generate_overall_summary(video_id: str, storage_dir: str, ollama_url: str = OLLAMA_URL) -> dict:
    """
    High-level MapReduce coordinator.
    Loads raw transcript, cleans via spaCy, chunks with overlap,
    generates chunk summaries in parallel, and reduces to a final cacheable JSON.
    """
    video_dir = os.path.join(storage_dir, video_id)
    summary_path = os.path.join(video_dir, "summary.json")
    
    if os.path.exists(summary_path):
        try:
            with open(summary_path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
            
    # Load transcript.json
    transcript_path = os.path.join(video_dir, "transcript.json")
    if not os.path.exists(transcript_path):
        return {
            "title": "Course Overview",
            "cohesive_summary": "No transcript found for this video. Please upload or process first.",
            "key_takeaways": []
        }
        
    with open(transcript_path, encoding='utf-8') as f:
        data = json.load(f)
        
    raw_text = data.get("transcript", "")
    if not raw_text:
        return {
            "title": "Course Overview",
            "cohesive_summary": "Transcript is empty.",
            "key_takeaways": []
        }
        
    # Step 1: Pre-processing & Text Cleaning Layer
    cleaned_text = clean_transcript_spacy(raw_text)
    
    # Step 2: Chunking Splitter
    chunks = chunk_text_overlapping(cleaned_text, chunk_size=600, overlap=100)
    
    gemini_key = os.environ.get("GEMINI_API_KEY")
    ollama_online = check_ollama_available(ollama_url)
    
    if not gemini_key and not ollama_online:
        # Standard fallback if LLMs are offline
        bullets = [cleaned_text[:120] + "..."]
        result = {
            "title": "Video Overview (Offline)",
            "cohesive_summary": cleaned_text[:300] + "..." if len(cleaned_text) > 300 else cleaned_text,
            "key_takeaways": bullets
        }
        return result
        
    # Step 3: Parallel Llama 1B Threads
    # Limit to 3 parallel requests to prevent overloading local uvicorn/ollama servers
    max_workers = 3 if gemini_key else 2
    
    print(f"[LearnForge MapReduce] Processing {len(chunks)} chunks in parallel...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        bullet_points = list(executor.map(lambda c: summarize_chunk(c, ollama_url, gemini_key), chunks))
        
    print(f"[LearnForge MapReduce] Reducing {len(bullet_points)} chunk summaries...")
    
    # Step 4: Final Aggregator Layer (Reduce)
    result = reduce_summaries(bullet_points, ollama_url, gemini_key)
    
    # Cache result
    os.makedirs(video_dir, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        
    return result
