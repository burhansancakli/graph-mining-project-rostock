#!/usr/bin/env python3
"""Run Louvain community detection on the semantic similarity graph.

Usage:
    python run_louvain.py
    python run_louvain.py --resolution 1.0

Output:
    output/louvain_partition.json   — {story_id: community_id, ...}
    output/louvain_summary.json     — modularity, #communities, per-community stats
    output/louvain_communities.csv  — story_id, community, region for easy analysis
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import community as community_louvain
import networkx as nx

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def load_graph() -> nx.Graph:
    path = OUTPUT_DIR / "semantic_graph.gml"
    if not path.exists():
        print(f"ERROR: {path} not found. Run build_graph.py first.")
        raise SystemExit(1)
    G = nx.read_gml(path)
    print(f"Loaded graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


def load_regions() -> dict[str, str]:
    path = OUTPUT_DIR / "story_regions.json"
    ids = json.loads((OUTPUT_DIR / "story_ids.json").read_text(encoding="utf-8"))
    regions = json.loads(path.read_text(encoding="utf-8"))
    return dict(zip(ids, regions))


def main():
    parser = argparse.ArgumentParser(description="Run Louvain on semantic graph")
    parser.add_argument("--resolution", type=float, default=1.0,
                        help="Louvain resolution parameter (default: 1.0, >1 = more communities)")
    args = parser.parse_args()

    G = load_graph()
    id_to_region = load_regions()

    # ── Run Louvain ────────────────────────────────────────────────────────
    print(f"\nRunning Louvain (resolution={args.resolution})...")
    partition = community_louvain.best_partition(G, weight="weight", resolution=args.resolution, random_state=42)
    modularity = community_louvain.modularity(partition, G, weight="weight")
    n_communities = len(set(partition.values()))

    print(f"  Communities: {n_communities}")
    print(f"  Modularity Q: {modularity:.4f}")

    # ── Per-community analysis ─────────────────────────────────────────────
    comm_members: dict[int, list[str]] = defaultdict(list)
    for node, comm in partition.items():
        comm_members[comm].append(node)

    comm_stats = []
    for comm_id in sorted(comm_members, key=lambda c: -len(comm_members[c])):
        members = comm_members[comm_id]
        region_dist = Counter(id_to_region.get(n, "unknown") for n in members)
        top_region = region_dist.most_common(1)[0]

        comm_stats.append({
            "community": comm_id,
            "size": len(members),
            "regions": dict(region_dist),
            "top_region": top_region[0],
            "top_region_frac": round(top_region[1] / len(members), 3),
        })

    # ── Print summary ──────────────────────────────────────────────────────
    print(f"\n{'Comm':>5} {'Size':>6} {'Dominant region':<15} {'Frac':>6}")
    print("-" * 40)
    for s in comm_stats[:20]:
        print(f"{s['community']:>5} {s['size']:>6} {s['top_region']:<15} {s['top_region_frac']:>6.3f}")
    if len(comm_stats) > 20:
        print(f"  ... and {len(comm_stats) - 20} more communities")

    # ── Save ────────────────────────────────────────────────────────────────
    # Partition dict (JSON-serializable)
    partition_json = {str(k): v for k, v in partition.items()}
    (OUTPUT_DIR / "louvain_partition.json").write_text(
        json.dumps(partition_json, indent=2), encoding="utf-8"
    )

    # Summary
    summary = {
        "resolution": args.resolution,
        "modularity": modularity,
        "n_communities": n_communities,
        "n_nodes": G.number_of_nodes(),
        "n_edges": G.number_of_edges(),
        "communities": comm_stats,
    }
    (OUTPUT_DIR / "louvain_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # CSV for easy downstream analysis
    csv_path = OUTPUT_DIR / "louvain_communities.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["story_id", "community", "region"])
        for node, comm in sorted(partition.items()):
            writer.writerow([node, comm, id_to_region.get(node, "unknown")])

    print(f"\nSaved:")
    print(f"  {OUTPUT_DIR / 'louvain_partition.json'}")
    print(f"  {OUTPUT_DIR / 'louvain_summary.json'}")
    print(f"  {OUTPUT_DIR / 'louvain_communities.csv'}")


if __name__ == "__main__":
    main()
