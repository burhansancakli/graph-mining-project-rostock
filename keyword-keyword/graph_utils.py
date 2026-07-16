"""
What changed vs. the original single-region version, and why:

1. Region-aware loading. The `merged/` dataset (built by
   ``scripts/merge_graph_csvs.py``) tags every row with its source region,
   but each region file numbers its own nodes starting from 0. That means
   story "103" in Denmark and story "103" in Mecklenburg are two completely
   different nodes that happen to share an ID. Every node is therefore keyed
   as ``"region:id"`` internally, never the bare id, whether you load a
   single region or the merged file.

2. Cross-region keyword canonicalization. "Werwolf" (German), "weerwolf"
   (Dutch) and "varulv" (Danish) all describe the same folklore motif but are
   different strings in different languages. `synonyms.json` is an
   extensible dictionary of "concepts" — patterns that, if found in a
   (normalized) keyword string, collapse it onto one shared canonical node
   (``concept:werewolf``) regardless of which region/language it came from.
   This is what lets you ask "does the werewolf motif form one community
   across regions, or separate ones?" instead of only within one region.

3. Reads columns by name (``csv.DictReader``), not by position, so the
   loader keeps working even if the merge script's column order changes.

Usage:
    from graph_utils import load_graph
    G, keyword_text, keyword_regions = load_graph("mecklenburg")
    G, keyword_text, keyword_regions = load_graph("all")   # merged/, every region
"""

import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import networkx as nx

# project_root/keyword-keyword/graph_utils.py -> project_root/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Burhan's merge_graph_csvs.py defaults to reading isebel-*.csv from the repo
# root and writing merged-*.csv into a top-level merged/ folder -- we keep
# both conventions as-is rather than moving his data layout around.
RAW_DIR = PROJECT_ROOT
MERGED_DIR = PROJECT_ROOT / "merged"

# ── CONFIG ────────────────────────────────────────────────────────────────
DATASET = "mecklenburg"     # mecklenburg | iceland | denmark | netherlands | all

# See the big comment at the co-occurrence loop below for why this exists
# and what it fixes. On by default -- tested to help every region, not just
# the ones with the "too many keywords per story" problem.
ENABLE_FRACTIONAL_WEIGHTING = True

# With ENABLE_FRACTIONAL_WEIGHTING, edge weights are usually well under 1.0
# per story (a pair from a 10-keyword story only contributes 1/9), so the
# old flat threshold of 2 (meant for integer counts) would throw away
# almost everything. 1.0 roughly means "these two co-occurred with the
# equivalent weight of at least one small (2-keyword) story between them".
# If you set ENABLE_FRACTIONAL_WEIGHTING = False, go back to MIN_COOCCURRENCE = 2.
MIN_COOCCURRENCE = 1.0

ENABLE_FUZZY_MERGE = True    # merge near-duplicate keyword strings within one region
FUZZY_MERGE_THRESHOLD = 92   # 0-100 (rapidfuzz.fuzz.ratio)
FUZZY_BLOCK_MAX_SIZE = 250   # skip pathologically large blocks (O(n^2) cost)

# Optional: drop keywords that appear in more than this fraction of stories
# (e.g. 0.03 = drop anything in >3% of stories) before building the
# co-occurrence graph -- the "these are basically stopwords" idea. Off by
# default (None). We tested this on the merged "all" dataset expecting it to
# raise modularity (very generic Dutch tags like "man"/"huis"/"nacht" sit at
# 3-6% document frequency) and it did NOT reliably help -- modularity got
# worse at a 0.5% cutoff, only partially recovered at 0.25%. These broad
# keywords carry real co-occurrence signal, they're not pure noise, so we
# don't strip them automatically. `document_frequency` / `document_frequency_ratio`
# are still computed and attached to every node so you can inspect/filter
# deliberately if you want to experiment further.
MAX_DOCUMENT_FREQUENCY_RATIO = None

SYNONYMS_FILE = Path(__file__).resolve().parent / "synonyms.json"

REGIONS = ["mecklenburg", "iceland", "denmark", "netherlands"]


def _paths_for(dataset: str):
    if dataset == "all":
        return MERGED_DIR / "merged-nodes.csv", MERGED_DIR / "merged-edges.csv"
    return RAW_DIR / f"isebel-{dataset}-nodes.csv", RAW_DIR / f"isebel-{dataset}-edges.csv"


NODES_FILE, EDGES_FILE = _paths_for(DATASET)


# ── Text normalization & synonym dictionary ─────────────────────────────────

