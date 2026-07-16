#!/usr/bin/env python3
"""
Run Girvan-Newman community detection on each region individually
and on the merged dataset.

For each region produces:
  - girvan_newman_<region>.png   (graph visualization)
  - girvan_newman_<region>.json  (community data)
"""

import json
import sys
from pathlib import Path

import networkx as nx
from networkx.algorithms.community import girvan_newman, modularity
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from collections import defaultdict
import itertools

import graph_utils

REGIONS = ["denmark", "iceland", "mecklenburg"]
OUTPUT_DIR = Path(__file__).resolve().parent / "gn_output"

# Per-region co-occurrence thresholds (these are the load_graph min_cooccurrence values)
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

# GN is slow — keep these reasonable
MIN_WEIGHT_GN = 5
MAX_NODES_GN = 300


def run_gn_for_region(dataset_name: str) -> dict:
    """Temporarily patch graph_utils to load a specific dataset, then run GN."""
    graph_utils.DATASET = dataset_name
    graph_utils.NODES_FILE = graph_utils.BASE_DIR / f"isebel-{dataset_name}-nodes.csv"
    graph_utils.EDGES_FILE = graph_utils.BASE_DIR / f"isebel-{dataset_name}-edges.csv"

    min_cooc = REGION_MIN_COOCCURRENCE.get(dataset_name, 10)
    min_comp = REGION_MIN_COMPONENT_SIZE.get(dataset_name, 50)
    G_full, keyword_text = graph_utils.load_graph(
        min_cooccurrence=min_cooc,
        min_component_size=min_comp,
    )

    # ── Build filtered subgraph for GN ───────────────────────────────────────
    G = nx.Graph()
    for u, v, data in G_full.edges(data=True):
        if data.get("weight", 1) >= MIN_WEIGHT_GN:
            G.add_edge(u, v, weight=data["weight"])

    if G.number_of_nodes() > MAX_NODES_GN:
        degree = dict(G.degree(weight="weight"))
        top_nodes = sorted(degree, key=lambda n: -degree[n])[:MAX_NODES_GN]
        G = G.subgraph(top_nodes).copy()

    if G.number_of_nodes() == 0:
        print(f"  ⚠ No nodes left after filtering for {dataset_name}, skipping.")
        return {}

    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()

    print(f"\n── Girvan-Newman [{dataset_name}] ──")
    print(f"  Subgraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  (filtered: weight >= {MIN_WEIGHT_GN}, max {MAX_NODES_GN} nodes)")
    print("  Running GN — this may take a minute...")

    # ── Run GN and pick the split with best modularity ────────────────────────
    gn_generator = girvan_newman(G)
    best_modularity = -1
    best_communities = None
    best_n = 0

    for communities in itertools.islice(gn_generator, 30):
        comm_list = list(communities)
        try:
            q = modularity(G, comm_list, weight="weight")
        except Exception:
            continue
        if q > best_modularity:
            best_modularity = q
            best_communities = comm_list
            best_n = len(comm_list)

    print(f"  Best communities: {best_n}")
    print(f"  Best Modularity Q: {best_modularity:.4f}")

    # ── Build partition dict ──────────────────────────────────────────────────
    partition = {}
    for comm_id, members in enumerate(best_communities):
        for node in members:
            partition[node] = comm_id

    # ── Top keywords per community ────────────────────────────────────────────
    degree = dict(G.degree(weight="weight"))
    comm_members = defaultdict(list)
    for node, comm in partition.items():
        comm_members[comm].append(node)

    results = []
    for comm, members in sorted(comm_members.items(), key=lambda x: -len(x[1])):
        top_nodes = sorted(members, key=lambda n: -degree.get(n, 0))[:8]
        top_keywords = [keyword_text.get(n, n) for n in top_nodes]
        results.append({
            "community": comm,
            "size": len(members),
            "top_keywords": top_keywords,
        })
        print(f"  Community {comm:2d} (size={len(members):3d}): {', '.join(top_keywords)}")

    # ── Werewolf cluster ──────────────────────────────────────────────────────
    werewolf_terms = {"werwolf", "werewolf", "werwölfe", "verwandlung"}
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
        print("\n  ★ Werewolf not found in subgraph.")

    # ── Visualization ─────────────────────────────────────────────────────────
    plt.figure(figsize=(12, 9))
    pos = nx.spring_layout(G, k=0.5, seed=42)
    colors = plt.cm.Set3([i / max(best_n, 1) for i in [partition.get(n, 0) for n in G.nodes()]])
    node_sizes = [40 + degree.get(n, 0) * 5 for n in G.nodes()]

    nx.draw_networkx_edges(G, pos, alpha=0.2, width=0.6)
    nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=node_sizes,
                           edgecolors="black", linewidths=0.3)

    label_nodes = set()
    for members in comm_members.values():
        label_nodes.update(sorted(members, key=lambda n: -degree.get(n, 0))[:2])
    nx.draw_networkx_labels(G, pos,
                            labels={n: keyword_text.get(n, n) for n in label_nodes},
                            font_size=7)

    plt.title(f"Girvan-Newman — {dataset_name} (weight≥{MIN_WEIGHT_GN})\n"
              f"{best_n} communities | Q={best_modularity:.3f}", fontsize=12)
    plt.axis("off")
    plt.tight_layout()
    png_out = OUTPUT_DIR / f"girvan_newman_{dataset_name}.png"
    plt.savefig(png_out, dpi=150)
    plt.close()
    print(f"\n  Saved: {png_out}")

    # ── Save JSON ─────────────────────────────────────────────────────────────
    json_out = OUTPUT_DIR / f"girvan_newman_{dataset_name}.json"
    output_data = {
        "algorithm": "Girvan-Newman",
        "dataset": dataset_name,
        "modularity": best_modularity,
        "n_communities": best_n,
        "min_weight": MIN_WEIGHT_GN,
        "max_nodes": MAX_NODES_GN,
        "graph_nodes": G.number_of_nodes(),
        "graph_edges": G.number_of_edges(),
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

    # Determine which regions to run (default: all)
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
            result = run_gn_for_region(region)
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

    summary_out = OUTPUT_DIR / "girvan_newman_summary.json"
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
