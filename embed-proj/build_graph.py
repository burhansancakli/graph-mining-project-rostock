#!/usr/bin/env python3
"""Build a k-NN similarity graph from story embeddings.

Each story is a node. Edges connect each story to its k most similar neighbors
(by cosine similarity). Weak edges below a similarity threshold are removed.

Usage:
    python build_graph.py
    python build_graph.py --k 10 --min-similarity 0.3

Output:
    output/semantic_graph.gml       — NetworkX graph (readable by Gephi etc.)
    output/graph_stats.json         — node/edge counts, degree stats
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import networkx as nx
from sklearn.neighbors import NearestNeighbors

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def load_embeddings() -> tuple[np.ndarray, list[str], list[str]]:
    emb_path = OUTPUT_DIR / "story_embeddings.npy"
    ids_path = OUTPUT_DIR / "story_ids.json"
    regions_path = OUTPUT_DIR / "story_regions.json"

    for p in [emb_path, ids_path, regions_path]:
        if not p.exists():
            print(f"ERROR: {p} not found. Run embed_stories.py first.")
            raise SystemExit(1)

    embeddings = np.load(emb_path)
    ids = json.loads(ids_path.read_text(encoding="utf-8"))
    regions = json.loads(regions_path.read_text(encoding="utf-8"))
    return embeddings, ids, regions


def build_knn_graph(
    embeddings: np.ndarray,
    ids: list[str],
    regions: list[str],
    k: int,
    min_similarity: float,
) -> nx.Graph:
    """Build k-NN graph with cosine similarity edges."""
    n = len(ids)
    print(f"Building {k}-NN graph for {n} stories...")

    # ── Find k nearest neighbors for each story ────────────────────────────
    t0 = time.time()
    nn = NearestNeighbors(n_neighbors=k + 1, metric="cosine", algorithm="brute")
    nn.fit(embeddings)
    distances, indices = nn.kneighbors(embeddings)
    print(f"  k-NN search done in {time.time() - t0:.1f}s")

    # ── Build graph ────────────────────────────────────────────────────────
    G = nx.Graph()

    # Add all nodes first
    for i, story_id in enumerate(ids):
        G.add_node(story_id, region=regions[i], index=i)

    # Add edges (skip self-match at index 0 of neighbors)
    edge_count = 0
    skipped_weak = 0

    for i in range(n):
        for j_idx in range(1, k + 1):  # skip self (index 0)
            j = indices[i][j_idx]
            cosine_sim = 1.0 - distances[i][j_idx]  # sklearn returns distance = 1 - cosine

            if cosine_sim < min_similarity:
                skipped_weak += 1
                continue

            # Avoid duplicate edges
            u, v = ids[i], ids[j]
            if G.has_edge(u, v):
                # Update weight to max of existing and new
                if cosine_sim > G[u][v]["weight"]:
                    G[u][v]["weight"] = cosine_sim
                continue

            G.add_edge(u, v, weight=round(cosine_sim, 4))
            edge_count += 1

    print(f"  Edges added: {edge_count} (skipped {skipped_weak} below threshold {min_similarity})")
    return G


def print_graph_stats(G: nx.Graph) -> dict:
    """Compute and print graph statistics."""
    degrees = [d for _, d in G.degree()]
    weights = [d["weight"] for _, _, d in G.edges(data=True)]

    stats = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "density": round(nx.density(G), 6),
        "avg_degree": round(np.mean(degrees), 2),
        "max_degree": max(degrees),
        "min_degree": min(degrees),
        "avg_weight": round(np.mean(weights), 4) if weights else 0,
        "min_weight": round(min(weights), 4) if weights else 0,
        "max_weight": round(max(weights), 4) if weights else 0,
        "n_components": nx.number_connected_components(G),
    }

    print(f"\n── Graph Statistics ──")
    for k, v in stats.items():
        print(f"  {k:<15} {v}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Build semantic similarity graph")
    parser.add_argument("--k", type=int, default=10,
                        help="Number of nearest neighbors per story (default: 10)")
    parser.add_argument("--min-similarity", type=float, default=0.3,
                        help="Minimum cosine similarity to keep an edge (default: 0.3)")
    args = parser.parse_args()

    embeddings, ids, regions = load_embeddings()
    print(f"Loaded embeddings: {embeddings.shape}, {len(ids)} stories, {len(set(regions))} regions")

    G = build_knn_graph(embeddings, ids, regions, args.k, args.min_similarity)

    if G.number_of_nodes() == 0:
        print("ERROR: Graph is empty! Try lowering --min-similarity")
        raise SystemExit(1)

    stats = print_graph_stats(G)

    # If disconnected, keep largest component for clean analysis
    if stats["n_components"] > 1:
        largest_cc = max(nx.connected_components(G), key=len)
        print(f"\n  Largest component: {len(largest_cc)}/{stats['nodes']} nodes")
        G = G.subgraph(largest_cc).copy()
        print(f"  Using largest connected component for analysis")

    # ── Save ────────────────────────────────────────────────────────────────
    nx.write_gml(G, OUTPUT_DIR / "semantic_graph.gml")
    (OUTPUT_DIR / "graph_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8"
    )

    print(f"\nSaved:")
    print(f"  {OUTPUT_DIR / 'semantic_graph.gml'}")
    print(f"  {OUTPUT_DIR / 'graph_stats.json'}")


if __name__ == "__main__":
    main()