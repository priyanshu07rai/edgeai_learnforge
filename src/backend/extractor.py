"""
extractor.py — Real Knowledge Extraction Pipeline

Stage 1: Clean transcript (remove filler + convert spoken → declarative)
Stage 2: Extract knowledge units (definitions, procedures, examples, terms)
Stage 3: Build structured educational notes
Stage 4: Build 30-second quick revision

NEVER pastes transcript sentences directly.
Converts spoken instructor language into textbook-style knowledge.
"""
import re
import math
from collections import Counter
from typing import Dict, List, Any


# ─────────────────────────────────────────────────────────────────────────────
# Stop words & constants
# ─────────────────────────────────────────────────────────────────────────────

_STOP_WORDS = {
    'the','a','an','and','or','but','in','on','at','to','for','of','with',
    'by','from','as','is','it','its','that','this','was','are','were','be',
    'been','have','has','had','do','does','did','will','would','could','should',
    'may','might','can','not','also','we','he','she','they','i','you','my',
    'your','our','his','her','their','what','who','which','how','when','where',
    'if','then','so','up','out','into','about','over','after','before','through',
    'during','each','all','both','any','many','more','most','other','such',
    'than','too','very','just','one','two','three','four','five','first',
    'second','third','last','next','now','here','there','some','few','much',
    'even','only','still','again','already','always','never','often','used',
    'using','use','get','got','take','make','made','become','became',
    'say','said','says','know','knew','think','thought','come','came','go','went',
    'see','seen','saw','let','put','set','run','ran','give','gave','keep','kept',
    'well','like','back','between','against','while','without','within','since',
    'because','although','though','however','therefore','thus','hence','whereas',
    'furthermore','moreover','additionally','subsequently','consequently',
    'called','known','named','referred','based','given','taken','found',
    'actually','basically','essentially','literally','simply','really',
    'quite','rather','almost','nearly','approximately','around',
    'including','following','according','regarding','related','associated',
    'among','along','upon','across','behind','beyond','below','above','under',
}


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Transcript Cleaning
# ─────────────────────────────────────────────────────────────────────────────

# Full filler detection regex
_FILLER_RE = re.compile(
    r'apna\s+college|codewithharry|shraddha\s+khapra|aman\s+dhattarwal|'
    r'hello\s+every\w*|welcome\s+back|welcome\s+to\s+(this|the)\s+(course|video|tutorial|lecture|series)|'
    r'\bsubscribe\b|\bsubscribed\b|like\s+and\s+share|hit\s+the\s+bell|notification\s+bell|'
    r'see\s+you\s+in\s+the\s+next|thank\s+you\s+for\s+watching|thanks\s+for\s+watching|'
    r'\bin\s+this\s+video\b|\bin\s+this\s+lecture\b|\bin\s+this\s+tutorial\b|'
    r'\bin\s+this\s+course\b|\bin\s+this\s+series\b|'
    r'my\s+name\s+is|super\s+excited|I\'?m\s+going\s+to\s+(walk|show|take|tell|explain\s+you)|'
    r'let\'?s\s+(get\s+started|start\s+with\s+this|begin|dive\s+in|jump\s+in)|'
    r'let\s+me\s+know|comment\s+below|don\'?t\s+forget\s+to|'
    r'check\s+out\s+my\s+(website|channel|playlist)|you\s+can\s+always\s+comment|'
    r'if\s+you\s+have\s+any\s+(errors|questions|doubts)|all\s+right\s+with\s+that\s+said|'
    r'alright\s+so\s+let|okay\s+so\s+let|right\s+so\s+let|'
    r'quick\s+note\s+here\s+this|as\s+always\b|stay\s+tuned|'
    r'drop\s+a\s+comment|smash\s+the\s+like|if\s+you\s+enjoyed\s+this|'
    r'full\s+stack\s+(machine\s+learning|development|series)|'
    r'dedicated\s+platform\s+for|you\s+are\s+in\s+the\s+right\s+place|'
    r'if\s+you\s+(enjoyed|like)\s+this\s+(video|course)|'
    r'I\s+want\s+to\s+quickly\s+guide|ran\.com|'
    r'today\s+we\s+(are\s+going\s+to|will\s+be|\'?re\s+going\s+to)\s+(cover|learn|discuss|look\s+at|talk)',
    re.IGNORECASE
)

# Spoken filler openers
_FILLER_OPENERS = re.compile(
    r'^(hey\s+(guys|everyone|there)\s*,?|'
    r'hi\s+(guys|everyone|there)\s*,?|'
    r'so\s+today\s+(we|I)|'
    r'now\s+in\s+this\s+(video|lecture)|'
    r'in\s+the\s+last\s+video|'
    r'alright\s+so|okay\s+so|right\s+so|'
    r'moving\s+on\s+to|'
    r'before\s+we\s+(start|begin|dive))',
    re.IGNORECASE
)

# Conversational openers to strip from otherwise-good sentences
_CONV_OPENERS = [
    (re.compile(r'^(hey\s+)?welcome\s+to\s+this\s+(course|video|tutorial|lecture|series)\s+(on\s+)?', re.I), ''),
    (re.compile(r'^(hey\s+)?welcome\s+to\s+the\s+(course|video|tutorial|lecture|series)\s+(on\s+)?', re.I), ''),
    (re.compile(r'^(hi\s+everyone\s+and\s+welcome\s+to\s+[\w\s]+\s+and\s+today\s+we\s+are\s+going\s+to\s+understand)\s+', re.I), ''),
    (re.compile(r'^(before\s+understanding\s+[\w\s]+\s*,?\s*it\s+is\s+very\s+important\s+to\s+understand)\s+', re.I), ''),
    (re.compile(r'^(whenever\s+we\s+talk\s+about|when\s+we\s+talk\s+about)\s+', re.I), ''),
    (re.compile(r'^(this\s+gives\s+rise\s+to|that\s+is\s+why|this\s+is\s+why)\s+', re.I), ''),
    (re.compile(r'^(let\'?s\s+assume|let\'?s\s+suppose)\s+(that\s+)?', re.I), ''),
    (re.compile(r'^(for\s+example\s*,?\s*we\s+have\s+a\s+machine\s+of\s+ours|for\s+example\s*,?\s*)\s*', re.I), ''),
    (re.compile(r'^(so\s+basically|basically\s*,?|so\s+essentially|essentially\s*,?)\s+', re.I), ''),
    (re.compile(r'^(alright|okay|right|so|now)\s*[,.\s]+', re.I), ''),
    (re.compile(r'^(you\s+can\s+see|as\s+you\s+can\s+see|as\s+we\s+can\s+see|you\s+see)\s+(that\s+)?', re.I), ''),
    (re.compile(r'^(remember\s+that|note\s+that|keep\s+in\s+mind\s+that|note\s*:)\s*', re.I), ''),
    (re.compile(r'^(what\s+I\s+mean\s+is|what\s+this\s+means\s+is|I\s+mean)\s*,?\s*', re.I), ''),
    (re.compile(r'^(let\'?s\s+)(talk\s+about|look\s+at|understand|see\s+how|discuss|go\s+through)\s+', re.I), ''),
    (re.compile(r'^(we\s+)(need\s+to|have\s+to|want\s+to|are\s+going\s+to|will)\s+', re.I), ''),
    (re.compile(r'^(you\s+)(need\s+to|have\s+to|want\s+to|should|will|can)\s+', re.I), ''),
    (re.compile(r'^(I\'?m\s+going\s+to|I\s+will|I\s+want\s+to|I\'?ll)\s+', re.I), ''),
    (re.compile(r'^(so\s+in\s+this\s+(section|part|video|lecture|topic))\s*,?\s*', re.I), ''),
    (re.compile(r'^(in\s+this\s+one\s*,?|in\s+here\s*,?|at\s+this\s+point\s*,?)\s*', re.I), ''),
    (re.compile(r'^(now\s+)?let\'?s\s+(go\s+to|create|import|define|say|run|start\s+with)\s+', re.I), ''),
    (re.compile(r'^(we\s+just\s+want\s+to\s+|we\s+simply\s+want\s+to\s+)', re.I), ''),
    (re.compile(r'^(you\s+can\s+simply\s+|you\s+can\s+just\s+)', re.I), ''),
    (re.compile(r'^(okay\s+so\s+)?at\s+this\s+point\s*,?\s*you\s+can\s+simply\s+', re.I), ''),
    (re.compile(r'^(this\s+is\s+where\s+we\s+are\s+going\s+to\s+|this\s+is\s+why\s+we\s+need\s+to\s+)', re.I), ''),
]

# Generic reject phrases
_GENERIC_REJECT = [
    'foundational concepts', 'best practices', 'practical examples',
    'key concepts', 'enable ollama', 'transcript is in hindi',
    'this section covers', 'in this section', 'further study',
    'more about this', 'as mentioned earlier', 'we will learn',
    'we will discuss', 'we will cover', 'let us understand',
]


