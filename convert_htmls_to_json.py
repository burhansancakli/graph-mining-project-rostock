#!/usr/bin/env python3
"""Convert downloaded ISEBEL story HTML pages to JSON files.

Extracts structured data (region, id, url, title, description, keywords,
persons, places, narration date, tale type, etc.) from each HTML file.

Example:
    python convert_htmls_to_json.py
    python convert_htmls_to_json.py --input-dir output/wossidia_story_htmls --output-dir output/wossidia_story_jsons
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from tqdm import tqdm

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("beautifulsoup4 is required. Install it with: pip install beautifulsoup4")
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert ISEBEL story HTML files to JSON")
    parser.add_argument(
        "--input-dir",
        default="output/wossidia_story_htmls",
        help="Directory containing the downloaded HTML files",
    )
    parser.add_argument(
        "--output-dir",
        default="output/wossidia_story_jsons",
        help="Directory to write JSON files to",
    )
    # Add these arguments inside parse_args()

    parser.add_argument(
        "--merge-only",
        action="store_true",
        help="Merge existing JSON files into one JSON file without converting HTML files",
    )
    parser.add_argument(
        "--merged-file",
        default="output/wossidia_story_jsons/all_stories.json",
        help="Output filename for merged JSON file",
    )
    return parser.parse_args()


def merge_json_files(input_dir: Path, output_file: Path):
    """Merge all JSON files in a directory into one JSON array."""

    json_files = sorted(
        f for f in input_dir.glob("*.json")
        if f.name != output_file.name
    )

    if not json_files:
        print(f"No JSON files found in '{input_dir}'.")
        raise SystemExit(1)

    print(f"Found {len(json_files)} JSON files to merge.")

    merged_data = []

    for json_file in tqdm(json_files, desc="Merging", unit="file"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            merged_data.append(data)

        except Exception as e:
            tqdm.write(f"ERROR reading {json_file.name}: {e}")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    output_file.write_text(
        json.dumps(
            merged_data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nDone! Merged {len(merged_data)} JSON files.")
    print(f"Saved merged file to: {output_file}")

def extract_region_from_filename(filename: str) -> str | None:
    """Extract region from filename.
    
    Handles patterns:
      - isebel-denmark-story-xxx.html  →  denmark
      - isebel-mecklenburg-story-xxx.html  →  mecklenburg
      - iceland-sagnagrunnur-story-1.html  →  iceland
    """
    # Try isebel-{region}-story pattern first
    m = re.match(r"isebel-(\w+)-story-", filename)
    if m:
        return m.group(1)
    # Try {region}-sagnagrunnur-story pattern
    m = re.match(r"(\w+)-sagnagrunnur-story-", filename)
    if m:
        return m.group(1)
    return None


def extract_id_from_filename(filename: str) -> str | None:
    """Extract story id from filename.
    
    Handles patterns:
      - isebel-denmark-story-da.etk.DS_01_0_00001.html  →  da.etk.DS_01_0_00001
      - iceland-sagnagrunnur-story-1.html  →  1
    """
    # Try isebel-{region}-story-{id}.html pattern
    m = re.match(r"isebel-\w+-story-(.+)\.html$", filename)
    if m:
        return m.group(1)
    # Try {region}-sagnagrunnur-story-{id}.html pattern
    m = re.match(r"\w+-sagnagrunnur-story-(.+)\.html$", filename)
    if m:
        return m.group(1)
    return None


def extract_sidebar_field(soup: BeautifulSoup, label_text: str) -> str | None:
    """Find a field in the sidebar by its hcLabel text, return the next sibling div's text."""
    labels = soup.find_all("div", class_="hcLabel")
    for label in labels:
        if label_text.lower() in label.get_text(strip=True).lower():
            next_div = label.find_next_sibling("div")
            if next_div:
                text = next_div.get_text(strip=True).strip()
                if text and text != "\xa0":
                    return text
    return None


def extract_keywords(soup: BeautifulSoup) -> list[str]:
    """Extract keyword tags from the sidebar."""
    keywords = []
    tags = soup.find_all("div", class_="hcIsTags")
    for tag in tags:
        a = tag.find("a")
        if a:
            text = a.get_text(strip=True).strip()
            if text:
                keywords.append(text)
    return keywords


def extract_persons(soup: BeautifulSoup) -> list[dict]:
    """Extract person info from sidebar."""
    persons = {}
    labels = soup.find_all("div", class_="hcLabel")
    for label in labels:
        label_text = label.get_text(strip=True)
        next_div = label.find_next_sibling("div")
        if not next_div:
            continue
        value = next_div.get_text(strip=True).strip()
        if not value or value == "\xa0":
            continue

        # Match person_id_xxx_N patterns
        m = re.match(r"person_(?:id_)?(\w+?)(?:_(\d+))?(_role|_gender)?$", label_text)
        if m:
            person_id = m.group(1)
            suffix = m.group(3) or ""
            if suffix == "_role":
                persons.setdefault(person_id, {})["role"] = value
            elif suffix == "_gender":
                persons.setdefault(person_id, {})["gender"] = value
            else:
                persons.setdefault(person_id, {})["name"] = value

    persons_raw = [
        {"name": p.get("name", ""), "role": p.get("role", ""), "gender": p.get("gender", "")}
        for p in persons.values()
        if p.get("name")
    ]
    # Deduplicate by name, keeping the entry with the most info
    seen_persons: dict[str, dict] = {}
    for p in persons_raw:
        key = p["name"]
        if key not in seen_persons or (p["role"] and not seen_persons[key]["role"]):
            seen_persons[key] = p
    return list(seen_persons.values())


