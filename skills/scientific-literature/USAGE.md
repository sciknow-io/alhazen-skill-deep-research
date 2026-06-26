# Scientific Literature Skill -- Usage Reference

Multi-source scientific literature search and ingestion for the Alhazen knowledge graph.
Sources: Europe PMC (EPMC), PubMed (NCBI), OpenAlex, bioRxiv/medRxiv.

---

## Commands

### `search` -- Search a source and store results

```bash
# Search Europe PMC (cursor-based, handles large corpora)
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc \
    --query "CRISPR AND gene editing" \
    --collection "CRISPR Papers" \
    --max-results 500

# Search PubMed
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source pubmed --query "CRISPR off-target effects" \
    --collection "collection-abc123" --max-results 30

# Search OpenAlex (broad interdisciplinary coverage)
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source openalex --query "base editing precision genome" --max-results 20

# Search bioRxiv/medRxiv (last 30 days, client-side keyword filter)
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source biorxiv --query "spatial transcriptomics" --max-results 20
```

**Options:**
- `--source` (required): `epmc`, `pubmed`, `openalex`, `biorxiv`, `medrxiv`
- `--query` (required): Search query
- `--collection`: Collection name (EPMC: creates new collection; others: collection ID to add to)
- `--collection-id`: Specific collection ID (EPMC only)
- `--max-results`: Limit number of papers fetched
- `--page-size`: Results per API call, EPMC only (default: 1000)

**Returns (EPMC):**
```json
{
  "success": true,
  "collection_id": "collection-abc123",
  "collection_name": "CRISPR Papers",
  "query": "CRISPR AND gene editing",
  "total_count": 15234,
  "fetched_count": 500,
  "stored_count": 487,
  "skipped_count": 13
}
```

**Returns (PubMed/OpenAlex/bioRxiv):**
```json
{
  "success": true,
  "source": "pubmed",
  "query": "CRISPR off-target",
  "inserted": 18,
  "skipped": 2,
  "papers": [{"id": "scilit-paper-abc", "title": "...", "status": "inserted"}, ...]
}
```

**Deduplication:** Papers already in the graph (matched by DOI or PMID) are skipped.

---

### `count` -- Count EPMC results without storing

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py count \
    --query "COVID-19 AND vaccine"
```

Returns: `{"success": true, "query": "...", "count": 42819}`

---

### `ingest` -- Fetch a single paper by DOI

```bash
# By DOI (tries OpenAlex first, then PubMed as fallback)
uv run python .claude/skills/scientific-literature/scientific_literature.py ingest \
    --doi "10.1038/s41587-020-0700-8" [--collection collection-abc123]

# By PMID (EPMC lookup)
uv run python .claude/skills/scientific-literature/scientific_literature.py ingest \
    --pmid "32015507" [--collection collection-abc123]
```

---

### `show` -- Show paper details for sensemaking

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py show \
    --id "scilit-paper-abc123"
```

Returns title, abstract, identifiers, and any notes already stored about this paper.

---

### `list` -- List papers

```bash
# All papers in graph
uv run python .claude/skills/scientific-literature/scientific_literature.py list

# Papers in a specific corpus
uv run python .claude/skills/scientific-literature/scientific_literature.py list \
    --collection "collection-abc123"
```

---

### `list-collections` -- List all scilit corpora

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py list-collections
```

---

### `embed` -- Generate Voyage AI embeddings and load Qdrant

```bash
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py embed \
    --collection collection-abc123 [--reembed] [--limit 500]
```

**Prerequisites:** Qdrant running (`make qdrant-start`), `VOYAGE_API_KEY` set.

- Fetches all `scilit-paper` members of the collection from TypeDB
- Checks which paper IDs already exist in Qdrant (skips unless `--reembed`)
- Builds embedding text: `title + "\n\n" + abstract`
- Calls Voyage AI `voyage-3-lite` in batches of 128 (1,024-dim vectors)
- Upserts into the `alhazen_papers` Qdrant collection

**Cost estimate:** ~$0.012 per 1,000 papers (voyage-3-lite is $0.02/M tokens; avg ~600 tokens/paper)

---

### `search-semantic` -- Find similar papers by meaning

```bash
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py search-semantic \
    --query "cardiac microRNA energy homeostasis" \
    --collection collection-abc123 --limit 10
