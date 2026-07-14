"""
Scans outputs/<dataset>/graph_export_<dataset>.json (written by
comparison.py, or by ex. louvain_analysis.py alone) across
every dataset that's been run, and bakes them all into one standalone file:
keyword-keyword/viz/network_explorer.html.

Run this again after any new comparison.py / louvain_analysis.py run to
refresh it.
"""

import json
from pathlib import Path

VIZ_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = VIZ_DIR.parent   # keyword-keyword/viz -> keyword-keyword
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUT_FILE = VIZ_DIR / "network_explorer.html"


def build():
    exports = {}
    for export_file in sorted(OUTPUT_DIR.glob("*/graph_export_*.json")):
        dataset = export_file.stem.replace("graph_export_", "")
        with open(export_file, encoding="utf-8") as fh:
            exports[dataset] = json.load(fh)

    if not exports:
        raise SystemExit(
            "No outputs/<dataset>/graph_export_*.json found -- run comparison.py "
            "(or louvain_analysis.py) first."
        )

    data_json = json.dumps(exports, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__DATA__", data_json)
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_FILE} with datasets: {list(exports.keys())}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ISEBEL -- thematic community explorer</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<style>
  :root{
    --ink:#14171f;
    --ink-2:#1c2029;
    --panel:#20242f;
    --parchment:#f3ecdb;
    --parchment-dim:#b9b2a0;
    --gold:#c9a24b;
    --rust:#b3563b;
    --line:#333a4a;
    --text-soft:#8891a3;
  }
  *{box-sizing:border-box;}
  html,body{margin:0;height:100%;background:var(--ink);color:var(--parchment);
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
    overflow:hidden;}
  #app{display:grid;grid-template-columns:290px 1fr 300px;grid-template-rows:auto 1fr;height:100%;}

  header{grid-column:1/4;display:flex;align-items:center;gap:16px;flex-wrap:wrap;
    padding:12px 20px;border-bottom:1px solid var(--line);background:var(--ink-2);}
  header h1{font-size:16px;letter-spacing:.01em;margin:0;font-weight:600;color:var(--parchment);
    white-space:nowrap;}
  .select-group{display:flex;align-items:center;gap:6px;}
  .select-group label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-soft);}
  header select{background:var(--panel);color:var(--parchment);
    border:1px solid var(--line);padding:6px 10px;font-family:inherit;font-size:12.5px;
    border-radius:4px;cursor:pointer;}
  header select:focus{outline:1px solid var(--gold);}
  .stats{display:flex;gap:16px;font-size:11.5px;color:var(--text-soft);margin-left:auto;}
  .stats .stat{display:flex;flex-direction:column;align-items:flex-end;line-height:1.3;}
  .stats .stat b{color:var(--gold);font-weight:700;font-size:13px;}
  .stats .stat span{font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;}

  aside{padding:16px 18px;overflow-y:auto;border-right:1px solid var(--line);font-size:13px;background:var(--ink);}
  aside.right{border-right:none;border-left:1px solid var(--line);}
  aside::-webkit-scrollbar{width:8px;}
  aside::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px;}

  h2.side-title{font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;color:var(--gold);
    margin:0 0 10px;font-weight:700;}

  #search{width:100%;padding:8px 10px;background:var(--panel);border:1px solid var(--line);
    color:var(--parchment);border-radius:4px;font-family:inherit;font-size:13px;margin-bottom:14px;}
  #search::placeholder{color:var(--text-soft);}
  #search:focus{outline:1px solid var(--gold);}

  .legend-item{display:flex;align-items:center;gap:8px;padding:6px 7px;border-radius:4px;
    cursor:pointer;transition:background .12s, opacity .12s;font-size:12.5px;line-height:1.3;}
  .legend-item:hover{background:rgba(255,255,255,.05);}
  .legend-item.dimmed{opacity:.32;}
  .swatch{width:11px;height:11px;border-radius:50%;flex:none;}
  .legend-item .lbl{color:var(--parchment-dim);}
  .legend-item .n{margin-left:auto;color:var(--text-soft);font-size:11px;}

  #top-keywords{list-style:none;margin:0;padding:0;font-size:12.5px;color:var(--parchment-dim);}
  #top-keywords li{display:flex;justify-content:space-between;padding:4px 2px;border-bottom:1px solid var(--line);}
  #top-keywords li span.rank{color:var(--text-soft);width:20px;flex:none;}

  #detail{font-size:12.5px;color:var(--parchment-dim);line-height:1.6;}
  #detail .kw{font-size:16px;color:var(--gold);font-weight:700;margin-bottom:6px;}
  #detail .row{margin:6px 0;}
  #detail .row b{color:var(--parchment);}
  #detail .region-pill{display:inline-block;background:var(--panel);border:1px solid var(--line);
    border-radius:10px;padding:1px 8px;margin:2px 3px 0 0;font-size:11px;color:var(--text-soft);}
  #detail .region-pill.cross{border-color:var(--rust);color:var(--rust);}
  #detail-empty{color:var(--text-soft);font-style:italic;}

  #canvas-wrap{position:relative;overflow:hidden;background:
    radial-gradient(ellipse at 50% 40%, #1a1e28 0%, var(--ink) 72%);cursor:grab;}
  #canvas-wrap.panning{cursor:grabbing;}
  svg{width:100%;height:100%;display:block;}
  .link{stroke:#4a5266;stroke-opacity:.32;}
  .node circle{stroke:var(--ink);stroke-width:1.2px;cursor:pointer;}
  .node.cross circle{stroke:var(--gold);stroke-width:2px;stroke-dasharray:2,1.5;}
  .node.unclustered circle{fill:#3a4050 !important;stroke:#565f74;stroke-dasharray:1.5,1.5;}
  .node text{fill:var(--parchment-dim);font-size:10px;pointer-events:none;
    paint-order:stroke;stroke:var(--ink);stroke-width:3px;}
  .node.faded{opacity:.07;}
  .link.faded{opacity:.025;}
  .node:hover circle{filter:brightness(1.25);}

  #tooltip{position:absolute;pointer-events:none;background:var(--panel);border:1px solid var(--gold);
    padding:7px 11px;border-radius:5px;font-size:12px;color:var(--parchment);display:none;
    max-width:240px;z-index:5;box-shadow:0 4px 14px rgba(0,0,0,.4);}

  #hint{position:absolute;bottom:14px;left:14px;font-size:10.5px;color:var(--text-soft);
    background:rgba(20,23,31,.75);padding:6px 10px;border-radius:4px;letter-spacing:.02em;}
  #reset-view{position:absolute;bottom:14px;right:14px;background:var(--panel);color:var(--parchment-dim);
    border:1px solid var(--line);padding:6px 12px;border-radius:4px;font-size:11.5px;cursor:pointer;}
  #reset-view:hover{border-color:var(--gold);color:var(--gold);}
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>ISEBEL thematic constellation</h1>
    <div class="select-group">
      <label for="dataset-select">Dataset</label>
      <select id="dataset-select"></select>
    </div>
    <div class="select-group">
      <label for="algo-select">Algorithm</label>
      <select id="algo-select">
        <option value="louvain">Louvain</option>
        <option value="girvan_newman">Girvan-Newman</option>
      </select>
    </div>
    <div class="stats">
      <div class="stat"><b id="stat-q">-</b><span>Modularity Q</span></div>
      <div class="stat"><b id="stat-comm">-</b><span>Communities</span></div>
      <div class="stat"><b id="stat-nodes">-</b><span>Nodes shown / total</span></div>
    </div>
  </header>

  <aside>
    <h2 class="side-title">Communities</h2>
    <input id="search" placeholder="search a keyword (e.g. werewolf)..."/>
    <div id="legend"></div>
  </aside>

  <div id="canvas-wrap">
    <svg></svg>
    <div id="tooltip"></div>
    <div id="hint">scroll/pinch to zoom &middot; drag background to pan &middot; drag a node to move it &middot; click a node to isolate its neighbours</div>
    <button id="reset-view">Reset view</button>
  </div>

  <aside class="right">
    <h2 class="side-title">Node detail</h2>
    <div id="detail"><div id="detail-empty">Click or search a keyword for details.</div></div>
    <h2 class="side-title" style="margin-top:22px">Top keywords overall</h2>
    <ol id="top-keywords"></ol>
  </aside>
