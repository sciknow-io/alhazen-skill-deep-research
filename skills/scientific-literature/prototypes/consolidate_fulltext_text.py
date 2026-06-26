#!/usr/bin/env python3
"""Consolidate extracted text into the unified per-paper full-text scheme.

End state per paper: ONE `scilit-pdf-fulltext` artifact `scilit-fulltext-<paper-hash>`,
renditions `fulltext/<paper-id>/scilit-fulltext-<paper-hash>.{pdf,txt}`, cache-path = the
.txt when text exists (else .pdf).

A1 (paper has BOTH a unified plain-alh pdf artifact + a legacy scilit-pdf-fulltext text
   artifact): move the text in, delete the plain-alh pdf artifact (its .pdf stays as the
   sibling), re-key the legacy (already the right type) to scilit-fulltext-<hash> (id swap
   preserves its fragments + representation), point cache-path at the .txt.
A2 (pdf-only plain-alh): re-type to scilit-pdf-fulltext (delete + recreate same id/attrs +
   re-point representation).
A3 (legacy text only, e.g. extracted/hallmarks_review.md): re-key it to scilit-fulltext-<hash>,
   move the file in, point cache-path at it.
Dry-run unless --apply."""
import os, sys, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import kqed as K
from kqed import escape_string, get_timestamp
CACHE = os.path.expanduser("~/.alhazen/cache")
STR_ATTRS = ["name","source-uri","cache-path","content-hash","mime-type","format","scilit-fulltext-kind"]

def paper_of(d, aid):
    r = K.r(d, f'match $x isa alh-artifact, has id "{escape_string(aid)}"; '
               f'(alh-artifact: $x, referent: $p) isa alh-representation; $p isa scilit-paper, has id $pid; '
               f'fetch {{"pid": $pid}};')
    return r[0]["pid"] if r else None

def get_attrs(d, aid):
    out = {}
    for a in STR_ATTRS:
        r = K.r(d, f'match $x isa alh-artifact, has id "{escape_string(aid)}", has {a} $v; fetch {{"v": $v}};')
        if r: out[a] = r[0]["v"]
    r = K.r(d, f'match $x isa alh-artifact, has id "{escape_string(aid)}", has file-size $v; fetch {{"v": $v}};')
    if r: out["file-size"] = r[0]["v"]
    return out

def n_frags(d, aid):
    return sum(1 for _ in K.r(d, f'match $a isa alh-artifact, has id "{escape_string(aid)}"; '
                                 f'(whole: $a, part: $f) isa alh-fragmentation; select $f;'))

def set_cache_path(d, aid, rel):
    if K._has(d, f'$a isa alh-artifact, has id "{escape_string(aid)}", has cache-path $v;'):
        K.w(d, f'match $a isa alh-artifact, has id "{escape_string(aid)}", has cache-path $v; delete has $v of $a;')
    K.w(d, f'match $a isa alh-artifact, has id "{escape_string(aid)}"; insert $a has cache-path "{escape_string(rel)}";')

def rekey(d, old, new):
    K.w(d, f'match $a isa alh-artifact, has id $o; $o == "{escape_string(old)}"; '
           f'delete has $o of $a; insert $a has id "{escape_string(new)}";')

def delete_artifact(d, aid):
    # drop its representation(s) then the entity
    K.w(d, f'match $a isa alh-artifact, has id "{escape_string(aid)}"; '
           f'$r isa alh-representation, links (alh-artifact: $a); delete $r;')
    K.w(d, f'match $a isa alh-artifact, has id "{escape_string(aid)}"; delete $a;')

def recreate_as_pdf_fulltext(d, aid, attrs, paper_id):
    parts = [f'has id "{escape_string(aid)}"']
    for k in STR_ATTRS:
        if attrs.get(k) is not None:
            parts.append(f'has {k} "{escape_string(str(attrs[k]))}"')
    if attrs.get("file-size") is not None:
        parts.append(f'has file-size {int(attrs["file-size"])}')
    parts.append(f'has created-at {get_timestamp()}')
    K.w(d, f'insert $a isa scilit-pdf-fulltext, {", ".join(parts)};')
    K.w(d, f'match $a isa scilit-pdf-fulltext, has id "{escape_string(aid)}"; $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
           f'insert (alh-artifact: $a, referent: $p) isa alh-representation;')

