#!/usr/bin/env python3
"""Download story HTML pages from ISEBEL for story nodes in a CSV file.

Example:
    python download_wossidia_story_htmls.py \
        --input isebel-mecklenburg-nodes.csv \
        --output-dir output/wossidia_story_htmls
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterator
from urllib import error, request

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


DEFAULT_URL_PREFIX = "https://search.isebel.eu/dataset/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download ISEBEL story pages from an ISEBEL nodes CSV")
    parser.add_argument("--input", default="isebel-mecklenburg-nodes.csv", help="Path to the nodes CSV file")
    parser.add_argument("--output-dir", default="output/wossidia_story_htmls", help="Folder where HTML files will be saved")
    parser.add_argument("--url-prefix", default=DEFAULT_URL_PREFIX, help="ISEBEL dataset URL prefix")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="User-Agent header")
    parser.add_argument("--max-stories", type=int, default=None, help="Limit how many stories to download")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing HTML files")
    parser.add_argument("--dry-run", action="store_true", help="Print planned downloads without saving files")
    parser.add_argument("--iceland-bruteforce-sagnagrunnur", action="store_true",
                        help="Brute-force download is-sagnagrunnur-sg_1 through sg_9999 (ignores --input)")
    parser.add_argument("--sagnagrunnur-start", type=int, default=1,
                        help="Start number for sagnagrunnur brute-force (default: 1)")
    parser.add_argument("--sagnagrunnur-end", type=int, default=9999,
                        help="End number for sagnagrunnur brute-force (default: 9999)")
    return parser.parse_args()


def iter_story_paths(csv_path: Path, skip_sagnagrunnur: bool = False) -> Iterator[tuple[str, str]]:
    skipped_sagnagrunnur = 0
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if len(row) < 3:
                continue
            node_type = row[1].strip()
            if node_type != "story":
                continue

            metadata_raw = row[2].strip()
            try:
                metadata = json.loads(metadata_raw)
            except json.JSONDecodeError:
                continue

            path = metadata.get("path")
            title = metadata.get("title") or ""
            if path:
                # Skip sagnagrunnur.SG_* paths - they can't be reliably mapped to URLs
                if skip_sagnagrunnur and ".sagnagrunnur.SG_" in path:
                    skipped_sagnagrunnur += 1
                    continue
                yield path, title
    if skipped_sagnagrunnur > 0:
        print(f"Note: Skipped {skipped_sagnagrunnur} sagnagrunnur.SG_* path(s) (unmappable to URLs).")
        print("Use --iceland-bruteforce-sagnagrunnur to download those via sequential brute-force.")


def make_filename(input_path: Path, story_path: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", story_path)
    dataset_name = input_path.stem.replace("-nodes", "")
    return f"{dataset_name}-story-{stem}.html"


def download_story_html(story_path: str, url_prefix: str, user_agent: str) -> bytes:
    # Convert dots to hyphens and lowercase to match ISEBEL URL format
    # e.g. de.wossidia.xmd-s001-000-005-437 -> de-wossidia-xmd-s001-000-005-437
    # e.g. da.etk.DS_04_0_02227 -> da-etk-ds_04_0_02227
    isebel_path = story_path.replace(".", "-").lower()
    url = f"{url_prefix}{isebel_path}"
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
    }
    print(url)
    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req, timeout=60) as response:
        return response.read()


def brute_force_download_sagnagrunnur(url_prefix: str, user_agent: str, output_dir: Path,
                                        start: int, end: int, overwrite: bool, dry_run: bool) -> int:
    """Brute-force download is-sagnagrunnur-sg_N from start to end."""
    total = end - start + 1
    count = 0
    skipped = 0
    errors = 0
    not_found = 0

    range_iter = range(start, end + 1)
    progress_iter = tqdm(range_iter, desc="Brute-forcing sagnagrunnur", unit="page") if tqdm else range_iter

    for i in progress_iter:
        isebel_path = f"is-sagnagrunnur-sg_{i}"
        filename = f"iceland-sagnagrunnur-story-{i}.html"
        output_path = output_dir / filename

        count += 1
        if output_path.exists() and not overwrite and not dry_run:
            skipped += 1
            continue

        if dry_run:
            continue

        url = f"{url_prefix}{isebel_path}"
        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "is,en-US;q=0.7,en;q=0.3",
        }
        req = request.Request(url, headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=30) as response:
                html_bytes = response.read()
                output_path.write_bytes(html_bytes)
        except error.HTTPError as exc:
            if exc.code == 404:
                not_found += 1
                continue
            errors += 1
            print(f"HTTP error for {isebel_path}: {exc.code} {exc.reason}", file=sys.stderr)
        except error.URLError as exc:
            errors += 1
            print(f"URL error for {isebel_path}: {exc.reason}", file=sys.stderr)

    print(f"Done. Processed {count} pages ({skipped} skipped, {not_found} not found, {errors} errors).")
    return 0


def main() -> int:
    args = parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Iceland brute-force mode: download is-sagnagrunnur-sg_1..9999
    if args.iceland_bruteforce_sagnagrunnur:
        print(f"Brute-forcing is-sagnagrunnur-sg_{args.sagnagrunnur_start} through "
              f"is-sagnagrunnur-sg_{args.sagnagrunnur_end}...")
        return brute_force_download_sagnagrunnur(
            args.url_prefix, args.user_agent, output_dir,
            args.sagnagrunnur_start, args.sagnagrunnur_end,
            args.overwrite, args.dry_run,
        )

    # Normal CSV-based mode
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    # Auto-detect: skip sagnagrunnur paths for Iceland CSVs
    skip_sagnagrunnur = "iceland" in input_path.name.lower()
    if skip_sagnagrunnur:
        print("Detected Iceland input: skipping sagnagrunnur.SG_* paths (use --iceland-bruteforce-sagnagrunnur for those).")

    # Collect all story paths first to know total for progress bar
    story_paths = list(iter_story_paths(input_path, skip_sagnagrunnur=skip_sagnagrunnur))
    total = len(story_paths)
    if args.max_stories is not None:
        story_paths = story_paths[:args.max_stories]
        total = len(story_paths)

    count = 0
    skipped = 0
    errors = 0

    # Set up progress bar
    progress_iter = tqdm(story_paths, desc="Downloading stories", unit="story") if tqdm else story_paths

    for story_path, title in progress_iter:
        filename = make_filename(input_path, story_path)
        output_path = output_dir / filename
        if output_path.exists() and not args.overwrite and not args.dry_run:
            skipped += 1
            count += 1
            if not tqdm:
                print(f"Skipping existing file ({count}/{total}): {output_path.name}")
            continue

        if not tqdm:
            print(f"Downloading ({count+1}/{total}) {story_path} -> {output_path.name}")
        if args.dry_run:
            count += 1
            continue

        try:
            html_bytes = download_story_html(story_path, args.url_prefix, args.user_agent)
        except error.HTTPError as exc:
            errors += 1
            print(f"HTTP error for {story_path}: {exc.code} {exc.reason}", file=sys.stderr)
            count += 1
            continue
        except error.URLError as exc:
            errors += 1
            print(f"URL error for {story_path}: {exc.reason}", file=sys.stderr)
            count += 1
            continue

        output_path.write_bytes(html_bytes)
        count += 1

    print(f"Done. Processed {count} story node(s) ({skipped} skipped, {errors} errors).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
