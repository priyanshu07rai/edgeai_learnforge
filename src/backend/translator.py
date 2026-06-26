"""
translator.py — Reliable Hindi→English translation.
Uses deep-translator (Google Translate, free, no API key).
Caches per-topic. Retries failed chunks. Never fails permanently.
"""
import os
import json
import time

_translator_available = None       # None=unchecked, True=ok, False=import error
_last_failure_time = 0             # Track when network last failed (retry after 30s)
_RETRY_COOLDOWN = 30               # Seconds before retrying after network failure
CHUNK_SIZE = 2000                  # Smaller = more reliable (original was 4500)
MAX_RETRIES = 2                    # Retries per chunk


def detect_language(text: str) -> str:
    """Returns 'en', 'hi', or 'mix'."""
    if not text or not text.strip():
        return 'en'
    total = max(len(text), 1)
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    ratio = ascii_chars / total
    if ratio > 0.82:
        return 'en'
    if ratio < 0.38:
        return 'hi'
    return 'mix'


def translate_to_english(text: str, cache_path: str = None, label: str = "") -> str:
    """
    Translate text to English.
    - Returns original if already English.
    - Caches result to disk.
    - Retries each chunk up to MAX_RETRIES times.
    - Never permanently disables — retries after _RETRY_COOLDOWN seconds.
    - Returns partial translation if some chunks succeed.
    """
    global _translator_available, _last_failure_time

    if not text or not text.strip():
        return text

    lang = detect_language(text)
    if lang == 'en':
        return text

    # ── Disk cache ────────────────────────────────────────────────────────
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding='utf-8') as f:
                cached = json.load(f)
            translated = cached.get('translated', '')
            # Validate cached translation is actually English
            if translated and detect_language(translated) == 'en':
                print(f"[Translator] Cache hit {label}")
                return translated
        except Exception:
            pass

    # ── Import check ──────────────────────────────────────────────────────
    if _translator_available is None or _translator_available == 'import_error':
        try:
            from deep_translator import GoogleTranslator
            _translator_available = True
        except ImportError:
            _translator_available = 'import_error'
            print("[Translator] deep-translator not installed. Run: pip install deep-translator")
            return text

    if _translator_available == 'import_error':
        return text

    # ── Network cooldown check ────────────────────────────────────────────
    if _last_failure_time > 0:
        elapsed = time.time() - _last_failure_time
        if elapsed < _RETRY_COOLDOWN:
            print(f"[Translator] Network cooldown ({int(_RETRY_COOLDOWN - elapsed)}s left) {label}")
            return text
        else:
            print(f"[Translator] Retrying after cooldown {label}")

    # ── Translate chunk by chunk ──────────────────────────────────────────
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        return text

    chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    translated_parts = []
    any_success = False

    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if not chunk:
            continue

        chunk_result = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[Translator] Chunk {i+1}/{len(chunks)} attempt {attempt} ({len(chunk)} chars) {label}")
                result = GoogleTranslator(source='auto', target='en').translate(chunk)
                if result and detect_language(result) != 'hi':
                    chunk_result = result
                    any_success = True
                    _last_failure_time = 0  # Reset failure timer on success
                    break
                else:
                    print(f"[Translator] Chunk {i+1} returned non-English, retrying...")
            except Exception as e:
                print(f"[Translator] Chunk {i+1} attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(1)

        if chunk_result:
            translated_parts.append(chunk_result)
        else:
            print(f"[Translator] Chunk {i+1} failed all retries - skipping")
            # Don't include failed Hindi chunk in output
            # (better to have partial English than mixed Hindi+English)

    if not any_success:
        _last_failure_time = time.time()
        print(f"[Translator] All chunks failed {label}")
        return text  # Return original — caller handles gracefully

    translated = ' '.join(translated_parts).strip()

    # Validate: if output is still mostly Hindi, don't use it
    if translated and detect_language(translated) == 'hi':
        print(f"[Translator] Output still Hindi after translation {label}")
        return text

    print(f"[Translator] Done: {len(text)} -> {len(translated)} chars {label}")

    # ── Cache ─────────────────────────────────────────────────────────────
    if cache_path and translated:
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'original_lang': lang,
                    'original_len': len(text),
                    'translated': translated,
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Translator] Cache write failed: {e}")

    return translated


def make_cache_path(video_dir: str, topic_id: str) -> str:
    return os.path.join(video_dir, "translations", f"{topic_id}.json")
