"""
- Uses the same keyword co-occurrence graph as Louvain (graph_utils).
- GN is O(m^2 n), so we filter to a subgraph: only edges with
  weight >= MIN_WEIGHT_GN, capped to the top MAX_NODES_GN nodes by degree.
- On large graphs (especially the merged "all" dataset: ~18k nodes /
  1.18M edges) a fixed MIN_WEIGHT_GN can still leave a very dense
  induced subgraph even after the node cap, which makes GN extremely slow
  (betweenness recomputation on every edge removal). `_auto_threshold()`
  raises the weight cutoff automatically until the raw filtered edge count
  is small, so the capped subgraph stays sparse.
"""

import itertools
from collections import defaultdict
from pathlib import Path

import networkx as nx
from networkx.algorithms.community import girvan_newman, modularity
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from graph_utils import load_graph, DATASET, PROJECT_ROOT

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

MIN_WEIGHT_GN = 1.5           # starting threshold (auto-raised for large graphs, see below)
                              # -- lowered from the old default of 5: with
                              # graph_utils.ENABLE_FRACTIONAL_WEIGHTING (default on),
                              # edge weights are usually well under 1 per story,
                              # so a threshold of 5 would filter out nearly everything
MAX_NODES_GN = 300             # hard cap: top-N nodes by degree
MAX_GN_SPLITS = 30              # how many dendrogram levels to explore
MAX_EDGES_BEFORE_CAP = 3000   # GN gets slow above this -> auto-raise the threshold

WEREWOLF_FALLBACK_TERMS = {"werwolf", "werewolf", "weerwolf", "varulv", "werwölfe", "verwandlung"}


def _auto_threshold(G_full, start_weight):
    """
    Raises MIN_WEIGHT_GN until the raw (pre node-cap) filtered edge count is
    below MAX_EDGES_BEFORE_CAP, so that capping to MAX_NODES_GN afterwards
    yields a sparse subgraph rather than a dense one cut down artificially.
    """
    weight = start_weight
    for _ in range(20):
        n_edges = sum(1 for _, _, d in G_full.edges(data=True) if d.get("weight", 1) >= weight)
        if n_edges <= MAX_EDGES_BEFORE_CAP:
            return weight
        weight = int(weight * 1.6) + 1
    return weight


def _find_community_by_terms(partition, keyword_text, terms, exact_node=None):
    if exact_node is not None and exact_node in partition:
        return partition[exact_node]
    for node, comm in partition.items():
        kw = keyword_text.get(node, node).lower()
        if any(t in kw for t in terms):
            return comm
    return None


