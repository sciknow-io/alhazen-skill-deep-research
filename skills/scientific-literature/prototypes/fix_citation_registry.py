#!/usr/bin/env python3
"""
Fix the Hallmarks-2023 citation registry: build_citation_registry resolved each
in-text reference number N by Crossref's `bibNN` KEY, but the correct paper is at
Crossref ARRAY POSITION N (references are returned in citation order). Result: every
scilit-reference-key, paper-level scilit-hinge, and scilit-citation-load is misassigned.

This re-resolves number -> paper by array position and rebuilds the linkage:
  - reset each registry paper's scilit-reference-key to its correct position(s)
  - re-point every paper-level hinge from the wrong paper to the correct one
  - recompute scilit-citation-load
Dry-run by default; pass --apply to write.

Run: uv run python prototypes/fix_citation_registry.py [--apply]
"""
import os, sys, re, json, urllib.request
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kqed as K
from kqed import escape_string

REVIEW_PAPER = "scilit-paper-21632e9ffb04"
REVIEW_DOI = "10.1016/j.cell.2022.11.001"

def canon(doi):
    if not doi: return ""
    s = str(doi).strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    return s.strip()

def crossref_positions():
    url = f"https://api.crossref.org/works/{REVIEW_DOI}"
    req = urllib.request.Request(url, headers={"User-Agent":"alhazen-kqed/1.0 (mailto:gullyburns@gmail.com)"})
    refs = json.load(urllib.request.urlopen(req, timeout=30))["message"]["reference"]
    pos2doi = {}
    for i, r in enumerate(refs, 1):     # array position (1-based) = in-text number
        doi = canon(r.get("DOI"))
        if doi: pos2doi[i] = doi
    return pos2doi, len(refs)

def main(apply=False):
    d = K.get_driver()
    try:
        pos2doi, ntot = crossref_positions()
        # registry papers: id -> {doi, refkeys}
        papers = {}
        for r in K.r(d, 'match $p isa scilit-paper, has id $id, has scilit-doi $doi; fetch {"id": $id, "doi": $doi};'):
            papers.setdefault(r["id"], {})["doi"] = canon(r["doi"])
        for r in K.r(d, 'match $p isa scilit-paper, has id $id, has scilit-reference-key $k; '
                        f'$k contains "{REVIEW_PAPER}:"; fetch {{"id": $id, "k": $k}};'):
            papers.setdefault(r["id"], {}).setdefault("rk", []).append(r["k"])
        doi2paper = {v["doi"]: pid for pid, v in papers.items() if v.get("doi")}

        # correct map: in-text position N -> registry paper (by DOI)
        pos2paper = {n: doi2paper[doi] for n, doi in pos2doi.items() if doi in doi2paper}
        # current (buggy) map: a paper's reference-key number M = the in-text number of claims hinged to it
        paper2num = {}   # pid -> M (its current reference-key number)
        for pid, v in papers.items():
            for k in v.get("rk", []):
                m = re.search(rf"{re.escape(REVIEW_PAPER)}:(\d+)", k)
                if m: paper2num[pid] = int(m.group(1))

        # paper-level hinges from the BULK review citing-claims only (scclaim-hmref-*);
        # hand-authored KQED-prototype hinges (e.g. scilit-claim-hm-ref123) are left untouched
        # because they were not built via the in-text-number -> bibNN mechanism.
        hinges = []
        for r in K.r(d, 'match $h isa scilit-hinge, links (hinging-claim: $c, hinged-to: $p); '
                        '$c isa scilit-claim, has id $cid; $p isa scilit-paper, has id $pid; '
                        '$h has scilit-hinge-term-id $cfc; fetch {"c": $cid, "p": $pid, "cfc": $cfc};'):
            if str(r["c"]).startswith("scclaim-hmref-"):
                hinges.append((r["c"], r["p"], r["cfc"]))

        repoint, keep, drop = [], 0, []
        for cid, pid, cfc in hinges:
            M = paper2num.get(pid)              # claim's in-text number
            correct = pos2paper.get(M) if M else None
            if correct is None:
                drop.append((cid, pid, M)); continue
            if correct == pid: keep += 1
            else: repoint.append((cid, pid, correct, cfc, M))

        print(json.dumps({
            "crossref_refs": ntot,
            "positions_with_doi": len(pos2doi),
            "positions_resolved_to_registry_paper": len(pos2paper),
            "registry_papers_with_doi": len(doi2paper),
            "paper_level_hinges": len(hinges),
            "hinges_already_correct": keep,
            "hinges_to_REPOINT": len(repoint),
            "hinges_to_DROP (in-text num -> non-registry paper)": len(drop),
        }, indent=2))
        print("\n-- spot check (claim, OLD paper, -> NEW paper, in-text#) --")
        for cid, old, new, cfc, M in repoint[:8]:
            print(f"   {cid}: {old} -> {new}  (#{M}, {cfc})")

        if not apply:
            print("\nDRY-RUN. Re-run with --apply to write.")
            return

        # APPLY: re-point hinges, reset reference-keys, recompute loads
        # 1. re-point
        for cid, old, new, cfc, M in repoint:
            K.w(d, f'match $c isa scilit-claim, has id "{cid}"; $p isa scilit-paper, has id "{old}"; '
                   f'$h isa scilit-hinge, links (hinging-claim: $c, hinged-to: $p); delete $h;')
            K.add_hinge(d, cid, new, cfc, target_kind="scilit-paper")
        # 2. drop wrong hinges (cite a paper not in registry)
        for cid, pid, M in drop:
            K.w(d, f'match $c isa scilit-claim, has id "{cid}"; $p isa scilit-paper, has id "{pid}"; '
                   f'$h isa scilit-hinge, links (hinging-claim: $c, hinged-to: $p); delete $h;')
        # 3. reset reference-keys to correct positions
        for pid, v in papers.items():
            for k in v.get("rk", []):
                K.w(d, f'match $p isa scilit-paper, has id "{pid}", has scilit-reference-key $x; '
                       f'$x == "{escape_string(k)}"; delete has $x of $p;')
        for n, pid in pos2paper.items():
            key = f"{REVIEW_PAPER}:{n}"
            if not K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-reference-key $k; $k == "{key}";'):
                K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-reference-key "{key}";')
        # 4. recompute citation-load from corrected hinges
        load = Counter()
        for r in K.r(d, 'match $h isa scilit-hinge, links (hinged-to: $p); $p isa scilit-paper, has id $pid; '
                        'fetch {"p": $pid};'):
            load[r["p"]] += 1
        for pid in set(list(load.keys()) + list(papers.keys())):
            if K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-citation-load $v;'):
                K.w(d, f'match $p isa scilit-paper, has id "{pid}", has scilit-citation-load $v; delete has $v of $p;')
            if load.get(pid):
                K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-citation-load {load[pid]};')
        print("\nAPPLIED:", json.dumps({"repointed": len(repoint), "dropped": len(drop),
                                        "reference_keys_set": len(pos2paper)}))
    finally:
        d.close()

if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
