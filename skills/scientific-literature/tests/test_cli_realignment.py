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


# ---------------------------------------------------------------------------
# Task 4 tests: KEfED bigraph authoring rework + delete slot commands
#   cmd_add_experiment  -> scilit-sensemaking-experiment (was ooevv-bundle-experiment)
#   cmd_add_process     -> kefed-model-element (was ooevv-set-process)
#   cmd_add_variable    -> ooevv-variable + kefed-model-element (was kefed-variable + kefed-element)
#                       -> produced-variable/producing-process (was produced-measurement/terminal-process)
#   cmd_bind_parameter  -> binding-bearer (was binding-process)
#   cmd_ensure_template -> kefed-model + kefed-model-state "template" (was kefed-template type)
#   cmd_instantiate_template -> scilit-sensemaking-experiment + ooevv-instance-of:model (was template role)
#   DELETE: cmd_add_slot, cmd_param_slot, cmd_bind_slot
# ---------------------------------------------------------------------------

def test_t4_bigraph_authoring_roundtrip(authoring_db, capsys):
    """Task 4: drive a small bigraph through cmd_add_experiment / cmd_add_process /
    cmd_add_variable / cmd_bind_parameter and assert the NEW relations round-trip correctly."""
    import scientific_literature as sl

    # --- prerequisites ---
    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-t4-1", has name "T4 bundle";')
    w(authoring_db,
      'insert $q isa ooevv-quality, has id "scqual-t4-1", has name "SIRT3 activity", '
      'has ooevv-definition "Enzymatic deacetylation activity of SIRT3 in mitochondria.", '
      'has created-at 2026-06-30T00:00:00;')

    # 1. add-experiment -> scilit-sensemaking-experiment
    args_exp = types.SimpleNamespace(bundle="scsm-t4-1", name="T4 SIRT3 assay")
    sl.cmd_add_experiment(args_exp)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_experiment failed: {res}"
    exp_id = res["experiment_id"]

    rows = r(authoring_db,
             f'match $b isa scilit-paper-sensemaking, has id "scsm-t4-1"; '
             f'$m isa kefed-model, has id "{exp_id}"; '
             f'(sensemaking: $b, experiment: $m) isa scilit-sensemaking-experiment; '
             f'fetch {{"eid": $m.id}};')
    assert rows, f"scilit-sensemaking-experiment not found for experiment {exp_id!r}"
    assert rows[0]["eid"] == exp_id

    # 2. add-process -> kefed-model-element(model, element)
    args_proc = types.SimpleNamespace(
        experiment=exp_id, template=None,
        name="Western blot assay", type="assay",
        parent=None,
        definition="A western blot detecting SIRT3 protein levels.",
        long_form=None,
    )
    sl.cmd_add_process(args_proc)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_process failed: {res}"
    proc_id = res["process_id"]

    rows = r(authoring_db,
             f'match $m isa kefed-model, has id "{exp_id}"; '
             f'$p isa ooevv-process, has id "{proc_id}"; '
             f'(model: $m, element: $p) isa kefed-model-element; '
             f'fetch {{"pid": $p.id}};')
    assert rows, f"kefed-model-element not found for process {proc_id!r}"
    assert rows[0]["pid"] == proc_id

    # 3. add-variable (measurement) -> ooevv-variable + kefed-model-element +
    #    ooevv-produced-by with produced-variable/producing-process roles
    args_meas = types.SimpleNamespace(
        experiment=exp_id, template=None,
        name="SIRT3 signal", role="measurement",
        quality="scqual-t4-1", scale_type="numeric",
        unit="AU", min=None, max=None, values=None,
        produced_by=proc_id,
        definition="Normalized SIRT3 band intensity from western blot.",
        long_form=None,
    )
    sl.cmd_add_variable(args_meas)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_variable (measurement) failed: {res}"
    var_meas_id = res["variable_id"]

    # ooevv-variable + kefed-model-element
    rows = r(authoring_db,
             f'match $m isa kefed-model, has id "{exp_id}"; '
             f'$v isa ooevv-variable, has id "{var_meas_id}"; '
             f'(model: $m, element: $v) isa kefed-model-element; '
             f'fetch {{"vid": $v.id}};')
    assert rows, f"kefed-model-element not found for measurement variable {var_meas_id!r}"
    assert rows[0]["vid"] == var_meas_id

    # ooevv-produced-by with NEW role names
    rows = r(authoring_db,
             f'match $v isa ooevv-variable, has id "{var_meas_id}"; '
             f'$p isa ooevv-process, has id "{proc_id}"; '
             f'(produced-variable: $v, producing-process: $p) isa ooevv-produced-by; '
             f'fetch {{"vid": $v.id}};')
    assert rows, "ooevv-produced-by produced-variable/producing-process not found"

    # ooevv-variable-role (not kefed-variable-role)
    rows = r(authoring_db,
             f'match $v isa ooevv-variable, has id "{var_meas_id}", has ooevv-variable-role $vr; '
             f'fetch {{"vr": $vr}};')
    assert rows and rows[0]["vr"] == "measurement", f"ooevv-variable-role mismatch: {rows}"

    # 4. add-variable (parameter) for bind-parameter test
    args_param = types.SimpleNamespace(
        experiment=exp_id, template=None,
        name="antibody concentration", role="parameter",
        quality="scqual-t4-1", scale_type="numeric",
        unit="ug/mL", min=None, max=None, values=None,
        produced_by=None,
        definition="Concentration of primary antibody used in the western blot.",
        long_form=None,
    )
    sl.cmd_add_variable(args_param)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_variable (parameter) failed: {res}"
    param_id = res["variable_id"]

    # 5. bind-parameter -> binding-bearer (not binding-process)
    args_bind = types.SimpleNamespace(
        process=proc_id, parameter=param_id, target_entity=None,
    )
    sl.cmd_bind_parameter(args_bind)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_bind_parameter failed: {res}"

    rows = r(authoring_db,
             f'match $p isa ooevv-process, has id "{proc_id}"; '
             f'$v isa ooevv-variable, has id "{param_id}"; '
             f'(binding-bearer: $p, bound-parameter: $v) isa ooevv-parameter-binding; '
             f'fetch {{"pid": $p.id}};')
    assert rows, "ooevv-parameter-binding with binding-bearer role not found"
    assert rows[0]["pid"] == proc_id


