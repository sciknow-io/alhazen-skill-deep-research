"""Tests for domain-general deterministic entity identity."""
from entity_identity import normalize_curie, entity_identity


def test_normalize_curie_prefix_case_and_obo_iri():
    assert normalize_curie("go:0006325") == "GO:0006325"
    assert normalize_curie("http://purl.obolibrary.org/obo/GO_0006325") == "GO:0006325"
    assert normalize_curie("CHEBI:26523") == "CHEBI:26523"
    # non-bio CURIE namespaces are handled identically (no domain assumption)
    assert normalize_curie("wikidata:Q42") == "WIKIDATA:Q42"
    assert normalize_curie("") == ""


def test_identity_curie_tier_is_deterministic_and_case_insensitive():
    a = entity_identity({"curie": "GO:0006325", "name": "chromatin organization"})
    b = entity_identity({"curie": "go:0006325"})
    assert a[0] == b[0]
    assert a[1] == "curie" and a[2] == "GO:0006325"
    assert a[0].startswith("scilit-entity-") and len(a[0]) == len("scilit-entity-") + 12


def test_identity_name_fallback_when_ungrounded():
    i = entity_identity({"name": "Transformer"})
    assert i[1] == "name" and i[2] == "transformer"
    # normalization collapses whitespace/punctuation so the same mention is one node
    assert i[0] == entity_identity({"name": " transformer "})[0]


def test_identity_is_domain_agnostic():
    # a non-bio entity grounds by CURIE exactly like a bio one
    bio = entity_identity({"curie": "PR:000015376", "name": "sirtuin-3"})
    cs = entity_identity({"curie": "WIKIDATA:Q11660", "name": "artificial intelligence"})
    assert bio[1] == "curie" and cs[1] == "curie"
    assert bio[0] != cs[0]
