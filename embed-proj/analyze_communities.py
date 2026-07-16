#!/usr/bin/env python3
"""Analyze Louvain communities: region entropy, heatmap, graph visualizations.

Core research question: do stories cluster by LANGUAGE or by THEME?

Usage:
    python analyze_communities.py

Output:
    output/region_entropy.png               — bar chart: entropy per community
    output/region_community_heatmap.png     — rows=communities, cols=regions
    output/graph_colored_by_region.png      — semantic graph, nodes colored by region
    output/graph_colored_by_community.png   — semantic graph, nodes colored by community
    output/community_classification.csv     — each community classified as theme/language/mixed
    output/analysis_report.txt              — human-readable summary
"""

import json
import math
import csv
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colormaps
from matplotlib.patches import Patch

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


# ── Data loaders ──────────────────────────────────────────────────────────────

def load_graph() -> nx.Graph:
    G = nx.read_gml(OUTPUT_DIR / "semantic_graph.gml")
    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


def load_partition() -> dict[str, int]:
    raw = json.loads((OUTPUT_DIR / "louvain_partition.json").read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items()}


def load_regions() -> dict[str, str]:
    ids = json.loads((OUTPUT_DIR / "story_ids.json").read_text(encoding="utf-8"))
    regions = json.loads((OUTPUT_DIR / "story_regions.json").read_text(encoding="utf-8"))
    return dict(zip(ids, regions))


# ── Analysis functions ────────────────────────────────────────────────────────

def compute_community_region_stats(
    partition: dict[str, int],
    id_to_region: dict[str, str],
) -> tuple[list[dict], list[str]]:
    """For each community, compute region distribution and entropy."""
    comm_regions: dict[int, list[str]] = defaultdict(list)
    for node, comm in partition.items():
        comm_regions[comm].append(id_to_region.get(node, "unknown"))

    all_regions = sorted(set(id_to_region.values()))
    stats = []

    for comm_id in sorted(comm_regions, key=lambda c: -len(comm_regions[c])):
        members = comm_regions[comm_id]
        n = len(members)
        counts = Counter(members)
        total_entropy = 0.0
        region_fracs = {}

        for r in all_regions:
            p = counts.get(r, 0) / n
            region_fracs[r] = round(p, 4)
            if p > 0:
                total_entropy -= p * math.log2(p)

        active_regions = sum(1 for v in counts.values() if v > 0)
        max_entropy = math.log2(active_regions) if active_regions > 1 else 0
        normalized_entropy = total_entropy / max_entropy if max_entropy > 0 else 0

        dominant_region = counts.most_common(1)[0]

        if normalized_entropy > 0.7:
            classification = "CROSS-LINGUAL (theme)"
        elif normalized_entropy < 0.3:
            classification = "SINGLE-REGION (language)"
        else:
            classification = "MIXED"

        stats.append({
            "community": comm_id,
            "size": n,
            "region_fracs": region_fracs,
            "region_counts": dict(counts),
            "entropy": round(total_entropy, 4),
            "normalized_entropy": round(normalized_entropy, 4),
            "dominant_region": dominant_region[0],
            "dominant_frac": round(dominant_region[1] / n, 3),
            "classification": classification,
        })

    return stats, all_regions


def plot_region_entropy(stats: list[dict], all_regions: list[str]):
    """Bar chart: normalized entropy per community, colored by dominant region."""
    region_colors = {
        "mecklenburg": "#e41a1c",
        "denmark": "#377eb8",
        "iceland": "#4daf4a",
        "netherlands": "#984ea3",
    }

    fig, ax = plt.subplots(figsize=(16, 6))

    entropies = [s["normalized_entropy"] for s in stats]
    colors = [region_colors.get(s["dominant_region"], "#999999") for s in stats]

    ax.bar(range(len(stats)), entropies, color=colors, edgecolor="white", linewidth=0.3)
    ax.axhline(y=0.7, color="green", linestyle="--", alpha=0.5, label="Cross-lingual threshold (0.7)")
    ax.axhline(y=0.3, color="red", linestyle="--", alpha=0.5, label="Single-region threshold (0.3)")

    ax.set_xlabel("Community (sorted by size)", fontsize=11)
    ax.set_ylabel("Normalized Region Entropy", fontsize=11)
    ax.set_title("Region Entropy per Community\n(high = cross-lingual, low = single-region)", fontsize=13)
    ax.set_ylim(0, 1.05)

    legend_elements = [Patch(facecolor=c, label=r) for r, c in region_colors.items() if r in all_regions]
    legend_elements += [
        plt.Line2D([0], [0], color="green", linestyle="--", label="Cross-lingual (0.7)"),
        plt.Line2D([0], [0], color="red", linestyle="--", label="Single-region (0.3)"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=9)

    plt.tight_layout()
    out = OUTPUT_DIR / "region_entropy.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Saved: {out}")


def plot_heatmap(stats: list[dict], all_regions: list[str]):
    """Heatmap: rows=communities, columns=regions, cell=fraction."""
    top_n = min(30, len(stats))
    top_stats = stats[:top_n]

    data = np.array([[s["region_fracs"].get(r, 0) for r in all_regions] for s in top_stats])

    fig, ax = plt.subplots(figsize=(max(8, len(all_regions) * 2), max(10, top_n * 0.5)))
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)

    ax.set_xticks(range(len(all_regions)))
    ax.set_xticklabels(all_regions, fontsize=11)
    ax.set_yticks(range(top_n))
    ax.set_yticklabels([f"C{s['community']} (n={s['size']})" for s in top_stats], fontsize=9)

    for i in range(top_n):
        for j in range(len(all_regions)):
            val = data[i, j]
            if val > 0.01:
                color = "white" if val > 0.5 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8, color=color)

    plt.colorbar(im, ax=ax, label="Fraction of community members from region")
    ax.set_title("Region x Community Heatmap\n(top communities by size)", fontsize=13)
    plt.tight_layout()
    out = OUTPUT_DIR / "region_community_heatmap.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Saved: {out}")


