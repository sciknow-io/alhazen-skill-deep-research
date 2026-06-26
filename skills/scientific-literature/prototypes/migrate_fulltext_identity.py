#!/usr/bin/env python3
"""Deterministic full-text artifacts + backfill. Dry-run unless --apply; symlink unless --move."""
import os, sys, glob, re, shutil
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
            aid = f"scilit-fulltext-{pid.split('-')[-1]}"
            dst_rel = f"fulltext/{pid}/{aid}.pdf"
            linked = K._has(d, f'$p isa scilit-paper, has id "{pid}"; $a isa alh-artifact, has id "{aid}"; '
                              f'$r isa alh-representation, links (alh-artifact: $a, referent: $p);')
            plan.append((pid, aid, src, dst_rel, linked))
        print(f"papers-with-cached-pdf={len(plan)} already-linked={sum(1 for x in plan if x[4])} "
              f"to-backfill={sum(1 for x in plan if not x[4])}")
        if not apply:
            print("DRY-RUN.")
            return
        created = 0
        linked_new = 0
        symlinked = 0
        skipped = 0
        for pid, aid, src, dst_rel, linked in plan:
            dst = os.path.join(CACHE, dst_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                shutil.move(src, dst)   # relocate the source into fulltext/; remove original
                symlinked += 1
            else:
                skipped += 1
            if not K._exists(d, aid):
                ts = get_timestamp()
                K.w(d, f'insert $a isa alh-artifact, has id "{aid}", has cache-path "{escape_string(dst_rel)}", '
                       f'has scilit-fulltext-kind "pdf", has format "application/pdf", has created-at {ts};')
                created += 1
            if not linked:
                K.w(d, f'match $a isa alh-artifact, has id "{aid}"; $p isa scilit-paper, has id "{pid}"; '
                       f'insert (alh-artifact: $a, referent: $p) isa alh-representation;')
                linked_new += 1
        print(f"APPLIED: artifacts-created={created} links-created={linked_new} symlinks-new={symlinked} symlinks-skipped={skipped}")
    finally:
        d.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv, move="--move" in sys.argv)
