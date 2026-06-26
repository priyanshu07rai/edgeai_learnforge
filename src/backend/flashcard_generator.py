"""
flashcard_generator.py — Generates Q&A flashcards from actual transcript content.
Translates Hindi→English first, then extracts factual Q&A pairs.
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
from extractor import extract_facts, build_flashcards, populate_legacy_keys_on_knowledge
from notes_generator import generate_notes_for_single_topic

# Load .env variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:1b"


def _safe(text, limit=300):
    return str(text)[:limit].encode('ascii', errors='replace').decode('ascii')


def generate_flashcards_for_video(video_id: str, storage_dir: str, ollama_url: str = OLLAMA_URL) -> dict:
    video_dir = os.path.join(storage_dir, video_id)
    cards_path = os.path.join(video_dir, "flashcards.json")

    if os.path.exists(cards_path):
        print(f"[LearnForge Flashcards] Serving cached flashcards for {video_id}")
        with open(cards_path, encoding='utf-8') as f:
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

    if not topics:
        return {"topics": []}

    print(f"[LearnForge Flashcards] Processing {len(topics)} topics for {video_id}...")

    ollama_online = check_ollama_available(ollama_url)
    if not ollama_online:
        print("[LearnForge Flashcards] Ollama OFFLINE - using translate+extract pipeline.")

    cards_topics = []

    for idx, t in enumerate(topics):
        topic_title = t.get("title", f"Topic {idx + 1}")
        topic_id = f"topic_{idx}"

        topic_text = t.get("content", "")
        if not topic_text:
            topic_chunks = [c.get("text", "") for c in chunks if c.get("topic_id") == topic_id]
            topic_text = " ".join(topic_chunks).strip()

        chunk_len = len(topic_text)
        print(f"[LearnForge Flashcards] -- Topic {idx+1}/{len(topics)}: '{_safe(topic_title, 80)}'")

        card_data = None

        # Fetch detailed notes for context (Detailed Notes -> Flashcards flow)
        notes_data = generate_notes_for_single_topic(video_id, idx, storage_dir, ollama_url)
        notes_markdown = notes_data.get("markdown", "")
        detailed = notes_data.get("detailed", {})

        # LLM path (Detailed Notes -> Flashcards)
        if len(notes_markdown) > 50 and ollama_online:
            card_data = _call_ollama_for_cards(topic_title, notes_markdown, ollama_url)

        # Offline/Heuristic path (build cards from clean notes structure, not raw transcript)
        if not card_data:
            facts = {
                'definitions': [detailed.get('what_is_it')] if detailed.get('what_is_it') else [],
                'features': [detailed.get('why_matters')] if detailed.get('why_matters') else [],
                'comparisons': detailed.get('comparisons', []),
                'terms': detailed.get('important_terms', []),
                'examples': detailed.get('examples', []),
                'ranked_sentences': detailed.get('key_points', []),
            }
            card_data = {"cards": build_flashcards(facts, topic_title)}

        final_cards = card_data.get("cards", []) if card_data else []
        print(f"[LearnForge Flashcards]    Final card count: {len(final_cards)}")

        cards_topics.append({
            "topic": topic_title,
            "cards": final_cards,
        })

    result = {"topics": cards_topics}
    with open(cards_path, "w", encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[LearnForge Flashcards] Saved flashcards.json for {video_id}.")
    return result


def _call_ollama_for_cards(topic_title: str, notes_markdown: str, ollama_url: str):
    prompt = f"""You are an expert educator.
Your task is to generate 8-10 flashcard Q&A pairs based strictly on the provided study notes.

Rules:
- **Third-Person Objective Voice Only:** Never use first-person speech ("I", "my", "we", "our", "us") or second-person speech ("you"). Keep all questions and answers completely objective.
- Every Q&A pair must be derived from a specific fact in the study notes.
- Do NOT use raw transcript narration or filler words.
- Keep questions and answers concise, clear, and direct.

Study Notes for '{topic_title}':
{notes_markdown}

Return ONLY valid JSON in this format:
{{"cards": [{{"question": "...", "answer": "..."}}]}}"""

    try:
        resp = requests.post(
            ollama_url,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=35,
        )
        if resp.status_code != 200:
            return None
        raw = resp.json().get("response", "").strip()
        return _parse_cards_json(raw)
    except Exception as e:
        print(f"[LearnForge Flashcards]    LLM failed: {e}")
        return None


def _parse_cards_json(raw: str):
    if not raw:
        return None
    for match in re.finditer(r'\{', raw):
        try:
            candidate = raw[match.start():]
            data = json.loads(candidate[:candidate.rfind('}') + 1])
            cards = data.get("cards", [])
            if not isinstance(cards, list) or not cards:
                continue
            valid = [
                c for c in cards
                if isinstance(c, dict) and c.get("question") and c.get("answer")
                and len(c["question"]) > 10 and len(c["answer"]) > 5
            ]
            if valid:
                return {"cards": valid}
        except Exception:
            continue
    return None


# ── Per-topic generation ─────────────────────────────────────────────────

def _generate_cards_llm(topic_title: str, knowledge: dict, gemini_key: str = None, ollama_url: str = None):
    prompt = f"""You are an educational study assistant.
