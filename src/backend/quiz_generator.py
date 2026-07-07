"""
quiz_generator.py — Generates MCQ quizzes from actual transcript content.
Translates Hindi→English first, then builds factual multiple-choice questions.
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
import random
from dotenv import load_dotenv
from ollama_health import check_ollama_available
from translator import translate_to_english, detect_language, make_cache_path
from extractor import extract_facts, build_quiz, populate_legacy_keys_on_knowledge
from notes_generator import generate_notes_for_single_topic

# Load .env variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:1b"


def _safe(text, limit=300):
    return str(text)[:limit].encode('ascii', errors='replace').decode('ascii')


def generate_quiz_for_video(video_id: str, storage_dir: str, ollama_url: str = OLLAMA_URL) -> dict:
    video_dir = os.path.join(storage_dir, video_id)
    quiz_path = os.path.join(video_dir, "quiz.json")

    if os.path.exists(quiz_path):
        print(f"[LearnForge Quiz] Serving cached quiz for {video_id}")
        with open(quiz_path, encoding='utf-8') as f:
            return json.load(f)

    topics_path = os.path.join(video_dir, "topics.json")
    if not os.path.exists(topics_path):
        return {"topics": []}
    with open(topics_path, encoding='utf-8') as f:
        topics = json.load(f)

    chunks_path = os.path.join(video_dir, "chunks.json")
    chunks = []
    if os.path.exists(chunks_path):
        with open(chunks_path, encoding='utf-8') as f:
            chunks = json.load(f)

    # Load notes for context (generated before quiz)
    notes_path = os.path.join(video_dir, "notes.json")
    notes_by_idx = {}
    if os.path.exists(notes_path):
        with open(notes_path, encoding='utf-8') as f:
            notes_data = json.load(f)
        for i, n in enumerate(notes_data.get("topics", [])):
            notes_by_idx[i] = n

    if not topics:
        return {"topics": []}

    print(f"[LearnForge Quiz] Processing {len(topics)} topics for {video_id}...")

    ollama_online = check_ollama_available(ollama_url)
    if not ollama_online:
        print("[LearnForge Quiz] Ollama OFFLINE - using translate+extract pipeline.")

    quiz_topics = []

    for idx, t in enumerate(topics):
        topic_title = t.get("title", f"Topic {idx + 1}")
        topic_id = f"topic_{idx}"

        topic_text = t.get("content", "")
        if not topic_text:
            topic_chunks = [c.get("text", "") for c in chunks if c.get("topic_id") == topic_id]
            topic_text = " ".join(topic_chunks).strip()

        chunk_len = len(topic_text)
        print(f"[LearnForge Quiz] -- Topic {idx+1}/{len(topics)}: '{_safe(topic_title, 80)}'")
        print(f"[LearnForge Quiz]    TEXT LENGTH: {chunk_len}")

        questions = None

        # Get cached/generated notes (Detailed Notes -> Quiz flow)
        notes_data = generate_notes_for_single_topic(video_id, idx, storage_dir, ollama_url)
        notes_markdown = notes_data.get("markdown", "")
        detailed = notes_data.get("detailed", {})

        # LLM path (Detailed Notes -> Quiz)
        if len(notes_markdown) > 50 and ollama_online:
            questions = _call_ollama_for_quiz(topic_title, notes_markdown, ollama_url)

        # Offline/Heuristic path (build quiz from clean notes structure, not raw transcript)
        if not questions:
            facts = {
                'definitions': [detailed.get('what_is_it')] if detailed.get('what_is_it') else [],
                'features': [detailed.get('why_matters')] if detailed.get('why_matters') else [],
                'comparisons': detailed.get('comparisons', []),
                'terms': detailed.get('important_terms', []),
                'examples': detailed.get('examples', []),
                'ranked_sentences': detailed.get('key_points', []),
            }
            questions = build_quiz(facts, topic_title)

        if not questions:
            questions = [{
                "question": f"What is the main topic covered in {topic_title}?",
                "options": [
                    f"A) {topic_title}",
                    "B) An unrelated historical event",
                    "C) A modern political development",
                    "D) A scientific discovery"
                ],
                "correct_answer": "A",
                "explanation": f"This section is dedicated to {topic_title}."
            }]

        print(f"[LearnForge Quiz]    Final question count: {len(questions)}")
        quiz_topics.append({"topic": topic_title, "quiz": questions})

    result = {"topics": quiz_topics}
    
    # Atomic write to prevent race conditions
    dir_name = os.path.dirname(quiz_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, quiz_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
    print(f"[LearnForge Quiz] Saved quiz.json for {video_id}.")
    return result


def _call_ollama_for_quiz(topic_title: str, notes_markdown: str, ollama_url: str):
    prompt = f"""Create 5 MCQs

