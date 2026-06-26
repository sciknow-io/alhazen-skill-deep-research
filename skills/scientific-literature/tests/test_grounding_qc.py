"""Tests for the pure grounding QC gate. The policy is a plain dict (captured per-investigation
in the KG, NOT a yaml file) and is domain-general."""
from grounding_qc import qc_check

# A biology-domain policy (one profile). The QC gate makes no bio assumptions itself.
BIO = {
    "confidence_threshold": 0.5,
    "trusted_sources": ["GO", "CL", "CHEBI", "HP", "UBERON", "MONDO", "HGNC", "UniProt"],
    "kinds": {
        "process": {"ontologies": ["GO"]},
        "gene": {"ontologies": ["HGNC", "UniProt"]},
        "chemical": {"ontologies": ["CHEBI"]},
    },
}
# A non-bio policy proves the gate is domain-general.
CS = {
    "confidence_threshold": 0.6,
    "trusted_sources": ["WIKIDATA"],
    "kinds": {"technique": {"ontologies": ["WIKIDATA"]}},
}


def _cand(**kw):
    base = dict(curie="GO:0006325", label="chromatin organization", source="GO",
                match_type="exact", obsolete=False, confidence=0.9, ambiguous=False)
    base.update(kw)
    return base


def test_accepts_clean_exact_match():
    assert qc_check(_cand(), "process", BIO)[0] == "grounded"


def test_rejects_unknown_kind():
    assert qc_check(_cand(), "nope", BIO)[0] == "needs-review"


def test_rejects_obsolete():
    assert qc_check(_cand(obsolete=True), "process", BIO)[0] == "needs-review"


def test_rejects_untrusted_source():
    assert qc_check(_cand(source="WIKIDATA"), "process", BIO)[0] == "needs-review"


def test_rejects_cross_branch():
    # a gene must not ground to a GO-sourced term
    assert qc_check(_cand(source="GO"), "gene", BIO)[0] == "needs-review"


def test_rejects_unresolved_curie():
    assert qc_check(_cand(curie="GO:"), "process", BIO)[0] == "needs-review"


def test_rejects_low_confidence_fuzzy():
    assert qc_check(_cand(match_type="fuzzy", confidence=0.3), "process", BIO)[0] == "needs-review"


def test_accepts_fuzzy_above_threshold():
    assert qc_check(_cand(match_type="fuzzy", confidence=0.8), "process", BIO)[0] == "grounded"


def test_ambiguity_guard():
    assert qc_check(_cand(ambiguous=True), "process", BIO)[0] == "needs-review"


def test_domain_general_non_bio_policy():
    cand = _cand(curie="WIKIDATA:Q11660", label="attention", source="WIKIDATA", confidence=0.9)
    assert qc_check(cand, "technique", CS)[0] == "grounded"
    # the bio term would be rejected under the CS policy (untrusted source)
    assert qc_check(_cand(), "technique", CS)[0] == "needs-review"
