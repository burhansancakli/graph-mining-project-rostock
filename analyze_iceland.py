#!/usr/bin/env python3
"""
Iceland Story Analysis Script
Reads all Iceland JSON story files and produces a comprehensive literary analysis.
"""

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

# ============================================================
# Configuration
# ============================================================
STORY_DIR = Path("output/wossidia_story_jsons")
NODE_CSV = Path("isebel-iceland-nodes.csv")
OUTPUT_FILE = Path("iceland_story_analysis.md")

# ============================================================
# 1. Load all Iceland story JSONs
# ============================================================
print("Loading Iceland stories...")
stories = []
for fname in sorted(os.listdir(STORY_DIR)):
    if fname.startswith("iceland-") and fname.endswith(".json"):
        fpath = STORY_DIR / fname
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            stories.append(data)
        except Exception as e:
            pass  # skip broken files silently

print(f"Loaded {len(stories)} Iceland stories.")

# ============================================================
# 2. Load keyword nodes from CSV
# ============================================================
csv_keywords = []
csv_keyword_ids = {}  # id -> name
try:
    with open(NODE_CSV, "r", encoding="utf-8") as f:
        for line in f:
            if '"keyword"' in line:
                # Extract the name from the JSON properties
                m = re.search(r'"name"\s*:\s*"([^"]*)"', line)
                id_match = re.match(r"(\d+),", line)
                if m:
                    kw_name = m.group(1).strip()
                    csv_keywords.append(kw_name)
                    if id_match:
                        csv_keyword_ids[id_match.group(1)] = kw_name
except Exception as e:
    print(f"Error reading CSV: {e}")

print(f"Found {len(csv_keywords)} keyword nodes in CSV.")

# ============================================================
# 3. Extract data from stories
# ============================================================
all_keywords = Counter()
all_places = Counter()
all_persons = Counter()
all_titles = []
all_descriptions = []
all_narration_dates = []
all_tale_types = Counter()
all_topic_languages = Counter()
stories_by_keyword = defaultdict(list)
keyword_cooccurrence = Counter()
description_word_freq = Counter()

# Also categorize keywords into thematic groups
THEME_CATEGORIES = {
    "Supernatural & Spirits": [
        "elves", "ghosts", "ghost belief", "demons", "nature spirits",
        "spirits", "elven settlements", "elven commerce", "female elve",
        "elvish entertainments", "elven settlements", "farm-protecting spirits",
        "mermaids", "sea monsters", "lake monster", "monsters", "trolls",
        "ogress", "changelings", "Named ghosts", "fetches", "ghostly smells",
        "summoning up", "summoning of beings (stefnur)", "seiður magic",
        "Magicians", "witches' familiars (tilberar)", "kynjamenn",
        "elves in need of aid", "midwives to the fairies", "Hagyrðingar",
        "personal hauntings", "waking the dead", "advice against ghosts"
    ],
    "Religion & Christian Faith": [
        "christmas", "Good Friday", "Christmas Cat", "ash wednesday",
        "crouchmass", "new year's night", "psalm singing", "singing at mass",
        "angels", "Holy men", "churches", "churchbells", "parishes",
        "corse-calls (warning of forthcoming death)", "sacrifices",
        "eye ointment", "calendars", "Shrove Tuesday", "First Day of Summer",
        "St Þorlákur's Mass", "important days"
    ],
    "Death & the Afterlife": [
        "ghost belief", "graves", "corpse-calls (warning of forthcoming death)",
        "Deaths and killings", "Revenges", "waking the dead",
        "personal hauntings", "suicide", "belief in fate"
    ],
    "Nature & Landscape": [
        "weather", "waterfalls", "cliffs, rocks", "driftwood",
        "marsh-mists", "rivers", "eggs", "egg-collecting", "harvesting",
        "coming of winter", "seals", "sea cows"
    ],
    "Daily Life & Work": [
        "fishing", "going to sea", "fishing stations", "boats and ships",
        "Danger at sea", "boat foremen", "fish processing", "harvesting",
        "workers (female)", "mills", "brewing", "charcoal making",
        "embroidery", "lighting", "lighting fuel", "technology", "scissors",
        "Atvinnuhættir"
    ],
    "Social Life & Customs": [
        "weddings", "games", "sayings", "verses", "ancient poems",
        "occasional verse", "verses", "storytellers (of legends)",
        "Births", "childbirth", "households", "teaching", "language",
        "Letters", "taboos", "oath or promise", "punishments"
    ],
    "Crime & Conflict": [
        "criminals", "thieves and thievery", "outlaws beliefs",
        "outlaws", "Revenges", "Blood"
    ],
    "Supernatural Powers": [
        "Magicians", "seiður magic", "summoning up",
        "summoning of beings (stefnur)", "eye ointment", "protection",
        "medical cures", "boundary marks"
    ],
    "Animals": [
        "seals", "Horses", "Fox and mink hunting", "hunting",
        "domestic animals", "sea cows"
    ],
    "Maritime Life": [
        "fishing", "going to sea", "boats and ships", "Danger at sea",
        "fishing stations", "fish processing", "boat foremen"
    ]
}

