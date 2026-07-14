"""
Overlapping community detection using BigCLAM (karateclub library).

Key difference from Louvain/GN:
  - BigCLAM allows a keyword to belong to MULTIPLE communities simultaneously
  - This matters because e.g. "Wolf" can belong to both the Werewolf cluster
    AND the Animal Tales cluster at once.
  - There is no standard modularity Q for overlapping communities, so we
    report overlap-count / coverage instead and compare qualitatively
    against Louvain/GN using metrics.jaccard_best_matches() (see comparison.py).

Note on what actually happens in practice (seen in real runs on
Mecklenburg): even when N_COMMUNITIES=16 is requested as the embedding
dimension, karateclub's BigCLAM assigns each node its single best-fit
community via argmax over that embedding, so the number of communities
that actually end up populated can be much smaller (we saw 3 on
Mecklenburg). That's expected behaviour, not a bug -- it's documented
below and reported at runtime.
"""

import sys
import types
import importlib.util
from collections import defaultdict
from pathlib import Path

import networkx as nx

# See the import note above: this avoids needing `gensim` (and therefore a
# C++ compiler on Windows) just to use BigCLAM, which never touches it.
if "karateclub" not in sys.modules:
    _stub = types.ModuleType("karateclub")
    _stub.__path__ = importlib.util.find_spec("karateclub").submodule_search_locations
    sys.modules["karateclub"] = _stub
from karateclub.estimator import Estimator  # noqa: F401  (BigClam needs this importable first)
from karateclub.community_detection.overlapping.bigclam import BigClam

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from graph_utils import load_graph, DATASET, PROJECT_ROOT

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

# BigCLAM is also slow on large graphs -- use a filtered, unweighted subgraph
MIN_WEIGHT_BIGCLAM = 3
MAX_NODES_BIGCLAM = 500
N_COMMUNITIES = 16  # latent embedding dimension; the number of communities that
# actually end up populated after argmax can be smaller (see above)

WEREWOLF_FALLBACK_TERMS = {"werwolf", "werewolf", "weerwolf", "varulv", "werwölfe", "verwandlung"}


def _normalize_memberships(raw_memberships, id_to_original):
    normalized = {}
    for node_int, comms in raw_memberships.items():
        if isinstance(comms, (list, tuple, set)):
            comms_list = [int(c) for c in comms]
        else:
            try:
                iter(comms)
            except TypeError:
                comms_list = [int(comms)]
            else:
                comms_list = [int(c) for c in comms]
        normalized[id_to_original[node_int]] = comms_list
    return normalized


