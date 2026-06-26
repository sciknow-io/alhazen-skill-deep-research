#!/usr/bin/env python3
"""
Persist the rhetorical (Teufel CFC) analysis of the Hallmarks-2023 review:
  - one scilit-claim (type "citing") per extracted citing claim, threaded under
    the review investigation, carrying its CFC;
  - a paper-level scilit-hinge[CFC] from each citing claim to every reference it
    cites (resolved via the citation-target registry's scilit-reference-key);
  - scilit-citation-load on each target = number of citing claims that cite it.

Input: /tmp/hm_claims.json  (list of {statement, refs:[int], cfc})
Run:   uv run python prototypes/persist_review_claims.py
"""
import os, sys, json, re
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kqed as K
from kqed import escape_string, get_timestamp

REVIEW_PAPER = "scilit-paper-21632e9ffb04"
REVIEW_INV   = "scinv-3e0aa419866c"
CLAIMS_JSON  = "/tmp/hm_claims.json"


def build_ref_map(d):
    """refnum (int) -> scilit-paper id, from registry reference-keys for this review."""
    rows = K.r(d, 'match $p isa scilit-paper, has scilit-reference-key $k; '
                  f'$k contains "{REVIEW_PAPER}:"; fetch {{"id": $p.id, "k": $k}};')
    m = {}
    for r in rows:
        mm = re.search(rf"{re.escape(REVIEW_PAPER)}:(\d+)", str(r["k"]))
        if mm:
            m[int(mm.group(1))] = r["id"]
    return m


def set_load(d, pid, n):
    if K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-citation-load $v;'):
        K.w(d, f'match $p isa scilit-paper, has id "{pid}", has scilit-citation-load $v; delete has $v of $p;')
    K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-citation-load {n};')


def main():
    claims = json.load(open(CLAIMS_JSON))
    d = K.get_driver()
    try:
        refmap = build_ref_map(d)
        load = Counter()
        made_claims = 0
        made_hinges = 0
        missing_refs = set()
        for i, c in enumerate(claims):
            cid = f"scclaim-hmref-{i:03d}"
            stmt = c["statement"].strip()
            cfc = c.get("cfc", "Neut")
            if not K._exists(d, cid):
                ts = get_timestamp()
                K.w(d, f'match $inv isa scilit-investigation, has id "{REVIEW_INV}"; '
                       f'insert $c isa scilit-claim, has id "{cid}", '
                       f'has name "{escape_string(stmt[:60])}", has scilit-claim-type "citing", '
                       f'has scilit-claim-statement "{escape_string(stmt)}", has created-at {ts}; '
                       f'(parent-note: $inv, child-note: $c) isa alh-note-threading;')
                made_claims += 1
            for refnum in c.get("refs", []):
                pid = refmap.get(refnum)
                if not pid:
                    missing_refs.add(refnum)
                    continue
                before = K._has(d, f'$c isa scilit-claim, has id "{cid}"; $t isa scilit-paper, has id "{pid}"; '
                                   f'(hinging-claim: $c, hinged-to: $t) isa scilit-hinge;')
                K.add_hinge(d, cid, pid, cfc, target_kind="scilit-paper")
                if not before:
                    made_hinges += 1
                load[pid] += 1
        # citation-load
        for pid, n in load.items():
            set_load(d, pid, n)
        print(json.dumps({
            "claims_created": made_claims,
            "hinges_created": made_hinges,
            "papers_with_load": len(load),
            "max_load": max(load.values()) if load else 0,
            "unresolved_ref_numbers": sorted(missing_refs)[:20],
            "unresolved_count": len(missing_refs),
        }, indent=2))
    finally:
        d.close()


if __name__ == "__main__":
    main()
