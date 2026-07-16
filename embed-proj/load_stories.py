#!/usr/bin/env python3
"""Load all story JSONs, filter by minimum word count, output summary stats.

Usage:
    python load_stories.py
    python load_stories.py --min-words 15
    python --min-words 20

Output:
    output/filtered_stories.json  — list of {id, region, text, keywords, language}
    output/load_stats.json        — per-region counts and word stats
"""

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORY_DIR = BASE_DIR / "output" / "wossidia_story_jsons"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def load_all_stories(min_words: int) -> list[dict]:
    """Load and filter story JSONs."""
    json_files = sorted(STORY_DIR.glob("*.json"))
    if not json_files:
        print(f"No JSON files found in {STORY_DIR}")
        raise SystemExit(1)

    print(f"Found {len(json_files)} JSON files in {STORY_DIR}")

    stories = []
    skipped_short = 0
    skipped_no_text = 0

    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ERROR reading {f.name}: {e}")
            continue

        text = (data.get("description") or "").strip()
        word_count = len(text.split())

        if not text:
            skipped_no_text += 1
            continue
        if word_count < min_words:
            skipped_short += 1
            continue

        stories.append({
            "id": data.get("id", f.stem),
            "region": data.get("region", "unknown"),
            "text": text,
            "keywords": data.get("keywords", []),
            "language": data.get("topic_language", "unknown"),
        })

    print(f"  Kept: {len(stories)} stories (≥{min_words} words)")
    print(f"  Skipped: {skipped_short} too short, {skipped_no_text} empty")

    return stories


def print_stats(stories: list[dict]) -> dict:
    """Print and return per-region statistics."""
    by_region: dict[str, list[dict]] = defaultdict(list)
    for s in stories:
        by_region[s["region"]].append(s)

    stats = {}
    print(f"\n{'Region':<15} {'Stories':>8} {'Avg words':>10} {'Median':>8} {'Languages'}")
    print("-" * 60)

    for region in sorted(by_region):
        region_stories = by_region[region]
        lengths = [len(s["text"].split()) for s in region_stories]
        langs = Counter(s["language"] for s in region_stories)

        stats[region] = {
            "count": len(region_stories),
            "avg_words": round(statistics.mean(lengths), 1),
            "median_words": round(statistics.median(lengths), 1),
            "languages": dict(langs),
        }

        lang_str = ", ".join(f"{k}:{v}" for k, v in sorted(langs.items()))
        print(f"{region:<15} {len(region_stories):>8} {stats[region]['avg_words']:>10.1f} {stats[region]['median_words']:>8.1f} {lang_str}")

    print(f"\n{'TOTAL':<15} {len(stories):>8}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Load and filter ISEBEL stories")
    parser.add_argument("--min-words", type=int, default=20,
                        help="Minimum word count to keep a story (default: 20)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stories = load_all_stories(args.min_words)

    if not stories:
        print("No stories passed the filter! Try --min-words 5")
        raise SystemExit(1)

    stats = print_stats(stories)

    # Save filtered stories
    out_stories = OUTPUT_DIR / "filtered_stories.json"
    out_stories.write_text(json.dumps(stories, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(stories)} stories → {out_stories}")

    # Save stats
    out_stats = OUTPUT_DIR / "load_stats.json"
    out_stats.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved stats → {out_stats}")


if __name__ == "__main__":
    main()
