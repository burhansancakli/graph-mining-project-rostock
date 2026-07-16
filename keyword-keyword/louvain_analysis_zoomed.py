"""
Base behaviour: run Louvain on the full graph, then optionally re-run Louvain on the induced subgraph of ONE
community, to see its internal sub-structure.

Usage:
  python louvain_analysis_zoomed.py
  python louvain_analysis_zoomed.py --zoom-community 1
  python louvain_analysis_zoomed.py --zoom-hexe
  python louvain_analysis_zoomed.py --zoom-werewolf --exclude-anchor
  python louvain_analysis_zoomed.py --dataset all --zoom-werewolf
"""


import argparse
from collections import defaultdict
from pathlib import Path

import community as community_louvain
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colormaps
import networkx as nx

from graph_utils import load_graph, DATASET, PROJECT_ROOT
from metrics import zoom_excluding_anchor

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

WEREWOLF_TERMS = {"werwolf", "werewolf", "weerwolf", "varulv", "werwölfe", "verwandlung"}
HEXE_TERMS = {"hexe", "hexen", "zauberin", "heks", "heksen", "hexerei", "zauberei", "witch"}


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

    print(f"\n-- Louvain [{name}] --")
    print(f"  Communities : {n_communities}")
    print(f"  Modularity Q: {modularity:.4f}")

    results = []
    for comm, members in sorted(comm_members.items(), key=lambda x: -len(x[1])):
        top_nodes = sorted(members, key=lambda n: -degree.get(n, 0))[:8]
        top_keywords = [keyword_text.get(n, n) for n in top_nodes]
        results.append({"community": comm, "size": len(members), "top_keywords": top_keywords})
        print(f"  Community {comm:2d} (size={len(members):4d}): {', '.join(top_keywords)}")

    return {
        "partition": partition, "degree": degree, "comm_members": comm_members,
        "modularity": modularity, "n_communities": n_communities, "results": results,
    }


def draw_partition(name, G, keyword_text, partition, analysis, filepath):
    plt.figure(figsize=(14, 10))
    pos = nx.spring_layout(G, k=0.4, seed=42, weight="weight")
    cmap = colormaps.get_cmap("tab20")
    node_colors = [cmap(partition[n] % 20) for n in G.nodes()]
    node_sizes = [30 + analysis["degree"].get(n, 0) * 3 for n in G.nodes()]

    nx.draw_networkx_edges(G, pos, alpha=0.15, width=0.5)
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes,
                           edgecolors="black", linewidths=0.3)

    label_nodes = set()
    for members in analysis["comm_members"].values():
        label_nodes.update(sorted(members, key=lambda n: -analysis["degree"].get(n, 0))[:3])
    nx.draw_networkx_labels(G, pos,
                            labels={n: keyword_text.get(n, n) for n in label_nodes},
                            font_size=7)

    plt.title(f"Louvain -- {name} | {analysis['n_communities']} communities | "
              f"Q={analysis['modularity']:.3f}", fontsize=13)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(filepath, dpi=150)
    plt.close()
    print(f"  Saved: {filepath}")


def run_base_louvain(dataset):
    out_dir = OUTPUT_DIR / dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    G, keyword_text, keyword_regions = load_graph(dataset)
    partition = community_louvain.best_partition(G, weight="weight", random_state=42)
    analysis = describe_partition(dataset, G, keyword_text, partition)
    draw_partition(dataset, G, keyword_text, partition, analysis, out_dir / f"louvain_{dataset}.png")
    return G, keyword_text, analysis, out_dir


def find_community_by_terms(partition, keyword_text, terms, exact_node=None):
    if exact_node is not None and exact_node in partition:
        return partition[exact_node]
    for node, comm in partition.items():
        kw = keyword_text.get(node, "").lower()
        if any(term in kw for term in terms):
            return comm
    return None


def find_anchor_node(comm_members_list, keyword_text, terms, exact_node=None):
    """Finds the actual node id to use as 'anchor' for --exclude-anchor."""
    if exact_node is not None and exact_node in comm_members_list:
        return exact_node
    for node in comm_members_list:
        kw = keyword_text.get(node, "").lower()
        if any(term in kw for term in terms):
            return node
    return None


