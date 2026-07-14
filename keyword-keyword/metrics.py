"""
  1. "Have some measures to compare the clusters to each other"
       - Adjusted Rand Index (ARI) and Normalized Mutual Information (NMI)
         between two full partitions (e.g. Louvain vs Girvan-Newman) — the
         standard way to say "these two algorithms agree/disagree by X".
       - A Jaccard best-match table: for every community in partition A,
         which community in partition B overlaps it most, and by how much.

  2. "Special clusters not found by others" — communities in one partition
     that have no good match in the other (best Jaccard overlap below a
     threshold) are flagged as algorithm-specific.

Implements the "singleton" idea:
  `zoom_excluding_anchor()` builds the induced subgraph of a community
  MINUS the anchor node itself and re-runs Louvain, so the anchor's own
  dominance doesn't hide the structure underneath it
"""

from collections import defaultdict

import community as community_louvain
import networkx as nx
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score


def partitions_to_common_labels(partition_a: dict, partition_b: dict):
    """
    Restricts both partitions to their shared nodes and returns two aligned
    label lists (needed by sklearn's ARI/NMI, which expect same-length
    label arrays over the same items).
    """
    common = sorted(set(partition_a) & set(partition_b))
    labels_a = [partition_a[n] for n in common]
    labels_b = [partition_b[n] for n in common]
    return common, labels_a, labels_b


def compare_partitions(partition_a: dict, partition_b: dict, name_a="A", name_b="B") -> dict:
    """
    Numeric agreement between two hard partitions (e.g. Louvain vs GN).
    ARI / NMI = 1.0 means identical grouping, ~0 means no better than random.
    """
    common, labels_a, labels_b = partitions_to_common_labels(partition_a, partition_b)
    if len(common) < 2:
        return {"n_common_nodes": len(common), "ari": None, "nmi": None}

    ari = adjusted_rand_score(labels_a, labels_b)
    nmi = normalized_mutual_info_score(labels_a, labels_b)
    print(f"\n-- Partition agreement: {name_a} vs {name_b} --")
    print(f"  Shared nodes       : {len(common)}")
    print(f"  Adjusted Rand Index: {ari:.4f}  (1.0 = identical, ~0 = random)")
    print(f"  Normalized Mutual Info: {nmi:.4f}")
    return {"n_common_nodes": len(common), "ari": ari, "nmi": nmi}


def _members_by_community(partition: dict) -> dict:
    out = defaultdict(set)
    for node, comm in partition.items():
        out[comm].add(node)
    return out


def jaccard_best_matches(partition_a: dict, partition_b: dict,
                          keyword_text: dict, degree: dict = None,
                          unique_threshold: float = 0.25) -> list:
    """
    For each community in A, finds its best-overlapping community in B
    (Jaccard similarity on member sets) and flags matches below
    `unique_threshold` as "no real counterpart in B" — these are the
    "special clusters not found by others".

    `degree` (optional, e.g. G.degree(weight="weight") as a dict) is used
    only to pick which example keywords to print for each community; if
    omitted, an arbitrary sample of members is shown instead.

    Returns a list of dicts, one per community in A, sorted by size desc:
      {community, size, top_keywords, best_match_in_b, jaccard, is_unique}
    """
    members_a = _members_by_community(partition_a)
    members_b = _members_by_community(partition_b)
    degree = degree or {}

    rows = []
    for comm_a, set_a in sorted(members_a.items(), key=lambda x: -len(x[1])):
        best_b, best_j = None, 0.0
        for comm_b, set_b in members_b.items():
            inter = len(set_a & set_b)
            if inter == 0:
                continue
            union = len(set_a | set_b)
            j = inter / union
            if j > best_j:
                best_j, best_b = j, comm_b

        example_nodes = sorted(set_a, key=lambda n: -degree.get(n, 0))[:6]
        top_keywords = [keyword_text.get(n, n) for n in example_nodes]
        rows.append({
            "community": comm_a,
            "size": len(set_a),
            "top_keywords": top_keywords,
            "best_match_in_b": best_b,
            "jaccard": round(best_j, 3),
            "is_unique": best_j < unique_threshold,
        })
    return rows


def print_unique_clusters_report(rows: list, name_a: str, name_b: str):
    unique_rows = [r for r in rows if r["is_unique"]]
    print(f"\n-- Communities in {name_a} with no real counterpart in {name_b} "
          f"(best Jaccard < threshold) --")
    if not unique_rows:
        print("  None — every community in A has a reasonable match in B.")
    for r in unique_rows:
        print(f"  Community {r['community']} (size={r['size']}, best Jaccard={r['jaccard']}): "
              f"{', '.join(r['top_keywords'])}")


def zoom_excluding_anchor(G: nx.Graph, keyword_text: dict, community_members: list,
                           anchor_id: str, random_state: int = 42) -> dict:
    """
    This reveals the sub-structure that the
    anchor's high degree otherwise dominates/masks.

    Returns the same shape as a normal Louvain result, plus which nodes were
    directly connected to the anchor (so you can see who "lost" their main
    hub).
    """
    if anchor_id not in community_members:
        raise ValueError(f"{anchor_id} is not a member of the given community")

    anchor_neighbors = set(G.neighbors(anchor_id)) & set(community_members)
    remaining = [n for n in community_members if n != anchor_id]
    H = G.subgraph(remaining).copy()

    if H.number_of_nodes() == 0:
        return {"n_nodes": 0, "note": "Nothing left after removing the anchor."}

    partition = community_louvain.best_partition(H, weight="weight", random_state=random_state)
    try:
        modularity = community_louvain.modularity(partition, H, weight="weight")
    except Exception:
        modularity = None

    degree = dict(H.degree(weight="weight"))
    comm_members = defaultdict(list)
    for node, comm in partition.items():
        comm_members[comm].append(node)

    results = []
    for comm, members in sorted(comm_members.items(), key=lambda x: -len(x[1])):
        top_nodes = sorted(members, key=lambda n: -degree.get(n, 0))[:8]
        results.append({
            "community": comm, "size": len(members),
            "top_keywords": [keyword_text.get(n, n) for n in top_nodes],
        })

    print(f"\n-- Zoom excluding anchor '{keyword_text.get(anchor_id, anchor_id)}' --")
    print(f"  Remaining subgraph: {H.number_of_nodes()} nodes, {H.number_of_edges()} edges")
    print(f"  Direct former neighbors of the anchor: {len(anchor_neighbors)}")
    if modularity is not None:
        print(f"  Modularity Q of what's left: {modularity:.4f} ({len(comm_members)} sub-communities)")
    for r in results:
        print(f"    Sub-community {r['community']:2d} (size={r['size']:3d}): {', '.join(r['top_keywords'])}")

    return {
        "anchor": anchor_id,
        "anchor_label": keyword_text.get(anchor_id, anchor_id),
        "n_nodes": H.number_of_nodes(),
        "n_edges": H.number_of_edges(),
        "n_anchor_neighbors": len(anchor_neighbors),
        "modularity": modularity,
        "n_sub_communities": len(comm_members),
        "results": results,
        "partition": partition,
    }
