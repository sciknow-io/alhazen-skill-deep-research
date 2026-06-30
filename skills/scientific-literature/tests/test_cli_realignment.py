"""
Tests for CLI/KQED re-alignment (Plan 2).

Task 1: scilit-sensemaking-experiment relation + authoring_db fixture.
Task 2: kqed.py authoring rewrite (add_kefed_model, add_observation, add_gap).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import w, r, SCRATCH_DB


def test_sensemaking_experiment_relation(scratch_db):
    w(scratch_db, 'insert $b isa scilit-paper-sensemaking, has id "scsm-1", has name "bundle";')
    w(scratch_db, 'insert $m isa kefed-model, has id "kefedm-x", has name "exp", has kefed-model-state "instantiated";')
    w(scratch_db, 'match $b isa scilit-paper-sensemaking, has id "scsm-1"; $m isa kefed-model, has id "kefedm-x";'
                  ' insert (sensemaking: $b, experiment: $m) isa scilit-sensemaking-experiment;')
    w(scratch_db, 'insert $i isa kefed-instance, has id "kefedi-x", has name "run";')
    w(scratch_db, 'match $b isa scilit-paper-sensemaking, has id "scsm-1"; $i isa kefed-instance, has id "kefedi-x";'
                  ' insert (sensemaking: $b, experiment: $i) isa scilit-sensemaking-experiment;')
    rows = r(scratch_db, 'match $b isa scilit-paper-sensemaking, has id "scsm-1";'
                         ' (sensemaking: $b, experiment: $e) isa scilit-sensemaking-experiment; $e has id $eid; fetch {"eid": $eid};')
    assert sorted(x["eid"] for x in rows) == ["kefedi-x", "kefedm-x"]


# ---------------------------------------------------------------------------
# Task 2 tests: add_kefed_model / add_observation / add_gap
# ---------------------------------------------------------------------------

def test_add_kefed_model_with_variables(authoring_db):
    """add_kefed_model inserts kefed-model + ooevv-variable elements via kefed-model-element.

    NEW signature: add_kefed_model(driver, name, experiment_type_term, variables=None, mid=None)
    Variables: list of (role, name, efo_label)  [3-tuple; value_set dropped].
    State must be 'template'.
    """
    import kqed
    mid = kqed.add_kefed_model(
        authoring_db,
        "Test Exp Model",
        "exp-type-dummy",      # vocab term; not in DB — classify silently skips
        variables=[
            ("parameter", "cell-type", "EFO:0000324"),
            ("measurement", "signal-intensity", ""),
        ],
        mid="kefedm-test-1",
    )
    assert mid == "kefedm-test-1"

    # model exists with state = "template"
    rows = r(authoring_db,
             'match $m isa kefed-model, has id "kefedm-test-1", has kefed-model-state $s; '
             'fetch {"s": $s};')
    assert rows, "kefed-model was not inserted"
    assert rows[0]["s"] == "template", f"expected 'template', got {rows[0]['s']!r}"

    # two ooevv-variable elements linked via kefed-model-element with correct roles
    var_rows = r(authoring_db,
                 'match $m isa kefed-model, has id "kefedm-test-1"; '
                 '(model: $m, element: $v) isa kefed-model-element; '
                 '$v isa ooevv-variable, has ooevv-variable-role $role; '
                 'fetch {"role": $role};')
    roles = sorted(x["role"] for x in var_rows)
    assert roles == ["measurement", "parameter"], f"unexpected roles: {roles}"


def test_add_observation_bundle_threaded(authoring_db):
    """add_observation inserts scilit-observation threaded under a sensemaking bundle.

    NEW signature: add_observation(driver, sensemaking_bundle, statement, knowledge_level, bio_scale,
                                   about=None, oid=None)
    Threading via scilit-sensemaking-observation (NOT scilit-investigation-observation).
    """
    import kqed
    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-obs-1", has name "obs test bundle";')
    oid = kqed.add_observation(
        authoring_db,
        "scsm-obs-1",                    # sensemaking_bundle (NOT investigation)
        "SIRT3 is enriched in HSCs.",
        "association",
        "molecular",
        oid="scobs-test-1",
    )
    assert oid == "scobs-test-1"

    # observation exists and is threaded under the bundle via scilit-sensemaking-observation
    rows = r(authoring_db,
             'match $b isa scilit-paper-sensemaking, has id "scsm-obs-1"; '
             '$o isa scilit-observation, has id "scobs-test-1"; '
             '(sensemaking: $b, observation: $o) isa scilit-sensemaking-observation; '
             'fetch {"id": $o.id};')
    assert rows, "scilit-observation not found under bundle via scilit-sensemaking-observation"
    assert rows[0]["id"] == "scobs-test-1"

    # observation carries knowledge-level and bio-scale
    kl_rows = r(authoring_db,
                'match $o isa scilit-observation, has id "scobs-test-1", '
                'has scilit-knowledge-level $kl, has scilit-bio-scale $bs; '
                'fetch {"kl": $kl, "bs": $bs};')
    assert kl_rows and kl_rows[0]["kl"] == "association"
    assert kl_rows[0]["bs"] == "molecular"


def test_add_gap_bundle_threaded(authoring_db):
    """add_gap inserts scilit-gap threaded under a sensemaking bundle.

    Signature: add_gap(driver, sensemaking_bundle, category_term, knowledge_goal,
                       provenance, statement, gid=None)
    Threading via scilit-sensemaking-reported-gap (NOT scilit-investigation-gap).
    """
    import kqed
    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-gap-1", has name "gap test bundle";')
    gid = kqed.add_gap(
        authoring_db,
        "scsm-gap-1",                              # sensemaking_bundle
        "dummy-category-term",                     # vocab term; not in DB — classify skips
        "understand the reversal mechanism",
        "explicit-cue",
        "The mechanism of SIRT3 aging reversal is unknown.",
        gid="scgap-test-1",
    )
    assert gid == "scgap-test-1"

    # gap exists and is threaded under the bundle via scilit-sensemaking-reported-gap
    rows = r(authoring_db,
             'match $b isa scilit-paper-sensemaking, has id "scsm-gap-1"; '
             '$g isa scilit-gap, has id "scgap-test-1"; '
             '(sensemaking: $b, reported-gap: $g) isa scilit-sensemaking-reported-gap; '
             'fetch {"id": $g.id};')
    assert rows, "scilit-gap not found under bundle via scilit-sensemaking-reported-gap"
    assert rows[0]["id"] == "scgap-test-1"

    # gap carries provenance
    prov_rows = r(authoring_db,
                  'match $g isa scilit-gap, has id "scgap-test-1", '
                  'has scilit-gap-provenance $p; fetch {"p": $p};')
    assert prov_rows and prov_rows[0]["p"] == "explicit-cue"
