import json
import requests
import re
from ollama_health import check_ollama_available

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False

def get_semantic_boundaries(segments, target_k):
    total_segments = len(segments)
    if total_segments <= target_k:
        return [{"start_segment": i, "end_segment": i} for i in range(total_segments)]
        
    # Group segments into chunks of ~15 segments (~45 seconds of content)
    chunk_size = 15
    chunks = []
    chunk_ranges = []
    
    current_chunk_text = []
    current_start = 0
    
    for idx, seg in enumerate(segments):
        current_chunk_text.append(seg.get("text", ""))
        if len(current_chunk_text) >= chunk_size or idx == total_segments - 1:
            chunks.append(" ".join(current_chunk_text))
            chunk_ranges.append((current_start, idx))
            current_chunk_text = []
            current_start = idx + 1
            
    num_chunks = len(chunks)
    if num_chunks <= target_k:
        return [{"start_segment": r[0], "end_segment": r[1]} for r in chunk_ranges]
        
    if HAS_EMBEDDINGS:
        try:
            from vector_db import get_embedding_model
            print(f"[LearnForge API] Fetching cached SentenceTransformer model all-MiniLM-L6-v2...")
            model = get_embedding_model()
            print(f"[LearnForge API] Computing embeddings for {num_chunks} chunks...")
            embeddings = model.encode(chunks)
            
            # Compute cosine similarities between consecutive chunks
            similarities = []
            for i in range(num_chunks - 1):
                a = embeddings[i]
                b = embeddings[i+1]
                sim = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
                similarities.append((sim, i))
                
            # Pick the lowest similarity boundaries (target_k - 1 boundaries)
            sorted_sims = sorted(similarities, key=lambda x: x[0])
            boundary_indices = sorted([x[1] for x in sorted_sims[:target_k - 1]])
            
            # Construct boundaries
            boundaries = []
            start_chunk = 0
            for b_idx in boundary_indices:
                boundaries.append({
                    "start_segment": chunk_ranges[start_chunk][0],
                    "end_segment": chunk_ranges[b_idx][1]
                })
                start_chunk = b_idx + 1
                
            boundaries.append({
                "start_segment": chunk_ranges[start_chunk][0],
                "end_segment": chunk_ranges[-1][1]
            })
            return boundaries
        except Exception as e:
            print(f"[LearnForge API] Semantic segmentation error: {e}. Falling back to even chunks.")
            
    # Fallback to splitting chunks evenly
    boundaries = []
    step = max(1, num_chunks // target_k)
    start_chunk = 0
    for i in range(target_k - 1):
        end_chunk = min(num_chunks - 1, start_chunk + step - 1)
        if end_chunk < start_chunk:
            end_chunk = start_chunk
        boundaries.append({
            "start_segment": chunk_ranges[start_chunk][0],
            "end_segment": chunk_ranges[end_chunk][1]
        })
        start_chunk = end_chunk + 1
        if start_chunk >= num_chunks:
            break
            
    if start_chunk < num_chunks:
        boundaries.append({
            "start_segment": chunk_ranges[start_chunk][0],
            "end_segment": chunk_ranges[-1][1]
        })
    return boundaries

def label_segment_with_llama(text_snippet, ollama_url):
    prompt = f"""You are a specialized educational AI content compiler.
Analyze this short section of a video transcript (which may be in Hindi, Hinglish, English, or mixed language).

Transcript block:
{text_snippet}

Instructions:
1. Identify the core educational concept taught in this block.
2. Formulate a 1-sentence summary of the concept in English.
3. Generate a professional English topic title (maximum 5 words) based on the summary. The title must be in English even if the transcript is in Hindi or Hinglish. Do not transliterate or include Hindi characters.
4. Output your response in this exact format:
SUMMARY: [1-sentence summary of the concept in English]
TITLE: [English Topic Title]
"""
    try:
        response = requests.post(
            ollama_url,
            json={
                "model": "llama3.2:1b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1
                }
            },
            timeout=5.0
        )
        if response.status_code == 200:
            result = response.json().get("response", "").strip()
            match = re.search(r'TITLE:\s*(.+)$', result, re.MULTILINE | re.IGNORECASE)
            title = match.group(1).strip() if match else result
            
            # Clean title
            title = title.replace('"', '').replace("'", "")
            title = re.sub(r'^```json\s*|```$', '', title, flags=re.MULTILINE).strip()
            title = re.sub(r'^[-\s:._|–]+', '', title).strip()
            
            # Discard Devanagari (Hindi characters) and let fallback handle it in English
            if re.search(r'[\u0900-\u097f]', title):
                return None
                
            if title and len(title) > 2 and len(title.split()) <= 8:
                return title
    except Exception:
        pass
    return None