def plot_graph(G: nx.Graph, partition: dict[str, int], id_to_region: dict[str, str], color_by: str):
    """Visualize the graph colored by region or community."""
    region_colors = {
        "mecklenburg": "#e41a1c",
        "denmark": "#377eb8",
        "iceland": "#4daf4a",
        "netherlands": "#984ea3",
    }

    nodes = list(G.nodes())
    n = len(nodes)

    if color_by == "region":
        colors = [region_colors.get(id_to_region.get(nd, "unknown"), "#999999") for nd in nodes]
        title = f"Semantic Graph — Colored by Region (n={n})"
    else:
        cmap = colormaps.get_cmap("tab20")
        colors = [cmap(partition.get(nd, 0) % 20) for nd in nodes]
        title = f"Semantic Graph — Colored by Community (n={n})"

    if n > 2000:
        rng = np.random.default_rng(42)
        sample_idx = rng.choice(n, size=min(2000, n), replace=False)
        sample_nodes = [nodes[i] for i in sample_idx]
        subG = G.subgraph(sample_nodes).copy()
        sample_colors = [colors[i] for i in sample_idx]
        colors_to_draw = sample_colors
        title += " (sampled 2000)"
    else:
        subG = G
        colors_to_draw = colors

    pos = nx.spring_layout(subG, k=0.3, seed=42)

    plt.figure(figsize=(14, 10))
    nx.draw_networkx_edges(subG, pos, alpha=0.05, width=0.2)
    nx.draw_networkx_nodes(subG, pos, node_color=colors_to_draw, node_size=8, edgecolors="none")

    plt.title(title, fontsize=13)
    plt.axis("off")
    plt.tight_layout()

    out = OUTPUT_DIR / f"graph_colored_by_{color_by}.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Saved: {out}")


def save_classification(stats: list[dict], all_regions: list[str]):
    """Save community classification to CSV and text report."""
    csv_path = OUTPUT_DIR / "community_classification.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["community", "size", "classification", "dominant_region",
                          "dominant_frac", "normalized_entropy"] + all_regions)
        for s in stats:
            row = [s["community"], s["size"], s["classification"], s["dominant_region"],
                   s["dominant_frac"], s["normalized_entropy"]]
            row += [s["region_fracs"].get(r, 0) for r in all_regions]
            writer.writerow(row)

    report_lines = ["=" * 70, "EMBEDDING-BASED COMMUNITY ANALYSIS REPORT", "=" * 70, ""]

    cross_lingual = [s for s in stats if "CROSS-LINGUAL" in s["classification"]]
    single_region = [s for s in stats if "SINGLE-REGION" in s["classification"]]
    mixed = [s for s in stats if s["classification"] == "MIXED"]

    report_lines.append(f"Total communities: {len(stats)}")
    report_lines.append(f"  Cross-lingual (theme):   {len(cross_lingual)}")
    report_lines.append(f"  Single-region (language): {len(single_region)}")
    report_lines.append(f"  Mixed:                    {len(mixed)}")
    report_lines.append("")

    report_lines.append("-- Cross-lingual communities (stories from multiple regions) --")
    for s in cross_lingual:
        report_lines.append(f"  Community {s['community']} (n={s['size']}): "
                            f"{s['region_counts']}  entropy={s['normalized_entropy']:.3f}")

    report_lines.append("")
    report_lines.append("-- Single-region communities (stories from one region only) --")
    for s in single_region[:10]:
        report_lines.append(f"  Community {s['community']} (n={s['size']}): "
                            f"{s['dominant_region']} ({s['dominant_frac']:.1%})")

    report_lines.append("")
    report_lines.append("=" * 70)
    report_lines.append("ANSWER TO RESEARCH QUESTION:")
    report_lines.append("=" * 70)
    if len(cross_lingual) > len(single_region):
        report_lines.append("-> Stories cluster primarily by THEME (cross-lingual communities dominate).")
        report_lines.append("   The embedding model captures semantic similarity that transcends language.")
    elif len(single_region) > len(cross_lingual):
        report_lines.append("-> Stories cluster primarily by LANGUAGE/REGION (single-region communities dominate).")
        report_lines.append("   Linguistic features dominate the embedding similarity.")
    else:
        report_lines.append("-> MIXED results: roughly equal numbers of theme-based and language-based communities.")
        report_lines.append("   Both factors influence story similarity.")

    report_text = "\n".join(report_lines)
    print(f"\n{report_text}")

    (OUTPUT_DIR / "analysis_report.txt").write_text(report_text, encoding="utf-8")
    print(f"\nSaved:")
    print(f"  {OUTPUT_DIR / 'analysis_report.txt'}")
    print(f"  {csv_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== Semantic Community Analysis ===\n")

    G = load_graph()
    partition = load_partition()
    id_to_region = load_regions()

    print(f"Partition: {len(set(partition.values()))} communities\n")

    print("Computing region entropy per community...")
    stats, all_regions = compute_community_region_stats(partition, id_to_region)

    print("\nGenerating visualizations...")
    plot_region_entropy(stats, all_regions)
    plot_heatmap(stats, all_regions)
    plot_graph(G, partition, id_to_region, color_by="region")
    plot_graph(G, partition, id_to_region, color_by="community")

    save_classification(stats, all_regions)


if __name__ == "__main__":
    main()
