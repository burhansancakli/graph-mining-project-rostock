"""
Runs Louvain + Girvan-Newman + BigCLAM on one dataset and compares them,
now with actual numbers behind the comparison:

  - Adjusted Rand Index / Normalized Mutual Information between Louvain and
    GN (the two hard-partitioning algorithms -- BigCLAM is overlapping, so
    it isn't directly comparable with ARI/NMI, which assume one label per
    node).
  - A Jaccard best-match table between Louvain and GN communities, flagging
    which communities have no real counterpart in the other algorithm
    ("special clusters not found by others").

Output (all under outputs/<dataset>/):
  - console table: algorithm | modularity Q | # communities | Werewolf community
  - comparison_<dataset>.png       -- bar chart of Q and #communities
  - werewolf_comparison_<dataset>.txt -- Werewolf cluster side-by-side
  - partition_agreement_<dataset>.txt -- ARI/NMI + Jaccard unique-cluster report
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from louvain_analysis import run_louvain
from girvan_newman_analysis import run_girvan_newman
from bigclam_analysis import run_bigclam
from graph_utils import DATASET, PROJECT_ROOT
from metrics import compare_partitions, jaccard_best_matches, print_unique_clusters_report

sys.path.insert(0, str(Path(__file__).resolve().parent))
from viz.export_data import export_comparison_json

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def _count_communities(memberships):
    ids = set()
    for comms in memberships.values():
        ids.update(int(c) for c in comms)
    return len(ids)


def compare(dataset: str = None, louvain_resolution: float = 1.0):
    ds = dataset or DATASET
    out_dir = OUTPUT_DIR / ds
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"RUNNING ALL 3 ALGORITHMS -- dataset = {ds}")
    print("=" * 60)

    louvain_res = run_louvain(ds, export_json=False, resolution=louvain_resolution)
    gn_res = run_girvan_newman(ds)
    bigclam_res = run_bigclam(ds)

    results = [louvain_res, gn_res, bigclam_res]
    displayed_community_counts = []

    print("\n" + "=" * 60)
    print(f"  COMPARISON SUMMARY -- {ds}")
    print("=" * 60)
    print(f"  {'Algorithm':<20} {'Modularity Q':>14} {'# Communities':>15} {'Werewolf comm':>14}")
    print(f"  {'-'*20} {'-'*14} {'-'*15} {'-'*14}")
    for r in results:
        q = f"{r['modularity']:.4f}" if r["modularity"] is not None else "N/A (overlap)"
        ww = str(r.get("werewolf_community", "N/A"))
        count = _count_communities(r["memberships"]) if r["algorithm"] == "BigCLAM" else r["n_communities"]
        displayed_community_counts.append(count)
        print(f"  {r['algorithm']:<20} {q:>14} {count:>15} {ww:>14}")
    print("=" * 60)

    overlap = bigclam_res.get("overlap_count", 0)
    total = len(bigclam_res.get("memberships", {}))
    if total > 0:
        print(f"\n  BigCLAM overlap: {overlap}/{total} nodes "
              f"({100 * overlap / total:.1f}%) belong to more than one community.")
        print("  -> These are thematic 'bridge' keywords.")
        print("  -> Louvain/GN force each of these into a single group -- BigCLAM shows the nuance.")

    # ── Quantitative agreement: Louvain vs GN (the professor's main ask) ─────
    agreement = compare_partitions(louvain_res["partition"], gn_res["partition"],
                                    name_a="Louvain", name_b="Girvan-Newman")
    jaccard_rows = jaccard_best_matches(louvain_res["partition"], gn_res["partition"],
                                        louvain_res["keyword_text"], degree=louvain_res["degree"])
    print_unique_clusters_report(jaccard_rows, "Louvain", "Girvan-Newman")

    with open(out_dir / f"partition_agreement_{ds}.txt", "w", encoding="utf-8") as f:
        f.write(f"Quantitative partition agreement -- {ds}\n")
        f.write("=" * 60 + "\n\n")
        f.write("Louvain vs Girvan-Newman\n")
        f.write(f"  Shared nodes: {agreement['n_common_nodes']}\n")
        if agreement["ari"] is not None:
            f.write(f"  Adjusted Rand Index: {agreement['ari']:.4f}  (1.0 = identical grouping, ~0 = random)\n")
            f.write(f"  Normalized Mutual Information: {agreement['nmi']:.4f}\n")
        f.write("\nJaccard best-match table (Louvain community -> closest Girvan-Newman community)\n")
        f.write("-" * 60 + "\n")
        for row in jaccard_rows:
            flag = "  <-- no good match in GN (algorithm-specific)" if row["is_unique"] else ""
            f.write(f"  Louvain comm {row['community']:>3} (size={row['size']:>4}) "
                    f"best match = GN comm {row['best_match_in_b']} "
                    f"(Jaccard={row['jaccard']}){flag}\n")
    print(f"\n  Saved partition agreement report: partition_agreement_{ds}.txt")

    # ── Combined JSON export for network_explorer.html (both algorithms on
    #    the same node/edge set, so switching algorithm in the viewer only
    #    recolors nodes instead of reshuffling the whole layout) ─────────────
    export_comparison_json(
        ds, louvain_res["G"], louvain_res["keyword_text"], louvain_res["degree"],
        louvain_res, gn_res=gn_res, out_path=out_dir / f"graph_export_{ds}.json",
    )

    # ── Bar chart: modularity Q + #communities ────────────────────────────────
    algs = [r["algorithm"] for r in results]
    qs = [r["modularity"] if r["modularity"] is not None else 0.0 for r in results]
    ns = displayed_community_counts

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    bars = axes[0].bar(algs, qs, color=["#4C72B0", "#DD8452", "#55A868"], edgecolor="black", width=0.5)
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Modularity Q")
    axes[0].set_title(f"Modularity Q comparison -- {ds}")
    for bar, q in zip(bars, qs):
        label = f"{q:.3f}" if q > 0 else "N/A"
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                     label, ha="center", va="bottom", fontsize=11, fontweight="bold")

    bars2 = axes[1].bar(algs, ns, color=["#4C72B0", "#DD8452", "#55A868"], edgecolor="black", width=0.5)
    axes[1].set_ylabel("Number of communities")
    axes[1].set_title(f"Number of communities -- {ds}")
    for bar, n in zip(bars2, ns):
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                     str(n), ha="center", va="bottom", fontsize=11, fontweight="bold")

    plt.tight_layout()
    out = out_dir / f"comparison_{ds}.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"\n  Saved chart: {out}")

    with open(out_dir / f"werewolf_comparison_{ds}.txt", "w", encoding="utf-8") as f:
        f.write(f"Werewolf cluster comparison -- {ds}\n")
        f.write("=" * 60 + "\n\n")
        for r in results:
            f.write(f"Algorithm: {r['algorithm']}\n")
            ww_comm = r.get("werewolf_community")
            if ww_comm is not None:
                entry = next((x for x in r.get("results", []) if x["community"] == ww_comm), None)
                if entry:
                    f.write(f"  Community {ww_comm} (size={entry['size']})\n")
                    f.write(f"  Top keywords: {', '.join(entry['top_keywords'])}\n")
            else:
                f.write("  Werewolf community not identified\n")
            f.write("\n")
    print(f"  Saved Werewolf comparison: werewolf_comparison_{ds}.txt")
    print("\nDone.")
    return results


if __name__ == "__main__":
    import sys
    compare(sys.argv[1] if len(sys.argv) > 1 else None)
