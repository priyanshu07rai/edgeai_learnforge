"""
cleaner.py — Pre-processing and Text Cleaning Layer (spaCy + Regex)

Filters vocal stumbles, conversational fillers, and personal pronouns
from transcript text, and segments sentences with correct punctuation and capitalization.
"""
import re

try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
        HAS_SPACY = True
    except OSError:
        # Model not downloaded yet
        HAS_SPACY = False
except ImportError:
    HAS_SPACY = False


def strip_timestamps(text: str) -> str:
    """Strips timestamp brackets like [00:15] or [01:23:45] from transcript text."""
    return re.sub(r'\[\d{1,2}:\d{2}(?::\d{2})?\]', '', text)


def deduplicate_consecutive_phrases(text: str) -> str:
    """
    Deduplicates consecutive identical words or phrases of up to 4 words.
    e.g. "set count set count" -> "set count"
         "initial value initial value" -> "initial value"
    """
    if not text:
        return ""
        
    # 1. Deduplicate consecutive identical words (case-insensitive)
    # e.g., "very very" -> "very", "is is" -> "is"
    text = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', text, flags=re.I)
    
    # 2. Deduplicate consecutive identical 2-word phrases
    # e.g., "initial value initial value" -> "initial value"
    text = re.sub(r'\b(\w+\s+\w+)(?:\s+\1\b)+', r'\1', text, flags=re.I)
    
    # 3. Deduplicate consecutive identical 3-word phrases
    # e.g., "react Fullstack app react Fullstack app" -> "react Fullstack app"
    text = re.sub(r'\b(\w+\s+\w+\s+\w+)(?:\s+\1\b)+', r'\1', text, flags=re.I)
    
    # 4. Deduplicate consecutive identical 4-word phrases
    text = re.sub(r'\b(\w+\s+\w+\s+\w+\s+\w+)(?:\s+\1\b)+', r'\1', text, flags=re.I)
    
    return text



