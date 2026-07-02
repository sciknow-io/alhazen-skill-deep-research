# KQED Sensemaking Dashboard — Design Spec (converged)

- **Date:** 2026-06-25
- **Status:** Approved (design). Implementation in progress.
- **Scope:** A **read-only**, **investigation-centered**, **domain-general** redesign of the
  scientific-literature dashboard around the KQED methodology, plus the agent-side pipelines (capture →
  survey → ground → synthesize) that produce what it displays.

## Context

The KG is rich (425 papers + populated KQED primitives) but the dashboard doesn't let an end user read the
literature through the KQED lens. Primary user: a newcomer orienting to a field (aging biology is the first
domain) who also serves experts. **Nothing in the core flow assumes biology** — biology is one configured
profile; the abstractions are generic.

## The model

**The investigation is the top-level unit, defined at framing time by:**
1. a stated **question/goal**,
2. its **scope** (which papers/corpus), and
3. its **grounding policy / domain profile** — captured **in the knowledge graph as part of the investigation**
   (NOT a global yaml file): the trusted ontologies/vocabularies, the per-kind category→ontology mapping, and
   the relationship-predicate vocabulary for this investigation's domain.

KQED elaborates a model answering the question across three systems — **discourse (S1) / epistemology (S2) /
mechanism-or-relationships (S3)**.

### Domain-general abstractions (no bio assumption)

- **Entity** = a generic domain entity with a verbatim mention + a **kind hint** (gene, protein, process,
  chemical, cell-type … *or* model, system, technique, benchmark, org … — any domain). Grounded later to a
  **category** and an **instance term** from the investigation's profile.
- **Relationship** = a generic typed edge `subject —predicate→ object` with a verbatim relation and, after
  grounding, a canonical **predicate** (e.g. RO/Biolink for biology; domain-appropriate predicates elsewhere).
- Biology (`bioentity`, mechanistic links, GO/CHEBI/CL/RO/Biolink) is one **profile**, not the base.

### Two clean separations

- **Capture (text) is separate from grounding.** Pass 1 captures mentions + kind hints + typed edges
  *verbatim*, committing to no ontology. Grounding is a later, targeted pass.
- **Sensemaking (generic, per-paper) is separate from analysis (per-investigation).** Sensemaking breaks each
  paper down as written, reusable across investigations; analysis addresses the investigation's question by
  reasoning across the in-scope papers.

## Pipeline (producer = Claude in conversation; consumer = read-only dashboard)

1. **Frame investigation** — capture **question + scope + grounding policy (in the KG)**.
2. **Capture (text, ungrounded)** — reuse the existing per-paper sensemaking framework; add a **kind hint** on
   each entity. No new sensemaking framework.
3. **Survey** — aggregate the ungrounded mentions + edges across the in-scope papers: what entities/relationships
   recur, do they cover the goals; emit a **grounding worklist** (feedback loop back to capture if gaps).
4. **Ground the types** — using the investigation's policy, ground the recurring **entity categories** and
   **relationship predicates** the survey surfaced (the typed schema).
5. **Ground the instances** — resolve entity mentions to ontology terms (category/kind-aware), per the policy;
   `ungrounded` stays first-class (marked, still shown).
6. **Synthesize** — deterministic **group-by on grounded `(subject-CURIE, predicate-CURIE, object-CURIE)`**;
   stance from **predicate agreement/opposition** across papers → `consensus | contested | emerging`. Writes
   `scilit-synthesis-note`s (analysis) that address the investigation's question/gaps.
7. **Dashboard** renders it, read-only.

## Core principles

1. **Display-only dashboard** — renders KG output; never writes or triggers work; user questions go through the
   agent (often as a new/refined investigation).
2. **Producer/consumer split** — write verbs (frame/capture/survey/ground/synthesize) vs read verbs (`show-*`/`list-*`).
3. **Grounding is goal-driven** — the survey + the investigation's own policy decide what to ground; never blanket.
4. **Falsifiable to the fragment** — synthesis note → evidence (per-paper sensemaking) → `alh-derivation` →
   fragment → paper.
5. **Ungrounded is first-class** — domains with thin ontology coverage still work.

## Grounding (lookup is pluggable, policy lives in the KG)

- Lookup client resolves a mention to a candidate term from the **investigation's trusted sources** (OLS4 hosts
  many ontologies; non-OLS resolvers — Wikidata, HGNC/UniProt, custom — are pluggable per profile).
