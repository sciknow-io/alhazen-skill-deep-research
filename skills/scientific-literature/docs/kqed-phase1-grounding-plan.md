# Phase 1 — Ontology Grounding: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ground scilit bioentities/concepts to canonical external ontology terms (OLS4) with a versioned
policy + QC gate, give bioentities deterministic CURIE-based identity, and migrate the 758 existing bioentities.

**Architecture:** Pure decision logic (CURIE normalization, identity, QC gate) lives in import-free modules
with unit tests. OLS I/O + KG writes live behind CLI verbs (the agent/producer). Ontology terms reuse
`alh-vocabulary-type`; grounding reuses `alh-classification`; ancestry reuses `alh-type-hierarchy`.

**Tech Stack:** Python 3.12, TypeDB 3.8 (typedb-driver), `requests`, `pyyaml`, pytest. OLS4 REST.

## Global Constraints

- Work in `~/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature/` on a feature branch;
  `make db-export` (from the alhazen repo) BEFORE any schema reload or migration.
- **scilit-namespaced schema only** — no `alhazen-core` edits.
- TypeDB 3.x: `entity X sub Y, owns a, plays r:role;`; `relation R, relates a;`; `attribute A, value string;`;
  bound-variable matches only; relation matches use `links`; `escape_string` every literal; raw UTF-8 (no `\uXXXX`);
  subtypes must redeclare `plays`; delete-has is `delete has $v of $e;`.
- Pure modules (`bioentity_identity.py`, `ontology_grounding.py` decision logic) MUST NOT import `kqed`/typedb,
  so their tests run without a DB.
- CURIE format `PREFIX:LOCALID`, Bioregistry-normalized prefixes: `GO CL CHEBI HP UBERON MONDO HGNC UniProt`.
- Run tests: `uv run --with pytest python -m pytest tests/<file> -q` (pure tests need no extra deps).
- Reuse `kqed.py` helpers: `w(driver,q)` write, `r(driver,q)` read→list[dict], `_has(driver,pattern)`,
  `_exists(driver,id)`, `escape_string`, `get_timestamp`, `generate_id`, `classify`, `add_vocab`.
- Mirror `paper_identity.py` exactly for the identity helper shape.

---

### Task 1: Schema — ontology term, grounding attributes, bioentity plays

**Files:**
- Modify: `schema.tql` (append a scilit-grounding block; add attrs; add `plays` to `scilit-bioentity`)

**Interfaces:**
- Produces: type `scilit-ontology-term`; attrs `scilit-curie`, `scilit-ontology-source`, `scilit-obsolete`,
  `scilit-grounding-state`; `scilit-bioentity plays alh-classification:classified-entity`.

- [ ] **Step 1: Add attributes + ontology-term entity to `schema.tql`** (place near the other scilit vocab/note types)

```tql
# --- Ontology grounding (Phase 1) ---
attribute scilit-curie, value string;            # e.g. "GO:0006325"
attribute scilit-ontology-source, value string;  # e.g. "GO","CL","CHEBI","HP","UBERON","MONDO","HGNC","UniProt"
attribute scilit-obsolete, value boolean;
attribute scilit-grounding-state, value string;  # grounded | needs-review | ungrounded

# A canonical external ontology concept = a controlled-vocabulary term with a CURIE.
entity scilit-ontology-term sub alh-vocabulary-type,
    owns scilit-curie,
    owns scilit-ontology-source,
    owns scilit-obsolete,
    plays alh-classification:type-facet,
    plays alh-type-hierarchy:subtype,
    plays alh-type-hierarchy:supertype;
```

- [ ] **Step 2: Let bioentity be grounded + carry grounding state.** Find the `entity scilit-bioentity` block
  and add the plays/owns (keep existing lines):

```tql
entity scilit-bioentity sub alh-domain-thing,
    owns scilit-grounding-state,
    plays alh-classification:classified-entity;
```

- [ ] **Step 3: Back up, then reload schema to verify it parses**

Run (from the alhazen repo root `/Users/gullyburns/skillful-alhazen`):
```bash
make db-export
TYPEDB_DATABASE=alhazen_notebook uv run python - <<'PY'
from typedb.driver import TypeDB, Credentials, DriverOptions, TransactionType
d=TypeDB.driver("localhost:1729",Credentials("admin","password"),DriverOptions())
schema=open(".claude/skills/scientific-literature/schema.tql").read()
with d.transaction("alhazen_notebook",TransactionType.SCHEMA) as tx:
    tx.query(schema).resolve(); tx.commit()
print("schema OK")
PY
```
Expected: `schema OK` (no `[DEX*]`/`[SYR*]` errors).

