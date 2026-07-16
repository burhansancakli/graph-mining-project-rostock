
import sys
from collections import defaultdict
from pathlib import Path

import community as community_louvain  # python-louvain
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colormaps
import networkx as nx

from graph_utils import load_graph, DATASET, PROJECT_ROOT

sys.path.insert(0, str(Path(__file__).resolve().parent))
from viz.export_data import export_comparison_json

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

WEREWOLF_FALLBACK_TERMS = {"werwolf", "werewolf", "weerwolf", "varulv", "werwölfe", "verwandlung"}


def _find_community_by_terms(partition, keyword_text, terms, exact_node=None):
    if exact_node is not None and exact_node in partition:
        return partition[exact_node]
    for node, comm in partition.items():
        kw = keyword_text.get(node, node).lower()
        if any(t in kw for t in terms):
            return comm
    return None


def run_louvain(dataset: str = None, export_json: bool = True, save_png: bool = True,
                 resolution: float = 1.0):
    """
    resolution: python-louvain's resolution parameter (default 1.0 = standard
    modularity). Worth knowing about specifically for the merged "all"
    dataset: modularity optimization has a well-documented "resolution
    limit" on large graphs -- it tends to merge what would be rich internal
    sub-structure into one big blob per region once the whole graph gets
    much bigger (we measured this directly: Mecklenburg alone splits into
    14 communities, but inside the merged "all" graph, at resolution=1,
    nearly all of Mecklenburg collapses into a single community). Raising
    `resolution` (try 2-5) partially recovers finer structure, at the cost
    of also fragmenting other regions more aggressively -- it's a knob to
    experiment with, not a one-line fix, so it isn't cranked up by default.
    """
    ds = dataset or DATASET
    out_dir = OUTPUT_DIR / ds
    out_dir.mkdir(parents=True, exist_ok=True)

    G, keyword_text, keyword_regions = load_graph(ds)

    partition = community_louvain.best_partition(G, weight="weight", random_state=42, resolution=resolution)
    modularity = community_louvain.modularity(partition, G, weight="weight")
    n_communities = len(set(partition.values()))

    print(f"\n-- Louvain results [{ds}] --")
    print(f"  Communities : {n_communities}")
    print(f"  Modularity Q: {modularity:.4f}")

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
        print(f"  Community {comm:2d} (size={len(members):4d}) regions={regions_in_comm}: "
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
        print("\n  * No Werewolf keyword found in this dataset.")

    if save_png:
        _draw_png(G, keyword_text, partition, comm_members, degree, ds, modularity, n_communities, out_dir)

    result = {
        "algorithm": "Louvain", "dataset": ds, "modularity": modularity,
        "n_communities": n_communities, "partition": partition,
        "results": results, "werewolf_community": werewolf_community,
        "G": G, "keyword_text": keyword_text, "comm_members": comm_members, "degree": degree,
    }

    if export_json:
        out_path = out_dir / f"graph_export_{ds}.json"
        export_comparison_json(ds, G, keyword_text, degree, result, gn_res=None, out_path=out_path)

    return result


def _draw_png(G, keyword_text, partition, comm_members, degree, ds, modularity, n_communities, out_dir):
    plt.figure(figsize=(14, 10))
    pos = nx.spring_layout(G, k=0.4, seed=42, weight="weight")
    cmap = colormaps.get_cmap("tab20")
    node_colors = [cmap(partition[n] % 20) for n in G.nodes()]
    node_sizes = [30 + degree.get(n, 0) * 3 for n in G.nodes()]

    nx.draw_networkx_edges(G, pos, alpha=0.15, width=0.5)
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes,
                           edgecolors="black", linewidths=0.3)

    label_nodes = set()
    for members in comm_members.values():
        label_nodes.update(sorted(members, key=lambda n: -degree.get(n, 0))[:3])
    nx.draw_networkx_labels(G, pos,
                            labels={n: keyword_text.get(n, n) for n in label_nodes},
                            font_size=7)

    plt.title(f"Louvain -- {ds} | {n_communities} communities | Q={modularity:.3f}", fontsize=13)
    plt.axis("off")
    plt.tight_layout()
    out = out_dir / f"louvain_{ds}.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    import sys
    run_louvain(sys.argv[1] if len(sys.argv) > 1 else None)
