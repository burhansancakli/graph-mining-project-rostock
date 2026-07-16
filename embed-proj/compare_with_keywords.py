#!/usr/bin/env python3
"""Compare embedding-based community detection with keyword-based results.

Loads Louvain results from both embed-proj/output/ and keyword-keyword/output/
and produces a side-by-side comparison.

Usage:
    python compare_with_keywords.py
    python compare_with_keywords.py --keyword-output-dir ../keyword-keyword/output

Output:
    output/comparison_report.md     — formatted comparison report
    output/comparison_summary.json  — machine-readable comparison data
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
KEYWORD_OUTPUT_DIR_DEFAULT = Path(__file__).resolve().parent.parent / "keyword-keyword" / "output"


def load_embed_results() -> dict:
    """Load embedding-based Louvain results."""
    summary_path = OUTPUT_DIR / "louvain_summary.json"
    if not summary_path.exists():
        print("ERROR: embed-proj/output/louvain_summary.json not found. Run pipeline first.")
        raise SystemExit(1)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    partition = json.loads((OUTPUT_DIR / "louvain_partition.json").read_text(encoding="utf-8"))

    return {"summary": summary, "partition": partition}


def load_keyword_results(keyword_dir: Path) -> dict:
    """Load keyword-based Louvain results (tries all region files)."""
    results = {}
    for region in ["mecklenburg", "denmark", "iceland", "netherlands", "merged"]:
        path = keyword_dir / f"louvain_{region}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            results[region] = data
            print(f"  Loaded keyword results for {region}")

    if not results:
        print(f"  WARNING: No keyword Louvain results found in {keyword_dir}")
        print(f"  (This is expected if you haven't run keyword analysis yet)")

    return results


def compare_modularity(embed_summary: dict, keyword_results: dict) -> list[dict]:
    """Compare modularity scores."""
    comparison = []

    # Embedding-based
    comparison.append({
        "method": "Embedding (semantic graph)",
        "modularity": embed_summary["modularity"],
        "n_communities": embed_summary["n_communities"],
        "n_nodes": embed_summary["n_nodes"],
        "n_edges": embed_summary["n_edges"],
        "graph_type": "Story-to-story (k-NN, cosine similarity)",
    })

    # Keyword-based (per region)
    for region, data in keyword_results.items():
        comparison.append({
            "method": f"Keyword co-occurrence ({region})",
            "modularity": data.get("modularity"),
            "n_communities": data.get("n_communities"),
            "n_nodes": data.get("n_nodes", "N/A"),
            "n_edges": data.get("n_edges", "N/A"),
            "graph_type": "Keyword-to-keyword (co-occurrence)",
        })

    return comparison


def find_hidden_connections(embed_partition: dict, id_to_region: dict, stories: dict) -> list[dict]:
    """Find semantically similar story pairs that share no keywords."""
    # Group stories by their embedding community
    comm_stories: dict[int, list[str]] = defaultdict(list)
    for story_id, comm in embed_partition.items():
        comm_stories[comm].append(story_id)

    hidden = []
    for comm_id, story_ids in comm_stories.items():
        if len(story_ids) < 2:
            continue

        # Check pairs within the same embedding community
        for i in range(min(len(story_ids), 50)):  # limit for performance
            for j in range(i + 1, min(len(story_ids), 50)):
                s1 = stories.get(story_ids[i], {})
                s2 = stories.get(story_ids[j], {})
                kw1 = set(s1.get("keywords", []))
                kw2 = set(s2.get("keywords", []))

                shared = kw1 & kw2
                if not shared and s1.get("region") != s2.get("region"):
                    hidden.append({
                        "story_1": story_ids[i],
                        "story_2": story_ids[j],
                        "region_1": s1.get("region"),
                        "region_2": s2.get("region"),
                        "community": comm_id,
                        "keywords_1": list(kw1)[:5],
                        "keywords_2": list(kw2)[:5],
                    })

    return hidden[:20]  # Top 20


def generate_report(comparison: list[dict], hidden: list[dict], embed_summary: dict) -> str:
    """Generate a markdown comparison report."""
    lines = [
        "# Embedding vs Keyword Community Detection: Comparison Report\n",
        "## Method Comparison\n",
        "| Method | Modularity Q | # Communities | Graph Size |",
        "|--------|-------------|---------------|------------|",
    ]

    for c in comparison:
        q = f"{c['modularity']:.4f}" if c["modularity"] is not None else "N/A"
        lines.append(f"| {c['method']} | {q} | {c['n_communities']} | {c['n_nodes']} nodes / {c['n_edges']} edges |")

    lines.extend([
        "\n## Key Differences\n",
        "| Aspect | Keyword Graph | Embedding Graph |",
        "|--------|--------------|-----------------|",
        "| **Nodes** | Keywords (~2,400) | Stories (~10,000+) |",
        "| **Edges** | Co-occurrence count | Cosine similarity (k-NN) |",
        "| **Captures** | Thematic keyword groups | Semantic text similarity |",
        "| **Language** | Depends on keyword language | Multilingual (same model for all) |",
        "",
        "## What Each Approach Finds\n",
        "### Keyword approach",
        "- Groups keywords that frequently appear together in stories",
        "- Communities represent thematic motif groups (Werewolf, Hexe, water spirits...)",
        "- Each region has its own keyword language",
        "",
        "### Embedding approach",
        "- Groups stories with similar narrative content",
        "- Communities represent groups of stories told in similar ways",
        "- Cross-lingual: a German and Danish werewolf story can end up in the same community",
        "",
    ])

    if hidden:
        lines.append("## Hidden Connections Found by Embedding Model\n")
        lines.append("Story pairs that are semantically similar but share NO keywords:\n")
        lines.append("| Story 1 | Region | Story 2 | Region | Community |")
        lines.append("|---------|--------|---------|--------|-----------|")
        for h in hidden[:10]:
            lines.append(f"| {h['story_1'][:30]} | {h['region_1']} | "
                         f"{h['story_2'][:30]} | {h['region_2']} | {h['community']} |")
        lines.append(f"\n({len(hidden)} total hidden connections found)\n")

    # Overall assessment
    embed_q = embed_summary.get("modularity", 0)
    lines.extend([
        "## Overall Assessment\n",
        f"- Embedding graph modularity Q = {embed_q:.4f}",
        "- (Higher Q = clearer community structure)\n",
    ])

    if embed_q > 0.3:
        lines.append("**Strong result**: The embedding model found meaningful thematic clusters "
                      "that transcend language barriers.")
    elif embed_q > 0.1:
        lines.append("**Moderate result**: Some thematic clustering is visible, but language "
                      "effects also play a role.")
    else:
        lines.append("**Weak result**: The embedding model struggles to separate communities. "
                      "Short text length (~72 words) may be a limiting factor.")

    lines.append("\n---\n*Generated by compare_with_keywords.py*")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compare embedding vs keyword community detection")
    parser.add_argument("--keyword-output-dir", type=Path, default=KEYWORD_OUTPUT_DIR_DEFAULT,
                        help="Path to keyword-keyword/output directory")
    args = parser.parse_args()

    print("=== Embedding vs Keyword Comparison ===\n")

    # Load results
    print("Loading embedding results...")
    embed = load_embed_results()
    embed_summary = embed["summary"]
    embed_partition = embed["partition"]
    print(f"  Embedding: Q={embed_summary['modularity']:.4f}, {embed_summary['n_communities']} communities")

    print(f"\nLoading keyword results from {args.keyword_output_dir}...")
    keyword_results = load_keyword_results(args.keyword_output_dir)

    # Load stories for hidden connection analysis
    stories_list = json.loads((OUTPUT_DIR / "filtered_stories.json").read_text(encoding="utf-8"))
    stories = {s["id"]: s for s in stories_list}

    id_to_region = {}
    ids = json.loads((OUTPUT_DIR / "story_ids.json").read_text(encoding="utf-8"))
    regions = json.loads((OUTPUT_DIR / "story_regions.json").read_text(encoding="utf-8"))
    id_to_region = dict(zip(ids, regions))

    # Comparison
    comparison = compare_modularity(embed_summary, keyword_results)

    print("\n── Modularity Comparison ──")
    for c in comparison:
        q = f"{c['modularity']:.4f}" if c["modularity"] is not None else "N/A"
        print(f"  {c['method']:<45} Q={q:>8}  {c['n_communities']:>4} communities")

    # Hidden connections
    print("\nFinding hidden connections (cross-lingual pairs sharing no keywords)...")
    hidden = find_hidden_connections(embed_partition, id_to_region, stories)
    print(f"  Found {len(hidden)} hidden cross-lingual connections")

    # Generate report
    report = generate_report(comparison, hidden, embed_summary)

    (OUTPUT_DIR / "comparison_report.md").write_text(report, encoding="utf-8")
    (OUTPUT_DIR / "comparison_summary.json").write_text(
        json.dumps({
            "comparison": comparison,
            "hidden_connections_count": len(hidden),
            "hidden_connections": hidden,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nSaved:")
    print(f"  {OUTPUT_DIR / 'comparison_report.md'}")
    print(f"  {OUTPUT_DIR / 'comparison_summary.json'}")


if __name__ == "__main__":
    main()