def fallback_clean_regex(raw_text: str) -> str:
    """Fallback regex cleaner when spaCy is unavailable."""
    cleaned = strip_timestamps(raw_text)
    
    # Aggressive conversational banters and introductory noise
    fillers = [
        r'(?:hey|hi|hello)\s+(?:everyone|guys|folks|all|team)\b',
        r'welcome\s+back(?:\s+welcome\s+back)?(?:\s+to\s+another\s+exciting\s+video)?',
        r'welcome\s+to\s+this\s+(?:video|course|tutorial|lecture|lesson)',
        r'and\s+in\s+this\s+video\s+let\'?s\s+talk\s+about',
        r'in\s+this\s+video\s+let\'?s\s+talk\s+about',
        r'let\'?s\s+talk\s+about',
        r'today\s+we\s+are\s+going\s+to\s+(?:talk\s+about|discuss|cover|learn)',
        r'this\s+[\w\s]{2,20}\s+is\s+really\s+a\s+hot\s+topic\s+right\s+now',
        r'you\s+can\s+see\s+the\s+topic\s+in\s+the\s+next\s+video',
        r'maybe\s+on\s+twitter\s+maybe\s+on\s+linkedin',
        r'\b(okay|basically|actually|right|uh|ah|um|like|you know|literally|simply|really)\b',
        r'\b(thank\s+you\s+for\s+watching|subscribe\s+to\s+the\s+channel|drop\s+a\s+comment|comment\s+below)\b'
    ]
    for pattern in fillers:
        cleaned = re.sub(pattern, '', cleaned, flags=re.I)
        
    cleaned = re.sub(r'[,.]\s*[,.]+', '.', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    rebuilt = []
    _DISCARD_STARTERS = ("everyone to", "to another exciting", "let's talk", "let us talk", "hot topic", "next video", "on twitter", "on linkedin")
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 15:
            continue
        if any(sent.lower().startswith(b) for b in _DISCARD_STARTERS):
            continue
        if sent[0].islower():
            sent = sent[0].upper() + sent[1:]
        if sent[-1] not in '.!?':
            sent += '.'
        rebuilt.append(sent)
        
    return deduplicate_consecutive_phrases(" ".join(rebuilt))


def clean_transcript_spacy(raw_text: str) -> str:
    """Uses NLP rules and spaCy dependency parsing to optimize transcript text for LLM generation."""
    if not HAS_SPACY:
        return fallback_clean_regex(raw_text)
        
    # 1. Strip timestamp brackets
    text_no_ts = strip_timestamps(raw_text)
    
    # 2. Pre-clean multi-word conversational fillers and introductory video banter
    multi_word_fillers = [
        r'(?:hey|hi|hello)\s+(?:everyone|guys|folks|all|team)\b',
        r'welcome\s+back(?:\s+welcome\s+back)?(?:\s+to\s+another\s+exciting\s+video)?',
        r'welcome\s+to\s+this\s+(?:video|course|tutorial|lecture|lesson)',
        r'and\s+in\s+this\s+video\s+let\'?s\s+talk\s+about',
        r'in\s+this\s+video\s+let\'?s\s+talk\s+about',
        r'let\'?s\s+talk\s+about',
        r'today\s+we\s+are\s+going\s+to\s+(?:talk\s+about|discuss|cover|learn)',
        r'this\s+[\w\s]{2,20}\s+is\s+really\s+a\s+hot\s+topic\s+right\s+now',
        r'you\s+can\s+see\s+the\s+topic\s+in\s+the\s+next\s+video',
        r'maybe\s+on\s+twitter\s+maybe\s+on\s+linkedin',
        r'\b(you\s+know|thank\s+you\s+for\s+watching|subscribe\s+to\s+the\s+channel)\b',
        r'\b(let\'?s\s+get\s+started|see\s+you\s+in\s+the\s+next|drop\s+a\s+comment|comment\s+below)\b'
    ]
    for pattern in multi_word_fillers:
        text_no_ts = re.sub(pattern, '', text_no_ts, flags=re.I)
        
    # Clean multiple commas/dots resulting from regex replacements
    text_no_ts = re.sub(r'[,.]\s*[,.]+', '.', text_no_ts)
    text_no_ts = re.sub(r'\s+', ' ', text_no_ts).strip()
    
    # 3. Process text with spaCy
    doc = nlp(text_no_ts)
    
    # Conversational markers & fillers
    fillers = {
        "okay", "basically", "actually", "right", "uh", "ah", "um", 
        "like", "mean", "literally", "simply", "really", "so", "now"
    }
    
    conversation_pronouns = {"i", "me", "my", "we", "us", "our", "you", "your"}
    _DISCARD_STARTERS = ("everyone to", "to another exciting", "let's talk", "let us talk", "hot topic", "next video", "on twitter", "on linkedin", "take care")
    
    rebuilt_sentences = []
    for sent in doc.sents:
        sent_tokens = []
        for token in sent:
            if token.is_punct and token.text in (",", ";", ":", "-"):
                if sent_tokens and sent_tokens[-1] in (",", ";", ":", "-"):
                    continue
                    
            if token.text.lower() in fillers or token.pos_ == "INTJ":
                continue
                
            if token.text.lower() in conversation_pronouns and token.dep_ in ("nsubj", "poss"):
                head_verb = token.head.text.lower()
                if head_verb in {"talk", "explain", "show", "tell", "discuss", "cover", "learn", "see", "understand"}:
                    continue
                    
            sent_tokens.append(token.text)
            
        sent_str = " ".join(sent_tokens).strip()
        sent_str = re.sub(r'\s+([.,!?])', r'\1', sent_str)
        sent_str = re.sub(r',\s*([.!?])', r'\1', sent_str)
        sent_str = re.sub(r',\s*,', ',', sent_str)
        sent_str = re.sub(r'\s+,', ',', sent_str)
        sent_str = re.sub(r'^[,.\s]+', '', sent_str).strip()
        
        # Deduplicate consecutive identical words
        sent_str = re.sub(r'\b(\w+)\s+\1\b', r'\1', sent_str, flags=re.I)
        
        if sent_str and len(sent_str) >= 15:
            if any(sent_str.lower().startswith(b) for b in _DISCARD_STARTERS):
                continue
            if sent_str[0].islower():
                sent_str = sent_str[0].upper() + sent_str[1:]
            if sent_str[-1] not in '.!?':
                sent_str += '.'
            rebuilt_sentences.append(sent_str)
            
    return deduplicate_consecutive_phrases(" ".join(rebuilt_sentences))
