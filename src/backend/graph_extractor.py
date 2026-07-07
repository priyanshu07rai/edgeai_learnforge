"""
graph_extractor.py — Structured Educational Knowledge Graph Generator

Strategy:
  1. Read from the EXISTING notes knowledge cache (topic_N_knowledge.json)
     which already contains: definitions, examples, steps, applications,
     keywords, best_practices, warnings, formulas etc.
  2. Transform that rich data into a validated educational hierarchy schema.
  3. Apply content validation — skip non-structural topics.
  4. No random keyword extraction. No isolated nouns. No hallucination.

Output schema:
{
  "main_topic": "...",
  "is_structural": true/false,
  "topic_type": "concept|algorithm|workflow|system|procedure|general",
  "explanation": "...",
  "subtopics": [
    {
      "title": "...",
      "description": "...",
      "icon": "...",
      "items": [],
      "children": []
    }
  ],
  "examples": ["..."],
  "key_takeaways": ["..."],
  "related_topics": ["..."],
  "flowchart_steps": ["..."]
}
"""

import os
import re
import json
import tempfile
from typing import Optional

# ── Content-type classifier ────────────────────────────────────────────────────

_NON_STRUCTURAL_SIGNALS = re.compile(
    r'\b(intro|introduction|welcome|overview|motivation|why\s+learn|'
    r'getting\s+started|what\s+we\s+will\s+learn|course\s+outline|'
    r'hello|hi\s+everyone|subscribe|outro|conclusion|wrap.?up|'
    r'summary\s+of\s+what|in\s+this\s+video|in\s+this\s+lecture)\b',
    re.IGNORECASE
)

_STRUCTURAL_SIGNALS = re.compile(
    r'\b(algorithm|workflow|system|architecture|pipeline|process|procedure|'
    r'implementation|pattern|design|structure|hierarchy|flowchart|cycle|'
    r'loop|condition|function|class|module|operator|statement|expression|'
    r'variable|type|method|inheritance|polymorphism|encapsulation|'
    r'recursion|sorting|searching|tree|graph|stack|queue|array|list|'
    r'dictionary|hash|binary|decimal|hexadecimal|protocol|layer|'
    r'model|framework|library|api|database|query|schema|index|'
    r'network|security|authentication|encryption|compression)\b',
    re.IGNORECASE
)

# Icons mapped to subtopic themes
_ICON_MAP = {
    'what': '❓',
    'definition': '📖',
    'how': '⚙️',
    'why': '💡',
    'types': '🗂️',
    'type': '🗂️',
    'example': '🧪',
    'application': '🚀',
    'advantage': '✅',
    'disadvantage': '❌',
    'step': '📋',
    'rule': '📏',
    'component': '🧩',
    'feature': '⭐',
    'property': '🔑',
    'operation': '🔧',
    'syntax': '💻',
    'comparison': '⚖️',
    'use': '🎯',
    'benefit': '🏆',
    'formula': '🔢',
    'conversion': '🔄',
    'structure': '🏗️',
    'representation': '📊',
}

_GENERIC_STOP = {
    'what', 'this', 'that', 'these', 'those', 'here', 'there', 'some',
    'also', 'just', 'like', 'very', 'really', 'quite', 'more', 'most',
    'then', 'when', 'where', 'which', 'who', 'they', 'them', 'their',
    'now', 'next', 'back', 'again', 'already', 'still', 'even', 'only',
    'first', 'second', 'third', 'last', 'both', 'each', 'every', 'all',
    'any', 'same', 'other', 'such', 'than', 'then', 'way', 'thing',
    'things', 'word', 'words', 'kind', 'kinds', 'part', 'parts',
    'topic', 'lecture', 'video', 'course', 'tutorial', 'lesson',
}


def _is_meaningful(text: str, min_words: int = 4) -> bool:
    """Check if a text string is a meaningful educational sentence."""
    if not text or len(text.strip()) < 15:
        return False
    words = [w.lower() for w in re.findall(r'\b\w{3,}\b', text)]
    content_words = [w for w in words if w not in _GENERIC_STOP]
    return len(content_words) >= min_words


def _clean_sentence(s: str) -> str:
    """Strip trailing punctuation and whitespace."""
    return s.strip().rstrip('.,;:')