def is_filler_sentence(sent: str) -> bool:
    """Returns True if sentence is pure YouTube filler / promotional."""
    s_low = sent.strip().lower()
    
    # Short pure filler phrases
    pure_fillers = [
        "subscribe", "hit the bell", "notification", "like and share",
        "welcome back", "hello every", "thank you for watching", "thanks for watching",
        "see you in the next", "drop a comment", "comment below", "smash the like",
        "stay tuned", "let's get started", "let's dive in", "welcome to this course",
        "welcome to this video", "welcome to this lecture", "welcome to this tutorial"
    ]
    
    # If the sentence is short and contains one of these, drop it
    if len(s_low) < 55 and any(f in s_low for f in pure_fillers):
        return True
        
    # If it is a generic YouTube greeting/outro and is short, drop it
    if len(s_low) < 60 and (_FILLER_RE.search(sent) or _FILLER_OPENERS.match(sent.strip())):
        return True
        
    return False


def clean_to_declarative(sentence: str) -> str:
    """
    Convert instructor/conversational speech to declarative educational language.
    "You can use APIView to build..." → "APIView is used to build..."
    "Let's create a serializer" → "Create a serializer."
    """
    s = sentence.strip()
    
    # Loop to strip conversational prefixes iteratively
    changed = True
    while changed:
        changed = False
        for pattern, replacement in _CONV_OPENERS:
            new_s = re.sub(pattern, replacement, s)
            if new_s != s:
                s = new_s.strip()
                if s and s[0].islower():
                    s = s[0].upper() + s[1:]
                changed = True
                break

    # Middle/end sentence conversational remnants cleanup
    s = re.sub(r'\b(anybody|anyone)\s+who\s+comes\s+to\s+this\s+URL\b', 'users visiting the URL', s, flags=re.I)
    s = re.sub(r'\b(we\s+are\s+going\s+to\s+do|we\s+will\s+implement)\b', 'implement', s, flags=re.I)
    s = re.sub(r'\b(let\'?s\s+create|we\s+are\s+going\s+to\s+create)\b', 'create', s, flags=re.I)
    s = re.sub(r'\b(our\s+previous\s+example|the\s+previous\s+lecture)\b', 'previous implementations', s, flags=re.I)
    s = re.sub(r'\b(your\s+server|our\s+server)\b', 'the server', s, flags=re.I)
    s = re.sub(r'\b(my\s+browser|your\s+browser)\b', 'the browser', s, flags=re.I)
    
    # Strip trailing filler phrases/transitions
    s = re.sub(r'[\s,]+(okay|right|you\s+know|as\s+well)\s*([.!?])?$', r'\2', s, flags=re.I)
    
    # Ensure capitalization and ending period
    if s:
        if s[0].islower():
            s = s[0].upper() + s[1:]
        if s[-1] not in '.!?':
            s += '.'
            
    return s


def heal_pause_periods(text: str) -> str:
    """Heal false pause periods in auto-captions based on surrounding parts of speech."""
    # 1. First, heal common compound word splits (case insensitive)
    compounds = [
        r'back\s*\.\s*end',
        r'front\s*\.\s*end',
        r'weather\s*\.\s*data',
        r'rest\s*\.\s*framework',
        r'software\s*\.\s*developer',
        r'app\s*\.\s*data',
        r'machine\s*\.\s*learning',
        r'real\s*\.\s*world',
        r'source\s*\.\s*code',
        r'web\s*\.\s*site',
        r'data\s*\.\s*base',
        r'api\s*\.\s*api',
    ]
    for c in compounds:
        text = re.sub(c, lambda m: m.group(0).replace('.', ''), text, flags=re.I)
        
    # 2. Heal periods preceded by words that cannot end a sentence
    cannot_end = {
        'the', 'a', 'an', 'this', 'these', 'those', 'my', 'your', 'our', 'their', 'his', 'her', 'its',
        'of', 'with', 'at', 'from', 'into', 'during', 'including', 'until', 'against', 'among', 'through',
        'to', 'in', 'on', 'by', 'between', 'about', 'under', 'above', 'for', 'stands', 'who', 'which', 'that',
        'is', 'are', 'was', 'were', 'am', 'be', 'been', 'will', 'would', 'should', 'can', 'could', 'have',
        'has', 'had', 'do', 'does', 'did', 'and', 'but', 'or', 'so', 'because', 'although', 'while', 'we',
        'they', 'i', 'you', 'he', 'she', 'it', 'us', 'our', 'them', 'who', 'whose', 'whom', 'which', 'here',
        'there', 'how', 'why', 'when', 'where', 'let', "let's", 'go', 'going', 'come', 'coming', 'take',
        'taking', 'make', 'making', 'do', 'doing', 'see', 'seeing', 'look', 'looking', 'current', 'many',
        'some', 'any', 'every', 'all', 'one', 'two', 'three', 'first', 'second', 'third', 'other', 'another',
        'very', 'really', 'basically', 'essentially', 'simply', 'just', 'still', 'even', 'only', 'also',
        'always', 'never', 'often', 'sometimes', 'usually', 'mostly', 'actually'
    }
    
    # 3. Heal periods followed by words that cannot start a sentence
    cannot_start = {
        'for', 'of', 'with', 'at', 'from', 'by', 'between', 'to', 'in', 'on', 'into', 'through', 'under', 'above',
        'who', 'whom', 'whose', 'which', 'that', 'and', 'but', 'or', 'so', 'because', 'although', 'while',
        'is', 'are', 'was', 'were', 'am', 'be', 'been', 'will', 'would', 'should', 'can', 'could', 'have',
        'has', 'had', 'do', 'does', 'did', 'cannot', 'couldnot', 'shouldnot', 'wouldnot',
        'serves', 'prepares', 'requested', 'gives', 'wants', 'request', 'order', 'ordered', 'brings', 'take',
        'client', 'server', 'kitchen', 'cook', 'waiter', 'food', 'restaurant', 'customer', 'back', 'front', 'end',
        'developments', 'thermometers', 'radar', 'systems', 'equipment', 'meteorologist', 'engineers', 'providers',
        'weather', 'data', 'framework', 'developer', 'app', 'learning', 'world', 'code', 'site', 'base',
        'these', 'those', 'this', 'that', 'them', 'us', 'you', 'me', 'him', 'her', 'it', 'its', 'their', 'our',
        'closely', 'technically', 'simply', 'basically', 'essentially', 'really', 'just', 'still', 'even', 'only',
        'also', 'always', 'never', 'often', 'sometimes', 'usually', 'mostly', 'actually', 'where', 'when', 'how',
        'why', 'what', 'who', 'the', 'a', 'an', 'very', 'more', 'less', 'most', 'least', 'well', 'here', 'there'
    }

    # Match word + period + space + word
    def replace_match(match):
        w1 = match.group(1)
        w2 = match.group(2)
        w1_low = w1.lower()
        w2_low = w2.lower()
        
        # Avoid matching uppercase starts since they represent real proper nouns or sentence starts
        if w2[0].isupper():
            return w1 + ". " + w2
            
        if w1_low in cannot_end or w2_low in cannot_start:
            return w1 + " " + w2
        # Otherwise, keep the period
        return w1 + ". " + w2

    # Regex matching word, followed by period, optional spaces, and another word
    return re.sub(r'(\b\w+)\s*\.\s*(\w+)', replace_match, text)


def remove_filler(text: str) -> str:
    """
    Stage 1A: Remove filler sentences, keeping only educational content.
    Returns cleaned text ready for knowledge extraction.
    """
    healed_text = heal_pause_periods(text)
    sentences = re.split(r'(?<=[.!?।])\s+|\n+', healed_text)
    clean = []
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 15:
            continue
        if is_filler_sentence(sent):
            continue
        clean.append(sent)
    return ' '.join(clean)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Knowledge Unit Extraction
# ─────────────────────────────────────────────────────────────────────────────

# Definition patterns: "[X] is a [Y]", "[X] refers to [Y]"
_DEF_RE = re.compile(
    r'\b\w[\w\s]{2,30}\s+(?:is|are|was|were)\s+(?:a|an|the)\s+\w',
    re.IGNORECASE
)
_DEF_RE2 = re.compile(
    r'\b(refers\s+to|means|defined\s+as|known\s+as|called|stands\s+for|short\s+for)\b',
    re.IGNORECASE
)

# Procedural/action patterns
_PROC_VERBS = re.compile(
    r'\b(create|build|install|configure|define|implement|set\s+up|add|write|run|execute|'
    r'declare|initialize|import|export|register|connect|start|deploy|test|use|apply|'
    r'generate|call|request|return|send|receive|handle|process|validate|serialize|'
    r'authenticate|authorize|inherit|extend|override|map|render)\b',
    re.IGNORECASE
)

# Example patterns
_EX_RE = re.compile(
    r'\bfor\s+example\b|\bfor\s+instance\b|\bsuch\s+as\b|\be\.g\.\b|\blike\b(?!\s+(and|or))',
    re.IGNORECASE
)

# Advantage/feature patterns
_FEATURE_RE = re.compile(
    r'\b(allows?|enables?|provides?|supports?|offers?|gives?|lets?\s+you|makes?\s+it|'
    r'advantage|benefit|feature|capability|useful\s+for|used\s+for|designed\s+for|'
    r'main\s+purpose|key\s+difference|difference\s+between)\b',
    re.IGNORECASE
)