- **QC gate** (pure, takes the investigation's policy as a dict): trusted-source check, kind/branch match,
  not-obsolete, CURIE resolves, match-quality threshold, ambiguity guard → failures = `needs-review`.
- **CURIE conventions** (Bioregistry-normalized) + IRI + source cached into the KG. **Conservative lump/split**:
  ground coarse to the highest unambiguous trusted term; finer distinctions live in retained text.
- **Deterministic identity** (`entity_identity`, mirrors `paper_identity`): CURIE-keyed when grounded, name-hash
  fallback when ungrounded → a canonical entity is one node.

## Data model delta (scilit `schema.tql` only — no core edits)

- Generic **entity** + **typed relationship** abstractions (generalize `scilit-bioentity`/`scilit-mechanistic-link`;
  biology becomes a profile/specialization). New attrs: `scilit-entity-kind` (capture), `scilit-predicate-curie`
  (grounded predicate on the edge), `scilit-grounding-state`.
- **`scilit-ontology-term sub alh-vocabulary-type`** (+ `scilit-curie`, `scilit-ontology-source`, `scilit-obsolete`;
  explicit `plays alh-classification:type-facet`, `alh-type-hierarchy:subtype/supertype`). Entity redeclares
  `plays alh-classification:classified-entity`. Grounding = `alh-classification` (provenance+confidence);
  ancestry = `alh-type-hierarchy`.
- **Investigation** gains `scilit-investigation-question` and a **grounding-policy captured in the KG**: a
  `scilit-grounding-policy` entity (one per investigation) holding the profile (trusted sources, per-kind
  category→ontology mapping, predicate vocabulary, threshold), linked to the investigation. NOT a yaml file.
- **Re-parent `scilit-observation`** → `alh-sensemaking-note` (per-paper, as-written; non-destructive `redefine`).
- **Reuse `scilit-synthesis-note`** (sub `alh-analysis-note`) for analysis. Add `scilit-synthesis-evidence`
  (note ↔ per-paper claim/observation); reuse `scilit-addresses` (note→gap), `alh-aboutness` (note→concept).
- `scilit-investigation-type` free string → kqed/deep-dive/survey/meeting are data, not schema. **No `scilit-topic`.**

## Information architecture — hub + per-investigation templates

Home `/` = hub: **Investigations** (cards = question + type badge) + **Collections/Corpora**. An
`investigation-type → template` registry dispatches `/investigation/[id]` (default = tabular reader).
- **Template A — KQED** (`kqed`/`deep-dive`): question → **analysis answer** (synthesis notes, stance badges,
  evidence chips) → S1 Discourse / S2 Epistemology / S3 Relationships (grounded typed graph, SVG). Chips drill to
  per-paper sensemaking → `/concept/[curie]` & `/paper/[id]` → fragment.
- **Template B — Survey/meeting tabular reader** (`survey`/`meeting`, e.g. CAIS): document × notes table; no graph.
- `/concept/[curie]` = ontology-term hub (label/def/CURIE→OLS link + everything grounded to it).

## Phases (each independently shippable)

- **P1 — Foundations & investigation framing:** generic entity/relationship schema + attrs; `scilit-ontology-term`;
  `scilit-investigation-question` + `scilit-grounding-policy` (in KG); framing verbs; pure `entity_identity` module.
- **P2 — Capture + Survey:** reuse existing sensemaking + capture `scilit-entity-kind`; `survey-entities` verb
  (coverage + grounding worklist; feedback loop). Re-parent `scilit-observation`.
- **P3 — Grounding + Synthesis:** pluggable lookup client + pure QC (policy from the investigation) + identity;
  type-grounding (categories + predicates) + instance-grounding driven by the worklist + policy; deterministic
  group-by on grounded `(subject,predicate,object)` + predicate stance → synthesis notes; read verb `show-investigation`.
- **P4 — Read-only dashboard:** hub + templates A/B + concept/paper; read verbs; build via skill `dashboard/` only.

## Verification

- Pure unit tests (pytest, no DB): `entity_identity` (CURIE + name fallback, determinism); QC gate (each check;
  domain-general — passes a non-bio policy too).
- Framing: an investigation stores question + scope + a grounding policy IN the KG (round-trips via `show-investigation`).
- Survey: ungrounded captures aggregate into a coverage table + worklist for the in-scope papers.
- Grounding: a biology investigation grounds SIRT3/SOD2→PR/HGNC, ROS→CHEBI:26523 under ITS policy; a non-bio
  investigation grounds under a different policy with no bio assumption; ungrounded → first-class.
- Synthesis: group-by on grounded triples; opposing predicates on one pair → contested; chip → evidence → fragment.
- Dashboard: hub; KQED investigation → question + analysis + SVG graph; survey (CAIS) → tabular reader; read-only
  invariant (routes call only `show-*`/`list-*`).

## Reuse map

`paper_identity.py`/`upsert_paper`; `kqed.py` `add_vocab/add_vocab_term/classify/add_observation/add_claim/
add_hinge/add_bioentity/add_mech_link/add_gap/ground_note`;
requests + `~/.alhazen/cache` HTTP convention; dashboard 4-slot build + `lib.ts:runScilit`/`atoms.tsx`/`tokens.ts`/
`embedding-map.tsx` SVG. **Superseded:** the topic-centered version, any standalone `grounding_policy.yaml`,
and `prototypes/import_deepdive.py` (deleted — superseded by CLI re-curation via element-set + KEfED verbs).
