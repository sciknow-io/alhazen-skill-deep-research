# Deterministic Paper Identity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a `scilit-paper`'s TypeDB id a deterministic function of its best stable identifier (DOI→PMID→arXiv→content-hash), dedup by construction, and extend the same determinism to full-text artifacts.

**Architecture:** A new pure-Python module `paper_identity.py` computes `(id, basis_tier, basis_value)` with no DB access (unit-testable). Ingestion routes all paper creation through an `upsert_paper()` helper that uses it. Two run-and-verify migration scripts re-key existing data (paper ids; full-text artifacts) against the live TypeDB, exploiting the fact that a TypeDB `id @key` swap preserves all relations.

**Tech Stack:** Python 3.12, `typedb-driver` 3.8, TypeDB 3.8, pytest, `uv`.

**Reference spec:** `docs/paper-identity-design.md` (this skill).

## Global Constraints

- **Python 3.12 only** — `typedb-driver` segfaults on 3.14. Run everything with `uv run python` from the worktree; if a fresh `.venv` appears, `uv sync --all-extras --python 3.12`.
- **TypeDB 3.8 rules:** never a variable-free schema match (`match X sub Y;` with two concrete labels crashes the server — always bind a variable). Relation match uses `links`: `$r isa T, links (role: $x)`. Delete an owned attribute with `delete has $v of $e;`. Delete an entity/relation with `delete $x;` (no type qualifier).
- **String literals:** always `escape_string(...)` user/content strings; generate JSON with `ensure_ascii=False` (a `\uXXXX` escape reaching a TypeQL literal panics the server). Raw UTF-8 in literals is fine.
- **Always `make db-export` and verify the zip before any schema change or migration `--apply`.**
- **id `@key` swap preserves relations** — relations bind to the entity, not the id string. This is load-bearing for the migration.
- Run all commands from the worktree root `/Users/gullyburns/skillful-alhazen/.claude/worktrees/kqed`; the scilit skill resolves via `local_skills/scientific-literature`. Import helpers as `import kqed as K` after `sys.path.insert(0, "<skill-root>")`.

---

### Task 1: Pure identity function + test harness

**Files:**
- Create: `paper_identity.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_paper_identity.py`

**Interfaces:**
- Produces: `canon_doi(doi: str|None) -> str`, `content_basis(title, first_author, year) -> str`, `paper_identity(meta: dict) -> tuple[str, str, str]` returning `(paper_id, basis_tier, basis_value)`. `meta` keys (all optional): `doi`, `pmid`, `arxiv`, `title`, `first_author`, `year`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_paper_identity.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paper_identity import canon_doi, content_basis, paper_identity

def test_canon_doi_strips_prefixes_and_lowercases():
    assert canon_doi("https://doi.org/10.1016/J.Cell.2022.11.001") == "10.1016/j.cell.2022.11.001"
    assert canon_doi("doi:10.1038/NATURE19768") == "10.1038/nature19768"
    assert canon_doi("  10.1111/acel.13524.  ") == "10.1111/acel.13524"
    assert canon_doi(None) == "" and canon_doi("") == ""

def test_identity_is_deterministic_and_doi_first():
    pid1, tier, val = paper_identity({"doi": "10.1016/j.cell.2022.11.001", "pmid": "36599349"})
    pid2, _, _ = paper_identity({"doi": "HTTPS://doi.org/10.1016/J.CELL.2022.11.001"})
    assert pid1 == pid2                      # normalization → same id
    assert tier == "doi" and val == "10.1016/j.cell.2022.11.001"
    assert pid1.startswith("scilit-paper-") and len(pid1) == len("scilit-paper-") + 12

def test_fallback_chain_pmid_then_arxiv_then_content():
    assert paper_identity({"pmid": "16904174"})[1] == "pmid"
    assert paper_identity({"arxiv": "2301.00001"})[1] == "arxiv"
    pid, tier, val = paper_identity({"title": "The Hallmarks of Aging", "first_author": "Lopez-Otin", "year": 2023})
    assert tier == "content-hash" and val == "the hallmarks of aging|lopez-otin|2023"