# Comparison patterns
_COMPARE_RE = re.compile(
    r'\b(vs\.?|versus|compared\s+to|unlike|in\s+contrast|on\s+the\s+other\s+hand|'
    r'difference\s+between|while|whereas|instead\s+of|rather\s+than)\b',
    re.IGNORECASE
)

# "Important / key / critical" markers
_IMPORTANT_RE = re.compile(
    r'\b(important|key\s+point|critical|essential|must|always|never|note\s+that|'
    r'warning|remember|keep\s+in\s+mind|mistake|common\s+error|pitfall|gotcha)\b',
    re.IGNORECASE
)

# Step/sequence markers
_STEP_RE = re.compile(
    r'\b(first|second|third|step\s+\d|then|next|after\s+that|finally|lastly|'
    r'step\s+one|step\s+two|step\s+three|begin\s+by|start\s+by|end\s+by)\b',
    re.IGNORECASE
)

# Analogy patterns: "think of X as Y", "X is like Y", "imagine X", "just like a [noun]"
_ANALOGY_RE = re.compile(
    r'\b(?:think\s+of\s+[\w\s-]{2,30}\s+as\s+[\w\s-]{2,30}|'
    r'[\w\s-]{2,30}\s+(?:is|are|was|were)\s+like\s+(?:a|an|the)?\s+[\w\s-]{2,30}|'
    r'imagine\s+[\w\s-]{2,30}|'
    r'just\s+like\s+(?:a|an|the)?\s+[\w-]{2,20})\b',
    re.IGNORECASE
)

# Misconception / negation patterns
_MISCONCEPTION_RE = re.compile(
    r'\b(?:is\s+not\s+(?:a|an|the)?\s+[\w\s-]{2,30}|'
    r'does\s+not\s+mean\s+[\w\s-]{2,30}|'
    r'do\s+not\s+mean\s+[\w\s-]{2,30}|'
    r'don\'?t\s+confuse\s+[\w\s-]{2,30}|'
    r'should\s+not\s+be\s+[\w\s-]{2,30}|'
    r'never\s+[\w\s-]{2,30}|'
    r'not\s+just\s+about\s+[\w\s-]{2,30})\b',
    re.IGNORECASE
)


