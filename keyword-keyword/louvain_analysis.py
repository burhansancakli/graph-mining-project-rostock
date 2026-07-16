"""
Community detection using the Louvain algorithm.

What it does:
  - Builds a keyword co-occurrence graph from story data
  - Runs Louvain to find communities (hard partitioning)
  - Reports modularity Q, number of communities, top keywords per community
  - Highlights the Werewolf cluster specifically
"""

import community as community_louvain  # python-louvain package
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colormaps
from collections import defaultdict

from graph_utils import load_graph, DATASET


def run_louvain():
    G, keyword_text = load_graph()

    # ── Run Louvain ───────────────────────────────────────────────────────────
    partition = community_louvain.best_partition(G, weight="weight", random_state=42)
    modularity = community_louvain.modularity(partition, G, weight="weight")
    n_communities = len(set(partition.values()))

    print(f"\n── Louvain Results [{DATASET}] ──")
    print(f"  Communities : {n_communities}")
    print(f"  Modularity Q: {modularity:.4f}")

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
        print(f"  Community {comm:2d} (size={len(members):4d}): {', '.join(top_keywords)}")

    # ── Werewolf cluster ──────────────────────────────────────────────────────
    werewolf_terms = {"werwolf", "werewolf", "werwölfe", "verwandlung", "varulv"}
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
        print("\n  ★ No Werewolf keyword found in this dataset.")

    # ── Visualization ─────────────────────────────────────────────────────────
    plt.figure(figsize=(14, 10))
    pos = __import__("networkx").spring_layout(G, k=0.4, seed=42, weight="weight")
    cmap = colormaps.get_cmap("tab20")
    node_colors = [cmap(partition[n] % 20) for n in G.nodes()]
    node_sizes = [30 + degree.get(n, 0) * 1 for n in G.nodes()]

    import networkx as nx
    nx.draw_networkx_edges(G, pos, alpha=0.15, width=0.5)
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes,
                           edgecolors="black", linewidths=0.3)

    # Label top 3 hub nodes per community
    label_nodes = set()
    for members in comm_members.values():
        label_nodes.update(sorted(members, key=lambda n: -degree.get(n, 0))[:3])
    nx.draw_networkx_labels(G, pos,
                            labels={n: keyword_text.get(n, n) for n in label_nodes},
                            font_size=7)

    plt.title(f"Louvain — {DATASET} | {n_communities} communities | Q={modularity:.3f}", fontsize=13)
    plt.axis("off")
    plt.tight_layout()
    out = f"louvain_{DATASET}.png"
    plt.savefig(out, dpi=150)
    print(f"\n  Saved: {out}")

    return {
        "algorithm": "Louvain",
        "dataset": DATASET,
        "modularity": modularity,
        "n_communities": n_communities,
        "partition": partition,
        "results": results,
        "werewolf_community": werewolf_community,
    }


if __name__ == "__main__":
    run_louvain()