- [ ] **Step 4: Commit**
```bash
git add schema.tql && git commit -m "feat(scilit): schema for ontology grounding (scilit-ontology-term + grounding attrs)"
```

---

### Task 2: Grounding policy file + loader

**Files:**
- Create: `grounding_policy.yaml`
- Create: `grounding_policy.py`
- Test: `tests/test_grounding_policy.py`

**Interfaces:**
- Produces: `load_policy(path=None) -> dict` with keys `policy_version:str`, `confidence_threshold:float`,
  `kinds: {kind: {ontologies:[str], branch:str}}`, `trusted_sources:[str]`.

- [ ] **Step 1: Write `grounding_policy.yaml`**
```yaml
policy_version: "v1"
confidence_threshold: 0.5
granularity: prefer-highest-unambiguous
trusted_sources: [GO, CL, CHEBI, HP, UBERON, MONDO, HGNC, UniProt]
kinds:
  gene:      { ontologies: [HGNC, UniProt], branch: molecular }
  protein:   { ontologies: [UniProt, HGNC], branch: molecular }
  process:   { ontologies: [GO],     branch: biological_process }
  cell_type: { ontologies: [CL],     branch: cell }
  anatomy:   { ontologies: [UBERON], branch: anatomy }
  chemical:  { ontologies: [CHEBI],  branch: chemical }
  phenotype: { ontologies: [HP],     branch: phenotype }
  disease:   { ontologies: [MONDO],  branch: disease }
```

- [ ] **Step 2: Write the failing test** `tests/test_grounding_policy.py`
```python
from grounding_policy import load_policy

def test_load_policy_defaults():
    p = load_policy()
    assert p["policy_version"] == "v1"
    assert p["confidence_threshold"] == 0.5
    assert "GO" in p["trusted_sources"]
    assert p["kinds"]["process"]["ontologies"] == ["GO"]
    assert p["kinds"]["gene"]["ontologies"][0] == "HGNC"
```

- [ ] **Step 3: Run — verify it fails**
`uv run --with pytest --with pyyaml python -m pytest tests/test_grounding_policy.py -q` → FAIL (no module).

- [ ] **Step 4: Implement `grounding_policy.py`**
```python
"""Load the versioned ontology-grounding policy (trusted sources, per-kind priority, thresholds)."""
import os
import yaml

_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grounding_policy.yaml")

def load_policy(path=None):
    with open(path or _DEFAULT, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
```

- [ ] **Step 5: Run — verify it passes**, then **commit**
```bash
uv run --with pytest --with pyyaml python -m pytest tests/test_grounding_policy.py -q   # PASS
git add grounding_policy.yaml grounding_policy.py tests/test_grounding_policy.py
git commit -m "feat(scilit): versioned ontology grounding policy + loader"
```

---

### Task 3: CURIE normalization + deterministic bioentity identity

**Files:**
- Create: `bioentity_identity.py`
- Test: `tests/test_bioentity_identity.py`

**Interfaces:**
- Produces: `normalize_curie(s) -> str` (canonical `PREFIX:LOCALID`); `bioentity_identity(meta) -> (id, basis_tier, basis_value)`
  where `meta = {curie?, name?}`, tier `curie`→id from CURIE, else `name`→id from normalized name.
  Id format `scilit-bioentity-<12hex>` (mirrors `paper_identity`).

- [ ] **Step 1: Write the failing test** `tests/test_bioentity_identity.py`
```python
from bioentity_identity import normalize_curie, bioentity_identity

def test_normalize_curie_prefix_case_and_iri():
    assert normalize_curie("go:0006325") == "GO:0006325"
    assert normalize_curie("http://purl.obolibrary.org/obo/GO_0006325") == "GO:0006325"
    assert normalize_curie("CHEBI:26523") == "CHEBI:26523"

def test_identity_curie_tier_is_deterministic():
    a = bioentity_identity({"curie": "GO:0006325", "name": "chromatin organization"})
    b = bioentity_identity({"curie": "go:0006325"})        # same concept, different casing
    assert a[0] == b[0]
    assert a[1] == "curie" and a[2] == "GO:0006325"
    assert a[0].startswith("scilit-bioentity-") and len(a[0]) == len("scilit-bioentity-") + 12

def test_identity_name_fallback_when_ungrounded():
    i = bioentity_identity({"name": "ROS"})
    assert i[1] == "name" and i[2] == "ros"
    assert i[0] == bioentity_identity({"name": " R O S "})[0]  # normalized name collapses
```

