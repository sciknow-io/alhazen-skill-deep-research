"""Tests for ground_term orchestration (search injected — no network)."""
from ontology_grounding import ground_term

BIO = {
    "confidence_threshold": 0.5,
    "trusted_sources": ["GO", "CHEBI", "CL"],
    "kinds": {"process": {"ontologies": ["GO"]}, "chemical": {"ontologies": ["CHEBI"]}},
}


def _fake(mention, ontologies):
    return [dict(curie="GO:0006325", iri="http://purl.obolibrary.org/obo/GO_0006325",
                 label="chromatin organization", source="GO", match_type="exact",
                 obsolete=False, confidence=0.95, ambiguous=False,
                 ancestors=["GO:0016043"])]


def test_ground_term_grounds_clean_match():
    g = ground_term("chromatin organization", "process", BIO, search=_fake)
    assert g["state"] == "grounded"
    assert g["curie"] == "GO:0006325" and g["source"] == "GO"
    assert "GO:0016043" in g["ancestors"]


def test_ground_term_no_candidate_is_ungrounded():
    g = ground_term("zxqq", "process", BIO, search=lambda m, o: [])
    assert g["state"] == "ungrounded"


def test_ground_term_cross_branch_needs_review():
    # a GO term offered for a 'chemical' kind (whose policy allows only CHEBI) -> needs-review
    g = ground_term("chromatin organization", "chemical", BIO, search=_fake)
    assert g["state"] == "needs-review"


def test_survey_term_infers_kind_from_source():
    from ontology_grounding import survey_term
    g = survey_term("chromatin organization", BIO, search=_fake)
    # source GO maps to the 'process' kind in the policy, and the exact match grounds
    assert g["kind"] == "process" and g["state"] == "grounded" and g["curie"] == "GO:0006325"


def test_survey_term_no_candidate_is_ungrounded():
    from ontology_grounding import survey_term
    g = survey_term("zxqq", BIO, search=lambda m, o: [])
    assert g["state"] == "ungrounded" and g["kind"] is None
