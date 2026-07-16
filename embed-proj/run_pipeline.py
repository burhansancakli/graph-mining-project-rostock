#!/usr/bin/env python3
"""Run the full embedding pipeline end-to-end.

Steps:
  1. load_stories.py      — load & filter stories
  2. embed_stories.py     — embed with multilingual model
  3. build_graph.py       — build k-NN similarity graph
  4. run_louvain.py       — Louvain community detection
  5. analyze_communities.py — entropy analysis & visualizations
  6. compare_with_keywords.py — compare with keyword-based results

Usage:
    python run_pipeline.py
    python run_pipeline.py --skip-embed       # skip embedding (reuse existing .npy)
    python run_pipeline.py --min-similarity 0.4 --k 15   # custom graph params
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(script: str, args: list[str] | None = None):
    """Run a Python script as a subprocess."""
    cmd = [sys.executable, str(SCRIPT_DIR / script)] + (args or [])
    print(f"\n{'=' * 60}")
    print(f"  Running: {script}")
    print(f"{'=' * 60}\n")

    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"\nERROR: {script} failed (exit code {result.returncode})")
        sys.exit(1)

    print(f"\n  [{script}] done in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Run full embedding pipeline")
    parser.add_argument("--skip-load", action="store_true", help="Skip step 1 (load_stories)")
    parser.add_argument("--skip-embed", action="store_true", help="Skip step 2 (embed_stories)")
    parser.add_argument("--skip-graph", action="store_true", help="Skip step 3 (build_graph)")
    parser.add_argument("--skip-louvain", action="store_true", help="Skip step 4 (run_louvain)")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip step 5 (analyze_communities)")
    parser.add_argument("--skip-compare", action="store_true", help="Skip step 6 (compare_with_keywords)")

    parser.add_argument("--min-words", type=int, default=20)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--min-similarity", type=float, default=0.3)
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    args = parser.parse_args()

    t_total = time.time()

    if not args.skip_load:
        run_script("load_stories.py", ["--min-words", str(args.min_words)])

    if not args.skip_embed:
        run_script("embed_stories.py", ["--model", args.model])

    if not args.skip_graph:
        run_script("build_graph.py", ["--k", str(args.k), "--min-similarity", str(args.min_similarity)])

    if not args.skip_louvain:
        run_script("run_louvain.py", ["--resolution", str(args.resolution)])

    if not args.skip_analysis:
        run_script("analyze_communities.py")

    if not args.skip_compare:
        run_script("compare_with_keywords.py")

    print(f"\n{'=' * 60}")
    print(f"  FULL PIPELINE COMPLETE — {time.time() - t_total:.1f}s total")
    print(f"  All outputs in: {SCRIPT_DIR / 'output'}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