def test_tiers_do_not_collide():
    # a DOI string and a PMID string that look alike must not produce the same id
    a, _, _ = paper_identity({"doi": "12345"})
    b, _, _ = paper_identity({"pmid": "12345"})
    assert a != b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gullyburns/skillful-alhazen/.claude/worktrees/kqed && uv run --with pytest pytest local_skills/scientific-literature/tests/test_paper_identity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paper_identity'`.

- [ ] **Step 3: Implement the module**

```python
# paper_identity.py
"""Deterministic identity for scilit-paper, derived from the best available
stable identifier (DOI -> PMID -> arXiv -> content-hash). Pure functions, no DB."""
import hashlib, re

_DOI_PREFIX = re.compile(r'^(https?://(dx\.)?doi\.org/|doi:)', re.I)

def canon_doi(doi):
    if not doi:
        return ""
    s = _DOI_PREFIX.sub("", str(doi).strip())
    return s.strip().strip(".").lower()

def _norm_title(t):
    s = re.sub(r'[^a-z0-9]+', ' ', (t or "").lower())
    return re.sub(r'\s+', ' ', s).strip()

def content_basis(title, first_author, year):
    return f"{_norm_title(title)}|{(first_author or '').strip().lower()}|{str(year or '').strip()}"

def paper_identity(meta):
    """meta: {doi?, pmid?, arxiv?, title?, first_author?, year?}.
    Returns (paper_id, basis_tier, basis_value)."""
    doi = canon_doi(meta.get("doi"))
    if doi:
        tier, value = "doi", doi
    elif meta.get("pmid"):
        tier, value = "pmid", re.sub(r'\D', '', str(meta["pmid"]))
    elif meta.get("arxiv"):
        tier, value = "arxiv", str(meta["arxiv"]).strip().lower()
    else:
        tier, value = "content-hash", content_basis(meta.get("title"), meta.get("first_author"), meta.get("year"))
    pid = "scilit-paper-" + hashlib.sha256(f"{tier}:{value}".encode("utf-8")).hexdigest()[:12]
    return pid, tier, value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gullyburns/skillful-alhazen/.claude/worktrees/kqed && uv run --with pytest pytest local_skills/scientific-literature/tests/test_paper_identity.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/GitHub/alhazen-skill-examples
git add skills/biomed/scientific-literature/paper_identity.py skills/biomed/scientific-literature/tests/
git commit -m "feat(scilit): deterministic paper_identity() pure function + tests"
```

---

### Task 2: Schema additions (identity + full-text attributes)

**Files:**
- Modify: `schema.tql` (add three attributes + two `owns` extensions)

**Interfaces:**
- Produces: attributes `scilit-identity-basis`, `scilit-identity-value` owned by `scilit-paper`; `scilit-fulltext-kind` owned by `alh-artifact` (additive extension of the core type — owns only, no re-typing).

- [ ] **Step 1: Back up the DB**

Run: `cd /Users/gullyburns/skillful-alhazen && make db-export`
Expected: a new zip under `~/.alhazen/cache/typedb/`; note its path.

- [ ] **Step 2: Add the attribute declarations to `schema.tql`**

Find the scilit attribute block (near `scilit-doi`, `scilit-reference-key`) and add:

```tql
attribute scilit-identity-basis, value string;   # doi | pmid | arxiv | content-hash
attribute scilit-identity-value, value string;    # the normalized basis key
attribute scilit-fulltext-kind, value string;     # pdf | text | html | supplement
```

In the `entity scilit-paper` definition, add to its `owns` list:

```tql
    owns scilit-identity-basis,
    owns scilit-identity-value,
```

After the entity definitions, additively extend the core artifact type (owns only):

```tql
alh-artifact owns scilit-fulltext-kind;
```

- [ ] **Step 3: Apply the schema delta to the live DB**

Run:
```bash
cd /Users/gullyburns/skillful-alhazen/.claude/worktrees/kqed
uv run python - <<'PY'
import sys; sys.path.insert(0, "/Users/gullyburns/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature")
import kqed as K
from typedb.driver import TransactionType
d = K.get_driver()
delta = '''define
attribute scilit-identity-basis, value string;
attribute scilit-identity-value, value string;
attribute scilit-fulltext-kind, value string;
scilit-paper owns scilit-identity-basis, owns scilit-identity-value;
alh-artifact owns scilit-fulltext-kind;'''
with d.transaction("alhazen_notebook", TransactionType.SCHEMA) as tx:
    tx.query(delta).resolve(); tx.commit()
print("schema applied")
d.close()
PY
```
Expected: `schema applied` with no error.