Generate 8-10 concept-based Q&A flashcards using ONLY the structured Knowledge Layer JSON below. Do NOT use conversational filler.
Format each flashcard to target core concepts, definitions, procedures, best practices, and warnings from the knowledge structure. All questions and answers must be in English.
Strict Voice Rules: Use Third-Person Objective Voice Only (never use "I", "my", "we", "us", "our", "you", or conversational tokens in questions or answers).

Topic: {topic_title}
Knowledge:
{json.dumps(knowledge, indent=2)}

Return ONLY valid JSON (no markdown wrapper, no other text):
{{"cards": [{{"question": "...", "answer": "..."}}]}}"""

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
            print(f"[Gemini API] Flashcards failed: {e}")
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
            print(f"[Ollama] Flashcards failed: {e}")

    if raw:
        return _parse_cards_json(raw)
    return None


def _build_cards_heuristic(knowledge: dict, topic_title: str) -> list:
    cards = []
    
    # 1. Definition card
    definition = knowledge.get("definition", "")
    if definition:
        cards.append({
            "question": f"What is the definition of {topic_title}?",
            "answer": definition
        })
        
    # 2. Analogy card
    analogy = knowledge.get("analogy", "")
    if analogy:
        cards.append({
            "question": f"What is a helpful analogy for understanding {topic_title}?",
            "answer": analogy
        })
        
    # 3. Warning/Pitfall card
    warnings = knowledge.get("warnings", [])
    for w in warnings[:2]:
        if w:
            cards.append({
                "question": f"What is a common mistake or pitfall to avoid regarding {topic_title}?",
                "answer": w
            })
            
    # 4. Best practices card
    best_practices = knowledge.get("best_practices", [])
    for bp in best_practices[:2]:
        if bp:
            cards.append({
                "question": f"What is an important best practice for working with {topic_title}?",
                "answer": bp
            })

    # 5. Procedures/Steps card
    procedures = knowledge.get("procedures", [])
    if procedures:
        steps_str = "\n".join(f"- {step}" for step in procedures[:5])
        cards.append({
            "question": f"What are the implementation steps for {topic_title}?",
            "answer": steps_str
        })
        
    # 6. Examples card
    examples = knowledge.get("examples", [])
    for ex in examples[:2]:
        if ex:
            cards.append({
                "question": f"What is a practical example of {topic_title}?",
                "answer": ex
            })
            
    # Fallback
    if not cards:
        summary = knowledge.get("summary", f"This topic covers the key concepts of {topic_title}.")
        cards.append({
            "question": f"What is the core focus of {topic_title}?",
            "answer": summary
        })
        
    return cards


def generate_flashcards_for_single_topic(
    video_id: str, topic_index: int, storage_dir: str, ollama_url: str = OLLAMA_URL
) -> dict:
    """Generate flashcards for ONE topic. Caches in flashcards_cache/topic_N.json."""
    video_dir = os.path.join(storage_dir, video_id)
    cache_dir = os.path.join(video_dir, "flashcards_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"topic_{topic_index}.json")
    knowledge_cache_path = os.path.join(video_dir, "notes_cache", f"topic_{topic_index}_knowledge.json")

    if os.path.exists(cache_path):
        with open(cache_path, encoding='utf-8') as f:
            return json.load(f)

    topics_path = os.path.join(video_dir, "topics.json")
    if not os.path.exists(topics_path):
        return {"topic": f"Topic {topic_index}", "topic_index": topic_index, "cards": []}

    with open(topics_path, encoding='utf-8') as f:
        topics = json.load(f)

    if topic_index >= len(topics):
        return {"topic": f"Topic {topic_index}", "topic_index": topic_index, "cards": []}

    t = topics[topic_index]
    topic_title = t.get("title", f"Topic {topic_index + 1}")

    # Ensure knowledge cache is generated (generate_notes_for_single_topic will create it if missing)
    if not os.path.exists(knowledge_cache_path):
        print(f"[LearnForge Flashcards] Knowledge cache missing. Triggering notes generator to extract knowledge...")
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

    card_data = None

    # Try Gemini if key is present
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key and knowledge:
        print(f"[LearnForge Flashcards] Generating from knowledge schema using Gemini for [{topic_index}]...")
        card_data = _generate_cards_llm(topic_title, knowledge, gemini_key=gemini_key)
        
    # Try Ollama if online
    if not card_data and knowledge:
        ollama_online = check_ollama_available(ollama_url)
        if ollama_online:
            print(f"[LearnForge Flashcards] Generating from knowledge schema using Ollama for [{topic_index}]...")
            card_data = _generate_cards_llm(topic_title, knowledge, ollama_url=ollama_url)

    # Heuristic fallback (using knowledge fields directly)
    if not card_data:
        print(f"[LearnForge Flashcards] Heuristic fallback generation for [{topic_index}]...")
        card_data = {"cards": _build_cards_heuristic(knowledge, topic_title)}

    result = {
        "topic": topic_title,
        "topic_index": topic_index,
        "cards": card_data.get("cards", []) if card_data else [],
    }

    with open(cache_path, "w", encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result
