import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paper_identity import canon_doi, content_basis, paper_identity

def test_canon_doi_strips_prefixes_and_lowercases():
    assert canon_doi("https://doi.org/10.1016/J.Cell.2022.11.001") == "10.1016/j.cell.2022.11.001"
    assert canon_doi("doi:10.1038/NATURE19768") == "10.1038/nature19768"
    assert canon_doi("  10.1111/acel.13524.  ") == "10.1111/acel.13524"
    assert canon_doi(None) == "" and canon_doi("") == ""

def test_identity_is_deterministic_and_doi_first():
    pid1, tier, val = paper_identity({"doi": "10.1016/j.cell.2022.11.001", "pmid": "36599349"})
    pid2, _, _ = paper_identity({"doi": "HTTPS://doi.org/10.1016/J.CELL.2022.11.001"})
    assert pid1 == pid2                      # normalization → same id
    assert tier == "doi" and val == "10.1016/j.cell.2022.11.001"
    assert pid1.startswith("scilit-paper-") and len(pid1) == len("scilit-paper-") + 12

def test_fallback_chain_pmid_then_arxiv_then_content():
    assert paper_identity({"pmid": "16904174"})[1] == "pmid"
    assert paper_identity({"arxiv": "2301.00001"})[1] == "arxiv"
    pid, tier, val = paper_identity({"title": "The Hallmarks of Aging", "first_author": "Lopez-Otin", "year": 2023})
    assert tier == "content-hash" and val == "the hallmarks of aging|lopez-otin|2023"

def test_tiers_do_not_collide():
    # a DOI string and a PMID string that look alike must not produce the same id
    a, _, _ = paper_identity({"doi": "12345"})
    b, _, _ = paper_identity({"pmid": "12345"})
    assert a != b