```

Returns ranked papers with similarity scores.

---

### `cluster` -- HDBSCAN thematic clustering

```bash
# Step 1: dry-run to inspect clusters
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py cluster \
    --collection collection-abc123 --min-cluster-size 15 --dry-run

# Step 2: write theme tags back to TypeDB
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py cluster \
    --collection collection-abc123 --min-cluster-size 15 \
    --labels 0:transcription-regulation 1:chromatin-remodeling 2:cell-cycle-control
```

**Tuning `--min-cluster-size`:** Start with 15 for large corpora (>500 papers); use 5-10 for small corpora.

---

### `plot-clusters` -- 2D UMAP scatter plot

```bash
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py plot-clusters \
    --collection collection-abc123 --min-cluster-size 10 \
    --output clusters.png --labels 0:theme-a 1:theme-b
```

---

## EPMC Query Syntax

### Boolean Operators
- `AND`, `OR`, `NOT`
- `""` for exact phrase
- `*` for wildcard
- `()` for grouping

### Field-Specific Searches

| Field | Example |
|-------|---------|
| `TITLE:` | `TITLE:CRISPR` |
| `ABSTRACT:` | `ABSTRACT:"gene editing"` |
| `AUTH:` | `AUTH:"Smith J"` |
| `JOURNAL:` | `JOURNAL:Nature` |
| `DOI:` | `DOI:"10.1038/..."` |
| `PMID:` | `PMID:12345678` |
| `GRANT_ID:` | `GRANT_ID:R01GM123456` |
| `GRANT_AGENCY:` | `GRANT_AGENCY:NIH` |

### Date Filters
```
PUB_YEAR:2023
FIRST_PDATE:[2020-01-01 TO 2024-12-31]
FIRST_PDATE:[2023-01-01 TO *]
```

### Publication Type
```
PUB_TYPE:"journal article"
PUB_TYPE:review
PUB_TYPE:preprint
OPEN_ACCESS:y
```

### Complex Query Examples

```bash
# CRISPR papers from 2022 onwards
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc \
    --query "CRISPR AND (Cas9 OR Cas12) AND FIRST_PDATE:[2022-01-01 TO *]" \
    --collection "Recent CRISPR"

# Open access single-cell papers
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc \
    --query '"single cell" AND (RNA-seq OR transcriptomics) AND OPEN_ACCESS:y' \
    --collection "Open Access scRNA-seq"
```

---

## Typical Workflow

```bash
# 1. Estimate EPMC corpus size
uv run python .claude/skills/scientific-literature/scientific_literature.py count \
    --query "your query"

# 2. Create collection (via typedb-notebook)
uv run python .claude/skills/typedb-notebook/typedb_notebook.py insert-collection \
    --name "CRISPR Off-Target Review"
# -> {"collection_id": "collection-abc123"}

# 3. Search and ingest from multiple sources
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc --query "CRISPR off-target" \
    --collection "CRISPR Off-Target Review" --max-results 500

uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source pubmed --query "CRISPR off-target effects" \
    --collection "collection-abc123" --max-results 30

# 4. List ingested papers
uv run python .claude/skills/scientific-literature/scientific_literature.py list \
    --collection "collection-abc123"

# 5. Show a paper for sensemaking
uv run python .claude/skills/scientific-literature/scientific_literature.py show \
    --id "scilit-paper-abc123"

# 6. Add a note (via typedb-notebook)
uv run python .claude/skills/typedb-notebook/typedb_notebook.py insert-note \
    --subject "scilit-paper-abc123" \
    --content "Key finding: off-target rate <0.1% with high-fidelity Cas9 variants"
```

---

## Semantic Search Workflow

```bash
# 1. Embed collection (one-time, incremental)
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py embed \
    --collection collection-abc123

# 2. Semantic search
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py search-semantic \
    --query "CDK8 kinase module stress response" \
    --collection "collection-abc123" --limit 10

# 3. Cluster (dry-run first)
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py cluster \
    --collection collection-abc123 --min-cluster-size 15 --dry-run
# Claude reads representative titles and proposes theme names, then:
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py cluster \
    --collection collection-abc123 --min-cluster-size 15 \
    --labels 0:transcription-regulation 1:chromatin-remodeling
