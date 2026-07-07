"""
qa_engine.py — Redesigned educational tutor Q&A engine.
Supports four modes: transcript, teacher (default), knowledge, hybrid.
Detects user intent (Comparison, Analogy, Code, Procedure, Definition).
Formats structured answers with three-layer educational layout + sources.
Falls back to cached knowledge JSON when offline.
"""
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

import os
import json
import re
import numpy as np
import faiss
import requests
from vector_db import get_embedding_model, search_index
from translator import detect_language, translate_to_english

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:1b"


def _safe(text, limit=200):
    return str(text)[:limit].encode('ascii', errors='replace').decode('ascii')


def _detect_intent(question: str) -> str:
    q_lower = question.lower()
    if any(k in q_lower for k in ["compare", "vs", "difference", "distinguish", "contrast", "comparison"]):
        return "Comparison"
    elif any(k in q_lower for k in ["analogy", "like a", "similar to", "metaphor", "analogue"]):
        return "Analogy"
    elif any(k in q_lower for k in ["code", "python", "javascript", "function", "implement", "snippet", "class", "write a program", "code example", "script"]):
        return "Code"
    elif any(k in q_lower for k in ["how to", "steps", "procedure", "guide", "setup", "install", "configure", "run", "execute", "tutorial"]):
        return "Procedure"
    elif any(k in q_lower for k in ["what is", "define", "meaning", "concept", "explain", "definition"]):
        return "Definition"
    else:
        return "General"


