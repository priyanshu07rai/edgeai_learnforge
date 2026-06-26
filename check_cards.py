import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

storage = 'storage'
for vid in os.listdir(storage):
    fp = os.path.join(storage, vid, 'flashcards.json')
    if os.path.exists(fp):
        with open(fp, encoding='utf-8') as f:
            data = json.load(f)
        topics = data.get('topics', [])
        print(f"Video: {vid}")
        print(f"Top-level keys: {list(data.keys())}")
        print(f"Topics count: {len(topics)}")
        if topics:
            t0 = topics[0]
            print(f"Topic[0] keys: {list(t0.keys())}")
            topic_name = t0.get('topic', 'N/A')
            print(f"Topic[0] name: {topic_name}")
            cards = t0.get('cards', [])
            print(f"Topic[0] cards: {len(cards)}")
            if cards:
                c0 = cards[0]
                q = c0.get('question', '')[:150]
                a = c0.get('answer', '')[:100]
                print(f"Card[0] question: {q}")
                print(f"Card[0] answer: {a}")
        print()
        break
