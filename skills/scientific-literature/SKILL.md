---
name: scientific-literature
triggers:
  - "search epmc"
  - "search pubmed"
  - "search openalex"
  - "search biorxiv"
  - "search medrxiv"
  - "find papers about"
  - "build a corpus"
  - "search literature"
  - "count papers"
  - "ingest paper"
  - "fetch paper by DOI"
  - "look up paper"
  - "add paper to corpus"
  - "embed papers"
  - "semantic search"
  - "find similar papers"
  - "cluster papers"
  - "thematic clustering"
prerequisites:
  - TypeDB running (install alhazen-core first and run /alhazen-core:init)
  - uv installed
  - Qdrant running for semantic commands (docker run -d -p 6333:6333 qdrant/qdrant)
  - VOYAGE_API_KEY set for embed/search-semantic/cluster
---

# Scientific Literature Skill

Multi-source scientific literature search, ingestion, and analysis.
Sources: Europe PMC, PubMed (NCBI), OpenAlex, bioRxiv/medRxiv.

## Quick Start

> **Path note:** Replace `<skill-path>` with your installation directory
> (e.g. `~/.claude/plugins/cache/scientific-literature/` when installed as a plugin).

```bash
# Count papers before committing (EPMC)
uv run --project <skill-path> python <skill-path>/scientific_literature.py count \
    --query "CRISPR AND gene editing"

# Search EPMC and store results in a corpus
uv run --project <skill-path> python <skill-path>/scientific_literature.py search \
    --source epmc --query "CRISPR AND gene editing" --collection "CRISPR Papers" \
    --max-results 500

# Ingest a single paper by DOI (OpenAlex + PubMed fallback)
uv run --project <skill-path> python <skill-path>/scientific_literature.py ingest \
    --doi "10.1038/s41587-020-0700-8"

# List papers in a corpus
uv run --project <skill-path> python <skill-path>/scientific_literature.py list \
    --collection "collection-abc123"
```

## Full-Text Ingestion & Per-Paper Cache — REQUIRED convention

This is the ONLY correct way to ingest a paper's full text and cache its files. It is
**mandatory and uniform across every scilit investigation** (search corpora, deep-dives,
CAIS, etc.) — never improvise an alternate layout.

### 1. Paper identity (deterministic)
Every paper is a `scilit-paper` whose id is a **pure function of its best stable
identifier**: `DOI → PMID → arXiv → content-hash(title|first-author|year)`. Compute it
with `paper_identity()` in `paper_identity.py`; create/find papers only via
`kqed.upsert_paper(driver, meta)`. Same paper → same id, always. The tier is recorded in
`scilit-identity-basis` / `scilit-identity-value`. (Full design: `docs/paper-identity-design.md`.)

### 2. One directory per paper; every file is named by ITS artifact id
```
~/.alhazen/cache/fulltext/<paper-id>/
    scilit-fulltext-<paper-hash>.pdf   # source rendition  ┐ ONE full-text artifact
    scilit-fulltext-<paper-hash>.txt   # kreuzberg text     ┘ (renditions share the id-base)
    <other-artifact-id>.<ext>          # any OTHER artifact of the paper (table/figure/supplement/data)
```
**A paper may have several artifacts; each FILE is named by the id of the artifact it
belongs to (basename = artifact id, suffix = format).** There is ONE **full-text artifact**
per paper, `scilit-fulltext-<paper-hash>` (paper-hash = the paper id's 12-hex suffix); its
`.pdf` source and `.txt` extraction are two **renditions of that single artifact**, sharing
the id-base and differing only by suffix. Any other content (extracted tables, figures,
supplements, datasets) is its OWN `alh-artifact`, file `<that-artifact-id>.<ext>`.
**EVERY such file goes in that paper's `fulltext/<paper-id>/` subdirectory — and nowhere
else** (NOT `cache/pdf/`, `cache/text/`, `cache/extracted/`, or `cache/papers/`).

### 3. Rules
- **MOVE files into place** (copy, then remove the original) — **never symlink**, and never
  leave a paper's content scattered in `cache/pdf/`, `cache/text/`, `cache/extracted/`, or
  `cache/papers/`.
- The **filename basename equals the artifact id** — a loose file is self-identifying.
- **Register every file as an `alh-artifact` with a complete file xref:**
  `cache-path = fulltext/<paper-id>/<artifact-id>.<ext>` **plus** `content-hash` (sha256),
  `file-size`, `mime-type`, and `format` — linked to the paper via `alh-representation`.
  The full-text artifact's `cache-path` points at its text rendition (`.txt`, the indexable
  one); the `.pdf` is the sibling by suffix.
- **The path is computable from the paper id** — the full-text artifact id is deterministic
  (`scilit-fulltext-<paper-hash>`), so `paper → fulltext/<paper-id>/scilit-fulltext-<paper-hash>.pdf`
  needs no graph lookup. Keep it that way.
- A paper with a local source PDF must carry `scilit-acquisition-status = held`; a
  cited-but-undownloaded reference is `needed`.

### 4. Ingestion flow (per paper)
1. `upsert_paper(meta)` → deterministic `<paper-id>`; full-text artifact id `scilit-fulltext-<paper-hash>`.
2. Download the source PDF → **move** to `fulltext/<paper-id>/scilit-fulltext-<paper-hash>.pdf`; register the artifact with the complete file xref (cache-path + content-hash + file-size + mime-type + format); set status `held`.
3. kreuzberg-extract the text → write `fulltext/<paper-id>/scilit-fulltext-<paper-hash>.txt` as the **same** artifact's `.txt` rendition.
4. Extracted tables / figures / supplements / data → each its OWN artifact, file `<artifact-id>.<ext>` in the same dir, with its own complete file xref.
5. Never write any of the above outside `fulltext/<paper-id>/`.