- [ ] **Step 2: Run — verify it fails**
`uv run --with pytest python -m pytest tests/test_bioentity_identity.py -q` → FAIL.

- [ ] **Step 3: Implement `bioentity_identity.py`** (mirror `paper_identity.py`)
```python
"""Deterministic identity for scilit-bioentity: CURIE when grounded, normalized-name fallback."""
import hashlib, re

_OBO_IRI = re.compile(r".*/obo/([A-Za-z]+)_(\d+)$")

def normalize_curie(s):
    if not s:
        return ""
    s = str(s).strip()
    m = _OBO_IRI.match(s)
    if m:
        return f"{m.group(1).upper()}:{m.group(2)}"
    if ":" in s:
        pfx, local = s.split(":", 1)
        return f"{pfx.strip().upper()}:{local.strip()}"
    return s.upper()

def _norm_name(n):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (n or "").lower())).strip()

def bioentity_identity(meta):
    """meta: {curie?, name?} -> (id, basis_tier, basis_value)."""
    curie = normalize_curie(meta.get("curie"))
    if curie:
        tier, value = "curie", curie
    else:
        tier, value = "name", _norm_name(meta.get("name"))
    bid = "scilit-bioentity-" + hashlib.sha256(f"{tier}:{value}".encode("utf-8")).hexdigest()[:12]
    return bid, tier, value
```

- [ ] **Step 4: Run — verify it passes**, then **commit**
```bash
uv run --with pytest python -m pytest tests/test_bioentity_identity.py -q   # PASS
git add bioentity_identity.py tests/test_bioentity_identity.py
git commit -m "feat(scilit): deterministic CURIE-based bioentity identity"
```

---

### Task 4: QC gate (the 6 noise checks)

**Files:**
- Create: `ontology_grounding.py` (decision-logic portion only this task)
- Test: `tests/test_ontology_grounding.py`

**Interfaces:**
- Consumes: `load_policy` (Task 2), `normalize_curie` (Task 3).
- Produces: `qc_check(candidate, kind, policy) -> (state, reason)` where `state ∈ {"grounded","needs-review"}`,
  `candidate = {curie, label, source, match_type, obsolete, confidence, ambiguous}`.
  `match_type ∈ {"exact","synonym","fuzzy"}`.

- [ ] **Step 1: Write the failing test** `tests/test_ontology_grounding.py`
```python
from grounding_policy import load_policy
from ontology_grounding import qc_check
P = load_policy()

def _cand(**kw):
    base = dict(curie="GO:0006325", label="chromatin organization", source="GO",
                match_type="exact", obsolete=False, confidence=0.9, ambiguous=False)
    base.update(kw); return base

def test_accepts_clean_exact_match():
    assert qc_check(_cand(), "process", P)[0] == "grounded"

def test_rejects_obsolete():
    assert qc_check(_cand(obsolete=True), "process", P)[0] == "needs-review"

def test_rejects_untrusted_source():
    assert qc_check(_cand(source="WIKIDATA"), "process", P)[0] == "needs-review"

def test_rejects_cross_branch():               # a gene must not ground to a GO source
    assert qc_check(_cand(source="GO"), "gene", P)[0] == "needs-review"

def test_rejects_low_confidence_fuzzy():
    assert qc_check(_cand(match_type="fuzzy", confidence=0.3), "process", P)[0] == "needs-review"

def test_ambiguity_guard():
    assert qc_check(_cand(ambiguous=True), "process", P)[0] == "needs-review"
```

- [ ] **Step 2: Run — verify it fails**
`uv run --with pytest --with pyyaml python -m pytest tests/test_ontology_grounding.py -q` → FAIL.

