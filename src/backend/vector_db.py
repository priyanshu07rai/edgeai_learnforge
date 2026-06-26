"""
vector_db.py — Hierarchical Parent-Child Chunking + FAISS IndexFlatIP

Implements the Kivo RAG Pipeline Architecture:
  - Parent chunks (~1000 chars, 200 char overlap) → stored in parents.json for LLM context
  - Child chunks (~400 chars, 100 char overlap)   → indexed in FAISS for precision search
  - Index type: IndexFlatIP with L2 normalization (= Cosine Similarity, faster than L2)
  - When a child matches, parent is fetched for full context

Pipeline: segment text → split into parents → split parents into children
         → embed children → L2 normalize → IndexFlatIP → save index + chunk map
"""
import os
import json
import re
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass, field
from typing import Optional

# Lazy-loaded model to keep startup times fast
_model = None

# ── Chunking constants (PPT recommended values) ─────────────────────────────
PARENT_CHUNK_SIZE   = 1000   # ~300-500 words — context window for LLM
PARENT_OVERLAP      = 200    # 200 char overlap between parents
CHILD_CHUNK_SIZE    = 400    # ~120 words — precision for FAISS search
CHILD_OVERLAP       = 100    # 100 char overlap between children


@dataclass
class ChunkResult:
    """Holds both child chunks (for FAISS) and parent chunks (for LLM context)."""
    children: list = field(default_factory=list)  # embedded + indexed
    parents:  list = field(default_factory=list)  # stored for context retrieval

    # Allow iteration so existing code that does `for c in chunks` still works
    def __iter__(self):
        return iter(self.children)

    def __len__(self):
        return len(self.children)

    def __getitem__(self, idx):
        return self.children[idx]


def get_embedding_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _split_boundary_aware(text: str, size: int, overlap: int) -> list[str]:
    """
    Boundary-aware text splitter (PPT section 3 — Chunking Logic).
    Splits on paragraphs (\\n\\n), then sentences ([.!?]), then words.
    Respects size limit and adds overlap from the previous chunk.
    """
    if not text or len(text) <= size:
        return [text] if text.strip() else []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + size, len(text))

        if end < len(text):
            # Try to split on paragraph boundary first
            para_cut = text.rfind("\n\n", start, end)
            if para_cut > start + size // 3:
                end = para_cut
            else:
                # Try sentence boundary
                sent_match = None
                for m in re.finditer(r'[.!?]\s+', text[start:end]):
                    sent_match = m
                if sent_match and sent_match.end() > size // 4:
                    end = start + sent_match.end()
                else:
                    # Fall back to word boundary
                    word_cut = text.rfind(" ", start, end)
                    if word_cut > start + size // 3:
                        end = word_cut

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move forward with overlap
        start = max(end - overlap, start + 1)

    return chunks


def chunk_transcript(segments: list, topics: list) -> ChunkResult:
    """
    Produces a ChunkResult with:
    - .children: child chunks (embedded + indexed in FAISS for precision search)
    - .parents:  parent chunks (stored in parents.json for LLM context retrieval)

    Each child carries: chunk_id, parent_id, topic_id, text.
    Each parent carries: parent_id, topic_id, text.
    """
    result = ChunkResult()
    parent_counter = 0
    child_counter = 0

    for topic_idx, topic in enumerate(topics):
        topic_id = f"topic_{topic_idx}"
        start_seg = topic.get("start_segment", 0)
        end_seg = topic.get("end_segment", 0)

        topic_segments = segments[start_seg:end_seg + 1]
        topic_text = " ".join([s.get("text", "") for s in topic_segments])

        if not topic_text.strip():
            continue

        # ── Split into PARENT chunks (large context windows) ──────────────────
        parent_texts = _split_boundary_aware(topic_text, PARENT_CHUNK_SIZE, PARENT_OVERLAP)

        for p_text in parent_texts:
            if not p_text.strip():
                continue

            parent_id = f"parent_{parent_counter}"
            result.parents.append({
                "parent_id": parent_id,
                "topic_id": topic_id,
                "text": p_text,
            })

            # ── Split each parent into CHILD chunks (search precision) ─────────
            child_texts = _split_boundary_aware(p_text, CHILD_CHUNK_SIZE, CHILD_OVERLAP)

            for c_text in child_texts:
                if not c_text.strip():
                    continue
                if len(c_text.split()) < 5:  # skip trivially short children
                    continue

                result.children.append({
                    "chunk_id": f"chunk_{child_counter}",
                    "parent_id": parent_id,
                    "topic_id": topic_id,
                    "text": c_text,
                })
                child_counter += 1

            parent_counter += 1

    return result


