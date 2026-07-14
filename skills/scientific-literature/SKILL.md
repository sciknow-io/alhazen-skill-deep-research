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

## KEfED Model Authoring — templates first; instantiate by binding grounded values

**The standard is templates-first.** A KEfED model (`kefed-model`, a **graph of
`kefed-model-node`s** reconstructing an experiment) is authored as an **instance of a reusable,
documented design TEMPLATE** — never built ad hoc per paper. The design skeleton is reusable and
comparable across papers; the scientific meaning lives entirely in the **semantics and background
knowledge linked to the grounded VALUES** bound to the template's parameters and constants.

**Workflow:** `recognize the design type → find-or-create a template → instantiate it under the
paper's bundle → bind grounded values → compose templates for multi-arm designs`. This makes
correctness a structural consequence of reuse rather than per-paper vigilance.

### Per-paper KEfED sensemaking — the (A)–(D) procedure

Run these four steps for every paper, then gate the result with `lint-sensemaking` (below). Steps
(B)–(D) are enforced by machine checks; step (A)'s *completeness* is not lintable (nothing can know
which experiments you failed to enter) — it is a discipline you owe the paper.

- **(A) Enumerate every experiment.** A paper usually runs *many* experiments (often 20+), spread
  across sections and figures. Before modelling, inventory them: walk the figures/tables and the
  claims and list each distinct experiment that produces evidence. Each becomes its own KEfED model
  (an inline experiment, or an instance of a template). *Completeness is on you; the linter only
  checks the models you build are well-formed.*