def _clean_filler_for_qa(text: str) -> str:
    if not text:
        return text
    # Clean common intro banter
    text = re.sub(r'^(alright\s+)?(so\s+)?(hey\s+)?(everyone|welcome\s+back)(\s+welcome\s+back)?\s*(to\s+another\s+exciting\s+video)?\s*(and\s+)?(in\s+this\s+video)?\s*(let\'s|let\s+s)\s+talk\s+about\s+', '', text, flags=re.I)
    text = re.sub(r'^(alright\s+)?(so\s+)?(hey\s+)?(everyone|welcome\s+back|welcome)\s+', '', text, flags=re.I)
    # Clean mid-sentence speech fillers
    text = re.sub(r'\b(so\s+you\s+know|you\s+know|basically|essentially|really|actually|uh|um)\b', '', text, flags=re.I)
    # Clean spacing
    text = re.sub(r'\s+', ' ', text).strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def _find_timestamp_for_chunk(chunk_text: str, segments: list) -> str:
    if not segments:
        return "00:00"

    def clean(t):
        return re.sub(r'[^a-zA-Z0-9]', '', t.lower())

    chunk_cleaned = clean(chunk_text)
    if not chunk_cleaned:
        return "00:00"

    best_start = None
    best_overlap = 0

    for seg in segments:
        seg_text = seg.get("text", "")
        seg_cleaned = clean(seg_text)
        if not seg_cleaned:
            continue

        if seg_cleaned in chunk_cleaned:
            idx = chunk_cleaned.find(seg_cleaned)
            score = 1000 - idx
            if score > best_overlap:
                best_overlap = score
                best_start = seg.get("start", 0.0)

    if best_start is not None:
        mins = int(best_start // 60)
        secs = int(best_start % 60)
        return f"{mins:02d}:{secs:02d}"

    # Fallback: word overlap
    chunk_words = set(re.findall(r'\b\w{3,}\b', chunk_text.lower()))
    if not chunk_words:
        return "00:00"

    best_seg = segments[0]
    max_overlap = -1
    for seg in segments:
        seg_words = set(re.findall(r'\b\w{3,}\b', seg.get("text", "").lower()))
        overlap = len(chunk_words & seg_words)
        if overlap > max_overlap:
            max_overlap = overlap
            best_seg = seg

    start_sec = best_seg.get("start", 0.0)
    mins = int(start_sec // 60)
    secs = int(start_sec % 60)
    return f"{mins:02d}:{secs:02d}"


def _build_prompt(question: str, context: str, mode: str, intent: str) -> str:
    prompt = f"""You are

CRITICAL RULE: You MUST write your entire response exclusively in English. If the input contains Hindi, Hinglish, or Devanagari characters, TRANSLATE it to English. DO NOT output any Hindi or Devanagari characters.
 an advanced agentic AI educational tutor. Your goal is to explain concepts clearly, accurately, and educationally.
You must always structure your response using these three section headers exactly. Do not omit any header. Do NOT output a '### 📖 Sources' header as it will be appended automatically.

### 🧠 General Explanation
[Your explanation goes here]

### 📚 What this course teaches
[What the course context teaches goes here]

### 💡 Extra Tip
[Your extra tip, best practice, warning, or advice goes here]

---
Current Mode: {mode.upper()}
Detected Intent: {intent.upper()}
"""

    intent_instructions = ""
    if intent == "Comparison":
        intent_instructions = "The user is asking for a comparison. Under '🧠 General Explanation', you MUST generate a clean markdown table comparing the key aspects/features (e.g. `| Feature | Entity 1 | Entity 2 |`)."
    elif intent == "Analogy":
        intent_instructions = "The user is asking for an analogy. Under '🧠 General Explanation', provide a memorable, clear, and rich analogy (e.g., comparing software to physical objects) to make the concept intuitive."
    elif intent == "Code":
        intent_instructions = "The user is asking for code. Under '🧠 General Explanation', provide a clear, clean, and well-commented code snippet."
    elif intent == "Procedure":
        intent_instructions = "The user is asking for a procedure. Under '🧠 General Explanation', present a structured, chronological step-by-step guide (using numbered lists 1., 2. etc.)."
    elif intent == "Definition":
        intent_instructions = "The user is asking for a definition. Under '🧠 General Explanation', provide a formal, precise definition followed by a simple explanation."
    else:
        intent_instructions = "Under '🧠 General Explanation', explain the concepts clearly, highlighting key terms and keeping the explanation highly structured and easy to read."

    prompt += f"\nIntent Guideline:\n{intent_instructions}\n"

    if mode == "transcript":
        prompt += """
Grounding Rule:
You are in TRANSCRIPT mode (strict grounding).
- Answer the question using ONLY the provided course sources context below.
- Do NOT use any external or general knowledge.
- If the answer is not in the sources, say "This topic is not covered in the transcript." in the sections.
- For both '🧠 General Explanation' and '📚 What this course teaches', restrict yourself 100% to the sources context.
"""
    elif mode == "teacher":
        prompt += """
Grounding Rule:
You are in TEACHER mode (default).
- Use the provided course sources context below as the primary reference.
- Explain the concepts in your own words like a helpful, clear teacher.
- Do NOT introduce advanced external tools or framework details unless they are relevant to explaining the concepts in the sources.
"""
    elif mode == "knowledge":
        prompt += """
Grounding Rule:
You are in KNOWLEDGE mode (general knowledge).
- Ignore the course context. Answer the student using your own general programming knowledge and computer science understanding.
- In the '📚 What this course teaches' section, explain that this concept is answered from general knowledge rather than course context.
"""
    elif mode == "hybrid":
        prompt += """
Grounding Rule:
You are in HYBRID mode (merged context + general knowledge).
- Combine the provided course sources context with your own general programming knowledge.
- Under '🧠 General Explanation', provide a comprehensive conceptual explanation using both.
- Under '📚 What this course teaches', specify what the provided course sources context teaches.
"""

    if mode != "knowledge" and context:
        prompt += f"\nCourse Sources Context:\n{context}\n"
    else:
        prompt += "\nNo Course Sources Context is provided for this query.\n"

    prompt += f"\nStudent Question: {question}\n\nStructured Answer:"
    return prompt


def _llm_answer(question: str, context: str, mode: str, intent: str, temperature: float = 0.3) -> str:
    prompt = _build_prompt(question, context, mode, intent)
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature
            }
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=25)
            if resp.status_code == 200:
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw and len(raw) > 10:
                    return raw
            else:
                print(f"[LearnForge QA] Gemini API error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"[LearnForge QA] Gemini API exception: {e}")

    # Fallback to Ollama
    try:
        payload = {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        resp = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=25,
        )
        if resp.status_code == 200:
            raw = resp.json().get("response", "").strip()
            if raw and len(raw) > 10:
                return raw
    except Exception as e:
        print(f"[LearnForge QA] Ollama LLM failed: {e}")

    return ""


def _ensure_headers(text: str) -> str:
    text = re.sub(r'#+\s*🧠?\s*General\s+Explanation\s*', '\n\n### 🧠 General Explanation\n', text, flags=re.I)
    text = re.sub(r'#+\s*📚?\s*What\s+this\s+course\s+teaches\s*', '\n\n### 📚 What this course teaches\n', text, flags=re.I)
    text = re.sub(r'#+\s*💡?\s*Extra\s+Tip\s*', '\n\n### 💡 Extra Tip\n', text, flags=re.I)

    has_general = "### 🧠 General Explanation" in text
    has_course = "### 📚 What this course teaches" in text
    has_tip = "### 💡 Extra Tip" in text

    if has_general and has_course and has_tip:
        return text.strip()

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) >= 3:
        general = paragraphs[0]
        course = "\n\n".join(paragraphs[1:-1])
        tip = paragraphs[-1]
    elif len(paragraphs) == 2:
        general = paragraphs[0]
        course = paragraphs[1]
        tip = "Try applying this concept in a small test project to see how it works in practice."
    else:
        general = text
        course = "This concept is discussed in detail in the course lecture."
        tip = "Try applying this concept in a small test project to see how it works in practice."

    return f"""### 🧠 General Explanation
{general}

### 📚 What this course teaches
{course}

### 💡 Extra Tip
{tip}"""