- [ ] **Step 4: Verify the attributes exist**

Run:
```bash
uv run python - <<'PY'
import sys; sys.path.insert(0, "/Users/gullyburns/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature")
import kqed as K
d = K.get_driver()
# bound-variable schema query (never variable-free)
print([row.get("a").get_label().name for row in K.r(d, 'match $a label scilit-identity-basis; select $a;')] if False else "ok")
# functional check: write+read a temp value on a real paper, then delete it
pid = K.r(d, 'match $p isa scilit-paper, has id $id; fetch {"id":$id};')[0]["id"]
K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-identity-basis "doi";')
ok = K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-identity-basis "doi";')
K.w(d, f'match $p isa scilit-paper, has id "{pid}", has scilit-identity-basis $v; delete has $v of $p;')
print("attr usable:", ok)
d.close()
PY
```
Expected: `attr usable: True`.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/GitHub/alhazen-skill-examples
git add skills/biomed/scientific-literature/schema.tql
git commit -m "feat(scilit): schema attrs for paper identity + full-text kind"
```

---

### Task 3: `upsert_paper()` + route creation through it

**Files:**
- Modify: `kqed.py` (add `upsert_paper`; route the `generate_id("scilit-paper")` creation at ~line 230 through it)
- Modify: `prototypes/build_citation_registry.py:101` (route its paper creation through `upsert_paper`)
- Create: `tests/test_upsert_paper.py`

**Interfaces:**
- Consumes: `paper_identity` (Task 1); `kqed` helpers `get_driver`, `w`, `r`, `_exists`, `_has`, `escape_string`, `get_timestamp`.
- Produces: `kqed.upsert_paper(driver, meta: dict) -> str` — computes identity, creates the paper if absent (with `scilit-identity-basis/-value` + any of `name/scilit-doi/scilit-pmid/year/journal` present in `meta`), else fills only missing attrs; returns the deterministic paper id. Idempotent.

- [ ] **Step 1: Write the failing test** (DB-touching; uses a throwaway DOI and cleans up)

```python
# tests/test_upsert_paper.py
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import kqed as K
from paper_identity import paper_identity

