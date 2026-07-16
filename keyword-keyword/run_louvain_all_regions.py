#!/usr/bin/env python3
"""
Run Louvain community detection on each region individually.

For each region produces:
  - louvain_<region>.png   (graph visualization)
  - louvain_<region>.json  (community data)
"""

import json
import math
import sys
from pathlib import Path

import networkx as nx
import community as community_louvain
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colormaps
from collections import defaultdict

import graph_utils

REGIONS = ["denmark", "iceland", "mecklenburg", "netherlands", "merged"]
OUTPUT_DIR = Path(__file__).resolve().parent / "louvain_output"

# Per-region co-occurrence thresholds
REGION_MIN_COOCCURRENCE = {
    "denmark": 10,
    "iceland": 30,
    "mecklenburg": 3,
    "netherlands": 10,
    "merged": 10,
}
REGION_MIN_COMPONENT_SIZE = {
    "denmark": 100,
    "iceland": 100,
    "mecklenburg": 30,
    "netherlands": 100,
    "merged": 100,
}


def run_louvain_for_region(dataset_name: str) -> dict:
    """Temporarily patch graph_utils to load a specific dataset, then run Louvain."""
    graph_utils.DATASET = dataset_name
    graph_utils.NODES_FILE = graph_utils.BASE_DIR / f"isebel-{dataset_name}-nodes.csv"
    graph_utils.EDGES_FILE = graph_utils.BASE_DIR / f"isebel-{dataset_name}-edges.csv"

    min_cooc = REGION_MIN_COOCCURRENCE.get(dataset_name, 10)
    min_comp = REGION_MIN_COMPONENT_SIZE.get(dataset_name, 50)
    G, keyword_text = graph_utils.load_graph(
        min_cooccurrence=min_cooc,
        min_component_size=min_comp,
    )

    if G.number_of_nodes() == 0:
        print(f"  ⚠ No nodes left for {dataset_name}, skipping.")
        return {}

    print(f"\n── Louvain [{dataset_name}] ──")
    print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # ── Run Louvain ───────────────────────────────────────────────────────────
    partition = community_louvain.best_partition(G, weight="weight", random_state=42)
    modularity = community_louvain.modularity(partition, G, weight="weight")
    n_communities = len(set(partition.values()))

    print(f"  Communities : {n_communities}")
    print(f"  Modularity Q: {modularity:.4f}")

    # ── Compute cluster quality metrics ──────────────────────────────────────
    degree = dict(G.degree(weight="weight"))
    total_weight = sum(d for _, _, d in G.edges(data="weight"))
    graph_density = nx.density(G)

    comm_members = defaultdict(list)
    for node, comm in partition.items():
        comm_members[comm].append(node)

    # Per-community metrics
    community_metrics = []
    all_conductances = []
    all_internal_densities = []
    inter_community_weight = 0.0

    for comm, members in comm_members.items():
        member_set = set(members)
        n = len(members)

        # Internal edges (both endpoints in community)
        internal_weight = 0.0
        for u in member_set:
            for v in G.neighbors(u):
                if v in member_set and u < v:
                    internal_weight += G[u][v].get("weight", 1)

        # Cut: edges leaving the community
        cut_weight = 0.0
        for u in member_set:
            for v in G.neighbors(u):
                if v not in member_set:
                    cut_weight += G[u][v].get("weight", 1)

        # Volume: sum of degrees (weighted) of nodes in community
        volume = sum(degree.get(n, 0) for n in member_set)

        # Conductance = cut / min(volume, 2*total - volume)
        # Lower = better separated
        denom = min(volume, 2 * total_weight - volume)
        conductance = cut_weight / denom if denom > 0 else 0.0

        # Internal density = actual internal edges / possible internal edges
        max_possible = n * (n - 1) / 2
        internal_density = internal_weight / max_possible if max_possible > 0 else 0.0

        inter_community_weight += cut_weight
        all_conductances.append(conductance)
        all_internal_densities.append(internal_density)

        community_metrics.append({
            "community": comm,
            "size": n,
            "internal_weight": internal_weight,
            "cut_weight": cut_weight,
            "volume": volume,
            "conductance": round(conductance, 4),
            "internal_density": round(internal_density, 4),
        })

    # Inter-community weight is counted twice (once per side), so halve it
    inter_community_weight /= 2
    intra_community_weight = total_weight - inter_community_weight
    cut_ratio = inter_community_weight / total_weight if total_weight > 0 else 0.0

    # Community size distribution
    sizes = [len(m) for m in comm_members.values()]
    size_entropy = -sum((s / sum(sizes)) * math.log2(s / sum(sizes)) for s in sizes if s > 0)
    max_size_ratio = max(sizes) / min(sizes) if sizes else 0
    avg_conductance = sum(all_conductances) / len(all_conductances) if all_conductances else 0
    avg_internal_density = sum(all_internal_densities) / len(all_internal_densities) if all_internal_densities else 0

    quality = {
        "modularity": modularity,
        "graph_density": round(graph_density, 6),
        "total_weight": total_weight,
        "intra_community_weight": round(intra_community_weight, 2),
        "inter_community_weight": round(inter_community_weight, 2),
        "cut_ratio": round(cut_ratio, 4),
        "avg_conductance": round(avg_conductance, 4),
        "avg_internal_density": round(avg_internal_density, 4),
        "size_entropy": round(size_entropy, 4),
        "max_size_ratio": round(max_size_ratio, 2),
        "communities": community_metrics,
    }

    print(f"  Cut ratio: {cut_ratio:.4f} (fraction of edges between communities)")
    print(f"  Avg conductance: {avg_conductance:.4f} (lower = better separated)")
    print(f"  Avg internal density: {avg_internal_density:.4f}")
    print(f"  Size entropy: {size_entropy:.4f} (higher = more balanced sizes)")

    # ── Top keywords per community ────────────────────────────────────────────
    results = []
    for comm, members in sorted(comm_members.items(), key=lambda x: -len(x[1])):
        top_nodes = sorted(members, key=lambda n: -degree.get(n, 0))[:8]
        top_keywords = [keyword_text.get(n, n) for n in top_nodes]
        results.append({
            "community": comm,
            "size": len(members),
            "top_keywords": top_keywords,
        })
        print(f"  Community {comm:2d} (size={len(members):4d}): {', '.join(top_keywords)}")

    # ── Werewolf cluster ──────────────────────────────────────────────────────
    werewolf_terms = {"werwolf", "werewolf", "werwölfe", "verwandlung", "varulv"}
    werewolf_community = None
    werewolf_members = []

    for node, comm in partition.items():
        kw = keyword_text.get(node, "").lower()
        if any(term in kw for term in werewolf_terms):
            werewolf_community = comm
            break

    if werewolf_community is not None:
        werewolf_members = comm_members[werewolf_community]
        ww_top = sorted(werewolf_members, key=lambda n: -degree.get(n, 0))[:12]
        print(f"\n  ★ Werewolf belongs to Community {werewolf_community}:")
        print(f"    {', '.join(keyword_text.get(n, n) for n in ww_top)}")
    else:
        print("\n  ★ No Werewolf keyword found in this dataset.")

    # ── Visualization ─────────────────────────────────────────────────────────
    plt.figure(figsize=(14, 10))
    pos = nx.spring_layout(G, k=0.4, seed=42, weight="weight")
    cmap = colormaps.get_cmap("tab20")
    node_colors = [cmap(partition[n] % 20) for n in G.nodes()]
    node_sizes = [30 + degree.get(n, 0) * 1 for n in G.nodes()]

    nx.draw_networkx_edges(G, pos, alpha=0.15, width=0.5)
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes,
                           edgecolors="black", linewidths=0.3)

    label_nodes = set()
    for members in comm_members.values():
        label_nodes.update(sorted(members, key=lambda n: -degree.get(n, 0))[:3])
    nx.draw_networkx_labels(G, pos,
                            labels={n: keyword_text.get(n, n) for n in label_nodes},
                            font_size=7)

    plt.title(f"Louvain — {dataset_name} | {n_communities} communities | Q={modularity:.3f}", fontsize=13)
    plt.axis("off")
    plt.tight_layout()
    png_out = OUTPUT_DIR / f"louvain_{dataset_name}.png"
    plt.savefig(png_out, dpi=150)
    plt.close()
    print(f"\n  Saved: {png_out}")

    # ── Save JSON ─────────────────────────────────────────────────────────────
    json_out = OUTPUT_DIR / f"louvain_{dataset_name}.json"
    output_data = {
        "algorithm": "Louvain",
        "dataset": dataset_name,
        "modularity": modularity,
        "n_communities": n_communities,
        "min_cooccurrence": min_cooc,
        "min_component_size": min_comp,
        "graph_nodes": G.number_of_nodes(),
        "graph_edges": G.number_of_edges(),
        "quality": quality,
        "communities": results,
        "werewolf_community": werewolf_community,
        "werewolf_members": [
            {"node_id": n, "keyword": keyword_text.get(n, n), "degree": degree.get(n, 0)}
            for n in sorted(werewolf_members, key=lambda n: -degree.get(n, 0))
        ],
    }

    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {json_out}")

    return output_data


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    if len(sys.argv) > 1:
        regions = sys.argv[1:]
    else:
        regions = REGIONS

    all_results = {}

    for region in regions:
        print(f"\n{'='*60}")
        print(f"  Processing: {region}")
        print(f"{'='*60}")
        try:
            result = run_louvain_for_region(region)
            if result:
                all_results[region] = result
        except FileNotFoundError as e:
            print(f"  ✗ Skipping {region}: {e}")
        except Exception as e:
            print(f"  ✗ Error processing {region}: {e}")
            import traceback
            traceback.print_exc()

    # ── Save combined summary ─────────────────────────────────────────────────
    summary = {}
    for region, data in all_results.items():
        summary[region] = {
            "modularity": data["modularity"],
            "n_communities": data["n_communities"],
            "graph_nodes": data["graph_nodes"],
            "graph_edges": data["graph_edges"],
            "werewolf_community": data["werewolf_community"],
        }

    summary_out = OUTPUT_DIR / "louvain_summary.json"
    with open(summary_out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  Summary saved: {summary_out}")
    print(f"{'='*60}")
    for region, s in summary.items():
        print(f"  {region:15s}  Q={s['modularity']:.4f}  "
              f"communities={s['n_communities']:3d}  "
              f"nodes={s['graph_nodes']:4d}  "
              f"edges={s['graph_edges']:5d}  "
              f"werewolf_comm={s['werewolf_community']}")


if __name__ == "__main__":
    main()
