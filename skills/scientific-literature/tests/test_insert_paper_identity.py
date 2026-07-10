import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import scientific_literature as SL
from paper_identity import paper_identity


def _cleanup(driver, pid):
    SL_DB = SL.TYPEDB_DATABASE
    with driver.transaction(SL_DB, SL.TransactionType.WRITE) as tx:
        tx.query(f'match $x has id "{pid}"; delete $x;').resolve()
        tx.commit()


def test_insert_paper_uses_deterministic_id_and_is_idempotent():
    driver = SL.get_driver()
    meta = {"doi": "10.9999/itest.insert-paper.identity", "title": "Test Insert Paper", "year": 2020}
    expected_id, tier, _ = paper_identity(meta)
    try:
        id1 = SL.insert_paper(driver, meta)
        id2 = SL.insert_paper(driver, meta)  # second call must not create a duplicate
        assert id1 == id2 == expected_id
        assert tier == "doi"
        with driver.transaction(SL.TYPEDB_DATABASE, SL.TransactionType.READ) as tx:
            rows = list(tx.query(f'match $p has id "{expected_id}"; select $p;').resolve())
        assert len(rows) == 1
    finally:
        _cleanup(driver, expected_id)
        driver.close()


def test_insert_epmc_paper_uses_deterministic_id_and_is_idempotent():
    driver = SL.get_driver()
    paper = {
        "doi": "10.9999/itest.insert-epmc.identity", "title": "Test EPMC Paper",
        "typedb_type": "scilit-paper", "source_uri": "https://example.com/test",
        "abstract": "", "journal": None, "journal_volume": None, "journal_issue": None,
        "page_range": None, "keywords": [], "pmid": None, "pmcid": None,
    }
    expected_id, _, _ = paper_identity({"doi": paper["doi"], "pmid": paper.get("pmid")})
    try:
        id1 = SL.insert_epmc_paper(driver, paper)
        id2 = SL.insert_epmc_paper(driver, paper)  # second call: must short-circuit, no duplicate
        assert id1 == id2 == expected_id
        with driver.transaction(SL.TYPEDB_DATABASE, SL.TransactionType.READ) as tx:
            rows = list(tx.query(f'match $p has id "{expected_id}"; select $p;').resolve())
        assert len(rows) == 1
    finally:
        _cleanup(driver, expected_id)
        driver.close()


def test_insert_epmc_paper_dedup_check_is_type_agnostic_for_preprints():
    """A scilit-preprint is a sibling type of scilit-paper (not a subtype). The
    duplicate-check must match by id alone, not `isa scilit-paper`, or a second
    ingest of the same preprint DOI would silently create a duplicate entity."""
    driver = SL.get_driver()
    paper = {
        "doi": "10.9999/itest.insert-epmc.preprint", "title": "Test Preprint",
        "typedb_type": "scilit-preprint", "source_uri": "https://example.com/preprint",
        "abstract": "", "journal": None, "journal_volume": None, "journal_issue": None,
        "page_range": None, "keywords": [], "pmid": None, "pmcid": None, "year": 2024,
    }
    expected_id, _, _ = paper_identity({"doi": paper["doi"], "pmid": paper.get("pmid")})
    try:
        id1 = SL.insert_epmc_paper(driver, paper)
        id2 = SL.insert_epmc_paper(driver, paper)
        assert id1 == id2 == expected_id
        with driver.transaction(SL.TYPEDB_DATABASE, SL.TransactionType.READ) as tx:
            rows = list(tx.query(f'match $p has id "{expected_id}"; select $p;').resolve())
        assert len(rows) == 1
    finally:
        _cleanup(driver, expected_id)
        driver.close()