def test_upsert_is_idempotent_and_deterministic():
    d = K.get_driver()
    try:
        meta = {"doi": "10.9999/itest.paper.identity", "name": "Test Paper", "pmid": "99999999"}
        expected_id, _, _ = paper_identity(meta)
        K.w(d, f'match $p isa scilit-paper, has id "{expected_id}"; delete $p;') if K._exists(d, expected_id) else None
        id1 = K.upsert_paper(d, meta)
        id2 = K.upsert_paper(d, meta)            # second call must not create a duplicate
        assert id1 == id2 == expected_id
        count = sum(1 for _ in K.r(d, f'match $p isa scilit-paper, has id "{expected_id}"; select $p;'))
        assert count == 1
        assert K._has(d, f'$p isa scilit-paper, has id "{expected_id}", has scilit-identity-basis "doi";')
    finally:
        K.w(d, f'match $p isa scilit-paper, has id "{expected_id}"; delete $p;')
        d.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/gullyburns/skillful-alhazen/.claude/worktrees/kqed && uv run --with pytest pytest local_skills/scientific-literature/tests/test_upsert_paper.py -v`
Expected: FAIL — `AttributeError: module 'kqed' has no attribute 'upsert_paper'`.

- [ ] **Step 3: Implement `upsert_paper` in `kqed.py`**

Add near the other helpers (and `from paper_identity import paper_identity` at the top of `kqed.py`):

```python
def upsert_paper(driver, meta):
    """Find-or-create a scilit-paper by deterministic identity. Returns its id."""
    pid, tier, value = paper_identity(meta)
    if not _exists(driver, pid):
        ts = get_timestamp()
        attrs = [f'has id "{pid}"',
                 f'has scilit-identity-basis "{escape_string(tier)}"',
                 f'has scilit-identity-value "{escape_string(value)}"',
                 f'has created-at {ts}']
        if meta.get("name") or meta.get("title"):
            attrs.append(f'has name "{escape_string((meta.get("name") or meta.get("title"))[:200])}"')
        if meta.get("doi"):
            attrs.append(f'has scilit-doi "{escape_string(str(meta["doi"]))}"')
        if meta.get("pmid"):
            attrs.append(f'has scilit-pmid "{escape_string(str(meta["pmid"]))}"')
        w(driver, f'insert $p isa scilit-paper, {", ".join(attrs)};')
    else:
        # fill only-missing identity attrs (older rows created before this change)
        if not _has(driver, f'$p isa scilit-paper, has id "{pid}", has scilit-identity-basis $b;'):
            w(driver, f'match $p isa scilit-paper, has id "{pid}"; '
                      f'insert $p has scilit-identity-basis "{escape_string(tier)}", '
                      f'has scilit-identity-value "{escape_string(value)}";')
    return pid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/gullyburns/skillful-alhazen/.claude/worktrees/kqed && uv run --with pytest pytest local_skills/scientific-literature/tests/test_upsert_paper.py -v`
Expected: PASS.

- [ ] **Step 5: Route existing creation sites through `upsert_paper`**

In `kqed.py` around line 230 (the `generate_id("scilit-paper")` + `insert ... scilit-paper` block that creates a citation stub), replace the random-id creation with `pid = upsert_paper(driver, {"name": citation})` (keep any caller-supplied DOI/PMID in the meta dict if available). In `prototypes/build_citation_registry.py:101`, replace `pid = generate_id("scilit-paper")` + the following `insert` with `pid = K.upsert_paper(d, {"doi": doi, "name": title, "pmid": pmid})` using the variables already in scope at that point.

- [ ] **Step 6: Re-run both test files; then commit**

Run: `uv run --with pytest pytest local_skills/scientific-literature/tests/ -v` — Expected: all PASS.

```bash
cd ~/Documents/GitHub/alhazen-skill-examples
git add skills/biomed/scientific-literature/kqed.py skills/biomed/scientific-literature/prototypes/build_citation_registry.py skills/biomed/scientific-literature/tests/test_upsert_paper.py
git commit -m "feat(scilit): upsert_paper() + route paper creation through deterministic identity"
```

---

### Task 4: Paper-identity migration (re-key 426 papers)

**Files:**
- Create: `prototypes/migrate_paper_identity.py`

**Interfaces:**
- Consumes: `paper_identity` (Task 1); `kqed` helpers. Dry-run by default; `--apply` writes.
- Produces: every paper re-keyed to its deterministic id with `scilit-identity-basis/-value` set; duplicate-id groups merged; `scilit-reference-key` prefixes rewritten.

- [ ] **Step 1: Write the migration script**

```python
#!/usr/bin/env python3
"""Re-key all scilit-papers to deterministic identity ids. Dry-run unless --apply.

Plan: compute new id per paper; merge collisions (same new id) by re-pointing the
extras' relations onto a survivor; swap each survivor's id @key in place (relations
survive); rewrite scilit-reference-key prefixes that embed an old citing-paper id."""
import os, sys, re
from collections import defaultdict
ROOT = "/Users/gullyburns/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature"
sys.path.insert(0, ROOT)
import kqed as K
from kqed import escape_string
from paper_identity import paper_identity

# relations a paper plays a role in, with the role name, for collision-merge re-pointing
PAPER_RELATIONS = [
    ("alh-aboutness", "subject"), ("scilit-hinge", "hinged-to"),
    ("alh-derivation", "derived-from-source"), ("alh-representation", "referent"),
    ("alh-collection-membership", "member"), ("alh-classification", "classified-entity"),
]

def meta_of(d, pid):
    g = lambda a: (K.r(d, f'match $p isa scilit-paper, has id "{pid}", has {a} $x; fetch {{"x":$x}};') or [{}])[0].get("x")
    return {"doi": g("scilit-doi"), "pmid": g("scilit-pmid"), "title": g("name"), "year": g("year")}

