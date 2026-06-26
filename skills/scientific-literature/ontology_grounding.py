"""Ontology grounding: a pluggable lookup client (OLS4 by default) + orchestration that resolves
a verbatim mention to a canonical term under an investigation's grounding policy.

Pure orchestration (`ground_term`) takes the policy as a dict and an injectable `search` function,
so it is unit-testable without network. The default `ols_search` hits EBI OLS4. The QC gate
(`grounding_qc.qc_check`) decides grounded vs needs-review. No domain assumptions beyond the policy.
"""
import time

import requests

from entity_identity import normalize_curie
from grounding_qc import qc_check

OLS4 = "https://www.ebi.ac.uk/ols4/api"
HEADERS = {"User-Agent": "skillful-alhazen/0.1 (mailto:alhazen@example.com)"}

# Source label -> OLS ontology id (lowercase). Sources OLS doesn't serve (HGNC/UniProt) are
# skipped here and left to a profile's dedicated resolver; unresolved -> ungrounded/needs-review.
_OLS_ONTOLOGY = {
    "GO": "go", "CL": "cl", "CHEBI": "chebi", "HP": "hp", "UBERON": "uberon",
    "MONDO": "mondo", "RO": "ro", "PR": "pr", "SO": "so", "OBI": "obi", "EFO": "efo",
}