CRITICAL RULE: You MUST write your entire response exclusively in English. If the input contains Hindi, Hinglish, or Devanagari characters, TRANSLATE it to English. DO NOT output any Hindi or Devanagari characters.
 based strictly on the provided study notes.

Rules:
- **Third-Person Objective Voice Only:** Never use first-person speech ("I", "my", "we", "our", "us") or second-person speech ("you"). Keep all questions, options, and explanations objective.
- Use only information from notes. Do NOT use outside information or raw transcript fillers.
- One correct answer.
- Three plausible distractors (options A, B, C, D).
- Avoid obvious wrong options.

Study Notes for '{topic_title}':
{notes_markdown}

Return ONLY valid JSON in this format:
{{"quiz": [{{"question": "...", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], "correct_answer": "A", "explanation": "..."}}]}}"""

    try:
        resp = requests.post(
            ollama_url,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=35,
        )
        if resp.status_code != 200:
            return None
        raw = resp.json().get("response", "").strip()
        return _parse_quiz_json(raw)
    except Exception as e:
        print(f"[LearnForge Quiz]    LLM failed: {e}")
        return None


def _parse_quiz_json(raw: str):
    if not raw:
        return None
    for match in re.finditer(r'\{', raw):
        try:
            candidate = raw[match.start():]
            data = json.loads(candidate[:candidate.rfind('}') + 1])
            quiz_list = data.get("quiz", [])
            if not isinstance(quiz_list, list) or not quiz_list:
                continue
            valid = []
            for q in quiz_list:
                if not isinstance(q, dict):
                    continue
                if not q.get("question") or not q.get("options") or not q.get("correct_answer"):
                    continue
                opts = q["options"]
                if not isinstance(opts, list) or len(opts) < 2:
                    continue
                valid.append({
                    "question": q["question"],
                    "options": opts[:4],
                    "correct_answer": q.get("correct_answer", "A"),
                    "explanation": q.get("explanation", ""),
                })
            if valid:
                return _randomize_quiz_options(valid)
        except Exception:
            continue
    return None

def _randomize_quiz_options(quiz_list: list) -> list:
    """Randomizes the options for each question and correctly remaps the correct_answer."""
    for q in quiz_list:
        opts = q.get("options", [])
        if not opts or len(opts) < 2:
            continue
            
        correct = str(q.get("correct_answer", "A")).strip()
        
        # 1. Determine the index of the current correct answer
        correct_idx = 0
        match = re.match(r'^([A-D])\b', correct, re.IGNORECASE)
        if match:
            # Case 1: "A" or "A)" or "a"
            correct_idx = ord(match.group(1).upper()) - ord('A')
        else:
            # Case 2: Full string match
            for i, opt in enumerate(opts):
                if correct.lower() in opt.lower():
                    correct_idx = i
                    break
                    
        correct_idx = min(max(correct_idx, 0), len(opts) - 1)
        
        # 2. Strip prefixes and extract the pure text of options
        clean_opts = [re.sub(r'^([A-D][\.\)]\s*)', '', opt, flags=re.IGNORECASE).strip() for opt in opts]
        correct_text = clean_opts[correct_idx]
        
        # 3. Shuffle the pure text options
        random.shuffle(clean_opts)
        
        # 4. Re-map the correct answer to its new index
        new_correct_idx = clean_opts.index(correct_text)
        new_correct_letter = chr(ord('A') + new_correct_idx)
        
        # 5. Re-apply the A/B/C/D prefixes to the shuffled options
        formatted_opts = [f"{chr(ord('A') + i)}) {opt}" for i, opt in enumerate(clean_opts)]
        
        # 6. Update the question object
        q["options"] = formatted_opts
        q["correct_answer"] = new_correct_letter
        
    return quiz_list


# ── Per-topic generation ─────────────────────────────────────────────────

def _generate_quiz_llm(topic_title: str, knowledge: dict, gemini_key: str = None, ollama_url: str = None):
    prompt = f"""You are a senior educational assessment designer creating high-quality multiple-choice questions.

