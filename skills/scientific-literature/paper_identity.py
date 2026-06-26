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