> `cache/pdf/` may still hold OTHER skills' documents (tech-recon, health-coach) — those are
> out of scope for this convention; do not touch them. This convention governs `scilit-paper`
> content only.

Reconciliation prototypes that retrofit existing data to this layout live in
`prototypes/reconcile_*_fulltext.py` (they MOVE sources into `fulltext/<paper-id>/`).

---

## KEfED Model Authoring — build STRUCTURED, RICH, ACCURATE, EXPRESSIVE models

A KEfED model (`kefed-model`, authored under a bundle with `add-experiment`) is a **graph of
`kefed-model-node`s** that reconstructs an experiment. Follow these principles:

1. **Reconstruct the real protocol from the paper's Methods.** Read the Experimental Procedures and
   build the actual material chain — *organism → sample preparation → assay → readout* — including where
   cells came from and how they were prepared (harvest, sort, lineage-deplete, transduce, transplant,
   culture...). The **combination of nodes in the graph carries the experimental-design semantics**, not
   any single node.

2. **Minimal ontological commitment per node; maximum reuse.** Node *definitions* are **generic and
   reusable** — `experimental mouse`, `bone-marrow harvest`, `competitive transplantation` — NOT
   `HSC (WT or SIRT3-KO mouse)`. What differentiates *this* experiment lives in the attached **variables +
   values**, never in node names. Share one OOEVV element wherever the concept genuinely recurs:
   `add-entity-node` / `add-process` find-or-create a def by name **within the model's element-set**, so
   pass `add-experiment --element-set <id>` to make a family of experiments **share one element-set** and
   thus one def per concept (verify: distinct defs ≪ node count).

3. **Variable = a grounded QUALITY + a reusable VALUE-SPECIFICATION.** (`add-variable`)
   - **Quality** (`ooevv-quality`, `ensure-quality`) = *what* is measured — the semantic anchor. Ground
     **only** with a verified, definition-matching curie (PATO/EFO); otherwise leave it **ungrounded**
     (precise local definition, `grounding-state "ungrounded"`, no curie). **Never fabricate a grounding.**
   - **Value-specification** (`ooevv-scale`, `ensure-value-spec --quality`) = *how* it is measured — the
     value space + method: `ordinal` ranks, `nominal`/`binary` set, `numeric` unit/range. A quality
     **enumerates its canonical value-specs** via `ooevv-quality-scale`. The **same quality** can be
     measured by **different value-specs**.
   - A variable **references a shared value-spec**: `add-variable --node <n> --role <r> --value-spec <id>`.
     **Reuse is the default** — `recognize → reuse → extend`: run `list-qualities` / `list-value-specs`
     before creating anything new.
   - **Role is fixed by the value-spec's cardinality**, not chosen freely: a value-spec with **one**
     possible value ⇒ `constant`; **two or more** ⇒ `parameter`. So `genotype {WT|SIRT3-KO}` is **always**
     a parameter, `species {mouse}` is a constant. `measurement` (the readout) is the third role.
     `add-variable` derives/auto-corrects parameter-vs-constant from the spec.
   - **Worked example — age.** One quality `age` (PATO:0000011) with canonical value-specs
     `{ordinal young<mature<old}` and `{numeric days, UO:0000033}`. A mouse-genetics paper's `age`
     variable references the ordinal spec; a pharmacokinetics paper's references days. **Same quality,
     different value-specs** — this is why the value-spec is a property of the quality, selected per variable.

4. **Place variables at the biologically-correct node.** Organism-level (`species`, `genotype`, `age`) on
   the mouse; cell-level (`cell-population`) on the sorted population; interventions (`construct`,
   `treatment`) on the transduction / recipient; the **measurement** on the readout assay. Traversing flow
   edges (`link-nodes --role input|output`) upstream from a measurement collects its indexing
   parameters — the **data signature** (`show-data-signature`). Rich chains ⇒ rich, correct signatures.

**Grounding policy (non-negotiable):** attach a curie **only** when a real ontology term's definition
genuinely matches the intended meaning. If a term can't be grounded, or the candidate's definition is
wrong, **OMIT the grounding** — better ungrounded-with-a-precise-local-definition than wrongly grounded.

**Verb sequence:** `add-experiment [--element-set]` → `add-entity-node --subject` / `add-process --type`
→ `link-nodes --role input|output` → `ensure-quality [--curie]` → `ensure-value-spec --quality
--scale-type` → `add-variable --value-spec` → `show-experiment` / `show-data-signature` to verify.

## Sensemaking — label observations by their evidence source

When adding a `scilit-observation`, give it a **source-locator label** (`add-observation
--source-label`) so its evidence locus is legible at a glance. The label becomes the note
`name`; the full statement always stays in `content`. The evidence is **not always a main
figure** — cover all cases:

- `OF4DF` — main **F**igure 4, panels D & F   ·   `OF2A-G` — Figure 2, panels A through G
- `OSF3B` — **S**upplemental **F**igure 3, panel B
- `OT2` / `OST1` — **T**able 2 / **S**upplemental **T**able 1
- `OE5` — **E**xperiment 5 (a result reported only in text/Methods, no display item)
- `OX` — text-only narrative assertion (no figure/table/experiment)
- `OF2A+SF4C` — one observation read off **multiple** loci (join with `+`)

Prefer the most specific display item (main-figure panel > supplemental > table); fall back
to `E<n>` for figure-less experimental results and `X` for pure narrative. Legacy seed form
`O4DF` (bare figure digit) is still accepted but write `OF4DF`. Full grammar:
[`docs/observation-source-labeling.md`](docs/observation-source-labeling.md).

---

**Read USAGE.md before executing commands** -- full command reference, source-specific options,
query syntax, semantic search workflow, and clustering guide.
