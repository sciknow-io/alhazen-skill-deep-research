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
    """add_kefed_model builds kefed-model + subject node + variable-bearing nodes (kefed-node-variable).

    2b.2 redesign: variables are attached to a kefed-model-node (the subject node) via
    kefed-node-variable, NOT directly in kefed-model-element as ooevv-variable.
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

    # kefed-model-node in kefed-model-element (not ooevv-variable directly)
    node_rows = r(authoring_db,
                  'match $m isa kefed-model, has id "kefedm-test-1"; '
                  '(model: $m, element: $n) isa kefed-model-element; $n isa kefed-model-node; '
                  'fetch {"nid": $n.id};')
    assert node_rows, "Expected kefed-model-node in kefed-model-element"

    # variables on nodes via kefed-node-variable (not directly in kefed-model-element)
    var_rows = r(authoring_db,
                 'match $m isa kefed-model, has id "kefedm-test-1"; '
                 '(model: $m, element: $n) isa kefed-model-element; '
                 '(node: $n, variable: $v) isa kefed-node-variable; '
                 '$v isa ooevv-variable, has ooevv-variable-role $role; '
                 'fetch {"role": $role};')
    roles = sorted(x["role"] for x in var_rows)
    assert roles == ["measurement", "parameter"], f"unexpected roles: {roles}"


# ---------------------------------------------------------------------------
# Task 2b.2 tests: kefed-model-node graph authoring via real CLI verbs
# ---------------------------------------------------------------------------

def test_2b2_kefed_node_graph_authoring_roundtrip(authoring_db, capsys):
    """Task 2b.2: author a small kefed-model-node graph via the real CLI verbs.

    Graph authored:
      cmd_add_experiment -> kefed-model + element-set
      cmd_add_entity_node -> subject kefed-model-node typed by ooevv-material-entity def
      cmd_add_process -> process kefed-model-node typed by ooevv-assay def
      cmd_link_nodes -> ooevv-process-input(entity_node, process_node)
      cmd_add_variable(measurement, node=process_node)
      cmd_add_variable(parameter, node=entity_node)

    Assertions: model->nodes, node->OOEVV type, node->variables (roles),
                flow edge (entity->process), model subject.
    Data-signature traversal: from measurement var's node (assay), follow
      ooevv-process-input backwards to reach entity node, then find parameter var.
    """
    import scientific_literature as sl

    # 1. Create bundle + experiment (model + element-set)
    w(authoring_db, 'insert $b isa scilit-paper-sensemaking, has id "scsm-2b2", has name "2b2 bundle";')
    args_exp = types.SimpleNamespace(bundle="scsm-2b2", name="2b2 SIRT3 assay")
    sl.cmd_add_experiment(args_exp)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_experiment failed: {res}"
    exp_id = res["experiment_id"]

    # 2. Add subject entity node (ooevv-material-entity def, marked as model subject)
    args_entity = types.SimpleNamespace(
        experiment=exp_id, template=None,
        name="SIRT3 cell line", subject=True,
        definition="Murine hematopoietic stem cells expressing SIRT3.",
    )
    sl.cmd_add_entity_node(args_entity)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_entity_node failed: {res}"
    entity_node_id = res["entity_node_id"]

    # 3. Add process node (ooevv-assay def)
    args_proc = types.SimpleNamespace(
        experiment=exp_id, template=None,
        name="western blot", type="assay",
        parent=None,
        definition="SDS-PAGE western blot for SIRT3 protein detection.",
        long_form=None,
    )
    sl.cmd_add_process(args_proc)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_process failed: {res}"
    proc_node_id = res["process_id"]  # kefed-model-node id

    # 4. Link subject -> assay via ooevv-process-input
    args_link = types.SimpleNamespace(from_node=entity_node_id, to_node=proc_node_id, role="input")
    sl.cmd_link_nodes(args_link)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_link_nodes failed: {res}"

    # 5. Quality prerequisite + measurement variable on the assay node
    w(authoring_db,
      'insert $q isa ooevv-quality, has id "scqual-2b2", has name "SIRT3 signal", '
      'has ooevv-definition "SIRT3 band intensity from western blot.", '
      'has created-at 2026-06-30T00:00:00;')
    args_meas = types.SimpleNamespace(
        node=proc_node_id,
        name="SIRT3 band intensity", role="measurement",
        quality="scqual-2b2", scale_type="numeric",
        unit="AU", min=None, max=None, values=None,
        definition="Normalized SIRT3 band intensity (measurement role).",
        long_form=None,
    )
    sl.cmd_add_variable(args_meas)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_variable (measurement) failed: {res}"
    meas_var_id = res["variable_id"]

    # 6. Parameter variable on the subject entity node
    args_param = types.SimpleNamespace(
        node=entity_node_id,
        name="cell line genotype", role="parameter",
        quality="scqual-2b2", scale_type="nominal",
        unit=None, min=None, max=None, values=None,
        definition="Cell line genotype used as experimental subject (parameter role).",
        long_form=None,
    )
    sl.cmd_add_variable(args_param)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_variable (parameter) failed: {res}"
    param_var_id = res["variable_id"]

    # === INDEPENDENT ASSERTIONS ===

    # A. Model has 2 nodes
    node_rows = r(authoring_db,
                  f'match $m isa kefed-model, has id "{exp_id}"; '
                  f'(model: $m, element: $n) isa kefed-model-element; $n isa kefed-model-node; '
                  f'fetch {{"nid": $n.id}};')
    assert len(node_rows) == 2, f"Expected 2 nodes, got {len(node_rows)}: {node_rows}"

    # B. Entity node typed by ooevv-material-entity
    type_rows = r(authoring_db,
                  f'match $n isa kefed-model-node, has id "{entity_node_id}"; '
                  f'(node: $n, node-type: $nt) isa kefed-node-type; $nt isa ooevv-material-entity; '
                  f'fetch {{"nid": $n.id}};')
    assert type_rows, "Entity node not typed by ooevv-material-entity"

    # C. Process node typed by ooevv-assay
    type_rows = r(authoring_db,
                  f'match $n isa kefed-model-node, has id "{proc_node_id}"; '
                  f'(node: $n, node-type: $nt) isa kefed-node-type; $nt isa ooevv-assay; '
                  f'fetch {{"nid": $n.id}};')
    assert type_rows, "Process node not typed by ooevv-assay"

    # D. Entity node is the model subject (ooevv-subject)
    subj_rows = r(authoring_db,
                  f'match $m isa kefed-model, has id "{exp_id}"; '
                  f'$n isa kefed-model-node, has id "{entity_node_id}"; '
                  f'(model: $m, subject-node: $n) isa ooevv-subject; '
                  f'fetch {{"nid": $n.id}};')
    assert subj_rows, "Entity node not marked as model subject via ooevv-subject"

    # E. Flow edge: entity -> assay via ooevv-process-input
    flow_rows = r(authoring_db,
                  f'match $src isa kefed-model-node, has id "{entity_node_id}"; '
                  f'$tgt isa kefed-model-node, has id "{proc_node_id}"; '
                  f'(input-node: $src, consuming-node: $tgt) isa ooevv-process-input; '
                  f'fetch {{"src": $src.id}};')
    assert flow_rows, "ooevv-process-input flow edge not found (entity -> assay)"

    # F. Measurement variable on assay node via kefed-node-variable
    meas_rows = r(authoring_db,
                  f'match $n isa kefed-model-node, has id "{proc_node_id}"; '
                  f'$v isa ooevv-variable, has id "{meas_var_id}"; '
                  f'(node: $n, variable: $v) isa kefed-node-variable; '
                  f'$v has ooevv-variable-role $role; '
                  f'fetch {{"role": $role}};')
    assert meas_rows and meas_rows[0]["role"] == "measurement", f"Measurement var not on assay node: {meas_rows}"

    # G. Parameter variable on entity node via kefed-node-variable
    param_rows = r(authoring_db,
                   f'match $n isa kefed-model-node, has id "{entity_node_id}"; '
                   f'$v isa ooevv-variable, has id "{param_var_id}"; '
                   f'(node: $n, variable: $v) isa kefed-node-variable; '
                   f'$v has ooevv-variable-role $role; '
                   f'fetch {{"role": $role}};')
    assert param_rows and param_rows[0]["role"] == "parameter", f"Parameter var not on entity node: {param_rows}"

    # H. DATA-SIGNATURE traversal: from meas var's node (assay), traverse ooevv-process-input
    #    backwards to reach entity node, which carries the parameter var.
    sig_rows = r(authoring_db,
                 f'match '
                 f'$assay_node isa kefed-model-node, has id "{proc_node_id}"; '
                 f'$meas_v isa ooevv-variable, has id "{meas_var_id}"; '
                 f'(node: $assay_node, variable: $meas_v) isa kefed-node-variable; '
                 f'(input-node: $entity_node, consuming-node: $assay_node) isa ooevv-process-input; '
                 f'$param_v isa ooevv-variable, has id "{param_var_id}"; '
                 f'(node: $entity_node, variable: $param_v) isa kefed-node-variable; '
                 f'fetch {{"param_id": $param_v.id}};')
    assert sig_rows, (
        "Data-signature traversal FAILED: could not reach parameter var from "
        "measurement var via ooevv-process-input edge"
    )
    assert sig_rows[0]["param_id"] == param_var_id


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
    """Task 4 (revised 2b.2): drive a small bigraph through the node-based verbs:
    cmd_add_experiment / cmd_add_process (returns kefed-model-node id) /
    cmd_add_variable (--node) / cmd_bind_parameter (--node, idempotent).
    Retired: ooevv-process directly in kefed-model-element; ooevv-produced-by;
             ooevv-parameter-binding / binding-bearer role."""
    import scientific_literature as sl

    # --- prerequisites ---
    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-t4-1", has name "T4 bundle";')
    w(authoring_db,
      'insert $q isa ooevv-quality, has id "scqual-t4-1", has name "SIRT3 activity", '
      'has ooevv-definition "Enzymatic deacetylation activity of SIRT3 in mitochondria.", '
      'has created-at 2026-06-30T00:00:00;')

    # 1. add-experiment -> scilit-sensemaking-experiment + element-set
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

    # 2. add-process -> kefed-model-node (NOT ooevv-process directly in kefed-model-element)
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
    proc_node_id = res["process_id"]  # now a kefed-model-node id

    # node in kefed-model-element (kefed-model-node, NOT ooevv-process directly)
    rows = r(authoring_db,
             f'match $m isa kefed-model, has id "{exp_id}"; '
             f'$n isa kefed-model-node, has id "{proc_node_id}"; '
             f'(model: $m, element: $n) isa kefed-model-element; '
             f'fetch {{"nid": $n.id}};')
    assert rows, f"kefed-model-element not found for node {proc_node_id!r}"
    assert rows[0]["nid"] == proc_node_id

    # node typed by ooevv-assay via kefed-node-type
    rows = r(authoring_db,
             f'match $n isa kefed-model-node, has id "{proc_node_id}"; '
             f'(node: $n, node-type: $nt) isa kefed-node-type; $nt isa ooevv-assay; '
             f'fetch {{"nid": $n.id}};')
    assert rows, "Process node not typed by ooevv-assay via kefed-node-type"

    # 3. add-variable (measurement) -> kefed-node-variable on process node (NOT kefed-model-element)
    args_meas = types.SimpleNamespace(
        node=proc_node_id,
        name="SIRT3 signal", role="measurement",
        quality="scqual-t4-1", scale_type="numeric",
        unit="AU", min=None, max=None, values=None,
        definition="Normalized SIRT3 band intensity from western blot.",
        long_form=None,
    )
    sl.cmd_add_variable(args_meas)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_variable (measurement) failed: {res}"
    var_meas_id = res["variable_id"]

    # measurement variable on node via kefed-node-variable
    rows = r(authoring_db,
             f'match $n isa kefed-model-node, has id "{proc_node_id}"; '
             f'$v isa ooevv-variable, has id "{var_meas_id}"; '
             f'(node: $n, variable: $v) isa kefed-node-variable; '
             f'fetch {{"vid": $v.id}};')
    assert rows, f"kefed-node-variable not found for measurement {var_meas_id!r}"
    assert rows[0]["vid"] == var_meas_id

    # ooevv-variable-role = measurement
    rows = r(authoring_db,
             f'match $v isa ooevv-variable, has id "{var_meas_id}", has ooevv-variable-role $vr; '
             f'fetch {{"vr": $vr}};')
    assert rows and rows[0]["vr"] == "measurement", f"ooevv-variable-role mismatch: {rows}"

    # 4. add-variable (parameter) on same process node
    args_param = types.SimpleNamespace(
        node=proc_node_id,
        name="antibody concentration", role="parameter",
        quality="scqual-t4-1", scale_type="numeric",
        unit="ug/mL", min=None, max=None, values=None,
        definition="Concentration of primary antibody used in the western blot.",
        long_form=None,
    )
    sl.cmd_add_variable(args_param)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_variable (parameter) failed: {res}"
    param_id = res["variable_id"]

    # 5. bind-parameter -> kefed-node-variable (idempotent; already linked via cmd_add_variable)
    args_bind = types.SimpleNamespace(
        node=proc_node_id, parameter=param_id, target_entity=None,
    )
    sl.cmd_bind_parameter(args_bind)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_bind_parameter failed: {res}"

    # kefed-node-variable for the bound parameter (idempotent — still exactly 1 link)
    rows = r(authoring_db,
             f'match $n isa kefed-model-node, has id "{proc_node_id}"; '
             f'$v isa ooevv-variable, has id "{param_id}"; '
             f'(node: $n, variable: $v) isa kefed-node-variable; '
             f'fetch {{"nid": $n.id}};')
    assert rows, "kefed-node-variable for bound parameter not found"
    assert rows[0]["nid"] == proc_node_id


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


# ---------------------------------------------------------------------------
# Task 6 tests: iteration-aware investigation/phase authoring
#   cmd_create_investigation -> seeds scilit-iteration index 1 via scilit-investigation-iteration
#   cmd_record_phase -> resolve-or-create scilit-iteration, link stage via scilit-iteration-stage
#   NO scilit-investigation-phasing or scilit-iteration-number in the code paths
# ---------------------------------------------------------------------------

def test_t6_create_investigation_seeds_iteration1(authoring_db, capsys):
    """cmd_create_investigation must seed a scilit-iteration with index 1 linked via
    scilit-investigation-iteration so every investigation starts with iteration 1."""
    import scientific_literature as sl

    # prerequisite: a corpus to hang the investigation on
    w(authoring_db,
      'insert $c isa scilit-corpus, has id "sclit-corpus-t6", has name "T6 test corpus";')

    args = types.SimpleNamespace(
        type="corpus",
        collection="sclit-corpus-t6",
        name="T6 iteration seed test",
        purpose="Verify iteration 1 is seeded on creation.",
        status=None,
    )
    sl.cmd_create_investigation(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["success"] is True, f"cmd_create_investigation failed: {result}"
    inv_id = result["id"]

    # scilit-iteration with index 1 must be linked to the investigation
    rows = r(authoring_db,
             f'match $inv isa scilit-investigation, has id "{inv_id}"; '
             f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration; '
             f'$it isa scilit-iteration, has scilit-iteration-index $idx; '
             f'fetch {{"idx": $idx}};')
    assert rows, f"No scilit-iteration linked to investigation {inv_id!r} via scilit-investigation-iteration"
    assert rows[0]["idx"] == 1, f"Expected iteration index 1, got {rows[0]['idx']}"


def test_t6_record_phase_via_iteration_path(authoring_db, capsys):
    """cmd_record_phase must create/find a scilit-iteration (by index) and link the
    scilit-investigation-phase via scilit-iteration-stage (NOT scilit-investigation-phasing)."""
    import scientific_literature as sl

    # setup: corpus + investigation (iteration 1 seeded by cmd_create_investigation)
    w(authoring_db,
      'insert $c isa scilit-corpus, has id "sclit-corpus-t6b", has name "T6b corpus";')

    args_inv = types.SimpleNamespace(
        type="corpus",
        collection="sclit-corpus-t6b",
        name="T6b phase authoring test",
        purpose="Verify phase is wired via iteration.",
        status=None,
    )
    sl.cmd_create_investigation(args_inv)
    captured = capsys.readouterr()
    inv_id = json.loads(captured.out)["id"]

    # call cmd_record_phase with --iteration 1 --phase discovery
    args_phase = types.SimpleNamespace(
        investigation=inv_id,
        phase="discovery",
        iteration=1,
        content="Initial discovery findings for iteration 1.",
        status=None,
    )
    sl.cmd_record_phase(args_phase)
    captured = capsys.readouterr()
    phase_result = json.loads(captured.out)
    assert phase_result["success"] is True, f"cmd_record_phase failed: {phase_result}"
    ph_id = phase_result["phase_note_id"]

    # assert: investigation -> scilit-iteration(index 1) -> scilit-iteration-stage -> phase("discovery")
    rows = r(authoring_db,
             f'match $inv isa scilit-investigation, has id "{inv_id}"; '
             f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration; '
             f'$it isa scilit-iteration, has scilit-iteration-index $idx; '
             f'(iteration: $it, stage: $ph) isa scilit-iteration-stage; '
             f'$ph isa scilit-investigation-phase, has scilit-phase $stage; '
             f'fetch {{"idx": $idx, "stage": $stage, "ph_id": $ph.id}};')
    assert rows, "investigation -> scilit-iteration -> scilit-iteration-stage -> phase chain not found"
    assert rows[0]["idx"] == 1
    assert rows[0]["stage"] == "discovery"
    assert rows[0]["ph_id"] == ph_id

    # assert: upsert (call again with different content, same phase)
    args_phase2 = types.SimpleNamespace(
        investigation=inv_id,
        phase="discovery",
        iteration=1,
        content="Updated discovery findings.",
        status=None,
    )
    sl.cmd_record_phase(args_phase2)
    captured = capsys.readouterr()
    phase_result2 = json.loads(captured.out)
    assert phase_result2["success"] is True
    assert phase_result2["phase_note_id"] == ph_id, "Upsert must return same phase note id"
    assert phase_result2["action"] == "updated", f"Expected 'updated', got {phase_result2['action']!r}"

    # assert updated content is stored
    content_rows = r(authoring_db,
                     f'match $ph isa scilit-investigation-phase, has id "{ph_id}", '
                     f'has content $c; fetch {{"c": $c}};')
    assert content_rows, "No content found after upsert"
    assert "Updated" in content_rows[0]["c"], f"Content not updated: {content_rows[0]['c']!r}"


# ---------------------------------------------------------------------------
# Task 5 tests: observation/bundle authoring rework
#   cmd_add_observation -> scilit-observation threaded via scilit-sensemaking-observation;
#                          NO kefed-observed-via / kefed-model / kefed-variable created here
#   cmd_create_bundle   -> bundle threaded under sensemaking stage of iteration 1
# ---------------------------------------------------------------------------

def test_t5_cmd_add_observation_simple(authoring_db, capsys):
    """cmd_add_observation must insert a scilit-observation (with knowledge-level + bio-scale)
    threaded under the bundle via scilit-sensemaking-observation, and must NOT create any
    kefed-model linked via the retired kefed-observed-via relation."""
    import scientific_literature as sl

    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-t5-obs", has name "T5 obs bundle";')

    # Pass experiment_type and variables — the OLD code would try to insert retired
    # kefed-variable/kefed-element types, which fail.  The NEW handler must ignore these
    # args and just insert the observation note.
    args = types.SimpleNamespace(
        bundle="scsm-t5-obs",
        statement="SIRT3 deacetylase activity declines with HSC aging.",
        name=None,
        knowledge_level="association",
        bio_scale="cellular",
        experiment_type="western blot",
        variables=json.dumps([{"name": "SIRT3 signal", "role": "measurement"}]),
    )
    sl.cmd_add_observation(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["success"] is True, f"cmd_add_observation failed: {result}"
    obs_id = result["observation_id"]

    # scilit-observation must exist, threaded under the bundle
    rows = r(authoring_db,
             f'match $b isa scilit-paper-sensemaking, has id "scsm-t5-obs"; '
             f'$o isa scilit-observation, has id "{obs_id}"; '
             f'(sensemaking: $b, observation: $o) isa scilit-sensemaking-observation; '
             f'fetch {{"id": $o.id}};')
    assert rows, f"scilit-observation {obs_id!r} not threaded via scilit-sensemaking-observation"
    assert rows[0]["id"] == obs_id

    # observation must carry knowledge-level and bio-scale
    attr_rows = r(authoring_db,
                  f'match $o isa scilit-observation, has id "{obs_id}", '
                  f'has scilit-knowledge-level $kl, has scilit-bio-scale $bs; '
                  f'fetch {{"kl": $kl, "bs": $bs}};')
    assert attr_rows, "scilit-knowledge-level / scilit-bio-scale missing on observation"
    assert attr_rows[0]["kl"] == "association"
    assert attr_rows[0]["bs"] == "cellular"

    # NO kefed-model must be linked via the retired kefed-observed-via
    # (that relation is gone from schema; verify no kefed-model was created at all in this tx)
    model_rows = r(authoring_db,
                   f'match $o isa scilit-observation, has id "{obs_id}"; '
                   f'$m isa kefed-model; '
                   f'(sensemaking: $b, experiment: $m) isa scilit-sensemaking-experiment; '
                   f'(sensemaking: $b, observation: $o) isa scilit-sensemaking-observation; '
                   f'fetch {{"mid": $m.id}};')
    assert not model_rows, (
        "cmd_add_observation must NOT create a kefed-model under the bundle — "
        "KEfED frame is authored separately via cmd_add_experiment"
    )


# ---------------------------------------------------------------------------
# Task 7 tests: read model rework (bundle/experiment/variable)
#   _load_bundle      -> no kefed_frame per observation; reads experiments via
#                        scilit-sensemaking-experiment; fixes scilit-claim hinge
#   _load_experiment  -> kefed-model-element(model,element); binding-bearer;
#                        produced-variable/producing-process; no container_type param
#   _var_brief        -> ooevv-variable; ooevv-variable-role; no slot block
#   _load_experiments -> scilit-sensemaking-experiment (not ooevv-bundle-experiment)
#   _load_instances   -> scilit-sensemaking-experiment (not ooevv-bundle-experiment)
# ---------------------------------------------------------------------------

def test_t7_load_bundle_experiment_variable(authoring_db, capsys):
    """_load_bundle and _load_experiment return the right dicts on the clean schema.

    Authoring path (Tasks 4-5):
      bundle -> scilit-sensemaking-observation -> observation
      bundle -> scilit-sensemaking-experiment  -> kefed-model
                kefed-model-element             -> process + variable
                ooevv-produced-by               -> produced-variable/producing-process
                ooevv-parameter-binding         -> binding-bearer/bound-parameter

    Assert:
      - bundle["observations"] has the observation (NO kefed_frame key)
      - bundle["experiments"]  has the kefed-model entry
      - _load_experiment returns processes with parameters and measurements (no slot)
      - _var_brief returns ooevv-variable-role, no 'slot' key
    """
    import scientific_literature as sl
    from typedb.driver import TransactionType

    # --- Build fixture data ---
    # 1. bundle
    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-t7-1", has name "T7 bundle";')

    # 2. observation threaded under bundle
    import types as _types
    args_obs = _types.SimpleNamespace(
        bundle="scsm-t7-1",
        statement="SIRT3 is enriched in young HSCs.",
        name=None,
        knowledge_level="association",
        bio_scale="cellular",
        experiment_type=None,
        variables=None,
    )
    sl.cmd_add_observation(args_obs)
    obs_id = json.loads(capsys.readouterr().out)["observation_id"]

    # 3. kefed-model experiment threaded under bundle
    args_exp = _types.SimpleNamespace(bundle="scsm-t7-1", name="T7 western blot")
    sl.cmd_add_experiment(args_exp)
    exp_id = json.loads(capsys.readouterr().out)["experiment_id"]

    # 4. process in the model
    args_proc = _types.SimpleNamespace(
        experiment=exp_id, template=None,
        name="T7 assay step", type="assay",
        parent=None, definition="A test assay.", long_form=None,
    )
    sl.cmd_add_process(args_proc)
    proc_id = json.loads(capsys.readouterr().out)["process_id"]

    # 5. measurement variable on the process node (node-based, no ooevv-produced-by)
    w(authoring_db,
      'insert $q isa ooevv-quality, has id "scqual-t7-1", has name "signal", '
      'has ooevv-definition "test signal", has created-at 2026-06-30T00:00:00;')
    args_meas = _types.SimpleNamespace(
        node=proc_id,  # proc_id is now a kefed-model-node id
        name="SIRT3 band", role="measurement",
        quality="scqual-t7-1", scale_type="numeric",
        unit="AU", min=None, max=None, values=None,
        definition="Normalized SIRT3 band intensity from western blot.",
        long_form=None,
    )
    sl.cmd_add_variable(args_meas)
    meas_id = json.loads(capsys.readouterr().out)["variable_id"]

    # 6. parameter variable on the process node (node-based, no ooevv-parameter-binding)
    args_param = _types.SimpleNamespace(
        node=proc_id,
        name="antibody conc", role="parameter",
        quality="scqual-t7-1", scale_type="numeric",
        unit="ug/mL", min=None, max=None, values=None,
        definition="Concentration of primary antibody used in western blot.",
        long_form=None,
    )
    sl.cmd_add_variable(args_param)
    param_id = json.loads(capsys.readouterr().out)["variable_id"]

    args_bind = _types.SimpleNamespace(
        node=proc_id, parameter=param_id, target_entity=None,
    )
    sl.cmd_bind_parameter(args_bind)
    capsys.readouterr()  # discard bind output

    # --- READ via _load_bundle + _load_experiment ---
    driver = authoring_db
    with driver.transaction(sl.TYPEDB_DATABASE, TransactionType.READ) as tx:
        bundle = sl._load_bundle(tx, "scsm-t7-1")

    # bundle must have the observation (no kefed_frame)
    assert bundle is not None, "_load_bundle returned None"
    obs_list = bundle.get("observations", [])
    assert len(obs_list) == 1, f"Expected 1 observation, got {len(obs_list)}"
    obs = obs_list[0]
    assert obs["id"] == obs_id
    assert "kefed_frame" not in obs, "observation must NOT carry kefed_frame"
    assert obs.get("knowledge_level") == "association"

    # bundle must have the experiment
    exp_list = bundle.get("experiments", [])
    assert len(exp_list) == 1, f"Expected 1 experiment, got {len(exp_list)}: {exp_list}"
    assert exp_list[0]["id"] == exp_id

    # experiment detail
    with driver.transaction(sl.TYPEDB_DATABASE, TransactionType.READ) as tx:
        exp_detail = sl._load_experiment(tx, exp_id)

    procs = exp_detail.get("processes", [])
    assert len(procs) == 1, f"Expected 1 process, got {len(procs)}"
    p = procs[0]
    assert p["id"] == proc_id

    # process must have measurement (no slot key on var_brief)
    meas_list = p.get("measurements", [])
    assert len(meas_list) == 1, f"Expected 1 measurement, got {meas_list}"
    m = meas_list[0]
    assert m["id"] == meas_id
    assert "slot" not in m, "variable must NOT have slot key"
    assert m.get("role") == "measurement"

    # process must have bound parameter
    param_list = p.get("parameters", [])
    assert len(param_list) == 1, f"Expected 1 parameter, got {param_list}"
    pp = param_list[0]
    assert pp["id"] == param_id
    assert "slot" not in pp, "parameter must NOT have slot key"
    assert pp.get("role") == "parameter"


def test_t5_cmd_create_bundle_iteration_wiring(authoring_db, capsys):
    """cmd_create_bundle must thread the bundle under the sensemaking stage of iteration 1
    via: investigation -> scilit-iteration(idx=1) -> scilit-iteration-stage ->
         scilit-investigation-phase(sensemaking) -> scilit-phase-sensemaking -> bundle."""
    import scientific_literature as sl

    # prerequisites: corpus, investigation (seeds iteration 1), paper
    w(authoring_db,
      'insert $c isa scilit-corpus, has id "sclit-corpus-t5b", has name "T5b corpus";')
    args_inv = types.SimpleNamespace(
        type="corpus",
        collection="sclit-corpus-t5b",
        name="T5b bundle wiring test",
        purpose="Verify bundle wired under sensemaking of iteration 1.",
        status=None,
    )
    sl.cmd_create_investigation(args_inv)
    captured = capsys.readouterr()
    inv_id = json.loads(captured.out)["id"]

    w(authoring_db,
      'insert $p isa scilit-paper, has id "scilit-paper-t5b-001", has name "Test paper T5b";')

    args_bundle = types.SimpleNamespace(
        investigation=inv_id,
        paper="scilit-paper-t5b-001",
        name="T5b sensemaking bundle",
        iteration=1,
    )
    sl.cmd_create_bundle(args_bundle)
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["success"] is True, f"cmd_create_bundle failed: {result}"
    bundle_id = result["bundle_id"]

    # bundle must be reachable via the full iteration chain at sensemaking phase
    rows = r(authoring_db,
             f'match $inv isa scilit-investigation, has id "{inv_id}"; '
             f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration; '
             f'$it isa scilit-iteration, has scilit-iteration-index $idx; '
             f'(iteration: $it, stage: $ph) isa scilit-iteration-stage; '
             f'$ph isa scilit-investigation-phase, has scilit-phase $stage; '
             f'(phase: $ph, sensemaking: $b) isa scilit-phase-sensemaking; '
             f'$b isa scilit-paper-sensemaking, has id "{bundle_id}"; '
             f'fetch {{"idx": $idx, "stage": $stage, "bid": $b.id}};')
    assert rows, "bundle not reachable via investigation -> iteration -> stage -> phase -> bundle"
    assert rows[0]["idx"] == 1, f"Expected iteration index 1, got {rows[0]['idx']}"
    assert rows[0]["stage"] == "sensemaking", f"Expected phase 'sensemaking', got {rows[0]['stage']!r}"
    assert rows[0]["bid"] == bundle_id


# ---------------------------------------------------------------------------
# Task 8 tests: _load_template / _load_instance / _load_investigation (clean schema)
# ---------------------------------------------------------------------------

def test_t8_load_template_no_slots(authoring_db, capsys):
    """_load_template must return shape from kefed-model+state=template; NO 'slots' key;
    'variables' gathered via model->node->kefed-node-variable; 'graph' from _load_experiment."""
    import types as _types
    import scientific_literature as sl
    from typedb.driver import TransactionType

    # Prerequisites: a quality for cmd_add_variable
    w(authoring_db,
      'insert $q isa ooevv-quality, has id "scqual-t8-1", has name "T8 signal", '
      'has ooevv-definition "Test quality for Task 8.", has created-at 2026-06-30T00:00:00;')

    # 1. Create a template (kefed-model with state "template") via cmd_ensure_template
    args_tpl = _types.SimpleNamespace(name="T8 western blot template")
    sl.cmd_ensure_template(args_tpl)
    tid = json.loads(capsys.readouterr().out)["template_id"]

    # 2. Add a process node to the template (needed so we have a node to attach var to)
    args_proc = _types.SimpleNamespace(
        experiment=None, template=tid,
        name="T8 assay step", type="assay",
        parent=None,
        definition="Test assay step for T8 template.",
        long_form=None,
    )
    sl.cmd_add_process(args_proc)
    proc_node_id = json.loads(capsys.readouterr().out)["process_id"]

    # 3. Add a parameter variable to the process node (via kefed-node-variable)
    args_var = _types.SimpleNamespace(
        node=proc_node_id,
        name="T8 antibody conc", role="parameter",
        quality="scqual-t8-1", scale_type="numeric",
        unit="ug/mL", min=None, max=None, values=None,
        definition="Concentration of primary antibody in T8 test.",
        long_form=None,
    )
    sl.cmd_add_variable(args_var)
    var_id = json.loads(capsys.readouterr().out)["variable_id"]

    # 4. Call _load_template -> assert shape
    driver = authoring_db
    with driver.transaction(sl.TYPEDB_DATABASE, TransactionType.READ) as tx:
        tpl = sl._load_template(tx, tid)

    assert tpl is not None, "_load_template returned None"
    assert tpl["id"] == tid
    assert "slots" not in tpl, "_load_template must NOT carry a 'slots' key (retired)"
    assert "variables" in tpl, "_load_template must carry a 'variables' list"
    assert len(tpl["variables"]) == 1, f"Expected 1 variable, got {tpl['variables']}"
    assert tpl["variables"][0]["id"] == var_id
    assert tpl["variables"][0].get("role") == "parameter"
    assert "graph" in tpl, "_load_template must carry a 'graph' key"


def test_t8_load_instance_no_bindings(authoring_db, capsys):
    """_load_instance must return shape from kefed-instance via model role; NO 'bindings' key;
    'data' rows with cells using ooevv-variable-role (not kefed-variable-role)."""
    import types as _types
    import scientific_literature as sl
    from typedb.driver import TransactionType

    # Prerequisites: quality, bundle (sensemaking), template with a variable
    w(authoring_db,
      'insert $q isa ooevv-quality, has id "scqual-t8b-1", has name "T8b signal", '
      'has ooevv-definition "Test quality for Task 8b.", has created-at 2026-06-30T00:00:00;')
    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-t8b-1", has name "T8b bundle";')

    # Template
    args_tpl = _types.SimpleNamespace(name="T8b template")
    sl.cmd_ensure_template(args_tpl)
    tid = json.loads(capsys.readouterr().out)["template_id"]

    # Add a process node to the template (needed for variable attachment)
    args_proc = _types.SimpleNamespace(
        experiment=None, template=tid,
        name="T8b assay step", type="assay",
        parent=None,
        definition="Test assay step for T8b template.",
        long_form=None,
    )
    sl.cmd_add_process(args_proc)
    proc_node_id_t8b = json.loads(capsys.readouterr().out)["process_id"]

    # Variable on the template process node (measurement via kefed-node-variable)
    args_var = _types.SimpleNamespace(
        node=proc_node_id_t8b,
        name="T8b measurement", role="measurement",
        quality="scqual-t8b-1", scale_type="numeric",
        unit="AU", min=None, max=None, values=None,
        definition="A measurement variable for T8b test.",
        long_form=None,
    )
    sl.cmd_add_variable(args_var)
    var_id = json.loads(capsys.readouterr().out)["variable_id"]

    # Instantiate template under bundle
    args_inst = _types.SimpleNamespace(bundle="scsm-t8b-1", template=tid, name="T8b run 1")
    sl.cmd_instantiate_template(args_inst)
    iid = json.loads(capsys.readouterr().out)["instance_id"]

    # Add a datum row with one cell
    args_datum = _types.SimpleNamespace(
        instance=iid,
        cells=json.dumps([{"variable": var_id, "value": "42", "number": 42.0}]),
        observation=None,
        gloss=None,
    )
    sl.cmd_add_datum(args_datum)
    capsys.readouterr()  # discard

    # Call _load_instance -> assert shape
    driver = authoring_db
    with driver.transaction(sl.TYPEDB_DATABASE, TransactionType.READ) as tx:
        inst = sl._load_instance(tx, iid)

    assert inst is not None, "_load_instance returned None"
    assert inst["id"] == iid
    assert "bindings" not in inst, "_load_instance must NOT carry a 'bindings' key (retired)"
    assert "template" in inst, "_load_instance must carry a 'template' key"
    assert inst["template"]["id"] == tid
    assert "data" in inst, "_load_instance must carry a 'data' list"
    assert len(inst["data"]) == 1, f"Expected 1 data row, got {len(inst['data'])}"
    cells = inst["data"][0]["cells"]
    assert len(cells) == 1, f"Expected 1 cell, got {len(cells)}"
    assert cells[0]["variable"] == var_id
    assert cells[0]["value"] == "42"
    assert cells[0].get("role") == "measurement"


def test_t8_load_investigation_iteration_phases(authoring_db, capsys):
    """_load_investigation phases must be traversed via scilit-investigation-iteration ->
    scilit-iteration -> scilit-iteration-stage, not the retired scilit-investigation-phasing.
    Each phase dict carries 'iteration' from scilit-iteration-index."""
    import types as _types
    import scientific_literature as sl
    from typedb.driver import TransactionType

    # 1. Create a corpus investigation (seeds iteration 1 automatically)
    w(authoring_db,
      'insert $c isa scilit-corpus, has id "sclit-corpus-t8c", has name "T8c corpus";')
    args_inv = _types.SimpleNamespace(
        type="corpus",
        collection="sclit-corpus-t8c",
        name="T8c investigation",
        purpose="Test _load_investigation iteration phases.",
        status=None,
    )
    sl.cmd_create_investigation(args_inv)
    inv_id = json.loads(capsys.readouterr().out)["id"]

    # 2. Record a discovery phase at iteration 1
    args_phase = _types.SimpleNamespace(
        investigation=inv_id,
        phase="discovery",
        content="Initial scoping for T8c.",
        iteration=1,
        status=None,
    )
    sl.cmd_record_phase(args_phase)
    capsys.readouterr()

    # 3. Call _load_investigation -> assert phases carry iteration index
    driver = authoring_db
    with driver.transaction(sl.TYPEDB_DATABASE, TransactionType.READ) as tx:
        inv = sl._load_investigation(tx, inv_id)

    assert inv is not None, "_load_investigation returned None"
    phases = inv.get("phases", [])
    assert phases, "_load_investigation must return at least one phase"
    # The discovery phase must carry iteration == 1
    disc = [p for p in phases if p.get("phase") == "discovery"]
    assert disc, f"Expected a 'discovery' phase; got phases: {phases}"
    assert disc[0].get("iteration") == 1, (
        f"Expected iteration=1 on discovery phase, got {disc[0].get('iteration')!r}"
    )


# ---------------------------------------------------------------------------
# Task 3a.2: element-set relation authoring + shared-set reuse
# ---------------------------------------------------------------------------

def test_cmd_add_experiment_elementset_relation(authoring_db, capsys):
    """cmd_add_experiment links the kefed-model to an ooevv-element-set via
    kefed-model-elementset relation (not eset-{id} naming convention),
    and persists definition/long-form on the kefed-model."""
    import scientific_literature as sl

    w(authoring_db, 'insert $b isa scilit-paper-sensemaking, has id "scsm-eset-a", has name "eset test bundle";')
    args = types.SimpleNamespace(
        bundle="scsm-eset-a",
        name="SIRT3 western blot experiment",
        definition="An experiment measuring SIRT3 protein levels via western blot.",
        long_form="SIRT3 protein expression assay",
        element_set=None,
    )
    sl.cmd_add_experiment(args)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_experiment failed: {res}"
    exp_id = res["experiment_id"]
    eset_id = res["element_set_id"]

    # element-set id must NOT be eset-<exp_id>
    assert eset_id != f"eset-{exp_id}", "element-set id must not use eset-{id} naming convention"

    # kefed-model is linked to element-set via kefed-model-elementset relation
    rel_rows = r(authoring_db,
                 f'match $m isa kefed-model, has id "{exp_id}"; '
                 f'(model: $m, element-set: $es) isa kefed-model-elementset; '
                 f'fetch {{"esid": $es.id}};')
    assert rel_rows, "kefed-model-elementset relation not found"
    assert rel_rows[0]["esid"] == eset_id

    # kefed-model owns definition and long-form
    def_rows = r(authoring_db,
                 f'match $m isa kefed-model, has id "{exp_id}", '
                 f'has ooevv-definition $d, has ooevv-long-form $lf; '
                 f'fetch {{"d": $d, "lf": $lf}};')
    assert def_rows, "kefed-model does not own definition/long-form"
    assert "SIRT3 protein levels" in def_rows[0]["d"]
    assert "SIRT3 protein expression" in def_rows[0]["lf"]


def test_cmd_ensure_template_elementset_relation(authoring_db, capsys):
    """cmd_ensure_template creates an element-set linked via kefed-model-elementset
    relation and persists definition/long-form on the kefed-model."""
    import scientific_literature as sl

    args = types.SimpleNamespace(
        name="qPCR expression profiling",
        definition="A template for quantifying gene expression via qPCR.",
        long_form="Quantitative polymerase chain reaction expression profiling",
        element_set=None,
    )
    sl.cmd_ensure_template(args)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_ensure_template failed: {res}"
    tpl_id = res["template_id"]
    assert res["reused"] is False

    # kefed-model-elementset relation exists
    rel_rows = r(authoring_db,
                 f'match $t isa kefed-model, has id "{tpl_id}"; '
                 f'(model: $t, element-set: $es) isa kefed-model-elementset; '
                 f'fetch {{"esid": $es.id}};')
    assert rel_rows, "kefed-model-elementset relation not found for template"

    # element-set id must NOT be eset-<tpl_id>
    assert rel_rows[0]["esid"] != f"eset-{tpl_id}"

    # kefed-model owns definition and long-form
    def_rows = r(authoring_db,
                 f'match $t isa kefed-model, has id "{tpl_id}", '
                 f'has ooevv-definition $d, has ooevv-long-form $lf; '
                 f'fetch {{"d": $d, "lf": $lf}};')
    assert def_rows, "kefed-model does not own definition/long-form"
    assert "qPCR" in def_rows[0]["d"]


def test_shared_elementset_def_reuse(authoring_db, capsys):
    """Model A creates an element-set and a process def in it.
    Model B shares A's element-set via --element-set.  When model B adds
    a process with the same type name, the existing def is REUSED (same id)
    — not duplicated — because both share the element-set."""
    import scientific_literature as sl

    # Create model A (an experiment) with its own element-set
    w(authoring_db, 'insert $b isa scilit-paper-sensemaking, has id "scsm-share-a", has name "share bundle A";')
    args_a = types.SimpleNamespace(
        bundle="scsm-share-a",
        name="Model A",
        definition="Model A definition.",
        long_form=None,
        element_set=None,
    )
    sl.cmd_add_experiment(args_a)
    out = capsys.readouterr().out
    res_a = json.loads(out)
    assert res_a["success"] is True
    exp_a_id = res_a["experiment_id"]
    eset_a_id = res_a["element_set_id"]

    # Add process "western blot" to model A — creates a def in A's element-set
    args_proc_a = types.SimpleNamespace(
        experiment=exp_a_id, template=None,
        name="western blot", type="assay",
        parent=None,
        definition="SDS-PAGE western blot for protein detection.",
        long_form=None,
    )
    sl.cmd_add_process(args_proc_a)
    out = capsys.readouterr().out
    res_proc_a = json.loads(out)
    assert res_proc_a["success"] is True
    proc_def_a_id = res_proc_a["process_def_id"]

    # Create model B (a template), REUSING model A's element-set via --element-set
    args_b = types.SimpleNamespace(
        name="Model B",
        definition="Model B reuses A's element-set.",
        long_form=None,
        element_set=eset_a_id,
    )
    sl.cmd_ensure_template(args_b)
    out = capsys.readouterr().out
    res_b = json.loads(out)
    assert res_b["success"] is True, f"cmd_ensure_template (model B) failed: {res_b}"
    tpl_b_id = res_b["template_id"]
    assert res_b["reused"] is False

    # Verify model B is linked to the SAME element-set as model A
    b_eset_rows = r(authoring_db,
                    f'match $m isa kefed-model, has id "{tpl_b_id}"; '
                    f'(model: $m, element-set: $es) isa kefed-model-elementset; '
                    f'fetch {{"esid": $es.id}};')
    assert b_eset_rows, "Model B not linked to any element-set"
    assert b_eset_rows[0]["esid"] == eset_a_id, (
        f"Model B linked to {b_eset_rows[0]['esid']!r}, expected {eset_a_id!r}")

    # Add process "western blot" to model B — must REUSE the existing def from shared element-set
    args_proc_b = types.SimpleNamespace(
        experiment=None, template=tpl_b_id,
        name="western blot", type="assay",
        parent=None,
        definition="SDS-PAGE western blot for protein detection.",
        long_form=None,
    )
    sl.cmd_add_process(args_proc_b)
    out = capsys.readouterr().out
    res_proc_b = json.loads(out)
    assert res_proc_b["success"] is True
    proc_def_b_id = res_proc_b["process_def_id"]

    # Same def id — reused from the shared element-set
    assert proc_def_b_id == proc_def_a_id, (
        f"Def not reused: model A used {proc_def_a_id!r}, model B used {proc_def_b_id!r}. "
        "Sharing element-set should have found the existing def.")

    # Only ONE def for 'western blot' in the shared element-set
    def_rows = r(authoring_db,
                 f'match $es isa ooevv-element-set, has id "{eset_a_id}"; '
                 f'(element-set: $es, element: $p) isa ooevv-set-element; '
                 f'$p isa ooevv-assay, has name "western blot"; '
                 f'fetch {{"pid": $p.id}};')
    assert len(def_rows) == 1, f"Expected 1 def for 'western blot', found {len(def_rows)}: {def_rows}"
    assert def_rows[0]["pid"] == proc_def_a_id


# ---------------------------------------------------------------------------
# Task 3a.3 tests: data-signature read verb + add-datum validation
# ---------------------------------------------------------------------------

def test_data_signature_traversal(authoring_db, capsys):
    """_data_signature + cmd_show_data_signature return the correct index for a measurement.

    Graph: subject entity node (parameter "genotype") -[ooevv-process-input]->
           assay node (measurement "expression").
    The data signature for "expression" must include "genotype" as an index parameter.
    """
    import pytest
    import scientific_literature as sl
    from typedb.driver import TransactionType

    # 1. Create experiment (kefed-model + element-set) under a bundle
    w(authoring_db, 'insert $b isa scilit-paper-sensemaking, has id "scsm-datasig-1", has name "datasig bundle";')
    args_exp = types.SimpleNamespace(
        bundle="scsm-datasig-1",
        name="Data signature test experiment",
        definition="Test experiment for data signature traversal.",
        long_form=None,
        element_set=None,
    )
    sl.cmd_add_experiment(args_exp)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_experiment failed: {res}"
    exp_id = res["experiment_id"]

    # 2. Add subject entity node
    args_entity = types.SimpleNamespace(
        experiment=exp_id, template=None,
        name="Cell line", subject=True,
        definition="Subject cell line entity.",
    )
    sl.cmd_add_entity_node(args_entity)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_entity_node failed: {res}"
    entity_node_id = res["entity_node_id"]

    # 3. Add assay process node
    args_proc = types.SimpleNamespace(
        experiment=exp_id, template=None,
        name="gene expression assay", type="assay",
        parent=None,
        definition="Assay measuring gene expression levels.",
        long_form=None,
    )
    sl.cmd_add_process(args_proc)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_process failed: {res}"
    proc_node_id = res["process_id"]

    # 4. Link entity -> assay via ooevv-process-input
    args_link = types.SimpleNamespace(from_node=entity_node_id, to_node=proc_node_id, role="input")
    sl.cmd_link_nodes(args_link)
    out = capsys.readouterr().out
    assert json.loads(out)["success"] is True, "cmd_link_nodes failed"

    # 5. Quality prerequisite for variables
    w(authoring_db,
      'insert $q isa ooevv-quality, has id "scqual-datasig-1", has name "gene expression signal", '
      'has ooevv-definition "mRNA expression level.", has created-at 2026-06-30T00:00:00;')

    # 6. Parameter variable "genotype" on entity node
    args_param = types.SimpleNamespace(
        node=entity_node_id,
        name="genotype", role="parameter",
        quality="scqual-datasig-1", scale_type="nominal",
        unit=None, min=None, max=None, values=None,
        definition="Cell line genotype (parameter).",
        long_form=None,
    )
    sl.cmd_add_variable(args_param)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_variable (parameter) failed: {res}"
    param_var_id = res["variable_id"]

    # 7. Measurement variable "expression" on assay node
    args_meas = types.SimpleNamespace(
        node=proc_node_id,
        name="expression", role="measurement",
        quality="scqual-datasig-1", scale_type="numeric",
        unit="RPKM", min=None, max=None, values=None,
        definition="Gene expression level (measurement).",
        long_form=None,
    )
    sl.cmd_add_variable(args_meas)
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["success"] is True, f"cmd_add_variable (measurement) failed: {res}"
    meas_var_id = res["variable_id"]

    # === TEST _data_signature ===
    with authoring_db.transaction(sl.TYPEDB_DATABASE, TransactionType.READ) as tx:
        sig = sl._data_signature(tx, exp_id)

    assert meas_var_id in sig, f"measurement var {meas_var_id!r} missing from signature: {sig}"
    meas_entry = sig[meas_var_id]
    assert meas_entry["name"] == "expression"
    index_ids = [item["id"] for item in meas_entry["index"]]
    assert param_var_id in index_ids, (
        f"parameter var {param_var_id!r} ('genotype') not in measurement index: {meas_entry['index']}"
    )
    genotype_entry = next(item for item in meas_entry["index"] if item["id"] == param_var_id)
    assert genotype_entry["name"] == "genotype"
    assert genotype_entry["role"] == "parameter"

    # === TEST cmd_show_data_signature ===
    args_sig = types.SimpleNamespace(model=exp_id)
    sl.cmd_show_data_signature(args_sig)
    out = capsys.readouterr().out
    sig_json = json.loads(out)
    assert meas_var_id in sig_json, f"measurement var missing from cmd_show_data_signature output"
    assert any(item["id"] == param_var_id for item in sig_json[meas_var_id]["index"])


def test_add_datum_validation_against_model(authoring_db, capsys):
    """cmd_add_datum validates --cells variable ids against the instance's model.

    Case (a): instance WITHOUT ooevv-instance-of -> validation skipped (backward compat).
    Case (b): instance WITH ooevv-instance-of ->
        - unknown variable id -> success=false, error contains variable id
        - valid model variable id -> success=true
    """
    import pytest
    import scientific_literature as sl

    # === Case (a): instance without model link — validation skipped ===
    w(authoring_db,
      'insert $v isa ooevv-variable, has id "oov-nomodel-v1", has name "free var", '
      'has ooevv-variable-role "measurement";')
    w(authoring_db,
      'insert $i isa kefed-instance, has id "scinst-nomodel-1", has name "no model instance";')
    args_nomodel = types.SimpleNamespace(
        instance="scinst-nomodel-1",
        cells=json.dumps([{"variable": "oov-nomodel-v1", "value": "x"}]),
        observation=None, gloss=None,
    )
    sl.cmd_add_datum(args_nomodel)
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result["success"] is True, f"No-model instance should skip validation: {result}"

    # === Case (b): instance WITH ooevv-instance-of ===

    # Build minimal model (experiment) with one process node + one measurement variable
    w(authoring_db,
      'insert $b isa scilit-paper-sensemaking, has id "scsm-valtest-1", has name "validation bundle";')
    args_exp = types.SimpleNamespace(
        bundle="scsm-valtest-1",
        name="validation test experiment",
        definition="Test experiment for add-datum validation.",
        long_form=None,
        element_set=None,
    )
    sl.cmd_add_experiment(args_exp)
    model_id = json.loads(capsys.readouterr().out)["experiment_id"]

    args_proc = types.SimpleNamespace(
        experiment=model_id, template=None,
        name="test assay", type="assay",
        parent=None,
        definition="A test assay for validation.",
        long_form=None,
    )
    sl.cmd_add_process(args_proc)
    proc_node_id = json.loads(capsys.readouterr().out)["process_id"]

    w(authoring_db,
      'insert $q isa ooevv-quality, has id "scqual-valtest-1", has name "val signal", '
      'has ooevv-definition "Test signal for validation.", has created-at 2026-06-30T00:00:00;')

    args_meas_v = types.SimpleNamespace(
        node=proc_node_id, name="test measurement", role="measurement",
        quality="scqual-valtest-1", scale_type="numeric",
        unit="AU", min=None, max=None, values=None,
        definition="A test measurement for validation.",
        long_form=None,
    )
    sl.cmd_add_variable(args_meas_v)
    model_var_id = json.loads(capsys.readouterr().out)["variable_id"]

    # Create an instance linked to the model via ooevv-instance-of
    args_inst = types.SimpleNamespace(
        bundle="scsm-valtest-1",
        template=model_id,
        name="validation instance run",
    )
    sl.cmd_instantiate_template(args_inst)
    inst_id = json.loads(capsys.readouterr().out)["instance_id"]

    # (b1) cell variable NOT in model -> success=false
    bogus_var_id = "oov-bogus-not-in-model"
    args_bad = types.SimpleNamespace(
        instance=inst_id,
        cells=json.dumps([{"variable": bogus_var_id, "value": "x"}]),
        observation=None, gloss=None,
    )
    with pytest.raises(SystemExit):
        sl.cmd_add_datum(args_bad)
    out = capsys.readouterr().out
    result_bad = json.loads(out)
    assert result_bad["success"] is False, f"Expected validation failure: {result_bad}"
    assert "unknown variable" in result_bad["error"], f"Unexpected error message: {result_bad['error']}"
    assert bogus_var_id in result_bad["error"], f"Bogus var id missing from error: {result_bad['error']}"

    # (b2) cell variable IN model -> success=true
    args_good = types.SimpleNamespace(
        instance=inst_id,
        cells=json.dumps([{"variable": model_var_id, "value": "42", "number": 42.0}]),
        observation=None, gloss=None,
    )
    sl.cmd_add_datum(args_good)
    out = capsys.readouterr().out
    result_good = json.loads(out)
    assert result_good["success"] is True, f"Expected validation pass: {result_good}"
    assert result_good["cells"] == 1


# ---------------------------------------------------------------------------
# Task 9: Retired-type guard (pure-logic, no DB)
# ---------------------------------------------------------------------------

def test_no_retired_types_in_cli():
    """Guard: no retired TypeQL type name survives in live code of kqed.py or
    scientific_literature.py.

    Stripping strategy:
      1. Remove all triple-quoted string literals (docstrings and historic notes).
      2. Remove full-line # comments.
      3. Remove inline # comment tails.

    What remains is live executable code (including single-quoted TypeQL f-strings).
    TypeQL queries use single-quoted f-strings; docstrings use triple-double-quotes;
    so stripping triple-quoted strings removes only documentation, not queries.

    Retired names that must NOT appear (precise tokens so kefed-model-element
    and ooevv-variable do NOT false-trip):
      - kefed-variable   (not substring of kefed-model-element or ooevv-variable)
      - kefed-element    (not substring of kefed-model-element)
      - kefed-observed-via, kefed-slot, kefed-template, kefed-template-slot
      - ooevv-param-slot, ooevv-slot-binding, ooevv-bundle-experiment
      - ooevv-set-process, ooevv-set-entity
      - scilit-reported-claim, scilit-reported-gap
      - kefed-value-set, scilit-iteration-number, scilit-investigation-phasing
      # kefed-model-node graph redesign (2b.1): retired bigraph relations
      - ooevv-parameter-binding, ooevv-produced-by
      # renamed bigraph roles (*-entity/*-process -> *-node)
      - subject-entity, input-entity, consuming-process, producing-process
      - output-entity, binding-bearer, bound-parameter, produced-variable
    """
    import re
    from pathlib import Path

    SKILL_DIR = Path(__file__).resolve().parent.parent

    RETIRED = [
        "kefed-variable",
        "kefed-element",
        "kefed-observed-via",
        "kefed-slot",
        "kefed-template",
        "kefed-template-slot",
        "ooevv-param-slot",
        "ooevv-slot-binding",
        "ooevv-bundle-experiment",
        "ooevv-set-process",
        "ooevv-set-entity",
        "scilit-reported-claim",
        "scilit-reported-gap",
        "kefed-value-set",
        "scilit-iteration-number",
        "scilit-investigation-phasing",
        # Retired in kefed-model-node graph redesign (2b.1): bigraph relations
        "ooevv-parameter-binding",
        "ooevv-produced-by",
        # Retired bigraph role names (renamed to *-node forms)
        "subject-entity",
        "input-entity",
        "consuming-process",
        "producing-process",
        "output-entity",
        "binding-bearer",
        "bound-parameter",
        "produced-variable",
        # Retired eset-{id} naming convention: element-set ids must come from generate_id,
        # NOT be derived from the model id.  Precise: won't trip on element-set / elementset /
        # kefed-model-elementset or generate_id("eset") (which produces eset_id variable).
        "eset-{mid}",
        "eset-{model_id}",
        "eset-{exp_id}",
    ]

    def live_text(path: Path) -> str:
        """Return only live code text: triple-quoted strings removed, # comments stripped."""
        source = path.read_text()
        # 1. Remove triple-quoted string literals (docstrings, historic notes in """/''').
        #    Uses lazy matching with DOTALL so each pair collapses to an empty string.
        source = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
        source = re.sub(r"'''.*?'''", '', source, flags=re.DOTALL)
        # 2. Remove full-line # comments and inline # comment tails.
        lines = []
        for line in source.splitlines():
            stripped = line.lstrip()
            if stripped.startswith('#'):
                continue
            if '#' in line:
                line = line[:line.index('#')]
            lines.append(line)
        return '\n'.join(lines)

    files = [
        ("kqed.py", SKILL_DIR / "kqed.py"),
        ("scientific_literature.py", SKILL_DIR / "scientific_literature.py"),
    ]

    violations = []
    for fname, fpath in files:
        text = live_text(fpath)
        for retired in RETIRED:
            if retired in text:
                violations.append(f"  {fname}: '{retired}'")

    assert not violations, (
        "Retired type names found in live CLI code (after stripping triple-quoted strings "
        "and # comments):\n" + "\n".join(violations)
    )