CRITICAL RULE: You MUST write your entire response exclusively in English. If the input contains Hindi, Hinglish, or Devanagari characters, TRANSLATE it to English. DO NOT output any Hindi or Devanagari characters.

Your task: Generate 5 HIGH-QUALITY, reasoning-based MCQs for the topic "{topic_title}" using ONLY facts from the Knowledge Layer JSON below.

# Quiz Quality Rules
1. FORBIDDEN question types: "What is the definition of..." or "Which of the following means..." — these are too shallow.
2. REQUIRED question depth — test application and reasoning:
   - "In which scenario would you use [concept] instead of [alternative]?"
   - "What is the expected outcome if [action/step] is performed?"
   - "Why is [best practice] recommended for [concept]?"
   - "What underlying problem does [concept] solve?"
3. Distractor Quality (Wrong Options):
   - Options must be highly believable.
   - Use common misconceptions or plausible but incorrect technical assumptions.
   - DO NOT use obvious filler or silly options.
4. Explanations MUST be educational. They should explain *why* the correct answer is right AND *why* the distractors are wrong based on the concept's principles.
5. Provide exactly 4 options labeled A, B, C, D.

# Voice Rules
- Use Third-Person Objective Voice Only.
- Never use "I", "my", "we", "us", "our", "you".

Topic: {topic_title}
Knowledge:
{json.dumps(knowledge, indent=2)}

