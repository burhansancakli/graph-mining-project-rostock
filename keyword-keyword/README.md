# keyword-keyword/

Keyword co-occurrence graph + community detection for the ISEBEL folklore
datasets. Two keywords are connected if they appear as tags on the same
story; edge weight = how often they co-occur.

## Layout

```
keyword-keyword/
├── graph_utils.py              -- loads CSVs, builds the graph (see below)
├── synonyms.json                -- cross-region/cross-language keyword concepts
├── metrics.py                   -- ARI/NMI + Jaccard cluster-comparison, singleton zoom
├── louvain_analysis.py          -- Louvain (hard communities)
├── louvain_analysis_zoomed.py   -- Louvain, zoomed into one community (+ --exclude-anchor)
├── girvan_newman_analysis.py    -- Girvan-Newman (hard communities, divisive)
├── bigclam_analysis.py          -- BigCLAM (overlapping communities)
├── comparison.py                -- runs all three + the metrics report
├── DIAGNOSIS_all_dataset.md     -- why Q/community count look worse on "all" than on
│                                    one region, and what's worth trying about it
├── viz/
│   ├── export_data.py           -- NOT run directly; imported by louvain_analysis.py
│   │                                and comparison.py to build the JSON the viewer reads
│   ├── build_explorer_html.py   -- run this: bakes the JSON exports into one HTML file
│   └── network_explorer.html    -- the interactive viewer itself 
└── outputs/                      -- everything each script produces, one
    └── <dataset>/                  subfolder per dataset (mecklenburg, all, ...)
        └── graph_export_<dataset>.json    -- read by viz/build_explorer_html.py;
                                               not needed once network_explorer.html
                                               has been (re)built
```


## Data source

Reads either:
- `../isebel-<region>-nodes.csv` / `../isebel-<region>-edges.csv` (single
  region, at the repo root -- unchanged from before), or
- `../merged/merged-nodes.csv` / `../merged/merged-edges.csv` (built by
  `../merge_graph_csvs.py`, all four regions in one file, each row tagged
  with a `region` column).

Set which one via the `DATASET` variable in `graph_utils.py`, or pass it as
an argument/CLI flag to any script (see "How to run" below).

**Important, and easy to miss**: the merged file reuses each region's own
original IDs, so e.g. story `103` in Denmark and story `103` in Mecklenburg
are different nodes that just share a number. `graph_utils.py` keys every
node as `"region:id"` internally so this can never silently collide.

## Cross-region keyword canonicalization

`synonyms.json` is an extensible dictionary of "concepts" -- e.g.
`"werwolf"` (German), `"weerwolf"` (Dutch) and `"varulv"` (Danish) all
collapse onto one shared node, `concept:werewolf`, regardless of region.
This is what lets you ask "does the werewolf motif form one community
across regions, or separate ones?" Add new concepts by editing the JSON
file -- no code changes needed. A few common Germanic-cognate motifs beyond
werewolf are pre-populated (devil, ghost, treasure, dragon, dwarf, witch,
church) as a starting point; **these patterns should be checked by someone
who reads Danish/Dutch**, they were derived from known root words, not
verified translations.

Keywords that don't match any concept are still deduplicated within one
region via fuzzy string matching (typos, trailing punctuation,
singular/plural) using `rapidfuzz`.

## Quantitative cluster comparison (metrics.py)

- `compare_partitions()` -- Adjusted Rand Index and Normalized Mutual
  Information between two hard partitions (e.g. Louvain vs Girvan-Newman).
  On Mecklenburg we got **ARI = 0.746, NMI = 0.833** -- a genuinely strong,
  numeric agreement between two algorithms that work in completely
  different ways, which is worth stating in the writeup instead of "they
  look similar".
- `jaccard_best_matches()` -- for every community in A, the best-overlapping
  community in B and the Jaccard score; communities with no good match
  anywhere in B are flagged as **algorithm-specific** ("special clusters not
  found by others", the professor's other remark).

## Singleton zoom, properly (metrics.zoom_excluding_anchor)

 The original `louvain_analysis_zoomed.py` zoomed into a community
but kept the anchor keyword inside the subgraph (so "Hexe"/"Werwolf" was
still the dominant hub in the picture). `--exclude-anchor` now actually
drops that node before re-running Louvain, so you see the substructure that
was otherwise hidden underneath it. Example, on Mecklenburg's werewolf
community with the anchor removed: it splits into small, very specific
sub-motifs -- transformation-into-dog, transformation-into-bear, the
wolf-strap, the "ample meal" -- rather than one blob around "werewolf".

## Interactive visualization (viz/)

Run `viz/build_explorer_html.py` again after any new `comparison.py` run to
pick up the latest export (it needs the file written by `comparison.py`,
since that's what includes both algorithms -- `louvain_analysis.py` run on
its own only has Louvain, and Girvan-Newman nodes will show as "not in this
algorithm's subgraph" until you run `comparison.py`).

## How to run

```bash
# from the repo root
python keyword-keyword/comparison.py                     # DATASET from graph_utils.py
python keyword-keyword/comparison.py mecklenburg          # or pass it explicitly
python keyword-keyword/comparison.py all                  # merged, all 4 regions

python keyword-keyword/louvain_analysis_zoomed.py --zoom-hexe
python keyword-keyword/louvain_analysis_zoomed.py --zoom-werewolf --exclude-anchor
python keyword-keyword/louvain_analysis_zoomed.py --dataset all --zoom-werewolf

python keyword-keyword/viz/build_explorer_html.py         # refresh the interactive viewer
```

## Known limitations 

- We did not machine-translate all ~36k keywords across 4 languages --
  `synonyms.json` covers a handful of concepts we're confident about,
  everything else stays region-specific unless someone extends the
  dictionary.
- Girvan-Newman on the merged "all" dataset needs an auto-raised weight
  threshold to stay fast (see `_auto_threshold` in
  `girvan_newman_analysis.py`) and still explores far fewer dendrogram
  splits relative to the graph's size than it does on a single region --
  treat GN results on "all" as exploratory, and prefer per-region GN runs
  for anything you want to lean on.
- BigCLAM's unweighted top-degree filtering can drop a keyword (including,
  on one run, Werewolf itself) out of the subgraph entirely before the
  algorithm even runs -- if a keyword you expect to see is "not found", check
  whether it survived the `MIN_WEIGHT_BIGCLAM` / `MAX_NODES_BIGCLAM` filters
  first, that's the likely reason, not a modeling failure.