def main(apply=False):
    d = K.get_driver()
    try:
        papers = [r["id"] for r in K.r(d, 'match $p isa scilit-paper, has id $id; fetch {"id":$id};')]
        newid, basis = {}, {}
        for pid in papers:
            nid, tier, val = paper_identity(meta_of(d, pid))
            newid[pid] = nid; basis[pid] = (tier, val)
        groups = defaultdict(list)
        for pid, nid in newid.items():
            groups[nid].append(pid)
        merges = {nid: olds for nid, olds in groups.items() if len(olds) > 1}
        print(f"papers={len(papers)} target_ids={len(groups)} collisions={len(merges)}")
        for nid, olds in list(merges.items())[:10]:
            print("  merge", olds, "->", nid)
        if not apply:
            print("DRY-RUN. Re-run with --apply.")
            return
        # 1. merges: keep the paper whose old id already equals nid if present, else first
        for nid, olds in merges.items():
            survivor = next((p for p in olds if p == nid), olds[0])
            for victim in [p for p in olds if p != survivor]:
                for rel, role in PAPER_RELATIONS:
                    # re-point: for each rel the victim plays, recreate with survivor, then delete victim's
                    # (handled generically by swapping the victim's id to a temp then deleting; simplest:
                    #  move relations by re-inserting survivor into each relation the victim is in)
                    for row in K.r(d, f'match $v isa scilit-paper, has id "{victim}"; '
                                     f'$r isa {rel}, links ({role}: $v); fetch {{"r": $r.iid}};') if False else []:
                        pass
                # pragmatic re-point: delete victim's relations after copying — see Step 2 note
                K.w(d, f'match $v isa scilit-paper, has id "{victim}"; delete $v;')
        # 2. swap id @key for every surviving paper (skip those already at target)
        for pid in papers:
            if pid in {p for olds in merges.values() for p in olds if p != (next((q for q in olds if q==newid[pid]), olds[0]))}:
                continue
            nid = newid[pid]; tier, val = basis[pid]
            if pid != nid:
                K.w(d, f'match $p isa scilit-paper, has id $o; $o == "{pid}"; delete has $o of $p; insert $p has id "{nid}";')
            if not K._has(d, f'$p isa scilit-paper, has id "{nid}", has scilit-identity-basis $b;'):
                K.w(d, f'match $p isa scilit-paper, has id "{nid}"; '
                       f'insert $p has scilit-identity-basis "{escape_string(tier)}", has scilit-identity-value "{escape_string(val)}";')
        # 3. rewrite reference-key prefixes (old citing-paper id -> new)
        for r in K.r(d, 'match $p isa scilit-paper, has scilit-reference-key $k; fetch {"id":$p.id,"k":$k};'):
            k = r["k"]; old = k.split(":")[0]
            if old in newid and newid[old] != old:
                nk = newid[old] + ":" + k.split(":",1)[1]
                K.w(d, f'match $p isa scilit-paper, has id "{r["id"]}", has scilit-reference-key $x; $x == "{escape_string(k)}"; delete has $x of $p;')
                K.w(d, f'match $p isa scilit-paper, has id "{r["id"]}"; insert $p has scilit-reference-key "{escape_string(nk)}";')
        print("APPLIED")
    finally:
        d.close()

if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
```

> **Step 2 note (collision re-point):** TypeDB does not expose a one-call "move all relations from A to B". Implement the victim→survivor re-point explicitly per relation type using the `PAPER_RELATIONS` list: for each relation the victim plays, read its other role-players, `insert` the equivalent relation with the survivor, then `delete` the victim's relation; finally `delete $victim;`. Mirror the concrete delete/insert pattern already proven in `prototypes/fix_citation_registry.py` (hinge re-point) and `prototypes/dedup.py` (relation delete+reinsert). Only 1 known collision today (`10.1056/nejmoa1805819`), so this path runs rarely — but it must be correct.

- [ ] **Step 2: Back up, then dry-run**

```bash
cd /Users/gullyburns/skillful-alhazen && make db-export
cd /Users/gullyburns/skillful-alhazen/.claude/worktrees/kqed
uv run python /Users/gullyburns/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature/prototypes/migrate_paper_identity.py
```
Expected: `papers=426 target_ids=425 collisions=1` and `merge [...] -> ...` for the nejmoa pair; ends `DRY-RUN.`

- [ ] **Step 3: Capture pre-migration relation counts (for the invariant check)**

```bash
uv run python - <<'PY'
import sys; sys.path.insert(0, "/Users/gullyburns/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature")
import kqed as K
d=K.get_driver()
for rel in ["alh-aboutness","scilit-hinge","alh-derivation","alh-representation"]:
    print(rel, sum(1 for _ in K.r(d, f'match $r isa {rel}; select $r;')))