def compress_bullet(bullet: str) -> List[str]:
    """
    Cleans bullets by stripping hedging/conversational fillers, and splits sentences
    ONLY at clean, grammatically sound boundaries (like semicolons, colons, or coordinate
    clauses) without leaving behind broken fragments or dangling clauses.
    """
    # 1. Strip hedging phrases at the beginning of the sentence
    hedging_patterns = [
        r'^it\s+is\s+important\s+to\s+note\s+that\s+',
        r'^as\s+we\s+can\s+see\s*,?\s*',
        r'^we\s+can\s+see\s+that\s+',
        r'^it\s+is\s+worth\s+mentioning\s+that\s+',
        r'^please\s+note\s+that\s+',
        r'^keep\s+in\s+mind\s+that\s+',
        r'^we\s+should\s+keep\s+in\s+mind\s+that\s+',
        r'^first\s+of\s+all\s*,?\s*',
        r'^so\s+basically\s*,?\s*',
        r'^essentially\s*,?\s*',
        r'^literally\s*,?\s*',
        r'^simply\s*,?\s*',
        r'^actually\s*,?\s*',
    ]
    
    compressed = bullet.strip()
    for pat in hedging_patterns:
        compressed = re.sub(pat, '', compressed, flags=re.I)
        
    if compressed and compressed[0].islower():
        compressed = compressed[0].upper() + compressed[1:]
        
    words = compressed.split()
    # If the sentence is reasonable in length, do not split it
    if len(words) <= 32:
        return [compressed]
        
    # 2. Find clean, grammatical split points
    # Splitters prioritized by strength and grammar
    splitters = [
        (r'\s*;\s*', '; '),
        (r'\s*:\s*', ': '),
        (r'\s+—\s+', ' — '),
        (r'\s+-\s+', ' - '),
        (r'\s+,\s+while\s+', ' while '),
        (r'\s+,\s+but\s+', ' but '),
        (r'\s+,\s+which\s+', ', which '),
        (r'\s+,\s+that\s+', ', that '),
        (r'\s+because\s+', ' because '),
        (r'\s+so\s+that\s+', ' so that '),
    ]
    
    dangling_ends = {
        'and', 'or', 'the', 'a', 'an', 'of', 'to', 'with', 'that', 'which', 
        'from', 'in', 'on', 'at', 'for', 'by', 'is', 'are', 'was', 'were', 
        'be', 'been', 'has', 'have', 'had', 'do', 'does', 'did', 'then', 'before', 'after'
    }
    dangling_starts = {
        'and', 'or', 'of', 'to', 'with', 'which', 'from', 'in', 'on', 'at', 
        'for', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'has', 'have', 
        'had', 'do', 'does', 'did', 'then', 'before', 'after'
    }
    
    for pat, replacement in splitters:
        parts = re.split(pat, compressed, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            p1, p2 = parts[0].strip(), parts[1].strip()
            w1 = p1.split()
            w2 = p2.split()
            
            # Ensure both sides have enough content to stand as clean notes
            if len(w1) >= 6 and len(w2) >= 6:
                # Clean word tokens to check dangling boundaries
                last_word = re.sub(r'[^\w]', '', w1[-1]).lower() if w1 else ''
                first_word = re.sub(r'[^\w]', '', w2[0]).lower() if w2 else ''
                
                # Check for dangling prepositions or conjunctions
                if last_word not in dangling_ends and first_word not in dangling_starts:
                    if not p1.endswith('.'): p1 += '.'
                    if p2[0].islower(): p2 = p2[0].upper() + p2[1:]
                    if not p2.endswith('.'): p2 += '.'
                    return compress_bullet(p1) + compress_bullet(p2)
                    
    # If no clean grammatical split point is found, keep the sentence whole to avoid incomplete fragments
    return [compressed]


def compute_tfidf_weights(sentences: List[str], corpus: List[str] = None) -> Dict[str, float]:
    """Compute TF-IDF weights for all non-stopwords in the sentences."""
    docs = []
    if corpus and len(corpus) > 1:
        for doc_text in corpus:
            doc_words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', doc_text) if w.lower() not in _STOP_WORDS]
            docs.append(set(doc_words))
    else:
        for sent in sentences:
            sent_words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', sent) if w.lower() not in _STOP_WORDS]
            docs.append(set(sent_words))
            
    N = len(docs)
    df = Counter()
    for d in docs:
        df.update(d)
        
    topic_words = []
    for sent in sentences:
        topic_words.extend([w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', sent) if w.lower() not in _STOP_WORDS])
    
    tf = Counter(topic_words)
    total_tf = sum(tf.values()) or 1
    
    tfidf = {}
    for word, count in tf.items():
        tf_val = count / total_tf
        df_val = df.get(word, 0)
        idf_val = math.log((1 + N) / (1 + df_val)) + 1
        tfidf[word] = tf_val * idf_val
        
    return tfidf


def rank_sentences_by_tfidf(sentences: List[str], tfidf_dict: Dict[str, float]) -> List[str]:
    """Rank sentences based on the sum of their word TF-IDF scores divided by word count."""
    scored = []
    for sent in sentences:
        words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', sent) if w.lower() not in _STOP_WORDS]
        if not words:
            score = 0.0
        else:
            score = sum(tfidf_dict.get(w, 0.0) for w in words) / len(words)
            
        bonus = 1.0
        if _DEF_RE.search(sent) or _DEF_RE2.search(sent):
            bonus *= 1.4
        if re.search(r'\b\d+\b', sent):
            bonus *= 1.2
        proper = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', sent)
        if proper:
            bonus *= (1 + 0.05 * min(len(proper), 5))
            
        scored.append((score * bonus, sent))
        
    scored.sort(key=lambda x: x[0], reverse=True)
    return [sent for _, sent in scored]


def extract_knowledge_units(text: str, topic_title: str, corpus: List[str] = None) -> Dict[str, Any]:
    """
    Stage 2: Extract structured knowledge units from cleaned English text.
    Returns a structured Knowledge Layer dictionary.
    """
    if not text or len(text.strip()) < 20:
        return _empty_knowledge(topic_title)

    # Heal mid-sentence pauses/periods
    healed_text = heal_pause_periods(text)

    # Split into sentences
    raw = re.split(r'(?<=[.!?।])\s+|\n+', healed_text)
    sentences = [s.strip() for s in raw if len(s.strip()) > 20]

    # Word frequency for term extraction
    all_words = []
    for s in sentences:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', s.lower())
        all_words.extend(w for w in words if w not in _STOP_WORDS)
    word_freq = Counter(all_words)

    # Classify each sentence
    definitions = []
    procedures = []
    examples = []
    features = []
    comparisons = []
    important = []
    steps = []
    analogies = []
    misconceptions = []
    general = []
    
    code_snippets = []
    terminal_commands = []
    warnings_list = []
    best_practices_list = []
    formulas_list = []

    for sent in sentences:
        if is_filler_sentence(sent):
            continue
        if len(sent) < 25:
            continue

        # Clean conversational openers
        cleaned = clean_to_declarative(sent)
        if not cleaned or len(cleaned) < 20:
            continue

        # Compress bullets
        for sub_sent in compress_bullet(cleaned):
            s_low = sub_sent.lower()
            
            # 1. Regex checks for specialized knowledge types
            is_cmd = any(cmd in s_low for cmd in ["pip install", "python manage.py", "django-admin", "source env", "npm run", "git clone", "git push", "git commit", "docker run", "docker-compose"])
            # Strict code detection: require actual code syntax markers, not just English words
            # Disqualify plain English sentences that happen to contain these words
            _has_code_fence = "```" in sub_sent
            _has_code_assignment = bool(re.search(r'\b\w+\s*=\s*[\w"\[{(]', sub_sent))  # x = value
            _has_code_call = bool(re.search(r'\b\w+\(.*\)', sub_sent))  # function(...)
            _has_code_keyword = bool(re.search(r'\b(def |class |import |from \w+ import|const |let |var |function |return |elif |else:|except:|lambda |yield |async |await )\b', sub_sent))
            _has_indent = sub_sent.startswith(("    ", "\t"))  # indented code
            is_code = (_has_code_fence or _has_code_keyword or (_has_code_assignment and _has_code_call) or _has_indent) and not is_cmd
            is_warning = any(w in s_low for w in ["warning", "error", "mistake", "fail", "wrong", "pitfall", "gotcha"])
            is_best_practice = any(bp in s_low for bp in ["best practice", "should", "always", "never", "must"])
            is_formula = any(form in s_low for form in ["formula", "equation", "calculate", "=", "+", "*", "/"]) and any(char.isdigit() for char in sub_sent)

            if is_cmd:
                terminal_commands.append(sub_sent)
            elif is_code:
                code_snippets.append(sub_sent)
            
            if is_warning:
                warnings_list.append(sub_sent)
            elif is_best_practice:
                best_practices_list.append(sub_sent)
                
            if is_formula:
                formulas_list.append(sub_sent)

            # 2. General classification
            is_question = bool(sub_sent.endswith('?') or s_low.startswith(('what ', 'how ', 'why ', 'when ', 'who ', 'let\'s understand ')))
            is_def = bool((_DEF_RE.search(sub_sent) or _DEF_RE2.search(sub_sent)) and not is_question)
            is_proc = bool(_PROC_VERBS.search(sub_sent)) and len(sub_sent.split()) < 25
            is_ex = bool(_EX_RE.search(sub_sent))
            is_feat = bool(_FEATURE_RE.search(sub_sent))
            is_cmp = bool(_COMPARE_RE.search(sub_sent))
            is_imp = bool(_IMPORTANT_RE.search(sub_sent))
            is_step = bool(_STEP_RE.search(sub_sent))
            is_analogy = bool(_ANALOGY_RE.search(sub_sent))
            is_misconception = bool(_MISCONCEPTION_RE.search(sub_sent))

            if is_analogy:
                analogies.append(sub_sent)
            elif is_misconception:
                misconceptions.append(sub_sent)
            elif is_def and not is_ex:
                definitions.append(sub_sent)
            elif is_step:
                steps.append(sub_sent)
            elif is_ex:
                examples.append(sub_sent)
            elif is_cmp:
                comparisons.append(sub_sent)
            elif is_feat:
                features.append(sub_sent)
            elif is_imp:
                important.append(sub_sent)
            elif is_proc:
                procedures.append(sub_sent)
            else:
                general.append(sub_sent)

    # Compute TF-IDF weights using sentences
    tfidf_dict = compute_tfidf_weights(sentences, corpus)

    # Rank each bucket using TF-IDF
    definitions = rank_sentences_by_tfidf(definitions, tfidf_dict)
    procedures = rank_sentences_by_tfidf(procedures, tfidf_dict)
    examples = rank_sentences_by_tfidf(examples, tfidf_dict)
    features = rank_sentences_by_tfidf(features, tfidf_dict)
    comparisons = rank_sentences_by_tfidf(comparisons, tfidf_dict)
    important = rank_sentences_by_tfidf(important, tfidf_dict)
    steps = rank_sentences_by_tfidf(steps, tfidf_dict)
    analogies = rank_sentences_by_tfidf(analogies, tfidf_dict)
    misconceptions = rank_sentences_by_tfidf(misconceptions, tfidf_dict)
    general = _rank_by_density(general, tfidf_dict)
    
    # Sort selected subsets chronologically to maintain the transcript flow
    definitions = sort_chronologically(definitions, sentences)
    procedures = sort_chronologically(procedures, sentences)
    examples = sort_chronologically(examples, sentences)
    features = sort_chronologically(features, sentences)
    comparisons = sort_chronologically(comparisons, sentences)
    important = sort_chronologically(important, sentences)
    steps = sort_chronologically(steps, sentences)
    analogies = sort_chronologically(analogies, sentences)
    misconceptions = sort_chronologically(misconceptions, sentences)
    general = sort_chronologically(general, sentences)
    
    code_snippets = sort_chronologically(code_snippets, sentences)
    terminal_commands = sort_chronologically(terminal_commands, sentences)
    warnings_list = sort_chronologically(warnings_list, sentences)
    best_practices_list = sort_chronologically(best_practices_list, sentences)
    formulas_list = sort_chronologically(formulas_list, sentences)

    # Extract key terms
    terms = _extract_key_terms(text, word_freq)

    # Construct the chronological explanation
    explanation_parts = general[:5]
    explanation_text = " ".join(explanation_parts)

    # Construct interview questions
    interview_questions = []
    is_intro_or_outro = any(w in topic_title.lower() for w in ["introduction", "overview", "conclusion", "summary", "wrap-up", "intro", "outro"])
    if not is_intro_or_outro:
        for df in definitions[:2]:
            m = re.match(r'^([^.!?]+?)\s+(?:is|are|was|were)\s+', df, re.I)
            if m:
                subj = m.group(1).strip()
                if len(subj.split()) <= 4 and len(subj) > 2:
                    subj_words = [w.strip(".,!?\"'") for w in subj.lower().split()]
                    conversational = {"okay", "ok", "see", "this", "that", "how", "why", "we", "you", "i", "me", "my", "our", "us", "here", "there", "what", "go", "let", "lets", "let's", "actually", "basically", "essentially", "simply", "really", "so", "now", "just"}
                    if not any(w in conversational for w in subj_words):
                        interview_questions.append(f"What is {subj} and how is it used in the context of {topic_title}?")
        
        if (steps or procedures) and not interview_questions:
            interview_questions.append(f"What are the key steps or commands required to implement or configure {topic_title}?")
        if comparisons:
            interview_questions.append(f"How does {topic_title} compare to other alternatives discussed in this section?")
            
    if not interview_questions:
        interview_questions.append(f"What is the primary subject of {topic_title} and its main components?")

    return {
        # New Knowledge Layer schema
        "concept": topic_title,
        "definition": definitions[0] if definitions else (explanation_parts[0] if explanation_parts else ""),
        "explanation": explanation_text,
        "analogy": analogies[0] if analogies else "",
        "examples": examples[:3],
        "procedures": steps[:5] if steps else procedures[:5],
        "misconceptions": misconceptions[:4],
        "applications": features[:4],
        "commands": terminal_commands[:4],
        "formulas": formulas_list[:3],
        "warnings": warnings_list[:3],
        "best_practices": best_practices_list[:3] if best_practices_list else important[:3],
        "interview_questions": interview_questions[:3],
        "keywords": terms[:12],
        "code": code_snippets[:3],
        "output": [],
        "summary": definitions[0] if definitions else (explanation_parts[0] if explanation_parts else f"Key concepts of {topic_title}."),
        
        # Legacy/compatibility schema
        'definitions': definitions[:5],
        'procedures': procedures[:6],
        'examples': examples[:3],
        'features': features[:4],
        'comparisons': comparisons[:3],
        'important': important[:4],
        'steps': steps[:6],
        'analogies': analogies[:3],
        'misconceptions': misconceptions[:4],
        'ranked_general': general[:8],
        'terms': terms[:12],
        'topic_title': topic_title,
        'ranked_sentences': general[:8],
        'years': re.findall(r'\b([5-9][0-9]{2}|[1-2][0-9]{3})\b', text),
        'year_sentences': [],
        'definition_sentences': definitions,
        'all_sentences': sentences,
        'has_terms': bool(terms),
        'is_rich': len(definitions) > 0 or len(general) > 2,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 — Build Detailed Notes (Structured Educational Content)
# ─────────────────────────────────────────────────────────────────────────────

def generate_markdown_comparison_table(comparisons: List[str]) -> str:
    """Generate a formatted markdown comparison table from comparative sentences."""
    if not comparisons or len(comparisons) < 2:
        return ""
        
    # 1. Detect compared entities
    entity1, entity2 = None, None
    for sent in comparisons:
        m1 = re.search(r'\b([\w\s-]{2,20})\s+vs\.?\s+([\w\s-]{2,20})\b', sent, re.I)
        if m1:
            entity1, entity2 = m1.group(1).strip(), m1.group(2).strip()
            break
        m2 = re.search(r'\bdifference\s+between\s+([\w\s-]{2,20})\s+and\s+([\w\s-]{2,20})\b', sent, re.I)
        if m2:
            entity1, entity2 = m2.group(1).strip(), m2.group(2).strip()
            break
            
    # If not found, look for common nouns in comparisons
    if not entity1 or not entity2:
        words = []
        for sent in comparisons:
            words.extend(re.findall(r'\b[a-zA-Z]{3,}\b', sent))
        counts = Counter([w.capitalize() for w in words if w.lower() not in _STOP_WORDS])
        top_words = [w for w, _ in counts.most_common(2)]
        if len(top_words) == 2:
            entity1, entity2 = top_words[0], top_words[1]
        else:
            entity1, entity2 = "Concept A", "Concept B"
            
    # 2. Extract comparison rows
    rows = []
    contrast_words = [r'\bwhile\b', r'\bwhereas\b', r'\bunlike\b', r'\bbut\b', r'\bin\s+contrast\s+to\s+[^,]+,']
    
    for sent in comparisons:
        split_found = False
        for cw in contrast_words:
            parts = re.split(cw, sent, flags=re.I)
            if len(parts) == 2:
                left, right = parts[0].strip(), parts[1].strip()
                left = left.rstrip(',; ')
                right = right.lstrip(',; ')
                
                e1_in_left = entity1.lower() in left.lower()
                e2_in_left = entity2.lower() in left.lower()
                e1_in_right = entity1.lower() in right.lower()
                e2_in_right = entity2.lower() in right.lower()
                
                val1, val2 = "", ""
                if e1_in_left and e2_in_right:
                    val1, val2 = left, right
                elif e2_in_left and e1_in_right:
                    val1, val2 = right, left
                else:
                    val1, val2 = left, right
                    
                feature = "Comparison Point"
                v_match = re.search(r'\b(?:is|are|has|have|uses|enables|supports|allows)\b\s+(\w+)', val1.lower())
                if v_match:
                    feature = v_match.group(0).capitalize()
                
                rows.append((feature, val1, val2))
                split_found = True
                break
        
        if not split_found:
            feature = "Note"
            if entity1.lower() in sent.lower():
                rows.append((feature, sent, "-"))
            elif entity2.lower() in sent.lower():
                rows.append((feature, "-", sent))
            else:
                rows.append((feature, sent, sent))
                
    if not rows:
        return ""
        
    md = f"| Feature | {entity1} | {entity2} |\n"
    md += "| --- | --- | --- |\n"
    for f, v1, v2 in rows[:5]:
        v1_clean = re.sub(rf'\b{entity1}\b', '', v1, flags=re.I).strip().strip(',.').capitalize()
        v2_clean = re.sub(rf'\b{entity2}\b', '', v2, flags=re.I).strip().strip(',.').capitalize()
        if not v1_clean: v1_clean = v1
        if not v2_clean: v2_clean = v2
        md += f"| {f} | {v1_clean} | {v2_clean} |\n"
        
    return md


def calculate_concept_density(knowledge: Dict, topic_title: str) -> Dict[str, str]:
    """Calculate topic concept density category and display badge."""
    defs = len(knowledge.get('definitions', []))
    steps = len(knowledge.get('steps', [])) + len(knowledge.get('procedures', []))
    terms = len(knowledge.get('terms', []))
    
    all_sents = (
        knowledge.get('definitions', []) +
        knowledge.get('procedures', []) +
        knowledge.get('steps', []) +
        knowledge.get('ranked_general', [])
    )
    word_count = sum(len(s.split()) for s in all_sents) or 1
    
    score = (defs * 3.0 + steps * 1.5 + terms * 0.5) / (word_count / 100 + 1)
    
    if score >= 3.0:
        return {"density": "Dense", "badge": "🔴 Dense"}
    elif score >= 1.5:
        return {"density": "Moderate", "badge": "🟡 Moderate"}
    else:
        return {"density": "Light", "badge": "🟢 Light"}


def get_original_index(sub_sent: str, sentences: List[str]) -> int:
    """Find the index of the sentence in `sentences` that best matches `sub_sent`."""
    if not sentences:
        return 999999
        
    sub_clean = re.sub(r'[^\w\s]', '', sub_sent.lower()).strip()
    if not sub_clean:
        return 999999
        
    sub_words = set(sub_clean.split())
    if not sub_words:
        return 999999
        
    best_idx = 999999
    best_overlap = -1
    best_ratio = -1.0
    
    for idx, sent in enumerate(sentences):
        sent_clean = re.sub(r'[^\w\s]', '', sent.lower()).strip()
        sent_words = set(sent_clean.split())
        
        # Word overlap
        overlap = len(sub_words & sent_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_ratio = overlap / max(len(sub_words | sent_words), 1)
            best_idx = idx
        elif overlap == best_overlap and overlap > 0:
            # Tie breaker: Jaccard similarity ratio
            ratio = overlap / max(len(sub_words | sent_words), 1)
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx
                
    # If no word overlap is found, check if sub_sent is a substring of any sentence
    if best_overlap <= 0:
        for idx, sent in enumerate(sentences):
            if sub_clean in sent.lower() or sent.lower() in sub_sent.lower():
                return idx
                
    return best_idx


def sort_chronologically(sub_sents: List[str], sentences: List[str]) -> List[str]:
    """Sort a list of sub-sentences chronologically based on their origin in `sentences`."""
    if not sub_sents or not sentences:
        return sub_sents
    # Keep stable sort using original index as key
    return sorted(sub_sents, key=lambda s: get_original_index(s, sentences))


def build_notes_from_knowledge(knowledge: Dict, topic_title: str) -> Dict:
    """
    Render Detailed Notes (markdown) and Quick Revision from the structured Knowledge Layer dict.
    """
    concept = knowledge.get("concept", topic_title)
    definition = knowledge.get("definition", "")
    explanation = knowledge.get("explanation", "")
    analogy = knowledge.get("analogy", "")
    examples = knowledge.get("examples", [])
    procedures = knowledge.get("procedures", [])
    misconceptions = knowledge.get("misconceptions", [])
    applications = knowledge.get("applications", [])
    commands = knowledge.get("commands", [])
    formulas = knowledge.get("formulas", [])
    warnings = knowledge.get("warnings", [])
    best_practices = knowledge.get("best_practices", [])
    interview_questions = knowledge.get("interview_questions", [])
    keywords = knowledge.get("keywords", [])
    code = knowledge.get("code", [])
    output = knowledge.get("output", [])
    summary = knowledge.get("summary", "")
    
    # ── Summary & Definition ──
    if not summary:
        if definition:
            summary = definition
        elif explanation:
            summary = explanation.split('.')[0] + '.'
        else:
            summary = f"This section covers the key concepts of {concept}."

    # ── Build Markdown ──
    md_lines = [f"# {concept} Notes\n"]
    
    # Check for custom sections
    has_custom = False
    custom_lines = []
    text_lower = concept.lower() + " " + " ".join(examples + warnings).lower()
    
    # Custom sections for API / Restaurant / Weather / JSON (as before)
    if "api" in concept.lower() or "application programming interface" in concept.lower():
        has_custom = True
        custom_lines.append(f"### {concept} Concepts\n")
        custom_lines.append("- An API (Application Programming Interface) is a protocol that enables two-way communication between a client (Front End) and a server (Back End).")
        custom_lines.append("- It allows applications to request and exchange data dynamically through standard interfaces (like REST APIs) without direct database access.")
        custom_lines.append("")
        if any(w in text_lower for w in ["request", "response", "client", "server", "http", "cycle"]):
            custom_lines.append("#### How API Works\n")
            custom_lines.append("##### Request–Response Cycle\n")
            custom_lines.append("- **Client Request:** The client sends an HTTP Request to the server through the API.")
            custom_lines.append("- **Server Processing:** The server processes the request and retrieves the requested data.")
            custom_lines.append("- **Server Response:** The server returns an HTTP Response through the API to the client.\n")
            custom_lines.append("##### Flow Diagram\n")
            custom_lines.append("```text")
            custom_lines.append("Client (Front End)")
            custom_lines.append("        |")
            custom_lines.append("   HTTP Request")
            custom_lines.append("        |")
            custom_lines.append("      API")
            custom_lines.append("        |")
            custom_lines.append("Server (Back End)")
            custom_lines.append("        |")
            custom_lines.append("  HTTP Response")
            custom_lines.append("        |")
            custom_lines.append("      API")
            custom_lines.append("        |")
            custom_lines.append("Client (Front End)")
            custom_lines.append("```")
            custom_lines.append("")
            
    if any(w in text_lower for w in ["restaurant", "waiter", "kitchen", "cook"]):
        has_custom = True
        custom_lines.append("#### Restaurant Analogy\n")
        custom_lines.append("##### Components\n")
        custom_lines.append("| Real World Component | Software World Equivalent | Description |")
        custom_lines.append("| -------------------- | ------------------------- | ----------- |")
        custom_lines.append("| Customer | Front End (Client) | Requests the food/data. |")
        custom_lines.append("| Waiter | API (Bridge) | Carries the request and serves the result. |")
        custom_lines.append("| Kitchen/Cook | Back End (Server) | Prepares the food/data. |\n")
        custom_lines.append("##### Process Flow\n")
        custom_lines.append("- **Order Food:** The customer places an order with the waiter.")
        custom_lines.append("- **Submit Order:** The waiter takes the order to the kitchen.")
        custom_lines.append("- **Prepare Food:** The kitchen prepares the ordered food.")
        custom_lines.append("- **Deliver Food:** The waiter delivers the prepared food back to the customer.\n")
        custom_lines.append("##### Key Idea\n")
        custom_lines.append("* The API acts as a communication bridge between the Front End and Back End. Direct communication is avoided; all requests flow through the API.")
        custom_lines.append("")
        
    if any(w in text_lower for w in ["weather", "radar", "thermometer", "meteorologist"]):
        has_custom = True
        custom_lines.append("#### Weather Application Example\n")
        custom_lines.append("##### The Problem\n")
        custom_lines.append("Suppose you are building a weather application.\n")
        custom_lines.append("##### Requirements & Challenge\n")
        custom_lines.append("* Display current weather information for a specific date, time, and location.")
        custom_lines.append("* Developers usually do not have meteorological equipment (like thermometers or radar systems) and are not meteorologists.\n")
        custom_lines.append("##### The Solution\n")
        custom_lines.append("Use a **Weather API** provided by meteorological data services.\n")
        custom_lines.append("##### How It Works\n")
        custom_lines.append("- **Send Query:** Send the required parameters (date, time, location) to the API.")
        custom_lines.append("- **Retrieve Data:** The API retrieves weather information.")
        custom_lines.append("- **Return Format:** The API returns the data, usually in **JSON format**.")
        custom_lines.append("- **Render:** Display the weather data on the website or application.")
        custom_lines.append("")

    if "json" in text_lower or "javascript object notation" in text_lower:
        has_custom = True
        custom_lines.append("#### JSON Response\n")
        custom_lines.append("* Most APIs return data in **JSON (JavaScript Object Notation)** format.")
        custom_lines.append("* JSON is easy for applications to read and process.")
        custom_lines.append("")

    if has_custom:
        md_lines.extend(custom_lines)
        
    # Conceptual/textbook structure (Always render this to preserve maximum depth and details!)
    if definition:
        md_lines.append(f"### {concept} Definition\n")
        md_lines.append(f"- {definition}\n")
        
    if explanation:
        md_lines.append(f"### Core Concepts & Explanation\n")
        # Render explanation as a cohesive paragraph, not disconnected bullets.
        # Split into sentences only to clean up whitespace, then re-join as flowing text.
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', explanation) if s.strip()]
        if len(sentences) <= 2:
            # Short explanation: render as a single paragraph
            md_lines.append(explanation.strip() + "\n")
        else:
            # Multi-sentence: render as a paragraph with the first sentence
            # as a topic opener, then the rest as a flowing continuation.
            paragraph = " ".join(sentences)
            md_lines.append(paragraph + "\n")
        md_lines.append("")
        
    if analogy:
        md_lines.append("### 💡 Analogy\n")
        md_lines.append(f"- {analogy}\n")
        
    if misconceptions:
        md_lines.append("### ⚠️ What This Is NOT\n")
        for m in misconceptions:
            md_lines.append(f"- {m}")
        md_lines.append("")
        
    if procedures:
        md_lines.append("### Implementation Procedures\n")
        for p in procedures:
            md_lines.append(f"- {p}")
        md_lines.append("")
        
    if applications:
        md_lines.append("### Practical Applications & Features\n")
        for a in applications:
            md_lines.append(f"- {a}")
        md_lines.append("")
        
    if examples:
        md_lines.append("### Examples & Use Cases\n")
        for e in examples:
            md_lines.append(f"- {e}")
        md_lines.append("")

    # Code snippets — only wrap in fenced code block if the snippet looks like actual code
    if code:
        _code_fence_re = re.compile(r'(def |class |import |from \w+ import|const |let |return |lambda |yield |async |await |elif |else:|except:)', re.I)
        _actual_code = [s for s in code if _code_fence_re.search(s) or s.strip().startswith('```')]
        _prose_code = [s for s in code if s not in _actual_code]

        # Render actual code snippets inside fenced blocks
        if _actual_code:
            md_lines.append("### Code Implementation\n")
            for snippet in _actual_code:
                if not snippet.strip().startswith("```"):
                    # Choose language tag based on content
                    lang = "python"
                    if any(t in snippet for t in ["const ", "let ", "function ", "=>", "document.", "console."]):
                        lang = "javascript"
                    elif any(t in snippet for t in ["<", ">", "html", "div", "span"]):
                        lang = "html"
                    md_lines.append(f"```{lang}")
                    md_lines.append(snippet.strip())
                    md_lines.append("```\n")
                else:
                    md_lines.append(snippet.strip() + "\n")

        # Misclassified prose — render as bullet points instead
        if _prose_code:
            for snippet in _prose_code:
                md_lines.append(f"- {snippet.strip()}")
            md_lines.append("")

    # Terminal Commands
    if commands:
        md_lines.append("### Terminal Setup & Commands\n")
        md_lines.append("```bash")
        for cmd in commands:
            md_lines.append(cmd)
        md_lines.append("```\n")

    # Warnings / Pitfalls
    if warnings:
        md_lines.append("### ⚠️ Common Mistakes & Warnings\n")
        for w in warnings:
            md_lines.append(f"- {w}")
        md_lines.append("")

    # Best practices
    if best_practices:
        md_lines.append("### ⚡ Best Practices & Key Takeaways\n")
        for bp in best_practices:
            md_lines.append(f"- {bp}")
        md_lines.append("")

    # Interview Questions
    if interview_questions:
        md_lines.append("### 🧠 Concept Check & Review\n")
        for idx_q, q in enumerate(interview_questions):
            md_lines.append(f"Question {idx_q+1}: {q}\n")

    markdown_notes = "\n".join(md_lines).strip()
    
    # Re-calculate density score
    defs_count = 1 if definition else 0
    steps_count = len(procedures)
    terms_count = len(keywords)
    total_words = len(markdown_notes.split()) or 1
    
    score = (defs_count * 3.0 + steps_count * 1.5 + terms_count * 0.5) / (total_words / 100 + 1)
    if score >= 3.0:
        density = "Dense"
        badge = "🔴 Dense"
    elif score >= 1.5:
        density = "Moderate"
        badge = "🟡 Moderate"
    else:
        density = "Light"
        badge = "🟢 Light"
        
    # Reconstruct dynamic sections list for frontend compatibility
    sections = []
    if definition:
        sections.append({"title": "Definition", "icon": "📌", "content": [definition]})
    if analogy:
        sections.append({"title": "Analogy", "icon": "💡", "content": [analogy]})
    if misconceptions:
        sections.append({"title": "What This Is NOT", "icon": "⚠️", "content": misconceptions})
    if procedures:
        sections.append({"title": "Steps", "icon": "⚙️", "content": procedures})
    if examples:
        sections.append({"title": "Example", "icon": "🧪", "content": examples})
    if warnings:
        sections.append({"title": "Common Mistakes", "icon": "⚠️", "content": warnings})
    if best_practices:
        sections.append({"title": "Key Takeaways", "icon": "⚡", "content": best_practices})
    if interview_questions:
        sections.append({"title": "Interview Questions", "icon": "💬", "content": interview_questions})
        
    return {
        "summary": summary,
        "what_is_it": definition or (explanation.split('.')[0] + '.' if explanation else ""),
        "why_matters": applications[0] if applications else (best_practices[0] if best_practices else ""),
        "how_it_works": procedures[:5],
        "example": examples[0] if examples else "",
        "key_points": best_practices[:7] if best_practices else (procedures[:7] if procedures else []),
        "important_terms": keywords[:8],
        "examples": examples[:3],
        "comparisons": knowledge.get("comparisons", [])[:2],
        "analogies": [analogy] if analogy else [],
        "misconceptions": misconceptions[:4],
        "common_mistakes": warnings[:3],
        "interview_questions": interview_questions[:3],
        "sections": sections,
        "markdown": markdown_notes,
        "density": density,
        "density_badge": badge,
    }


def build_structured_notes(knowledge: Dict, topic_title: str) -> Dict:
    """
    Stage 3: Build multi-section educational notes from knowledge units.
    NOT a transcript. NOT a summary. A structured textbook entry.
    """
    return build_notes_from_knowledge(knowledge, topic_title)


# Keep old name for backward compat
def build_detailed_notes(facts: Dict, topic_title: str) -> Dict:
    """Alias — routes to build_structured_notes."""
    return build_structured_notes(facts, topic_title)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4 — Quick Revision (30-second read)
# ─────────────────────────────────────────────────────────────────────────────

def build_quick_revision_30s(detailed: Dict, topic_title: str) -> Dict:
    """
    Stage 4: Build a 30-second revision sheet from Detailed Notes.
    Max ~200 words. Bullets only. No paragraphs. No transcript sentences.
    """
    what_is_it = detailed.get('what_is_it', '')
    why_matters = detailed.get('why_matters', '')
    key_points = detailed.get('key_points', [])
    terms = detailed.get('important_terms', [])
    summary = detailed.get('summary', '')
    how_it_works = detailed.get('how_it_works', [])
    comparisons = detailed.get('comparisons', [])

    # Definition: first sentence of what_is_it, or first sentence of summary
    definition_source = what_is_it or summary
    if definition_source:
        first_sent = re.split(r'(?<=[.!?])\s+', definition_source)[0]
        definition = first_sent.strip()
        if not definition.endswith('.'):
            definition += '.'
    else:
        definition = f"{topic_title} — key concepts."

    # Key facts: compress to ≤12 words each
    fact_pool = (
        key_points[:4] +
        how_it_works[:3] +
        comparisons[:2]
    )
    facts = []
    for point in fact_pool:
        if not point:
            continue
        # Strip sentence to core fact (≤12 words)
        point = point.rstrip('.')
        words = point.split()
        if len(words) <= 14:
            facts.append(point)
        else:
            # Find natural break
            for sep in [',', ';', ' —', ' -', ' which', ' that']:
                if sep in point:
                    short = point.split(sep)[0].strip()
                    if 5 <= len(short.split()) <= 14:
                        facts.append(short)
                        break
            else:
                facts.append(' '.join(words[:12]) + '…')
        if len(facts) >= 5:
            break

    # No fallback facts from terms to avoid templated hallucinations

    # Remember: most distinctive single sentence
    remember = ''
    if comparisons:
        remember = comparisons[0]
    elif why_matters:
        # Short version of why it matters
        words = why_matters.split()
        remember = ' '.join(words[:15])
        if len(why_matters.split()) > 15:
            remember += '…'
    elif key_points:
        words = key_points[0].split()
        remember = ' '.join(words[:12])

    return {
        'definition': definition,
        'facts': facts[:5],
        'terms': terms[:5],
        'remember': remember,
        # Backward compat fields
        'one_liner': definition.split('.')[0] if definition else topic_title,
        'bullets': facts[:5],
    }


# Keep old name for backward compat
def build_revision_notes(detailed: Dict, topic_title: str) -> Dict:
    """Alias — routes to build_quick_revision_30s."""
    return build_quick_revision_30s(detailed, topic_title)


# ─────────────────────────────────────────────────────────────────────────────
# Flashcards & Quiz builders (derive from knowledge, not transcript)
# ─────────────────────────────────────────────────────────────────────────────

def build_flashcards(facts: Dict, topic_title: str) -> List[Dict]:
    """Build Q&A flashcards from knowledge units."""
    cards = []
    defs = facts.get('definitions', facts.get('definition_sentences', []))
    features = facts.get('features', [])
    comparisons = facts.get('comparisons', [])
    terms = facts.get('terms', [])
    examples = facts.get('examples', [])
    ranked = facts.get('ranked_general', facts.get('ranked_sentences', []))

    # 1. Definition cards (best quality)
    for sent in defs[:5]:
        if len(cards) >= 10:
            break
        subjects = re.findall(r'\b[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]+)*\b', sent)
        subjects = [s for s in subjects if s.lower() not in _STOP_WORDS and len(s) > 3]
        if subjects:
            cards.append({
                "question": f"What is {subjects[0]}?",
                "answer": sent.strip()
            })
        else:
            # Extract subject from "[X] is a [Y]" pattern
            m = re.match(r'^([^.!?]+?)\s+(?:is|are|was)\s+', sent, re.I)
            if m:
                subj = m.group(1).strip()[:40]
                cards.append({"question": f"What is {subj}?", "answer": sent.strip()})

    # 2. Feature/advantage cards
    for sent in features[:3]:
        if len(cards) >= 10:
            break
        cards.append({
            "question": f"What is an advantage or use case of {topic_title}?",
            "answer": sent.strip()
        })

    # 3. Comparison cards
    for sent in comparisons[:2]:
        if len(cards) >= 10:
            break
        cards.append({
            "question": f"How does {topic_title} compare to similar concepts?",
            "answer": sent.strip()
        })

    # 4. Example cards
    for sent in examples[:2]:
        if len(cards) >= 10:
            break
        cards.append({
            "question": f"Give an example related to {topic_title}.",
            "answer": sent.strip()
        })

    # 5. Term cards
    for term in terms[:4]:
        if len(cards) >= 10:
            break
        if not any(term in c.get('answer', '') for c in cards):
            cards.append({
                "question": f"What is the significance of {term}?",
                "answer": f"{term} is a key concept related to {topic_title}."
            })

    # Pad to minimum 4
    if not cards and ranked:
        cards.append({
            "question": f"What does this section of {topic_title} explain?",
            "answer": ranked[0]
        })

    return cards[:10]


def build_quiz(facts: Dict, topic_title: str) -> List[Dict]:
    """Build MCQ quiz from knowledge units — NOT templates."""
    questions = []
    defs = facts.get('definitions', facts.get('definition_sentences', []))
    features = facts.get('features', [])
    comparisons = facts.get('comparisons', [])
    terms = facts.get('terms', [])
    ranked = facts.get('ranked_general', facts.get('ranked_sentences', []))
    years = facts.get('years', [])

    # 1. Definition-based MCQ (best quality)
    for sent in defs[:2]:
        if len(questions) >= 5 or len(sent) < 40:
            continue
        m = re.match(r'^([^.!?]{5,60}?)\s+(?:is|are|was)\s+', sent, re.I)
        if m:
            subj = m.group(1).strip()
            questions.append({
                "question": f"Which statement correctly describes {subj}?",
                "options": [
                    f"A) {sent[:130]}",
                    f"B) {subj} is not related to {topic_title}",
                    f"C) {subj} is the opposite of what is described",
                    "D) None of the above"
                ],
                "correct_answer": "A",
                "explanation": f"The content states: {sent[:160]}"
            })

    # 2. Feature/use-case MCQ
    for sent in features[:1]:
        if len(questions) >= 5:
            break
        questions.append({
            "question": f"What is a key capability or benefit in {topic_title}?",
            "options": [
                f"A) {sent[:120]}",
                f"B) It has no practical application",
                f"C) It makes things more complex without benefit",
                "D) It is only applicable in other contexts"
            ],
            "correct_answer": "A",
            "explanation": sent[:160]
        })

    # 3. Term-based MCQ
    if len(terms) >= 3 and len(questions) < 5:
        questions.append({
            "question": f"Which of the following is a key concept in {topic_title}?",
            "options": [
                f"A) {terms[0]}",
                f"B) {terms[1] if len(terms)>1 else 'Unrelated Concept'}",
                f"C) {terms[2] if len(terms)>2 else 'Another Term'}",
                "D) None of the above"
            ],
            "correct_answer": "A",
            "explanation": f"{terms[0]} is directly covered in this section."
        })

    # 4. Year-based MCQ
    if years and len(questions) < 5:
        yr = years[0]
        base = int(yr)
        questions.append({
            "question": f"Which year is significant in the context of {topic_title}?",
            "options": [f"A) {yr}", f"B) {base+50}", f"C) {base-50}", f"D) {base+100}"],
            "correct_answer": "A",
            "explanation": f"{yr} is mentioned as a key year in this section."
        })

    # 5. Content-based MCQ from ranked sentences
    for sent in ranked[:2]:
        if len(questions) >= 5 or len(sent) < 40:
            continue
        questions.append({
            "question": f"Which statement about {topic_title} is supported by the content?",
            "options": [
                f"A) {sent[:120]}",
                "B) The content contains no factual statements",
                f"C) The opposite of option A",
                "D) None of the above"
            ],
            "correct_answer": "A",
            "explanation": f"The content directly states: {sent[:150]}"
        })

    # Pad to 5 minimum
    while len(questions) < 3:
        term_str = ', '.join(terms[:2]) if terms else topic_title
        questions.append({
            "question": f"What is the primary focus of {topic_title}?",
            "options": [
                f"A) {term_str} and related concepts",
                "B) Unrelated modern technology",
                "C) Historical fiction",
                "D) Geographic exploration"
            ],
            "correct_answer": "A",
            "explanation": f"{topic_title} focuses on the stated subject matter."
        })
        break

    return questions[:5]


# ─────────────────────────────────────────────────────────────────────────────
# Legacy wrappers (for backward compat with old code that calls extract_facts)
# ─────────────────────────────────────────────────────────────────────────────

def extract_facts(text: str, topic_title: str = '') -> Dict[str, Any]:
    """Legacy wrapper — calls extract_knowledge_units."""
    return extract_knowledge_units(text, topic_title)


def build_summary(facts: Dict, topic_title: str) -> str:
    """Legacy: returns summary string."""
    detailed = build_structured_notes(facts, topic_title)
    return detailed['summary']


def build_key_points(facts: Dict, topic_title: str) -> List[str]:
    """Legacy: returns key_points list."""
    detailed = build_structured_notes(facts, topic_title)
    return detailed['key_points']


def build_important_terms(facts: Dict, topic_title: str) -> List[str]:
    """Legacy: returns terms list."""
    return facts.get('terms', [topic_title])[:10]


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_key_terms(text: str, word_freq: Counter) -> List[str]:
    """Extract important technical terms, proper nouns, and repeated concepts."""
    terms = []
    seen = set()

    # Multi-word proper noun phrases (e.g., "REST API", "Django REST Framework")
    phrase_re = re.compile(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+\b')
    phrases = phrase_re.findall(text)
    phrase_freq = Counter(phrases)
    for phrase, _ in phrase_freq.most_common(8):
        plow = phrase.lower()
        if plow not in seen and not _is_stop_phrase(phrase):
            terms.append(phrase)
            seen.add(plow)

    # Single proper nouns
    single_re = re.compile(r'\b[A-Z][a-zA-Z]{3,}\b')
    singles = single_re.findall(text)
    single_freq = Counter(singles)
    for name, count in single_freq.most_common(10):
        nlow = name.lower()
        if nlow not in seen and name not in _STOP_WORDS and len(name) > 3:
            if not any(name in t for t in terms):
                terms.append(name)
                seen.add(nlow)
        if len(terms) >= 12:
            break

    # Repeated technical lowercase terms (≥2 occurrences, ≥6 chars)
    tech = [(w, c) for w, c in word_freq.most_common(25)
            if c >= 2 and len(w) >= 5 and w not in _STOP_WORDS and w not in seen]
    for term, _ in tech[:5]:
        if term not in seen:
            terms.append(term.capitalize())
            seen.add(term)
        if len(terms) >= 14:
            break

    return terms[:12]


def _rank_by_density(sentences: List[str], tfidf_dict: Dict[str, float]) -> List[str]:
    """Rank sentences by information density (TF-IDF weights + factual patterns)."""
    if not sentences:
        return []

    scored = []
    for sent in sentences:
        words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', sent)
                 if w.lower() not in _STOP_WORDS]
        if not words:
            continue

        base = sum(tfidf_dict.get(w, 0.0) for w in words) / len(words)
        bonus = 1.0

        # Factual content bonus
        if _DEF_RE.search(sent) or _DEF_RE2.search(sent):
            bonus *= 1.4
        if re.search(r'\b\d+\b', sent):
            bonus *= 1.2
        proper = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', sent)
        if proper:
            bonus *= (1 + 0.05 * min(len(proper), 5))

        # Length sweet spot (8-40 words)
        wc = len(sent.split())
        if wc < 6:
            bonus *= 0.4
        elif wc > 60:
            bonus *= 0.6
        elif wc > 40:
            bonus *= 0.85

        scored.append((base * bonus, sent))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate by word overlap
    selected = []
    selected_sets = []
    for _, sent in scored:
        sw = set(re.findall(r'\b[a-zA-Z]{4,}\b', sent.lower())) - _STOP_WORDS
        dup = any(
            len(sw & ex) / max(len(sw | ex), 1) > 0.55
            for ex in selected_sets
        )
        if not dup:
            selected.append(sent)
            selected_sets.append(sw)

    return selected


def _deduplicate(items: List[str]) -> List[str]:
    """Remove very similar strings from a list."""
    if not items:
        return []
    seen = []
    seen_sets = []
    for item in items:
        words = set(re.findall(r'\b[a-zA-Z]{4,}\b', item.lower())) - _STOP_WORDS
        dup = any(
            len(words & ex) / max(len(words | ex), 1) > 0.6
            for ex in seen_sets
        )
        if not dup:
            seen.append(item)
            seen_sets.append(words)
    return seen


def _is_stop_phrase(phrase: str) -> bool:
    return all(w in _STOP_WORDS or w in {'The', 'This', 'That', 'These', 'Those', 'An', 'A'}
               for w in phrase.split())


def _is_generic(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in _GENERIC_REJECT)


def _empty_knowledge(topic_title: str) -> Dict:
    return {
        # New Knowledge Layer schema
        "concept": topic_title,
        "definition": "",
        "explanation": "",
        "analogy": "",
        "examples": [],
        "procedures": [],
        "misconceptions": [],
        "applications": [],
        "commands": [],
        "formulas": [],
        "warnings": [],
        "best_practices": [],
        "interview_questions": [],
        "keywords": [],
        "code": [],
        "output": [],
        "summary": "",
        
        # Legacy/compatibility schema
        'definitions': [], 'procedures': [], 'examples': [], 'features': [],
        'comparisons': [], 'important': [], 'steps': [], 'analogies': [],
        'misconceptions': [], 'ranked_general': [],
        'terms': [], 'topic_title': topic_title,
        'ranked_sentences': [], 'years': [], 'year_sentences': [],
        'definition_sentences': [], 'all_sentences': [],
        'has_terms': False, 'is_rich': False,
    }


def populate_legacy_keys_on_knowledge(k: dict) -> dict:
    """
    Ensure a dictionary returned by LLM or parser contains both the new conceptual keys
    and the legacy compatibility keys, populating defaults where necessary.
    """
    # Ensure new keys exist
    concept = k.get("concept", k.get("topic_title", k.get("topic", "")))
    k["concept"] = concept
    
    definition = k.get("definition", "")
    k["definition"] = definition
    
    explanation = k.get("explanation", "")
    k["explanation"] = explanation
    
    analogy = k.get("analogy", "")
    k["analogy"] = analogy
    
    examples = k.get("examples", [])
    if not isinstance(examples, list):
        examples = [examples] if examples else []
    k["examples"] = examples
    
    procedures = k.get("procedures", [])
    if not isinstance(procedures, list):
        procedures = [procedures] if procedures else []
    k["procedures"] = procedures
    
    misconceptions = k.get("misconceptions", [])
    if not isinstance(misconceptions, list):
        misconceptions = [misconceptions] if misconceptions else []
    k["misconceptions"] = misconceptions
    
    applications = k.get("applications", [])
    if not isinstance(applications, list):
        applications = [applications] if applications else []
    k["applications"] = applications
    
    commands = k.get("commands", [])
    if not isinstance(commands, list):
        commands = [commands] if commands else []
    k["commands"] = commands
    
    formulas = k.get("formulas", [])
    if not isinstance(formulas, list):
        formulas = [formulas] if formulas else []
    k["formulas"] = formulas
    
    warnings = k.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = [warnings] if warnings else []
    k["warnings"] = warnings
    
    best_practices = k.get("best_practices", [])
    if not isinstance(best_practices, list):
        best_practices = [best_practices] if best_practices else []
    k["best_practices"] = best_practices
    
    interview_questions = k.get("interview_questions", [])
    if not isinstance(interview_questions, list):
        interview_questions = [interview_questions] if interview_questions else []
    k["interview_questions"] = interview_questions
    
    keywords = k.get("keywords", k.get("terms", []))
    if not isinstance(keywords, list):
        keywords = [keywords] if keywords else []
    k["keywords"] = keywords
    
    code = k.get("code", [])
    if not isinstance(code, list):
        code = [code] if code else []
    k["code"] = code
    
    output = k.get("output", [])
    if not isinstance(output, list):
        output = [output] if output else []
    k["output"] = output
    
    summary = k.get("summary", "")
    k["summary"] = summary

    # Now populate legacy compatibility keys if they do not exist or are empty
    if "definitions" not in k or not k["definitions"]:
        k["definitions"] = [definition] if definition else []
    if "features" not in k or not k["features"]:
        k["features"] = applications
    if "comparisons" not in k or not k["comparisons"]:
        k["comparisons"] = []
    if "important" not in k or not k["important"]:
        k["important"] = (warnings + best_practices)[:4]
    if "steps" not in k or not k["steps"]:
        k["steps"] = procedures
    if "analogies" not in k or not k["analogies"]:
        k["analogies"] = [analogy] if analogy else []
    if "ranked_general" not in k or not k["ranked_general"]:
        k["ranked_general"] = [explanation] if explanation else []
    if "terms" not in k or not k["terms"]:
        k["terms"] = keywords
    if "topic_title" not in k or not k["topic_title"]:
        k["topic_title"] = concept
    if "ranked_sentences" not in k or not k["ranked_sentences"]:
        k["ranked_sentences"] = k["ranked_general"]
    if "years" not in k or not k["years"]:
        k["years"] = []
    if "year_sentences" not in k or not k["year_sentences"]:
        k["year_sentences"] = []
    if "definition_sentences" not in k or not k["definition_sentences"]:
        k["definition_sentences"] = k["definitions"]
    if "all_sentences" not in k or not k["all_sentences"]:
        k["all_sentences"] = k["definitions"] + k["procedures"] + k["examples"] + k["ranked_general"]
    k["has_terms"] = bool(k["terms"])
    k["is_rich"] = len(k["definitions"]) > 0 or len(k["ranked_general"]) > 2

    return k