def run_bigclam(dataset: str = None, save_png: bool = True):
    ds = dataset or DATASET
    out_dir = OUTPUT_DIR / ds
    out_dir.mkdir(parents=True, exist_ok=True)

    G_full, keyword_text, keyword_regions = load_graph(ds)

    # ── Build filtered subgraph (BigCLAM uses an unweighted graph) ───────────
    G = nx.Graph()
    for u, v, data in G_full.edges(data=True):
        if data.get("weight", 1) >= MIN_WEIGHT_BIGCLAM:
            G.add_edge(u, v)

    if G.number_of_nodes() > MAX_NODES_BIGCLAM:
        degree = dict(G.degree())
        top_nodes = sorted(degree, key=lambda n: -degree[n])[:MAX_NODES_BIGCLAM]
        G = G.subgraph(top_nodes).copy()

    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()

    print(f"\n-- BigCLAM [{ds}] --")
    print(f"  Subgraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # BigCLAM needs consecutive integer node labels.
    node_list = list(G.nodes())
    G_relabeled = nx.relabel_nodes(G, {n: i for i, n in enumerate(node_list)})
    id_to_original = {i: n for i, n in enumerate(node_list)}

    # Some karateclub versions expect every node to have a self-loop.
    for node in list(G_relabeled.nodes()):
        G_relabeled.add_edge(node, node)

    # ── Run BigCLAM ───────────────────────────────────────────────────────────
    model = BigClam(dimensions=N_COMMUNITIES)
    model.fit(G_relabeled)
    memberships = model.get_memberships()  # node_int -> community id(s)

    print(f"  Communities requested: {N_COMMUNITIES} (latent embedding dimension)")
    community_ids = sorted({int(c) for c in memberships.values()} if
                           not any(isinstance(c, (list, tuple, set)) for c in memberships.values())
                           else {int(x) for c in memberships.values() for x in
                                 (c if isinstance(c, (list, tuple, set)) else [c])})
    print(f"  Communities actually populated (argmax): {len(community_ids)}")
    if len(community_ids) < N_COMMUNITIES:
        print(f"  Note: karateclub's BigCLAM here assigns one winning community per node via "
              f"argmax, so fewer than {N_COMMUNITIES} ids can show up even though the "
              f"embedding has {N_COMMUNITIES} dimensions -- this is expected, not an error.")

    memberships_orig = _normalize_memberships(memberships, id_to_original)

    comm_members = defaultdict(list)
    for node, comms in memberships_orig.items():
        for c in comms:
            comm_members[c].append(node)

    multi_membership = sum(1 for comms in memberships_orig.values() if len(comms) > 1)
    print(f"  Nodes in multiple communities (overlap): {multi_membership} / {len(memberships_orig)} "
          f"({100 * multi_membership / max(len(memberships_orig), 1):.1f}%)")

    degree = dict(G.degree())
    results = []
    for comm, members in sorted(comm_members.items(), key=lambda x: -len(x[1])):
        top_nodes = sorted(members, key=lambda n: -degree.get(n, 0))[:8]
        top_keywords = [keyword_text.get(n, n) for n in top_nodes]
        results.append({"community": comm, "size": len(members), "top_keywords": top_keywords})
        print(f"  Community {comm:2d} (size={len(members):3d}): {', '.join(top_keywords)}")

    # ── Werewolf: is it in multiple communities? ─────────────────────────────
    print("\n  * Werewolf keyword memberships:")
    found = False
    for node, comms in memberships_orig.items():
        kw = keyword_text.get(node, "").lower()
        if node == "concept:werewolf" or any(t in kw for t in WEREWOLF_FALLBACK_TERMS):
            print(f"    '{keyword_text.get(node, node)}' -> communities: {comms}")
            for c in comms:
                top_in_comm = sorted(comm_members[c], key=lambda n: -degree.get(n, 0))[:6]
                print(f"      Community {c}: {', '.join(keyword_text.get(n, n) for n in top_in_comm)}")
            found = True
    werewolf_community = None
    if not found:
        print("    Not found in the filtered subgraph (it may have been cut by the "
              "unweighted top-degree filter -- this is a real limitation of BigCLAM "
              "on a hub-dominated graph like this one, worth calling out in the writeup).")
    else:
        # for parity with the Louvain/GN result dict (comparison.py's werewolf txt export)
        for node, comms in memberships_orig.items():
            kw = keyword_text.get(node, "").lower()
            if node == "concept:werewolf" or any(t in kw for t in WEREWOLF_FALLBACK_TERMS):
                werewolf_community = comms[0] if comms else None
                break

    if save_png:
        _draw_png(G, G_relabeled, keyword_text, memberships_orig, id_to_original, degree, ds, out_dir)

    return {
        "algorithm": "BigCLAM", "dataset": ds,
        "modularity": None,  # not applicable to overlapping communities
        "n_communities": len(community_ids),
        "memberships": memberships_orig,
        "results": results,
        "overlap_count": multi_membership,
        "werewolf_community": werewolf_community,
    }


def _draw_png(G, G_relabeled, keyword_text, memberships_orig, id_to_original, degree, ds, out_dir):
    primary_comm = {}
    for node in G_relabeled.nodes():
        orig = id_to_original.get(node, node)
        comms = memberships_orig.get(orig, [0])
        primary_comm[node] = comms[0] if comms else 0

    fig, ax = plt.subplots(figsize=(12, 9))
    pos = nx.spring_layout(G_relabeled, k=0.5, seed=42)

    cmap = plt.get_cmap("tab20")
    colors = [cmap(primary_comm.get(n, 0) % 20) for n in G_relabeled.nodes()]
    node_sizes = [40 + degree.get(id_to_original.get(n, n), 1) * 5 for n in G_relabeled.nodes()]

    overlap_nodes = [n for n in G_relabeled.nodes()
                     if len(memberships_orig.get(id_to_original.get(n, n), [])) > 1]

    nx.draw_networkx_edges(G_relabeled, pos, alpha=0.15, width=0.5, ax=ax)
    nx.draw_networkx_nodes(G_relabeled, pos, node_color=colors,
                           node_size=node_sizes, edgecolors="black", linewidths=0.3, ax=ax)
    if overlap_nodes:
        nx.draw_networkx_nodes(G_relabeled, pos, nodelist=overlap_nodes,
                               node_color="none", node_size=[node_sizes[n] + 20 for n in overlap_nodes],
                               edgecolors="red", linewidths=2.0, ax=ax)

    label_ids = sorted(G_relabeled.nodes(), key=lambda n: -degree.get(id_to_original.get(n, n), 0))[:30]
    nx.draw_networkx_labels(G_relabeled, pos,
                            labels={n: keyword_text.get(id_to_original.get(n, n), str(n)) for n in label_ids},
                            font_size=7, ax=ax)

    unique_primary_communities = sorted({primary_comm[n] for n in G_relabeled.nodes()})
    legend_handles = [
        Line2D([0], [0], marker='o', linestyle='', markerfacecolor=cmap(comm % 20),
               markeredgecolor='black', markersize=8, label=f'Community {comm}')
        for comm in unique_primary_communities
    ]
    ax.legend(handles=legend_handles, title='Community colors', loc='center left',
              bbox_to_anchor=(1.0, 0.5), frameon=True)

    ax.set_title(f"BigCLAM (overlapping) -- {ds}\n"
                 f"red ring = node in more than one community", fontsize=12)
    ax.set_axis_off()
    plt.tight_layout(rect=(0, 0, 0.84, 1))
    out = out_dir / f"bigclam_{ds}.png"
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    import sys

    run_bigclam(sys.argv[1] if len(sys.argv) > 1 else None)