</div>

<script>
const ALL_DATA = __DATA__;

const PALETTE = ["#c9a24b","#8a9a5b","#b3563b","#5c7a9e","#a0678c","#6ba3a0",
                 "#c98a4b","#7d7db0","#9a5b5b","#5b9a7d","#b0a06b","#6b8ac9",
                 "#9a7db0","#7db09a","#c9705b","#8ab06b","#d4b25e","#7396b5"];

let state = {
  dataset: null, algo: "louvain",
  nodes: [], links: [], nodeById: new Map(),
  hiddenComms: new Set(), selected: null, raw: null,
};

const svg = d3.select("svg");
const g = svg.append("g");
const linkLayer = g.append("g").attr("class", "links");
const nodeLayer = g.append("g").attr("class", "nodes");
const tooltip = d3.select("#tooltip");
const canvasWrap = document.getElementById("canvas-wrap");

const zoomBehavior = d3.zoom()
  .scaleExtent([0.1, 8])
  .on("start", () => canvasWrap.classList.add("panning"))
  .on("zoom", (ev) => g.attr("transform", ev.transform))
  .on("end", () => canvasWrap.classList.remove("panning"));
svg.call(zoomBehavior);
svg.on("click", (ev) => { if (ev.target === svg.node()) resetHighlight(); });

