"""Grounding QC gate (pure, domain-general).

Decides whether a candidate ontology match is trustworthy enough to accept as a grounding,
or must be flagged `needs-review`. The `policy` is a plain dict captured per-investigation in
the knowledge graph (NOT a yaml file); this function makes no domain assumptions of its own.

policy shape:
    {
      "confidence_threshold": float,
      "trusted_sources": [str, ...],
      "kinds": { kind: {"ontologies": [str, ...]}, ... },
    }
candidate shape:
    {curie, label, source, match_type("exact"|"synonym"|"fuzzy"), obsolete(bool),
     confidence(float), ambiguous(bool)}
"""
from entity_identity import normalize_curie


def qc_check(candidate, kind, policy):
    """Return (state, reason): 'grounded' iff all checks pass, else 'needs-review'."""
    kindcfg = policy.get("kinds", {}).get(kind)
    if not kindcfg:
        return "needs-review", f"unknown kind {kind!r}"
    src = candidate.get("source")
    # 1. trusted source
    if src not in policy.get("trusted_sources", []):
        return "needs-review", f"source {src} not trusted"
    # 2. kind/branch match — the kind's allowed ontologies
    if src not in kindcfg.get("ontologies", []):
        return "needs-review", f"source {src} not allowed for kind {kind}"
    # 3. not obsolete
    if candidate.get("obsolete"):
        return "needs-review", "obsolete term"
    # 4. CURIE resolves (well-formed PREFIX:LOCAL)
    curie = normalize_curie(candidate.get("curie"))
    if ":" not in curie or not curie.split(":", 1)[1]:
        return "needs-review", "unresolved CURIE"
    # 5. match quality — exact/synonym OK; fuzzy must clear the threshold
    if candidate.get("match_type") == "fuzzy" and \
            float(candidate.get("confidence", 0)) < policy.get("confidence_threshold", 0.5):
        return "needs-review", "fuzzy match below threshold"
    # 6. ambiguity guard
    if candidate.get("ambiguous"):
        return "needs-review", "ambiguous match"
    return "grounded", "ok"
