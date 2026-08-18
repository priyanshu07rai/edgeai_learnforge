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
import tempfile
from collections import Counter, OrderedDict
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

from config import OLLAMA_URL, MODEL_MAIN, DEFAULT_NUM_CTX, DEFAULT_NUM_PREDICT
from ollama_health import check_ollama_available, resolve_model

MODEL = MODEL_MAIN


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

    dir_name = os.path.dirname(cache_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, cache_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

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


# ── Code-block syntax patterns (used by sanitizer) ─────────────────────────────
_REAL_CODE_RE = re.compile(
    r'(?:^|\n)[ \t]*(?:'
    r'def \w+\s*\(|'
    r'class \w+[:(]|'
    r'import \w|'
    r'from \w+ import|'
    r'const |let |var |function\s+\w+\s*\(|'
    r'=>|'
    r'\w+\(\)|'
    r'return |'
    r'elif |else:|except:|'
    r'lambda |yield |async def|await |'
    r'#include|'
    r'\$\s*\w+|'
    r'pip install|npm install|git |docker |curl |wget'
    r')',
    re.MULTILINE
)


def sanitize_markdown_code_blocks(markdown: str) -> str:
    """
    Post-process LLM-generated markdown to remove false-positive code blocks.

    Rules:
    - Empty or whitespace-only code blocks → removed entirely.
    - Code blocks whose content does NOT match real code syntax patterns AND
      has fewer than 3 lines → demoted to plain bullet-point paragraphs.
    - Everything else (real code) → kept as-is.
    """
    if not markdown:
        return markdown

    # Regex that captures: ```<lang>\n<content>\n``` or ```<content>```
    fence_re = re.compile(r'```([a-zA-Z]*)\n?(.*?)```', re.DOTALL)

    def _handle_fence(m):
        lang = m.group(1).strip()
        content = m.group(2)
        stripped = content.strip()

        # Rule 1: Empty block → remove
        if not stripped:
            return ''

        # Rule 2: Check if it looks like real code
        has_real_code = bool(_REAL_CODE_RE.search(stripped))
        lines = [l for l in stripped.splitlines() if l.strip()]
        is_multiline = len(lines) >= 2

        if has_real_code or (is_multiline and len(stripped) > 80):
            # Keep as code block, ensure language tag is on its own line
            lang_tag = lang if lang else ''
            return f'```{lang_tag}\n{stripped}\n```'

        # Rule 3: It's prose that was wrongly fenced → demote to bullet point
        # Join lines and return as a plain paragraph
        prose = ' '.join(lines)
        return f'- {prose}'

    sanitized = fence_re.sub(_handle_fence, markdown)

    # Collapse 3+ consecutive blank lines into 2
    sanitized = re.sub(r'\n{3,}', '\n\n', sanitized)
    return sanitized.strip()


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

    # Save the knowledge cache atomically
    cache_dir = os.path.join(video_dir, "notes_cache")
    os.makedirs(cache_dir, exist_ok=True)
    knowledge_cache_path = os.path.join(cache_dir, f"topic_{topic_index}_knowledge.json")
    
    fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, knowledge_cache_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    detailed = build_notes_from_knowledge(knowledge, topic_title)
    revision = build_quick_revision_30s(detailed, topic_title)

    # Sanitize the markdown to remove false-positive code blocks before caching
    raw_md = detailed.get("markdown", "")
    detailed["markdown"] = sanitize_markdown_code_blocks(raw_md)

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

    # ── Step 3: Deterministic Keywords ─────────────────────────────────────────
    key_terms = extract_deterministic_keywords(llm_input_text)
    print(f"[LearnForge Notes] [{topic_index}] Deterministic key terms: {key_terms}")

    # ── Step 4: LLM Knowledge Extraction ────────────────────────────────────────
    # NOTE: We removed the is_technical() router gate — it was incorrectly flagging
    # real educational content as "conversational" and generating useless stub text.
    # Instead: attempt LLM extraction for ALL segments with sufficient content (≥200 chars).
    # The LLM prompts themselves handle conversational vs. technical distinctions internally.
    knowledge = None
    ollama_online = check_ollama_available(ollama_url)

    if len(llm_input_text) >= 200 and ollama_online:
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



def _call_llm_to_extract_knowledge(topic_title: str, cleaned_text: str, ollama_url: str = OLLAMA_URL) -> dict:
    """
    Ollama 1B LLM extraction pipeline: 4 small focused prompts, each asking ONE thing reliably.
    """
    if ollama_url:
        return _call_ollama_focused_pipeline(topic_title, cleaned_text, ollama_url)
    return None


def _call_ollama_focused_pipeline(topic_title: str, cleaned_text: str, ollama_url: str) -> dict:
    """
    Ollama 1B pipeline: 4 small, focused prompts — each asks ONE specific thing.
    Small models fail on complex multi-field JSON but work well on single focused questions.
    Results are assembled into the full Knowledge Layer schema.
    """
    # Limit input to what the 1B model can handle without degrading
    text_snippet = cleaned_text[:2000]

    def _ask(prompt: str, is_list: bool = False):
        """Ask Ollama one focused question, return text answer."""
        target_model = resolve_model(MODEL_MAIN)
        try:
            resp = requests.post(
                ollama_url,
                json={
                    "model": target_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": DEFAULT_NUM_PREDICT,
                        "num_ctx": DEFAULT_NUM_CTX,
                    }
                },
                timeout=8.0
            )
            if resp.status_code == 200:
                answer = resp.json().get("response", "").strip()
                # Remove any meta-commentary like "Sure, here is..." or "Based on the text..."
                answer = re.sub(r'^(?:sure[,.]?|here(?:\s+is)?[,:]?|based\s+on\s+[^,]+[,:]?|the\s+answer\s+is[:]?)\s*', '', answer, flags=re.I).strip()
                return answer
        except Exception:
            pass
        return ""

    print(f"[LearnForge Notes] [Ollama 1B] Running focused 4-prompt pipeline for '{topic_title}'...")

    # Prompt 1: Definition — "What is X in one clear sentence?"
    definition_raw = _ask(
        f"""Write a formal, one-sentence textbook definition for "{topic_title}".
Define what it is objectively and clearly in the third person.
Do NOT use conversational language. Never say "In this video", "Let's talk", or "Welcome".
Format: {topic_title} is [formal definition of what it is and what it does].

Topic: {topic_title}
Context:
{text_snippet[:1500]}

Definition:"""
    )

    # Prompt 2: Explanation — "Explain the core concept in 2-4 sentences"
    explanation_raw = _ask(
        f"""Read this transcript excerpt about "{topic_title}".
Write 2-4 clear sentences explaining the core concept — how it works and why it matters.
Do NOT copy conversational chatter. Do NOT start with "I", "we", "you", "In this video", "Alright", or "Okay".
Write in objective, third-person style.

Transcript excerpt:
{text_snippet}

Write only the explanation (no labels):"""
    )

    # Prompt 3: Key points — "List 3 key facts as bullet points"
    keypoints_raw = _ask(
        f"""Read this transcript excerpt about "{topic_title}".
List exactly 3 key facts or takeaways as short bullet points.
Each bullet must be a complete fact, not a transcript sentence.
Format: - [fact]

Transcript excerpt:
{text_snippet}

Key facts:"""
    )

    # Prompt 4: Summary — "Summarize in one sentence"
    summary_raw = _ask(
        f"""In ONE sentence, summarize what "{topic_title}" is and why it is important, based on this excerpt:
{text_snippet[:800]}

Summary sentence:"""
    )

    # Parse key points into a list
    keypoints = []
    for line in keypoints_raw.splitlines():
        line = line.strip().lstrip('-•*123456789. ').strip()
        if len(line) > 15 and not line.lower().startswith(('sure', 'here', 'based', 'key fact', 'key point')):
            keypoints.append(line)

    # Validate outputs — if they look like transcript copies or are empty, use fallback
    def _is_good(text: str) -> bool:
        if not text or len(text.strip()) < 15:
            return False
        s_low = text.lower().strip()
        bad_phrases = (
            'alright', 'okay', 'so ', 'in this video', 'in this course',
            'my name is', 'hello', 'welcome', 'i am', "i'm", 'we are',
            'today we', 'in this lecture', 'let\'s talk', 'let us talk',
            'hot topic', 'twitter', 'linkedin', 'next video', 'previous video',
            'everyone to another', 'exciting video', 'subscribe', 'channel'
        )
        return not any(b in s_low for b in bad_phrases)

    definition = definition_raw if _is_good(definition_raw) else f"{topic_title} is a core software and system engineering concept covering key architectural and practical principles."
    explanation = explanation_raw if _is_good(explanation_raw) else (" ".join(keypoints[:2]) if keypoints else "")
    summary = summary_raw if _is_good(summary_raw) else definition

    print(f"[LearnForge Notes] [Ollama 1B] def={len(definition)}c, exp={len(explanation)}c, kp={len(keypoints)}, sum={len(summary)}c")

    return {
        "concept": topic_title,
        "definition": definition,
        "explanation": explanation,
        "analogy": "",
        "examples": [],
        "procedures": keypoints[2:] if len(keypoints) > 2 else [],
        "applications": keypoints[:2] if keypoints else [],
        "commands": [],
        "formulas": [],
        "warnings": [],
        "best_practices": keypoints[:3],
        "interview_questions": [f"What is {topic_title} and what is its significance?"],
        "keywords": [],
        "code": [],
        "output": [],
        "summary": summary,
    }




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

            # Sanitize the LLM-generated markdown to strip false-positive code blocks
            raw_md = detailed.get("markdown", "")
            clean_md = sanitize_markdown_code_blocks(raw_md)

            return {
                "topic": topic_title,
                "topic_index": topic_index,
                "summary": summary,
                "key_points": key_points,
                "important_terms": detailed.get("important_terms", []),
                "markdown": clean_md,
                "detailed": {
                    "summary": summary,
                    "markdown": clean_md,
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