document.getElementById("reset-view").addEventListener("click", () => {
  svg.transition().duration(400).call(zoomBehavior.transform, d3.zoomIdentity);
});

function colorFor(commId){
  if (commId === null || commId === undefined) return "#3a4050";
  return PALETTE[((commId % PALETTE.length) + PALETTE.length) % PALETTE.length];
}

function sizeOf(container){
  const box = container.node().getBoundingClientRect();
  return { w: box.width || 900, h: box.height || 700 };
}

// ---------------------------------------------------------------------------
// Layout: computed ONCE per dataset with a force simulation that we run
// synchronously to completion, then throw away. Nothing moves on its own
// after this -- panning/zooming/dragging never re-triggers physics.
// ---------------------------------------------------------------------------
function computeStaticLayout(nodes, links, w, h){
  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id)
      .distance(l => 70 - Math.min(45, (l.weight || 1)))
      .strength(0.25))
    .force("charge", d3.forceManyBody().strength(-110))
    .force("center", d3.forceCenter(w / 2, h / 2))
    .force("collide", d3.forceCollide(d => radiusFor(d) + 5))
    .stop();

  const nTicks = 320;
  for (let i = 0; i < nTicks; i++) sim.tick();
  sim.stop();
}

let currentRadiusScale = null;
function radiusFor(d){
  return currentRadiusScale ? currentRadiusScale(d.degree) : 6;
}

function loadDataset(name){
  state.dataset = name;
  state.hiddenComms = new Set();
  state.selected = null;

  const d = ALL_DATA[name];
  state.raw = d;
  state.nodes = d.nodes.map(n => ({ ...n }));
  state.links = d.edges.map(e => ({ ...e }));
  state.nodeById = new Map(state.nodes.map(n => [n.id, n]));

  const { w, h } = sizeOf(d3.select("#canvas-wrap"));
  const maxDeg = d3.max(state.nodes, n => n.degree) || 1;
  currentRadiusScale = d3.scaleSqrt().domain([0, maxDeg]).range([4, 26]);

  computeStaticLayout(state.nodes, state.links, w, h);
  buildTopKeywords(d.top_keywords_overall || []);
  applyAlgorithm(state.algo);
}

function communityOf(node){
  return node.communities ? node.communities[state.algo] : null;
}

function applyAlgorithm(algo){
  state.algo = algo;
  state.hiddenComms = new Set();
  state.selected = null;
  document.getElementById("detail").innerHTML =
    '<div id="detail-empty">Click or search a keyword for details.</div>';

  const info = state.raw.algorithms[algo];
  document.getElementById("stat-q").textContent = (info && info.modularity != null) ? info.modularity.toFixed(3) : "-";
  document.getElementById("stat-comm").textContent = (info && info.n_communities != null) ? info.n_communities : "-";
  document.getElementById("stat-nodes").textContent = state.raw.shown_nodes + " / " + state.raw.total_graph_nodes;

  buildLegend();
  renderGraph();
}

