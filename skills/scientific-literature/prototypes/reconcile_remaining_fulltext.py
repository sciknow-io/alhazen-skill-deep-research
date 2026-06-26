#!/usr/bin/env python3
"""Final tail: for DOI papers still without a full-text artifact and not marked 'needed',
locate a source PDF under alternate cache/pdf naming (arXiv `arxiv-<id>*.pdf`, or a fuzzy
normalized-DOI prefix that tolerates malformed suffixes). Link found sources into the
fulltext scheme; mark genuinely-sourceless papers `needed`. Dry-run unless --apply."""
import os, sys, glob, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import kqed as K
from kqed import escape_string, get_timestamp
CACHE = os.path.expanduser("~/.alhazen/cache")
PDF = os.path.join(CACHE, "pdf")

def find_source(doi):
    if "arxiv." in doi:
        aid = doi.split("arxiv.")[-1]
        for pat in (f"arxiv-{aid}*.pdf", f"arxiv-{aid.replace('.','_')}*.pdf"):
            h = glob.glob(os.path.join(PDF, pat))
            if h: return h[0]
    base = doi.replace("/", "_")
    h = sorted(glob.glob(os.path.join(PDF, base + "*.pdf")))
    return h[0] if h else None

def main(apply=False, move=False):
    d = K.get_driver()
    try:
        rows = K.r(d, 'match $p isa scilit-paper, has id $id, has scilit-doi $x; '
                      'not {$a isa alh-artifact, has scilit-fulltext-kind "pdf"; (alh-artifact:$a, referent:$p) isa alh-representation;}; '
                      'not {$p has scilit-acquisition-status "needed";}; fetch {"id":$id,"x":$x};')
        recl, needed = [], []
        for r in rows:
            pid, doi = r["id"], (r["x"] or "").strip().lower()
            src = find_source(doi)
            (recl if src else needed).append((pid, doi, src))
        print(f"tail={len(rows)} | reclaimable(source found)={len(recl)} | mark-needed(no source)={len(needed)}")
        if not apply:
            for pid, doi, src in recl: print("  RECLAIM", doi, "->", os.path.basename(src))
            print("DRY-RUN."); return
        art=lnk=sym=stat=mark=0
        for pid, doi, src in recl:
            aid = f"scilit-fulltext-{pid.split('-')[-1]}"
            dst_rel = f"fulltext/{pid}/{aid}.pdf"; dst = os.path.join(CACHE, dst_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst): shutil.move(src, dst); sym+=1
            if not K._exists(d, aid):
                ts=get_timestamp()
                K.w(d, f'insert $a isa alh-artifact, has id "{aid}", has cache-path "{escape_string(dst_rel)}", '
                       f'has scilit-fulltext-kind "pdf", has format "application/pdf", has created-at {ts};'); art+=1
            if not K._has(d, f'$p isa scilit-paper, has id "{pid}"; $a isa alh-artifact, has id "{aid}"; '
                            f'$r isa alh-representation, links (alh-artifact:$a, referent:$p);'):
                K.w(d, f'match $a isa alh-artifact, has id "{aid}"; $p isa scilit-paper, has id "{pid}"; '
                       f'insert (alh-artifact:$a, referent:$p) isa alh-representation;'); lnk+=1
            if not K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-acquisition-status $s;'):
                K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-acquisition-status "held";'); stat+=1
        for pid, doi, src in needed:
            if not K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-acquisition-status $s;'):
                K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-acquisition-status "needed";'); mark+=1
        print(f"APPLIED: reclaimed artifacts={art} links={lnk} symlinks={sym} held={stat} | marked-needed={mark}")
    finally:
        d.close()

if __name__ == "__main__":
    main(apply="--apply" in sys.argv, move="--move" in sys.argv)