def ensure_pdf_fulltext_type(d, aid, paper_id):
    """Guarantee `aid` is typed scilit-pdf-fulltext. No-op when it already is (the common
    A1/A3 legacy artifact). For a legacy text artifact that was a plain alh-artifact (the
    extracted/hallmarks_review.md case), re-type via delete+recreate, preserving its
    representation (recreated) and its fragment links (fragment entities survive the
    artifact delete; we re-link them). TypeDB 3.x has no in-place re-type."""
    if K._has(d, f'$a isa scilit-pdf-fulltext, has id "{escape_string(aid)}";'):
        return
    attrs = get_attrs(d, aid)
    frags = [row["fid"] for row in K.r(d,
        f'match $a isa alh-artifact, has id "{escape_string(aid)}"; '
        f'(whole: $a, part: $f) isa alh-fragmentation; $f isa alh-fragment, has id $fid; '
        f'fetch {{"fid": $fid}};')]
    delete_artifact(d, aid)                       # drops representation + fragmentation relations
    recreate_as_pdf_fulltext(d, aid, attrs, paper_id)
    for fid in frags:                             # fragment entities survived; re-link them
        K.w(d, f'match $a isa scilit-pdf-fulltext, has id "{escape_string(aid)}"; '
               f'$f isa alh-fragment, has id "{escape_string(fid)}"; '
               f'insert (whole: $a, part: $f) isa alh-fragmentation;')

def main(apply=False):
    d = K.get_driver()
    try:
        unified, legacy = {}, {}
        for r in K.r(d, 'match $a isa alh-artifact, has id $aid, has cache-path $cp; fetch {"aid": $aid, "cp": $cp};'):
            aid, cp = r["aid"], r["cp"]
            if cp.startswith("fulltext/") and cp.endswith(".pdf") and aid.startswith("scilit-fulltext-"):
                p = paper_of(d, aid);  unified[p] = (aid, cp) if p else unified.get(p)
            elif cp.startswith("text/") or cp.startswith("extracted/"):
                p = paper_of(d, aid);  legacy[p] = (aid, cp) if p else legacy.get(p)
        unified.pop(None, None); legacy.pop(None, None)
        a1 = [p for p in legacy if p in unified]
        a2 = [p for p in unified if p not in legacy]
        a3 = [p for p in legacy if p not in unified]
        fragarts = fragn = 0
        for p in legacy:
            n = n_frags(d, legacy[p][0])
            if n: fragarts += 1; fragn += n
        # pending = classification keys on cache-path, but the type may already be fixed
        # (this script is idempotent): count only the artifacts still needing a re-type.
        a2_pending = sum(1 for p in a2
                         if not K._has(d, f'$a isa scilit-pdf-fulltext, has id "{escape_string(unified[p][0])}";'))
        print(f"A1(merge both)={len(a1)} | A2(re-type pdf-only)={len(a2)} (pending={a2_pending}) "
              f"| A3(legacy-only)={len(a3)} | legacy frag-artifacts={fragarts} frags={fragn}")
        if not apply:
            print("DRY-RUN. Re-run with --apply."); return
        # A1
        for p in a1:
            uaid, _ = unified[p]; laid, lcp = legacy[p]
            ext = ".md" if lcp.endswith(".md") else ".txt"
            new_txt = f"fulltext/{p}/{uaid}{ext}"
            src, dst = os.path.join(CACHE, lcp), os.path.join(CACHE, new_txt)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(src) and not os.path.exists(dst): shutil.move(src, dst)
            delete_artifact(d, uaid)          # free the deterministic id (its .pdf stays on disk)
            rekey(d, laid, uaid)              # legacy survives (fragments preserved by id swap)
            set_cache_path(d, uaid, new_txt)
            ensure_pdf_fulltext_type(d, uaid, p)  # re-type if the legacy was a plain alh-artifact
            if not K._has(d, f'$a isa alh-artifact, has id "{escape_string(uaid)}", has scilit-fulltext-kind $k;'):
                K.w(d, f'match $a isa alh-artifact, has id "{escape_string(uaid)}"; insert $a has scilit-fulltext-kind "pdf";')
        # A2 — re-type pdf-only plain alh-artifacts (no fragments). ensure_pdf_fulltext_type
        # early-returns for any already re-typed, so re-running --apply is a safe no-op.
        for p in a2:
            ensure_pdf_fulltext_type(d, unified[p][0], p)
        # A3
        for p in a3:
            laid, lcp = legacy[p]
            new_aid = f"scilit-fulltext-{p.split('-')[-1]}"
            ext = ".md" if lcp.endswith(".md") else ".txt"
            new_rel = f"fulltext/{p}/{new_aid}{ext}"
            src, dst = os.path.join(CACHE, lcp), os.path.join(CACHE, new_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(src) and not os.path.exists(dst): shutil.move(src, dst)
            rekey(d, laid, new_aid); set_cache_path(d, new_aid, new_rel)
            ensure_pdf_fulltext_type(d, new_aid, p)  # re-type if the legacy was a plain alh-artifact
        print(f"APPLIED: A1={len(a1)} A2={len(a2)} A3={len(a3)}")
    finally:
        d.close()

if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
