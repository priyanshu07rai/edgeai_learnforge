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
    with open(quiz_path, "w", encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[LearnForge Quiz] Saved quiz.json for {video_id}.")
    return result


def _call_ollama_for_quiz(topic_title: str, notes_markdown: str, ollama_url: str):
    prompt = f"""Create 5 MCQs based strictly on the provided study notes.

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
                return valid
        except Exception:
            continue
    return None


# ── Per-topic generation ─────────────────────────────────────────────────

def _generate_quiz_llm(topic_title: str, knowledge: dict, gemini_key: str = None, ollama_url: str = None):
    prompt = f"""You are an educational study assistant.
Generate 5 MCQ questions using ONLY the structured Knowledge Layer JSON below. Do NOT use conversational filler.
Strict Voice Rules: Use Third-Person Objective Voice Only (never use "I", "my", "we", "us", "our", "you", or conversational tokens in questions, options, or explanations).
Every question must have 4 distinct options (labeled A, B, C, D), a correct_answer (e.g. "A"), and a brief explanation. All text must be in English.

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
    quiz = []
    
    # 1. Definition question
    definition = knowledge.get("definition", "")
    if definition:
        quiz.append({
            "question": f"Which of the following best defines the concept of {topic_title}?",
            "options": [
                f"A) {definition}",
                "B) It is an obsolete framework with no modern usage.",
                "C) It refers to the design system styling layer.",
                "D) None of the above."
            ],
            "correct_answer": "A",
            "explanation": f"The definition of {topic_title} is: {definition}"
        })
        
    # 2. Warning / Pitfall question
    warnings = knowledge.get("warnings", [])
    if warnings:
        w = warnings[0]
        quiz.append({
            "question": f"What is a critical warning or mistake to avoid regarding {topic_title}?",
            "options": [
                f"A) {w}",
                "B) Implementing default configurations without testing.",
                "C) Writing self-documenting code remarks.",
                "D) None of the above."
            ],
            "correct_answer": "A",
            "explanation": f"A common warning/pitfall is: {w}"
        })
        
    # 3. Best practice question
    best_practices = knowledge.get("best_practices", [])
    if best_practices:
        bp = best_practices[0]
        quiz.append({
            "question": f"Which of the following is a recommended best practice for {topic_title}?",
            "options": [
                f"A) {bp}",
                "B) Disabling error logging to improve execution speed.",
                "C) Hardcoding authentication credentials in source files.",
                "D) None of the above."
            ],
            "correct_answer": "A",
            "explanation": f"A key best practice is: {bp}"
        })
        
    # 4. Procedure / Step question
    procedures = knowledge.get("procedures", [])
    if procedures:
        step = procedures[0]
        quiz.append({
            "question": f"What is a key step involved in implementing or configuring {topic_title}?",
            "options": [
                f"A) {step}",
                "B) Deleting configuration files before starting.",
                "C) Setting all security permissions to public.",
                "D) None of the above."
            ],
            "correct_answer": "A",
            "explanation": f"A key step is: {step}"
        })

    # 5. Example / Application question
    examples = knowledge.get("examples", [])
    if examples:
        ex = examples[0]
        quiz.append({
            "question": f"Which of the following represents a practical example or application of {topic_title}?",
            "options": [
                f"A) {ex}",
                "B) A static text file containing user interface notes.",
                "C) A default database table with no entries.",
                "D) None of the above."
            ],
            "correct_answer": "A",
            "explanation": f"A practical example is: {ex}"
        })
        
    # Fill up if empty or less than 3 questions
    while len(quiz) < 3:
        keywords = knowledge.get("keywords", [])
        kw_str = f" involving {', '.join(keywords[:2])}" if keywords else ""
        quiz.append({
            "question": f"What is the primary subject or focus of {topic_title}?",
            "options": [
                f"A) The core architectural mechanisms and principles of {topic_title}{kw_str}.",
                "B) Standard website hosting layouts.",
                "C) Basic filesystem directory styling.",
                "D) None of the above."
            ],
            "correct_answer": "A",
            "explanation": f"This timeline section specifically covers {topic_title}."
        })
        break
        
    return quiz[:5]


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

    with open(cache_path, "w", encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result
