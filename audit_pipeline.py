import os
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

storage = 'storage'
dirs = [d for d in os.listdir(storage) if os.path.isdir(os.path.join(storage, d))]
print(f"Found {len(dirs)} video directories")

# Find most complete video dir (has both chunks and topics)
best = None
best_file_count = 0
for vid in dirs:
    vdir = os.path.join(storage, vid)
    files = set(os.listdir(vdir))
    if 'chunks.json' in files and 'topics.json' in files:
        if len(files) > best_file_count:
            best_file_count = len(files)
            best = vid

if not best:
    print("No complete video found (needs chunks.json + topics.json)")
    exit()

print(f"Auditing: {best}")
vdir = os.path.join(storage, best)
all_files = os.listdir(vdir)
print(f"Files: {all_files}")

with open(os.path.join(vdir, 'chunks.json'), encoding='utf-8') as f:
    chunks = json.load(f)
with open(os.path.join(vdir, 'topics.json'), encoding='utf-8') as f:
    topics = json.load(f)

print(f"\nTopics: {len(topics)}, Chunks: {len(chunks)}")
print()

print("=" * 70)
print("CHUNK COVERAGE PER TOPIC")
print("=" * 70)
for i, t in enumerate(topics[:10]):
    tid = f"topic_{i}"
    matching = [c for c in chunks if c.get('topic_id') == tid]
    chunk_text = ' '.join(c.get('text', '') for c in matching)
    title = t.get('title', 'NO TITLE')
    
    print(f"[{tid}] {title}")
    print(f"  Matching chunks: {len(matching)}, Total chars: {len(chunk_text)}")
    
    if chunk_text:
        # Show first 500 chars, safely encoded
        preview = chunk_text[:500].encode('ascii', errors='replace').decode('ascii')
        print(f"  Content preview:\n  {preview}")
    else:
        print("  !! NO CHUNK TEXT FOUND - this topic has no content")
    print()

print("=" * 70)
print("TOPIC ID CONSISTENCY CHECK")
print("=" * 70)
chunk_topic_ids = set(c.get('topic_id') for c in chunks)
expected_ids = set(f"topic_{i}" for i in range(len(topics)))
print(f"Expected topic IDs: {sorted(expected_ids)}")
print(f"Found in chunks:    {sorted(chunk_topic_ids)}")
missing = expected_ids - chunk_topic_ids
extra = chunk_topic_ids - expected_ids
if missing:
    print(f"MISSING from chunks: {missing}")
if extra:
    print(f"EXTRA in chunks: {extra}")
if not missing and not extra:
    print("All topic IDs match correctly")

print()
print("=" * 70)
print("NOTES/FLASHCARDS STATUS")
print("=" * 70)
notes_path = os.path.join(vdir, 'notes.json')
flash_path = os.path.join(vdir, 'flashcards.json')

if os.path.exists(notes_path):
    with open(notes_path, encoding='utf-8') as f:
        notes = json.load(f)
    ntopics = notes.get('topics', [])
    print(f"notes.json: {len(ntopics)} topics")
    for n in ntopics[:3]:
        summary = n.get('summary', '')
        kp = n.get('key_points', [])
        safe_summary = summary[:250].encode('ascii', errors='replace').decode('ascii')
        print(f"  Topic: {n.get('topic')}")
        print(f"  Summary: {safe_summary}")
        print(f"  Key points: {len(kp)}")
        if kp:
            safe_kp = kp[0][:150].encode('ascii', errors='replace').decode('ascii')
            print(f"  KP[0]: {safe_kp}")
        print()
else:
    print("notes.json: not yet generated")

if os.path.exists(flash_path):
    with open(flash_path, encoding='utf-8') as f:
        fc = json.load(f)
    ftopics = fc.get('topics', [])
    print(f"flashcards.json: {len(ftopics)} topics")
    for ft in ftopics[:2]:
        cards = ft.get('cards', [])
        print(f"  Topic: {ft.get('topic')}")
        print(f"  Cards: {len(cards)}")
        if cards:
            q = cards[0].get('question', '')
            safe_q = q[:200].encode('ascii', errors='replace').decode('ascii')
            print(f"  Q[0]: {safe_q}")
        print()
else:
    print("flashcards.json: not yet generated")