Return ONLY valid JSON (no markdown wrapper, no other text):
{{"quiz": [{{"question": "...", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], "correct_answer": "A", "explanation": "..."}}]}}"""


    raw = ""
    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print(f"[Gemini API] Quiz failed: {e}")
    elif ollama_url:
        try:
            resp = requests.post(
                ollama_url,
                json={"model": MODEL, "prompt": prompt, "stream": False, "format": "json"},
                timeout=35,
            )
            if resp.status_code == 200:
                raw = resp.json().get("response", "").strip()
        except Exception as e:
            print(f"[Ollama] Quiz failed: {e}")

    if raw:
        return _parse_quiz_json(raw)
    return None


def _build_quiz_heuristic(knowledge: dict, topic_title: str) -> list:
    """Build reasoning-based MCQs from knowledge fields without an LLM."""
    quiz = []
    
    # 1. Reasoning/Purpose question (from explanation)
    explanation = knowledge.get("explanation", "")
    if explanation:
        quiz.append({
            "question": f"What is the primary underlying purpose or mechanism of {topic_title}?",
            "options": [
                f"A) {explanation[:120].strip()}...",
                "B) It serves as a legacy fallback system with no active use.",
                "C) It replaces all external dependencies with a single binary.",
                "D) It only handles UI rendering without affecting logic."
            ],
            "correct_answer": "A",
            "explanation": f"The core purpose is: {explanation}"
        })
        
    # 2. Warning / Pitfall question
    warnings = knowledge.get("warnings", [])
    if warnings:
        w = warnings[0]
        quiz.append({
            "question": f"If a developer is working with {topic_title}, what critical pitfall must they avoid?",
            "options": [
                f"A) {w}",
                "B) Over-documenting the implementation details.",
                "C) Using it in conjunction with standard industry tools.",
                "D) Relying on built-in security features."
            ],
            "correct_answer": "A",
            "explanation": f"A common pitfall to avoid is: {w}"
        })
        
    # 3. Best practice question
    best_practices = knowledge.get("best_practices", [])
    if best_practices:
        bp = best_practices[0]
        quiz.append({
            "question": f"To ensure stability and efficiency when using {topic_title}, which practice should be followed?",
            "options": [
                f"A) {bp}",
                "B) Disable all error logging to improve runtime execution speed.",
                "C) Hardcode configuration values directly into the core source files.",
                "D) Bypass standard initialization procedures."
            ],
            "correct_answer": "A",
            "explanation": f"A recommended best practice is: {bp}"
        })
        
    # 4. Procedure / Step question
    procedures = knowledge.get("procedures", [])
    if procedures:
        step = procedures[0]
        quiz.append({
            "question": f"When implementing or configuring {topic_title}, what is a necessary action?",
            "options": [
                f"A) {step}",
                "B) Deleting all prior configuration files without backups.",
                "C) Setting global variables for all internal states.",
                "D) Skipping the validation phase."
            ],
            "correct_answer": "A",
            "explanation": f"An essential step is: {step}"
        })

    # 5. Example / Application question
    applications = knowledge.get("applications", [])
    examples = knowledge.get("examples", [])
    app_ex = applications[0] if applications else (examples[0] if examples else "")
    if app_ex:
        quiz.append({
            "question": f"In which of the following real-world scenarios is {topic_title} most effectively applied?",
            "options": [
                f"A) {app_ex}",
                "B) When building a purely static informational text file.",
                "C) When creating a system with zero user interactions.",
                "D) When reverting an application to its earliest prototype."
            ],
            "correct_answer": "A",
            "explanation": f"A primary application is: {app_ex}"
        })
        
    # Fill up if empty
    if not quiz:
        summary = knowledge.get("summary", f"This topic covers the key concepts of {topic_title}.")
        quiz.append({
            "question": f"What is the most accurate high-level description of {topic_title}?",
            "options": [
                f"A) {summary}",
                "B) It is an outdated methodology not used in modern development.",
                "C) It is a purely visual design concept with no technical function.",
                "D) It is an experimental feature not meant for production."
            ],
            "correct_answer": "A",
            "explanation": f"The core definition is: {summary}"
        })
        
    return _randomize_quiz_options(quiz)[:5]


def generate_quiz_for_single_topic(
    video_id: str, topic_index: int, storage_dir: str, ollama_url: str = OLLAMA_URL
) -> dict:
    """Generate quiz for ONE topic. Caches in quiz_cache/topic_N.json."""
    video_dir = os.path.join(storage_dir, video_id)
    cache_dir = os.path.join(video_dir, "quiz_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"topic_{topic_index}.json")
    knowledge_cache_path = os.path.join(video_dir, "notes_cache", f"topic_{topic_index}_knowledge.json")

    if os.path.exists(cache_path):
        with open(cache_path, encoding='utf-8') as f:
            return json.load(f)

    topics_path = os.path.join(video_dir, "topics.json")
    if not os.path.exists(topics_path):
        return {"topic": f"Topic {topic_index}", "topic_index": topic_index, "quiz": []}

    with open(topics_path, encoding='utf-8') as f:
        topics = json.load(f)

    if topic_index >= len(topics):
        return {"topic": f"Topic {topic_index}", "topic_index": topic_index, "quiz": []}

    t = topics[topic_index]
    topic_title = t.get("title", f"Topic {topic_index + 1}")

    # Ensure knowledge cache is generated (generate_notes_for_single_topic will create it if missing)
    if not os.path.exists(knowledge_cache_path):
        print(f"[LearnForge Quiz] Knowledge cache missing. Triggering notes generator to extract knowledge...")
        generate_notes_for_single_topic(video_id, topic_index, storage_dir, ollama_url)

    # Load knowledge cache
    if os.path.exists(knowledge_cache_path):
        with open(knowledge_cache_path, encoding='utf-8') as f:
            knowledge = json.load(f)
        knowledge = populate_legacy_keys_on_knowledge(knowledge)
    else:
        # Extreme fallback: build empty knowledge
        from extractor import _empty_knowledge
        knowledge = populate_legacy_keys_on_knowledge(_empty_knowledge(topic_title))

    questions = None

    # Try Gemini if key is present
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key and knowledge:
        print(f"[LearnForge Quiz] Generating from knowledge schema using Gemini for [{topic_index}]...")
        questions = _generate_quiz_llm(topic_title, knowledge, gemini_key=gemini_key)
        
    # Try Ollama if online
    if not questions and knowledge:
        ollama_online = check_ollama_available(ollama_url)
        if ollama_online:
            print(f"[LearnForge Quiz] Generating from knowledge schema using Ollama for [{topic_index}]...")
            questions = _generate_quiz_llm(topic_title, knowledge, ollama_url=ollama_url)

    # Heuristic fallback (using knowledge fields directly)
    if not questions:
        print(f"[LearnForge Quiz] Heuristic fallback generation for [{topic_index}]...")
        questions = _build_quiz_heuristic(knowledge, topic_title)

    result = {
        "topic": topic_title,
        "topic_index": topic_index,
        "quiz": questions,
    }

    # Atomic thread-safe cache write
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