- [ ] **Step 3: Implement `qc_check` in `ontology_grounding.py`**
```python
"""Ontology grounding: QC gate (pure) + OLS client + orchestration (added in later tasks)."""
from bioentity_identity import normalize_curie

def qc_check(candidate, kind, policy):
    """Return (state, reason): 'grounded' iff all 6 checks pass, else 'needs-review'."""
    kindcfg = policy["kinds"].get(kind)
    if not kindcfg:
        return "needs-review", f"unknown kind {kind!r}"
    src = candidate.get("source")
    # 1. trusted source
    if src not in policy["trusted_sources"]:
        return "needs-review", f"source {src} not trusted"
    # 2. branch / kind match (the kind's allowed ontologies)
    if src not in kindcfg["ontologies"]:
        return "needs-review", f"source {src} not allowed for kind {kind}"
    # 3. not obsolete
    if candidate.get("obsolete"):
        return "needs-review", "obsolete term"
    # 4. CURIE resolves (well-formed PREFIX:LOCAL)
    curie = normalize_curie(candidate.get("curie"))
    if ":" not in curie or not curie.split(":", 1)[1]:
        return "needs-review", "unresolved CURIE"
    # 5. match quality (exact/synonym OR fuzzy above threshold)
    mt = candidate.get("match_type")
    if mt == "fuzzy" and float(candidate.get("confidence", 0)) < policy["confidence_threshold"]:
        return "needs-review", "fuzzy match below threshold"
    # 6. ambiguity guard
    if candidate.get("ambiguous"):
        return "needs-review", "ambiguous match"
    return "grounded", "ok"
```

- [ ] **Step 4: Run — verify it passes**, then **commit**
```bash
uv run --with pytest --with pyyaml python -m pytest tests/test_ontology_grounding.py -q   # PASS
git add ontology_grounding.py tests/test_ontology_grounding.py
git commit -m "feat(scilit): ontology grounding QC gate (6 checks)"
```

---

### Task 5: OLS4 client + term cache + ground_term orchestration

**Files:**
- Modify: `ontology_grounding.py` (add `ols_search`, `ols_ancestors`, `ground_term`)
- Test: `tests/test_ontology_grounding.py` (add an orchestration test with a stubbed search fn)

**Interfaces:**
- Consumes: `qc_check` (Task 4), `load_policy`, `normalize_curie`.
- Produces: `ground_term(mention, kind, policy, search=ols_search) -> dict`
  `{curie, iri, label, source, ancestors:[curie], confidence, state, reason}` (state `grounded|needs-review`;
  caller treats no-candidate as `ungrounded`). `ols_search(mention, ontologies) -> [candidate]`.

- [ ] **Step 1: Write the failing orchestration test** (inject a fake `search` — no network)
```python
from ontology_grounding import ground_term
from grounding_policy import load_policy
P = load_policy()

def _fake_search(mention, ontologies):
    return [dict(curie="GO:0006325", iri="http://purl.obolibrary.org/obo/GO_0006325",
                 label="chromatin organization", source="GO", match_type="exact",
                 obsolete=False, confidence=0.95, ambiguous=False, ancestors=["GO:0016043"])]

def test_ground_term_uses_policy_priority_and_qc():
    g = ground_term("chromatin organization", "process", P, search=_fake_search)
    assert g["curie"] == "GO:0006325" and g["state"] == "grounded"
    assert g["source"] == "GO" and "GO:0016043" in g["ancestors"]

def test_ground_term_no_candidate_is_unresolved():
    g = ground_term("zxqq", "process", P, search=lambda m, o: [])
    assert g["state"] == "ungrounded"
```

- [ ] **Step 2: Run — verify it fails** (functions not defined).