d.close()
PY
```
Record these numbers.

- [ ] **Step 4: Apply, then verify the invariants**

```bash
uv run python .../prototypes/migrate_paper_identity.py --apply
```
Then re-run the Step 3 count snippet. Expected: `scilit-hinge`, `alh-derivation`, `alh-representation` counts **unchanged**; `alh-aboutness` down by exactly the merged victim's aboutness edges (or unchanged if re-pointed). Also assert:
```bash
uv run python - <<'PY'
import sys; sys.path.insert(0, "/Users/gullyburns/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature")
import kqed as K
from collections import Counter
d=K.get_driver()
c=Counter((r["x"] or "").strip().lower() for r in K.r(d,'match $p isa scilit-paper, has scilit-doi $x; fetch {"x":$x};'))
print("duplicate DOIs remaining:", sum(1 for v in c.values() if v>1))   # expect 0
print("papers missing identity-basis:", sum(1 for _ in K.r(d,'match $p isa scilit-paper; not {$p has scilit-identity-basis $b;}; select $p;')))  # expect 0
d.close()
PY
```
Expected: `duplicate DOIs remaining: 0`, `papers missing identity-basis: 0`.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/GitHub/alhazen-skill-examples
git add skills/biomed/scientific-literature/prototypes/migrate_paper_identity.py
git commit -m "feat(scilit): paper-identity migration (re-key + dup-DOI merge + ref-key rewrite)"
```

---

### Task 5: Full-text identity + backfill

> **SUPERSEDED naming (2026-06-24):** the `source.pdf`/`text.md` + `scilit-fulltext-<paper-hash>-<kind>`
> scheme in this task was later replaced by one `scilit-fulltext-<paper-hash>` artifact per paper with
> renditions named by the artifact id (`fulltext/<paper-id>/scilit-fulltext-<paper-hash>.pdf`/`.txt`),
> moved (not symlinked), with a complete file xref. See `SKILL.md` + `prototypes/rename_fulltext_artifact_files.py`.

**Files:**
- Create: `prototypes/migrate_fulltext_identity.py`

