#!/usr/bin/env python3
"""
Build the citation-target registry for a review paper:
  - resolve the review's reference list (Crossref),
  - match each reference DOI against the local PDF cache,
  - classify primary vs review by venue/title,
  - upsert one scilit-paper per reference (real if held, stub if needed),
    carrying scilit-acquisition-status / -target-genre / -reference-key.

Reuses existing scilit-paper rows when a row with the same scilit-doi exists
(so the 106 already-ingested papers are reconciled, not duplicated).

Run:  uv run python prototypes/build_citation_registry.py
"""
import os, sys, json, re, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kqed as K
from kqed import escape_string

REVIEW_PAPER = "scilit-paper-21632e9ffb04"
REVIEW_DOI   = "10.1016/j.cell.2022.11.001"
CROSSREF_JSON = "/tmp/review_crossref.json"
PDF_DIR = os.path.expanduser("~/.alhazen/cache/pdf")

REVIEW_VENUE_RX = re.compile(
    r"nat(\.|ure)? rev|trends |annu(\.|al)? rev|physiol\.? rev|ageing res|"
    r"pharmacol\.? rev|endocr\.? rev|cold spring harb|review", re.I)
REVIEW_TITLE_RX = re.compile(r"hallmark|a review|: a review|perspective|overview of", re.I)


def canon(s):
    s = (s or "").lower()
    s = re.sub(r"\.pdf$", "", s)
    s = re.sub(r"__dup\d+", "", s)
    s = re.sub(r"^doi[\W_]+", "", s)
    s = re.sub(r"[\W_]*pdf$", "", s)
    s = re.sub(r"[\/_\-]+", ".", s)
    s = re.sub(r"\.+", ".", s).strip(".")
    return s


def build_cache_index():
    idx = {}
    for path in glob.glob(os.path.join(PDF_DIR, "*.pdf")):
        idx[canon(os.path.basename(path))] = os.path.basename(path)
    return idx


def classify_genre(title, journal):
    if REVIEW_VENUE_RX.search(journal or "") or REVIEW_TITLE_RX.search(title or ""):
        return "review"
    return "primary"


def find_paper_by_doi(d, doi):
    rows = K.r(d, f'match $p isa scilit-paper, has scilit-doi $x; $x == "{escape_string(doi)}"; fetch {{"id": $p.id}};')
    return rows[0]["id"] if rows else None


def set_single_attr(d, pid, attr, value):
    """Idempotent set of a single-valued attribute: drop any existing, then insert."""
    if K._has(d, f'$p isa scilit-paper, has id "{pid}", has {attr} "{escape_string(value)}";'):
        return
    if K._has(d, f'$p isa scilit-paper, has id "{pid}", has {attr} $v;'):
        K.w(d, f'match $p isa scilit-paper, has id "{pid}", has {attr} $v; delete has $v of $p;')
    K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has {attr} "{escape_string(value)}";')


def main():
    refs = json.load(open(CROSSREF_JSON))["message"].get("reference", [])
    cache = build_cache_index()
    d = K.get_driver()
    counts = {"held": 0, "needed": 0, "primary": 0, "review": 0, "reused": 0, "stub": 0}
    try:
        for ref in refs:
            doi = (ref.get("DOI") or "").lower().strip()
            if not doi:
                continue
            m = re.search(r"bib(\d+)$", ref.get("key", ""))
            refnum = m.group(1) if m else "?"
            refkey = f"{REVIEW_PAPER}:{refnum}"
            title = ref.get("article-title") or ref.get("volume-title") or ""
            journal = ref.get("journal-title") or ""
            year = ref.get("year") or ""
            genre = classify_genre(title, journal)
            held = canon(doi) in cache
            status = "held" if held else "needed"
            counts[status] += 1; counts[genre] += 1

            pid = find_paper_by_doi(d, doi)
            if pid:
                counts["reused"] += 1
                set_single_attr(d, pid, "scilit-acquisition-status", status)
                set_single_attr(d, pid, "scilit-target-genre", genre)
                # add reference-key if absent (multi-valued)
                if not K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-reference-key "{escape_string(refkey)}";'):
                    K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-reference-key "{escape_string(refkey)}";')
            else:
                counts["stub"] += 1
                pid = K.upsert_paper(d, {"doi": doi, "name": title or doi})
                set_single_attr(d, pid, "scilit-acquisition-status", status)
                set_single_attr(d, pid, "scilit-target-genre", genre)
                if not K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-reference-key "{escape_string(refkey)}";'):
                    K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-reference-key "{escape_string(refkey)}";')
                if journal:
                    set_single_attr(d, pid, "scilit-journal-name", journal)
                if year.isdigit():
                    if not K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-publication-year $y;'):
                        K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-publication-year {int(year)};')
        print(json.dumps(counts, indent=2))
    finally:
        d.close()


if __name__ == "__main__":
    main()