```

### Semantic Search Architecture

```
TypeDB (authoritative graph)     Qdrant (semantic index)
-----------------------------    -------------------------
scilit-paper                     collection: "alhazen_papers"
  id, name, abstract-text          point id = uuid5(paper_id)
  doi, year, keyword               vector = voyage-3-lite(title+abstract)
   (theme tags written back) <-    payload = {paper_id, collection_ids[], title, doi, year}
```

**Environment variables:**
- `VOYAGE_API_KEY` -- from https://dash.voyageai.com/
- `QDRANT_HOST` -- Qdrant host (default: localhost)
- `QDRANT_PORT` -- Qdrant port (default: 6333)

---

## Feature Faceting

Topic clustering (`cluster`) finds *one* axis of variation -- semantic similarity of
title+abstract. That works when a corpus is genuinely multi-**topic**. But many corpora
are multi-**facet** instead: nearly every item is "the same kind of thing" (e.g. "an LLM
agent system applied to domain X optimizing property Y"), differing along several
*orthogonal* dimensions at once. On such a corpus a single embedding clustering
**saturates** -- it collapses into one dominant blob plus a large noise tail.

Feature faceting is the follow-on workflow: instead of forcing one clustering, classify
each item along several orthogonal categorical **facets**, store them as namespaced
keyword tags, and study the **cross-tabulation**. Dense cells show where the field is
piling up; empty cells are white space (candidate gaps).

### When to reach for it (the saturation signal)

Run `cluster --dry-run` first. Faceting is warranted when you see:

- **One mega-cluster** holding a large fraction of the corpus, plus
- **High noise** (often 20-35%), where the noise items are *not* junk but each
  distinctive on some axis *other than topic* (a unique domain, a position/critique vs.
  a system, an unusual method). Inspect the noise titles: if they look "interesting and
  varied" rather than "off-topic", the corpus is multi-facet.

> Diagnostic heuristic: if folding a second sub-corpus in (e.g. demos alongside papers)
> *reduces* cluster count and *grows* the mega-cluster, topic-space is saturated.

### Facet conventions

Each facet is a small enum; assign **one primary value** per item per facet (cross-tabs
need a single cell). Store as `scilit-keyword` using a `facet:value` namespace so the
existing `list-by-keyword` command and the cluster tag-writer stay interoperable:

```
topology:single-agent         stage:application-development     concern:cost-efficiency
topology:multi-agent          contribution:system-framework-tool  domain:scientific-discovery
topology:compound-non-agentic autonomy:oversight-hitl           memory:persistent-memory
                              se-agent:true   (boolean: tag only when true)
```

A reusable 8-facet schema for agentic / LLM-systems corpora (adapt per corpus):

| # | Facet | Values |
|---|-------|--------|
| 1 | **topology** | `single-agent` · `multi-agent` (>=2 coordinating) · `compound-non-agentic` (fixed LLM pipeline, no autonomy) |
| 2 | **stage** (where in the stack) | `pre-training` · `post-training` (RL/reasoning/prompt-program opt) · `serving-inference` · `application-development` · `evaluation` · `ops-governance` |
| 3 | **concern** (the "-ility" foregrounded) | `cost-efficiency` · `latency-throughput` · `safety-security` · `reliability-robustness` · `correctness-verification` · `fairness-equity` · `privacy-compliance` · `energy` · `interpretability-legibility` |
| 4 | **contribution** (what the item *is*) | `system-framework-tool` · `method-algorithm` · `empirical-study` · `benchmark-dataset` · `theory-formalism` · `position-critique` |
| 5 | **domain** (application area) | `general` (domain-agnostic) · `software-eng` · `data-analytics` · `scientific-discovery` · `cybersecurity` · `clinical` · `ecommerce-marketing` · `iot-embedded` · `hardware-eda` · `agent-society` · `finance-insurance` · `legal-policy` · `devops-sre` · `quantum` · ... (open-ended) |
| 6 | **se-agent** (boolean) | `true` for software-engineering / coding agents |
| 7 | **autonomy** (human-in-the-loop) | `autonomous` (closes its own loop) · `oversight-hitl` (human approves/gates) · `human-collaborative` (human is a co-actor) |
| 8 | **memory** (state across turns) | `stateless` · `context-engineering` (in-context/RAG, no durable store) · `persistent-memory` (writes & reads a durable memory store) |

`concern` is usually the most *interesting* facet because it is the axis topic-clustering
keeps entangling. `stage x concern` is the recommended headline matrix; `contribution x stage`
and `memory x topology` are strong secondary cuts.

### Workflow

```bash
# 1. Embed + diagnose saturation (dry-run)
VOYAGE_API_KEY=xxx ... cluster --collection <id> --min-cluster-size 5 --dry-run
#    -> one big cluster + high noise  => proceed to faceting

