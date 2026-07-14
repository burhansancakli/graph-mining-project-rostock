"""
Builds the JSON that network_explorer.html reads. Used by both
louvain_analysis.py (Louvain-only, when run standalone) and comparison.py
(Louvain + Girvan-Newman together, so the viewer can switch between them).

Why one shared node/edge set for both algorithms:
  Louvain runs on the whole connected graph; Girvan-Newman only runs on a
  smaller, weight-filtered subgraph (it's too slow otherwise -- see
  girvan_newman_analysis.py). If we exported each algorithm's own subgraph
  separately, switching between them in the viewer would reshuffle the
  entire layout and defeat the point of comparing them. Instead we pick ONE
  shared set of nodes (the top-degree nodes of the full graph) and, for each
  node, attach whichever community label each algorithm assigned to it (or
  null if that node fell outside Girvan-Newman's filtered subgraph). Same
  layout, same nodes -- only the coloring changes when you switch algorithm.
"""

import json


def export_comparison_json(dataset: str, G, keyword_text: dict, degree: dict,
                            louvain_res: dict, gn_res: dict = None,
                            out_path=None, max_nodes: int = 400):
    """
    louvain_res: dict returned by louvain_analysis.run_louvain() (required)
    gn_res: dict returned by girvan_newman_analysis.run_girvan_newman(), or
            None if only Louvain has been run for this dataset so far.
    """
    top_nodes = sorted(G.nodes(), key=lambda n: -degree.get(n, 0))[:max_nodes]
    sub = G.subgraph(top_nodes)

    louvain_partition = louvain_res["partition"]
    gn_partition = gn_res["partition"] if gn_res else {}

    nodes_out = []
    for n in sub.nodes():
        nodes_out.append({
            "id": n,
            "label": keyword_text.get(n, n),
            "degree": round(degree.get(n, 0), 2),
            "regions": sub.nodes[n].get("regions", []),
            "cross_region": sub.nodes[n].get("is_cross_region_concept", False),
            "document_frequency_ratio": sub.nodes[n].get("document_frequency_ratio", 0.0),
            "communities": {
                "louvain": louvain_partition.get(n),
                "girvan_newman": gn_partition.get(n) if gn_res else None,
            },
        })

    edges_out = [
        {"source": u, "target": v, "weight": data.get("weight", 1)}
        for u, v, data in sub.edges(data=True)
    ]

    def _top_keywords_overall(n=10):
        return [keyword_text.get(n_, n_) for n_ in
                sorted(G.nodes(), key=lambda x: -degree.get(x, 0))[:n]]

    payload = {
        "dataset": dataset,
        "total_graph_nodes": G.number_of_nodes(),
        "total_graph_edges": G.number_of_edges(),
        "shown_nodes": len(nodes_out),
        "top_keywords_overall": _top_keywords_overall(),
        "algorithms": {
            "louvain": {
                "available": True,
                "modularity": louvain_res["modularity"],
                "n_communities": louvain_res["n_communities"],
            },
            "girvan_newman": {
                "available": gn_res is not None,
                "modularity": gn_res["modularity"] if gn_res else None,
                "n_communities": gn_res["n_communities"] if gn_res else None,
            },
        },
        "nodes": nodes_out,
        "edges": edges_out,
    }

    if out_path is not None:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        print(f"  Saved JSON export for the interactive viewer: {out_path} "
              f"({len(nodes_out)}/{G.number_of_nodes()} nodes shown, "
              f"algorithms: louvain{'+girvan_newman' if gn_res else ''})")

    return payload
