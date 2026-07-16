#!/usr/bin/env python3
"""
Run Louvain, Girvan-Newman, and/or BigCLAM community detection on each region.

Usage:
    python run_community_detection.py                              # all three algorithms
    python run_community_detection.py --louvain                    # Louvain only
    python run_community_detection.py --gn                         # GN only
    python run_community_detection.py --bigclam                    # BigCLAM only
    python run_community_detection.py --louvain --bigclam          # Louvain + BigCLAM
    python run_community_detection.py --regions denmark iceland    # specific regions

Output goes to a single `output/` folder:
    output/louvain_<region>.png / .json
    output/girvan_newman_<region>.png / .json
    output/bigclam_<region>.png / .json
    output/summary.json
"""

import argparse
import json
import math
import sys
import traceback
from collections import defaultdict
from pathlib import Path

import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colormaps
from matplotlib.lines import Line2D

import graph_utils

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# ── Region configs ────────────────────────────────────────────────────────────
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

# GN-specific settings (slow — stricter filtering for larger datasets)
GN_MIN_WEIGHT_DEFAULT = 5
GN_MAX_NODES_DEFAULT = 300

REGION_GN_MIN_WEIGHT = {
    "denmark": 15,
    "iceland": 5,
    "mecklenburg": 5,
    "netherlands": 20,
    "merged": 15,
}
REGION_GN_MAX_NODES = {
    "denmark": 150,
    "iceland": 300,
    "mecklenburg": 300,
    "netherlands": 120,
    "merged": 150,
}

# BigCLAM settings (overlapping community detection)
BIGCLAM_MIN_WEIGHT_DEFAULT = 3
BIGCLAM_MAX_NODES_DEFAULT = 500
BIGCLAM_N_COMMUNITIES_DEFAULT = 16

REGION_BIGCLAM_MIN_WEIGHT = {
    "denmark": 5,
    "iceland": 3,
    "mecklenburg": 3,
    "netherlands": 8,
    "merged": 5,
}
REGION_BIGCLAM_MAX_NODES = {
    "denmark": 400,
    "iceland": 500,
    "mecklenburg": 500,
    "netherlands": 350,
    "merged": 400,
}
REGION_BIGCLAM_N_COMMUNITIES = {
    "denmark": 16,
    "iceland": 8,
    "mecklenburg": 14,
    "netherlands": 16,
    "merged": 20,
}


def _load_region(dataset_name: str):
    """Patch graph_utils and load a region's graph."""
    graph_utils.DATASET = dataset_name
    graph_utils.NODES_FILE = graph_utils.BASE_DIR / f"isebel-{dataset_name}-nodes.csv"
    graph_utils.EDGES_FILE = graph_utils.BASE_DIR / f"isebel-{dataset_name}-edges.csv"

    min_cooc = REGION_MIN_COOCCURRENCE.get(dataset_name, 10)
    min_comp = REGION_MIN_COMPONENT_SIZE.get(dataset_name, 50)
    G, keyword_text = graph_utils.load_graph(
        min_cooccurrence=min_cooc,
        min_component_size=min_comp,
    )
    return G, keyword_text, min_cooc, min_comp


