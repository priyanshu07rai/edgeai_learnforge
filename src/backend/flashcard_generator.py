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
import tempfile
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
    
    # Atomic write to prevent race conditions
    dir_name = os.path.dirname(cards_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, cards_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
    print(f"[LearnForge Flashcards] Saved flashcards.json for {video_id}.")
    return result


def _call_ollama_for_cards(topic_title: str, notes_markdown: str, ollama_url: str):
    prompt = f"""You are

CRITICAL RULE: You MUST write your entire response exclusively in English. If the input contains Hindi, Hinglish, or Devanagari characters, TRANSLATE it to English. DO NOT output any Hindi or Devanagari characters.
 an expert educator.
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
    prompt = f"""You are a senior educational content specialist creating active-recall flashcards.

CRITICAL RULE: You MUST write your entire response exclusively in English. If the input contains Hindi, Hinglish, or Devanagari characters, TRANSLATE it to English. DO NOT output any Hindi or Devanagari characters.

Your task: Generate 6-8 HIGH-QUALITY concept-focused flashcards for the topic "{topic_title}" using ONLY facts from the Knowledge Layer JSON below.

# Flashcard Quality Rules
1. FORBIDDEN question types: "What is the definition of..." or "What does X mean?" — these are shallow.
2. REQUIRED question depth — use these question patterns:
   - "Why does [concept] work this way?"
   - "What is the key difference between X and Y?"
   - "In what scenario would you use [concept]?"
   - "What happens if [condition] is not met?"
   - "How does [concept] achieve [outcome]?"
   - "What is the most common mistake when working with [concept]?"
   - "What is the practical significance of [concept]?"
3. Each card must teach ONE clear idea — no compound questions.
4. AVOID duplicate or near-duplicate cards covering the same fact.
5. Prioritize: conceptual reasoning > applications > warnings > procedures.
6. Every card must have a 'type' field (one of: "conceptual", "application", "misconception", "insight").
7. Every card must have a 'hint' field — a single short sentence that nudges toward the answer without giving it away.

# Voice Rules
- Use Third-Person Objective Voice Only.
- Never use "I", "my", "we", "us", "our", "you", or "let's".

Topic: {topic_title}
Knowledge:
{json.dumps(knowledge, indent=2)}

Return ONLY valid JSON (no markdown wrapper, no other text):
{{"cards": [
  {{"question": "...", "answer": "...", "type": "conceptual", "hint": "Think about the core purpose..."}},
  {{"question": "...", "answer": "...", "type": "application", "hint": "Consider a real-world use case..."}}
]}}"""

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
                timeout=40,
            )
            if resp.status_code == 200:
                raw = resp.json().get("response", "").strip()
        except Exception as e:
            print(f"[Ollama] Flashcards failed: {e}")

    if raw:
        return _parse_cards_json(raw)
    return None


def _build_cards_heuristic(knowledge: dict, topic_title: str) -> list:
    """Build typed, concept-rich flashcards from knowledge fields without an LLM."""
    cards = []

    # 1. Why/How the concept works — from explanation
    explanation = knowledge.get("explanation", "")
    if explanation and len(explanation) > 30:
        # Take the most informative sentence as the core reasoning card
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', explanation) if len(s.strip()) > 20]
        if sents:
            cards.append({
                "question": f"How does {topic_title} work, and why is it designed that way?",
                "answer": sents[0] if len(sents) == 1 else " ".join(sents[:3]),
                "type": "conceptual",
                "hint": "Think about the core mechanism and purpose."
            })

    # 2. Definition — one card, reframed as a reasoning question
    definition = knowledge.get("definition", "")
    if definition:
        cards.append({
            "question": f"What is {topic_title} and what problem does it solve?",
            "answer": definition,
            "type": "conceptual",
            "hint": "Focus on its role and the problem it addresses."
        })

    # 3. Application card — from applications list
    applications = knowledge.get("applications", [])
    for app in applications[:2]:
        if app and len(app) > 15:
            cards.append({
                "question": f"In what real-world scenario is {topic_title} most useful?",
                "answer": app,
                "type": "application",
                "hint": "Think about a concrete use case or industry context."
            })
            break  # one application card is enough

    # 4. Analogy card
    analogy = knowledge.get("analogy", "")
    if analogy:
        cards.append({
            "question": f"What real-world analogy best illustrates how {topic_title} works?",
            "answer": analogy,
            "type": "insight",
            "hint": "Think about an everyday object or system with similar behavior."
        })

    # 5. Misconception card
    misconceptions = knowledge.get("misconceptions", [])
    for m in misconceptions[:1]:
        if m:
            cards.append({
                "question": f"What is a common misconception about {topic_title}?",
                "answer": m,
                "type": "misconception",
                "hint": "Think about what people often assume incorrectly."
            })

    # 6. Warning/Pitfall card
    warnings = knowledge.get("warnings", [])
    for w in warnings[:1]:
        if w:
            cards.append({
                "question": f"What critical mistake should be avoided when working with {topic_title}?",
                "answer": w,
                "type": "misconception",
                "hint": "Think about a step that is easy to skip but causes problems."
            })

    # 7. Best practice card
    best_practices = knowledge.get("best_practices", [])
    for bp in best_practices[:1]:
        if bp:
            cards.append({
                "question": f"What is the most important best practice to follow with {topic_title}?",
                "answer": bp,
                "type": "insight",
                "hint": "Think about what experienced practitioners always do."
            })

    # 8. Steps card — procedural
    procedures = knowledge.get("procedures", [])
    if len(procedures) >= 2:
        steps_str = " → ".join(p.strip().rstrip('.') for p in procedures[:5])
        cards.append({
            "question": f"What are the key steps involved in implementing {topic_title}?",
            "answer": steps_str,
            "type": "application",
            "hint": "Think about the sequence of actions required."
        })

    # 9. Example card
    examples = knowledge.get("examples", [])
    for ex in examples[:1]:
        if ex and len(ex) > 15:
            cards.append({
                "question": f"What is a practical example that demonstrates {topic_title}?",
                "answer": ex,
                "type": "application",
                "hint": "Think about a specific scenario or code example from the lecture."
            })

    # Fallback
    if not cards:
        summary = knowledge.get("summary", f"This topic covers the key concepts of {topic_title}.")
        cards.append({
            "question": f"What is the core significance of {topic_title}?",
            "answer": summary,
            "type": "conceptual",
            "hint": "Think about why this concept matters in practice."
        })

    # Deduplicate by question similarity
    seen_q = set()
    deduped = []
    for card in cards:
        q_key = re.sub(r'[^a-z0-9]', '', card['question'].lower())[:60]
        if q_key not in seen_q:
            seen_q.add(q_key)
            deduped.append(card)

    return deduped


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
