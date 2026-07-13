python keyword-keyword/comparison.py
python keyword-keyword/louvain_analysis_zoomed.py --zoom-hexe
python keyword-keyword/louvain_analysis_zoomed.py --zoom-werewolf
python ISEBEL_download_wossidia_story_htmls.py --input isebel-mecklenburg-nodes.csv
python ISEBEL_download_wossidia_story_htmls.py --input isebel-denmark-nodes.csv
python ISEBEL_download_wossidia_story_htmls.py --input isebel-iceland-nodes.csv
python ISEBEL_download_wossidia_story_htmls.py --iceland-bruteforce-sagnagrunnur --sagnagrunnur-start 0 --sagnagrunnur-end 10000
python ISEBEL_download_wossidia_story_htmls.py --input isebel-netherlands-nodes.csv
---

## Project Context

This is a **graph mining project from the University of Rostock** analyzing folk narrative datasets from [ISEBEL](https://search.isebel.eu/) (Intelligent Search Engine for Belief Legends).

### What it does
- Builds **keyword co-occurrence graphs** from folktales across 4 European regions (Mecklenburg, Denmark, Netherlands, Iceland)
- Runs **community detection algorithms** (Louvain, Girvan-Newman, BigCLAM) to find thematic clusters in the stories
- Allows **zooming into specific motif communities** (e.g., werewolf/Werwolf, witch/Hexe)

### Data flow
1. Stories come from ISEBEL/WossiDiA as CSV exports with nodes (stories, keywords, persons, places, dates) and edges (relationships)
2. graph_utils.py builds a keyword co-occurrence graph: two keywords are connected if they appear in the same story, edge weight = how often they co-occur
3. Community detection finds groups of related keywords → these represent thematic motifs in the folklore

### Key files
| File | Purpose |
|------|---------|
| graph_utils.py | Loads CSV data, builds NetworkX graph (configurable `DATASET` variable) |
| louvain_analysis_zoomed.py | Louvain with `--zoom-werewolf` / `--zoom-hexe` / `--zoom-community N` |
| girvan_newman_analysis.py | Girvan-Newman divisive clustering |
| bigclam_analysis.py | BigCLAM overlapping communities |
| comparison.py | Cross-region comparison |
| download_wossidia_story_htmls.py | Fetches story HTML from ISEBEL |
| merge_graph_csvs.py | Merges regional CSV datasets |

### Research goals
Comparing **thematic folklore patterns** across Northern European regions — for example, do werewolf and witch motifs form distinct communities in Mecklenburg vs. Denmark vs. Iceland?