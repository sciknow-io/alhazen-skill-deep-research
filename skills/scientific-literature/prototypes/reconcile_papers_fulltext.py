#!/usr/bin/env python3
"""Reconcile scilit-papers whose source PDF lives in the `papers/` download workspace
(e.g. CAIS-2026, DOI-structured `papers/<prefix>/<suffix>.pdf`) into the SAME full-text
scheme as every other scilit investigation: symlink the source to
`fulltext/<paper-id>/<artifact-id>.pdf`, create the deterministic `scilit-fulltext-<paper-hash>`
artifact (kind=pdf) linked via alh-representation, and set acquisition-status=held.

Dry-run unless --apply; symlink unless --move."""
import os, sys, glob, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import kqed as K
from kqed import escape_string, get_timestamp
CACHE = os.path.expanduser("~/.alhazen/cache")

def papers_dir_index():
    """DOI (lower) -> source path, for files under cache/papers/<prefix>/<suffix>.pdf"""
    idx = {}
    for f in glob.glob(os.path.join(CACHE, "papers", "**", "*.pdf"), recursive=True):
        prefix = os.path.basename(os.path.dirname(f))
        doi = f"{prefix}/{os.path.basename(f)[:-4]}".lower()
        idx[doi] = f
    return idx

def main(apply=False, move=False):
    d = K.get_driver()
    try:
        src_by_doi = papers_dir_index()
        rows = K.r(d, 'match $p isa scilit-paper, has id $id, has scilit-doi $x; fetch {"id":$id,"x":$x};')
        plan = []
        for r in rows:
            pid, doi = r["id"], (r["x"] or "").strip().lower()
            src = src_by_doi.get(doi)
            if not src:
                continue
            aid = f"scilit-fulltext-{pid.split('-')[-1]}"
            linked = K._has(d, f'$p isa scilit-paper, has id "{pid}"; $a isa alh-artifact, has id "{aid}"; '
                              f'$r isa alh-representation, links (alh-artifact: $a, referent: $p);')
            has_status = K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-acquisition-status $s;')
            plan.append((pid, doi, aid, src, f"fulltext/{pid}/{aid}.pdf", linked, has_status))
        print(f"papers/-sourced scilit-papers={len(plan)} | already-linked={sum(1 for x in plan if x[5])} "
              f"| to-link={sum(1 for x in plan if not x[5])} | missing-status={sum(1 for x in plan if not x[6])}")
        if not apply:
            print("DRY-RUN. Re-run with --apply."); return
        art=lnk=sym=stat=0
        for pid, doi, aid, src, dst_rel, linked, has_status in plan:
            dst = os.path.join(CACHE, dst_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                shutil.move(src, dst); sym += 1
            if not K._exists(d, aid):
                ts = get_timestamp()
                K.w(d, f'insert $a isa alh-artifact, has id "{aid}", has cache-path "{escape_string(dst_rel)}", '
                       f'has scilit-fulltext-kind "pdf", has format "application/pdf", has created-at {ts};'); art += 1
            if not linked:
                K.w(d, f'match $a isa alh-artifact, has id "{aid}"; $p isa scilit-paper, has id "{pid}"; '
                       f'insert (alh-artifact: $a, referent: $p) isa alh-representation;'); lnk += 1
            if not has_status:
                K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-acquisition-status "held";'); stat += 1
        print(f"APPLIED: artifacts={art} links={lnk} symlinks={sym} status-set={stat}")
    finally:
        d.close()

if __name__ == "__main__":
    main(apply="--apply" in sys.argv, move="--move" in sys.argv)
