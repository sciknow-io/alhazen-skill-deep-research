#!/usr/bin/env python3
"""Reconcile scilit-papers whose source PDF is legacy-named (`pdf/artifact-<id>.pdf`,
reachable only via the paper's existing non-fulltext artifact, not by DOI filename)
into the unified full-text scheme: symlink the source to `fulltext/<paper-id>/<artifact-id>.pdf`,
create the deterministic `scilit-fulltext-<paper-hash>` artifact + alh-representation,
set acquisition-status=held if missing. Dry-run unless --apply; symlink unless --move."""
import os, sys, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import kqed as K
from kqed import escape_string, get_timestamp
CACHE = os.path.expanduser("~/.alhazen/cache")

def source_for(aid, cache_path):
    """Candidate source PDFs for a legacy artifact, first existing wins."""
    cands = [os.path.join(CACHE, "pdf", f"{aid}.pdf")]               # pdf/artifact-<id>.pdf
    if cache_path:
        if cache_path.lower().endswith(".pdf"):
            cands.append(os.path.join(CACHE, cache_path))            # cache-path already a pdf
        if cache_path.startswith("text/") and cache_path.endswith(".txt"):
            cands.append(os.path.join(CACHE, "pdf", os.path.basename(cache_path)[:-4] + ".pdf"))
    for c in cands:
        if os.path.exists(c):
            return c
    return None

def main(apply=False, move=False):
    d = K.get_driver()
    try:
        # papers that already have a NEW fulltext pdf artifact -> skip
        done = set(r["id"] for r in K.r(d,
            'match $p isa scilit-paper, has id $id; $a isa alh-artifact, has scilit-fulltext-kind "pdf"; '
            '(alh-artifact:$a, referent:$p) isa alh-representation; fetch {"id":$id};'))
        # papers with ANY linked artifact + that artifact's id/cache-path
        cand = {}
        for r in K.r(d, 'match $p isa scilit-paper, has id $pid; '
                        '$a isa alh-artifact, has id $aid, has cache-path $cp; '
                        '(alh-artifact:$a, referent:$p) isa alh-representation; '
                        'fetch {"pid":$pid,"aid":$aid,"cp":$cp};'):
            if r["pid"] in done: continue
            if r["aid"].startswith("scilit-fulltext-"): continue
            cand.setdefault(r["pid"], []).append((r["aid"], r["cp"]))
        plan = []
        for pid, arts in cand.items():
            src = None
            for aid, cp in arts:
                src = source_for(aid, cp)
                if src: break
            if src:
                plan.append((pid, src))
        print(f"papers needing legacy reconcile={len(cand)} | source PDF resolved={len(plan)} | unresolved={len(cand)-len(plan)}")
        if not apply:
            print("DRY-RUN. Re-run with --apply."); return
        art=lnk=sym=stat=0
        for pid, src in plan:
            aid = f"scilit-fulltext-{pid.split('-')[-1]}"
            dst_rel = f"fulltext/{pid}/{aid}.pdf"; dst = os.path.join(CACHE, dst_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                shutil.move(src, dst); sym += 1
            if not K._exists(d, aid):
                ts = get_timestamp()
                K.w(d, f'insert $a isa alh-artifact, has id "{aid}", has cache-path "{escape_string(dst_rel)}", '
                       f'has scilit-fulltext-kind "pdf", has format "application/pdf", has created-at {ts};'); art += 1
            if not K._has(d, f'$p isa scilit-paper, has id "{pid}"; $a isa alh-artifact, has id "{aid}"; '
                            f'$r isa alh-representation, links (alh-artifact:$a, referent:$p);'):
                K.w(d, f'match $a isa alh-artifact, has id "{aid}"; $p isa scilit-paper, has id "{pid}"; '
                       f'insert (alh-artifact:$a, referent:$p) isa alh-representation;'); lnk += 1
            if not K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-acquisition-status $s;'):
                K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-acquisition-status "held";'); stat += 1
        print(f"APPLIED: artifacts={art} links={lnk} symlinks={sym} status-set={stat}")
    finally:
        d.close()

if __name__ == "__main__":
    main(apply="--apply" in sys.argv, move="--move" in sys.argv)
