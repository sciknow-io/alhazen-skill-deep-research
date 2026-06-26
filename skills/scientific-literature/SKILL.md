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

**Read USAGE.md before executing commands** -- full command reference, source-specific options,
query syntax, semantic search workflow, and clustering guide.
