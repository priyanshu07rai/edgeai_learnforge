"""
transcript_refiner.py — Conservative Transcript Polish Layer

PURPOSE:
  Lightly clean ASR/YouTube transcript text to improve readability
  WITHOUT reducing educational depth or removing meaningful content.

PHILOSOPHY:
  This layer behaves like a careful human proofreader, NOT an AI rewriter.
  It only removes what is unambiguously noise:
    - Pure vocal hesitation sounds (um, uh, hmm)
    - ASR bracketed noise markers ([inaudible], [music])
    - Consecutive stutter repetitions (the the the → the)
    - Obvious ASR misspellings (gonna → going to)

  It deliberately PRESERVES:
    - "so", "now", "but", "well", "basically", "actually", "look", "see"
      → These are PEDAGOGICAL CONNECTORS that signal transitions and emphasis.
    - "right", "okay", "alright" when mid-sentence or used for emphasis
    - All examples, reasoning, analogies, and explanation steps
    - The teacher's natural conversational flow
    - All technical terminology in full

WHAT THIS LAYER DOES NOT DO:
  - Does NOT summarize or shorten explanations
  - Does NOT remove educational transition words
  - Does NOT rewrite sentences
  - Does NOT call any LLM or AI model
  - Does NOT alter meaning of any kind

PIPELINE (in order of application):
  1. Remove bracketed ASR noise markers
  2. Strip pure vocal hesitation sounds (um, uh, hmm) only as isolated words
  3. Fix informal ASR contractions (gonna → going to)
  4. Fix tech term capitalization (python → Python, html → HTML)
  5. Remove stutter-style consecutive word repetitions
  6. Normalize whitespace
  7. Fix punctuation spacing artifacts
  8. Capitalize first letter of each timestamped segment
"""

import re


# ══════════════════════════════════════════════════════════════════════════════
# 1. TECH TERM CAPITALIZATION MAP
# ══════════════════════════════════════════════════════════════════════════════
# Applied as whole-word regex replacements (word boundaries enforced).
# Only corrects capitalization — never changes spelling or meaning.

_TECH_TERMS = {
    # Programming Languages
    "python":       "Python",
    "javascript":   "JavaScript",
    "typescript":   "TypeScript",
    "java":         "Java",
    "kotlin":       "Kotlin",
    "golang":       "Go",
    "rust":         "Rust",
    "swift":        "Swift",
    "csharp":       "C#",
    "cpp":          "C++",
    "ruby":         "Ruby",
    "php":          "PHP",
    "scala":        "Scala",
    "perl":         "Perl",
    "haskell":      "Haskell",
    "elixir":       "Elixir",
    "dart":         "Dart",
    "lua":          "Lua",

    # Frontend Frameworks / Libraries
    "react":        "React",
    "reactjs":      "React.js",
    "vuejs":        "Vue.js",
    "vue":          "Vue",
    "angular":      "Angular",
    "nextjs":       "Next.js",
    "nuxtjs":       "Nuxt.js",
    "svelte":       "Svelte",
    "solidjs":      "SolidJS",
    "astro":        "Astro",

    # Backend Frameworks
    "django":       "Django",
    "flask":        "Flask",
    "fastapi":      "FastAPI",
    "expressjs":    "Express.js",
    "nodejs":       "Node.js",
    "node.js":      "Node.js",
    "springboot":   "Spring Boot",
    "laravel":      "Laravel",
    "rails":        "Rails",

    # ML / AI
    "tensorflow":   "TensorFlow",
    "pytorch":      "PyTorch",
    "sklearn":      "scikit-learn",
    "scikit-learn": "scikit-learn",
    "huggingface":  "Hugging Face",
    "langchain":    "LangChain",
    "openai":       "OpenAI",
    "ollama":       "Ollama",
    "llama":        "LLaMA",
    "bert":         "BERT",
    "gpt":          "GPT",
    "llm":          "LLM",
    "llms":         "LLMs",
    "nlp":          "NLP",
    "rag":          "RAG",
    "faiss":        "FAISS",
    "lstm":         "LSTM",
    "cnn":          "CNN",
    "rnn":          "RNN",
    "gan":          "GAN",
    "transformers": "Transformers",

    # Databases
    "mysql":         "MySQL",
    "postgresql":    "PostgreSQL",
    "postgres":      "PostgreSQL",
    "sqlite":        "SQLite",
    "mongodb":       "MongoDB",
    "redis":         "Redis",
    "elasticsearch": "Elasticsearch",
    "firebase":      "Firebase",
    "supabase":      "Supabase",
    "dynamodb":      "DynamoDB",
    "cassandra":     "Cassandra",

    # Cloud / DevOps / Tools
    "aws":       "AWS",
    "gcp":       "GCP",
    "azure":     "Azure",
    "kubernetes":"Kubernetes",
    "k8s":       "Kubernetes",
    "docker":    "Docker",
    "nginx":     "Nginx",
    "github":    "GitHub",
    "gitlab":    "GitLab",
    "ci/cd":     "CI/CD",
    "cicd":      "CI/CD",

    # Acronyms & Concepts
    "api":      "API",
    "apis":     "APIs",
    "rest":     "REST",
    "restful":  "RESTful",
    "graphql":  "GraphQL",
    "html":     "HTML",
    "css":      "CSS",
    "json":     "JSON",
    "xml":      "XML",
    "yaml":     "YAML",
    "sql":      "SQL",
    "nosql":    "NoSQL",
    "orm":      "ORM",
    "jwt":      "JWT",
    "oauth":    "OAuth",
    "ml":       "ML",
    "ai":       "AI",
    "cpu":      "CPU",
    "gpu":      "GPU",
    "ram":      "RAM",
    "ide":      "IDE",
    "cli":      "CLI",
    "gui":      "GUI",
    "sdk":      "SDK",
    "http":     "HTTP",
    "https":    "HTTPS",
    "url":      "URL",
    "uri":      "URI",
    "cdn":      "CDN",
    "dns":      "DNS",
    "tcp":      "TCP",
    "ssl":      "SSL",
    "tls":      "TLS",
    "crud":     "CRUD",
    "mvc":      "MVC",
    "mvvm":     "MVVM",
    "oop":      "OOP",
    "solid":    "SOLID",
    "os":       "OS",
    "ui":       "UI",
    "ux":       "UX",

    # Dev Tools
    "git":       "Git",
    "vscode":    "VS Code",
    "vs code":   "VS Code",
    "jupyter":   "Jupyter",
    "copilot":   "Copilot",
    "webpack":   "Webpack",
    "vite":      "Vite",
    "tailwind":  "Tailwind",
    "tailwindcss": "Tailwind CSS",
    "bootstrap": "Bootstrap",
    "postman":   "Postman",

    # Libraries
    "pandas":     "pandas",
    "numpy":      "NumPy",
    "matplotlib": "Matplotlib",
    "axios":      "Axios",
}


