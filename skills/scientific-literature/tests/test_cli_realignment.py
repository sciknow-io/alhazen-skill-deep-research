"""
Tests for CLI/KQED re-alignment (Plan 2).

Task 1: scilit-sensemaking-experiment relation + authoring_db fixture.
Task 2: kqed.py authoring rewrite (add_kefed_model, add_observation, add_gap).
Task 3: RENAME-ONLY batch (reported-claim -> claim, reported-gap -> gap, kefed-variable -> ooevv-variable).
"""
import json
import os
import sys
import types

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


# ---------------------------------------------------------------------------
# Task 3 tests: RENAME-ONLY batch
#   cmd_add_reported_claim  -> inserts scilit-claim (was scilit-reported-claim)
#   cmd_add_reported_gap    -> inserts scilit-gap   (was scilit-reported-gap)
#   cmd_add_datum           -> matches ooevv-variable (was kefed-variable)
# ---------------------------------------------------------------------------

def test_cmd_add_reported_claim_inserts_scilit_claim(authoring_db, capsys):
    """cmd_add_reported_claim must insert a scilit-claim (not the retired scilit-reported-claim)
    and thread it under the bundle via scilit-sensemaking-reported-claim."""
    import scientific_literature as sl

    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-claim-t3", has name "claim bundle t3";')

    args = types.SimpleNamespace(
        bundle="scsm-claim-t3",
        type="primary",
        statement="SIRT3 activity declines with age in HSCs.",
        rhetorical_role=None,
        cites="",
        observations="",
    )
    sl.cmd_add_reported_claim(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["success"] is True, f"handler returned: {result}"
    claim_id = result["reported_claim_id"]

    # scilit-claim must exist and be threaded under the bundle
    rows = r(authoring_db,
             f'match $b isa scilit-paper-sensemaking, has id "scsm-claim-t3"; '
             f'$cl isa scilit-claim, has id "{claim_id}"; '
             f'(sensemaking: $b, reported-claim: $cl) isa scilit-sensemaking-reported-claim; '
             f'fetch {{"id": $cl.id}};')
    assert rows, f"scilit-claim {claim_id!r} not threaded under bundle via scilit-sensemaking-reported-claim"
    assert rows[0]["id"] == claim_id

    # claim must carry type and statement
    attr_rows = r(authoring_db,
                  f'match $cl isa scilit-claim, has id "{claim_id}", '
                  f'has scilit-claim-type $t, has scilit-claim-statement $s; '
                  f'fetch {{"t": $t, "s": $s}};')
    assert attr_rows and attr_rows[0]["t"] == "primary"
    assert "SIRT3" in attr_rows[0]["s"]


def test_cmd_add_reported_gap_inserts_scilit_gap(authoring_db, capsys):
    """cmd_add_reported_gap must insert a scilit-gap (not the retired scilit-reported-gap)
    and thread it under the bundle via scilit-sensemaking-reported-gap."""
    import scientific_literature as sl

    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-gap-t3", has name "gap bundle t3";')

    args = types.SimpleNamespace(
        bundle="scsm-gap-t3",
        statement="The mechanism by which SIRT3 reversal operates is unknown.",
        goal="understand the reversal mechanism",
    )
    sl.cmd_add_reported_gap(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["success"] is True, f"handler returned: {result}"
    gap_id = result["reported_gap_id"]

    # scilit-gap must exist and be threaded under the bundle
    rows = r(authoring_db,
             f'match $b isa scilit-paper-sensemaking, has id "scsm-gap-t3"; '
             f'$g isa scilit-gap, has id "{gap_id}"; '
             f'(sensemaking: $b, reported-gap: $g) isa scilit-sensemaking-reported-gap; '
             f'fetch {{"id": $g.id}};')
    assert rows, f"scilit-gap {gap_id!r} not threaded under bundle via scilit-sensemaking-reported-gap"
    assert rows[0]["id"] == gap_id


def test_cmd_add_datum_uses_ooevv_variable(authoring_db, capsys):
    """cmd_add_datum must link cells to ooevv-variable (not the retired kefed-variable).
    The ooevv-cell relation must be inserted when a valid ooevv-variable id is given."""
    import scientific_literature as sl

    # Insert prerequisite: kefed-instance + ooevv-variable
    w(authoring_db,
      'insert $i isa kefed-instance, has id "scinst-datum-t3", has name "test instance t3";')
    w(authoring_db,
      'insert $v isa ooevv-variable, has id "oov-datum-t3", has name "SIRT3 activity", '
      'has ooevv-variable-role "measurement";')

    args = types.SimpleNamespace(
        instance="scinst-datum-t3",
        cells=json.dumps([{"variable": "oov-datum-t3", "value": "low", "number": 0.3}]),
        observation=None,
        gloss=None,
    )
    sl.cmd_add_datum(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["success"] is True, f"handler returned: {result}"
    datum_id = result["datum_id"]
    assert result["cells"] == 1

    # ooevv-cell must link the datum to the ooevv-variable
    cell_rows = r(authoring_db,
                  f'match $d isa ooevv-datum, has id "{datum_id}"; '
                  f'$v isa ooevv-variable, has id "oov-datum-t3"; '
                  f'(datum: $d, cell-variable: $v) isa ooevv-cell; '
                  f'fetch {{"did": $d.id, "vid": $v.id}};')
    assert cell_rows, f"ooevv-cell not found linking datum {datum_id!r} to variable 'oov-datum-t3'"
    assert cell_rows[0]["did"] == datum_id
    assert cell_rows[0]["vid"] == "oov-datum-t3"
