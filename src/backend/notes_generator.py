"""
notes_generator.py — Multi-stage Knowledge Pipeline

Stage 1: Translate (if Hindi) → clean filler → declarative language
Stage 2: extract_knowledge_units() → typed sentence buckets
Stage 3: build_structured_notes() → What is it / Why / How / Example / Key Terms
Stage 4: build_quick_revision_30s() → 30-second revision sheet

Nothing from the transcript is pasted directly.
"""
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

import os
import json
import requests
import re
from collections import Counter
try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
        HAS_SPACY = True
    except OSError:
        HAS_SPACY = False
except ImportError:
    HAS_SPACY = False
from dotenv import load_dotenv
from ollama_health import check_ollama_available
from translator import translate_to_english, detect_language, make_cache_path
from cleaner import clean_transcript_spacy
from extractor import (
    extract_knowledge_units,
    build_structured_notes,
    build_quick_revision_30s,
    remove_filler,
    compute_tfidf_weights,
    rank_sentences_by_tfidf,
    _deduplicate,
    _rank_by_density,
    populate_legacy_keys_on_knowledge,
    build_notes_from_knowledge,
)

# Load .env variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:1b"


def _safe(text, limit=300):
    return str(text)[:limit].encode('ascii', errors='replace').decode('ascii')


# ── Per-topic generation ───────────────────────────────────────────────────────