def _compute_quality(G, partition, comm_members, degree, total_weight, modularity):
    """Compute cluster quality metrics (conductance, cut ratio, etc.)."""
    graph_density = nx.density(G)
    community_metrics = []
    all_conductances = []
    all_internal_densities = []
    inter_community_weight = 0.0

    for comm, members in comm_members.items():
        member_set = set(members)
        n = len(members)

        internal_weight = 0.0
        for u in member_set:
            for v in G.neighbors(u):
                if v in member_set and u < v:
                    internal_weight += G[u][v].get("weight", 1)

        cut_weight = 0.0
        for u in member_set:
            for v in G.neighbors(u):
                if v not in member_set:
                    cut_weight += G[u][v].get("weight", 1)

        volume = sum(degree.get(m, 0) for m in member_set)
        denom = min(volume, 2 * total_weight - volume)
        conductance = cut_weight / denom if denom > 0 else 0.0

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

    inter_community_weight /= 2
    intra_community_weight = total_weight - inter_community_weight
    cut_ratio = inter_community_weight / total_weight if total_weight > 0 else 0.0

    sizes = [len(m) for m in comm_members.values()]
    size_entropy = -sum(
        (s / sum(sizes)) * math.log2(s / sum(sizes))
        for s in sizes if s > 0
    )
    max_size_ratio = max(sizes) / min(sizes) if sizes else 0
    avg_conductance = sum(all_conductances) / len(all_conductances) if all_conductances else 0
    avg_internal_density = sum(all_internal_densities) / len(all_internal_densities) if all_internal_densities else 0

    return {
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


def _find_werewolf(partition, comm_members, keyword_text, degree):
    """Find which community the werewolf keyword belongs to."""
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

    return werewolf_community, werewolf_members


def _get_top_keywords(comm_members, degree, keyword_text, top_n=8):
    """Get top keywords per community sorted by degree."""
    results = []
    for comm, members in sorted(comm_members.items(), key=lambda x: -len(x[1])):
        top_nodes = sorted(members, key=lambda n: -degree.get(n, 0))[:top_n]
        top_keywords = [keyword_text.get(n, n) for n in top_nodes]
        results.append({
            "community": comm,
            "size": len(members),
            "top_keywords": top_keywords,
        })
    return results


# ── LOUVAIN ───────────────────────────────────────────────────────────────────

def run_louvain_for_region(dataset_name: str) -> dict:
    import community as community_louvain

    G, keyword_text, min_cooc, min_comp = _load_region(dataset_name)

    if G.number_of_nodes() == 0:
        print(f"  ⚠ No nodes left for {dataset_name}, skipping.")
        return {}

    print(f"\n── Louvain [{dataset_name}] ──")
    print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    partition = community_louvain.best_partition(G, weight="weight", random_state=42)
    modularity = community_louvain.modularity(partition, G, weight="weight")
    n_communities = len(set(partition.values()))

    print(f"  Communities : {n_communities}")
    print(f"  Modularity Q: {modularity:.4f}")

    degree = dict(G.degree(weight="weight"))
    total_weight = sum(d for _, _, d in G.edges(data="weight"))

    comm_members = defaultdict(list)
    for node, comm in partition.items():
        comm_members[comm].append(node)

    quality = _compute_quality(G, partition, comm_members, degree, total_weight, modularity)
    print(f"  Cut ratio: {quality['cut_ratio']:.4f}")
    print(f"  Avg conductance: {quality['avg_conductance']:.4f}")

    results = _get_top_keywords(comm_members, degree, keyword_text)
    for r in results:
        print(f"  Community {r['community']:2d} (size={r['size']:4d}): {', '.join(r['top_keywords'])}")

    werewolf_community, werewolf_members = _find_werewolf(partition, comm_members, keyword_text, degree)
    if werewolf_community is not None:
        ww_top = sorted(werewolf_members, key=lambda n: -degree.get(n, 0))[:12]
        print(f"\n  ★ Werewolf belongs to Community {werewolf_community}:")
        print(f"    {', '.join(keyword_text.get(n, n) for n in ww_top)}")
    else:
        print("\n  ★ No Werewolf keyword found in this dataset.")

    # Visualization
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

    # JSON
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


# ── GIRVAN-NEWMAN ─────────────────────────────────────────────────────────────

def run_gn_for_region(dataset_name: str) -> dict:
    import itertools
    from networkx.algorithms.community import girvan_newman, modularity as gn_modularity

    G_full, keyword_text, min_cooc, min_comp = _load_region(dataset_name)

    # Per-region GN filtering
    gn_min_weight = REGION_GN_MIN_WEIGHT.get(dataset_name, GN_MIN_WEIGHT_DEFAULT)
    gn_max_nodes = REGION_GN_MAX_NODES.get(dataset_name, GN_MAX_NODES_DEFAULT)

    # Filter to stronger edges for GN
    G = nx.Graph()
    for u, v, data in G_full.edges(data=True):
        if data.get("weight", 1) >= gn_min_weight:
            G.add_edge(u, v, weight=data["weight"])

    if G.number_of_nodes() > gn_max_nodes:
        degree_full = dict(G.degree(weight="weight"))
        top_nodes = sorted(degree_full, key=lambda n: -degree_full[n])[:gn_max_nodes]
        G = G.subgraph(top_nodes).copy()

    if G.number_of_nodes() == 0:
        print(f"  ⚠ No nodes left after GN filtering for {dataset_name}, skipping.")
        return {}

    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()

    print(f"\n── Girvan-Newman [{dataset_name}] ──")
    print(f"  Subgraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  (filtered: weight >= {gn_min_weight}, max {gn_max_nodes} nodes)")
    print("  Running GN — this may take a minute...")

    gn_generator = girvan_newman(G)
    best_modularity = -1
    best_communities = None
    best_n = 0

    for communities in itertools.islice(gn_generator, 30):
        comm_list = list(communities)
        try:
            q = gn_modularity(G, comm_list, weight="weight")
        except Exception:
            continue
        if q > best_modularity:
            best_modularity = q
            best_communities = comm_list
            best_n = len(comm_list)

    print(f"  Best communities: {best_n}")
    print(f"  Best Modularity Q: {best_modularity:.4f}")

    partition = {}
    for comm_id, members in enumerate(best_communities):
        for node in members:
            partition[node] = comm_id

    degree = dict(G.degree(weight="weight"))
    total_weight = sum(d for _, _, d in G.edges(data="weight"))

    comm_members = defaultdict(list)
    for node, comm in partition.items():
        comm_members[comm].append(node)

    quality = _compute_quality(G, partition, comm_members, degree, total_weight, best_modularity)
    print(f"  Cut ratio: {quality['cut_ratio']:.4f}")
    print(f"  Avg conductance: {quality['avg_conductance']:.4f}")

    results = _get_top_keywords(comm_members, degree, keyword_text)
    for r in results:
        print(f"  Community {r['community']:2d} (size={r['size']:3d}): {', '.join(r['top_keywords'])}")

    werewolf_community, werewolf_members = _find_werewolf(partition, comm_members, keyword_text, degree)
    if werewolf_community is not None:
        ww_top = sorted(werewolf_members, key=lambda n: -degree.get(n, 0))[:12]
        print(f"\n  ★ Werewolf belongs to Community {werewolf_community}:")
        print(f"    {', '.join(keyword_text.get(n, n) for n in ww_top)}")
    else:
        print("\n  ★ Werewolf not found in subgraph.")

    # Visualization
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
    plt.title(f"Girvan-Newman — {dataset_name} (weight≥{gn_min_weight})\n"
              f"{best_n} communities | Q={best_modularity:.3f}", fontsize=12)
    plt.axis("off")
    plt.tight_layout()
    png_out = OUTPUT_DIR / f"girvan_newman_{dataset_name}.png"
    plt.savefig(png_out, dpi=150)
    plt.close()
    print(f"\n  Saved: {png_out}")

    # JSON
    json_out = OUTPUT_DIR / f"girvan_newman_{dataset_name}.json"
    output_data = {
        "algorithm": "Girvan-Newman",
        "dataset": dataset_name,
        "modularity": best_modularity,
        "n_communities": best_n,
        "min_weight": gn_min_weight,
        "max_nodes": gn_max_nodes,
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


# ── BIGCLAM (overlapping communities) ─────────────────────────────────────────

def run_bigclam_for_region(dataset_name: str) -> dict:
    from karateclub import BigClam

    G_full, keyword_text, min_cooc, min_comp = _load_region(dataset_name)

    # Per-region BigCLAM filtering
    bc_min_weight = REGION_BIGCLAM_MIN_WEIGHT.get(dataset_name, BIGCLAM_MIN_WEIGHT_DEFAULT)
    bc_max_nodes = REGION_BIGCLAM_MAX_NODES.get(dataset_name, BIGCLAM_MAX_NODES_DEFAULT)
    bc_n_comm = REGION_BIGCLAM_N_COMMUNITIES.get(dataset_name, BIGCLAM_N_COMMUNITIES_DEFAULT)

    # Build filtered subgraph (BigCLAM uses unweighted)
    G = nx.Graph()
    for u, v, data in G_full.edges(data=True):
        if data.get("weight", 1) >= bc_min_weight:
            G.add_edge(u, v)

    if G.number_of_nodes() > bc_max_nodes:
        degree_full = dict(G.degree())
        top_nodes = sorted(degree_full, key=lambda n: -degree_full[n])[:bc_max_nodes]
        G = G.subgraph(top_nodes).copy()

    if G.number_of_nodes() == 0:
        print(f"  ⚠ No nodes left after BigCLAM filtering for {dataset_name}, skipping.")
        return {}

    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()

    print(f"\n── BigCLAM [{dataset_name}] ──")
    print(f"  Subgraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  (filtered: weight >= {bc_min_weight}, max {bc_max_nodes} nodes)")

    # Relabel nodes as consecutive integers (required by karateclub)
    node_list = list(G.nodes())
    G_relabeled = nx.relabel_nodes(G, {n: i for i, n in enumerate(node_list)})
    id_to_original = {i: n for i, n in enumerate(node_list)}

    # Add self-loops (required by karateclub BigCLAM)
    for node in list(G_relabeled.nodes()):
        G_relabeled.add_edge(node, node)

    # Run BigCLAM
    print(f"  Running BigCLAM (n_communities={bc_n_comm})...")
    model = BigClam(dimensions=bc_n_comm)
    model.fit(G_relabeled)
    raw_memberships = model.get_memberships()

    # Normalize memberships
    memberships_orig = {}
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
        memberships_orig[id_to_original[node_int]] = comms_list

    # Build community -> members mapping (overlapping)
    comm_members = defaultdict(list)
    for node, comms in memberships_orig.items():
        for c in comms:
            comm_members[c].append(node)

    n_communities = len(comm_members)
    multi_membership = sum(1 for comms in memberships_orig.values() if len(comms) > 1)
    overlap_pct = 100 * multi_membership / max(len(memberships_orig), 1)

    print(f"  Communities produced: {n_communities}")
    print(f"  Nodes in multiple communities (overlap): {multi_membership}"
          f" / {len(memberships_orig)} ({overlap_pct:.1f}%)")

    # Compute quality metrics (using primary community assignment for comparability)
    degree = dict(G.degree())
    total_weight = sum(d for _, _, d in G.edges(data="weight", default=1))
    # For quality metrics, assign each node to its first community only
    primary_partition = {node: comms[0] for node, comms in memberships_orig.items() if comms}
    primary_comm_members = defaultdict(list)
    for node, comm in primary_partition.items():
        primary_comm_members[comm].append(node)

    quality = _compute_quality(G, primary_partition, primary_comm_members, degree, total_weight, 0)
    # BigCLAM doesn't have modularity Q in the traditional sense
    quality["modularity"] = None
    quality["overlap_nodes"] = multi_membership
    quality["overlap_percentage"] = round(overlap_pct, 1)

    print(f"  Cut ratio: {quality['cut_ratio']:.4f} (primary communities)")
    print(f"  Avg conductance: {quality['avg_conductance']:.4f}")

    # Top keywords per community
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

    # Werewolf — can be in multiple communities
    werewolf_terms = {"werwolf", "werewolf", "werwölfe", "verwandlung", "varulv"}
    werewolf_communities = []
    print("\n  ★ Werewolf keyword memberships:")
    found = False
    for node, comms in memberships_orig.items():
        kw = keyword_text.get(node, "").lower()
        if any(term in kw for term in werewolf_terms):
            print(f"    '{keyword_text.get(node, node)}' → communities: {comms}")
            for c in comms:
                top_in_comm = sorted(comm_members[c], key=lambda n: -degree.get(n, 0))[:6]
                print(f"      Community {c}: {', '.join(keyword_text.get(n, n) for n in top_in_comm)}")
            werewolf_communities = comms
            found = True
    if not found:
        print("    Not found in subgraph.")

    # Visualization
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

    # Highlight overlap nodes with red ring
    overlap_nodes = [n for n in G_relabeled.nodes()
                     if len(memberships_orig.get(id_to_original.get(n, n), [])) > 1]

    nx.draw_networkx_edges(G_relabeled, pos, alpha=0.15, width=0.5, ax=ax)
    nx.draw_networkx_nodes(G_relabeled, pos, node_color=colors,
                           node_size=node_sizes, edgecolors="black", linewidths=0.3, ax=ax)
    if overlap_nodes:
        nx.draw_networkx_nodes(G_relabeled, pos, nodelist=overlap_nodes,
                               node_color="none",
                               node_size=[node_sizes[i] + 20 for i, n in enumerate(G_relabeled.nodes()) if n in overlap_nodes],
                               edgecolors="red", linewidths=2.0, ax=ax)

    label_ids = sorted(G_relabeled.nodes(), key=lambda n: -degree.get(id_to_original.get(n, n), 0))[:30]
    nx.draw_networkx_labels(G_relabeled, pos,
                            labels={n: keyword_text.get(id_to_original.get(n, n), str(n)) for n in label_ids},
                            font_size=7, ax=ax)

    unique_primary = sorted({primary_comm[n] for n in G_relabeled.nodes()})
    legend_handles = [
        Line2D([0], [0], marker='o', linestyle='', markerfacecolor=cmap(comm % 20),
               markeredgecolor='black', markersize=8, label=f'Community {comm}')
        for comm in unique_primary
    ]
    ax.legend(handles=legend_handles, title='Primary community', loc='center left',
              bbox_to_anchor=(1.0, 0.5), frameon=True)
    ax.set_title(f"BigCLAM (overlapping) — {dataset_name}\n"
                 f"{n_communities} communities | {overlap_pct:.1f}% overlap | red ring = multi-community", fontsize=12)
    ax.set_axis_off()
    plt.tight_layout(rect=(0, 0, 0.84, 1))
    png_out = OUTPUT_DIR / f"bigclam_{dataset_name}.png"
    fig.savefig(png_out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"\n  Saved: {png_out}")

    # JSON
    json_out = OUTPUT_DIR / f"bigclam_{dataset_name}.json"
    output_data = {
        "algorithm": "BigCLAM",
        "dataset": dataset_name,
        "modularity": None,
        "n_communities": n_communities,
        "dimensions": bc_n_comm,
        "min_weight": bc_min_weight,
        "max_nodes": bc_max_nodes,
        "min_cooccurrence": min_cooc,
        "min_component_size": min_comp,
        "graph_nodes": G.number_of_nodes(),
        "graph_edges": G.number_of_edges(),
        "quality": quality,
        "communities": results,
        "werewolf_communities": werewolf_communities,
        "memberships": {str(k): v for k, v in memberships_orig.items()},
    }
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {json_out}")

    return output_data


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run Louvain, Girvan-Newman, and/or BigCLAM community detection.")
    parser.add_argument("--regions", nargs="+", metavar="REGION",
                        help="Regions to process (default: all)")
    parser.add_argument("--louvain", action="store_true", help="Run Louvain only")
    parser.add_argument("--gn", action="store_true", help="Run Girvan-Newman only")
    parser.add_argument("--bigclam", action="store_true", help="Run BigCLAM only")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    all_regions = args.regions or ["denmark", "iceland", "mecklenburg", "netherlands", "merged"]
    # If no algorithm flag is given, run all three
    any_flag = args.louvain or args.gn or args.bigclam
    run_louvain = not any_flag or args.louvain
    run_gn = not any_flag or args.gn
    run_bigclam = not any_flag or args.bigclam

    louvain_results = {}
    gn_results = {}
    bigclam_results = {}

    for region in all_regions:
        print(f"\n{'='*60}")
        print(f"  Processing: {region}")
        print(f"{'='*60}")

        if run_louvain:
            try:
                result = run_louvain_for_region(region)
                if result:
                    louvain_results[region] = result
            except FileNotFoundError as e:
                print(f"  ✗ Skipping Louvain for {region}: {e}")
            except Exception as e:
                print(f"  ✗ Louvain error for {region}: {e}")
                traceback.print_exc()

        if run_gn:
            try:
                result = run_gn_for_region(region)
                if result:
                    gn_results[region] = result
            except FileNotFoundError as e:
                print(f"  ✗ Skipping GN for {region}: {e}")
            except Exception as e:
                print(f"  ✗ GN error for {region}: {e}")
                traceback.print_exc()

        if run_bigclam:
            try:
                result = run_bigclam_for_region(region)
                if result:
                    bigclam_results[region] = result
            except FileNotFoundError as e:
                print(f"  ✗ Skipping BigCLAM for {region}: {e}")
            except Exception as e:
                print(f"  ✗ BigCLAM error for {region}: {e}")
                traceback.print_exc()

    # ── Combined summary ──────────────────────────────────────────────────────
    summary = {"louvain": {}, "girvan_newman": {}, "bigclam": {}}

    for region, data in louvain_results.items():
        q = data.get("quality", {})
        summary["louvain"][region] = {
            "modularity": data["modularity"],
            "n_communities": data["n_communities"],
            "graph_nodes": data["graph_nodes"],
            "graph_edges": data["graph_edges"],
            "cut_ratio": q.get("cut_ratio"),
            "avg_conductance": q.get("avg_conductance"),
            "werewolf_community": data["werewolf_community"],
        }

    for region, data in gn_results.items():
        q = data.get("quality", {})
        summary["girvan_newman"][region] = {
            "modularity": data["modularity"],
            "n_communities": data["n_communities"],
            "graph_nodes": data["graph_nodes"],
            "graph_edges": data["graph_edges"],
            "cut_ratio": q.get("cut_ratio"),
            "avg_conductance": q.get("avg_conductance"),
            "werewolf_community": data["werewolf_community"],
        }

    for region, data in bigclam_results.items():
        q = data.get("quality", {})
        summary["bigclam"][region] = {
            "modularity": None,
            "n_communities": data["n_communities"],
            "graph_nodes": data["graph_nodes"],
            "graph_edges": data["graph_edges"],
            "cut_ratio": q.get("cut_ratio"),
            "avg_conductance": q.get("avg_conductance"),
            "overlap_percentage": q.get("overlap_percentage"),
            "werewolf_communities": data.get("werewolf_communities"),
        }

    summary_out = OUTPUT_DIR / "summary.json"
    with open(summary_out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  Summary saved: {summary_out}")
    print(f"{'='*60}")

    if summary["louvain"]:
        print("\n  Louvain:")
        for region, s in summary["louvain"].items():
            print(f"    {region:15s}  Q={s['modularity']:.4f}  "
                  f"communities={s['n_communities']:3d}  "
                  f"cut={s['cut_ratio']:.3f}  "
                  f"cond={s['avg_conductance']:.3f}  "
                  f"werewolf={s['werewolf_community']}")

    if summary["girvan_newman"]:
        print("\n  Girvan-Newman:")
        for region, s in summary["girvan_newman"].items():
            print(f"    {region:15s}  Q={s['modularity']:.4f}  "
                  f"communities={s['n_communities']:3d}  "
                  f"cut={s['cut_ratio']:.3f}  "
                  f"cond={s['avg_conductance']:.3f}  "
                  f"werewolf={s['werewolf_community']}")

    if summary["bigclam"]:
        print("\n  BigCLAM (overlapping):")
        for region, s in summary["bigclam"].items():
            print(f"    {region:15s}  "
                  f"communities={s['n_communities']:3d}  "
                  f"cut={s['cut_ratio']:.3f}  "
                  f"cond={s['avg_conductance']:.3f}  "
                  f"overlap={s['overlap_percentage']:.1f}%  "
                  f"werewolf={s['werewolf_communities']}")


if __name__ == "__main__":
    main()
