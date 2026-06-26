# Paper Identity Convention — Design Spec

- **Date:** 2026-06-24
- **Status:** Approved (design); pending implementation plan
- **Scope:** `scilit-paper` identity + full-text artifact identity. **Out of scope:** the citation / reference-key *model* (`<citing>:<position>`).

## Context & problem

A `scilit-paper` is currently identified by an **opaque random-hex id** (`scilit-paper-<12hex>`, minted by `generate_id`). This is position-independent but **unstable**: re-ingesting the same paper mints a *new* id, so the same real paper can fragment into multiple records (we already have one duplicate-DOI collision, `10.1056/nejmoa1805819` → 2 papers).

Separately, the `scilit-reference-key` attribute (`<citing-paper-id>:<ref-number>`, on 294 papers) **indexes on citation position**. That scheme caused a systematic mis-resolution bug (Crossref `bibNN` key ≠ in-text citation number), fixed in `prototypes/fix_citation_registry.py`. That experience motivates a paper identity that is **derived from the paper itself**, never from a citing context or position.

Corpus facts (2026-06-24): 426 papers; 419 have a DOI (98%), 299 a PMID (70%), 294 a reference-key. The 7 DOI-less papers are hand-seeded `kqed-stub-N` mention stubs. 577 `alh-artifact`s exist but only **114 papers** have a graph-linked full-text artifact, while **412 PDFs** sit in `cache/pdf/` keyed by DOI.

## Goals / non-goals

**Goals**
- A paper's TypeDB id is its **canonical identity**, computed **deterministically** so the same paper always maps to the same id (dedup by construction).
- The convention is **general**: every paper gets an id, including DOI-less ones.
- Extend the same determinism to **full-text artifacts** so `paper → its PDF/text` is computable.

**Non-goals**
- Do **not** redesign the citation/reference-key model. We only mechanically rewrite the id *prefix* embedded in existing reference-key strings during migration.
- Do **not** introduce human-readable citekeys; ids stay opaque (transparency lives in attributes).

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Scope | Paper identity (+ full text). Citation model unchanged. |
| Identity basis | The TypeDB paper id is canonical; external ids (DOI/PMID) are **attributes**, not the name. |
| Stability | The id is a **deterministic function** of the paper's best stable identifier. |
| DOI-less papers | **Identifier fallback chain**: DOI → PMID → arXiv/other → content-hash. |
| Id format | **Pure hash + tier attributes** — preserves the current `scilit-paper-<12hex>` shape. |
| Full text | **In scope** — deterministic artifact id + per-paper cache path; backfill unlinked PDFs. |

## §1 — The identity function

A single canonical helper `paper_identity(metadata) -> (id, basis_tier, basis_value)`:

```
# 1. pick the highest-available stable identifier (fallback chain)
if normalized_doi:        basis_tier, basis_value = "doi",          normalized_doi
elif pmid:                basis_tier, basis_value = "pmid",         digits_only(pmid)
elif arxiv_or_other:      basis_tier, basis_value = "arxiv",        normalized_other_id
else:                     basis_tier, basis_value = "content-hash", f"{norm_title}|{first_author_surname}|{year}"

# 2. deterministic id (tier prefixed so a DOI and a PMID can never collide)
key = f"{basis_tier}:{basis_value}"
id  = "scilit-paper-" + sha256(key.encode()).hexdigest()[:12]
```

**Normalization**
- **DOI** (`canon_doi`): lowercase; strip `https://doi.org/`, `http://dx.doi.org/`, `doi:` prefixes; strip surrounding whitespace and trailing punctuation. (Harden the existing `canon()` used in `fix_citation_registry.py` and reuse it everywhere.)
- **PMID**: digits only.
- **content-hash basis_value**: `norm_title` = lowercased, punctuation stripped, whitespace collapsed; `first_author_surname` = lowercased; `year` = 4 digits. Joined with `|`.

**Stored on every paper**
- `scilit-identity-basis` — one of `doi | pmid | arxiv | content-hash`.
- `scilit-identity-value` — the normalized `basis_value` (the transparent, human-inspectable key).
- `scilit-doi` / `scilit-pmid` remain ordinary attributes (a paper keeps its DOI even when identity falls back, e.g. before a DOI is discovered).

**Collision safety:** 12 hex = 48 bits; birthday-bound ~16M papers for 50% — safe past any realistic corpus. New attributes are additive to `schema.tql`.

## §2 — Ingestion behavior

Every ingestion path (epmc / openalex / bioRxiv / the citation-registry builder / deep-dive paper creation in `make_stragglers`-style code) computes `paper_identity()` and **upserts**:
- if a paper with that id exists → merge new/better metadata into it (fill missing attrs; never duplicate);
- else → create it with the deterministic id + basis attrs.

No code path calls `generate_id("scilit-paper")` any more. Dedup is enforced at the door, so the duplicate-DOI class of bug cannot recur.

## §3 — Migration of the existing 426 papers

