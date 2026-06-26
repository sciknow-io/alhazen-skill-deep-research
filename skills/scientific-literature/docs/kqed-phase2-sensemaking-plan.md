# Phase 2 — Generic Per-Paper Sensemaking: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement
> task-by-task. Steps use checkbox (`- [ ]`) syntax. **Depends on Phase 1** (CURIE bioentity identity).

**Goal:** Break each paper down **as written** into reusable, paper-scoped sensemaking notes (extraction,
observations, methodology, the claims and mechanism the paper states, with grounded bioentities) —
investigation-independent so the same breakdown serves any investigation.

**Architecture:** Sensemaking notes are `alh-sensemaking` notes linked to the paper by `alh-aboutness` (NOT
threaded under an investigation). A `sensemake-paper` verb persists a structured breakdown the agent produced;
`show-paper-sensemaking` reads it back. Mechanism statements create grounded bioentities via Phase-1
`upsert_bioentity`.

**Tech Stack:** Python 3.12, TypeDB 3.8, pytest.

## Global Constraints

- Feature branch; `make db-export` before the schema redefine or any migration.
- scilit-namespaced schema only; TypeDB 3.x rules (bound vars, `links`, `escape_string`, raw UTF-8,
  `delete has $v of $e;`, explicit `plays` on subtypes).
- **Sensemaking is generic & paper-scoped: a sensemaking note links to the paper (`alh-aboutness`) and MUST
  NOT reference any investigation.** Reuse across investigations is the point.
- Reuse `kqed.py` helpers (`w/r/_has/_exists/escape_string/get_timestamp/generate_id`, `ground_note`,
  `upsert_bioentity` from Phase 1) and the existing `add_observation/add_claim/add_mech_link` shapes.
- Run DB-guarded tests: `TYPEDB_DATABASE=alhazen_notebook uv run --with pytest python -m pytest tests/<f> -q`.

---

### Task 1: Re-parent `scilit-observation` into the sensemaking tier

**Files:** Modify `schema.tql` (change the `scilit-observation` supertype).

**Interfaces:** Produces: `scilit-observation sub alh-sensemaking-note` (was `sub alh-note`).

- [ ] **Step 1: Back up** — `cd /Users/gullyburns/skillful-alhazen && make db-export`.
- [ ] **Step 2: Edit `schema.tql`** — change the `entity scilit-observation sub alh-note,` line to
  `entity scilit-observation sub alh-sensemaking-note,` (keep all `owns`/`plays`).
- [ ] **Step 3: Apply non-destructively on the live DB** (preserves the 466 instances):
```bash
TYPEDB_DATABASE=alhazen_notebook uv run python - <<'PY'
from typedb.driver import TypeDB, Credentials, DriverOptions, TransactionType
d=TypeDB.driver("localhost:1729",Credentials("admin","password"),DriverOptions())
with d.transaction("alhazen_notebook",TransactionType.SCHEMA) as tx:
    tx.query("redefine entity scilit-observation sub alh-sensemaking-note;").resolve(); tx.commit()
with d.transaction("alhazen_notebook",TransactionType.READ) as tx:
    n=len(list(tx.query('match $o isa scilit-observation, has id $i; fetch {"i":$i};').resolve()))
print("observations after reparent:", n)
PY
```
Expected: `observations after reparent: 466` (count unchanged).

- [ ] **Step 4: Commit** — `git add schema.tql && git commit -m "refactor(scilit): scilit-observation -> alh-sensemaking-note (per-paper as-written)"`

---

### Task 2: Paper-scoped sensemaking helpers in `kqed.py`

**Files:** Modify `kqed.py`; Test `tests/test_paper_sensemaking.py` (DB-guarded).

**Interfaces:**
- Produces: `add_paper_observation(driver, paper_id, statement, knowledge_level, bio_scale, frags=None) -> oid`;
  `add_paper_claim(driver, paper_id, statement, claim_type="primary", frags=None) -> cid`;
  `add_paper_mech_link(driver, paper_id, source_meta, mtype, target_meta, confidence=0.8) -> None`
  (uses `upsert_bioentity`; records the link is asserted-by this paper via `alh-aboutness` on the source claim).
  All link to the paper via `alh-aboutness`, never to an investigation.