stories_with_keywords = 0
stories_with_descriptions = 0
stories_with_places = 0
empty_descriptions = 0

for story in stories:
    # Keywords
    kws = story.get("keywords", [])
    if kws:
        stories_with_keywords += 1
        for kw in kws:
            all_keywords[kw] += 1
            stories_by_keyword[kw].append(story.get("title", "Untitled"))
        # Co-occurrence
        for i in range(len(kws)):
            for j in range(i + 1, min(len(kws), i + 6)):  # top 5 co-occurring
                pair = tuple(sorted([kws[i], kws[j]]))
                keyword_cooccurrence[pair] += 1

    # Places
    places = story.get("places", [])
    if places:
        stories_with_places += 1
        for p in places:
            pname = p.get("name", "").strip()
            if pname:
                all_places[pname] += 1

    # Persons
    persons = story.get("persons", [])
    for p in persons:
        pname = p.get("name", "").strip()
        if pname:
            all_persons[pname] += 1

    # Title
    title = story.get("title", "")
    if title:
        all_titles.append(title)

    # Description
    desc = story.get("description", "") or ""
    if desc.strip():
        stories_with_descriptions += 1
        all_descriptions.append(desc)
        # Word frequency from descriptions (English content)
        words = re.findall(r'\b[a-zA-Z]{4,}\b', desc.lower())
        for w in words:
            if w not in {'this', 'that', 'with', 'from', 'they', 'have', 'been', 'were',
                         'said', 'them', 'their', 'some', 'when', 'what', 'which',
                         'about', 'there', 'into', 'then', 'than', 'other', 'would',
                         'could', 'should', 'will', 'were', 'been', 'being', 'also',
                         'very', 'much', 'more', 'most', 'such', 'only', 'just',
                         'after', 'before', 'where', 'while', 'every', 'each',
                         'here', 'does', 'will', 'have', 'made', 'come', 'came'}:
                description_word_freq[w] += 1
    else:
        empty_descriptions += 1

    # Narration date
    nd = story.get("narration_date")
    if nd:
        all_narration_dates.append(nd)

    # Tale type
    tt = story.get("tale_type")
    if tt:
        all_tale_types[tt] += 1

    # Topic language
    tl = story.get("topic_language", "")
    if tl:
        all_topic_languages[tl] += 1

# ============================================================
# 4. Categorize keywords into themes
# ============================================================
theme_counts = Counter()
theme_keywords_detail = defaultdict(list)
uncategorized_keywords = Counter()

for kw, count in all_keywords.most_common():
    found = False
    for theme, theme_kws in THEME_CATEGORIES.items():
        if kw in theme_kws:
            theme_counts[theme] += count
            theme_keywords_detail[theme].append((kw, count))
            found = True
            break  # assign to first matching category only
    if not found:
        uncategorized_keywords[kw] = count

# Sort theme details by count within each theme
for theme in theme_keywords_detail:
    theme_keywords_detail[theme].sort(key=lambda x: x[1], reverse=True)

# ============================================================
# 5. Analysis for date ranges
# ============================================================
years = []
for d in all_narration_dates:
    if d and len(d) >= 4:
        try:
            years.append(int(d[:4]))
        except:
            pass

# ============================================================
# 6. Generate Markdown Report
# ============================================================
lines = []
lines.append("# Iceland Stories — Comprehensive Literary Analysis")
lines.append("")
lines.append(f"**Source:** Sagnagrunnur (Icelandic Folklore Archive) via ISEBEL/WOSSIDIA")
lines.append(f"**Total stories analyzed:** {len(stories)}")
lines.append(f"**Keyword taxonomy nodes (CSV):** {len(csv_keywords)}")
lines.append("")