def build_and_persist_index(chunks: ChunkResult, output_dir: str):
    """
    Embeds child chunks, L2-normalizes them, builds FAISS IndexFlatIP
    (= cosine similarity, faster than L2 distance for text).
    Saves: faiss.index, chunks.json (children), parents.json (parent texts).
    """
    if not chunks or len(chunks) == 0:
        return

    os.makedirs(output_dir, exist_ok=True)

    # Save parents (from ChunkResult.parents or legacy fallback)
    parents = chunks.parents if isinstance(chunks, ChunkResult) else []
    if parents:
        with open(os.path.join(output_dir, "parents.json"), "w", encoding="utf-8") as f:
            json.dump(parents, f, indent=2, ensure_ascii=False)
        print(f"[VectorDB] Saved {len(parents)} parent chunks -> parents.json")

    model = get_embedding_model()
    texts = [c["text"] for c in chunks]

    # Generate embeddings
    embeddings = model.encode(texts, show_progress_bar=False)
    embeddings = np.array(embeddings).astype("float32")

    # ── PPT: L2 Normalize + IndexFlatIP (= Cosine Similarity, runs faster) ───
    # Pre-normalize so ||v|| = 1 → Inner Product == Cosine Similarity
    faiss.normalize_L2(embeddings)  # in-place normalization

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)   # Inner Product index
    index.add(embeddings)

    # Save FAISS index
    faiss.write_index(index, os.path.join(output_dir, "faiss.index"))

    # Save child chunks map
    with open(os.path.join(output_dir, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump(list(chunks), f, indent=2, ensure_ascii=False)

    print(f"[VectorDB] Built IndexFlatIP with {len(chunks)} child chunks "
          f"({dimension}D, L2-normalized) -> faiss.index")


def get_parent_text(video_dir: str, parent_id: str) -> str:
    """Fetch the parent chunk text by parent_id from parents.json."""
    parents_path = os.path.join(video_dir, "parents.json")
    if not os.path.exists(parents_path):
        return ""
    with open(parents_path, encoding="utf-8") as f:
        parents = json.load(f)
    for p in parents:
        if p.get("parent_id") == parent_id:
            return p.get("text", "")
    return ""


def search_index(video_dir: str, query: str, top_k: int = 5,
                 topic_id: str | None = None) -> list[dict]:
    """
    Search the FAISS index using the PPT retrieval pattern:
    1. Embed + L2-normalize the query
    2. IndexFlatIP search for top child chunks
    3. For each child, fetch its parent chunk (broader context)
    4. Deduplicate by parent_id so the LLM gets unique parent chunks

    Returns list of dicts: {child_text, parent_text, topic_id, score}
    """
    faiss_path = os.path.join(video_dir, "faiss.index")
    chunks_path = os.path.join(video_dir, "chunks.json")

    if not os.path.exists(faiss_path) or not os.path.exists(chunks_path):
        return []

    index = faiss.read_index(faiss_path)
    with open(chunks_path, encoding="utf-8") as f:
        chunks = json.load(f)

    model = get_embedding_model()
    q_emb = model.encode([query], show_progress_bar=False).astype("float32")
    faiss.normalize_L2(q_emb)  # normalize query too

    # Search more candidates then deduplicate by parent
    search_k = min(top_k * 3, len(chunks))
    distances, indices = index.search(q_emb, search_k)

    results = []
    seen_parents = set()

    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0 or idx >= len(chunks):
            continue

        chunk = chunks[idx]

        # Filter by topic if specified
        if topic_id and chunk.get("topic_id") != topic_id:
            continue

        parent_id = chunk.get("parent_id", "")

        # Deduplicate: skip if we already have this parent (PPT pattern)
        if parent_id in seen_parents:
            continue
        seen_parents.add(parent_id)

        # Fetch parent for full LLM context
        parent_text = get_parent_text(video_dir, parent_id)

        results.append({
            "child_text": chunk["text"],
            "parent_text": parent_text or chunk["text"],
            "topic_id": chunk.get("topic_id", ""),
            "parent_id": parent_id,
            "score": float(dist),
        })

        if len(results) >= top_k:
            break

    return results