def label_segment_heuristic(text, segment_index=None):
    """
    Universal topic namer — works for any subject (chemistry, math, CS, history, etc.)
    Avoids hardcoded DRF/React keywords that falsely match non-CS content.
    """
    text_clean = text.strip()
    text_lower = text_clean.lower()
    words_in_text = re.findall(r'\b[a-z]{3,}\b', text_lower)
    suffix = f" {segment_index + 1}" if segment_index is not None else ""

    # ── Extract meaningful noun phrases from capitalized words in content ──────
    # Works well for post-Whisper translated text as Whisper capitalizes key entities.
    capitalized = re.findall(r'\b[A-Z][a-z]{3,}\b', text_clean)
    # Filter out common stop words
    stop = {"This", "That", "They", "Their", "There", "Here", "Have", "Will",
            "What", "When", "Where", "Which", "Then", "Also", "With", "From",
            "Into", "About", "Because", "After", "Before", "Some", "More", "Very",
            "Just", "Like", "Make", "Take", "Look", "Okay", "Right"}
    capitalized = [w for w in capitalized if w not in stop]
    if len(capitalized) >= 2:
        # Avoid repetitive words
        unique_caps = list(dict.fromkeys(capitalized))
        if len(unique_caps) >= 2:
            return " ".join(unique_caps[:3]) + suffix

    # ── Longest content words as topic name ───────────────────────────────────
    long_words = sorted(set(w for w in words_in_text if len(w) >= 6), key=len, reverse=True)
    if long_words:
        return " ".join(long_words[:3]).title()

    return f"Topic{suffix}"

