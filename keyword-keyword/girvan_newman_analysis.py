"""
Community detection using the Girvan-Newman algorithm.

What it does:
  - Uses the same keyword co-occurrence graph as Louvain
  - IMPORTANT: GN is very slow (O(m²n)), so we filter to a subgraph
    using only edges with weight >= MIN_WEIGHT_GN to keep it feasible
  - Stops GN iterations when modularity Q is maximized
  - Compares community structure with Louvain result
"""

import networkx as nx
from networkx.algorithms.community import girvan_newman, modularity
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from collections import defaultdict
import itertools

from graph_utils import load_graph, DATASET

# GN is slow — filter to stronger edges only to keep runtime reasonable
MIN_WEIGHT_GN = 5   # increase if the dataset is large (denmark/netherlands)
MAX_NODES_GN = 300  # hard cap: take subgraph of top-degree nodes


def run_girvan_newman():
    G_full, keyword_text = load_graph()

    # ── Build filtered subgraph for GN ───────────────────────────────────────
    G = nx.Graph()
    for u, v, data in G_full.edges(data=True):
        if data.get("weight", 1) >= MIN_WEIGHT_GN:
            G.add_edge(u, v, weight=data["weight"])

    # If still too large, keep top-degree nodes only
    if G.number_of_nodes() > MAX_NODES_GN:
        degree = dict(G.degree(weight="weight"))
        top_nodes = sorted(degree, key=lambda n: -degree[n])[:MAX_NODES_GN]
        G = G.subgraph(top_nodes).copy()

    # Keep largest connected component
    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()

    print(f"\n── Girvan-Newman [{DATASET}] ──")
    print(f"  Subgraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  (filtered: weight >= {MIN_WEIGHT_GN}, max {MAX_NODES_GN} nodes)")
    print("  Running GN — this may take a minute...")

    # ── Run GN and pick the split with best modularity ────────────────────────
    gn_generator = girvan_newman(G)
    best_modularity = -1
    best_communities = None
    best_n = 0

    # Explore up to 30 splits to find modularity peak
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

    # ── Build partition dict (same format as Louvain for easy comparison) ─────
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
        results.append({"community": comm, "size": len(members), "top_keywords": top_keywords})
        print(f"  Community {comm:2d} (size={len(members):3d}): {', '.join(top_keywords)}")

    # ── Werewolf cluster ──────────────────────────────────────────────────────
    werewolf_terms = {"werwolf", "werewolf", "werwölfe", "verwandlung"}
    werewolf_community = None

    for node, comm in partition.items():
        kw = keyword_text.get(node, "").lower()
        if any(term in kw for term in werewolf_terms):
            werewolf_community = comm
            break

    if werewolf_community is not None:
        ww_members = comm_members[werewolf_community]
        ww_top = sorted(ww_members, key=lambda n: -degree.get(n, 0))[:12]
        print(f"\n  ★ Werewolf belongs to Community {werewolf_community}:")
        print(f"    {', '.join(keyword_text.get(n, n) for n in ww_top)}")
    else:
        print("\n  ★ Werewolf not found in subgraph (filtered out by weight threshold).")

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

    plt.title(f"Girvan-Newman — {DATASET} (weight≥{MIN_WEIGHT_GN})\n"
              f"{best_n} communities | Q={best_modularity:.3f}", fontsize=12)
    plt.axis("off")
    plt.tight_layout()
    out = f"girvan_newman_{DATASET}.png"
    plt.savefig(out, dpi=150)
    print(f"\n  Saved: {out}")

    return {
        "algorithm": "Girvan-Newman",
        "dataset": DATASET,
        "modularity": best_modularity,
        "n_communities": best_n,
        "partition": partition,
        "results": results,
        "werewolf_community": werewolf_community,
    }


if __name__ == "__main__":
    run_girvan_newman()