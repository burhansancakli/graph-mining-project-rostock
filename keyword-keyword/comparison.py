"""
comparison.py
Runs all 3 community detection algorithms and compares their results.

Output:
  - Console table: algorithm | modularity Q | # communities | Werewolf community
  - comparison_table.png  — bar chart comparing Q values
  - werewolf_comparison.txt — side-by-side Werewolf cluster from each algorithm
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from louvain_analysis import run_louvain
from girvan_newman_analysis import run_girvan_newman
from bigclam_analysis import run_bigclam
from graph_utils import DATASET


def _count_communities(memberships):
    community_ids = set()
    for comms in memberships.values():
        if isinstance(comms, (list, tuple, set)):
            community_ids.update(int(c) for c in comms)
        else:
            try:
                iter(comms)
            except TypeError:
                community_ids.add(int(comms))
            else:
                community_ids.update(int(c) for c in comms)
    return len(community_ids)


def compare():
    print("=" * 60)
    print("RUNNING ALL 3 ALGORITHMS — comparison.py")
    print("=" * 60)

    louvain_res  = run_louvain()
    gn_res       = run_girvan_newman()
    bigclam_res  = run_bigclam()

    results = [louvain_res, gn_res, bigclam_res]
    displayed_community_counts = []

    # ── Console comparison table ──────────────────────────────────────────────
    print("\n")
    print("=" * 60)
    print(f"  COMPARISON SUMMARY — {DATASET}")
    print("=" * 60)
    print(f"  {'Algorithm':<20} {'Modularity Q':>14} {'# Communities':>15} {'Werewolf comm':>14}")
    print(f"  {'-'*20} {'-'*14} {'-'*15} {'-'*14}")
    for r in results:
        q = f"{r['modularity']:.4f}" if r["modularity"] is not None else "N/A (overlap)"
        ww = str(r.get("werewolf_community", "N/A"))
        if r["algorithm"] == "BigCLAM":
            community_count = _count_communities(r.get("memberships", {}))
        else:
            community_count = r["n_communities"]
        displayed_community_counts.append(community_count)
        print(f"  {r['algorithm']:<20} {q:>14} {community_count:>15} {ww:>14}")
    print("=" * 60)

    # ── Notes on BigCLAM ─────────────────────────────────────────────────────
    overlap = bigclam_res.get("overlap_count", 0)
    total = len(bigclam_res.get("memberships", {}))
    if total > 0:
        print(f"\n  BigCLAM overlap: {overlap}/{total} nodes "
              f"({100 * overlap / total:.1f}%) belong to multiple communities.")
        print("  → These are thematic 'bridge' keywords (e.g. Wolf, transformation)")
        print("  → Louvain/GN force these into one group — BigCLAM shows the nuance.")
    # ── Bar chart: modularity Q ───────────────────────────────────────────────
    algs = [r["algorithm"] for r in results]
    qs   = [r["modularity"] if r["modularity"] is not None else 0.0 for r in results]
    ns   = [displayed_community_counts[i] for i, _ in enumerate(results)]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Q values
    bars = axes[0].bar(algs, qs, color=["#4C72B0", "#DD8452", "#55A868"], edgecolor="black", width=0.5)
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Modularity Q")
    axes[0].set_title(f"Modularity Q comparison — {DATASET}")
    for bar, q in zip(bars, qs):
        label = f"{q:.3f}" if q is not None and q > 0 else "N/A"
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                     label, ha="center", va="bottom", fontsize=11, fontweight="bold")

    # Number of communities
    bars2 = axes[1].bar(algs, ns, color=["#4C72B0", "#DD8452", "#55A868"], edgecolor="black", width=0.5)
    axes[1].set_ylabel("Number of communities")
    axes[1].set_title(f"Number of communities — {DATASET}")
    for bar, n in zip(bars2, ns):
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                     str(n), ha="center", va="bottom", fontsize=11, fontweight="bold")

    plt.tight_layout()
    out = f"comparison_{DATASET}.png"
    plt.savefig(out, dpi=150)
    print(f"\n  Saved chart: {out}")

    # ── Werewolf cluster side-by-side ─────────────────────────────────────────
    with open(f"werewolf_comparison_{DATASET}.txt", "w", encoding="utf-8") as f:
        f.write(f"Werewolf cluster comparison — {DATASET}\n")
        f.write("=" * 60 + "\n\n")
        for r in results:
            f.write(f"Algorithm: {r['algorithm']}\n")
            ww_comm = r.get("werewolf_community")
            if ww_comm is not None:
                comm_results = r.get("results", [])
                ww_entry = next((x for x in comm_results if x["community"] == ww_comm), None)
                if ww_entry:
                    f.write(f"  Community {ww_comm} (size={ww_entry['size']}):\n")
                    f.write(f"  Top keywords: {', '.join(ww_entry['top_keywords'])}\n")
            else:
                f.write("  Werewolf community not identified\n")
            f.write("\n")

    print(f"  Saved Werewolf comparison: werewolf_comparison_{DATASET}.txt")
    print("\nDone.")


if __name__ == "__main__":
    compare()