# Overview
lines.append("---")
lines.append("## 1. Dataset Overview")
lines.append("")
lines.append(f"| Metric | Count |")
lines.append(f"|--------|-------|")
lines.append(f"| Total stories | {len(stories)} |")
lines.append(f"| Stories with keywords | {stories_with_keywords} |")
lines.append(f"| Stories with descriptions | {stories_with_descriptions} |")
lines.append(f"| Stories without descriptions | {empty_descriptions} |")
lines.append(f"| Unique keywords in stories | {len(all_keywords)} |")
lines.append(f"| Unique places mentioned | {len(all_places)} |")
lines.append(f"| Unique persons mentioned | {len(all_persons)} |")
if years:
    lines.append(f"| Narration date range | {min(years)} – {max(years)} |")
lines.append("")

# Theme Analysis
lines.append("---")
lines.append("## 2. Thematic Analysis")
lines.append("")
lines.append("Themes are derived from the keyword taxonomy applied to stories. Keywords were")
lines.append("grouped into broader thematic categories based on their semantic meaning.")
lines.append("")
lines.append("### Theme Distribution")
lines.append("")
lines.append("| Rank | Theme | Story-mentions | Share |")
lines.append("|------|-------|---------------|-------|")
total_theme_mentions = sum(theme_counts.values())
for rank, (theme, count) in enumerate(theme_counts.most_common(), 1):
    pct = (count / total_theme_mentions * 100) if total_theme_mentions > 0 else 0
    lines.append(f"| {rank} | {theme} | {count} | {pct:.1f}% |")
lines.append("")

# Top keywords overall
lines.append("### Top 40 Most Frequent Keywords")
lines.append("")
lines.append("| Rank | Keyword | Occurrences | Category |")
lines.append("|------|---------|-------------|----------|")
for rank, (kw, count) in enumerate(all_keywords.most_common(40), 1):
    # Find category
    cat = "Uncategorized"
    for theme, theme_kws in THEME_CATEGORIES.items():
        if kw in theme_kws:
            cat = theme
            break
    lines.append(f"| {rank} | {kw} | {count} | {cat} |")
lines.append("")

# Detailed theme breakdown
lines.append("### Detailed Theme Breakdown")
lines.append("")
for theme, _ in theme_counts.most_common():
    kws_in_theme = theme_keywords_detail[theme]
    total_in_theme = sum(c for _, c in kws_in_theme)
    lines.append(f"#### {theme}")
    lines.append(f"*Total keyword mentions: {total_in_theme}*")
    lines.append("")
    # Show top 10 keywords in this theme
    for kw, cnt in kws_in_theme[:10]:
        lines.append(f"- **{kw}** ({cnt})")
    if len(kws_in_theme) > 10:
        lines.append(f"- *...and {len(kws_in_theme) - 10} more keywords*")
    lines.append("")

# Keyword co-occurrence
lines.append("---")
lines.append("## 3. Keyword Co-occurrence")
lines.append("")
lines.append("Most frequently co-occurring keyword pairs (when two keywords appear together in the same story):")
lines.append("")
lines.append("| Rank | Keyword Pair | Count |")
lines.append("|------|-------------|-------|")
for rank, ((kw1, kw2), cnt) in enumerate(keyword_cooccurrence.most_common(25), 1):
    lines.append(f"| {rank} | {kw1} ↔ {kw2} | {cnt} |")
lines.append("")

# Places
lines.append("---")
lines.append("## 4. Geographic Distribution")
lines.append("")
lines.append("### Top 30 Narration Places")
lines.append("")
lines.append("| Rank | Place | Story count |")
lines.append("|------|-------|-------------|")
for rank, (place, cnt) in enumerate(all_places.most_common(30), 1):
    lines.append(f"| {rank} | {place} | {cnt} |")
lines.append("")

# Persons
lines.append("---")
lines.append("## 5. Key Persons (Narrators, Collectors, Subjects)")
lines.append("")
lines.append("### Top 30 Persons Mentioned")
lines.append("")
lines.append("| Rank | Person | Mentions |")
lines.append("|------|--------|----------|")
for rank, (person, cnt) in enumerate(all_persons.most_common(30), 1):
    lines.append(f"| {rank} | {person} | {cnt} |")
lines.append("")