function buildLegend(){
  const nodesWithComm = state.nodes.map(n => ({ ...n, _comm: communityOf(n) }));
  const known = nodesWithComm.filter(n => n._comm !== null && n._comm !== undefined);
  const unknownCount = nodesWithComm.length - known.length;

  const byComm = d3.rollups(known, v => v.length, n => n._comm)
    .sort((a, b) => d3.descending(a[1], b[1]));

  const legend = document.getElementById("legend");
  legend.innerHTML = "";
  byComm.forEach(([comm, count]) => {
    const topNode = known.filter(n => n._comm === comm)
      .sort((a, b) => d3.descending(a.degree, b.degree))[0];
    const row = document.createElement("div");
    row.className = "legend-item";
    row.dataset.comm = comm;
    row.innerHTML = `<span class="swatch" style="background:${colorFor(comm)}"></span>
      <span class="lbl">${topNode ? topNode.label : "community " + comm}</span><span class="n">${count}</span>`;
    row.addEventListener("click", () => toggleCommunity(comm));
    legend.appendChild(row);
  });

  if (unknownCount > 0){
    const row = document.createElement("div");
    row.className = "legend-item";
    row.dataset.comm = "__none__";
    row.innerHTML = `<span class="swatch" style="background:#3a4050;border:1px dashed #7a8296"></span>
      <span class="lbl">not in this algorithm's subgraph</span><span class="n">${unknownCount}</span>`;
    row.addEventListener("click", () => toggleCommunity(null));
    legend.appendChild(row);
  }
}

function toggleCommunity(comm){
  const key = comm === null ? "__none__" : comm;
  if (state.hiddenComms.has(key)) state.hiddenComms.delete(key); else state.hiddenComms.add(key);
  document.querySelectorAll(".legend-item").forEach(el => {
    const k = el.dataset.comm === "__none__" ? "__none__" : +el.dataset.comm;
    el.classList.toggle("dimmed", state.hiddenComms.has(k));
  });
  applyFade();
}

function isHidden(node){
  const c = communityOf(node);
  const key = (c === null || c === undefined) ? "__none__" : c;
  return state.hiddenComms.has(key);
}

function applyFade(){
  nodeLayer.selectAll("g.node").classed("faded", d => isHidden(d));
  linkLayer.selectAll("line").classed("faded", l => isHidden(l.source) || isHidden(l.target));
}

function renderGraph(){
  linkLayer.selectAll("*").remove();
  nodeLayer.selectAll("*").remove();

  linkLayer.selectAll("line").data(state.links).join("line")
    .attr("class", "link")
    .attr("stroke-width", l => Math.min(3, 0.4 + Math.log(1 + (l.weight || 1)) * 0.4))
    .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x).attr("y2", d => d.target.y);

  const maxDeg = d3.max(state.nodes, n => n.degree) || 1;

  nodeLayer.selectAll("g.node").data(state.nodes, d => d.id).join(enter => {
    const gEnter = enter.append("g")
      .attr("class", d => "node" + (d.cross_region ? " cross" : "") +
        ((communityOf(d) === null || communityOf(d) === undefined) ? " unclustered" : ""))
      .attr("transform", d => `translate(${d.x},${d.y})`);
    gEnter.append("circle")
      .attr("r", d => radiusFor(d))
      .attr("fill", d => colorFor(communityOf(d)))
      .on("mouseover", (ev, d) => showTooltip(ev, d))
      .on("mousemove", (ev) => moveTooltip(ev))
      .on("mouseout", hideTooltip)
      .on("click", (ev, d) => { ev.stopPropagation(); selectNode(d); });
    gEnter.append("text")
      .attr("dy", d => -(radiusFor(d) + 4))
      .attr("text-anchor", "middle")
      .text(d => d.degree > maxDeg * 0.32 ? d.label : "");
    gEnter.call(dragBehavior());
    return gEnter;
  });

  applyFade();

  function dragBehavior(){
    return d3.drag()
      .on("start", function(){ d3.select(this).raise(); })
      .on("drag", function(ev, d){
        d.x = ev.x; d.y = ev.y;
        d3.select(this).attr("transform", `translate(${d.x},${d.y})`);
        linkLayer.selectAll("line")
          .filter(l => l.source.id === d.id || l.target.id === d.id)
          .attr("x1", l => l.source.x).attr("y1", l => l.source.y)
          .attr("x2", l => l.target.x).attr("y2", l => l.target.y);
      });
  }
}