def run_zoomed_louvain(dataset, community_id, zoom_label=None, filename=None,
                        exclude_anchor_terms=None, exclude_anchor_exact=None):
    G, keyword_text, base_analysis, out_dir = run_base_louvain(dataset)
    comm_members = base_analysis["comm_members"]

    if community_id not in comm_members:
        print(f"\nCommunity {community_id} not found in base partition.")
        print(f"Choose one of: {sorted(comm_members.keys())}")
        return base_analysis

    members = comm_members[community_id]
    label = zoom_label or f"{dataset} community {community_id}"

    if exclude_anchor_terms is not None:
        anchor = find_anchor_node(members, keyword_text, exclude_anchor_terms, exclude_anchor_exact)
        if anchor is None:
            print(f"\nNo matching anchor keyword found inside community {community_id}; "
                  f"falling back to the normal zoom (anchor kept in).")
        else:
            zoom_result = zoom_excluding_anchor(G, keyword_text, members, anchor)
            return {"base": base_analysis, "zoom_excluding_anchor": zoom_result}

    H = G.subgraph(members).copy()
    out_name = filename or (out_dir / f"louvain_{dataset}_community_{community_id}.png")

    print(f"\n-- Zooming into community {community_id} on {dataset} --")
    print(f"  Subgraph: {H.number_of_nodes()} nodes, {H.number_of_edges()} edges")

    partition = community_louvain.best_partition(H, weight="weight", random_state=42)
    zoom_analysis = describe_partition(label, H, keyword_text, partition)
    draw_partition(label, H, keyword_text, partition, zoom_analysis, out_name)
    return {"base": base_analysis, "zoom": zoom_analysis}


def main():
    parser = argparse.ArgumentParser(description="Run Louvain and optionally zoom into one community.")
    parser.add_argument("--dataset", "-d", default=DATASET,
                        help="mecklenburg | iceland | denmark | netherlands | all")
    parser.add_argument("--exclude-anchor", action="store_true",
                        help="Drop the anchor keyword itself before re-running Louvain on the zoomed "
                             "community (the professor's original 'remove the word' suggestion).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--zoom-community", "-z", type=int,
                       help="Community ID from the base Louvain partition to zoom into")
    group.add_argument("--zoom-werewolf", action="store_true",
                       help="Zoom into the community containing the werewolf keyword/concept")
    group.add_argument("--zoom-hexe", action="store_true",
                       help="Zoom into the community containing a hexe/witch keyword")
    args = parser.parse_args()

    if not args.zoom_community and not args.zoom_werewolf and not args.zoom_hexe:
        run_base_louvain(args.dataset)
        return

    out_dir = OUTPUT_DIR / args.dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    G, keyword_text, keyword_regions = load_graph(args.dataset)
    partition = community_louvain.best_partition(G, weight="weight", random_state=42)
    base_analysis = describe_partition(args.dataset, G, keyword_text, partition)
    draw_partition(args.dataset, G, keyword_text, partition, base_analysis,
                   out_dir / f"louvain_{args.dataset}.png")

    if args.zoom_werewolf:
        community_id = find_community_by_terms(partition, keyword_text, WEREWOLF_TERMS,
                                                exact_node="concept:werewolf")
        if community_id is None:
            print("\nNo werewolf-related keyword found in the base partition.")
            return
        print(f"\nSelected werewolf community: {community_id}")
        run_zoomed_louvain(
            args.dataset, community_id,
            zoom_label=f"{args.dataset} werewolf community",
            filename=out_dir / f"louvain_{args.dataset}_community_werewolf.png",
            exclude_anchor_terms=WEREWOLF_TERMS if args.exclude_anchor else None,
            exclude_anchor_exact="concept:werewolf",
        )
    elif args.zoom_hexe:
        community_id = find_community_by_terms(partition, keyword_text, HEXE_TERMS,
                                                exact_node="concept:witch")
        if community_id is None:
            print("\nNo hexe/witch-related keyword found in the base partition.")
            return
        print(f"\nSelected hexe community: {community_id}")
        run_zoomed_louvain(
            args.dataset, community_id,
            zoom_label=f"{args.dataset} hexe community",
            filename=out_dir / f"louvain_{args.dataset}_community_hexe.png",
            exclude_anchor_terms=HEXE_TERMS if args.exclude_anchor else None,
            exclude_anchor_exact="concept:witch",
        )
    else:
        run_zoomed_louvain(
            args.dataset, args.zoom_community,
            exclude_anchor_terms=None,  # only meaningful for the named --zoom-werewolf/--zoom-hexe cases
        )


if __name__ == "__main__":
    main()