def _build_sources_section(results: list, topics_list: list, transcript_data: dict, mode: str) -> str:
    if mode == "knowledge":
        return "### 📖 Sources\n- **Concept**: General Programming Knowledge (Knowledge Mode) — Confidence: High"

    if not results:
        return "### 📖 Sources\n- **Concept**: Course Context — Confidence: Low"

    sources_md = []
    for r in results:
        topic_id = r.get("topic_id", "")
        topic_title = "General Lecture"
        if topic_id.startswith("topic_"):
            try:
                t_idx = int(topic_id.split("_")[1])
                if t_idx < len(topics_list):
                    topic_title = topics_list[t_idx].get("title", f"Topic {t_idx}")
            except Exception:
                pass

        child_text = r.get("child_text", "")
        segments = transcript_data.get("segments", [])
        timestamp = _find_timestamp_for_chunk(child_text, segments)

        score = r.get("score", 1.0)
        if score >= 0.5:
            confidence = "High"
        elif score >= 0.3:
            confidence = "Medium"
        else:
            confidence = "Low"

        sources_md.append(f"- **Topic**: {topic_title} (Timestamp: {timestamp}) — Confidence: {confidence}")

    return "### 📖 Sources\n" + "\n".join(sources_md)


def _build_fallback_answer(video_dir: str, question: str, topic_index: int, topics_list: list) -> tuple[str, list]:
    notes_cache_dir = os.path.join(video_dir, "notes_cache")
    if not os.path.exists(notes_cache_dir):
        return "No local cache found. Please process this video online first.", []

    candidates = []
    if topic_index >= 0:
        k_path = os.path.join(notes_cache_dir, f"topic_{topic_index}_knowledge.json")
        if os.path.exists(k_path):
            candidates.append((topic_index, k_path))
    else:
        # Search all topics
        for filename in os.listdir(notes_cache_dir):
            if filename.startswith("topic_") and filename.endswith("_knowledge.json"):
                m = re.match(r"topic_(\d+)_knowledge.json", filename)
                if m:
                    idx = int(m.group(1))
                    candidates.append((idx, os.path.join(notes_cache_dir, filename)))

    if not candidates:
        return "No local knowledge cache found for this topic.", []

    q_words = set(re.findall(r'\b\w{3,}\b', question.lower()))
    best_idx = -1
    best_k_data = None
    best_overlap = -1

    for idx, path in candidates:
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue

        keywords = set()
        for k in ["concept", "topic_title"]:
            val = data.get(k, "")
            if isinstance(val, str):
                keywords.update(re.findall(r'\b\w{3,}\b', val.lower()))
        for k in ["terms", "keywords"]:
            val = data.get(k, [])
            if isinstance(val, list):
                keywords.update(str(x).lower() for x in val)

        overlap = len(q_words & keywords)
        if overlap > best_overlap:
            best_overlap = overlap
            best_idx = idx
            best_k_data = data

    if not best_k_data:
        idx, path = candidates[0]
        try:
            with open(path, encoding='utf-8') as f:
                best_k_data = json.load(f)
                best_idx = idx
        except Exception:
            return "Failed to load fallback knowledge cache.", []

    intent = _detect_intent(question)
    explanation_parts = []

    if intent == "Comparison":
        comparisons = best_k_data.get("comparisons", [])
        if comparisons:
            table_lines = ["| Feature | Details |", "| --- | --- |"]
            for comp in comparisons:
                if isinstance(comp, str):
                    table_lines.append(f"| Comparison | {_clean_filler_for_qa(comp)} |")
                elif isinstance(comp, dict):
                    feat = comp.get("feature", "Detail")
                    val = comp.get("value", "") or comp.get("text", "")
                    table_lines.append(f"| {feat} | {_clean_filler_for_qa(val)} |")
            explanation_parts.append("\n".join(table_lines))
        else:
            concept_name = best_k_data.get("concept") or best_k_data.get("topic_title") or "Concept"
            desc = _clean_filler_for_qa(best_k_data.get("definition") or best_k_data.get("summary") or "No detail available.")
            explanation_parts.append(f"| Term | Description |\n| --- | --- |\n| {concept_name} | {desc} |")
    elif intent == "Analogy":
        analogy = best_k_data.get("analogy") or best_k_data.get("analogies")
        if analogy:
            if isinstance(analogy, list):
                explanation_parts.extend(_clean_filler_for_qa(str(x)) for x in analogy)
            else:
                explanation_parts.append(_clean_filler_for_qa(str(analogy)))
        else:
            explanation_parts.append(_clean_filler_for_qa(best_k_data.get("explanation") or best_k_data.get("summary") or "No analogy available."))
    elif intent == "Code":
        code = best_k_data.get("code")
        if code:
            if isinstance(code, list):
                explanation_parts.append("```python\n" + "\n".join(code) + "\n```")
            else:
                explanation_parts.append("```python\n" + str(code) + "\n```")
        else:
            explanation_parts.append("No code snippet available in course cache.")
    elif intent == "Procedure":
        steps = best_k_data.get("procedures") or best_k_data.get("steps")
        if steps:
            for i, step in enumerate(steps):
                explanation_parts.append(f"{i+1}. {_clean_filler_for_qa(step)}")
        else:
            explanation_parts.append(_clean_filler_for_qa(best_k_data.get("explanation") or best_k_data.get("summary") or "No step-by-step procedure available."))
    else:
        definition = best_k_data.get("definition") or best_k_data.get("definitions")
        if definition:
            if isinstance(definition, list) and definition:
                explanation_parts.append(_clean_filler_for_qa(definition[0]))
            else:
                explanation_parts.append(_clean_filler_for_qa(str(definition)))
        
        explanation = best_k_data.get("explanation")
        if explanation:
            explanation_parts.append(_clean_filler_for_qa(str(explanation)))

    # Deduplicate explanation parts to prevent raw repetition
    seen_parts = set()
    unique_parts = []
    for p in explanation_parts:
        if p and p not in seen_parts:
            seen_parts.add(p)
            unique_parts.append(p)
    general_explanation = "\n\n".join(unique_parts)

    # 2. What this course teaches (Clean bullets instead of duplicating general explanation)
    teaches_bullets = []
    for key in ["features", "steps", "best_practices", "important"]:
        val = best_k_data.get(key, [])
        if isinstance(val, list):
            for x in val:
                cleaned = _clean_filler_for_qa(str(x))
                if len(cleaned) > 20 and cleaned not in teaches_bullets:
                    teaches_bullets.append(cleaned)
                    
    # If we don't have enough specific bullets, use ranked_sentences
    if len(teaches_bullets) < 3:
        ranked = best_k_data.get("ranked_sentences", [])
        if isinstance(ranked, list):
            for x in ranked:
                cleaned = _clean_filler_for_qa(str(x))
                if len(cleaned) > 20 and cleaned not in teaches_bullets:
                    teaches_bullets.append(cleaned)
                    
    if teaches_bullets:
        course_teaches = "\n".join(f"- {b}" for b in teaches_bullets[:4])
    else:
        course_teaches = _clean_filler_for_qa(best_k_data.get("summary") or best_k_data.get("explanation") or "The course discusses the core concept and its implementations.")

    extra_tips = []
    for key in ["best_practices", "warnings", "misconceptions", "important"]:
        val = best_k_data.get(key, [])
        if val:
            if isinstance(val, list):
                extra_tips.extend(val)
            else:
                extra_tips.append(str(val))
    extra_tip = _clean_filler_for_qa(extra_tips[0]) if extra_tips else "Focus on the practical implementations and check dependencies carefully."

    topic_title = best_k_data.get("topic_title") or best_k_data.get("concept") or f"Topic {best_idx}"

    answer_md = f"""### 🧠 General Explanation
{general_explanation}

### 📚 What this course teaches
{course_teaches}

### 💡 Extra Tip
{extra_tip}

### 📖 Sources
- **Topic**: {topic_title} (Fallback Cache) — Confidence: High (Cached Knowledge)"""

    return answer_md, [best_k_data.get("concept") or topic_title]