# 2. Classify each item along the facets. This is an LLM (Claude) reading
#    title+abstract per item and assigning one primary value per facet --
#    there is no CLI subcommand for it; it is a sensemaking step.

# 3. Write the classifications back as namespaced keyword tags via TypeQL
#    (idempotent: skip a tag the paper already has):
#       match $p isa scilit-paper, has id "<pid>";
#       insert $p has scilit-keyword "concern:safety-security";

# 4. Query any facet value with the existing command:
... list-by-keyword --keyword "concern:safety-security"

# 5. Cross-tabulate (facet x facet) to read dense cells (crowding) and
#    empty cells (white space / gaps).
```

### Worked example -- ACM CAIS 2026 (105 items: 60 papers + 45 demos)

Topic clustering on the 60 papers gave a clean 4-way split that matched the conference's
own editorial pillars. But folding the 45 demos in collapsed it to a single 57-item
mega-cluster + 17 noise -> saturation. Faceting the full 105 along all 8 facets yielded
interpretable marginals and cross-tabs, e.g.:

- **topology**: 67 single-agent / 23 multi-agent / 15 compound-non-agentic.
- **stage**: application-development 45, evaluation 21, ops-governance 15, post-training 12,
  serving-inference 12, **pre-training 0** -- CAIS is a "right-of-the-stack" venue.
- **contribution**: system-framework-tool 54 (a *demo* venue -- artifacts dominate),
  method-algorithm 28, empirical-study 11, benchmark-dataset 9, theory-formalism 2,
  position-critique 1.
- **domain**: 60 `general` (domain-agnostic infrastructure) vs. a long tail of 14 verticals
  (data-analytics 9, software-eng 8, scientific-discovery 5, ...) -- the field's center of
  gravity is reusable substrate, not vertical applications.
- **autonomy**: 90 autonomous / 11 human-collaborative / **4 oversight-hitl** -- explicit
  human-gating is rare and lives *only* in single-agent systems.
- **memory**: 94 stateless / 7 persistent-memory / 4 context-engineering -- durable memory is
  still a frontier; persistent memory is **6/7 single-agent** (multi-agent memory is white space).
- **cross-tab cells**: `contribution x stage` -- benchmark-dataset sits entirely in `evaluation`
  (9/9), method-algorithm concentrates in `post-training` (10) while system-framework-tool owns
  `application-development` (33); `memory x topology` -- multi-agent persistent memory = **0**.

The payoff is the matrix, not the clusters: it surfaces both crowding and gaps that a
single topic clustering cannot.

### Persisting a faceting run (scilit-faceting-note)

Steps 2-5 above are otherwise throwaway scripts. To make a faceting run **durable and
re-runnable**, store it as a `scilit-faceting-note` — a subtype of the core
`alh-analysis-pipeline-note` (a stored, executable [Hamilton](https://hamilton.dagworks.io/)
pipeline). The note holds the pipeline source (`alh-pipeline-script`), the exact inputs
(`alh-pipeline-config`: facet schema + per-paper assignments + corpus ids), links to its source
corpora via `alh-aboutness`, and — after a run — the rendered cross-tab report in `content`.

The pipeline module (`pipelines/pipeline_faceting.py`) is a self-contained Hamilton DAG:

```
collection_ids ─▶ corpus_items ─▶ written_tags ─▶ facet_rows ─▶ crosstab_markdown
assignments / facet_schema ─────▶ written_tags
facet_schema / crosstabs ──────────────────────▶ crosstab_markdown
```

- `corpus_items` fetches the `scilit-paper` members of each corpus.
- `written_tags` **idempotently** writes `<facet>:<value>` `scilit-keyword` tags (skips any
  already present — so re-running never duplicates or overwrites).
- `facet_rows` reads the tags back per paper.
- `crosstab_markdown` (the terminal output) renders marginals + the requested cross-tabs.

Create and run it via the **core** typedb-notebook commands (no scilit-specific CLI):

```bash
# Create the note (links it to both source corpora; stores script + config)
uv run python skills/typedb-notebook/typedb_notebook.py create-pipeline-note \
    --type scilit-faceting-note \
    --collections collection-cais2026-papers,collection-cais2026-demos \
    --script @pipelines/pipeline_faceting.py \
    --config @cais_faceting_config.json \
    --name "ACM CAIS 2026 — 8-facet faceting"