def segment_transcript_llama(transcript_text, segments, lang_code="en", ollama_url="http://localhost:11434/api/generate"):
    if not segments:
        return []
        
    duration = segments[-1]["end"] if segments else 0.0
    target_k = max(12, min(20, int(duration // 900)))
    if target_k < 3:
        target_k = 3
        
    print(f"[LearnForge API] Initializing Semantic Topic Segmentation (Target: {target_k} Knowledge Units)...")
    
    boundaries = get_semantic_boundaries(segments, target_k)
    
    ollama_online = check_ollama_available(ollama_url)
    
    topics = []
    for idx, b in enumerate(boundaries):
        block_segments = segments[b["start_segment"]:b["end_segment"]+1]
        block_text = " ".join([s.get("text", "") for s in block_segments])
        
        title = None
        if ollama_online:
            title = label_segment_with_llama(block_text[:3000], ollama_url)
        
        if not title:
            # Pass idx so generic Hindi fallback titles are unique (prevents merging)
            title = label_segment_heuristic(block_text, segment_index=idx)
            
        topics.append({
            "title": title,
            "start_segment": b["start_segment"],
            "end_segment": b["end_segment"],
            "original_language": lang_code
        })
        
    refined_topics = refine_topics(topics)
    print(f"[LearnForge API] Refined topics count from {len(topics)} to {len(refined_topics)}.")
    print(f"[LearnForge API] Generated {len(refined_topics)} unique Knowledge Units successfully.")
    return refined_topics

def refine_topics(topics, merge_consecutive=True):
    if not topics:
        return []
        
    # Step 1: Clean and truncate each title to maximum 5 words
    for t in topics:
        title = t["title"]
        title = title.replace('"', '').replace("'", "").strip()
        
        # Clean trailing filler words and phrases (e.g. "Core Code Implementation - Okay")
        title = re.sub(r'\s*[-\s:._|–/]+\s*(okay|look|okay sorry|sorry|sir|basically|actually|right|uh|ah|um|you know)\b.*$', '', title, flags=re.I)
        title = re.sub(r'\b(okay|look|sorry|sir)\s*$', '', title, flags=re.I).strip()

        # Clean suffixes like " (Part X)", " Part X", " Continued", etc.
        title = re.sub(r'\s*\(\s*Part\s*\d+\s*\)\s*$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s+Part\s+\d+\s*$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s+Continued\s*$', '', title, flags=re.IGNORECASE)
        title = title.strip()
        
        # Clean trailing separators before and after word truncation
        title = re.sub(r'\s*[-\s:._|–/]+$', '', title).strip()
        
        # Truncate to maximum 5 words
        words = title.split()
        if len(words) > 5:
            title = " ".join(words[:5])
            
        # Clean trailing separators again after truncation
        title = re.sub(r'\s*[-\s:._|–/]+$', '', title).strip()
        
        t["title"] = title

    # Generic/numbered fallback titles (e.g. "Concept Explanation 3") must NOT be merged
    # even if somehow two consecutive segments share the same generic label.
    # Generic/numbered titles that must never be merged even if text matches
    GENERIC_TITLE_PREFIXES = ("concept explanation", "core concept", "segment ")

    # Step 2: Merge consecutive topics that have the same title (case-insensitive)
    refined = []
    for t in topics:
        if not t["title"]:
            t["title"] = "Concept Explanation"

        title_lower = t["title"].lower()
        # Never merge generic/numbered fallback titles — each is its own segment
        is_generic = any(title_lower.startswith(p) for p in GENERIC_TITLE_PREFIXES)

        # Merge if consecutive and have the exact same title, but NOT generic titles
        if (refined and not is_generic
                and refined[-1]["title"].lower() == title_lower):
            refined[-1]["end_segment"] = max(refined[-1]["end_segment"], t["end_segment"])
        else:
            refined.append(t)
            
    # Step 3: Check for non-consecutive duplicates and differentiate them
    seen_titles = {}
    for idx, t in enumerate(refined):
        title = t["title"]
        title_lower = title.lower()
        if title_lower in seen_titles:
            seen_titles[title_lower].append(idx)
        else:
            seen_titles[title_lower] = [idx]
            
    # Differentiate duplicate titles (e.g. Part 2)
    for title_lower, indices in seen_titles.items():
        if len(indices) > 1:
            base_display_title = refined[indices[0]]["title"]
            for dup_count, idx in enumerate(indices):
                if dup_count > 0:
                    refined[idx]["title"] = f"{base_display_title} (Part {dup_count + 1})"
                    
    return refined


def split_long_topics(topics, segments, lang_code, ollama_url):
    """
    Sub-segment long coarse topics into finer subtopics dynamically.
    For any topic longer than 150 seconds, use semantic boundaries to split.
    """
    if not topics or not segments:
        return topics

    ollama_online = check_ollama_available(ollama_url)

    refined = []
    global_sub_idx = 0  # unique index across all subtopics to prevent merging
    for topic in topics:
        start_idx = topic["start_segment"]
        end_idx = topic["end_segment"]
        
        # Calculate duration of this topic
        start_time = segments[start_idx]["start"]
        end_time = segments[end_idx]["end"]
        duration = end_time - start_time
        
        # If topic is longer than 150 seconds and has enough segments, split it
        if duration > 150 and (end_idx - start_idx) > 8:
            sub_k = max(2, min(5, int(duration // 80)))
            print(f"[LearnForge API] Sub-segmenting topic '{topic['title']}' ({int(duration)}s) into {sub_k} subtopics...")
            
            sub_segments = segments[start_idx:end_idx+1]
            boundaries = get_semantic_boundaries(sub_segments, sub_k)
            
            for sub_b_idx, sub_b in enumerate(boundaries):
                g_start = start_idx + sub_b["start_segment"]
                g_end = start_idx + sub_b["end_segment"]
                
                sub_text = " ".join([s.get("text", "") for s in segments[g_start:g_end+1]])
                title = None
                if ollama_online:
                    title = label_segment_with_llama(sub_text[:3000], ollama_url)
                if not title:
                    title = label_segment_heuristic(sub_text, segment_index=global_sub_idx)
                
                # Format subtopic title — always include Part number so each is unique
                generic_prefixes = ("core concept", "concept explanation")
                title_lower = title.lower()
                if any(title_lower.startswith(p) for p in generic_prefixes):
                    title = f"Segment {global_sub_idx + 1}"
                else:
                    title = f"{title} (Part {sub_b_idx + 1})"
                
                refined.append({
                    "title": title,
                    "start_segment": g_start,
                    "end_segment": g_end,
                    "original_language": lang_code
                })
                global_sub_idx += 1
        else:
            refined.append(topic)
            global_sub_idx += 1
            
    return refine_topics(refined, merge_consecutive=False)