def _get_icon(title: str) -> str:
    """Pick an icon based on the subtopic title keywords."""
    t = title.lower()
    for keyword, icon in _ICON_MAP.items():
        if keyword in t:
            return icon
    return '🔵'


def _classify_topic_type(title: str, knowledge: dict) -> str:
    """Classify the educational type of the topic."""
    t = title.lower()
    steps = knowledge.get('procedures', [])
    definitions = knowledge.get('definition', '')
    
    if re.search(r'\balgori?thm\b|\bsorting\b|\bsearching\b|\brecursion\b', t):
        return 'algorithm'
    if re.search(r'\bworkflow\b|\bpipeline\b|\bprocess\b|\bcycle\b', t):
        return 'workflow'
    if re.search(r'\bsystem\b|\barchitecture\b|\bnetwork\b|\bprotocol\b', t):
        return 'system'
    if steps and len(steps) >= 2:
        return 'procedure'
    if re.search(r'\bwhat\s+is\b|\bintroduction\s+to\b|\bconc?ept\b', t):
        return 'concept'
    return 'general'


def _is_structural_topic(title: str, knowledge: dict) -> bool:
    """Determine if this topic warrants a knowledge graph visualization."""
    # Skip purely motivational/conversational topics
    if _NON_STRUCTURAL_SIGNALS.search(title):
        # Even motivational topics can have structure if they have real content
        steps = knowledge.get('procedures', [])
        defs = knowledge.get('definition', '')
        if not steps and not defs:
            return False

    # Topics with real educational content
    has_definition = bool(knowledge.get('definition', '').strip())
    has_applications = len(knowledge.get('applications', [])) >= 1
    has_steps = len(knowledge.get('procedures', [])) >= 1
    has_examples = len(knowledge.get('examples', [])) >= 1
    has_keywords = len(knowledge.get('keywords', [])) >= 3

    score = sum([has_definition, has_applications, has_steps, has_examples, has_keywords])
    return score >= 2


def _build_subtopics(title: str, knowledge: dict, topic_type: str) -> list:
    """
    Build the educational subtopic list from the knowledge schema.
    Each subtopic corresponds to a semantic category.
    """
    subtopics = []
    definition = knowledge.get('definition', '')
    explanation = knowledge.get('explanation', '')
    applications = knowledge.get('applications', [])
    procedures = knowledge.get('procedures', [])
    examples = knowledge.get('examples', [])
    best_practices = knowledge.get('best_practices', [])
    warnings = knowledge.get('warnings', [])
    formulas = knowledge.get('formulas', [])
    keywords = knowledge.get('keywords', [])
    analogies = knowledge.get('analogy', '')

    # 1. Core definition subtopic
    if definition and _is_meaningful(definition):
        desc = _clean_sentence(definition)
        subtopics.append({
            'title': f'What is {title.split()[-1] if len(title.split()) <= 3 else title}?',
            'description': desc[:200],
            'icon': '❓',
            'items': [],
            'children': [],
        })

    # 2. Key properties / features
    if keywords and len(keywords) >= 3:
        subtopics.append({
            'title': 'Key Properties',
            'description': 'Core characteristics and properties of this concept.',
            'icon': '🔑',
            'items': [k.title() for k in keywords[:6] if k.lower() not in _GENERIC_STOP],
            'children': [],
        })

    # 3. How it works (procedures/steps)
    if procedures and len(procedures) >= 1:
        clean_steps = [_clean_sentence(s) for s in procedures[:5] if _is_meaningful(s)]
        if clean_steps:
            subtopics.append({
                'title': 'How It Works',
                'description': clean_steps[0] if clean_steps else '',
                'icon': '⚙️',
                'items': clean_steps[1:] if len(clean_steps) > 1 else [],
                'children': [],
            })

    # 4. Applications / Use Cases
    if applications and len(applications) >= 1:
        app_items = [_clean_sentence(a) for a in applications[:5] if _is_meaningful(a)]
        if app_items:
            subtopics.append({
                'title': 'Applications',
                'description': 'Real-world uses and applications.',
                'icon': '🚀',
                'items': app_items,
                'children': [],
            })

    # 5. Advantages / Best Practices
    if best_practices and len(best_practices) >= 1:
        bp_items = [_clean_sentence(b) for b in best_practices[:4] if _is_meaningful(b)]
        if bp_items:
            subtopics.append({
                'title': 'Best Practices',
                'description': bp_items[0] if bp_items else '',
                'icon': '✅',
                'items': bp_items[1:] if len(bp_items) > 1 else [],
                'children': [],
            })

    # 6. Warnings / Common Mistakes
    if warnings and len(warnings) >= 1:
        warn_items = [_clean_sentence(w) for w in warnings[:3] if _is_meaningful(w)]
        if warn_items:
            subtopics.append({
                'title': 'Common Mistakes',
                'description': warn_items[0] if warn_items else '',
                'icon': '⚠️',
                'items': warn_items[1:] if len(warn_items) > 1 else [],
                'children': [],
            })

    # 7. Formulas (for math/CS topics)
    if formulas and len(formulas) >= 1:
        f_items = [_clean_sentence(f) for f in formulas[:3] if _is_meaningful(f, min_words=2)]
        if f_items:
            subtopics.append({
                'title': 'Formulas & Rules',
                'description': f_items[0] if f_items else '',
                'icon': '🔢',
                'items': f_items[1:] if len(f_items) > 1 else [],
                'children': [],
            })

    # Limit to 5 subtopics for clean visualization
    return subtopics[:5]


