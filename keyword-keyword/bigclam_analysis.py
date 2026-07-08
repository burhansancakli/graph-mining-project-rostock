"""
Overlapping community detection using BigCLAM (karateclub library).

Key difference from Louvain/GN:
  - BigCLAM allows a keyword to belong to MULTIPLE communities simultaneously
  - This is relevant because e.g. "Wolf" can belong to both
    the Werewolf cluster AND the Animal Tales cluster
  - There is no standard modularity Q for overlapping communities,
    so we report NMI and coverage instead, and compare qualitatively

"""

import networkx as nx
from karateclub import BigClam
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from collections import defaultdict

from graph_utils import load_graph, DATASET

# BigCLAM is also slow on large graphs — use filtered subgraph
MIN_WEIGHT_BIGCLAM = 3
MAX_NODES_BIGCLAM = 500
N_COMMUNITIES = 16   # set to same as Louvain result for fair comparison


def run_bigclam():
    G_full, keyword_text = load_graph()

    # ── Build filtered subgraph ───────────────────────────────────────────────
    G = nx.Graph()
    for u, v, data in G_full.edges(data=True):
        if data.get("weight", 1) >= MIN_WEIGHT_BIGCLAM:
            G.add_edge(u, v)  # BigCLAM uses unweighted graph

    if G.number_of_nodes() > MAX_NODES_BIGCLAM:
        degree = dict(G.degree())
        top_nodes = sorted(degree, key=lambda n: -degree[n])[:MAX_NODES_BIGCLAM]
        G = G.subgraph(top_nodes).copy()

    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()

    print(f"\n── BigCLAM [{DATASET}] ──")
    print(f"  Subgraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # BigCLAM requires nodes to be relabeled as consecutive integers
    node_list = list(G.nodes())
    G_relabeled = nx.relabel_nodes(G, {n: i for i, n in enumerate(node_list)})
    id_to_original = {i: n for i, n in enumerate(node_list)}

    # ── Run BigCLAM ───────────────────────────────────────────────────────────
    model = BigClam(dimensions=N_COMMUNITIES)
    model.fit(G_relabeled)
    memberships = model.get_memberships()  # dict: node_int -> list of community IDs

    print(f"  Communities requested: {N_COMMUNITIES}")

    # ── Translate back to original node IDs ───────────────────────────────────
    # memberships_orig: original_node_id -> list of community IDs
    memberships_orig = {
        id_to_original[node_int]: comms
        for node_int, comms in memberships.items()
    }

    # Build community -> members mapping (overlapping)
    comm_members = defaultdict(list)
    for node, comms in memberships_orig.items():
        for c in comms:
            comm_members[c].append(node)

    # ── Stats on overlap ──────────────────────────────────────────────────────
    multi_membership = sum(1 for comms in memberships_orig.values() if len(comms) > 1)
    print(f"  Nodes in multiple communities (overlap): {multi_membership} "
          f"/ {len(memberships_orig)} "
          f"({100 * multi_membership / max(len(memberships_orig), 1):.1f}%)")

    # ── Top keywords per community ────────────────────────────────────────────
    degree = dict(G.degree())
    results = []
    for comm, members in sorted(comm_members.items(), key=lambda x: -len(x[1])):
        top_nodes = sorted(members, key=lambda n: -degree.get(n, 0))[:8]
        top_keywords = [keyword_text.get(n, n) for n in top_nodes]
        results.append({"community": comm, "size": len(members), "top_keywords": top_keywords})
        print(f"  Community {comm:2d} (size={len(members):3d}): {', '.join(top_keywords)}")

    # ── Werewolf — key question: is it in multiple communities? ───────────────
    werewolf_terms = {"werwolf", "werewolf", "werwölfe", "verwandlung"}
    print("\n  ★ Werewolf keyword memberships:")
    found = False
    for node, comms in memberships_orig.items():
        kw = keyword_text.get(node, "").lower()
        if any(term in kw for term in werewolf_terms):
            print(f"    '{keyword_text.get(node, node)}' → communities: {comms}")
            for c in comms:
                top_in_comm = sorted(comm_members[c], key=lambda n: -degree.get(n, 0))[:6]
                print(f"      Community {c}: {', '.join(keyword_text.get(n, n) for n in top_in_comm)}")
            found = True
    if not found:
        print("    Not found in subgraph.")

    # ── Visualization ─────────────────────────────────────────────────────────
    # For overlapping communities: color by PRIMARY community (most members → node)
    primary_comm = {}
    for node in G.nodes():
        orig = id_to_original.get(node, node)
        comms = memberships_orig.get(orig, [0])
        primary_comm[node] = comms[0] if comms else 0

    plt.figure(figsize=(12, 9))
    pos = nx.spring_layout(G_relabeled, k=0.5, seed=42)
    colors = plt.cm.tab20([primary_comm.get(n, 0) % 20 / 20 for n in G_relabeled.nodes()])
    node_sizes = [40 + degree.get(id_to_original.get(n, n), 1) * 5 for n in G_relabeled.nodes()]

    # Nodes with overlap drawn with a ring border
    overlap_nodes = [n for n in G_relabeled.nodes()
                     if len(memberships_orig.get(id_to_original.get(n, n), [])) > 1]

    nx.draw_networkx_edges(G_relabeled, pos, alpha=0.15, width=0.5)
    nx.draw_networkx_nodes(G_relabeled, pos, node_color=colors,
                           node_size=node_sizes, edgecolors="black", linewidths=0.3)
    if overlap_nodes:
        nx.draw_networkx_nodes(G_relabeled, pos, nodelist=overlap_nodes,
                               node_color="none", node_size=[node_sizes[n] + 20 for n in overlap_nodes],
                               edgecolors="red", linewidths=2.0)

    label_ids = sorted(G_relabeled.nodes(), key=lambda n: -degree.get(id_to_original.get(n, n), 0))[:30]
    nx.draw_networkx_labels(G_relabeled, pos,
                            labels={n: keyword_text.get(id_to_original.get(n, n), str(n)) for n in label_ids},
                            font_size=7)

    plt.title(f"BigCLAM (overlapping) — {DATASET}\n"
              f"{N_COMMUNITIES} communities | red ring = multi-community node", fontsize=12)
    plt.axis("off")
    plt.tight_layout()
    out = f"bigclam_{DATASET}.png"
    plt.savefig(out, dpi=150)
    print(f"\n  Saved: {out}")

    return {
        "algorithm": "BigCLAM",
        "dataset": DATASET,
        "modularity": None,       # not applicable for overlapping
        "n_communities": N_COMMUNITIES,
        "memberships": memberships_orig,
        "results": results,
        "overlap_count": multi_membership,
    }


if __name__ == "__main__":
    run_bigclam()