- [ ] **Step 3: Implement the client + orchestration** (append to `ontology_grounding.py`)
```python
import json, os, time
from pathlib import Path
import requests

OLS4 = "https://www.ebi.ac.uk/ols4/api"
HEADERS = {"User-Agent": "skillful-alhazen/0.1 (mailto:alhazen@example.com)"}
_CACHE = Path.home() / ".alhazen" / "cache" / "ontology"

def _ont_param(ontologies):
    # OLS ontology ids are lowercase (go, cl, chebi, hp, uberon, mondo); HGNC/UniProt handled by caller fallback
    return ",".join(o.lower() for o in ontologies if o in ("GO", "CL", "CHEBI", "HP", "UBERON", "MONDO"))

def ols_search(mention, ontologies):
    """Query OLS4 search; return normalized candidate dicts (best first)."""
    params = {"q": mention, "ontology": _ont_param(ontologies), "rows": 5, "exact": "false"}
    resp = requests.get(f"{OLS4}/search", params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    docs = resp.json().get("response", {}).get("docs", [])
    out = []
    for d in docs:
        label = d.get("label", "")
        syns = [s.lower() for s in (d.get("synonym") or [])]
        ml = mention.lower()
        match_type = "exact" if label.lower() == ml else ("synonym" if ml in syns else "fuzzy")
        out.append(dict(
            curie=d.get("obo_id") or d.get("short_form", "").replace("_", ":"),
            iri=d.get("iri", ""), label=label,
            source=(d.get("ontology_name") or "").upper(),
            match_type=match_type, obsolete=bool(d.get("is_obsolete")),
            confidence=1.0 if match_type != "fuzzy" else 0.4,
            ambiguous=False, ancestors=[],
        ))
    # ambiguity guard: >1 distinct high-quality source for the same mention
    nonfuzzy = {c["source"] for c in out if c["match_type"] in ("exact", "synonym")}
    if len(nonfuzzy) > 1:
        for c in out:
            c["ambiguous"] = True
    time.sleep(0.2)
    return out

def ground_term(mention, kind, policy, search=ols_search):
    """Resolve a mention to a canonical term under the policy. Returns a grounding dict."""
    kindcfg = policy["kinds"].get(kind, {})
    candidates = search(mention, kindcfg.get("ontologies", [])) or []
    if not candidates:
        return {"state": "ungrounded", "reason": "no candidate", "curie": "", "label": mention,
                "source": "", "iri": "", "ancestors": [], "confidence": 0.0}
    best = candidates[0]
    state, reason = qc_check(best, kind, policy)
    return {"state": state, "reason": reason, "curie": normalize_curie(best["curie"]),
            "iri": best.get("iri", ""), "label": best.get("label", mention),
            "source": best.get("source", ""), "ancestors": best.get("ancestors", []),
            "confidence": best.get("confidence", 0.0)}
```

- [ ] **Step 4: Run the stubbed tests — verify they pass.** (Network not exercised; `ols_search` covered live in
  Task 9 verification.)

- [ ] **Step 5: Commit**
```bash
git add ontology_grounding.py tests/test_ontology_grounding.py
git commit -m "feat(scilit): OLS4 client + ground_term orchestration"
```

---

### Task 6: kqed helpers — upsert_bioentity + persist_grounding

**Files:**
- Modify: `kqed.py` (add `upsert_bioentity`, `persist_grounding`, `upsert_ontology_term`)
- Test: `tests/test_kqed_grounding.py` (DB-backed; guarded to run only when TypeDB reachable)

**Interfaces:**
- Consumes: `bioentity_identity` (Task 3); `add_vocab`/`classify` (existing kqed). 
- Produces: `upsert_ontology_term(driver, grounding) -> term_id` (creates a `scilit-ontology-term` from a
  `ground_term` dict, idempotent on CURIE); `upsert_bioentity(driver, meta) -> bid` (CURIE-keyed, mirrors
  `upsert_paper`); `persist_grounding(driver, bid, grounding) -> None` (classify bioentity→term + set
  `scilit-grounding-state`).

- [ ] **Step 1: Write a DB-guarded test** `tests/test_kqed_grounding.py`
```python
import os, pytest
pytest.importorskip("typedb.driver")
import kqed as K

def _driver():
    try:
        d = K.get_driver(); return d
    except Exception:
        pytest.skip("TypeDB not reachable")

def test_upsert_bioentity_curie_is_idempotent():
    d = _driver()
    try:
        meta = {"curie": "GO:0006325", "name": "chromatin organization"}
        a = K.upsert_bioentity(d, meta); b = K.upsert_bioentity(d, {"curie": "go:0006325"})
        assert a == b and a.startswith("scilit-bioentity-")
    finally:
        d.close()
```

- [ ] **Step 2: Run — verify it fails** (`upsert_bioentity` missing):
`TYPEDB_DATABASE=alhazen_notebook uv run --with pytest python -m pytest tests/test_kqed_grounding.py -q`

