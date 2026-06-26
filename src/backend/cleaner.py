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
    # Strip timestamps first
    cleaned = strip_timestamps(raw_text)
    
    # Basic vocal pauses and repetitive filler patterns
    fillers = [
        r'\b(okay|basically|actually|right|uh|ah|um|like|you know|literally|simply|really)\b',
        r'\b(hello\s+everyone|welcome\s+back|welcome\s+to\s+this\s+video)\b',
        r'\b(thank\s+you\s+for\s+watching|subscribe\s+to\s+the\s+channel)\b'
    ]
    for pattern in fillers:
        cleaned = re.sub(pattern, '', cleaned, flags=re.I)
        
    # Standardize spaces and punctuation
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Capitalize sentences and ensure ending periods
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    rebuilt = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
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
    
    # 2. Pre-clean multi-word conversational fillers with regex
    multi_word_fillers = [
        r'\b(you\s+know|welcome\s+back|hello\s+everyone|thank\s+you\s+for\s+watching|subscribe\s+to\s+the\s+channel)\b',
        r'\b(welcome\s+to\s+this\s+video|welcome\s+to\s+this\s+course|welcome\s+to\s+this\s+tutorial)\b',
        r'\b(let\'?s\s+get\s+started|see\s+you\s+in\s+the\s+next|drop\s+a\s+comment|comment\s+below)\b'
    ]
    for pattern in multi_word_fillers:
        text_no_ts = re.sub(pattern, '', text_no_ts, flags=re.I)
        
    # Clean multiple commas/dots resulting from regex replacements
    text_no_ts = re.sub(r'[,.]\s*[,.]+', ',', text_no_ts)
    text_no_ts = re.sub(r'\s+', ' ', text_no_ts).strip()
    
    # 3. Process text with spaCy
    doc = nlp(text_no_ts)
    
    # Conversational markers & fillers
    fillers = {
        "okay", "basically", "actually", "right", "uh", "ah", "um", 
        "like", "mean", "literally", "simply", "really", "so", "now"
    }
    
    # Personal pronouns to filter out when they are part of conversational transitions
    conversation_pronouns = {"i", "me", "my", "we", "us", "our", "you", "your"}
    
    rebuilt_sentences = []
    for sent in doc.sents:
        sent_tokens = []
        for token in sent:
            # Skip duplicate punctuation
            if token.is_punct and token.text in (",", ";", ":", "-"):
                if sent_tokens and sent_tokens[-1] in (",", ";", ":", "-"):
                    continue
                    
            # Skip vocal pauses and interjections
            if token.text.lower() in fillers or token.pos_ == "INTJ":
                continue
                
            # Filter pronouns only when part of conversational transition verbs
            # e.g., "I will explain", "we are going to learn", "I want to show you"
            if token.text.lower() in conversation_pronouns and token.dep_ in ("nsubj", "poss"):
                head_verb = token.head.text.lower()
                if head_verb in {"talk", "explain", "show", "tell", "discuss", "cover", "learn", "see", "understand"}:
                    continue
                    
            sent_tokens.append(token.text)
            
        sent_str = " ".join(sent_tokens).strip()
        # Clean spacing around punctuation
        sent_str = re.sub(r'\s+([.,!?])', r'\1', sent_str)
        # Clean trailing commas before ending punctuation
        sent_str = re.sub(r',\s*([.!?])', r'\1', sent_str)
        # Clean duplicate commas/spaces
        sent_str = re.sub(r',\s*,', ',', sent_str)
        sent_str = re.sub(r'\s+,', ',', sent_str)
        sent_str = re.sub(r'^[,.\s]+', '', sent_str).strip()
        
        # Deduplicate consecutive identical words (e.g. "is is" -> "is")
        sent_str = re.sub(r'\b(\w+)\s+\1\b', r'\1', sent_str, flags=re.I)
        
        if sent_str:
            # Capitalize first letter
            if sent_str[0].islower():
                sent_str = sent_str[0].upper() + sent_str[1:]
            # Ensure it ends with period
            if sent_str[-1] not in '.!?':
                sent_str += '.'
            rebuilt_sentences.append(sent_str)
            
    return deduplicate_consecutive_phrases(" ".join(rebuilt_sentences))