# Execute it: (idempotent) tag write + cross-tab report written to the note's content
uv run python skills/typedb-notebook/typedb_notebook.py run-pipeline-note --id <scfn-id>

# Round-trip the stored script, config, and rendered report
uv run python skills/typedb-notebook/typedb_notebook.py show-pipeline-note --id <scfn-id>
```

The `config` (`alh-pipeline-config`) is an id-keyed JSON: `inputs.assignments` maps each
paper id → `{facet: value}`, `inputs.facet_schema` declares each facet's `namespace` (and a
`boolean` flag for presence-only facets like `se-agent`), `inputs.crosstabs` lists the facet
pairs to tabulate, and `output_attr_map` routes `crosstab_markdown → content`.

---

## Investigations

An **investigation** is a named, dated, purpose-driven inquiry — the scilit analogue of a
tech-recon investigation, but with an **explicit phase structure**. It is modelled as a note
**about** a subject (`alh-aboutness`): the note's `name` is the title, its `content` is the
purpose/goal, and `created-at` is the start date, plus a `scilit-investigation-status` lifecycle
attribute. Each phase is a single `scilit-investigation-phase` note threaded under it
(`alh-note-threading`) and tagged with a `scilit-phase` attribute. The canonical lifecycle is:

```
discovery → ingest → sensemaking → analysis → report
```

The **analysis** phase reuses the analysis machinery already built: existing
`scilit-faceting-note` pipelines are threaded under the analysis phase note (so an investigation
references — rather than re-implements — faceting runs).

### Investigation types

`scilit-investigation-type` selects the kind of inquiry (the 5-phase spine is shared; the type
changes phase *contents* and attached artifacts):

| Type | Subject | Adds |
|---|---|---|
| `corpus` (default) | a `scilit-corpus` | faceting pipelines under analysis |
| `deep-dive` | a single focal `scilit-paper` | claims → evidence → source papers, plus citation-impact notes |

A **deep-dive** resolves *every* claim in one focal paper down to primary evidence (tracing cited
papers, found-or-ingested as real `scilit-paper` entities) and surveys how citing papers received
those claims. Claims are threaded under the investigation; evidence under each claim; each evidence
and each citation-impact links its source/citing paper via `alh-aboutness`.

### `create-investigation` -- Start a corpus or deep-dive investigation

```bash
# corpus investigation (default)
uv run python .claude/skills/scientific-literature/scientific_literature.py create-investigation \
    --type corpus \
    --collection collection-cais2026-papers \
    --name "CAIS agent-safety landscape" \
    --purpose "## Goal\nMap the agent-safety subfield across the CAIS 2026 corpus." \
    --status scoping
# -> { "id": "scinv-...", "type": "corpus", ... }

# deep-dive investigation over one focal paper (DOI or scilit-paper id)
uv run python .claude/skills/scientific-literature/scientific_literature.py create-investigation \
    --type deep-dive \
    --paper "10.1038/s41587-020-0700-8" \
    --name "Deep dive: prime editing" \
    --purpose "## Goal\nResolve every claim to primary evidence." \
    --status scoping
# -> { "id": "scinv-...", "type": "deep-dive", "focal_paper": "scilit-paper-...", ... }
```

### `record-phase` -- Upsert a phase note (and optionally advance status)

One phase note per `(investigation, phase)`. Re-running with the same `--phase` **updates** the
note's content rather than creating a duplicate.

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py record-phase \
    --investigation scinv-... \
    --phase discovery \
    --content "## Discovery\nSearched ACM DL; 105 items (60 papers + 45 demos)." \
    --status discovery
```

### `link-analysis` -- Attach a faceting note to the analysis phase