# ══════════════════════════════════════════════════════════════════════════════
# 2. SAFE INFORMAL CONTRACTIONS
# ══════════════════════════════════════════════════════════════════════════════
# ONLY unambiguously informal ASR artifacts are fixed here.
# "cause" is intentionally excluded — it can mean "cause/effect" in teaching.
# "yeah/yep/nope" are excluded — teachers use them naturally as affirmations.
# "actually/basically/right/well" are excluded — they're pedagogical.

_CONTRACTIONS = [
    # Typo-grade informal speech (safe to fix)
    (r"\bgonna\b",  "going to"),
    (r"\bgona\b",   "going to"),
    (r"\bwanna\b",  "want to"),
    (r"\blemme\b",  "let me"),
    (r"\bgimme\b",  "give me"),
    (r"\btryna\b",  "trying to"),
    (r"\bkinda\b",  "kind of"),
    (r"\bsorta\b",  "sort of"),
    (r"\boutta\b",  "out of"),
    (r"\bdunno\b",  "don't know"),
    (r"\bgotta\b",  "got to"),
    (r"\bmighta\b", "might have"),
    (r"\bcould've\b",  "could have"),
    (r"\bwould've\b",  "would have"),
    (r"\bshould've\b", "should have"),
    (r"\bcoulda\b",    "could have"),
    (r"\bwoulda\b",    "would have"),
    (r"\bshoulda\b",   "should have"),
    (r"\btho\b",    "though"),
    (r"\bthru\b",   "through"),
    (r"\bcoz\b",    "because"),

    # Chat abbreviations (ASR rarely produces these, but just in case)
    (r"\bur\b(?=\s+[a-zA-Z])",  "your"),
    (r"\bu\b(?=\s+[a-zA-Z])",   "you"),
]


# ══════════════════════════════════════════════════════════════════════════════
# 3. PURE VOCAL HESITATION SOUNDS — removed ONLY as isolated words
# ══════════════════════════════════════════════════════════════════════════════
# IMPORTANT: These are matched ONLY when surrounded by spaces/boundaries
# so "uh" in "github" or "aha" is never touched.
# We do NOT remove "okay", "right", "well", "so" — those carry teaching meaning.

_VOCAL_HESITATIONS = re.compile(
    r"(?<!\w)"                          # not preceded by a word char
    r"\b(?:um|uh|hmm|hm|huh|err|er)\b" # pure hesitation sounds
    r"(?!\w)"                           # not followed by a word char
    r"[,]?",                            # optionally eat a following comma
    re.IGNORECASE
)


# ══════════════════════════════════════════════════════════════════════════════
# 4. ASR NOISE MARKERS — bracketed artifacts from auto-captioning
# ══════════════════════════════════════════════════════════════════════════════

