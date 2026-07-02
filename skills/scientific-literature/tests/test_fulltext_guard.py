"""
Constraint: KQED ingestion (create-bundle) MUST be blocked when the focal paper has
no full text on disk / in the graph. You cannot sense-make a paper you haven't got.

A paper "has full text" iff it has an alh-representation to a fulltext artifact
(an alh-artifact bearing scilit-fulltext-kind, e.g. scilit-pdf-fulltext / scilit-jats-fulltext).
"""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import w, r, SCRATCH_DB

TS = "2026-01-01T00:00:00"


def _seed_investigation_and_paper(db, paper_id, with_fulltext):
    w(db, f'insert $inv isa scilit-investigation, has id "scinv-guard", has name "Guard inv", has created-at {TS};')
    w(db, f'insert $p isa scilit-paper, has id "{paper_id}", has name "Guard paper", has created-at {TS};')
    if with_fulltext:
        w(db, f'insert $a isa scilit-pdf-fulltext, has id "scilit-fulltext-guard", '
              f'has name "Guard paper [full text]", has scilit-fulltext-kind "pdf", has created-at {TS};')
        w(db, f'match $p isa scilit-paper, has id "{paper_id}"; $a isa scilit-pdf-fulltext, has id "scilit-fulltext-guard"; '
              f'insert (alh-artifact: $a, referent: $p) isa alh-representation;')


def _run_create_bundle(paper_id, capsys):
    import scientific_literature as sl
    args = types.SimpleNamespace(investigation="scinv-guard", paper=paper_id, iteration=1, name="guard bundle")
    exit_code = None
    try:
        sl.cmd_create_bundle(args)
    except SystemExit as e:
        exit_code = e.code
    out = json.loads(capsys.readouterr().out)
    return out, exit_code


def test_create_bundle_blocked_without_fulltext(authoring_db, capsys):
    """create-bundle refuses a paper that has no full text, and creates no bundle."""
    _seed_investigation_and_paper(authoring_db, "scilit-paper-noft", with_fulltext=False)

    out, exit_code = _run_create_bundle("scilit-paper-noft", capsys)

    assert out["success"] is False, f"expected refusal, got {out}"
    assert "full text" in out["error"].lower()
    assert exit_code == 1
    # no bundle was created
    bundles = r(authoring_db, 'match $b isa scilit-paper-sensemaking, has id $i; fetch {"i": $i};')
    assert bundles == [], f"a bundle was created despite missing full text: {bundles}"


def test_create_bundle_allowed_with_fulltext(authoring_db, capsys):
    """create-bundle proceeds normally once the paper has a fulltext artifact."""
    _seed_investigation_and_paper(authoring_db, "scilit-paper-hasft", with_fulltext=True)

    out, exit_code = _run_create_bundle("scilit-paper-hasft", capsys)

    assert out["success"] is True, f"expected success, got {out}"
    assert exit_code is None
    assert out["paper"] == "scilit-paper-hasft"
    bundles = r(authoring_db, 'match $b isa scilit-paper-sensemaking, has id $i; fetch {"i": $i};')
    assert len(bundles) == 1
