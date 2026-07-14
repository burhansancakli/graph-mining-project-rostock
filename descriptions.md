## Labels in this dataset

### Node labels
These are types of nodes in the graph.
- `date`
  - A node representing a date, likely the date of narration or collection.
- `keyword`
  - A thematic or subject keyword associated with a story.
- `person`
  - A node representing an individual (e.g. narrator, informant, collector).
- `place`
  - A geographic or location node tied to a story.
- `story`
  - A story node that is being told/recorded.

### Edge labels
These are relationship types connecting nodes.
- `collector`
  - Connects a story to the person who collected or recorded it.
- `content`
  - Connects a story or narration to its content node or content entity. It's mostly just keyword
- `date-of-narration`
  - Links a story to the date when it was narrated.
- `informant`
  - Links a story to the person who provided the material or information. Most likely the same with narrator.
- `keyword-of-narration`
  - It's broken, only exists in co-occurence.csv
- `narrator`
  - Links a story to the person who narrated or told it.
- `place-of-narration`
  - Links a story to the place where it was narrated.

### How to read them
- Node labels describe what the entity is.
- Edge labels describe what the relationship means.

So in short:
- `person`, `date`, `place`, `keyword`, `story` = node types
- `collector`, `content`, `date-of-narration`, `informant`, `keyword-of-narration`, `narrator`, `place-of-narration` = relationship roles between those nodes

## Label availability by file

### Edge files
- isebel-denmark-edges.csv
  - present: `content`, `date-of-narration`, `narrator`, `place-of-narration`
  - missing: `collector`, `informant`, `keyword-of-narration`
- isebel-iceland-co-occurence-edges.csv
  - present: `date-of-narration`, `keyword-of-narration`, `place-of-narration`
  - missing: `collector`, `content`, `informant`, `narrator`
  - Seems like it is broken
- isebel-iceland-edges.csv
  - present: `collector`, `content`, `informant`, `place-of-narration`
  - missing: `date-of-narration`, `keyword-of-narration`, `narrator`
- isebel-mecklenburg-edges.csv
  - present: `content`, `date-of-narration`, `narrator`, `place-of-narration`
  - missing: `collector`, `informant`, `keyword-of-narration`
- isebel-netherlands-edges.csv
  - present: `content`, `date-of-narration`, `narrator`, `place-of-narration`
  - missing: `collector`, `informant`, `keyword-of-narration`

### Node files
- isebel-denmark-nodes.csv
  - present: `date`, `keyword`, `person`, `place`, `story`
  - missing: none
- isebel-iceland-co-occurence-nodes.csv
  - present: `date`, `keyword`, `person`, `place`
  - missing: `story`
- isebel-iceland-nodes.csv
  - present: `keyword`, `person`, `place`, `story`
  - missing: `date`
- isebel-mecklenburg-nodes.csv
  - present: `date`, `keyword`, `person`, `place`, `story`
  - missing: none
- isebel-netherlands-nodes.csv
  - present: `date`, `keyword`, `person`, `place`, `story`
  - missing: none