- **(B) Describe each experiment as a BIPARTITE bigraph.** Nodes are **entities** (`material-entity`
  or an information/**dataset** ICE) and **processes** (`assay` | `material-processing` |
  `data-transformation`). A process's inputs and outputs are entities. **An entity never flows into
  another entity, and a process never flows into another process** — every flow edge joins an entity
  to a process. `link-nodes` enforces this at write-time (`--role input` ⇒ entity→process; `--role
  output` ⇒ process→entity; `--force` overrides); `_chk_bipartite` + `_chk_flow_roles` re-check it,
  and `_chk_acyclic` verifies the graph is a DAG. *(A future graph-grammar layer — a Synchronous
  Hyperedge Replacement Grammar (SHRG), e.g. via Bolinas — will recognise richer design-pattern
  grammars; export a model's hypergraph term today with `show-experiment --id <m> --format hgraph`.)*
- **(C) Attach parameters; read the data signature.** Put each `parameter`/`constant` on the
  biologically-correct node (rule 4 below) and each `measurement` on the process that measures it.
  The **data signature** of a measurement — the parameter set that indexes its readout — is then
  *computed* by tracing the bigraph (`show-data-signature`), not hand-assigned.
- **(D) Capture how data-transformations remap the index — explicitly.** A `data-transformation`
  that combines datasets can *change or destroy* index parameters, and this cannot be inferred from
  the graph. Declare it with **`map-params`** (writes `ooevv-param-mapping`): `passthrough` (an index
  param survives), `aggregate-collapse-destroy` (it is **consumed** — e.g. a correlation coefficient
  or a mean-over-replicates collapses the per-sample index), `combine` (≥2 params fold into one
  derived contrast), `derive` (a new param appears). `show-data-signature` applies these rules so the
  computed value carries the *correct* index (and reports what was `consumed`); `_chk_transformation_mapping`
  **fails** any index-consuming transformation left undeclared (it would otherwise default to naive
  passthrough — the classic signature-inflation bug).

### Model-quality gate — `lint-sensemaking --id <paper>`

Runs the OOEVV/KEfED/rhetoric checks over the paper's whole curation (inline experiments **and** the
templates behind its instances). The KEfED-category checks encode (B)–(D): `bigraph-bipartite`,
`bigraph-flow-roles`, `bigraph-acyclic`, `experiment-has-subject`, `nodes-connected`, and
`transformation-mapping`. Treat any `fail` as blocking — a well-formed model passes all six.

**A template = a documented design pattern** (`ensure-template`, `kefed-model-state: template`): a
generic bigraph plus a stated **purpose** and the **warrant** its data-signature licenses (e.g.
*sufficiency* = a phenotype readout indexed by `{transgene × induction}`). Its data-signature
topology is the template's fingerprint: any experiment with that signature IS an instance of that
design type, regardless of which gene/reagent/cell fills it. **Recognize before you build:**
`list-templates` / `list-qualities` / `list-entities`.

Build (or extend) a template's generic graph with these principles:

1. **Reconstruct the real protocol from the paper's Methods.** Read the Experimental Procedures and
   build the actual material chain — *organism → sample preparation → sample → manipulation → manipulated_sample → assay → readout* — 
   including where cells came from and how they were prepared (harvest, sort, lineage-deplete, transduce, transplant,
   culture...). The **combination of nodes in the graph carries the experimental-design semantics**, not
   any single node.

2. **Minimal ontological commitment per node; maximum reuse.** Node *definitions* are **generic and
   reusable** — `experimental mouse`, `bone-marrow harvest`, `competitive transplantation` — NOT
   `HSC (WT or SIRT3-KO mouse)`. What differentiates *this* experiment lives in the attached **variables +
   values**, never in node names. Share one OOEVV element wherever the concept genuinely recurs:
   `add-entity-node` / `add-process` find-or-create a def by name **within the model's element-set**, so
   pass `add-experiment --element-set <id>` to make a family of experiments **share one element-set** and
   thus one def per concept (verify: distinct defs ≪ node count).
   **A node name is the KIND of thing, never its specifics.** Strip every specific out of the name and
   move it into a variable: `C57BL/6 male mouse` → `mouse` (+ `strain`, `sex`, `species`);
   `aged mouse tail-tip fibroblasts` → `fibroblast` (+ `tissue source`, `donor age state`, `species`);
   `MeV-derived iPSC clones` → `iPSC clone` (+ `reprogramming vector`);
   `S. cerevisiae ancestor strain (RWY12/BY4741, tlc1-delta)` → `yeast strain` (+ `strain background`,
   `telomere genotype`). **Drop parentheticals** that encode sample size / provenance / genotype
   (`(811 single cells)`, `(all cell types)`, `(humanized line)`) — put that in the node's DEFINITION.

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
   **A `measurement` lives on the PROCESS that measures it** (an `assay`, or the `data-transformation`
   that computes the reported value) — **never on a bare trailing data-product entity**. If you find a
   trailing "result/profile/matrix/readout" *entity* that carries the measurements, it is an **analysis
   process mislabeled as an entity**: retype it to `data-transformation` (keep its indexing parameters,
   e.g. `cell type identity`, on it), or move the measurements onto the upstream assay and drop the empty
   entity. Measurements on a process keep them co-indexed by that process's parameters.

5. **Model the HIDDEN process that generated or sorted a specialization.** When an entity's distinguishing
   property is the *result of a procedure*, add that procedure as an explicit node and attach the property
   as **its** parameter — do not bury it in a name:
   - a genotype from a knockout / allele edit → a `material-processing` node (`genetic modification`,
     `TLC1 humanization`) that **outputs** the strain, carrying the genotype parameter;
   - a cell-type from clustering / annotation → a `data-transformation` (`cell-type clustering`) carrying
     `cell type identity` (this is "the process that sorted them");
   - a derived cell state (iPSC, reprogramming intermediate) → the reprogramming process that produced it.
   Add such a node when the paper's workflow genuinely implies it; for standard reagents (an inbred strain,
   a catalog cell line) capture identity as a **constant** rather than inventing a procurement step.

6. **Compose templates for multi-arm designs.** When an experiment chains designs — e.g. a
   conditional-overexpression *sufficiency* assay whose output feeds a *conditioned-media bioassay*
   on a second cell type — instantiate BOTH templates and wire one's **exported** node as the
   other's **imported** input. The downstream arm then inherits the upstream arm's full
   data-signature through the transfer edge automatically (a paracrine readout is correctly indexed
   by its *source's* `{transgene × induction × time}`). **Never hand-duplicate a shared parameter** —
   place each parameter once, at the upstream node where it is set, and let the flow graph propagate
   it (duplicating it downstream is the classic signature-inflation bug).

7. **Instantiate by binding GROUNDED values — this is where meaning lives.** `instantiate-template
   --bundle --template` creates the instance; fill each parameter/constant with `add-datum` (grounded
   values, one row per data point). Every bound value carries the science and must be grounded to a
   real term — genes/proteins → HGNC/PR, chemicals → CHEBI, cells → CL/CLO, qualities → PATO/EFO —
   **looked up, never invented** (e.g. `transgene = CHOP → HGNC:DDIT3`, `inducer = doxycycline →
   CHEBI`, `subject = MLE12 → CLO`). Template structure + grounded values = the interpretable claim.
   Corollary: because all cross-paper variation is in the bound values, a *bound constant* such as the
   inducing reagent is freely swappable (doxycycline → 4-OHT → IPTG) while the design feature it
   expresses — here inducibility, which buys a within-line ± control — is what the template guarantees.

**Read the figure/table, not just the legend.** The legend + Methods give the template *structure*;
the figure/table IMAGE gives the instance's *data-signature dimensions and values* (panel layout, axes,
series, bar heights, significance). Run **`extract-floats --id <paper>`** (a curation precondition
alongside `fetch-pdf`/`parse-pdf-blocks`) to render each figure/table to a PNG stored as a
`scilit-figure`/`scilit-table` fragment on the paper's full-text artifact. Detection is
**caption-anchored + negative-space**: `Fig N`/`Table N` captions anchor floats, and a float region is
low-body-text page area carrying graphical content (raster **or** vector drawings **or** ruled table
grid) — so it handles vector-native figures, ruled tables, cross-page legends, and multiple floats per
page, and it **flags (never guesses)** any region it cannot pair to a caption. Then read each float
image to fill the instance's `add-datum` rows. **Value source, in order of preference:** a real
source-data table (supplement / GEO) → the float's `find_tables` rows → chart-read estimates (tag these
`value-source: figure-estimate`). Link each datum's observation to the float's fragment id + panel so
evidence traces to the pixels.

**Grounding policy (non-negotiable):** attach a curie **only** when a real ontology term's definition
genuinely matches the intended meaning. If a term can't be grounded, or the candidate's definition is
wrong, **OMIT the grounding** — better ungrounded-with-a-precise-local-definition than wrongly grounded.

**Verb sequence.** *Author/extend a template:* `ensure-template [--element-set]` → `add-entity-node
--template <sctpl> --subject` / `add-process --template <sctpl> --type` → `link-nodes --role
input|output` (bipartite-enforced) → `ensure-quality [--curie]` → `ensure-value-spec --quality
--scale-type` → `add-variable --value-spec` → `map-params --transformation <knode> --rule <kind>`
for every index-remapping data-transformation (D) → `show-template` / `show-data-signature` to
verify the fingerprint. *Instantiate for a paper:* `instantiate-template --bundle <scsense>
--template <sctpl>` → `add-datum --cells` (grounded values, one row per data point) →
`show-instance`. A genuinely novel one-off with no template can still be built directly with
`add-experiment [--element-set]`, but prefer promoting the recurring design to a template. Finish
with `lint-sensemaking --id <paper>` and clear every KEfED `fail`.

**Correcting an existing model (edit verbs).** To bring an already-curated model up to the rules above
without rebuilding it — the node id, its variables and its flow edges are preserved:
- `rename-node --node <knode> --name "<generic>"` — make an over-specific entity name generic (renames
  the node and its sole-use OOEVV def).
- `retype-node --node <knode> --type <material-entity|assay|material-processing|data-transformation>
  [--name "<n>"]` — fix a mislabeled node (e.g. a measurement-bearing "result/profile" *entity* → the
  `data-transformation` that produced it).
- `move-variable --variable <scvar> --to-node <knode>` — canonicalize a measurement onto its measuring
  process, or move a specialization parameter onto the hidden process that sets it (rule 5).
- `set-node-definition --node <knode> --definition "..."` — park stripped-out specifics in the definition.
- `delete-node --node <knode>` — drop an emptied trailing entity (refuses while it still carries
  variables; move them off first). Re-check `show-data-signature` after any edit — indices should only
  get richer, never disappear.

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