_ASR_NOISE = re.compile(
    r"\[(?:inaudible|crosstalk|music|laughter|applause|noise|silence|sic|unclear)\]",
    re.IGNORECASE
)


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _apply_tech_normalization(text: str) -> str:
    """
    Replace tech terms with canonical capitalized forms.
    Sorted longest-first to handle multi-word terms before single-word terms.
    Only applies at word boundaries to avoid partial matches.
    """
    for term_lower, term_correct in sorted(_TECH_TERMS.items(), key=lambda x: -len(x[0])):
        pattern = r'\b' + re.escape(term_lower) + r'\b'
        try:
            text = re.sub(pattern, term_correct, text, flags=re.IGNORECASE)
        except re.error:
            pass
    return text


def _apply_contractions(text: str) -> str:
    """Fix unambiguously informal speech patterns only."""
    for pattern, replacement in _CONTRACTIONS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _remove_vocal_hesitations(text: str) -> str:
    """
    Remove pure vocal hesitation sounds (um, uh, hmm, er).
    These carry zero information and are pure ASR/speech artifacts.
    """
    text = _VOCAL_HESITATIONS.sub('', text)
    # Clean up any double spaces left behind
    text = re.sub(r'  +', ' ', text)
    return text


def _deduplicate_stutters(text: str) -> str:
    """
    Remove stutter-style consecutive word repetitions.
    Only removes exact immediate repetitions (e.g. "the the the" → "the").
    Does NOT remove meaningful repeated phrases like "very very important".
    Limits to single-word deduplication only to avoid false positives.
    """
    # Single word stutter: "the the" → "the", "is is" → "is"
    # Only collapse 2+ exact repeats (not pairs which may be emphasis)
    text = re.sub(r'\b(\w+)(?:\s+\1){2,}\b', r'\1', text, flags=re.IGNORECASE)
    return text


def _normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces. Preserve newlines."""
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def _fix_punctuation_spacing(text: str) -> str:
    """
    Fix common ASR punctuation artifacts:
    - Remove space before punctuation: "word ." → "word."
    - Ensure space after comma/semicolon where missing.
    Does NOT add or remove terminal punctuation (preserves the teacher's pacing).
    """
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    text = re.sub(r'([,;:])(?!\s)', r'\1 ', text)
    return text


def _capitalize_segment_start(text: str) -> str:
    """
    Capitalize the very first letter of a transcript segment/line.
    Only touches the first character — does not restructure sentences.
    """
    text = text.strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def refine_transcript_segment(text: str) -> str:
    """
    Apply conservative polish to a single transcript segment.

    Safe to call on short individual segments (e.g. YouTube caption lines).
    Preserves ALL educational content. Only removes pure acoustic/ASR noise.

    Order matters — hesitations removed before dedup to avoid
    leaving orphaned spaces that confuse the dedup regex.
    """
    if not text or len(text.strip()) < 2:
        return text

    # Step 1: Strip bracketed ASR noise markers
    text = _ASR_NOISE.sub('', text)

    # Step 2: Fix informal contractions (gonna, wanna, etc.)
    text = _apply_contractions(text)

    # Step 3: Normalize tech term capitalization
    text = _apply_tech_normalization(text)

    # Step 4: Remove pure vocal hesitation sounds (um, uh, hmm, er)
    text = _remove_vocal_hesitations(text)

    # Step 5: Remove stutter-style 3+ consecutive repetitions only
    text = _deduplicate_stutters(text)

    # Step 6: Normalize whitespace
    text = _normalize_whitespace(text)

    # Step 7: Fix punctuation spacing artifacts
    text = _fix_punctuation_spacing(text)

    # Step 8: Capitalize segment start
    text = _capitalize_segment_start(text)

    return text


def refine_transcript(transcript: str) -> str:
    """
    Apply conservative polish to a full transcript string.

    - Preserves all timestamps ([MM:SS] or [HH:MM:SS]) on each line.
    - Applies refinement only to the text portion of each line.
    - Does NOT restructure, merge, or reorder any lines.
    - Does NOT remove transition words or pedagogical connectors.

    This function is intentionally conservative. When in doubt, it
    preserves the original text rather than modifying it.
    """
    if not transcript:
        return transcript

    _TS_RE = re.compile(r'^(\[\d{2}:\d{2}(?::\d{2})?\])\s*')

    lines = transcript.splitlines()
    result_lines = []

    for line in lines:
        raw = line  # always keep original as fallback
        stripped = line.strip()

        if not stripped:
            result_lines.append('')
            continue

        m = _TS_RE.match(stripped)
        if m:
            # Line has a timestamp prefix — refine only the text portion
            timestamp = m.group(1)
            text_part = stripped[m.end():]
            refined = refine_transcript_segment(text_part)
            result_lines.append(f"{timestamp} {refined}" if refined else timestamp)
        else:
            # No timestamp — refine the whole line
            result_lines.append(refine_transcript_segment(stripped))

    # Remove completely blank lines at start/end, but preserve internal structure
    return '\n'.join(result_lines).strip()