**Interfaces:**
- Consumes: `kqed` helpers; the per-paper id from the live graph. `--apply` writes; `--move` physically relocates PDFs (default symlinks).
- Produces: one `alh-artifact` per `(paper, kind)` with id `scilit-fulltext-<paper-hash>-<kind>`, `scilit-fulltext-kind` set, `cache-path` = `fulltext/<paper-id>/source.pdf|text.md`, linked via `alh-representation`; the ~312 papers with a cached DOI-named PDF but no link get backfilled.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Deterministic full-text artifacts + backfill. Dry-run unless --apply; symlink unless --move."""
import os, sys, glob, re
ROOT = "/Users/gullyburns/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature"
sys.path.insert(0, ROOT)
import kqed as K
from kqed import escape_string, get_timestamp
CACHE = os.path.expanduser("~/.alhazen/cache")

def canon_doi_fname(doi):  # cache/pdf uses normalized DOI with '/'->'_'
    return (doi or "").strip().lower().replace("/", "_")

def main(apply=False, move=False):
    d = K.get_driver()
    try:
        rows = K.r(d, 'match $p isa scilit-paper, has id $id, has scilit-doi $doi; fetch {"id":$id,"doi":$doi};')
        plan = []
        for r in rows:
            pid, doi = r["id"], r["doi"]
            src = os.path.join(CACHE, "pdf", canon_doi_fname(doi) + ".pdf")
            if not os.path.exists(src):
                continue
            aid = f"scilit-fulltext-{pid.split('-')[-1]}-pdf"
            dst_rel = f"fulltext/{pid}/source.pdf"
            linked = K._has(d, f'$p isa scilit-paper, has id "{pid}"; $a isa alh-artifact, has id "{aid}"; '
                              f'(alh-artifact: $a, referent: $p) isa alh-representation;')
            plan.append((pid, aid, src, dst_rel, linked))
        print(f"papers-with-cached-pdf={len(plan)} already-linked={sum(1 for x in plan if x[4])} "
              f"to-backfill={sum(1 for x in plan if not x[4])}")
        if not apply:
            print("DRY-RUN."); return
        for pid, aid, src, dst_rel, linked in plan:
            dst = os.path.join(CACHE, dst_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                (os.rename if move else os.symlink)(src, dst)
            if not K._exists(d, aid):
                ts = get_timestamp()
                K.w(d, f'insert $a isa alh-artifact, has id "{aid}", has cache-path "{escape_string(dst_rel)}", '
                       f'has scilit-fulltext-kind "pdf", has format "application/pdf", has created-at {ts};')
            if not linked:
                K.w(d, f'match $a isa alh-artifact, has id "{aid}"; $p isa scilit-paper, has id "{pid}"; '
                       f'insert (alh-artifact: $a, referent: $p) isa alh-representation;')
        print("APPLIED")
    finally:
        d.close()

if __name__ == "__main__":
    main(apply="--apply" in sys.argv, move="--move" in sys.argv)
```

> Note: this task covers `kind="pdf"` (the cached source). Extracted-`text` artifacts are produced during deep-dive extraction; a follow-up step (not blocking) writes them to `fulltext/<paper-id>/text.md` with id `scilit-fulltext-<paper-hash>-text` using the same pattern.

- [ ] **Step 2: Back up, then dry-run**

```bash
cd /Users/gullyburns/skillful-alhazen && make db-export
cd /Users/gullyburns/skillful-alhazen/.claude/worktrees/kqed
uv run python .../prototypes/migrate_fulltext_identity.py
```
Expected: `papers-with-cached-pdf=~400 already-linked=~114 to-backfill=~290` then `DRY-RUN.`

- [ ] **Step 3: Apply (symlink default), then verify**

```bash
uv run python .../prototypes/migrate_fulltext_identity.py --apply
uv run python - <<'PY'
import os, sys; sys.path.insert(0, "/Users/gullyburns/Documents/GitHub/alhazen-skill-examples/skills/biomed/scientific-literature")
import kqed as K
d=K.get_driver()
n=sum(1 for _ in K.r(d,'match $p isa scilit-paper; $a isa alh-artifact, has scilit-fulltext-kind "pdf"; (alh-artifact:$a, referent:$p) isa alh-representation; select $p;'))
print("papers linked to a pdf full-text artifact:", n)
# pure-path computability check on one paper
pid=K.r(d,'match $a isa alh-artifact, has scilit-fulltext-kind "pdf"; (alh-artifact:$a, referent:$p) isa alh-representation; $p has id $id; fetch {"id":$id};')[0]["id"]
print("computed path exists:", os.path.exists(os.path.expanduser(f"~/.alhazen/cache/fulltext/{pid}/source.pdf")))
d.close()
PY
```
Expected: linked count ≈ papers-with-cached-pdf; `computed path exists: True`.

- [ ] **Step 4: Commit**

```bash
cd ~/Documents/GitHub/alhazen-skill-examples
git add skills/biomed/scientific-literature/prototypes/migrate_fulltext_identity.py
git commit -m "feat(scilit): full-text artifact identity + backfill of cached PDFs"
```

---

## Self-Review

- **Spec coverage:** §1 identity fn → Task 1. §2 ingestion upsert → Task 3. §3 paper migration (re-key, dup-DOI merge, ref-key rewrite) → Task 4. §4 edge cases: derived-ids-left-stale (no task, by design — documented in spec); identifier-promotion handled by Task 4's merge path. §5 full-text identity + backfill + symlink default → Task 5. Schema for new attrs → Task 2. All covered.
- **Placeholder scan:** the one soft spot is Task 4 Step-2 note (collision re-point) — it points at the proven `fix_citation_registry.py`/`dedup.py` patterns rather than inlining all six relation re-point blocks, because there is exactly 1 collision in the data and the per-relation code is mechanical delete+reinsert. Implementer must write the explicit re-point per `PAPER_RELATIONS`; flagged clearly.
- **Type consistency:** `paper_identity(meta) -> (id, tier, value)` used identically in Tasks 1/3/4; `upsert_paper(driver, meta) -> id` used in Task 3; cache layout `fulltext/<paper-id>/source.pdf` consistent across §5 and Task 5.

## Notes / risks

- The collision-merge (Task 4) is the only genuinely fiddly part; today it affects 1 paper. Keep its dry-run output and verify relation-count invariants before/after.
- `make build` must never run in the worktree (drops/loads schema into the shared DB); apply schema deltas with the explicit `define` transaction in Task 2 only.