Ensures an `analysis` phase note exists, then threads the `scilit-faceting-note` under it
(idempotent).

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py link-analysis \
    --investigation scinv-... \
    --faceting-note scfn-d65ae930475a
```

### `show-investigation` -- Full investigation with phases in canonical order

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py show-investigation \
    --id scinv-...
```

Returns the investigation metadata, its linked corpus, the phase notes ordered
`discovery → … → report`, and (under the analysis phase) the linked faceting notes.
It also returns `collection` `{id, name, count}` and `papers[]` (the investigation's
paper set, sorted by year desc) — see **Investigation paper collection** below.

### `list-investigations` / `set-status`

```bash
# All investigations, or scoped to one corpus
uv run python .claude/skills/scientific-literature/scientific_literature.py list-investigations \
    [--collection collection-cais2026-papers]

# Advance the lifecycle status
uv run python .claude/skills/scientific-literature/scientific_literature.py set-status \
    --investigation scinv-... --status report
```

### Deep-dive commands (claims, evidence, citation impact)

These operate on a `--type deep-dive` investigation. Claims, evidence, and impacts land naturally
in the `analysis` phase; the writeup belongs in `report` (use `record-phase`).

```bash
# 1. Add a claim (type: primary | secondary | peripheral)
uv run python .claude/skills/scientific-literature/scientific_literature.py add-claim \
    --investigation scinv-... \
    --type primary \
    --statement "Prime editing installs all 12 base-to-base conversions without DSBs."
# -> { "claim_id": "scclaim-...", ... }

# 2. Add evidence for a claim, targeted by --claim-id. A --source-doi (or --source-id)
#    is found-or-ingested as a real scilit-paper and linked via alh-aboutness.
#    evidence-type: experimental | observational | computational | review | theoretical | anecdotal
uv run python .claude/skills/scientific-literature/scientific_literature.py add-evidence \
    --investigation scinv-... \
    --claim-id scclaim-... \
    --evidence-type experimental \
    --source-doi "10.1126/science.aba8853" \
    --experimental-design "HEK293T transfection, amplicon sequencing" \
    --data-summary "Up to 51% editing efficiency at target loci."
# -> { "evidence_id": "scev-...", "source_paper": "scilit-paper-...", ... }

# 3. Record how a citing paper received the focal paper.
#    impact-type: supports | refutes | extends | nuances | uses | unrelated
uv run python .claude/skills/scientific-literature/scientific_literature.py add-citation-impact \
    --investigation scinv-... \
    --citing-doi "10.1038/s41586-021-03609-w" \
    --impact-type extends \
    --impact-summary "Extends prime editing to primary human cells in vivo."
# -> { "impact_id": "scimpact-...", "citing_paper": "scilit-paper-...", ... }
```

### Investigation paper collection

Every investigation owns a **collection of all the papers it touched**, surfaced as a
`scilit-corpus` so it appears in the landing Corpora list and has its own corpus page.

- **Corpus investigations** reuse their source corpus as the collection — no extra collection
  is created.
- **Deep-dive investigations** get a *dedicated* curated corpus (named `"<inv name> - papers"`,
  `alh-is-extensional false`, no logical query). Its members accumulate as the investigation
  grows: the **focal** paper (on `create-investigation`), each **evidence source** paper (on
  `add-evidence`), and each **citing** paper (on `add-citation-impact`) — all found-or-ingested
  as real `scilit-paper`s and added idempotently.

**Membership is papers only.** External information artifacts (PDF, JATS/PDF full-text,
supplementary data, citation records) are **never** direct collection members — they attach to
each paper via `alh-representation` and surface transitively through the paper. The
investigation→collection link reuses `alh-aboutness(note, subject)` with `subject isa
scilit-corpus`; collection membership reuses `alh-collection-membership(collection, member)` with
`member isa scilit-paper`. No new schema.

#### `backfill-investigation-collection` -- Populate the collection for an existing investigation

Investigations created before this feature (or any whose collection drifted) can be (re)populated
from their existing aboutness links — focal + every evidence-source + every citing paper. Idempotent.

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py \
    backfill-investigation-collection --id scinv-...
# -> { "success": true, "investigation": "scinv-...", "collection": "collection-...",
#      "papers_added": 12 }
```

### `export-investigation` -- Markdown or JSON report

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py export-investigation \
    --id scinv-... --format md   # or: --format json
```