# Temporal Analysis
lines.append("---")
lines.append("## 6. Temporal Distribution")
lines.append("")
if years:
    # Decade distribution
    decade_counter = Counter()
    for y in years:
        decade = (y // 10) * 10
        decade_counter[decade] += 1
    lines.append("### Stories by Decade of Narration")
    lines.append("")
    lines.append("| Decade | Count |")
    lines.append("|--------|-------|")
    for decade in sorted(decade_counter.keys()):
        lines.append(f"| {decade}s | {decade_counter[decade]} |")
    lines.append("")
    lines.append(f"*Stories with narration dates: {len(years)} out of {len(stories)}*")
    lines.append(f"*Date range: {min(years)} – {max(years)}*")
else:
    lines.append("*No narration dates found in the dataset.*")
lines.append("")

# Language
lines.append("---")
lines.append("## 7. Topic Language Distribution")
lines.append("")
lines.append("| Language | Count |")
lines.append("|----------|-------|")
for lang, cnt in all_topic_languages.most_common():
    lines.append(f"| {lang} | {cnt} |")
lines.append("")

# Title analysis - sample interesting titles
lines.append("---")
lines.append("## 8. Sample Story Titles")
lines.append("")
lines.append("Here is a sampling of story titles to illustrate the breadth of the collection:")
lines.append("")

# Group titles by keyword theme for a more interesting display
sample_by_theme = {}
for kw, count in all_keywords.most_common(15):
    if stories_by_keyword[kw]:
        sample_by_theme[kw] = stories_by_keyword[kw][:5]

for theme_kws, titles in list(sample_by_theme.items())[:10]:
    lines.append(f"**Stories tagged '{theme_kws}':**")
    for t in titles[:3]:
        lines.append(f"- *{t}*")
    lines.append("")

# Uncategorized keywords of interest
lines.append("---")
lines.append("## 9. Notable Uncategorized Keywords")
lines.append("")
lines.append("These keywords do not fit neatly into the predefined thematic categories:")
lines.append("")
for kw, cnt in uncategorized_keywords.most_common(30):
    lines.append(f"- **{kw}** ({cnt} mentions)")
lines.append("")

# Description analysis
lines.append("---")
lines.append("## 10. Description Content Analysis")
lines.append("")
lines.append("### Most Frequent Words in Story Descriptions (English)")
lines.append("")
lines.append("| Rank | Word | Frequency |")
lines.append("|------|------|-----------|")
for rank, (word, cnt) in enumerate(description_word_freq.most_common(40), 1):
    lines.append(f"| {rank} | {word} | {cnt} |")
lines.append("")

# Methodology
lines.append("---")
lines.append("## 11. Methodology & Notes")
lines.append("")
lines.append("- **Data source:** Story JSON files from the Sagnagrunnur (Icelandic Folklore Archive) extracted via ISEBEL")
lines.append("- **Keyword taxonomy:** Loaded from `isebel-iceland-nodes.csv` (481 keyword nodes)")
lines.append("- **Thematic grouping:** Keywords were manually assigned to 10 broader thematic categories")
lines.append("  based on semantic similarity. Some keywords appear in multiple potential categories;")
lines.append("  each was assigned to its primary category only.")
lines.append(f"- **Stories analyzed:** {len(stories)} JSON files")
lines.append(f"- **Keyword coverage:** {stories_with_keywords} stories ({stories_with_keywords/len(stories)*100:.1f}%) had at least one keyword")
lines.append(f"- **Description coverage:** {stories_with_descriptions} stories ({stories_with_descriptions/len(stories)*100:.1f}%) had a text description")
lines.append(f"- **Place coverage:** {stories_with_places} stories ({stories_with_places/len(stories)*100:.1f}%) had a narration place")
lines.append("- **Co-occurrence:** Pairs of keywords appearing in the same story (capped at 5 pairings per keyword to avoid trivial pairs)")
lines.append("")
lines.append("---")
lines.append("*Generated by `analyze_iceland.py`*")

# ============================================================
# 7. Write output
# ============================================================
output = "\n".join(lines)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(output)

print(f"\nAnalysis written to {OUTPUT_FILE}")
print(f"Total stories: {len(stories)}")
print(f"Unique keywords: {len(all_keywords)}")
print(f"Unique places: {len(all_places)}")
print(f"Unique persons: {len(all_persons)}")
print(f"Top 5 keywords: {all_keywords.most_common(5)}")
print(f"Top 5 themes: {theme_counts.most_common(5)}")
