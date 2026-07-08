import csv
import json
from collections import defaultdict
import networkx as nx
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET = "mecklenburg"   # mecklenburg | iceland | denmark | netherlands
MIN_COOCCURRENCE = 2      # minimum times two keywords must co-occur to form an edge

NODES_FILE = BASE_DIR / f"isebel-{DATASET}-nodes.csv"
EDGES_FILE = BASE_DIR / f"isebel-{DATASET}-edges.csv"


def load_graph() -> tuple[nx.Graph, dict[str, str]]:
    """
    Returns:
        G           — keyword co-occurrence graph (nodes=keyword IDs, edge weight=co-occurrence count)
        keyword_text — dict mapping keyword node ID → human-readable keyword string
    """
    # 1. Load node labels and keyword text
    node_label: dict[str, str] = {}
    keyword_text: dict[str, str] = {}

    with open(NODES_FILE, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            nid, label, props = row[0], row[1], row[2]
            node_label[nid] = label
            if label == "keyword":
                try:
                    p = json.loads(props)
                    text = p.get("keyword") or p.get("text") or p.get("name") or p.get("label") or str(p)
                except Exception:
                    text = props
                keyword_text[nid] = str(text)

    print(f"[{DATASET}] Loaded {len(node_label)} nodes, {len(keyword_text)} keywords")

    # 2. Build story → keyword mapping from "content" edges
    story_keywords: dict[str, set] = defaultdict(set)

    with open(EDGES_FILE, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            src, dst, label = row[0], row[1], row[2]
            if label == "content":
                story_keywords[src].add(dst)

    print(f"[{DATASET}] Stories with keywords: {len(story_keywords)}")

    # 3. Count keyword co-occurrences across stories
    cooc: dict[tuple, int] = defaultdict(int)

    for story, kws in story_keywords.items():
        kws = list(kws)
        for i in range(len(kws)):
            for j in range(i + 1, len(kws)):
                a, b = kws[i], kws[j]
                if a > b:
                    a, b = b, a
                cooc[(a, b)] += 1

    # 4. Build NetworkX graph with weight filter
    G = nx.Graph()
    for (a, b), w in cooc.items():
        if w >= MIN_COOCCURRENCE:
            G.add_edge(a, b, weight=w)

    # Keep only the largest connected component for clean analysis
    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()

    print(f"[{DATASET}] Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G, keyword_text