- [ ] **Step 3: Implement in `kqed.py`** (mirror `upsert_paper`; import the identity helper at top)
```python
from bioentity_identity import bioentity_identity, normalize_curie

def upsert_ontology_term(driver, g):
    """g: a ground_term() dict with curie/label/source/iri. Idempotent on CURIE."""
    curie = normalize_curie(g["curie"])
    hit = r(driver, f'match $t isa scilit-ontology-term, has scilit-curie "{escape_string(curie)}"; fetch {{"id": $t.id}};')
    if hit:
        return hit[0]["id"]
    tid = generate_id("scterm"); ts = get_timestamp()
    q = (f'insert $t isa scilit-ontology-term, has id "{tid}", '
         f'has name "{escape_string(g.get("label") or curie)}", has description "{escape_string(g.get("label") or curie)}", '
         f'has scilit-curie "{escape_string(curie)}", has scilit-ontology-source "{escape_string(g.get("source",""))}", '
         f'has scilit-obsolete false, has created-at {ts}')
    if g.get("iri"):
        q += f', has iri "{escape_string(g["iri"])}"'
    w(driver, q + ";")
    return tid

def upsert_bioentity(driver, meta):
    """Find-or-create a scilit-bioentity by deterministic identity (CURIE, else name). Returns id."""
    bid, tier, value = bioentity_identity(meta)
    if not _exists(driver, bid):
        ts = get_timestamp()
        attrs = [f'has id "{bid}"', f'has created-at {ts}']
        if meta.get("name"):
            attrs.append(f'has name "{escape_string(meta["name"])}"')
        w(driver, f'insert $b isa scilit-bioentity, {", ".join(attrs)};')
    elif meta.get("name") and not _has(driver, f'$b isa scilit-bioentity, has id "{bid}", has name $n;'):
        w(driver, f'match $b isa scilit-bioentity, has id "{bid}"; insert $b has name "{escape_string(meta["name"])}";')
    return bid

def persist_grounding(driver, bid, g):
    """Classify a bioentity to its ontology term and stamp grounding-state."""
    state = g.get("state", "ungrounded")
    # set/refresh grounding-state
    if _has(driver, f'$b isa scilit-bioentity, has id "{escape_string(bid)}", has scilit-grounding-state $s;'):
        w(driver, f'match $b isa scilit-bioentity, has id "{escape_string(bid)}", has scilit-grounding-state $s; delete has $s of $b;')
    w(driver, f'match $b isa scilit-bioentity, has id "{escape_string(bid)}"; insert $b has scilit-grounding-state "{escape_string(state)}";')
    if state == "grounded" and g.get("curie"):
        tid = upsert_ontology_term(driver, g)
        classify(driver, bid, tid, provenance=f'OLS/{g.get("source","")} ({g.get("reason","")})',
                 confidence=g.get("confidence"))
```

- [ ] **Step 4: Run the test — verify it passes** (commits the tx inside helpers via `w`/`r` which use their own
  transactions per existing kqed convention). If `get_driver` autocommits per-call, confirm idempotency holds.

- [ ] **Step 5: Commit**
```bash
git add kqed.py tests/test_kqed_grounding.py
git commit -m "feat(scilit): upsert_bioentity (CURIE identity) + persist_grounding"
```

---

### Task 7: CLI verbs — ground-entity, ground-corpus, list-ungrounded

**Files:**
- Modify: `scientific_literature.py` (argparse subparsers + dispatch + `cmd_ground_entity`,
  `cmd_ground_corpus`, `cmd_list_ungrounded`)

**Interfaces:**
- Consumes: `kqed.upsert_bioentity/persist_grounding`, `ontology_grounding.ground_term`, `grounding_policy.load_policy`.
- Produces: CLI `ground-entity --id <bid> [--mention M --kind K]`, `ground-corpus --investigation <id>`,
  `list-ungrounded` (JSON list of `{id, name}`).

- [ ] **Step 1: Add subparsers** (in `main()` near other `add_parser` calls)
```python
    p = subparsers.add_parser("ground-entity", help="Ground one bioentity to an ontology term via OLS")
    p.add_argument("--id", required=True); p.add_argument("--mention"); p.add_argument("--kind", default="process")
    p = subparsers.add_parser("ground-corpus", help="Ground all bioentities used in an investigation")
    p.add_argument("--investigation", required=True); p.add_argument("--kind", default="process")
    p = subparsers.add_parser("list-ungrounded", help="List bioentities not yet grounded")
```
and in the dispatch dict:
```python
        "ground-entity": cmd_ground_entity,
        "ground-corpus": cmd_ground_corpus,
        "list-ungrounded": cmd_list_ungrounded,
```