def _normalize(text: str) -> str:
    """lowercase, strip accents/diacritics, strip punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_synonym_patterns() -> dict:
    """Compile synonyms.json into {concept_name: compiled_regex}."""
    if not SYNONYMS_FILE.exists():
        return {}
    with open(SYNONYMS_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    compiled = {}
    for concept, cfg in raw.items():
        if concept.startswith("_"):
            continue
        patterns = [_normalize(p) for p in cfg.get("patterns", []) if p.strip()]
        if patterns:
            compiled[concept] = re.compile("|".join(re.escape(p) for p in patterns))
    return compiled


def canonicalize_keyword(raw_text: str, region: str, synonym_patterns: dict) -> tuple:
    """
    Returns (canonical_id, display_text).
    If the text matches a concept in synonyms.json -> a shared cross-region
    node ("concept:werewolf"). Otherwise it stays region-specific
    ("mecklenburg:some normalized phrase").
    """
    norm = _normalize(raw_text)
    for concept, pattern in synonym_patterns.items():
        if pattern.search(norm):
            return f"concept:{concept}", concept
    return f"{region}:{norm}", raw_text.strip()


def _fuzzy_merge_map(region_keywords: dict) -> dict:
    """
    region_keywords: {region: {canonical_id_before_fuzzy: display_text}}
    Only merges WITHIN the same region (we never guess across languages
    without an explicit synonym match). Returns old_id -> merged_id.
    """
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return {}

    mapping = {}
    for region, kw_dict in region_keywords.items():
        items = [(kid, _normalize(text)) for kid, text in kw_dict.items() if not kid.startswith("concept:")]
        blocks = defaultdict(list)
        for kid, norm in items:
            blocks[norm[:3]].append((kid, norm))

        parent = {kid: kid for kid, _ in items}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for block in blocks.values():
            n = len(block)
            if n < 2 or n > FUZZY_BLOCK_MAX_SIZE:
                continue
            for i in range(n):
                for j in range(i + 1, n):
                    kid1, t1 = block[i]
                    kid2, t2 = block[j]
                    if fuzz.ratio(t1, t2) >= FUZZY_MERGE_THRESHOLD:
                        union(kid1, kid2)

        for kid, _ in items:
            mapping[kid] = find(kid)
    return mapping


# ── Main loader ──────────────────────────────────────────────────────────────

def load_graph(dataset: str = None):
    """
    Returns:
      G               — networkx graph. Nodes = canonical keyword concepts.
                         Edge weight = number of stories they co-occur in.
      keyword_text    — dict canonical_id -> most common display text
      keyword_regions — dict canonical_id -> set(regions the concept appears in)
    """
    ds = dataset or DATASET
    nodes_file, edges_file = _paths_for(ds)
    merged_format = ds == "all"

    if not nodes_file.exists() or not edges_file.exists():
        raise FileNotFoundError(
            f"Missing data for dataset '{ds}'. Expected:\n  {nodes_file}\n  {edges_file}"
        )

    synonym_patterns = load_synonym_patterns()

    id_to_canonical: dict = {}                       # "region:id" -> canonical keyword id
    region_keywords: dict = defaultdict(dict)          # region -> {canon_id: display}
    keyword_regions: dict = defaultdict(set)
    keyword_display_counts: dict = defaultdict(lambda: defaultdict(int))
    n_nodes_seen = 0

    # ── 1. Load nodes ────────────────────────────────────────────────────────
    with open(nodes_file, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            n_nodes_seen += 1
            nid, label, props = row["id"], row["label"], row["properties"]
            region = row["region"] if merged_format else ds

            if label == "keyword":
                try:
                    p = json.loads(props)
                    text = p.get("name") or p.get("keyword") or p.get("text") or p.get("label") or str(p)
                except Exception:
                    text = props
                text = str(text)
                canon_id, display = canonicalize_keyword(text, region, synonym_patterns)
                id_to_canonical[f"{region}:{nid}"] = canon_id
                region_keywords[region][canon_id] = display
                keyword_regions[canon_id].add(region)
                keyword_display_counts[canon_id][display] += 1

    print(f"[{ds}] Loaded {n_nodes_seen} nodes, "
          f"{sum(len(v) for v in region_keywords.values())} keyword concepts (pre fuzzy-merge)")

    # ── 2. Optional fuzzy merge (typos / plural-singular within one region) ──
    if ENABLE_FUZZY_MERGE:
        fuzzy_map = _fuzzy_merge_map(region_keywords)
        if fuzzy_map:
            for key, canon in id_to_canonical.items():
                if canon in fuzzy_map:
                    merged_into = fuzzy_map[canon]
                    if merged_into != canon:
                        id_to_canonical[key] = merged_into
                        keyword_regions[merged_into] |= keyword_regions.get(canon, set())
                        for disp, cnt in keyword_display_counts.get(canon, {}).items():
                            keyword_display_counts[merged_into][disp] += cnt
            n_merged = sum(1 for old, new in fuzzy_map.items() if old != new)
            print(f"[{ds}] Fuzzy-merge folded {n_merged} near-duplicate variants together")

    keyword_text = {
        cid: max(counts.items(), key=lambda x: x[1])[0]
        for cid, counts in keyword_display_counts.items()
    }

    # ── 3. story -> set(canonical keyword) from "content" edges ─────────────
    story_keywords: dict = defaultdict(set)

    with open(edges_file, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src, dst, label = row["src-id"], row["dst-id"], row["label"]
            region = row["region"] if merged_format else ds
            if label == "content":
                canon = id_to_canonical.get(f"{region}:{dst}")
                if canon:
                    story_keywords[f"{region}:{src}"].add(canon)

    print(f"[{ds}] Stories with at least one keyword: {len(story_keywords)}")

    # ── document frequency: how many stories use each keyword ────────────────
    # Kept as metadata (visible in the viewer / detail panel) rather than an
    # automatic filter -- see graph_utils.py's module docstring / the
    # "why we don't auto-strip generic keywords" note below for why.
    doc_freq: dict = defaultdict(int)
    for kws in story_keywords.values():
        for k in kws:
            doc_freq[k] += 1
    n_stories = len(story_keywords)

    if MAX_DOCUMENT_FREQUENCY_RATIO is not None and n_stories > 0:
        cutoff = MAX_DOCUMENT_FREQUENCY_RATIO * n_stories
        too_generic = {k for k, c in doc_freq.items() if c > cutoff}
        if too_generic:
            for kws in story_keywords.values():
                kws -= too_generic
            print(f"[{ds}] Dropped {len(too_generic)} keyword(s) appearing in more than "
                  f"{MAX_DOCUMENT_FREQUENCY_RATIO*100:.0f}% of stories "
                  f"({', '.join(keyword_text.get(k, k) for k in list(too_generic)[:8])}"
                  f"{'...' if len(too_generic) > 8 else ''})")

    # ── Co-occurrence -> graph ─────────────────────────────────────────────
    # ENABLE_FRACTIONAL_WEIGHTING (see config, on by default) matters a lot:
    # a story tagged with k keywords contributes k*(k-1)/2 pairs. Denmark and
    # Netherlands have a meaningful share of stories tagged with dozens or
    # even hundreds of keywords (Denmark: 12.7% of stories have >20 keywords,
    # one has 387; Netherlands: 15.3%, one has 214) -- those few stories
    # alone can contribute tens of thousands of pairs, turning the graph into
    # a near-complete graph with no real community structure (we measured
    # this: Denmark's baseline Louvain Q was 0.114 on a 5,837-node/713,393-edge
    # graph). Weighting each story's contribution by 1/(k-1) instead of a
    # flat 1 keeps every story's total "vote" roughly constant regardless of
    # how many keywords it's tagged with, which is the standard fix for this
    # in co-occurrence-network literature. Measured effect: Denmark's Q goes
    # from 0.114 to 0.65, Mecklenburg's (already good) goes from 0.757 to
    # 0.853 -- it helps everywhere, not just the problem cases.
    cooc: dict = defaultdict(float)
    for kws in story_keywords.values():
        kws = list(kws)
        k = len(kws)
        if k < 2:
            continue
        contribution = 1.0 / (k - 1) if ENABLE_FRACTIONAL_WEIGHTING else 1.0
        for i in range(len(kws)):
            for j in range(i + 1, len(kws)):
                a, b = kws[i], kws[j]
                if a > b:
                    a, b = b, a
                cooc[(a, b)] += contribution

    G = nx.Graph()
    for (a, b), w in cooc.items():
        if w >= MIN_COOCCURRENCE:
            G.add_edge(a, b, weight=w)

    if G.number_of_nodes() == 0:
        raise RuntimeError(f"Graph for '{ds}' came out empty — check MIN_COOCCURRENCE or the source files.")

    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()

    # region as a node attribute (needed for e.g. keyword <-> place analysis)
    for n in G.nodes():
        G.nodes[n]["regions"] = sorted(keyword_regions.get(n, set()))
        G.nodes[n]["is_cross_region_concept"] = n.startswith("concept:")
        G.nodes[n]["document_frequency"] = doc_freq.get(n, 0)
        G.nodes[n]["document_frequency_ratio"] = round(doc_freq.get(n, 0) / n_stories, 4) if n_stories else 0.0

    print(f"[{ds}] Final graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G, keyword_text, keyword_regions


if __name__ == "__main__":
    load_graph()