def run_girvan_newman(dataset: str = None, save_png: bool = True):
    ds = dataset or DATASET
    out_dir = OUTPUT_DIR / ds
    out_dir.mkdir(parents=True, exist_ok=True)

    G_full, keyword_text, keyword_regions = load_graph(ds)

    effective_weight = _auto_threshold(G_full, MIN_WEIGHT_GN)
    if effective_weight != MIN_WEIGHT_GN:
        print(f"  [auto] MIN_WEIGHT_GN raised to {effective_weight} "
              f"(the graph is too large/dense for the default {MIN_WEIGHT_GN})")

    G = nx.Graph()
    for u, v, data in G_full.edges(data=True):
        if data.get("weight", 1) >= effective_weight:
            G.add_edge(u, v, weight=data["weight"])

    if G.number_of_nodes() > MAX_NODES_GN:
        degree = dict(G.degree(weight="weight"))
        top_nodes = sorted(degree, key=lambda n: -degree[n])[:MAX_NODES_GN]
        G = G.subgraph(top_nodes).copy()

    if G.number_of_nodes() == 0:
        raise RuntimeError(
            f"GN subgraph for '{ds}' came out empty -- lower MIN_WEIGHT_GN (currently {effective_weight})."
        )

    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()
    for n in G.nodes():
        G.nodes[n]["regions"] = G_full.nodes[n].get("regions", [])

    print(f"\n-- Girvan-Newman [{ds}] --")
    print(f"  Subgraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  (filtered: weight >= {effective_weight}, max {MAX_NODES_GN} nodes)")
    print("  Running GN -- this can take a while...")

    gn_generator = girvan_newman(G)
    best_modularity = -1
    best_communities = None
    best_n = 0

    for communities in itertools.islice(gn_generator, MAX_GN_SPLITS):
        comm_list = list(communities)
        try:
            q = modularity(G, comm_list, weight="weight")
        except Exception:
            continue
        if q > best_modularity:
            best_modularity = q
            best_communities = comm_list
            best_n = len(comm_list)

    print(f"  Best split found: {best_n} communities")
    print(f"  Best modularity Q: {best_modularity:.4f}")

    partition = {}
    for comm_id, members in enumerate(best_communities):
        for node in members:
            partition[node] = comm_id

    degree = dict(G.degree(weight="weight"))
    comm_members = defaultdict(list)
    for node, comm in partition.items():
        comm_members[comm].append(node)

    results = []
    for comm, members in sorted(comm_members.items(), key=lambda x: -len(x[1])):
        top_nodes = sorted(members, key=lambda n: -degree.get(n, 0))[:8]
        top_keywords = [keyword_text.get(n, n) for n in top_nodes]
        regions_in_comm = sorted({r for n in members for r in G.nodes[n].get("regions", [])})
        results.append({
            "community": comm, "size": len(members),
            "top_keywords": top_keywords, "regions": regions_in_comm,
        })
        print(f"  Community {comm:2d} (size={len(members):3d}) regions={regions_in_comm}: "
              f"{', '.join(top_keywords)}")

    werewolf_community = _find_community_by_terms(
        partition, keyword_text, WEREWOLF_FALLBACK_TERMS, exact_node="concept:werewolf"
    )
    if werewolf_community is not None:
        ww_members = comm_members[werewolf_community]
        ww_top = sorted(ww_members, key=lambda n: -degree.get(n, 0))[:12]
        print(f"\n  * Werewolf belongs to community {werewolf_community}:")
        print(f"    {', '.join(keyword_text.get(n, n) for n in ww_top)}")
    else:
        print("\n  * Werewolf not present in the filtered subgraph (weight threshold cut it out).")

    if save_png:
        _draw_png(G, keyword_text, partition, degree, ds, effective_weight, best_n, best_modularity, out_dir)

    return {
        "algorithm": "Girvan-Newman", "dataset": ds, "modularity": best_modularity,
        "n_communities": best_n, "partition": partition,
        "results": results, "werewolf_community": werewolf_community,
        "G": G, "keyword_text": keyword_text, "comm_members": comm_members, "degree": degree,
    }


def _draw_png(G, keyword_text, partition, degree, ds, effective_weight, best_n, best_modularity, out_dir):
    fig, ax = plt.subplots(figsize=(12, 9))
    pos = nx.spring_layout(G, k=0.5, seed=42)
    colors = plt.cm.Set3([i / max(best_n, 1) for i in [partition.get(n, 0) for n in G.nodes()]])
    node_sizes = [40 + degree.get(n, 0) * 5 for n in G.nodes()]

    nx.draw_networkx_edges(G, pos, alpha=0.2, width=0.6, ax=ax)
    nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=node_sizes,
                           edgecolors="black", linewidths=0.3, ax=ax)

    comm_members = defaultdict(list)
    for node, comm in partition.items():
        comm_members[comm].append(node)
    label_nodes = set()
    for members in comm_members.values():
        label_nodes.update(sorted(members, key=lambda n: -degree.get(n, 0))[:2])
    nx.draw_networkx_labels(G, pos,
                            labels={n: keyword_text.get(n, n) for n in label_nodes},
                            font_size=7, ax=ax)

    ax.set_title(f"Girvan-Newman -- {ds} (weight>={effective_weight})\n"
                 f"{best_n} communities | Q={best_modularity:.3f}", fontsize=12)
    ax.set_axis_off()
    plt.tight_layout()
    out = out_dir / f"girvan_newman_{ds}.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    import sys
    run_girvan_newman(sys.argv[1] if len(sys.argv) > 1 else None)