- [ ] **Step 2: Implement the commands** (follow the `cmd_add_claim` shape; import at top:
  `import kqed as K`, `from ontology_grounding import ground_term`, `from grounding_policy import load_policy`)
```python
def cmd_ground_entity(args):
    policy = load_policy()
    with get_driver() as d:
        name = args.mention
        if not name:
            hit = K.r(d, f'match $b isa scilit-bioentity, has id "{escape_string(args.id)}", has name $n; fetch {{"n": $n}};')
            name = hit[0]["n"] if hit else args.id
        g = ground_term(name, args.kind, policy)
        K.persist_grounding(d, args.id, g)
    print(json.dumps({"success": True, "id": args.id, "mention": name,
                      "curie": g.get("curie"), "state": g["state"], "reason": g.get("reason")}, indent=2))

def cmd_ground_corpus(args):
    policy = load_policy()
    grounded = needs = ung = 0
    with get_driver() as d:
        rows = K.r(d, f'match $inv isa scilit-investigation, has id "{escape_string(args.investigation)}"; '
                      f'$ml isa scilit-mechanistic-link, links (mech-source: $b); $b isa scilit-bioentity, has id $bid, has name $n; '
                      f'fetch {{"bid": $bid, "n": $n}};')
        seen = {}
        for row in rows:
            seen[row["bid"]] = row["n"]
        for bid, name in seen.items():
            g = ground_term(name, args.kind, policy); K.persist_grounding(d, bid, g)
            grounded += g["state"] == "grounded"; needs += g["state"] == "needs-review"; ung += g["state"] == "ungrounded"
    print(json.dumps({"success": True, "grounded": grounded, "needs_review": needs, "ungrounded": ung}, indent=2))

def cmd_list_ungrounded(args):
    with get_driver() as d:
        rows = K.r(d, 'match $b isa scilit-bioentity, has id $bid, has name $n; '
                      'not { $b has scilit-grounding-state "grounded"; }; fetch {"id": $bid, "name": $n};')
    print(json.dumps({"success": True, "count": len(rows), "ungrounded": rows}, indent=2))
```

- [ ] **Step 3: Smoke test each verb**
```bash
uv run python scientific_literature.py list-ungrounded | head
# pick a bioentity id from the KG and:
uv run python scientific_literature.py ground-entity --id <scilit-bioentity-...> --mention "chromatin organization" --kind process
```
Expected: `state` one of `grounded|needs-review|ungrounded`; ground-entity returns a CURIE when grounded.

- [ ] **Step 4: Commit**
```bash
git add scientific_literature.py && git commit -m "feat(scilit): ground-entity/ground-corpus/list-ungrounded verbs"
```

---

### Task 8: Migration — ground + re-key the 758 bioentities

**Files:**
- Create: `prototypes/ground_bioentities.py`

**Interfaces:**
- Consumes: all of the above. Dry-run default; `--apply`. Re-keys grounded bioentities to CURIE identity via
  id `@key` swap (preserves `scilit-mechanistic-link`), merges name-dupes resolving to one CURIE, leaves
  ungrounded as-is.

