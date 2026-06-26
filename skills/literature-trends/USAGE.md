# Literature Trends Skill — Usage Reference

## Overview

The literature-trends skill applies **abductive argumentation analysis** to a set of keyword-tagged scientific papers, tracing how explanatory hypotheses emerge, evolve, and replace each other across time windows.

**Abductive reasoning** (inference to the best explanation) frames each time window as: *Given these observations, what hypothesis was proposed? What evidence supported it? What did it leave unexplained?* The genealogy links between windows capture how the field's explanatory framework evolved.

---

## Workflow

### 1. Prerequisites

Papers must already be ingested and tagged with a keyword. Typically:
```bash
# Ingest and cluster a corpus
uv run python .claude/skills/scientific-literature/scientific_literature.py \
    search --source epmc --query "partial reprogramming aging" --collection "My Corpus"
uv run python .claude/skills/scientific-literature/scientific_literature.py \
    cluster --collection "collection-id" --min-cluster-size 15 \
    --labels 0:partial-reprogramming 1:senescence ...
```

### 2. Fetch papers by keyword in time windows

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py \
    list-by-keyword --keyword "partial-reprogramming" \
    --collection "collection-id" \
    --year-from 2016 --year-to 2018 2>/dev/null
```

### 3. Do the abductive analysis (Claude reads abstracts)

For each time window, identify:

| Field | Description |
|---|---|
| `phenomenon` | What observation dominated this window and needed explanation? |
| `hypothesis` | What mechanistic/theoretical explanation was proposed? |
| `evidence` | 2-3 key experimental results supporting it |
| `gaps` | What the hypothesis left unexplained |
| `genealogy_type` | `null` / `refines` / `extends` / `challenges` / `supersedes` |
| `genealogy_description` | How this window relates to the prior window's hypothesis |

**Genealogy types:**
- `refines` — same mechanism, better specified (e.g., identifies PRC2 as the target)
- `extends` — same mechanism applied to new domains (e.g., from progeroid to wild-type aging)
- `challenges` — new evidence undermines the prior hypothesis
- `supersedes` — prior hypothesis replaced by a fundamentally different one

### 4. Create the thread

```bash
uv run python .claude/skills/literature-trends/literature_trends.py create-thread \
    --name "Partial Reprogramming Trend Analysis" \
    --keyword "partial-reprogramming" \
    --source-collection "collection-925280f3c398"
# Returns: { "thread_id": "trend-thread-abc123", ... }
```

### 5. Record hypothesis notes per window

```bash
uv run python .claude/skills/literature-trends/literature_trends.py record-hypothesis \
    --thread "trend-thread-abc123" \
    --window "2016-2018" \
    --title "Hypothesis: Safe Window for Epigenetic Rejuvenation (2016-2018)" \
    --subject "collection-925280f3c398" \
    --content "## Window 2016-2018\n\n**Phenomenon:** ...\n\n**Hypothesis:** ...\n\n**Evidence:** ...\n\n**Gaps:** ..."
# Returns: { "note_id": "trend-hyp-note-def456", ... }
```

### 6. Record genealogy edges

```bash
uv run python .claude/skills/literature-trends/literature_trends.py record-genealogy \
    --predecessor "trend-hyp-note-2016" \
    --successor "trend-hyp-note-2019" \
    --type "extends" \
    --description "Extends safe-window hypothesis from progeroid to wild-type aging; introduces information theory of aging framework"
```

### 7. Show the full genealogy chain

```bash
uv run python .claude/skills/literature-trends/literature_trends.py show-thread \
    --thread "trend-thread-abc123"
```

---

## Data Model

### TypeDB entities

| Entity | Parent | Key attributes |
|---|---|---|
| `trend-thread` | `collection` | `id @key`, `name`, `keyword`, `trend-window` |
| `trend-hypothesis-note` | `note` | `id @key`, `name`, `content`, `trend-window`, `abductive-role` |

`trend-thread` inherits: `id @key`, `name`, `description`, `provenance`, `created-at`,
plays `collection-membership:collection`, `aboutness:subject`.

`trend-hypothesis-note` inherits from `note`: `id @key`, `name`, `content`, `confidence`,
`provenance`, `created-at`, plays `aboutness:note`, `note-threading:parent-note/child-note`,
`evidence-chain:claim/evidence`, `collection-membership:member`.

### TypeDB relations

| Relation | Roles | Attributes |
|---|---|---|
| `hypothesis-genealogy` | `predecessor`, `successor` | `genealogy-type`, `confidence`, `provenance` |
| `collection-membership` | `collection`, `member` | `created-at` |
| `aboutness` | `note`, `subject` | `created-at` |

### Attribute values

- `abductive-role`: `"phenomenon"` | `"hypothesis"` | `"evidence"` | `"gap"` | `"full-analysis"`
- `genealogy-type`: `"refines"` | `"extends"` | `"challenges"` | `"supersedes"`
- `trend-window`: free string, e.g. `"2016-2018"`, `"2019-2021"`

---

## Commands Reference

### `create-thread`

Create a `trend-thread` collection node representing one trend analysis project.

```
--name        Human-readable name (required)
--keyword     The keyword tag shared by all papers (required)
--source-collection   Collection ID of the source paper corpus (optional)
```

### `record-hypothesis`

Store a `trend-hypothesis-note` and add it to the thread.

```
--thread      Trend thread ID (required)
--window      Time window string, e.g. "2016-2018" (required)
--content     Markdown content with abductive analysis (required)
--title       Note title (default: "Hypothesis: <window>")
--role        abductive-role value (optional)
--subject     Collection/entity ID to link via aboutness (optional)
```

### `record-genealogy`

Insert a `hypothesis-genealogy` edge between two notes.

```
--predecessor     Earlier note ID (required)
--successor       Later note ID (required)
--type            refines|extends|challenges|supersedes (required)
--description     Human-readable description (optional)
```

### `show-thread`

Fetch the full thread: metadata, all hypothesis notes ordered by window, and all genealogy edges.

```
--thread      Trend thread ID (required)
```

---

## TypeDB Pitfalls

- **Cannot fetch from relation variable**: Do NOT fetch `$g.genealogy-type`. Bind in `match` instead:
  `has genealogy-type $gtype` then fetch `$gtype`.
- **No limit in fetch**: TypeDB 3.x fetch queries don't support `limit`. Apply `results[:N]` in Python.
- **trend-hypothesis-note inherits `note` roles**: use `collection-membership`, `aboutness`,
  `note-threading`, `evidence-chain` — all inherited.
- **trend-keyword vs keyword**: `trend-thread` owns `trend-keyword` (defined in this schema), not `keyword`
  (which is defined in `scientific-literature/schema.tql` and only owned by `scilit-paper`). Use
  `trend-keyword` in all queries against `trend-thread`.