def generate_notes_for_single_topic(
    video_id: str, topic_index: int, storage_dir: str,
    ollama_url: str = OLLAMA_URL,
) -> dict:
    """
    Generate DETAILED + REVISION notes for ONE topic.
    Cache: notes_cache/topic_N.json and notes_cache/topic_N_knowledge.json
    Returns: { topic, topic_index, detailed: {...}, revision: {...} }
    """
    video_dir = os.path.join(storage_dir, video_id)
    cache_dir = os.path.join(video_dir, "notes_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"topic_{topic_index}.json")
    knowledge_cache_path = os.path.join(cache_dir, f"topic_{topic_index}_knowledge.json")

    # Load topics.json for metadata (needed for titles and linking)
    topics_path = os.path.join(video_dir, "topics.json")
    topics_list = []
    if os.path.exists(topics_path):
        try:
            with open(topics_path, encoding='utf-8') as f:
                topics_list = json.load(f)
        except Exception:
            pass

    # If the notes cache exists, load it
    if os.path.exists(cache_path):
        with open(cache_path, encoding='utf-8') as f:
            cached = json.load(f)
        # Migrate old flat format to new sectioned format
        if "detailed" not in cached or "what_is_it" not in cached.get("detailed", {}) or "common_mistakes" not in cached.get("detailed", {}):
            cached = _migrate_old_cache(cached)
        return cached

    # Load topic_title and text
    if not topics_list or topic_index >= len(topics_list):
        return _fallback(f"Topic {topic_index + 1}", topic_index)
        
    t = topics_list[topic_index]
    topic_title = t.get("title", f"Topic {topic_index + 1}")
    topic_id = f"topic_{topic_index}"
    
    topic_text = t.get("content", "")
    if not topic_text:
        chunks_path = os.path.join(video_dir, "chunks.json")
        if os.path.exists(chunks_path):
            with open(chunks_path, encoding='utf-8') as f:
                chunks = json.load(f)
            topic_text = " ".join(
                c.get("text", "") for c in chunks if c.get("topic_id") == topic_id
            ).strip()

    print(f"[LearnForge Notes] [{topic_index}] '{_safe(topic_title, 60)}' | {len(topic_text)} chars")

    # Load from knowledge.json cache if exists
    if os.path.exists(knowledge_cache_path):
        print(f"[LearnForge Notes] [{topic_index}] Loading Knowledge from cache...")
        with open(knowledge_cache_path, encoding='utf-8') as f:
            knowledge = json.load(f)
        knowledge = populate_legacy_keys_on_knowledge(knowledge)
        
        # Build notes from knowledge
        detailed = build_notes_from_knowledge(knowledge, topic_title)
        revision = build_quick_revision_30s(detailed, topic_title)
        result = {
            "topic": topic_title,
            "topic_index": topic_index,
            "summary": detailed.get("summary", ""),
            "key_points": detailed.get("key_points", []),
            "important_terms": knowledge.get("keywords", []),
            "markdown": detailed.get("markdown", ""),
            "detailed": detailed,
            "revision": revision,
            "density": detailed.get("density", "Light"),
            "density_badge": detailed.get("density_badge", "🟢 Light")
        }
    else:
        # Generate new result and cache knowledge
        result = _run_pipeline(topic_title, topic_id, topic_text, topic_index, video_dir, ollama_url)

    if topics_list:
        result = apply_cross_topic_linking(topic_index, result, topics_list)

    with open(cache_path, "w", encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result


def _enforce_context_budget(text: str, max_chars: int = 8000) -> str:
    """
    PPT Context Budget Enforcer — limits input to the LLM to max_chars.
    Splits at sentence boundaries to avoid cutting mid-sentence.
    When text is long (e.g. 14k+ chars), returns the most content-dense portion.
    """
    if not text or len(text) <= max_chars:
        return text

    # Try to cut at a sentence boundary
    cut = text[:max_chars]
    # Walk back to last sentence terminator
    last_stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind(".\n"))
    if last_stop > max_chars // 2:
        cut = cut[:last_stop + 1]

    return cut.strip()


def extract_knowledge_units_multi_window(cleaned: str, topic_title: str, corpus: list = None) -> dict:
    """
    Extract knowledge units over multiple overlapping windows for long topics.
    """
    if len(cleaned) <= 8000:
        return extract_knowledge_units(cleaned, topic_title, corpus=corpus)
        
    # Split into overlapping windows (~4000 chars size, ~1000 chars overlap)
    sentences = re.split(r'(?<=[.!?।])\s+|\n+', cleaned)
    windows = []
    current_window = []
    current_len = 0
    
    i = 0
    while i < len(sentences):
        sent = sentences[i]
        current_window.append(sent)
        current_len += len(sent) + 1
        
        if current_len >= 4000 or i == len(sentences) - 1:
            windows.append(" ".join(current_window))
            if i == len(sentences) - 1:
                break
            # Overlap backtrack
            overlap_len = 0
            overlap_sentences = []
            for sj in reversed(current_window):
                overlap_sentences.append(sj)
                overlap_len += len(sj) + 1
                if overlap_len >= 1000:
                    break
            current_window = list(reversed(overlap_sentences))
            current_len = overlap_len
        i += 1
        
    # Extract on each window
    window_results = []
    for w in windows:
        res = extract_knowledge_units(w, topic_title, corpus=corpus)
        window_results.append(res)
        
    if not window_results:
        return extract_knowledge_units(cleaned, topic_title, corpus=corpus)
        
    # Merge buckets
    merged = {
        'definitions': [], 'procedures': [], 'examples': [], 'features': [],
        'comparisons': [], 'important': [], 'steps': [], 'analogies': [],
        'misconceptions': [], 'ranked_general': [], 'terms': [], 'years': [],
        
        # New conceptual keys
        'commands': [], 'formulas': [], 'warnings': [], 'best_practices': [],
        'interview_questions': [], 'keywords': [], 'code': [], 'output': []
    }
    
    for r in window_results:
        for k in merged.keys():
            merged[k].extend(r.get(k, []))
            
    # Deduplicate and sort/rank terms
    term_counts = Counter(merged['terms'])
    top_terms = [t for t, _ in term_counts.most_common(12)]
    
    # Re-calculate TF-IDF over full sentences list
    tfidf_dict = compute_tfidf_weights(sentences, corpus)
    
    # Rank and deduplicate buckets
    merged_definitions = rank_sentences_by_tfidf(merged['definitions'], tfidf_dict)
    merged_procedures = rank_sentences_by_tfidf(merged['procedures'], tfidf_dict)
    merged_examples = rank_sentences_by_tfidf(merged['examples'], tfidf_dict)
    merged_features = rank_sentences_by_tfidf(merged['features'], tfidf_dict)
    merged_comparisons = rank_sentences_by_tfidf(merged['comparisons'], tfidf_dict)
    merged_important = rank_sentences_by_tfidf(merged['important'], tfidf_dict)
    merged_steps = rank_sentences_by_tfidf(merged['steps'], tfidf_dict)
    merged_analogies = rank_sentences_by_tfidf(merged['analogies'], tfidf_dict)
    merged_misconceptions = rank_sentences_by_tfidf(merged['misconceptions'], tfidf_dict)
    
    ranked_general = _rank_by_density(merged['ranked_general'], tfidf_dict)
    
    res = {
        'definitions': _deduplicate(merged_definitions)[:5],
        'procedures': _deduplicate(merged_procedures)[:6],
        'examples': _deduplicate(merged_examples)[:3],
        'features': _deduplicate(merged_features)[:4],
        'comparisons': _deduplicate(merged_comparisons)[:3],
        'important': _deduplicate(merged_important)[:4],
        'steps': _deduplicate(merged_steps)[:6],
        'analogies': _deduplicate(merged_analogies)[:3],
        'misconceptions': _deduplicate(merged_misconceptions)[:4],
        'ranked_general': ranked_general[:8],
        'terms': top_terms,
        'topic_title': topic_title,
        'ranked_sentences': ranked_general[:8],
        'years': list(set(merged['years'])),
        'year_sentences': [],
        'definition_sentences': merged_definitions,
        'all_sentences': sentences,
        'has_terms': bool(top_terms),
        'is_rich': len(merged_definitions) > 0 or len(ranked_general) > 2,
        
        # New conceptual lists
        'commands': _deduplicate(merged['commands'])[:4],
        'formulas': _deduplicate(merged['formulas'])[:3],
        'warnings': _deduplicate(merged['warnings'])[:3],
        'best_practices': _deduplicate(merged['best_practices'])[:3],
        'interview_questions': _deduplicate(merged['interview_questions'])[:3],
        'keywords': top_terms,
        'code': _deduplicate(merged['code'])[:3],
        'output': _deduplicate(merged['output'])[:3],
    }
    
    from extractor import populate_legacy_keys_on_knowledge
    return populate_legacy_keys_on_knowledge(res)


def apply_cross_topic_linking(current_idx: int, current_result: dict, topics: list) -> dict:
    """
    Scan for terms appearing in other topics and add cross-reference footers to bullets.
    """
    if not topics or len(topics) <= 1:
        return current_result
        
    detailed = current_result.get("detailed", {})
    key_points = detailed.get("key_points", [])
    markdown = detailed.get("markdown", "")
    terms = detailed.get("important_terms", [])
    
    if not terms:
        return current_result
        
    other_topics = []
    for other_idx, t in enumerate(topics):
        if other_idx == current_idx:
            continue
        title = t.get("title", "")
        if title:
            other_topics.append({
                "idx": other_idx,
                "title": title,
                "normalized_title": title.lower()
            })
            
    # Link bullets in key_points
    linked_points = []
    for kp in key_points:
        linked_kp = kp
        links_added = []
        for term in terms:
            if len(term) < 3:
                continue
            if term.lower() in kp.lower():
                for ot in other_topics:
                    if term.lower() in ot["normalized_title"] and ot["idx"] not in links_added:
                        linked_kp += f" (→ also covered in Topic {ot['idx'] + 1}: {ot['title']})"
                        links_added.append(ot["idx"])
                        break
        linked_points.append(linked_kp)
        
    # Link bullets in markdown
    md_lines = []
    for line in markdown.splitlines():
        if line.strip().startswith("- ") or line.strip().startswith("* "):
            linked_line = line
            links_added = []
            for term in terms:
                if len(term) < 3:
                    continue
                if term.lower() in line.lower():
                    for ot in other_topics:
                        if term.lower() in ot["normalized_title"] and ot["idx"] not in links_added:
                            linked_line += f" (→ also covered in Topic {ot['idx'] + 1}: {ot['title']})"
                            links_added.append(ot["idx"])
                            break
            md_lines.append(linked_line)
        else:
            md_lines.append(line)
            
    detailed["key_points"] = linked_points
    detailed["markdown"] = "\n".join(md_lines)
    current_result["key_points"] = linked_points
    current_result["markdown"] = detailed["markdown"]
    current_result["detailed"] = detailed
    
    return current_result


def _run_pipeline(topic_title, topic_id, topic_text, topic_index, video_dir, ollama_url):
    """
    Generate knowledge first, cache it, and then build study notes from it.
    """
    knowledge = _run_pipeline_for_knowledge(topic_title, topic_id, topic_text, topic_index, video_dir, ollama_url)
    
    # Save the knowledge cache
    cache_dir = os.path.join(video_dir, "notes_cache")
    os.makedirs(cache_dir, exist_ok=True)
    knowledge_cache_path = os.path.join(cache_dir, f"topic_{topic_index}_knowledge.json")
    with open(knowledge_cache_path, "w", encoding='utf-8') as f:
        json.dump(knowledge, f, indent=2, ensure_ascii=False)

    detailed = build_notes_from_knowledge(knowledge, topic_title)
    revision = build_quick_revision_30s(detailed, topic_title)

    result = {
        "topic": topic_title,
        "topic_index": topic_index,
        "summary": detailed.get("summary", ""),
        "key_points": detailed.get("key_points", []),
        "important_terms": knowledge.get("keywords", []),
        "markdown": detailed.get("markdown", ""),
        "detailed": detailed,
        "revision": revision,
        "density": detailed.get("density", "Light"),
        "density_badge": detailed.get("density_badge", "🟢 Light")
    }
    
    return result


def _run_pipeline_for_knowledge(topic_title, topic_id, topic_text, topic_index, video_dir, ollama_url):
    """
    Full extraction pipeline that outputs a unified Knowledge Layer schema dict.
    """
    from extractor import _empty_knowledge, populate_legacy_keys_on_knowledge

    if not topic_text or len(topic_text.strip()) < 30:
        return populate_legacy_keys_on_knowledge(_empty_knowledge(topic_title))

    # Load all topic contents to act as corpus for TF-IDF
    topics_path = os.path.join(video_dir, "topics.json")
    corpus = None
    if os.path.exists(topics_path):
        try:
            with open(topics_path, encoding='utf-8') as f:
                topics_list = json.load(f)
            corpus = [t.get("content", "") for t in topics_list if t.get("content", "")]
        except Exception:
            pass

    # ── Step 1: Translate if Hindi ────────────────────────────────────────────
    lang = detect_language(topic_text)
    print(f"[LearnForge Notes]    lang={lang}")

    if lang in ('hi', 'mix'):
        cache_path = make_cache_path(video_dir, topic_id)
        english_text = translate_to_english(topic_text, cache_path=cache_path, label=f"[{topic_id}]")
        print(f"[LearnForge Notes]    translated: {_safe(english_text, 200)}")
    else:
        english_text = topic_text

    if not english_text or len(english_text.strip()) < 20:
        return populate_legacy_keys_on_knowledge(_empty_knowledge(topic_title))

    # ── Step 2: Remove filler (using spaCy NLP cleaner) ───────────────────────
    cleaned = clean_transcript_spacy(english_text)
    print(f"[LearnForge Notes]    cleaned: {len(english_text)}->{len(cleaned)} chars | preview: {_safe(cleaned, 200)}")

    # Budget input to 8000 chars for technical classification and LLM extraction
    llm_input_text = _enforce_context_budget(cleaned, max_chars=8000)

    # ── Step 3: Deterministic Keywords & Technical Routing ────────────────────
    key_terms = extract_deterministic_keywords(llm_input_text)
    print(f"[LearnForge Notes] [{topic_index}] Deterministic key terms: {key_terms}")
    
    gemini_key = os.environ.get("GEMINI_API_KEY")
    routing_metadata = llama_metadata_router(llm_input_text, gemini_key=gemini_key, ollama_url=ollama_url)
    print(f"[LearnForge Notes] [{topic_index}] Routing metadata: {routing_metadata}")
    
    # Strictly non-technical or conversational overview chunk
    if not routing_metadata.get("is_technical") or len(llm_input_text) < 500:
        print(f"[LearnForge Notes] [{topic_index}] Flagged as conversational/non-technical. Generating conversational outline.")
        
        summary_text = f"This segment outlines conversational remarks, course pacing orientation, or general overview of {topic_title}."
        k = _empty_knowledge(topic_title)
        k["concept"] = topic_title
        k["definition"] = summary_text
        k["explanation"] = "The instructor introduces the foundational context and outlines the course structure or upcoming concepts. No direct technical implementation steps or terminal commands are performed in this introductory block."
        k["applications"] = ["Understanding high-level outline and context."]
        k["warnings"] = ["Assuming technical configurations are performed in this conversational section."]
        k["interview_questions"] = [f"What is the primary theme or introductory context covered in this segment?"]
        k["keywords"] = key_terms if key_terms else ["Introduction"]
        return populate_legacy_keys_on_knowledge(k)

    # ── Step 4: Technical extraction ──────────────────────────────────────────
    knowledge = None
    ollama_online = check_ollama_available(ollama_url)

    if gemini_key and len(llm_input_text) > 80:
        print(f"[LearnForge Notes] Calling Gemini knowledge extraction for [{topic_index}]...")
        knowledge = _call_llm_to_extract_knowledge(topic_title, llm_input_text, gemini_key=gemini_key)
        
    if not knowledge and ollama_online and len(llm_input_text) > 80:
        print(f"[LearnForge Notes] Calling Ollama knowledge extraction for [{topic_index}]...")
        knowledge = _call_llm_to_extract_knowledge(topic_title, llm_input_text, ollama_url=ollama_url)

    # ── Step 5: Heuristic extraction fallback ─────────────────────────────────
    if not knowledge:
        print(f"[LearnForge Notes] Falling back to Heuristic extraction for [{topic_index}]...")
        knowledge = extract_knowledge_units_multi_window(cleaned, topic_title, corpus=corpus)

    # Ensure deterministic keywords are mapped
    knowledge["keywords"] = key_terms
    knowledge["terms"] = key_terms

    return populate_legacy_keys_on_knowledge(knowledge)


def _call_llm_to_extract_knowledge(topic_title: str, cleaned_text: str, gemini_key: str = None, ollama_url: str = None) -> dict:
    """
    Three-pass LLM pipeline that extracts the exact Knowledge Layer JSON schema.
    """
    # Step 1: Cleaning Agent
    cleaning_prompt = f"""You are a transcript cleaning assistant.
Your job is to clean this transcript section for educational study notes.
- Remove YouTube filler words, announcements, sponsor slots, subscribe requests, greetings (e.g., "Hello everyone", "Welcome back", "Subscribe to the channel").
- Remove conversational filler words and spoken narration (e.g., "okay", "uh", "all right", "you know", "let's see", "one second", "now let's go here", "let's start", "I am going to").
- Convert spoken conversational cues to clean declarative instructions.
  Example: "okay so now let's go to urls.py" -> "Go to urls.py."
- Keep ONLY clean educational facts, concepts, explanations, and instructions.
- Convert all first-person speech ("I", "we", "my", "we", "us", "our", "let's") or second-person speech ("you") to objective, third-person statements.

Topic: {topic_title}
Transcript chunk:
{cleaned_text[:3500]}

Return ONLY the cleaned educational text, maintaining the factual information without conversational fillers or spoken narration. Do not include markdown formatting or warnings."""

    if gemini_key:
        raw_cleaned = _call_gemini_raw(cleaning_prompt, gemini_key, json_mode=False)
    elif ollama_url:
        raw_cleaned = _call_ollama_raw(cleaning_prompt, ollama_url, json_mode=False)
    else:
        return None

    if not raw_cleaned or len(raw_cleaned.strip()) < 20:
        print("[LearnForge Notes] Cleaning Agent failed or returned empty text.")
        raw_cleaned = cleaned_text

    # Step 2: Knowledge Extraction Agent
    extraction_prompt = f"""You are an educational knowledge extraction engine.
Your task is to convert this free-form educational text into structured concepts and facts.
Do NOT summarize yet. Just extract the facts and entities as they are described.
Do NOT assume or invent any facts or patterns not explicitly present in the text.
Strict Third-Person Objective Voice Only: Rewrite concepts and sentences in objective, third-person voice. Do NOT include first-person terms ("I", "we", "my", "our", "us") in any extracted concepts, definitions, examples, or mistakes.

Educational Text:
{raw_cleaned}

Return ONLY a JSON object with this exact structure (no markdown wrapper, no other text):
{{
  "concept": "{topic_title}",
  "definition": "A formal, clear textbook definition of the concept",
  "explanation": "Detailed explanation of the concept's core principles and working mechanism",
  "analogy": "A memorable real-world analogy to help explain the concept",
  "examples": ["List of practical examples or use cases mentioned"],
  "procedures": ["List of step-by-step implementation procedures or steps"],
  "misconceptions": ["List of misconceptions or what the concept is NOT"],
  "applications": ["List of features, advantages, or practical applications"],
  "commands": ["List of terminal commands or setup commands"],
  "formulas": ["List of mathematical formulas or equations if any"],
  "warnings": ["List of warnings, common mistakes, or pitfalls"],
  "best_practices": ["List of best practices or key takeaways"],
  "interview_questions": ["2-3 interview-style review questions on this concept"],
  "keywords": ["List of key noun technical terms (keywords)"],
  "code": ["List of code snippets or code blocks"],
  "output": ["Expected outputs of code/commands if mentioned"],
  "summary": "A 1-2 sentence high-level summary of the entire concept"
}}"""

    if gemini_key:
        raw_pass1 = _call_gemini_raw(extraction_prompt, gemini_key, json_mode=True)
    elif ollama_url:
        raw_pass1 = _call_ollama_raw(extraction_prompt, ollama_url, json_mode=True)
    else:
        return None

    if not raw_pass1:
        return None

    # Parse JSON from Pass 1
    extracted_knowledge = None
    for match in re.finditer(r'\{', raw_pass1):
        try:
            candidate = raw_pass1[match.start():]
            extracted_knowledge = json.loads(candidate[:candidate.rfind('}') + 1])
            break
        except Exception:
            continue

    if not extracted_knowledge:
        print(f"[LearnForge Notes] Failed to parse Knowledge Extraction JSON: {raw_pass1[:200]}")
        return None

    # Step 3: Teacher Agent (Refinement)
    teacher_prompt = f"""# Role and Objective
You are the AI engine refine raw knowledge units extracted from a lecture transcript into a perfect, textbook-quality structured Knowledge Layer JSON payload.

# Style and Quality Rules
- **Third-Person Objective Voice Only:** Never use "I", "me", "my", "you", "we", "us", "let's", or "the instructor". Rewrite all actions objectively (e.g., instead of "I'll open VS Code", write "Open the project folder in Visual Studio Code").
- **Zero Transcript Leakage:** Never copy raw conversational stumbles or self-promotional pitches.
- **High-Density Technical Rephrasing:** Turn messy spoken explanations into polished, professional textbook-quality prose.
- **Strict Truthfulness:** Only include facts, steps, code, or examples that are actually present or described in the structured knowledge. Do NOT invent new commands, code, or APIs.

Extracted Knowledge:
{json.dumps(extracted_knowledge, indent=2)}

Return ONLY a JSON object with this exact structure (no markdown wrapper, no other text):
{{
  "concept": "{topic_title}",
  "definition": "Formal definition of the concept",
  "explanation": "Detailed explanation of the concept's core principles",
  "analogy": "Memorable real-world analogy",
  "examples": ["Example 1", "Example 2"],
  "procedures": ["Step 1", "Step 2"],
  "misconceptions": ["Misconception 1", "Misconception 2"],
  "applications": ["Application 1", "Application 2"],
  "commands": ["command 1", "command 2"],
  "formulas": ["formula 1"],
  "warnings": ["warning/pitfall 1"],
  "best_practices": ["best practice 1"],
  "interview_questions": ["Question 1", "Question 2"],
  "keywords": ["Keyword1", "Keyword2"],
  "code": ["code block 1"],
  "output": ["output 1"],
  "summary": "1-2 sentence high-level summary"
}}"""

    if gemini_key:
        raw_pass2 = _call_gemini_raw(teacher_prompt, gemini_key, json_mode=True)
    elif ollama_url:
        raw_pass2 = _call_ollama_raw(teacher_prompt, ollama_url, json_mode=True)
    else:
        return None

    if not raw_pass2:
        return None

    # Parse JSON from Pass 2
    final_knowledge = None
    for match in re.finditer(r'\{', raw_pass2):
        try:
            candidate = raw_pass2[match.start():]
            final_knowledge = json.loads(candidate[:candidate.rfind('}') + 1])
            break
        except Exception:
            continue

    if not final_knowledge:
        print(f"[LearnForge Notes] Failed to parse Teacher Agent Refinement JSON: {raw_pass2[:200]}")
        return None

    return final_knowledge

    print(f"[LearnForge Notes]    heuristic: {len(detailed['key_points'])} key points, {len(detailed['important_terms'])} terms")

    result = {
        "topic": topic_title,
        "topic_index": topic_index,
        "summary": detailed.get("summary", ""),
        "key_points": detailed.get("key_points", []),
        "important_terms": key_terms,
        "markdown": detailed.get("markdown", ""),
        "detailed": detailed,
        "revision": revision,
        "density": detailed.get("density", "Light"),
        "density_badge": detailed.get("density_badge", "🟢 Light")
    }
    
    if topics_list:
        result = apply_cross_topic_linking(topic_index, result, topics_list)
        
    return result


def extract_deterministic_keywords(transcript_text: str, top_n=8) -> list:
    """
    Extracts high-value technical nouns and proper nouns completely 
    without an LLM, ensuring 100% truthfulness to the text.
    """
    if not transcript_text:
        return []
        
    if not HAS_SPACY:
        # Fallback keyword extraction using regex/split
        words = re.findall(r'\b[a-zA-Z]{3,}\b', transcript_text.lower())
        fillers = {"video", "course", "guys", "lecture", "tutorial", "topic", "sir", "okay", "sorry", "look", "like", "would", "about", "there", "their", "them"}
        filtered = [w.capitalize() for w in words if w not in fillers]
        return [word for word, count in Counter(filtered).most_common(top_n)]
        
    doc = nlp(transcript_text.lower())
    
    # Filter out common filler words and prioritize technical elements
    fillers = {"video", "course", "hey", "guys", "lecture", "tutorial", "topic", "sir", "okay", "sorry", "look"}
    keywords = []
    for token in doc:
        if token.pos_ in ["NOUN", "PROPN"] and token.text not in fillers and len(token.text) > 2:
            keywords.append(token.text.capitalize())
            
    return [word for word, count in Counter(keywords).most_common(top_n)]


def llama_metadata_router(text: str, gemini_key: str = None, ollama_url: str = None) -> dict:
    """
    Query the LLM to classify if the transcript segment is technical
    and identify its primary language/framework and confidence score.
    Returns: { "is_technical": bool, "primary_language_or_framework": str, "confidence_score": float }
    """
    prompt = f"""You are a semantic routing engine. Analyze this transcript segment and categorize its structural payload.
    
    Transcript:
    {text[:3000]}
    
    Return ONLY a JSON object with this exact structure (no markdown wrapper, no other text):
    {{
      "is_technical": true,
      "primary_language_or_framework": "Django",
      "confidence_score": 0.95
    }}
    
    Rules:
    - Set is_technical to true if code, syntax, or core software engineering concepts are actively taught or discussed. Set it to false if it is just greetings, chatting, pacing orientation, general channel updates, or personal discussion.
    - Set primary_language_or_framework to the main software tool/language (e.g. 'Django', 'React', 'Git', 'Docker'). If it is purely conversational or intro, write 'Pure Discussion'.
    - Set confidence_score to a float between 0.0 and 1.0.
    """
    
    # Try calling LLM (Gemini or Ollama)
    raw_res = None
    if gemini_key:
        raw_res = _call_gemini_raw(prompt, gemini_key, json_mode=True)
    elif ollama_url:
        raw_res = _call_ollama_raw(prompt, ollama_url, json_mode=True)
        
    # Default fallback routing
    fallback_res = {
        "is_technical": True,  # Default to technical to prevent false N/As if offline
        "primary_language_or_framework": "Unknown",
        "confidence_score": 0.5
    }
    
    if not raw_res:
        return fallback_res
        
    # Parse JSON
    for match in re.finditer(r'\{', raw_res):
        try:
            candidate = raw_res[match.start():]
            data = json.loads(candidate[:candidate.rfind('}') + 1])
            # Validate keys
            if "is_technical" in data:
                return {
                    "is_technical": bool(data.get("is_technical")),
                    "primary_language_or_framework": str(data.get("primary_language_or_framework", "Unknown")),
                    "confidence_score": float(data.get("confidence_score", 0.5))
                }
        except Exception:
            continue
            
    return fallback_res


def is_banter_or_empty_chunk(text: str) -> bool:
    """
    Checks if a transcript chunk is short or contains conversational/vlogging banter
    without technical programming or configurations.
    """
    if not text:
        return True
    
    # Threshold 1: If fewer than 600 characters
    if len(text) < 600:
        return True
        
    text_lower = text.lower()
    
    # High-frequency interview/vlog filler keywords
    vlog_words = ["welcome", "subscribe", "channel", "everyone", "hello", "video", "course", "tutorial", "like share", "comment below"]
    # Code/technical formatting keywords
    tech_keywords = [
        "class", "def ", "function", "import", "from ", "const ", "let ", "var ", 
        "return", "pip", "python", "npm", "git", "run", "command", "api", 
        "serializers", "model", "url", "route", "database", "table", "postman", 
        "django", "react", "html", "css", "docker", "deploy", "config", "install",
        "generic", "viewset", "apiview", "token", "jwt"
    ]
    
    has_vlog = any(vw in text_lower for vw in vlog_words)
    has_tech = any(tk in text_lower for tk in tech_keywords)
    
    if has_vlog and not has_tech:
        return True
        
    return False


def _call_llm_banter_prompt(topic_title: str, cleaned_text: str, topic_index: int, gemini_key: str = None, ollama_url: str = None):
    """
    Simpler prompt layout designed specifically for empty or banter/introductory segments.
    Strictly yields N/A for code/procedural blocks.
    """
    prompt = f"""# Role and Objective
You are an adaptive educational parsing engine. Your job is to extract technical training notes from a raw transcript.

# Strict Truthfulness Rules
- **The Empty Content Rule:** If a specific section (like Code, Commands, or Implementation Steps) contains no actual developer actions or technical code execution in the transcript, you MUST write "N/A - This segment is an conversational discussion/introduction."
- Do NOT make up steps, do NOT guess instructions based on the title, and do NOT turn a casual question into an implementation configuration rule.

Transcript text:
{cleaned_text[:3000]}

Return ONLY a JSON object with this exact structure (no markdown wrapper, no other text):
{{
  "detailed": {{
    "summary": "2-3 educational sentences explaining what this conversational/introductory segment discusses.",
    "markdown": "### Course Discussion\\n- This segment covers conversational remarks, course pacing orientation, or a general introduction to the topic of {topic_title}.\\n- The instructor outlines the context and structure of upcoming concepts.\\n- No direct technical implementation steps or terminal commands are performed in this introductory block.\\n\\n### 🧠 Concept Check & Review\\nQuestion 1: What general overview or introductory context was introduced regarding {topic_title}?",
    "sections": [
      {{
        "title": "Concept",
        "icon": "📌",
        "content": ["Outline of the introductory context or conversational details discussed in this video block."]
      }}
    ],
    "important_terms": ["Overview"]
  }},
  "revision": {{
    "definition": "Overview of {topic_title} introductory context.",
    "facts": ["This segment outlines foundational context for {topic_title}", "No code implementation or procedures are executed in this section"],
    "terms": ["Introduction"],
    "remember": "No code is implemented in this block"
  }}
}}"""

    if gemini_key:
        raw_res = _call_gemini_raw(prompt, gemini_key, json_mode=True)
    elif ollama_url:
        raw_res = _call_ollama_raw(prompt, ollama_url, json_mode=True)
    else:
        return None

    if not raw_res:
        return None

    return _parse_llm(raw_res, topic_title, topic_index)


# ── Two-Pass LLM Pipeline ────────────────────────────────────────────────────

def _call_gemini_raw(prompt: str, api_key: str, json_mode: bool = False) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    if json_mode:
        payload["generationConfig"] = {"responseMimeType": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=40)
        if resp.status_code == 200:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            print(f"[Gemini API] Error response: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[Gemini API] Exception calling Gemini: {e}")
    return ""


def _call_ollama_raw(prompt: str, ollama_url: str, json_mode: bool = False) -> str:
    try:
        payload = {"model": MODEL, "prompt": prompt, "stream": False}
        if json_mode:
            payload["format"] = "json"
        resp = requests.post(
            ollama_url,
            json=payload,
            timeout=40,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
    except Exception as e:
        print(f"[Ollama] Exception calling Ollama: {e}")
    return ""


def _call_llm_three_pass(topic_title: str, cleaned_text: str, topic_index: int, gemini_key: str = None, ollama_url: str = None):
    # Step 1: Cleaning Agent
    cleaning_prompt = f"""You are a transcript cleaning assistant.
Your job is to clean this transcript section for educational study notes.
- Remove YouTube filler words, announcements, sponsor slots, subscribe requests, greetings (e.g., "Hello everyone", "Welcome back", "Subscribe to the channel").
- Remove conversational filler words and spoken narration (e.g., "okay", "uh", "all right", "you know", "let's see", "one second", "now let's go here", "let's start", "I am going to").
- Convert spoken conversational cues to clean declarative instructions.
  Example: "okay so now let's go to urls.py" -> "Go to urls.py."
- Keep ONLY clean educational facts, concepts, explanations, and instructions.
- Convert all first-person speech ("I", "me", "my", "we", "us", "our", "let's") or second-person speech ("you") to objective, third-person statements.

Topic: {topic_title}
Transcript chunk:
{cleaned_text[:3500]}

Return ONLY the cleaned educational text, maintaining the factual information without conversational fillers or spoken narration. Do not include markdown formatting or warnings."""

    if gemini_key:
        raw_cleaned = _call_gemini_raw(cleaning_prompt, gemini_key, json_mode=False)
    elif ollama_url:
        raw_cleaned = _call_ollama_raw(cleaning_prompt, ollama_url, json_mode=False)
    else:
        return None

    if not raw_cleaned or len(raw_cleaned.strip()) < 20:
        print("[LearnForge Notes] Cleaning Agent failed or returned empty text.")
        raw_cleaned = cleaned_text

    # Step 2: Knowledge Extraction Agent
    extraction_prompt = f"""You are an educational knowledge extraction engine.
Your task is to convert this free-form educational text into structured concepts and facts.
Do NOT summarize yet. Just extract the facts and entities as they are described.
Do NOT assume or invent any facts or patterns not explicitly present in the text.
Strict Third-Person Objective Voice Only: Rewrite concepts and sentences in objective, third-person voice. Do NOT include first-person terms ("I", "we", "my", "our", "us") in any extracted concepts, definitions, examples, or mistakes.
If no commands, examples, or mistakes are discussed in the text, return empty lists [] for those fields.

Educational Text:
{raw_cleaned}

Return ONLY a JSON object with this exact structure (no markdown wrapper, no other text):
{{
  "topic": "{topic_title}",
  "concepts": ["Concept 1 Name", "Concept 2 Name"],
  "definitions": ["Definition 1", "Definition 2"],
  "examples": ["Example 1", "Example 2"],
  "commands": ["command/code snippet 1"],
  "mistakes": ["common mistake 1", "common mistake 2"],
  "future_topics": ["next topic/future concept 1"]
}}"""

    if gemini_key:
        raw_pass1 = _call_gemini_raw(extraction_prompt, gemini_key, json_mode=True)
    elif ollama_url:
        raw_pass1 = _call_ollama_raw(extraction_prompt, ollama_url, json_mode=True)
    else:
        return None

    if not raw_pass1:
        return None

    # Parse JSON from Pass 1
    extracted_knowledge = None
    for match in re.finditer(r'\{', raw_pass1):
        try:
            candidate = raw_pass1[match.start():]
            extracted_knowledge = json.loads(candidate[:candidate.rfind('}') + 1])
            break
        except Exception:
            continue

    if not extracted_knowledge:
        print(f"[LearnForge Notes] Failed to parse Knowledge Extraction JSON: {raw_pass1[:200]}")
        return None

    # Step 3: Teacher Agent
    teacher_prompt = f"""# Role and Objective
You are the AI engine behind a premium educational platform's study-guide feature. Your goal is to convert messy, raw lecture transcripts (represented here as structured knowledge units) into perfectly structured, textbook-quality "Detailed Notes".

# Strict Truthfulness Rules
- **The Empty Content Rule:** If a specific section (like Code, Commands, or Implementation Steps) contains no actual developer actions or technical code execution in the transcript, you MUST write "N/A - This segment is an conversational discussion/introduction."
- Do NOT make up steps, do NOT guess instructions based on the title, and do NOT turn a casual question into an implementation configuration rule.

# Style and Quality Rules (Strict Synthesis Penalties)
- **Third-Person Objective Voice Only:** Never use "I", "me", "my", "you", "we", "us", "let's", or "the instructor". Rewrite all actions objectively (e.g., instead of "I'll open VS Code", write "Open the project folder in Visual Studio Code" or "The developer opens Visual Studio Code").
- **Zero Transcript Leakage:** Never copy raw conversational stumbles, self-promotional pitches (like references to free courses or YouTube links), or broken sentences verbatim. 
- **High-Density Technical Rephrasing:** Turn messy spoken walkthroughs into polished, professional prose. Synthesize explanations clearly.
- **No Placeholders:** Never use placeholders or template strings. Generate actual questions based on the technical content.

Structured Knowledge:
{json.dumps(extracted_knowledge, indent=2)}

Rules for Sections:
- Dynamically select which sections to generate. Only include sections if they are supported by direct facts in the Structured Knowledge.
- Choose section titles ONLY from this allowed list:
   - "Definition"
   - "Concept"
   - "Steps"
   - "Code"
   - "Commands"
   - "Example"
   - "Installation"
   - "Configuration"
   - "Architecture"
   - "Advantages"
   - "Key Takeaways"
   - "Common Mistakes" (ONLY if mistakes are explicitly present in the Structured Knowledge)
   - "Interview Questions" (ONLY if explicitly supported by technical concepts or questions in the Structured Knowledge)
- Do NOT use a fixed template. If the knowledge only discusses installation, only generate the "Installation" and "Commands" or "Configuration" sections.
- For each section, provide a suitable emoji icon (e.g. 📌 for Definition, ⚙️ for Steps, 💻 for Code, ⚠️ for Common Mistakes, etc.).
- The content for each section must be a list of clear, educational, non-conversational sentences.
- The "revision" object must be strictly derived from the detailed notes sections, keeping it short, bulleted, and factual (maximum 150 words total, no examples or stories).

Return ONLY a JSON object with this exact structure (no markdown wrapper, no other text):
{{
  "detailed": {{
    "summary": "2-3 educational sentences explaining what this topic teaches",
    "markdown": "A comprehensive, highly detailed textbook-quality study guide in Markdown format. Follow these strict rules:\n- **Third-Person Objective Voice Only:** Never use 'I', 'me', 'my', 'you', 'we', 'us', or 'the instructor'. Rewrite all actions objectively.\n- **Zero Transcript Leakage:** Never copy raw conversational stumbles, self-promotional pitches, or broken sentences verbatim.\n- **High-Density Technical Rephrasing:** Turn messy spoken walkthroughs into polished, professional prose.\n- **Format Structure:**\n   1. Do NOT use rigid generic headers (like '📘 Segment Synthesis', 'Technical Procedures & Commands', 'Code & Terminal Commands'). Instead, use organic, concept-based headings (e.g. `### OOP Encapsulation` or `### Client-Server Request Cycle` or `### Commands & Setup`).\n   2. All explanatory text, concepts, steps, and procedures MUST be structured as clean, detailed, high-density bullet points (`-` or `*`).\n   3. Do NOT use numbered lists. Use bullet points for all sequential operations or setup steps.\n   4. Do NOT prefix bullet points with rigid template bold headers like `**Core Focus:**`, `**Context & Purpose:**`, or `**[Topic Title]:**`. Simply present direct, clear, professional sentences as bullet points.\n   5. If code blocks or terminal commands are mentioned, include them directly under the relevant descriptive headings using markdown fenced code blocks (e.g. ` ```bash ` or ` ```python `). If no code or commands are present, do NOT include any code block or 'N/A' placeholders.\n   6. The only standard section at the end is `### 🧠 Concept Check & Review` where you generate 2-3 high-quality academic review questions based strictly on the technical content (e.g., Question 1: [question], Question 2: [question]).",
    "sections": [
      {{
        "title": "Section Title",
        "icon": "emoji",
        "content": ["Sentence 1", "Sentence 2"]
      }}
    ],
    "important_terms": ["Term1", "Term2", "Term3"]
  }},
  "revision": {{
    "definition": "One-sentence exam-ready definition of the core concept (max 20 words)",
    "facts": ["5 to 8 exam-relevant factual bullets (max 12 words each, no examples or stories)"],
    "terms": ["3 to 5 keywords only"],
    "remember": "One memorable key takeaway or critical distinction (max 15 words)"
  }}
}}"""

    # Call LLM for Pass 3
    if gemini_key:
        raw_pass2 = _call_gemini_raw(teacher_prompt, gemini_key, json_mode=True)
    elif ollama_url:
        raw_pass2 = _call_ollama_raw(teacher_prompt, ollama_url, json_mode=True)
    else:
        return None

    if not raw_pass2:
        return None

    return _parse_llm(raw_pass2, topic_title, topic_index)


_GENERIC_PHRASES = [
    "foundational concepts", "best practices", "practical examples",
    "covers the core", "in this section", "this section covers",
    "let us", "we will", "key concepts", "overview of", "introduction to",
]


def _parse_llm(raw: str, topic_title: str, topic_index: int):
    """Extract and validate JSON from LLM response."""
    # Find JSON block
    for match in re.finditer(r'\{', raw):
        try:
            candidate = raw[match.start():]
            end = candidate.rfind('}')
            if end < 0:
                continue
            data = json.loads(candidate[:end + 1])
            detailed = data.get("detailed", {})
            revision = data.get("revision", {})
            summary = detailed.get("summary", "")

            # Reject if generic
            if any(p in summary.lower() for p in _GENERIC_PHRASES):
                return None

            sections = detailed.get("sections", [])
            if not summary or not sections:
                return None

            # Map dynamic sections to old flat keys for compatibility
            what_is_it = ""
            why_matters = ""
            how_it_works = []
            example = ""
            common_mistakes = []
            interview_questions = []
            key_points = []

            for sec in sections:
                title = sec.get("title", "")
                t_low = title.lower()
                content = sec.get("content", [])
                content_list = content if isinstance(content, list) else [content]
                content_str = " ".join(content_list)

                if "definition" in t_low or "concept" in t_low:
                    what_is_it = content_str
                elif "advantage" in t_low or "why matters" in t_low:
                    why_matters = content_str
                elif "step" in t_low or "how" in t_low or "install" in t_low or "config" in t_low or "setup" in t_low:
                    how_it_works = content_list
                elif "example" in t_low or "code" in t_low or "command" in t_low:
                    example = content_str
                elif "mistake" in t_low or "error" in t_low:
                    common_mistakes = content_list
                elif "interview" in t_low or "question" in t_low:
                    interview_questions = content_list
                elif "takeaway" in t_low or "point" in t_low:
                    key_points = content_list

            # Fallback if key_points is empty but we have general sections
            if not key_points and sections:
                key_points = sections[0].get("content", [])

            return {
                "topic": topic_title,
                "topic_index": topic_index,
                "summary": summary,
                "key_points": key_points,
                "important_terms": detailed.get("important_terms", []),
                "markdown": detailed.get("markdown", ""),
                "detailed": {
                    "summary": summary,
                    "markdown": detailed.get("markdown", ""),
                    "what_is_it": what_is_it or summary,
                    "why_matters": why_matters,
                    "how_it_works": how_it_works,
                    "example": example,
                    "key_points": key_points,
                    "important_terms": detailed.get("important_terms", []),
                    "comparisons": [],
                    "examples": [example] if example else [],
                    "common_mistakes": common_mistakes,
                    "interview_questions": interview_questions,
                    "sections": sections,
                },
                "revision": {
                    "definition": revision.get("definition", summary.split('.')[0] if summary else ""),
                    "facts": revision.get("facts", []),
                    "terms": revision.get("terms", detailed.get("important_terms", [])[:4]),
                    "remember": revision.get("remember", ""),
                    "one_liner": revision.get("definition", ""),
                    "bullets": revision.get("facts", []),
                }
            }
        except Exception:
            continue
    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fallback(topic_title: str, topic_index: int) -> dict:
    """Always-valid structure — never crashes."""
    return {
        "topic": topic_title,
        "topic_index": topic_index,
        "summary": "",
        "key_points": [],
        "important_terms": [],
        "markdown": "",
        "detailed": {
            "summary": "",
            "markdown": "",
            "what_is_it": "",
            "why_matters": "",
            "how_it_works": [],
            "example": "",
            "key_points": [],
            "important_terms": [],
            "comparisons": [],
            "examples": [],
            "common_mistakes": [],
            "interview_questions": [],
            "sections": [],
        },
        "revision": {
            "definition": "",
            "facts": [],
            "terms": [],
            "remember": "",
            "one_liner": "",
            "bullets": [],
        }
    }


def _migrate_old_cache(old: dict) -> dict:
    """Migrate old flat-format cache to new sectioned format."""
    topic = old.get("topic", "Topic")
    idx = old.get("topic_index", 0)
    summary = old.get("summary", "")
    key_points = old.get("key_points", [])
    terms = old.get("important_terms", [])
    old_detailed = old.get("detailed", {})
    common_mistakes = old_detailed.get("common_mistakes", [])
    interview_questions = old_detailed.get("interview_questions", [])
    
    # Build fallback markdown for old cache migration
    md_lines = [f"# {topic} Notes\n", "## Key Concepts\n"]
    if summary:
        md_lines.append(f"* {summary}")
    for kp in key_points[:5]:
        md_lines.append(f"* {kp}")
    markdown_notes = "\n".join(md_lines).strip()

    return {
        "topic": topic, "topic_index": idx,
        "summary": summary,
        "key_points": key_points,
        "important_terms": terms,
        "markdown": old_detailed.get("markdown", markdown_notes),
        "detailed": {
            "summary": summary,
            "markdown": old_detailed.get("markdown", markdown_notes),
            "what_is_it": old_detailed.get("what_is_it", summary.split('.')[0] if summary else ""),
            "why_matters": old_detailed.get("why_matters", ""),
            "how_it_works": old_detailed.get("how_it_works", []),
            "example": old_detailed.get("example", ""),
            "key_points": key_points,
            "important_terms": terms,
            "comparisons": old_detailed.get("comparisons", []),
            "examples": old_detailed.get("examples", []),
            "common_mistakes": common_mistakes,
            "interview_questions": interview_questions,
            "sections": old_detailed.get("sections", []),
        },
        "revision": old.get("revision", {
            "definition": summary.split('.')[0] if summary else topic,
            "facts": [p[:80] for p in key_points[:5]],
            "terms": terms[:4],
            "remember": "",
            "one_liner": summary.split('.')[0] if summary else topic,
            "bullets": [p[:60] for p in key_points[:5]],
        })
    }


def merge_topics_with_identical_notes(video_id: str, storage_dir: str) -> list:
    """
    Load topics, generate heuristic notes for each topic to check for duplicates,
    identify consecutive topics that produce the exact same heuristic notes,
    and merge them into a single topic, updating topics.json.
    """
    video_dir = os.path.join(storage_dir, video_id)
    topics_path = os.path.join(video_dir, "topics.json")
    if not os.path.exists(topics_path):
        return []

    with open(topics_path, encoding='utf-8') as f:
        topics = json.load(f)

    if len(topics) <= 1:
        return topics

    from extractor import extract_knowledge_units, build_structured_notes
    from translator import detect_language, translate_to_english, make_cache_path
    from extractor import remove_filler

    print(f"[LearnForge Merge] Running fast heuristic duplicate notes check on {len(topics)} topics...")

    # We repeat until no consecutive merges are made
    changed = True
    while changed:
        changed = False
        notes_markdown_list = []
        for idx, t in enumerate(topics):
            title = t.get("title", "")
            topic_text = t.get("content", "")
            
            # Fast translate/clean if Hinglish
            lang = detect_language(topic_text)
            if lang in ('hi', 'mix'):
                cache_path = make_cache_path(video_dir, f"topic_{idx}")
                english_text = translate_to_english(topic_text, cache_path=cache_path, label=f"[merge-topic_{idx}]")
            else:
                english_text = topic_text
                
            cleaned = remove_filler(english_text)
            knowledge = extract_knowledge_units(cleaned or english_text, title)
            detailed = build_structured_notes(knowledge, title)
            md = detailed.get("markdown", "").strip()
            notes_markdown_list.append(md)

        new_topics = []
        skip_next = False
        for i in range(len(topics)):
            if skip_next:
                skip_next = False
                continue

            if i < len(topics) - 1:
                md1 = notes_markdown_list[i]
                md2 = notes_markdown_list[i+1]

                # Clean markdown values for comparison (ignore headers and title instances)
                t1_title = topics[i].get("title", "")
                t2_title = topics[i+1].get("title", "")
                
                c_md1 = re.sub(r'^#\s+.+? Notes\n', '', md1, flags=re.I).strip()
                c_md2 = re.sub(r'^#\s+.+? Notes\n', '', md2, flags=re.I).strip()
                
                if t1_title:
                    c_md1 = re.sub(re.escape(t1_title), "[TOPIC_TITLE]", c_md1, flags=re.I)
                if t2_title:
                    c_md2 = re.sub(re.escape(t2_title), "[TOPIC_TITLE]", c_md2, flags=re.I)

                # If they generate the same markdown notes body
                if c_md1 and c_md1 == c_md2:
                    t1 = topics[i]
                    t2 = topics[i+1]
                    title1 = t1.get("title", "")
                    title2 = t2.get("title", "")
                    
                    if title1.lower() == title2.lower():
                        merged_title = title1
                    else:
                        merged_title = f"{title1} & {title2}"

                    print(f"[LearnForge Merge] Merging consecutive topics: '{title1}' & '{title2}' due to identical notes content.")
                    merged_topic = {
                        "title": merged_title,
                        "start_segment": min(t1.get("start_segment", 0), t2.get("start_segment", 0)),
                        "end_segment": max(t1.get("end_segment", 0), t2.get("end_segment", 0)),
                        "content": (t1.get("content", "") + " " + t2.get("content", "")).strip(),
                        "original_language": t1.get("original_language", "en")
                    }
                    new_topics.append(merged_topic)
                    skip_next = True
                    changed = True

                    # Clear all caches for this video so they are regenerated
                    cache_dir = os.path.join(video_dir, "notes_cache")
                    if os.path.exists(cache_dir):
                        for f_name in os.listdir(cache_dir):
                            try:
                                os.remove(os.path.join(cache_dir, f_name))
                            except Exception:
                                pass
                    for fn in ["notes.json", "flashcards.json", "quiz.json"]:
                        p = os.path.join(video_dir, fn)
                        if os.path.exists(p):
                            try:
                                os.remove(p)
                            except Exception:
                                pass
                else:
                    new_topics.append(topics[i])
            else:
                new_topics.append(topics[i])

        if changed:
            topics = new_topics
            with open(topics_path, "w", encoding="utf-8") as f:
                json.dump(topics, f, indent=2, ensure_ascii=False)

    return topics


# ── Legacy bulk generation ─────────────────────────────────────────────────────

def generate_notes_for_video(video_id: str, storage_dir: str, ollama_url: str = OLLAMA_URL) -> dict:
    """Legacy: generate notes for all topics (used by /notes/generate endpoint)."""
    video_dir = os.path.join(storage_dir, video_id)
    topics_path = os.path.join(video_dir, "topics.json")
    if not os.path.exists(topics_path):
        return {"topics": []}
    with open(topics_path, encoding='utf-8') as f:
        topics = json.load(f)
    results = []
    for idx in range(len(topics)):
        result = generate_notes_for_single_topic(video_id, idx, storage_dir, ollama_url)
        results.append(result)
    return {"topics": results}


def merge_introduction_topics(video_id: str, storage_dir: str) -> list:
    """
    Merges consecutive topics that both contain 'introduction' or start with 'intro'
    into a single merged 'Introduction' topic. Clear caches so study space regenerates.
    """
    video_dir = os.path.join(storage_dir, video_id)
    topics_path = os.path.join(video_dir, "topics.json")
    if not os.path.exists(topics_path):
        return []

    with open(topics_path, encoding='utf-8') as f:
        topics = json.load(f)

    if not topics:
        return []

    print(f"[LearnForge Merge] Running introduction topics merge check on {len(topics)} topics...")

    def is_intro(title: str) -> bool:
        t = title.lower().strip()
        t = re.sub(r'^[-\s:._|–\d]+', '', t).strip()
        return t.startswith("introduction") or t.startswith("intro")

    # We repeat until no consecutive intro merges are made
    changed = True
    while changed:
        changed = False
        new_topics = []
        skip_next = False
        for i in range(len(topics)):
            if skip_next:
                skip_next = False
                continue

            if i < len(topics) - 1:
                t1 = topics[i]
                t2 = topics[i+1]
                title1 = t1.get("title", "")
                title2 = t2.get("title", "")

                if is_intro(title1) and is_intro(title2):
                    # Combine consecutive intro topics
                    print(f"[LearnForge Merge] Merging consecutive intro topics: '{title1}' & '{title2}'")
                    merged_title = "Introduction"
                    
                    merged_topic = {
                        "title": merged_title,
                        "start_segment": min(t1.get("start_segment", 0), t2.get("start_segment", 0)),
                        "end_segment": max(t1.get("end_segment", 0), t2.get("end_segment", 0)),
                        "content": (t1.get("content", "") + " " + t2.get("content", "")).strip(),
                        "original_language": t1.get("original_language", "en")
                    }
                    new_topics.append(merged_topic)
                    skip_next = True
                    changed = True

                    # Clear all caches for this video so they are regenerated
                    cache_dir = os.path.join(video_dir, "notes_cache")
                    if os.path.exists(cache_dir):
                        for f_name in os.listdir(cache_dir):
                            try:
                                os.remove(os.path.join(cache_dir, f_name))
                            except Exception:
                                pass
                    for fn in ["notes.json", "flashcards.json", "quiz.json"]:
                        p = os.path.join(video_dir, fn)
                        if os.path.exists(p):
                            try:
                                os.remove(p)
                            except Exception:
                                pass
                else:
                    new_topics.append(t1)
            else:
                new_topics.append(topics[i])

        if changed:
            topics = new_topics
            with open(topics_path, "w", encoding="utf-8") as f:
                json.dump(topics, f, indent=2, ensure_ascii=False)

    return topics