def extract_places(soup: BeautifulSoup) -> list[dict]:
    """Extract place info from sidebar."""
    places = {}
    labels = soup.find_all("div", class_="hcLabel")
    for label in labels:
        label_text = label.get_text(strip=True)
        next_div = label.find_next_sibling("div")
        if not next_div:
            continue
        value = next_div.get_text(strip=True).strip()
        if not value or value == "\xa0":
            continue

        m = re.match(r"place_(?:id_)?(\w+?)(?:_(\d+))?(_role)?$", label_text)
        if m:
            place_id = m.group(1)
            suffix = m.group(3) or ""
            if suffix == "_role":
                places.setdefault(place_id, {})["role"] = value
            else:
                places.setdefault(place_id, {})["name"] = value

    places_raw = [
        {"name": p.get("name", ""), "role": p.get("role", "")}
        for p in places.values()
        if p.get("name")
    ]
    # Deduplicate by name, keeping the entry with the most info
    seen_places: dict[str, dict] = {}
    for p in places_raw:
        key = p["name"]
        if key not in seen_places or (p["role"] and not seen_places[key]["role"]):
            seen_places[key] = p
    return list(seen_places.values())


def extract_story_text(soup: BeautifulSoup) -> str:
    """Extract the story text from the main content area."""
    # The story text is in a <p> or <ol> after <div class="topic-title">
    topic_div = soup.find("div", class_="topic-title")
    if topic_div:
        # Get the next sibling that contains the story
        next_el = topic_div.find_next_sibling()
        if next_el:
            return next_el.get_text(separator="\n", strip=True)

    # Fallback: look for <p> or <ol> inside the main content area
    main = soup.find("div", class_="hcLayoutMain")
    if main:
        h2 = main.find("h2")
        if h2:
            # Get text after h2
            text_parts = []
            for el in h2.find_next_siblings():
                if el.name in ("p", "ol", "ul"):
                    text_parts.append(el.get_text(separator="\n", strip=True))
            if text_parts:
                return "\n".join(text_parts)

    return ""


def extract_source_url(soup: BeautifulSoup) -> str | None:
    """Extract the external source URL from the sidebar."""
    aside = soup.find("div", class_="hcLayoutAside")
    if aside:
        # The source URL is in an <a> tag after the org image
        a_tag = aside.find("a", href=True)
        if a_tag:
            href = a_tag["href"]
            if href.startswith("http"):
                return href
    return None


def extract_og_metadata(soup: BeautifulSoup) -> dict:
    """Extract Open Graph metadata."""
    result = {}
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    if og_title:
        result["og_title"] = og_title.get("content", "")
    if og_desc:
        result["og_description"] = og_desc.get("content", "")
    return result


def parse_html_file(filepath: Path) -> dict:
    """Parse a single ISEBEL HTML file and return structured data."""
    html_content = filepath.read_text(encoding="utf-8")
    soup = BeautifulSoup(html_content, "html.parser")

    filename = filepath.name
    region = extract_region_from_filename(filename)
    story_id = extract_id_from_filename(filename)

    # Title from <h2>
    h2 = soup.find("h2")
    title = h2.get_text(strip=True) if h2 else ""

    # OG metadata
    og = extract_og_metadata(soup)

    # Story text
    story_text = extract_story_text(soup)

    # Topic language
    topic_div = soup.find("div", class_="topic-title")
    topic_lang = topic_div.get_text(strip=True) if topic_div else ""

    # Source URL
    source_url = extract_source_url(soup)

    # Sidebar fields
    narration_date = extract_sidebar_field(soup, "Narration date")
    tale_type = extract_sidebar_field(soup, "Tale type")
    narration_place = extract_sidebar_field(soup, "Narration Place")

    # Breadcrumb organization (skip the generic "Organizations" breadcrumb link)
    org = ""
    org_links = soup.find_all("a", href=re.compile(r"/organization/"))
    for org_link in org_links:
        text = org_link.get_text(strip=True)
        if text and text.lower() != "organizations":
            org = text
            break

    # Keywords, persons, places
    keywords = extract_keywords(soup)
    persons = extract_persons(soup)
    places = extract_places(soup)

    return {
        "region": region,
        "id": story_id,
        "url": source_url,
        "title": title,
        "description": story_text,
        "topic_language": topic_lang,
        "organization": org,
        "keywords": keywords,
        "persons": persons,
        "places": places,
        "narration_date": narration_date,
        "tale_type": tale_type,
        "narration_place": narration_place,
        "og_title": og.get("og_title", ""),
        "og_description": og.get("og_description", ""),
        "html_file": filename,
    }


def main():
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if args.merge_only:
        merge_json_files(
            output_dir,
            Path(args.merged_file)
        )
        return
    
    if not input_dir.exists():
        print(f"Error: Input directory '{input_dir}' does not exist.")
        raise SystemExit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    html_files = sorted(input_dir.glob("*.html"))
    if not html_files:
        print(f"No HTML files found in '{input_dir}'.")
        raise SystemExit(1)

    print(f"Found {len(html_files)} HTML files in '{input_dir}'")
    print(f"Writing JSON files to '{output_dir}'")

    success_count = 0
    error_count = 0

    iterator = tqdm(html_files, desc="Converting", unit="file") if tqdm else html_files

    for html_file in iterator:
        try:
            data = parse_html_file(html_file)
            json_filename = html_file.stem + ".json"
            json_path = output_dir / json_filename
            json_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            success_count += 1
        except Exception as e:
            if tqdm:
                tqdm.write(f"  ERROR parsing {html_file.name}: {e}")
            else:
                print(f"  ERROR parsing {html_file.name}: {e}")
            error_count += 1

    print(f"\nDone! Converted {success_count} files ({error_count} errors).")
    print(f"JSON files are in: {output_dir}")


if __name__ == "__main__":
    main()