- [ ] **Step 1: Write the DB-guarded test** `tests/test_paper_sensemaking.py`
```python
import pytest; pytest.importorskip("typedb.driver")
import kqed as K

def _d():
    try: return K.get_driver()
    except Exception: pytest.skip("TypeDB not reachable")

def test_observation_is_about_paper_not_investigation():
    d=_d()
    try:
        papers=K.r(d,'match $p isa scilit-paper, has id $i; fetch {"i":$i};')[:1]
        if not papers: pytest.skip("no papers")
        pid=papers[0]["i"]
        oid=K.add_paper_observation(d,pid,"TEST obs as written","observation","molecular")
        about=K.r(d,f'match $o isa scilit-observation, has id "{oid}"; $p isa scilit-paper, has id "{pid}"; '
                   f'(note: $o, subject: $p) isa alh-aboutness; fetch {{"ok": $p.id}};')
        assert about, "observation must be about the paper"
        K.w(d,f'match $o isa scilit-observation, has id "{oid}"; delete $o;')  # cleanup
    finally: d.close()
```

- [ ] **Step 2: Run — verify it fails** (`add_paper_observation` missing).
- [ ] **Step 3: Implement in `kqed.py`** (paper-scoped variants of the existing creators)
```python
def add_paper_observation(driver, paper_id, statement, knowledge_level, bio_scale, frags=None):
    oid = generate_id("scobs"); ts = get_timestamp()
    w(driver, f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
              f'insert $o isa scilit-observation, has id "{oid}", has name "{escape_string(statement[:60])}", '
              f'has content "{escape_string(statement)}", has scilit-knowledge-level "{escape_string(knowledge_level)}", '
              f'has scilit-bio-scale "{escape_string(bio_scale)}", has created-at {ts}; '
              f'(note: $o, subject: $p) isa alh-aboutness;')
    if frags: ground_note(driver, oid, frags)
    return oid

def add_paper_claim(driver, paper_id, statement, claim_type="primary", frags=None):
    cid = generate_id("scclaim"); ts = get_timestamp()
    w(driver, f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
              f'insert $c isa scilit-claim, has id "{cid}", has name "{escape_string(statement[:60])}", '
              f'has scilit-claim-type "{escape_string(claim_type)}", has scilit-claim-statement "{escape_string(statement)}", '
              f'has created-at {ts}; (note: $c, subject: $p) isa alh-aboutness;')
    if frags: ground_note(driver, cid, frags)
    return cid

def add_paper_mech_link(driver, paper_id, source_meta, mtype, target_meta, confidence=0.8):
    s = upsert_bioentity(driver, source_meta); t = upsert_bioentity(driver, target_meta)
    if not _has(driver, f'$s isa scilit-bioentity, has id "{escape_string(s)}"; $t isa scilit-bioentity, has id "{escape_string(t)}"; '
                        f'$ml isa scilit-mechanistic-link, links (mech-source: $s, mech-target: $t);'):
        w(driver, f'match $s isa scilit-bioentity, has id "{escape_string(s)}"; $t isa scilit-bioentity, has id "{escape_string(t)}"; '
                  f'insert (mech-source: $s, mech-target: $t) isa scilit-mechanistic-link, '
                  f'has scilit-mech-type "{escape_string(mtype)}", has confidence {confidence};')
    return s, t
```

- [ ] **Step 4: Run — verify it passes.** **Commit**
`git add kqed.py tests/test_paper_sensemaking.py && git commit -m "feat(scilit): paper-scoped sensemaking creators (observation/claim/mech-link)"`

---

### Task 3: CLI — `sensemake-paper` (write) + `show-paper-sensemaking` (read)

**Files:** Modify `scientific_literature.py`.

**Interfaces:**
- Produces: `sensemake-paper --id <paper> --records <json-file>` where the JSON is
  `{observations:[{statement,knowledge_level,bio_scale,frags?}], claims:[{statement,type?,frags?}],
  mech_links:[{source:{name,curie?}, type, target:{name,curie?}}]}`; idempotent on content.
  `show-paper-sensemaking --id <paper>` returns `{paper, observations:[], claims:[], mech_links:[], grounded_concepts:[]}`.

- [ ] **Step 1: Add subparsers + dispatch**
```python
    p = subparsers.add_parser("sensemake-paper", help="Persist a per-paper sensemaking breakdown (as written)")
    p.add_argument("--id", required=True); p.add_argument("--records", required=True, help="path to breakdown JSON")
    p = subparsers.add_parser("show-paper-sensemaking", help="Read a paper's generic sensemaking")
    p.add_argument("--id", required=True)
```
```python
        "sensemake-paper": cmd_sensemake_paper,
        "show-paper-sensemaking": cmd_show_paper_sensemaking,
```

