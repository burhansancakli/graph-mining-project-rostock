#!/usr/bin/env python3
"""Embed all filtered story texts using a multilingual sentence-transformer.

Usage:
    python embed_stories.py
    python embed_stories.py --model paraphrase-multilingual-MiniLM-L12-v2

Output:
    output/story_embeddings.npy   — (n_stories, dim) float32 array
    output/story_ids.json         — list of story IDs in same order as embeddings
    output/story_regions.json     — list of region labels in same order
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def load_filtered_stories() -> list[dict]:
    path = OUTPUT_DIR / "filtered_stories.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run load_stories.py first.")
        raise SystemExit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Embed stories with multilingual model")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"HuggingFace model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="Batch size for encoding (default: 64)")
    args = parser.parse_args()

    stories = load_filtered_stories()
    print(f"Loaded {len(stories)} stories from filtered_stories.json")

    # ── Load model ──────────────────────────────────────────────────────────
    print(f"\nLoading model: {args.model}")
    t0 = time.time()

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    print(f"  Model loaded in {time.time() - t0:.1f}s (dim={model.get_sentence_embedding_dimension()})")

    # ── Encode ──────────────────────────────────────────────────────────────
    texts = [s["text"] for s in stories]
    print(f"\nEmbedding {len(texts)} stories (batch_size={args.batch_size})...")
    t0 = time.time()

    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,  # unit vectors → cosine = dot product
    )

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s ({len(texts) / elapsed:.0f} stories/sec)")

    # ── Save ────────────────────────────────────────────────────────────────
    ids = [s["id"] for s in stories]
    regions = [s["region"] for s in stories]

    np.save(OUTPUT_DIR / "story_embeddings.npy", embeddings.astype(np.float32))
    (OUTPUT_DIR / "story_ids.json").write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")
    (OUTPUT_DIR / "story_regions.json").write_text(json.dumps(regions, ensure_ascii=False), encoding="utf-8")

    print(f"\nSaved:")
    print(f"  {OUTPUT_DIR / 'story_embeddings.npy'}  shape={embeddings.shape}")
    print(f"  {OUTPUT_DIR / 'story_ids.json'}  ({len(ids)} ids)")
    print(f"  {OUTPUT_DIR / 'story_regions.json'}  ({len(regions)} labels)")

    # Quick sanity check: print 5 random pairs and their cosine similarity
    print("\n── Sample similarities (random pairs) ──")
    rng = np.random.default_rng(42)
    for _ in range(5):
        i, j = rng.integers(0, len(texts), size=2)
        sim = np.dot(embeddings[i], embeddings[j])
        r_i, r_j = regions[i], regions[j]
        print(f"  [{r_i}] {texts[i][:50]}...")
        print(f"  [{r_j}] {texts[j][:50]}...")
        print(f"  cosine = {sim:.4f}\n")


if __name__ == "__main__":
    main()
