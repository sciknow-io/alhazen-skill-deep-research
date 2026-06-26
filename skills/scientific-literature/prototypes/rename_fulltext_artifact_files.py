#!/usr/bin/env python3
"""Name full-text cache files by their artifact id. For each pdf full-text artifact
(`scilit-fulltext-<hash>-pdf` with cache-path `fulltext/<paper-id>/source.pdf`):
  - re-key the artifact id to the kind-less `scilit-fulltext-<hash>` (one artifact / paper;
    the .pdf and future .txt renditions share this id-base, differing only by suffix),
  - rename the file `source.pdf` -> `<new-id>.pdf` (move within the same dir),
  - update the cache-path file xref,
  - complete the file xref: backfill content-hash / file-size / mime-type where absent.
Relations bind to the entity, so the id @key swap preserves alh-representation/fragmentation.
Dry-run unless --apply."""
import os, sys, hashlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import kqed as K
from kqed import escape_string
CACHE = os.path.expanduser("~/.alhazen/cache")

def main(apply=False):
    d = K.get_driver()
    try:
        rows = K.r(d, 'match $a isa alh-artifact, has scilit-fulltext-kind "pdf", has id $id, has cache-path $cp; '
                      'fetch {"id":$id,"cp":$cp};')
        plan, skip, collide = [], 0, []
        for r in rows:
            old_aid, old_rel = r["id"], r["cp"]
            if not old_aid.endswith("-pdf"):
                skip += 1; continue                       # already kind-less / not a target
            new_aid = old_aid[:-4]                         # strip trailing "-pdf"
            parts = old_rel.split("/")                     # fulltext/<paper-id>/source.pdf
            if len(parts) < 3 or parts[0] != "fulltext":
                skip += 1; continue
            paper_id = parts[1]
            new_rel = f"fulltext/{paper_id}/{new_aid}.pdf"
            if K._exists(d, new_aid):                      # id collision guard
                collide.append((old_aid, new_aid)); continue
            plan.append((old_aid, new_aid, old_rel, new_rel))
        print(f"pdf fulltext artifacts={len(rows)} | to-rename={len(plan)} | skip(non-target)={skip} | COLLISIONS={len(collide)}")
        for o,n,_,_ in plan[:6]: print(f"   {o} -> {n}")
        if collide: print("   !! collisions:", collide[:5])
        if not apply:
            print("DRY-RUN. Re-run with --apply."); return
        moved=rekey=cp=meta=0
        for old_aid, new_aid, old_rel, new_rel in plan:
            old_f, new_f = os.path.join(CACHE, old_rel), os.path.join(CACHE, new_rel)
            if os.path.exists(old_f) and not os.path.exists(new_f):
                os.rename(old_f, new_f); moved += 1        # same dir => rename
            # re-key the artifact id (relations survive)
            K.w(d, f'match $a isa alh-artifact, has id $o; $o == "{escape_string(old_aid)}"; '
                   f'delete has $o of $a; insert $a has id "{escape_string(new_aid)}";'); rekey += 1
            # update cache-path file xref
            K.w(d, f'match $a isa alh-artifact, has id "{escape_string(new_aid)}", has cache-path $v; delete has $v of $a;')
            K.w(d, f'match $a isa alh-artifact, has id "{escape_string(new_aid)}"; insert $a has cache-path "{escape_string(new_rel)}";'); cp += 1
            # complete the file xref: content-hash / file-size / mime-type (only where absent)
            if os.path.exists(new_f):
                b = open(new_f, "rb").read()
                if not K._has(d, f'$a isa alh-artifact, has id "{escape_string(new_aid)}", has content-hash $h;'):
                    K.w(d, f'match $a isa alh-artifact, has id "{escape_string(new_aid)}"; insert $a has content-hash "{hashlib.sha256(b).hexdigest()}";')
                if not K._has(d, f'$a isa alh-artifact, has id "{escape_string(new_aid)}", has file-size $s;'):
                    K.w(d, f'match $a isa alh-artifact, has id "{escape_string(new_aid)}"; insert $a has file-size {len(b)};')
                if not K._has(d, f'$a isa alh-artifact, has id "{escape_string(new_aid)}", has mime-type $m;'):
                    K.w(d, f'match $a isa alh-artifact, has id "{escape_string(new_aid)}"; insert $a has mime-type "application/pdf";')
                meta += 1
        print(f"APPLIED: files-moved={moved} ids-rekeyed={rekey} cache-paths={cp} xref-completed={meta}")
    finally:
        d.close()

if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
