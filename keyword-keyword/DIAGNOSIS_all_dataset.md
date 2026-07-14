# Why "all" (merged, 4 regions) looks worse than a single region -- diagnosis

Short version: it's **not** a bug in reading the data, and it's **not**
primarily a translation problem either (though that's still worth doing).
The dominant cause is that the merged graph is structurally close to **four
separate graphs stitched together by only 8 shared keywords**, combined
with a well-known weakness of modularity optimization on large graphs (the
"resolution limit"). Both were confirmed with actual numbers below, not
guessed.

## The numbers

| | Mecklenburg alone | "all" (4 regions merged) |
|---|---|---|
| Nodes | 1,259 | 18,412 |
| Louvain Q | 0.754 | 0.518 |
| Louvain communities | 14 | 32-35 (varies slightly run to run) |
| Girvan-Newman Q | 0.760 | 0.113 |
| Girvan-Newman communities | 10 | 29 (on a 266-node subgraph only) |
| Louvain vs GN agreement (ARI/NMI) | 0.746 / 0.833 | 0.225 / 0.276 |

## Finding 1 (confirmed): the merged graph is almost four disconnected graphs

Of 18,412 nodes, only **8** are cross-region "concept" nodes (from
`synonyms.json`). Of 1,185,007 edges, only **29,061 (2.5%)** touch one of
those 8 nodes at all. The other 97.5% of edges connect two keywords from
the *same* region.

Louvain's output: **34 of the 35 communities are >95% single-region** (one community is 99% Netherlands,
another 100% Denmark, another 100% Mecklenburg, and so on -- only Iceland's
one small community sits at 75% purity). So Louvain isn't really finding
"cross-region themes" on `all` right now -- it's mostly rediscovering each
region's own graph separately, glued together by almost nothing. That
alone explains why the community *count* goes up (you're roughly summing
four regions' worth of structure) while overall Q looks unremarkable
(the global partition is dominated by weak, mostly-irrelevant cross-region
noise around those 8 bridge nodes).

## Finding 2 (confirmed): the resolution limit, not just noise

Expected Mecklenburg's rich internal structure (14 communities) to
still show up *inside* the merged graph, just alongside the other regions'
communities. It doesn't. Inside `all`, at the default resolution, **nearly
all of Mecklenburg's ~1,260 nodes end up in ONE community**, not 14. This
is the textbook "resolution limit" of modularity optimization (Fortunato &
Barthelemy): once the total graph is much bigger, splitting a
sub-community further stops paying off in the modularity score, even where
real internal structure exists, so Louvain merges it into one blob.

Tested raising Louvain's `resolution` parameter (now exposed as an
argument to `run_louvain()`) to counteract this:

| resolution | communities | standard Q | Mecklenburg's own community count inside `all` |
|---|---|---|---|
| 1.0 (default) | 35 | 0.518 | 1 (blob of ~1,135 nodes) |
| 1.5 | 22 | 0.472 | -- |
| 2.0 | 17 | 0.310 | 8 |
| 3.0 | 67 | 0.197 | 9 |
| 5.0 | 246 | 0.147 | 10 (largest piece down to 514 nodes) |

It's a real, usable knob (Mecklenburg's structure does start reappearing),
but it's not a clean fix: a single global resolution value can't be tuned
separately per region, so pushing it up to recover Mecklenburg's structure
fragments Netherlands and Denmark far more aggressively than we'd want.


## Finding 3 (tested, and it did NOT help)

First guess was that a handful of extremely generic keywords were
diluting the graph: `witch`, `ghost`, `devil`, `church` each appear in
6-8% of ALL 70,249 stories, and several very generic Dutch tags (`dood` =
death, `man`, `huis` = house, `nacht` = night, `sterven` = to die) sit at
3-6%. That's a classic "these behave like stopwords" pattern in
co-occurrence networks, so we tried stripping keywords above a document
frequency cutoff before building the graph, expecting modularity to go up.

It didn't, reliably:

| cutoff (keywords dropped) | nodes | edges | Q |
|---|---|---|---|
| none | 18,412 | 1,185,007 | 0.518 |
| >1% of stories (60 dropped) | 17,925 | 1,046,949 | 0.500 |
| >0.5% of stories (238 dropped) | 10,893 | 227,132 | **0.354** (worse) |
| >0.25% of stories (884 dropped) | 9,750 | 120,582 | 0.451 |

Modularity got *worse* at a moderate cutoff before partially recovering at
a stricter one -- these "generic" keywords are carrying real co-occurrence
signal (witch/ghost/devil/church are genuine core folklore motifs, not
noise), so blindly stripping them isn't the fix. We're reporting this as a
tested-and-rejected hypothesis rather than silently dropping it, so nobody
re-discovers the same dead end. `document_frequency_ratio` is still
computed and attached to every node (visible in the viewer's node detail
panel) so you can inspect this deliberately if you want to experiment
further yourselves.

## Is translation/more synonyms the fix, then?

Partially, and it's still worth doing, but be precise about what it would
and wouldn't fix. Expanding `synonyms.json` would raise the 2.5%
cross-region-edge figure and let Louvain find genuine cross-region theme
communities (right now it structurally can't, there's almost no bridge to
find them with). It would **not** by itself fix the resolution-limit
problem (Finding 2), which is about graph *size*, not language coverage --
even a perfectly translated, fully unified vocabulary across all 4 regions
would still hit the same resolution limit once the graph is this much
bigger than Mecklenburg alone.

Realistic translation coverage: we can't machine-translate ~36,000
keywords across 4 languages from inside this environment (no translation
API access here), so `synonyms.json` stays a manually-curated, extensible
list. The highest-leverage next step for this specific problem is
whatever Burhan's embedding-model work on the full scraped story text
turns into -- semantic/structural similarity across languages is a much
better tool for this than string-pattern matching, once it exists.