function showTooltip(ev, d){
  const comm = communityOf(d);
  const commLabel = (comm === null || comm === undefined) ? "not clustered here" : ("community " + comm);
  tooltip.style("display", "block").html(
    `<b>${d.label}</b><br/>${commLabel} &middot; degree ${d.degree}<br/>${d.regions.join(", ") || "-"}`
  );
  moveTooltip(ev);
}
function moveTooltip(ev){
  const box = document.getElementById("canvas-wrap").getBoundingClientRect();
  tooltip.style("left", (ev.clientX - box.left + 14) + "px").style("top", (ev.clientY - box.top + 10) + "px");
}
function hideTooltip(){ tooltip.style("display", "none"); }

function selectNode(d){
  state.selected = d;
  const neighborIds = new Set([d.id]);
  state.links.forEach(l => {
    if (l.source.id === d.id) neighborIds.add(l.target.id);
    if (l.target.id === d.id) neighborIds.add(l.source.id);
  });
  nodeLayer.selectAll("g.node").classed("faded", n => !neighborIds.has(n.id));
  linkLayer.selectAll("line").classed("faded", l => !(neighborIds.has(l.source.id) && neighborIds.has(l.target.id)));
  renderDetail(d, neighborIds.size - 1);
}

function resetHighlight(){
  state.selected = null;
  applyFade();
  document.getElementById("detail").innerHTML =
    '<div id="detail-empty">Click or search a keyword for details.</div>';
}

function renderDetail(d, neighborCount){
  const comm = communityOf(d);
  const commLine = (comm === null || comm === undefined)
    ? "Not part of this algorithm's analyzed subgraph"
    : `Community ${comm}`;
  const regionsHtml = d.regions.map(r => `<span class="region-pill${d.cross_region ? ' cross' : ''}">${r}</span>`).join(" ");
  const docFreqPct = ((d.document_frequency_ratio || 0) * 100).toFixed(1);
  document.getElementById("detail").innerHTML = `
    <div class="kw">${d.label}</div>
    <div class="row"><b>${state.algo === 'louvain' ? 'Louvain' : 'Girvan-Newman'}:</b> ${commLine}</div>
    <div class="row"><b>Degree (co-occurrences):</b> ${d.degree}</div>
    <div class="row"><b>Neighbours shown:</b> ${neighborCount}</div>
    <div class="row"><b>Appears in:</b> ${docFreqPct}% of stories in this dataset</div>
    <div class="row"><b>Regions:</b><br/>${regionsHtml}</div>
    ${d.cross_region ? '<div class="row" style="color:var(--rust)">cross-region concept (canonicalized via synonyms.json)</div>' : ''}
    ${docFreqPct > 3 ? '<div class="row" style="color:var(--text-soft)">very generic keyword (appears broadly) -- treat as a weak thematic signal</div>' : ''}
  `;
}

function buildTopKeywords(list){
  const ol = document.getElementById("top-keywords");
  ol.innerHTML = "";
  list.forEach((label, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="rank">${i + 1}.</span><span>${label}</span>`;
    ol.appendChild(li);
  });
}

document.getElementById("search").addEventListener("input", (ev) => {
  const q = ev.target.value.trim().toLowerCase();
  if (!q){ resetHighlight(); return; }
  const match = state.nodes.find(n => n.label.toLowerCase().includes(q));
  if (match) selectNode(match);
});

document.getElementById("algo-select").addEventListener("change", (ev) => {
  applyAlgorithm(ev.target.value);
});

const sel = document.getElementById("dataset-select");
Object.keys(ALL_DATA).forEach(name => {
  const opt = document.createElement("option");
  opt.value = name; opt.textContent = name;
  sel.appendChild(opt);
});
sel.addEventListener("change", () => loadDataset(sel.value));

window.addEventListener("resize", () => {
  // re-render only (no relayout), so a browser resize doesn't reshuffle nodes
  renderGraph();
});

loadDataset(Object.keys(ALL_DATA)[0]);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
