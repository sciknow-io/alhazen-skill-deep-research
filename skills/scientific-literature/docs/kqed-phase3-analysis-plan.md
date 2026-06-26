# Phase 3 — Investigation Framing + Analysis: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use
> checkbox (`- [ ]`) syntax. **Depends on Phases 1–2** (CURIE grounding; paper-scoped sensemaking).

**Goal:** Give an investigation a stated **question/goal**, then produce **analysis** (`scilit-synthesis-note`)
that **answers the question** by clustering the in-scope papers' Layer-1 sensemaking on grounded anchors and
reconciling agreement/conflict via Teufel-CFC hinges — each synthesis note carrying a stance and evidence links.

**Architecture:** A pure `cluster_synthesis` module (clustering + stance reconciliation) is unit-tested without
a DB. A DB layer reads Layer-1 sensemaking for the investigation's papers, runs the pure clustering, and writes
synthesis notes with evidence/concept/gap links. `analyze-investigation` is the producer verb; `show-investigation`
is the read verb the dashboard uses.

**Tech Stack:** Python 3.12, TypeDB 3.8, pytest.

## Global Constraints

- Feature branch; `make db-export` before schema reload.
- scilit-namespaced schema only; TypeDB 3.x rules (bound vars, `links`, `escape_string`, raw UTF-8,
  relations can't be `alh-aboutness` subjects — use `scilit-synthesis-concerns` for mech-links).
- **Analysis is investigation-scoped & addresses the question; it links to Layer-1 sensemaking as evidence.**
- Stance vocabulary: `consensus | contested | emerging`. CFC mapping: contrast→contested,
  support/coreference/uses→consensus, single-or-sparse→emerging.
- Reuse `scilit-synthesis-note` (exists), `scilit-addresses` (note→gap), `alh-aboutness` (note→concept),
  `kqed` helpers + Phase-1 grounding.

---

### Task 1: Schema — investigation question, synthesis stance + links

**Files:** Modify `schema.tql`.

**Interfaces:** Produces attr `scilit-investigation-question`, attr `scilit-synthesis-stance`;
relations `scilit-synthesis-evidence` (relates synthesis-note, relates evidence) and `scilit-synthesis-concerns`
(relates synthesis-note, relates mech-link); plays redeclared on `scilit-synthesis-note`, `scilit-claim`,
`scilit-observation`, `scilit-mechanistic-link`.

- [ ] **Step 1: Edit `schema.tql`**
```tql
attribute scilit-investigation-question, value string;
attribute scilit-synthesis-stance, value string;   # consensus | contested | emerging

relation scilit-synthesis-evidence,
    relates synthesis-note,
    relates evidence;
relation scilit-synthesis-concerns,
    relates synthesis-note,
    relates concerned-link;
```
Add `owns scilit-investigation-question` to `entity scilit-investigation`. Add to `scilit-synthesis-note`:
`owns scilit-synthesis-stance, plays scilit-synthesis-evidence:synthesis-note, plays scilit-synthesis-concerns:synthesis-note`.
Add `plays scilit-synthesis-evidence:evidence` to BOTH `scilit-claim` and `scilit-observation`.
Add `plays scilit-synthesis-concerns:concerned-link` to `scilit-mechanistic-link`.

- [ ] **Step 2: Back up + reload schema** (same SCHEMA-transaction snippet as Phase 1 Task 1 Step 3) → `schema OK`.
- [ ] **Step 3: Commit** — `git commit -am "feat(scilit): investigation question + synthesis stance/evidence/concerns"`

---

### Task 2: Pure clustering + stance reconciliation

**Files:** Create `cluster_synthesis.py`; Test `tests/test_cluster_synthesis.py`.

**Interfaces:**
- Produces: `cluster_and_reconcile(items) -> [cluster]`. `items`: list of dicts
  `{id, kind:"claim"|"observation", paper_id, anchor:tuple|str|None, cfc:[str]}` where `anchor` is a grounded
  mech-link `("GO:..","GO:..")` or a single grounded CURIE; `cfc` is the list of Teufel terms on hinges between
  this item and others in scope. `cluster`: `{key, members:[id], papers:set, stance}`.

- [ ] **Step 1: Write the failing test** `tests/test_cluster_synthesis.py`
```python
from cluster_synthesis import cluster_and_reconcile

def test_groups_by_shared_anchor():
    items = [
        {"id":"a","kind":"claim","paper_id":"p1","anchor":("PR:1","PR:2"),"cfc":["PSup"]},
        {"id":"b","kind":"claim","paper_id":"p2","anchor":("PR:1","PR:2"),"cfc":["PSup"]},
        {"id":"c","kind":"observation","paper_id":"p3","anchor":"CHEBI:26523","cfc":[]},
    ]
    cl = {c["key"]: c for c in cluster_and_reconcile(items)}
    assert set(cl[("PR:1","PR:2")]["members"]) == {"a","b"}
    assert cl["CHEBI:26523"]["members"] == ["c"]

def test_stance_contested_on_contrast():
    items=[{"id":"a","kind":"claim","paper_id":"p1","anchor":("X","Y"),"cfc":["PSup"]},
           {"id":"b","kind":"claim","paper_id":"p2","anchor":("X","Y"),"cfc":["PContrast"]}]
    assert cluster_and_reconcile(items)[0]["stance"] == "contested"

def test_stance_consensus_multi_paper_support():
    items=[{"id":"a","kind":"claim","paper_id":"p1","anchor":("X","Y"),"cfc":["PSup"]},
           {"id":"b","kind":"claim","paper_id":"p2","anchor":("X","Y"),"cfc":["CoCoGM"]}]
    assert cluster_and_reconcile(items)[0]["stance"] == "consensus"

def test_stance_emerging_single_paper():
    items=[{"id":"a","kind":"claim","paper_id":"p1","anchor":("X","Y"),"cfc":[]}]
    assert cluster_and_reconcile(items)[0]["stance"] == "emerging"

def test_ungrounded_items_excluded_from_anchor_clusters():
    items=[{"id":"a","kind":"claim","paper_id":"p1","anchor":None,"cfc":[]}]
    out = cluster_and_reconcile(items)
    assert out and out[0]["key"] == "__ungrounded__" and out[0]["stance"] == "emerging"
```

- [ ] **Step 2: Run — verify it fails.**
- [ ] **Step 3: Implement `cluster_synthesis.py`**
```python
"""Pure cross-paper clustering + stance reconciliation for investigation analysis (no DB)."""
from collections import defaultdict

_CONTRAST = {"PContrast", "Contrast", "CoCoR0", "Weak"}        # disagreement signals
_SUPPORT = {"PSup", "PUse", "CoCoGM", "CoCoXY", "Coref"}       # agreement signals

def _stance(members, cfc_all, paper_count):
    if any(t in _CONTRAST for t in cfc_all):
        return "contested"
    if paper_count >= 2 and any(t in _SUPPORT for t in cfc_all):
        return "consensus"
    if paper_count >= 2:
        return "consensus"        # corroborated across papers even without explicit CFC
    return "emerging"

def cluster_and_reconcile(items):
    groups = defaultdict(list)
    for it in items:
        key = it["anchor"] if it.get("anchor") else "__ungrounded__"
        groups[key].append(it)
    out = []
    for key, members in groups.items():
        cfc_all = [t for m in members for t in m.get("cfc", [])]
        papers = {m["paper_id"] for m in members}
        stance = "emerging" if key == "__ungrounded__" else _stance(members, cfc_all, len(papers))
        out.append({"key": key, "members": [m["id"] for m in members], "papers": papers, "stance": stance})
    return out
```

- [ ] **Step 4: Run — verify it passes.** **Commit**
`uv run --with pytest python -m pytest tests/test_cluster_synthesis.py -q` → PASS;
`git add cluster_synthesis.py tests/test_cluster_synthesis.py && git commit -m "feat(scilit): cross-paper clustering + stance reconciliation (pure)"`

---

### Task 3: kqed — write a synthesis note with evidence/concept/stance

**Files:** Modify `kqed.py`; Test `tests/test_synthesis_note.py` (DB-guarded).

**Interfaces:**
- Produces: `add_synthesis_note(driver, investigation_id, statement, stance, evidence_ids, concept_curies=None,
  mech_link=None, gap_id=None) -> sid`. Threads the note under the investigation (`alh-note-threading`),
  links each evidence id via `scilit-synthesis-evidence`, links concepts via `alh-aboutness` to their
  `scilit-ontology-term`, optionally `scilit-synthesis-concerns` the mech-link and `scilit-addresses` a gap.

- [ ] **Step 1: DB-guarded test** — create a synthesis note over two known claim ids; assert it carries the
  stance and resolves both evidence links (`scilit-synthesis-evidence`), then clean up.
- [ ] **Step 2: Implement**
```python
def add_synthesis_note(driver, investigation_id, statement, stance, evidence_ids,
                       concept_curies=None, mech_link=None, gap_id=None):
    sid = generate_id("scsyn"); ts = get_timestamp()
    w(driver, f'match $inv isa scilit-investigation, has id "{escape_string(investigation_id)}"; '
              f'insert $s isa scilit-synthesis-note, has id "{sid}", has name "{escape_string(statement[:60])}", '
              f'has content "{escape_string(statement)}", has scilit-synthesis-stance "{escape_string(stance)}", '
              f'has created-at {ts}; (parent-note: $inv, child-note: $s) isa alh-note-threading;')
    for eid in evidence_ids:
        w(driver, f'match $s isa scilit-synthesis-note, has id "{sid}"; $e has id "{escape_string(eid)}"; '
                  f'insert (synthesis-note: $s, evidence: $e) isa scilit-synthesis-evidence;')
    for curie in (concept_curies or []):
        hit = r(driver, f'match $t isa scilit-ontology-term, has scilit-curie "{escape_string(curie)}"; fetch {{"id": $t.id}};')
        if hit:
            w(driver, f'match $s isa scilit-synthesis-note, has id "{sid}"; $t isa scilit-ontology-term, has id "{escape_string(hit[0]["id"])}"; '
                      f'insert (note: $s, subject: $t) isa alh-aboutness;')
    if gap_id:
        w(driver, f'match $s isa scilit-synthesis-note, has id "{sid}"; $g isa scilit-gap, has id "{escape_string(gap_id)}"; '
                  f'insert (addressing-note: $s, gap: $g) isa scilit-addresses;')
    if mech_link:
        s_curie, t_curie = mech_link
        w(driver, f'match $s isa scilit-synthesis-note, has id "{sid}"; '
                  f'$src isa scilit-bioentity, has scilit-grounding-state "grounded"; (classified-entity: $src) isa alh-classification; '
                  f'$ml isa scilit-mechanistic-link, links (mech-source: $src); '
                  f'insert (synthesis-note: $s, concerned-link: $ml) isa scilit-synthesis-concerns;')
    return sid
```
*(Note: the mech-link binding above is approximate — bind the exact link by matching both endpoints' CURIE
groundings; the implementer refines the match to the specific `(src,tgt)` link.)*

- [ ] **Step 3: Run — verify it passes. Commit.**

---

### Task 4: CLI — set-investigation-question, analyze-investigation, show-investigation

**Files:** Modify `scientific_literature.py`.

**Interfaces:**
- Produces: `set-investigation-question --id <inv> --question "..."`; `analyze-investigation --id <inv>`
  (reads in-scope papers' Layer-1, builds `items`, runs `cluster_and_reconcile`, writes one synthesis note per
  cluster addressing the question); `show-investigation --id <inv>` → `{question, type, analysis:[{statement,
  stance, evidence:[...]}], gaps:[...], concepts:[...], mech_links:[...]}`.

- [ ] **Step 1: Add subparsers + dispatch** for the three verbs.
- [ ] **Step 2: `cmd_set_investigation_question`** — WRITE the attribute (delete-has then insert if present).
- [ ] **Step 3: `cmd_analyze_investigation`** — scope = papers about/in the investigation
  (`alh-aboutness`/collection membership). For each in-scope paper, read its Layer-1 claims/observations,
  their grounded anchors (via `alh-classification`→`scilit-ontology-term` CURIE, and grounded mech-links),
  and CFC terms on their hinges; build `items`; call `cluster_synthesis.cluster_and_reconcile`; for each cluster
  call `K.add_synthesis_note(...)` with a statement summarizing the cluster, its stance, member evidence ids,
  the cluster's concept curies / mech-link, and any gap it addresses. Idempotent: skip a cluster whose synthesis
  note (by anchor key) already exists for the investigation.
- [ ] **Step 4: `cmd_show_investigation`** — read the question + the investigation's synthesis notes with their
  resolved evidence (`scilit-synthesis-evidence`), concepts (`alh-aboutness`→term), gaps, and mech-links.
- [ ] **Step 5: Smoke test** on the SIRT3/epigenetics deep-dive: set a question, `analyze-investigation`,
  then `show-investigation` returns synthesis notes with stances + evidence; a contested cluster shows ≥2 papers.
- [ ] **Step 6: Commit** — `git commit -am "feat(scilit): set/analyze/show investigation (question + analysis)"`

---

## Self-Review notes
- Pure clustering (`cluster_synthesis`) is DB-free and fully unit-tested; the DB layer only marshals items and
  persists notes — keeps the testable logic separate from I/O (per the risk note in the master plan).
- `analyze-investigation` is the agent-run producer; the LLM-authored cluster *summary statement* is supplied by
  the agent at call time (the deterministic clustering/stance is testable; the prose is the agent's judgment).
- Verification: chip → synthesis-note → `scilit-synthesis-evidence` → Layer-1 claim/observation →
  `alh-derivation` → fragment → paper full text round-trips; rerun `analyze-investigation` is idempotent.