def ols_search(mention, ontologies):
    """Query OLS4 search across the given source labels; return normalized candidate dicts."""
    onts = ",".join(_OLS_ONTOLOGY[o] for o in ontologies if o in _OLS_ONTOLOGY)
    if not onts:
        return []
    params = {"q": mention, "ontology": onts, "rows": 5, "exact": "false"}
    resp = requests.get(f"{OLS4}/search", params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    docs = resp.json().get("response", {}).get("docs", [])
    ml = mention.strip().lower()
    out = []
    for d in docs:
        label = d.get("label", "") or ""
        syns = [s.lower() for s in (d.get("synonym") or [])]
        match_type = "exact" if label.lower() == ml else ("synonym" if ml in syns else "fuzzy")
        curie = d.get("obo_id") or (d.get("short_form", "") or "").replace("_", ":")
        out.append({
            "curie": normalize_curie(curie),
            "iri": d.get("iri", ""),
            "label": label,
            "source": (d.get("ontology_name") or "").upper(),
            "match_type": match_type,
            "obsolete": bool(d.get("is_obsolete")),
            "confidence": 1.0 if match_type != "fuzzy" else 0.4,
            "ambiguous": False,
            "ancestors": [],
        })
    # ambiguity guard: >1 distinct source with a non-fuzzy hit for the same mention
    strong_sources = {c["source"] for c in out if c["match_type"] in ("exact", "synonym")}
    if len(strong_sources) > 1:
        for c in out:
            c["ambiguous"] = True
    time.sleep(0.2)  # be polite to OLS
    return out


HGNC_REST = "https://rest.genenames.org"


def hgnc_search(mention, ontologies):
    """Resolve a gene/protein mention via the HGNC REST API (exact symbol fetch, then name search).
    Only runs when 'HGNC' is a requested source. Returns ols_search-shaped candidate dicts."""
    if "HGNC" not in ontologies:
        return []
    hdr = {**HEADERS, "Accept": "application/json"}
    out = []
    # 1. exact symbol fetch (the verbatim name is often the gene symbol)
    try:
        resp = requests.get(f"{HGNC_REST}/fetch/symbol/{mention}", headers=hdr, timeout=30)
        if resp.ok:
            for d in resp.json().get("response", {}).get("docs", []):
                out.append({"curie": d.get("hgnc_id", ""), "iri": "", "label": d.get("symbol", mention),
                            "source": "HGNC", "match_type": "exact", "obsolete": bool(d.get("status") == "Withdrawn"),
                            "confidence": 1.0, "ambiguous": False, "ancestors": []})
    except requests.RequestException:
        pass
    # 2. fall back to name/alias search
    if not out:
        try:
            resp = requests.get(f"{HGNC_REST}/search/{requests.utils.quote(mention)}", headers=hdr, timeout=30)
            if resp.ok:
                docs = resp.json().get("response", {}).get("docs", [])
                if docs:
                    top = docs[0]
                    score = float(top.get("score", 0))
                    out.append({"curie": top.get("hgnc_id", ""), "iri": "", "label": top.get("symbol", mention),
                                "source": "HGNC", "match_type": "synonym" if score >= 1.0 else "fuzzy",
                                "obsolete": False, "confidence": min(1.0, score / 5.0) if score else 0.4,
                                "ambiguous": len(docs) > 1 and score < 2.0, "ancestors": []})
        except requests.RequestException:
            pass
    time.sleep(0.1)
    return out


def search_sources(mention, sources):
    """Pluggable lookup dispatcher: route each requested source to its resolver (OLS for OBO
    ontologies, HGNC for genes), merge the candidates. New domains add resolvers here."""
    cands = list(ols_search(mention, sources))
    cands += hgnc_search(mention, sources)
    return cands


_MATCH_RANK = {"exact": 0, "synonym": 1, "fuzzy": 2}


def _select_best(candidates):
    """Pick the strongest candidate: prefer exact > synonym > fuzzy, then higher confidence.
    OLS relevance ranking sometimes puts a partial/fuzzy hit ahead of an exact one."""
    live = [c for c in candidates if not c.get("obsolete")]
    if not live:
        return candidates[0] if candidates else None
    return sorted(live, key=lambda c: (_MATCH_RANK.get(c.get("match_type"), 3),
                                       -float(c.get("confidence", 0))))[0]


def survey_term(mention, policy, search=search_sources):
    """Survey a mention WITHOUT a known kind: search across all the policy's ontologies, take the best
    hit, INFER the kind from the matched source, and QC it. Used by the survey step to discover which
    entities ground (and to what category) before committing. Returns
    {mention, state, curie, source, kind, label, reason}."""
    onts = []
    for cfg in policy.get("kinds", {}).values():
        for o in cfg.get("ontologies", []):
            if o not in onts:
                onts.append(o)
    cands = search(mention, onts) or []
    if not cands:
        return {"mention": mention, "state": "ungrounded", "reason": "no candidate",
                "curie": "", "source": "", "kind": None, "label": mention}
    best = _select_best(cands)
    inferred = None
    for k, cfg in policy.get("kinds", {}).items():
        if best.get("source") in cfg.get("ontologies", []):
            inferred = k
            break
    if inferred is None:
        return {"mention": mention, "state": "needs-review", "reason": "no kind maps to source",
                "curie": normalize_curie(best.get("curie")), "source": best.get("source", ""),
                "kind": None, "label": best.get("label", mention)}
    state, reason = qc_check(best, inferred, policy)
    return {"mention": mention, "state": state, "reason": reason,
            "curie": normalize_curie(best.get("curie")), "source": best.get("source", ""),
            "kind": inferred, "label": best.get("label", mention)}


def ground_term(mention, kind, policy, search=search_sources):
    """Resolve `mention` (of `kind`) to a canonical term under `policy`. Returns a grounding dict
    {state, reason, curie, iri, label, source, confidence, ancestors}. state is
    'grounded' | 'needs-review' | 'ungrounded'."""
    kindcfg = policy.get("kinds", {}).get(kind, {})
    candidates = search(mention, kindcfg.get("ontologies", [])) or []
    if not candidates:
        return {"state": "ungrounded", "reason": "no candidate", "curie": "", "iri": "",
                "label": mention, "source": "", "confidence": 0.0, "ancestors": []}
    best = _select_best(candidates)
    state, reason = qc_check(best, kind, policy)
    return {"state": state, "reason": reason, "curie": normalize_curie(best.get("curie")),
            "iri": best.get("iri", ""), "label": best.get("label", mention),
            "source": best.get("source", ""), "confidence": best.get("confidence", 0.0),
            "ancestors": best.get("ancestors", [])}