def _build_flowchart_steps(knowledge: dict) -> list:
    """Extract ordered process steps for workflow/procedure topics."""
    procedures = knowledge.get('procedures', [])
    steps = [_clean_sentence(s) for s in procedures if _is_meaningful(s)]
    return steps[:6]


def _build_related_topics(keywords: list, title: str) -> list:
    """Build related topics from keywords, filtering generic terms."""
    related = []
    for kw in keywords:
        kw_clean = kw.strip().title()
        if (
            len(kw_clean) > 3
            and kw_clean.lower() not in _GENERIC_STOP
            and kw_clean.lower() not in title.lower()
        ):
            related.append(kw_clean)
    return list(dict.fromkeys(related))[:8]  # deduplicate, limit 8


def _build_explanation(knowledge: dict) -> str:
    """Build a clean explanation paragraph."""
    definition = knowledge.get('definition', '')
    explanation = knowledge.get('explanation', '')
    
    if definition and len(definition) > 30:
        return _clean_sentence(definition)
    if explanation and len(explanation) > 30:
        # Take first clean sentence of explanation
        first = explanation.split('.')[0].strip()
        return _clean_sentence(first) if len(first) > 20 else _clean_sentence(explanation[:200])
    return ''


def _build_key_takeaways(knowledge: dict) -> list:
    """Build key takeaways from best practices and important points."""
    best = knowledge.get('best_practices', [])
    important_terms = knowledge.get('keywords', [])
    
    takeaways = []
    for bp in best[:4]:
        if _is_meaningful(bp):
            takeaways.append(_clean_sentence(bp))
    
    if not takeaways and knowledge.get('definition'):
        takeaways.append(_clean_sentence(knowledge['definition']))

    return takeaways[:5]


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_graph_for_single_topic(
    video_id: str,
    topic_index: int,
    storage_dir: str,
) -> Optional[dict]:
    """
    Generate a structured educational Knowledge Graph for a single topic.

    Reads from the notes knowledge cache first to avoid duplicate LLM calls.
    Transforms the rich knowledge schema into a validated educational hierarchy.

    Returns None only if the topic is completely unstructural (e.g., motivational intro).
    """
    video_dir = os.path.join(storage_dir, video_id)
    graph_cache_dir = os.path.join(video_dir, 'graph_cache')
    os.makedirs(graph_cache_dir, exist_ok=True)
    cache_path = os.path.join(graph_cache_dir, f'topic_{topic_index}_graph.json')

    # ── 1. Return from cache ─────────────────────────────────────────────────
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    # ── 2. Load topics.json ──────────────────────────────────────────────────
    topics_path = os.path.join(video_dir, 'topics.json')
    if not os.path.exists(topics_path):
        print(f'[LearnForge Graph] topics.json not found for {video_id}')
        return None

    with open(topics_path, 'r', encoding='utf-8') as f:
        topics = json.load(f)

    if topic_index >= len(topics):
        return None

    topic = topics[topic_index]
    topic_title = topic.get('title', f'Topic {topic_index + 1}')
    # Strip emoji prefixes like "⏩ ", "▶ " etc.
    topic_title = re.sub(r'^[\U00010000-\U0010ffff\u2000-\u27ff\s]+', '', topic_title).strip()
    if not topic_title:
        topic_title = topic.get('title', f'Topic {topic_index + 1}')

    # ── 3. Load knowledge from notes cache ───────────────────────────────────
    notes_cache_dir = os.path.join(video_dir, 'notes_cache')
    knowledge_cache_path = os.path.join(notes_cache_dir, f'topic_{topic_index}_knowledge.json')
    
    knowledge = {}
    if os.path.exists(knowledge_cache_path):
        try:
            with open(knowledge_cache_path, 'r', encoding='utf-8') as f:
                knowledge = json.load(f)
            print(f'[LearnForge Graph] Loaded knowledge cache for Topic {topic_index}.')
        except Exception as e:
            print(f'[LearnForge Graph] Failed to load knowledge cache: {e}')
    
    # Fallback: load from notes cache directly
    if not knowledge:
        notes_path = os.path.join(notes_cache_dir, f'topic_{topic_index}.json')
        if os.path.exists(notes_path):
            try:
                with open(notes_path, 'r', encoding='utf-8') as f:
                    notes = json.load(f)
                # Reconstruct minimal knowledge from notes
                detailed = notes.get('detailed', {})
                knowledge = {
                    'definition': notes.get('summary', ''),
                    'explanation': ' '.join(detailed.get('key_points', [])[:3]),
                    'examples': detailed.get('examples', []),
                    'applications': [],
                    'procedures': [],
                    'best_practices': [],
                    'warnings': [],
                    'keywords': notes.get('important_terms', []),
                    'formulas': [],
                    'analogy': '',
                }
                print(f'[LearnForge Graph] Reconstructed knowledge from notes cache for Topic {topic_index}.')
            except Exception as e:
                print(f'[LearnForge Graph] Failed to load notes cache: {e}')

    # ── 4. Fallback: build from topic content directly ───────────────────────
    if not knowledge:
        content = topic.get('content', '')
        if content and len(content) > 100:
            try:
                from extractor import extract_knowledge_units, remove_filler
                cleaned = remove_filler(content)
                knowledge = extract_knowledge_units(cleaned, topic_title)
                print(f'[LearnForge Graph] Built knowledge from topic content for Topic {topic_index}.')
            except Exception as e:
                print(f'[LearnForge Graph] Extractor fallback failed: {e}')
                knowledge = {}

    # ── 5. Validate structural content ──────────────────────────────────────
    if not _is_structural_topic(topic_title, knowledge):
        result = {
            'main_topic': topic_title,
            'is_structural': False,
            'topic_type': 'general',
            'explanation': _build_explanation(knowledge),
            'subtopics': [],
            'examples': [],
            'key_takeaways': [],
            'related_topics': [],
            'flowchart_steps': [],
        }
        _atomic_save(result, cache_path, graph_cache_dir)
        print(f'[LearnForge Graph] Topic {topic_index} is non-structural. Saved minimal schema.')
        return result

    # ── 6. Build structured educational hierarchy ────────────────────────────
    topic_type = _classify_topic_type(topic_title, knowledge)
    subtopics = _build_subtopics(topic_title, knowledge, topic_type)
    flowchart_steps = _build_flowchart_steps(knowledge)
    
    # Build clean examples list
    raw_examples = knowledge.get('examples', [])
    clean_examples = [
        _clean_sentence(ex)
        for ex in raw_examples[:3]
        if _is_meaningful(ex)
    ]

    result = {
        'main_topic': topic_title,
        'is_structural': True,
        'topic_type': topic_type,
        'explanation': _build_explanation(knowledge),
        'subtopics': subtopics,
        'examples': clean_examples,
        'key_takeaways': _build_key_takeaways(knowledge),
        'related_topics': _build_related_topics(
            knowledge.get('keywords', []), topic_title
        ),
        'flowchart_steps': flowchart_steps,
    }

    _atomic_save(result, cache_path, graph_cache_dir)
    print(f'[LearnForge Graph] Saved educational graph for Topic {topic_index} (type={topic_type}).')
    return result


def _atomic_save(data: dict, path: str, dir_: str):
    """Atomically write JSON to path."""
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f'[LearnForge Graph] Atomic save failed: {e}')
