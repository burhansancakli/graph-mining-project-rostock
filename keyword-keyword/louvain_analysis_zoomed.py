"""
Zoomed Louvain community detection.

This script runs Louvain on the full keyword co-occurrence graph and
optionally reruns Louvain on a selected community's induced subgraph.

Usage:
  python keyword-keyword/louvain_analysis_zoomed.py
  python keyword-keyword/louvain_analysis_zoomed.py --zoom-community 1
  python keyword-keyword/louvain_analysis_zoomed.py --zoom-hexe
"""

import argparse
from collections import defaultdict

import community as community_louvain
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colormaps

from graph_utils import load_graph, DATASET

WEREWOLF_TERMS = {"werwolf", "werewolf", "werwölfe", "verwandlung"}
HEXE_TERMS = {"hexe", "hexen", "zauberin", "heren", "hexerei", "zauberei"}


def build_comm_members(partition):
    comm_members = defaultdict(list)
    for node, comm in partition.items():
        comm_members[comm].append(node)
    return comm_members


def describe_partition(name, G, keyword_text, partition):
    degree = dict(G.degree(weight="weight"))
    comm_members = build_comm_members(partition)
    modularity = community_louvain.modularity(partition, G, weight="weight")
    n_communities = len(comm_members)

    print(f"\n── Louvain [{name}] ──")
    print(f"  Communities : {n_communities}")
    print(f"  Modularity Q: {modularity:.4f}")

    results = []
    for comm, members in sorted(comm_members.items(), key=lambda x: -len(x[1])):
        top_nodes = sorted(members, key=lambda n: -degree.get(n, 0))[:8]
        top_keywords = [keyword_text.get(n, n) for n in top_nodes]
        results.append({"community": comm, "size": len(members), "top_keywords": top_keywords})
        print(f"  Community {comm:2d} (size={len(members):4d}): {', '.join(top_keywords)}")

    return {
        "partition": partition,
        "degree": degree,
        "comm_members": comm_members,
        "modularity": modularity,
        "n_communities": n_communities,
        "results": results,
    }


def draw_partition(name, G, keyword_text, partition, analysis, filename):
    plt.figure(figsize=(14, 10))
    pos = __import__("networkx").spring_layout(G, k=0.4, seed=42, weight="weight")
    cmap = colormaps.get_cmap("tab20")
    node_colors = [cmap(partition[n] % 20) for n in G.nodes()]
    node_sizes = [30 + analysis["degree"].get(n, 0) * 3 for n in G.nodes()]

    import networkx as nx
    nx.draw_networkx_edges(G, pos, alpha=0.15, width=0.5)
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes,
                           edgecolors="black", linewidths=0.3)

    label_nodes = set()
    for members in analysis["comm_members"].values():
        label_nodes.update(sorted(members, key=lambda n: -analysis["degree"].get(n, 0))[:3])
    nx.draw_networkx_labels(G, pos,
                            labels={n: keyword_text.get(n, n) for n in label_nodes},
                            font_size=7)

    plt.title(f"Louvain — {name} | {analysis['n_communities']} communities | Q={analysis['modularity']:.3f}", fontsize=13)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    print(f"  Saved: {filename}")


def run_base_louvain():
    G, keyword_text = load_graph()
    partition = community_louvain.best_partition(G, weight="weight", random_state=42)
    analysis = describe_partition(DATASET, G, keyword_text, partition)
    draw_partition(DATASET, G, keyword_text, partition, analysis, f"louvain_{DATASET}.png")
    return G, keyword_text, analysis


def run_zoomed_louvain(community_id, zoom_label=None, filename=None):
    G, keyword_text, base_analysis = run_base_louvain()
    comm_members = base_analysis["comm_members"]

    if community_id not in comm_members:
        print(f"\nCommunity {community_id} not found in base partition.")
        print(f"Choose one of: {sorted(comm_members.keys())}")
        return base_analysis

    members = comm_members[community_id]
    H = G.subgraph(members).copy()
    label = zoom_label or f"{DATASET} community {community_id}"
    out_name = filename or f"louvain_{DATASET}_community_{community_id}.png"

    print(f"\n── Zooming into community {community_id} on {DATASET} ──")
    print(f"  Subgraph: {H.number_of_nodes()} nodes, {H.number_of_edges()} edges")

    partition = community_louvain.best_partition(H, weight="weight", random_state=42)
    zoom_analysis = describe_partition(label, H, keyword_text, partition)
    draw_partition(label, H, keyword_text, partition, zoom_analysis, out_name)
    return {"base": base_analysis, "zoom": zoom_analysis}


def find_community_by_terms(partition, keyword_text, terms):
    for node, comm in partition.items():
        kw = keyword_text.get(node, "").lower()
        if any(term in kw for term in terms):
            return comm
    return None


def main():
    parser = argparse.ArgumentParser(description="Run Louvain and optionally zoom into a single community.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--zoom-community", "-z", type=int,
                       help="Community ID from the base Louvain partition to rerun Louvain on")
    group.add_argument("--zoom-werewolf", action="store_true",
                       help="Zoom into the community containing the werewolf keyword")
    group.add_argument("--zoom-hexe", action="store_true",
                       help="Zoom into the community containing a hexe/witch keyword")
    args = parser.parse_args()

    if not args.zoom_community and not args.zoom_werewolf and not args.zoom_hexe:
        run_base_louvain()
        return

    G, keyword_text = load_graph()
    partition = community_louvain.best_partition(G, weight="weight", random_state=42)
    base_analysis = describe_partition(DATASET, G, keyword_text, partition)
    draw_partition(DATASET, G, keyword_text, partition, base_analysis, f"louvain_{DATASET}.png")

    if args.zoom_werewolf:
        community_id = find_community_by_terms(partition, keyword_text, WEREWOLF_TERMS)
        if community_id is None:
            print("\nNo werewolf-related keyword found in the base partition.")
            return
        print(f"\nSelected werewolf community: {community_id}")
        run_zoomed_louvain(community_id,
                           zoom_label=f"{DATASET} werewolf community",
                           filename=f"louvain_{DATASET}_community_werewolf.png")
    elif args.zoom_hexe:
        community_id = find_community_by_terms(partition, keyword_text, HEXE_TERMS)
        if community_id is None:
            print("\nNo hexe/witch-related keyword found in the base partition.")
            return
        print(f"\nSelected hexe community: {community_id}")
        run_zoomed_louvain(community_id,
                           zoom_label=f"{DATASET} hexe community",
                           filename=f"louvain_{DATASET}_community_hexe.png")
    else:
        community_id = args.zoom_community
        run_zoomed_louvain(community_id)


if __name__ == "__main__":
    main()