def answer_question(
    video_id: str,
    storage_dir: str,
    question: str,
    topic_index: int = -1,   # -1 = search all topics
    top_k: int = 3,
    mode: str = "teacher",
) -> dict:
    """
    Answer a question about video content using RAG with Parent-Child retrieval.
    Supports four modes: transcript, teacher, knowledge, hybrid.
    """
    video_dir = os.path.join(storage_dir, video_id)
    faiss_path = os.path.join(video_dir, "faiss.index")
    chunks_path = os.path.join(video_dir, "chunks.json")
    topics_path = os.path.join(video_dir, "topics.json")
    transcript_path = os.path.join(video_dir, "transcript.json")

    if mode != "knowledge" and (not os.path.exists(faiss_path) or not os.path.exists(chunks_path)):
        return {
            "answer": "No index found for this video. Please process the video first.",
            "sources": [],
            "error": "no_index"
        }

    q_lang = detect_language(question)
    if q_lang in ('hi', 'mix'):
        question_en = translate_to_english(question, label="[qa-question]")
    else:
        question_en = question

    intent = _detect_intent(question_en)

    topics_list = []
    if os.path.exists(topics_path):
        try:
            with open(topics_path, encoding='utf-8') as f:
                topics_list = json.load(f)
        except Exception as e:
            print(f"[LearnForge QA] Failed to load topics.json: {e}")

    transcript_data = {}
    if os.path.exists(transcript_path):
        try:
            with open(transcript_path, encoding='utf-8') as f:
                transcript_data = json.load(f)
        except Exception as e:
            print(f"[LearnForge QA] Failed to load transcript.json: {e}")

    results = []
    sources_en = []

    if mode != "knowledge":
        q_lower = question_en.lower()
        broad_patterns = ["what topics", "summarize", "overview", "what does", "explain everything",
                          "what is covered", "all concepts", "full summary", "entire"]
        is_broad_query = any(p in q_lower for p in broad_patterns) or len(q_lower.split()) <= 3
        effective_k = 6 if is_broad_query else top_k

        topic_filter = f"topic_{topic_index}" if topic_index >= 0 else None
        results = search_index(video_dir, question_en, top_k=effective_k, topic_id=topic_filter)

        if not results:
            if os.path.exists(chunks_path):
                try:
                    with open(chunks_path, encoding='utf-8') as f:
                        chunks = json.load(f)
                    if topic_index >= 0:
                        filtered_chunks = [c for c in chunks if c.get("topic_id") == f"topic_{topic_index}"]
                    else:
                        filtered_chunks = chunks
                    results = [{"parent_text": c["text"], "child_text": c["text"], "topic_id": c.get("topic_id", "")}
                               for c in filtered_chunks[:effective_k]]
                except Exception:
                    pass

        if results:
            sources_raw = [r.get("parent_text") or r.get("child_text", "") for r in results]
            for chunk_text in sources_raw:
                lang = detect_language(chunk_text)
                if lang in ('hi', 'mix'):
                    translated = translate_to_english(chunk_text, label="[qa-chunk]")
                    sources_en.append(translated if translated else chunk_text)
                else:
                    sources_en.append(chunk_text)

    context = "\n\n".join(f"[Source {i+1}]\n{s}" for i, s in enumerate(sources_en))
    temperature = 0.0 if mode == "transcript" else 0.3

    answer = ""
    if mode == "transcript" and not sources_en:
        answer = "This topic is not covered in the transcript."
    else:
        answer = _llm_answer(question_en, context, mode, intent, temperature)

    if answer:
        answer = _ensure_headers(answer)
        sources_section = _build_sources_section(results, topics_list, transcript_data, mode)
        answer = f"{answer}\n\n{sources_section}"
    else:
        print("[LearnForge QA] LLM offline/failed. Using heuristic fallback.")
        answer, fallback_sources = _build_fallback_answer(video_dir, question_en, topic_index, topics_list)
        sources_en = fallback_sources

    print(f"[LearnForge QA] Q: {_safe(question_en)} | A: {_safe(answer)}")

    return {
        "answer": answer,
        "sources": [s[:300] + "..." if len(s) > 300 else s for s in sources_en[:3]]
    }