1. **Backup** (`make db-export`, verify zip).
2. **Compute** the new id + `scilit-identity-basis`/`-value` for every paper.
3. **Collision merges:** group papers by computed new id. For any group >1 (the known dup-DOI pair; any stub that now resolves to a DOI):
   - pick a survivor (prefer the one with the most relations / richest metadata);
   - re-point every relation of the others onto the survivor (`alh-aboutness`, `scilit-hinge`, `alh-derivation`, `alh-note-threading`, `alh-representation`, `alh-collection-membership`, `alh-classification`, …);
   - copy any attributes the survivor lacks; delete the extras.
4. **Swap the `id @key`** in place per surviving paper: `match $p ... has id $old; delete has $old of $p; insert $p has id "<new>";`. **Relations are preserved automatically** — TypeDB binds relations to the entity, not to the id string. Add the basis attrs.
5. **Rewrite string-embedded ids:** `scilit-reference-key` values (`<citing-id>:<refnum>`) carry the citing paper's *old* id → rewrite the prefix to the new id. The `:refnum` part is untouched.

## §4 — Edge cases & caveats

- **Identifier promotion.** If a content-hash / PMID paper later gains a DOI, its canonical id changes → handle as a **merge** into the DOI-based id (§3.3), not a silent re-key. Rare; documented.
- **Derived ids stay as-is.** Deep-dive investigation / claim / observation / kefed-model ids embed the *old* 12-hex paper suffix (`scinv-dd-<pid12>`, `scclaim-dd-<pid12>-…`). They keep functioning (opaque handles) but are cosmetically stale after migration. **Decision: leave them.** Only *new* derived ids use the new suffix. Chasing the cascade is churn for no functional gain.
- **Citation model unchanged.** Only the id prefix inside reference-key strings is rewritten; the `<citing>:<position>` scheme itself is a separate, future concern.

## §5 — Full-text identity (extension)

> **SUPERSEDED naming (2026-06-24):** the filename/id convention below (`source.pdf`/`text.md`,
> per-`(paper,kind)` artifact id `scilit-fulltext-<paper-hash>-<kind>`) was later replaced by:
> **one `scilit-fulltext-<paper-hash>` artifact per paper** whose renditions are named by the
> artifact id — `fulltext/<paper-id>/scilit-fulltext-<paper-hash>.pdf` (and `.txt`), sharing the
> id-base. Files are **moved** (not symlinked) and carry a complete file xref
> (`cache-path` + `content-hash` + `file-size` + `mime-type`). See `SKILL.md` (the live convention)
> and `prototypes/rename_fulltext_artifact_files.py`. The original text is kept for history.

Full text stays an `alh-artifact` linked by `alh-representation` (`alh-artifact ↔ referent`), but gains **identity derived from the paper + a `kind`**:

- **Kinds:** `pdf` (source PDF), `text` (extracted markdown). Extensible (`html`, `supplement`).
- **Artifact id:** `scilit-fulltext-<paper-hash>-<kind>` (`paper-hash` = the paper id's 12-hex suffix). Exactly **one artifact per (paper, kind)**, deterministic → upsert. New attribute `scilit-fulltext-kind`.
- **Cache path (per-paper directory):** `fulltext/<paper-id>/source.pdf`, `fulltext/<paper-id>/text.md`. Fully computable from the paper id; uniform across all identifier tiers (works for DOI-less papers).

**Backfill + relocation migration**
- For each held paper, if a source PDF exists at `cache/pdf/<normalized-doi>.pdf`, place it at `fulltext/<paper-id>/source.pdf` and create/relink the `pdf` artifact via `alh-representation` — connecting the **~312 currently-unlinked** papers.
- Re-key the **114 existing** full-text artifacts to deterministic ids; relocate their cache files into the new layout; extracted text → `fulltext/<paper-id>/text.md`.
- The `alh-representation` links survive the paper-id swap regardless; this step additionally normalizes artifact ids/paths.
- **Relocation = symlink by default** (the ~412 PDFs are GB-scale; avoid doubling disk). A `--move` flag physically relocates instead.

## Verification

- `paper_identity()` is pure and deterministic: same metadata → same id across processes; unit tests on each tier + normalization edge cases.
- Post-migration: 0 duplicate-DOI records; every paper has `scilit-identity-basis`/`-value`; relation counts unchanged (spot-check aboutness / hinges / derivations before vs after); reference-key prefixes resolve to existing paper ids.
- Re-running ingestion over the same inputs creates **0 new papers** (idempotent upsert).
- Full text: every held paper with a cached PDF has a linked `pdf` artifact at `fulltext/<paper-id>/source.pdf`; `paper → fulltext` resolvable by pure path computation.
- Spot-check the known collision (`10.1056/nejmoa1805819`) collapses to a single record with all relations retained.

## Deferred / future

- Redesign the citation/reference-key model to a position-independent `cites(citing → cited)` edge keyed by the cited paper's identity (separate spec).
- Promote `paper_identity` + the full-text layout to a shared core utility if other skills adopt them.
