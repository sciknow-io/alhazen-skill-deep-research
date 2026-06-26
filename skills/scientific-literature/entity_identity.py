"""Deterministic, domain-general identity for scilit entities.

An entity's id is a pure function of its best stable key: a grounded CURIE when available,
else a normalized verbatim name. Mirrors paper_identity.py. No domain assumptions (works for
biology CURIEs, Wikidata, or any other namespace) and no DB dependency.
"""
import hashlib
import re

_OBO_IRI = re.compile(r".*/obo/([A-Za-z]+)_(\d+)$")


def normalize_curie(s):
    """Canonicalize a CURIE/IRI to `PREFIX:LOCALID` with an upper-cased prefix."""
    if not s:
        return ""
    s = str(s).strip()
    m = _OBO_IRI.match(s)
    if m:
        return f"{m.group(1).upper()}:{m.group(2)}"
    if ":" in s:
        pfx, local = s.split(":", 1)
        return f"{pfx.strip().upper()}:{local.strip()}"
    return s.upper()


def _norm_name(n):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (n or "").lower())).strip()


def entity_identity(meta):
    """meta: {curie?, name?} -> (entity_id, basis_tier, basis_value).

    tier 'curie' when a CURIE is present (canonical concept identity), else 'name'
    (normalized-mention fallback for ungrounded entities).
    """
    curie = normalize_curie(meta.get("curie"))
    if curie:
        tier, value = "curie", curie
    else:
        tier, value = "name", _norm_name(meta.get("name"))
    eid = "scilit-entity-" + hashlib.sha256(f"{tier}:{value}".encode("utf-8")).hexdigest()[:12]
    return eid, tier, value