- [ ] **Step 1: Write `prototypes/ground_bioentities.py`**
```python
"""Ground existing scilit-bioentities and re-key grounded ones to CURIE identity. Dry-run unless --apply."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import kqed as K
from kqed import escape_string
from bioentity_identity import bioentity_identity
from ontology_grounding import ground_term
from grounding_policy import load_policy

def main(apply=False, kind="process"):
    policy = load_policy(); d = K.get_driver()
    try:
        ents = K.r(d, 'match $b isa scilit-bioentity, has id $bid, has name $n; fetch {"bid": $bid, "n": $n};')
        grounded = needs = ung = rekeyed = merged = 0
        for e in ents:
            bid, name = e["bid"], e["n"]
            g = ground_term(name, kind, policy)
            grounded += g["state"] == "grounded"; needs += g["state"] == "needs-review"; ung += g["state"] == "ungrounded"
            if not apply:
                continue
            K.persist_grounding(d, bid, g)
            if g["state"] == "grounded":
                new_id, _, _ = bioentity_identity({"curie": g["curie"], "name": name})
                if new_id != bid:
                    if K._exists(d, new_id):           # merge: repoint mech-links, delete old
                        _merge_bioentity(d, bid, new_id); merged += 1
                    else:                              # re-key in place (preserves relations)
                        K.w(d, f'match $b isa scilit-bioentity, has id $o; $o == "{escape_string(bid)}"; '
                               f'delete has $o of $b; insert $b has id "{escape_string(new_id)}";')
                        rekeyed += 1
        print(f"grounded={grounded} needs-review={needs} ungrounded={ung} rekeyed={rekeyed} merged={merged} "
              f"({'APPLIED' if apply else 'DRY-RUN'})")
    finally:
        d.close()

def _merge_bioentity(d, old, new):
    for role in ("mech-source", "mech-target"):
        for e in K.r(d, f'match $ml isa scilit-mechanistic-link, links ({role}: $o); $o isa scilit-bioentity, has id "{escape_string(old)}"; '
                        f'$ml has id $mid; fetch {{"mid": $mid}};') or []:
            pass  # relations have no id; repoint via re-insert below
    # repoint by rebuilding links: match each mech-link touching old, recreate with new, delete old link
    K.w(d, f'match $o isa scilit-bioentity, has id "{escape_string(old)}"; '
           f'$n isa scilit-bioentity, has id "{escape_string(new)}"; '
           f'$ml isa scilit-mechanistic-link, links (mech-source: $o, mech-target: $t), has scilit-mech-type $mt; '
           f'insert $ml2 isa scilit-mechanistic-link (mech-source: $n, mech-target: $t), has scilit-mech-type $mt;')
    K.w(d, f'match $o isa scilit-bioentity, has id "{escape_string(old)}"; '
           f'$n isa scilit-bioentity, has id "{escape_string(new)}"; '
           f'$ml isa scilit-mechanistic-link, links (mech-target: $o, mech-source: $s), has scilit-mech-type $mt; '
           f'insert $ml2 isa scilit-mechanistic-link (mech-target: $n, mech-source: $s), has scilit-mech-type $mt;')
    K.w(d, f'match $o isa scilit-bioentity, has id "{escape_string(old)}"; $ml isa scilit-mechanistic-link, links (mech-source: $o); delete $ml;')
    K.w(d, f'match $o isa scilit-bioentity, has id "{escape_string(old)}"; $ml isa scilit-mechanistic-link, links (mech-target: $o); delete $ml;')
    K.w(d, f'match $o isa scilit-bioentity, has id "{escape_string(old)}"; delete $o;')

if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
```

- [ ] **Step 2: Back up + dry-run**
```bash
cd /Users/gullyburns/skillful-alhazen && make db-export
cd ~/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature
uv run python prototypes/ground_bioentities.py        # DRY-RUN, prints counts
```
Expected: a line `grounded=… needs-review=… ungrounded=… rekeyed=0 merged=0 (DRY-RUN)`.

- [ ] **Step 3: Apply + verify mech-links preserved**
```bash
uv run python prototypes/ground_bioentities.py --apply
uv run python scientific_literature.py list-ungrounded | python3 -c "import sys,json;print('ungrounded:',json.load(sys.stdin)['count'])"
```
Verify (read query): a known grounded entity (e.g. SIRT3) now has id `scilit-bioentity-<hash(curie)>` and its
mechanistic links still resolve; total `scilit-mechanistic-link` count unchanged vs the pre-apply count.

- [ ] **Step 4: Commit**
```bash
git add prototypes/ground_bioentities.py
git commit -m "feat(scilit): migrate 758 bioentities to CURIE identity + grounding state"
```

---

## Self-Review notes (carried into execution)
- Pure modules import-free of DB: `bioentity_identity`, `ontology_grounding` (qc_check/ground_term decision path).
- `ols_search` network path is exercised only in Task 8 apply (live); unit tests stub `search`.
- The `_merge_bioentity` recreate-then-delete must run before deleting the old entity; verify mech-link counts
  before/after on a backup. If merges are >0 and risky, run with `--apply` only after the dry-run shows the
  expected `rekeyed`/`merged` split.
- Verification (whole phase): `uv run --with pytest --with pyyaml python -m pytest tests/ -q` green; live
  grounding of SIRT3/SOD2→PR or HGNC, ROS→CHEBI:26523, HSC→CL:0000037 (some may land `needs-review` — acceptable).