- [ ] **Step 2: Implement** (content-idempotency: skip an observation/claim whose statement already exists about the paper)
```python
def cmd_sensemake_paper(args):
    rec = json.load(open(args.records, encoding="utf-8"))
    n_obs = n_cl = n_ml = 0
    with get_driver() as d:
        if not K._exists(d, args.id):
            print(json.dumps({"success": False, "error": "paper not found"})); sys.exit(1)
        for o in rec.get("observations", []):
            if not K._has(d, f'$o isa scilit-observation, has content "{escape_string(o["statement"])}"; '
                            f'$p isa scilit-paper, has id "{escape_string(args.id)}"; (note: $o, subject: $p) isa alh-aboutness;'):
                K.add_paper_observation(d, args.id, o["statement"], o.get("knowledge_level","observation"),
                                        o.get("bio_scale","molecular"), o.get("frags")); n_obs += 1
        for c in rec.get("claims", []):
            if not K._has(d, f'$c isa scilit-claim, has scilit-claim-statement "{escape_string(c["statement"])}"; '
                            f'$p isa scilit-paper, has id "{escape_string(args.id)}"; (note: $c, subject: $p) isa alh-aboutness;'):
                K.add_paper_claim(d, args.id, c["statement"], c.get("type","primary"), c.get("frags")); n_cl += 1
        for m in rec.get("mech_links", []):
            K.add_paper_mech_link(d, args.id, m["source"], m["type"], m["target"], m.get("confidence",0.8)); n_ml += 1
    print(json.dumps({"success": True, "paper": args.id, "observations": n_obs, "claims": n_cl, "mech_links": n_ml}, indent=2))

def cmd_show_paper_sensemaking(args):
    with get_driver() as d:
        obs = K.r(d, f'match $p isa scilit-paper, has id "{escape_string(args.id)}"; $o isa scilit-observation; '
                     f'(note: $o, subject: $p) isa alh-aboutness; $o has id $oid, has content $c, '
                     f'has scilit-knowledge-level $kl, has scilit-bio-scale $bs; '
                     f'fetch {{"id": $oid, "content": $c, "knowledge_level": $kl, "bio_scale": $bs}};')
        claims = K.r(d, f'match $p isa scilit-paper, has id "{escape_string(args.id)}"; $c isa scilit-claim; '
                        f'(note: $c, subject: $p) isa alh-aboutness; $c has id $cid, has scilit-claim-statement $s; '
                        f'fetch {{"id": $cid, "statement": $s}};')
    print(json.dumps({"success": True, "paper": args.id, "observations": obs, "claims": claims}, indent=2))
```

- [ ] **Step 3: Smoke test** — write a tiny breakdown JSON for one paper, run `sensemake-paper`, then
  `show-paper-sensemaking --id <paper>`; confirm the observations/claims come back and are about the paper.

- [ ] **Step 4: Commit** — `git add scientific_literature.py && git commit -m "feat(scilit): sensemake-paper + show-paper-sensemaking verbs"`

---

### Task 4: Refit the deep-dive importer to paper-scoped sensemaking

**Files:** Modify `prototypes/import_deepdive.py`.

**Interfaces:** Consumes the Task-2 paper-scoped creators. Produces: per-paper observations/claims/mech-links
that are **about the paper** (reusable), while the investigation linkage (claims/gaps that answer its question)
moves to Phase 3.

- [ ] **Step 1: Replace investigation-threaded creation of observations/claims/mech-links** in
  `import_deepdive.py` with the paper-scoped helpers (`add_paper_observation`, `add_paper_claim`,
  `add_paper_mech_link`). Keep gap creation and CFC hinge wiring (those are discourse/epistemic structure),
  but the per-paper breakdown now attaches to the paper, not the investigation.

- [ ] **Step 2: Dry-run on one deep-dive record** and confirm the created notes are about the paper
  (`show-paper-sensemaking --id <focal-paper>` returns them) and NOT solely threaded under the investigation.

- [ ] **Step 3: Commit** — `git commit -am "refactor(scilit): deep-dive importer creates paper-scoped sensemaking"`

---

### Task 5: Backfill — existing investigation-bound notes get paper aboutness

**Files:** Create `prototypes/backfill_paper_aboutness.py`.

**Interfaces:** Additive only — for each existing `scilit-observation`/`scilit-claim` that is threaded under an
investigation and lacks an `alh-aboutness` to a paper, add it from the investigation's focal paper. Never deletes.

- [ ] **Step 1: Write the backfill** (match notes under an investigation, find that investigation's focal paper
  via its `alh-aboutness`/focal link, insert the missing `(note,subject:paper)` aboutness). Dry-run default.
- [ ] **Step 2: Back up + dry-run + apply**; verify every Layer-1 note now has a paper aboutness.
- [ ] **Step 3: Commit.**

---

## Self-Review notes
- Spec coverage: re-parent (T1), paper-scoped creators (T2), write/read verbs (T3), importer refit (T4),
  backfill (T5) — covers "break the paper down as written, paper-scoped, reusable."
- Sensemaking creators take NO investigation argument — enforces the generic/reusable rule.
- Whole-phase verification: `sensemake-paper` a paper, then attach it (in Phase 3) to two different
  investigations and confirm both reuse the same Layer-1 notes (no duplication).