def test_t4_ensure_template_uses_kefed_model_state(authoring_db, capsys):
    """cmd_ensure_template must find-or-create a kefed-model with kefed-model-state 'template'
    (not the retired kefed-template type)."""
    import scientific_literature as sl

    # First call: create (kefed-model does not own ooevv-definition; definition arg is unused)
    args_create = types.SimpleNamespace(
        name="qPCR expression profiling",
        definition=None,
        long_form=None,
    )
    sl.cmd_ensure_template(args_create)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_ensure_template (create) failed: {res}"
    assert res["reused"] is False
    tpl_id = res["template_id"]

    # kefed-model with state "template" must exist
    rows = r(authoring_db,
             f'match $t isa kefed-model, has id "{tpl_id}", has kefed-model-state $s; '
             f'fetch {{"s": $s}};')
    assert rows and rows[0]["s"] == "template", f"kefed-model template state not found: {rows}"

    # Second call: find (reuse)
    sl.cmd_ensure_template(args_create)
    out = capsys.readouterr().out
    res2 = json.loads(out)
    assert res2["success"] is True
    assert res2["reused"] is True
    assert res2["template_id"] == tpl_id


def test_t4_instantiate_template_uses_sensemaking_experiment(authoring_db, capsys):
    """cmd_instantiate_template must attach instance via scilit-sensemaking-experiment
    and use ooevv-instance-of with model role (not template role)."""
    import scientific_literature as sl

    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-t4-inst", has name "inst bundle";')
    # Create a template-state model manually
    w(authoring_db,
      'insert $t isa kefed-model, has id "kefedm-t4-tpl", has name "Test Template", '
      'has kefed-model-state "template", has created-at 2026-06-30T00:00:00;')

    args_inst = types.SimpleNamespace(
        bundle="scsm-t4-inst",
        template="kefedm-t4-tpl",
        name="test instance run",
    )
    sl.cmd_instantiate_template(args_inst)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_instantiate_template failed: {res}"
    inst_id = res["instance_id"]

    # ooevv-instance-of with model role (not template)
    rows = r(authoring_db,
             f'match $i isa kefed-instance, has id "{inst_id}"; '
             f'$m isa kefed-model, has id "kefedm-t4-tpl"; '
             f'(instance: $i, model: $m) isa ooevv-instance-of; '
             f'fetch {{"iid": $i.id}};')
    assert rows, "ooevv-instance-of with model role not found"
    assert rows[0]["iid"] == inst_id

    # scilit-sensemaking-experiment must link bundle to instance (not ooevv-bundle-experiment)
    rows = r(authoring_db,
             f'match $b isa scilit-paper-sensemaking, has id "scsm-t4-inst"; '
             f'$i isa kefed-instance, has id "{inst_id}"; '
             f'(sensemaking: $b, experiment: $i) isa scilit-sensemaking-experiment; '
             f'fetch {{"iid": $i.id}};')
    assert rows, "scilit-sensemaking-experiment not found for kefed-instance"
    assert rows[0]["iid"] == inst_id


def test_t4_slot_commands_deleted():
    """Task 4: cmd_add_slot / cmd_param_slot / cmd_bind_slot must be deleted from the module."""
    import scientific_literature as sl

    assert not hasattr(sl, 'cmd_add_slot'), \
        "cmd_add_slot must be deleted (slots folded into uninstantiated variables)"
    assert not hasattr(sl, 'cmd_param_slot'), \
        "cmd_param_slot must be deleted"
    assert not hasattr(sl, 'cmd_bind_slot'), \
        "cmd_bind_slot must be deleted"