`show-investigation` returns the same data as JSON; for a deep-dive it includes `focal_paper`,
`claims` (sorted primary → secondary → peripheral, each with nested `evidence` and its
`source_paper`), and `citation_impacts` (each with its `citing_paper`).

---

## Meeting surveys (discourse sources)

A **meeting survey** (a `survey`-type investigation, e.g. the CAIS 2026 conference survey)
covers a program of papers + spoken sessions. Two types support this, both in the
**domain-neutral discourse/source layer** (KQED System 1) — they never touch the biomed
S2/S3 (KEfED, bio-mechanism):

- **`scilit-session`** — a discourse SOURCE (keynote | workshop | tutorial | talk | panel),
  sibling of `scilit-paper`. Owns `scilit-session-type`, `scilit-speaker` (multi),
  `scilit-affiliation` (multi), `scilit-session-url`, `scilit-publication-year`. A claim can
  cite a talk via `scilit-hinge:hinged-to`, exactly as it cites a paper; a session is a corpus
  member and an aboutness subject like any source.
- **`scilit-experience-note`** — a first-person anecdote / engagement record (`sub
  alh-sensemaking-note`), `about` a session/paper/person. Owns `scilit-experience-event` (the
  occasion, e.g. "CAIS 2026 keynote"). This is distinct from the KQED epistemic
  `scilit-observation` (a measurement-in-context, System 2 / KEfED D-node).

---

## Source Connector Details

### Europe PMC
- **API:** `https://www.ebi.ac.uk/europepmc/webservices/rest/search`
- **Pagination:** Cursor-based (handles corpora of 50k+ papers reliably)
- **Coverage:** ~45M+ records including PubMed and preprints
- **Best for:** Large-scale corpus building, combined PubMed + preprint coverage
- **Docs:** https://europepmc.org/RestfulWebService

### PubMed (NCBI Entrez)
- **API:** `esearch.fcgi` (get PMIDs) + `efetch.fcgi` (get full XML records)
- **Rate limit:** 3 req/s without key; 10 req/s with `NCBI_API_KEY`
- **API key:** Free from https://www.ncbi.nlm.nih.gov/account/
- **Best for:** Precise biomedical queries, MeSH-filtered searches

### OpenAlex
- **API:** `https://api.openalex.org/works?search=...`
- **API key:** Free from https://openalex.org/settings/api
- **Coverage:** 240M+ works across all disciplines
- **Note:** Abstracts stored as inverted indexes; reconstructed automatically
- **Best for:** Broad interdisciplinary searches

### bioRxiv / medRxiv
- **API:** `https://api.biorxiv.org/pubs/biorxiv/30d/{cursor}` (date range only)
- **Limitation:** No full-text search -- fetches last 30 days, filters client-side by keyword
- **Best for:** Recent preprints

---

## Cross-Skill: Literature as Learning Resources

Paper collections can serve as learning resources for the **jobhunt** skill.

```bash
# 1. Search for papers on a skill gap topic
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc \
    --query "machine learning systems design" \
    --collection "ML Systems Reading List" \
    --max-results 20

# 2. Link the collection to a skill gap in jobhunt
uv run python .claude/skills/jobhunt/jobhunt.py link-collection \
    --collection "<collection-id>" --skill "machine-learning"

# 3. View updated learning plan
uv run python .claude/skills/jobhunt/jobhunt.py learning-plan
```

---

## Data Model

Papers are stored as `scilit-paper` entities (sub `domain-thing`) using the `schema.tql` schema:

| Attribute | Type | Notes |
|-----------|------|-------|
| `id` | string @key | Auto-generated (`scilit-paper-xxxxxxxx`) or `doi-...` for EPMC |
| `name` | string | Paper title |
| `abstract-text` | string | Full abstract |
| `doi` | string | DOI (without https://doi.org/ prefix) |
| `pmid` | string | PubMed ID |
| `pmcid` | string | PubMed Central ID |
| `arxiv-id` | string | arXiv ID |
| `publication-year` | integer | Year of publication |
| `journal-name` | string | Journal or preprint server name |
| `source-uri` | string | Canonical URL for this paper |
| `keyword` | string (multi) | Keywords and theme tags |
