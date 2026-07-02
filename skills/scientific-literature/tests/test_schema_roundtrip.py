"""
Smoke test: scratch-DB round-trip for the current schema.tql.

Proves the harness can:
  1. Provision a throwaway `alh_scilit_schema_test` DB with core + scilit schema.
  2. Insert a `scilit-paper` entity.
  3. Read it back via a fetch query.

Import note: tests/ has an __init__.py (making it a package), so we use an explicit
sys.path insert to ensure `conftest` is importable as a bare module name regardless
of how pytest resolves the package boundary.
"""
import sys
import os

# Ensure tests/ dir is on sys.path so `conftest` resolves as a top-level module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import w, r  # noqa: E402


def test_harness_loads_current_schema(scratch_db):
    """Round-trip a scilit-paper through the scratch DB to verify harness + schema."""
    w(scratch_db, 'insert $p isa scilit-paper, has id "scilit-paper-smoke", has name "smoke";')
    rows = r(
        scratch_db,
        'match $p isa scilit-paper, has id "scilit-paper-smoke", has name $n; fetch {"n": $n};',
    )
    assert rows, "Expected at least one row but got none"
    assert rows[0]["n"] == "smoke", f"Expected 'smoke' but got {rows[0]['n']!r}"


def test_ooevv_elementset_and_elements(scratch_db):
    w(scratch_db,
      'insert $s isa ooevv-element-set, has id "ooevv-es-rnaseq", has name "RNASeq",'
      '  has ooevv-definition "vocabulary for RNASeq experiments";')
    # a material entity, a measurement variable, an assay process, a numeric scale, all in the set
    w(scratch_db,
      'match $s isa ooevv-element-set, has id "ooevv-es-rnaseq";'
      'insert $m isa ooevv-material-entity, has id "ooevv-me-mouse", has name "mouse";'
      ' (element-set: $s, element: $m) isa ooevv-set-element;')
    w(scratch_db,
      'match $s isa ooevv-element-set, has id "ooevv-es-rnaseq";'
      'insert $v isa ooevv-variable, has id "ooevv-var-expr", has name "expression",'
      '  has ooevv-variable-role "measurement", has ooevv-ice-kind "measurement",'
      '  has kefed-efo-label "EFO:0000001";'
      ' (element-set: $s, element: $v) isa ooevv-set-element;')
    w(scratch_db,
      'match $s isa ooevv-element-set, has id "ooevv-es-rnaseq";'
      'insert $a isa ooevv-assay, has id "ooevv-assay-qpcr", has name "qPCR";'
      ' (element-set: $s, element: $a) isa ooevv-set-element;')
    rows = r(scratch_db,
      'match $s isa ooevv-element-set, has id "ooevv-es-rnaseq";'
      ' (element-set: $s, element: $e) isa ooevv-set-element; $e has name $n; fetch {"n": $n};')
    names = sorted(x["n"] for x in rows)
    assert names == ["expression", "mouse", "qPCR"]
    # role + ice-kind round-trip on the variable
    vr = r(scratch_db, 'match $v isa ooevv-variable, has id "ooevv-var-expr", has ooevv-variable-role $role,'
                       ' has ooevv-ice-kind $k; fetch {"role": $role, "k": $k};')
    assert vr[0]["role"] == "measurement" and vr[0]["k"] == "measurement"
    # quality round-trip: create ooevv-quality in the set and link via ooevv-measures
    w(scratch_db,
      'match $s isa ooevv-element-set, has id "ooevv-es-rnaseq"; $v isa ooevv-variable, has id "ooevv-var-expr";'
      ' insert $q isa ooevv-quality, has id "ooevv-qual-expr-level", has name "expression level";'
      ' (element-set: $s, element: $q) isa ooevv-set-element;'
      ' (measured-variable: $v, quality: $q) isa ooevv-measures;')
    qr = r(scratch_db,
      'match $v isa ooevv-variable, has id "ooevv-var-expr";'
      ' (measured-variable: $v, quality: $q) isa ooevv-measures; $q has name $n; fetch {"n": $n};')
    assert qr, "Expected ooevv-measures round-trip to return a row"
    assert qr[0]["n"] == "expression level"


def test_quality_canonical_value_specs(scratch_db):
    """A quality enumerates its canonical value-specifications (scales) via ooevv-quality-scale.
    The SAME quality 'age' has two value-specs: ordinal {young<old} and numeric [days]."""
    w(scratch_db, 'insert $q isa ooevv-quality, has id "ooevv-qual-age", has name "age",'
                  '  has ooevv-definition "the age of the organism";')
    # ordinal value-spec
    w(scratch_db,
      'match $q isa ooevv-quality, has id "ooevv-qual-age";'
      ' insert $s isa ooevv-ordinal-scale, has id "ooevv-vs-age-ordinal", has name "age (young/old)",'
      '   has ooevv-named-rank "young", has ooevv-named-rank "old";'
      ' (quality: $q, scale: $s) isa ooevv-quality-scale;')
    # numeric value-spec (days)
    w(scratch_db,
      'match $q isa ooevv-quality, has id "ooevv-qual-age";'
      ' insert $s isa ooevv-numeric-scale, has id "ooevv-vs-age-days", has name "age (days)",'
      '   has ooevv-unit "days";'
      ' (quality: $q, scale: $s) isa ooevv-quality-scale;')
    rows = r(scratch_db,
      'match $q isa ooevv-quality, has id "ooevv-qual-age";'
      ' (quality: $q, scale: $s) isa ooevv-quality-scale; $s has name $n; fetch {"n": $n};')
    names = sorted(x["n"] for x in rows)
    assert names == ["age (days)", "age (young/old)"], f"expected 2 canonical value-specs, got {names}"


def _seed_elementset(db):
    w(db, 'insert $s isa ooevv-element-set, has id "ooevv-es-x", has name "X";')


def test_kefed_bigraph(scratch_db):
    _seed_elementset(scratch_db)
    # model + OOEVV definitions in element-set
    w(scratch_db, 'insert $m isa kefed-model, has id "kefedm-1", has name "qPCR run",'
                  '  has content "protocol", has format "kefed-bigraph";')
    w(scratch_db, 'match $s isa ooevv-element-set, has id "ooevv-es-x";'
                  'insert $me isa ooevv-material-entity, has id "me-subj", has name "mouse";'
                  ' (element-set: $s, element: $me) isa ooevv-set-element;')
    w(scratch_db, 'match $s isa ooevv-element-set, has id "ooevv-es-x";'
                  'insert $mp isa ooevv-material-processing, has id "mp-1", has name "knockout";'
                  ' (element-set: $s, element: $mp) isa ooevv-set-element;')
    # Create model nodes typed by the OOEVV defs; add to model
    w(scratch_db, 'match $m isa kefed-model, has id "kefedm-1"; $me isa ooevv-material-entity, has id "me-subj";'
                  'insert $nsubj isa kefed-model-node, has id "knode-subj", has name "mouse-node";'
                  ' (node: $nsubj, node-type: $me) isa kefed-node-type;'
                  ' (model: $m, element: $nsubj) isa kefed-model-element;')
    w(scratch_db, 'match $m isa kefed-model, has id "kefedm-1"; $mp isa ooevv-material-processing, has id "mp-1";'
                  'insert $nproc isa kefed-model-node, has id "knode-mp1", has name "knockout-node";'
                  ' (node: $nproc, node-type: $mp) isa kefed-node-type;'
                  ' (model: $m, element: $nproc) isa kefed-model-element;')
    # subject node via ooevv-subject (renamed role: subject-node)
    w(scratch_db, 'match $m isa kefed-model, has id "kefedm-1"; $nsubj isa kefed-model-node, has id "knode-subj";'
                  'insert (model: $m, subject-node: $nsubj) isa ooevv-subject;')
    # material flow: subject node feeds into knockout node (renamed roles: input-node, consuming-node)
    w(scratch_db, 'match $nsubj isa kefed-model-node, has id "knode-subj";'
                  ' $nproc isa kefed-model-node, has id "knode-mp1";'
                  'insert (input-node: $nsubj, consuming-node: $nproc) isa ooevv-process-input;')
    # treatment parameter on knockout node + genotype parameter on subject node (kefed-node-variable)
    w(scratch_db, 'match $nproc isa kefed-model-node, has id "knode-mp1";'
                  'insert $par isa ooevv-variable, has id "var-treat", has name "treatment",'
                  '  has ooevv-variable-role "parameter";'
                  ' (node: $nproc, variable: $par) isa kefed-node-variable;')
    w(scratch_db, 'match $nsubj isa kefed-model-node, has id "knode-subj";'
                  'insert $g isa ooevv-variable, has id "var-geno", has name "genotype",'
                  '  has ooevv-variable-role "parameter";'
                  ' (node: $nsubj, variable: $g) isa kefed-node-variable;')
    # subject node reads back via ooevv-subject (new role name: subject-node)
    sj = r(scratch_db, 'match $m isa kefed-model, has id "kefedm-1";'
                       ' (model: $m, subject-node: $n) isa ooevv-subject; $n has name $nn; fetch {"nn": $nn};')
    assert sj[0]["nn"] == "mouse-node"
    # BOTH nodes carry a parameter variable via kefed-node-variable
    bearers = r(scratch_db, 'match (node: $n, variable: $par) isa kefed-node-variable;'
                            ' $par has name $pn; fetch {"pn": $pn};')
    assert sorted(x["pn"] for x in bearers) == ["genotype", "treatment"]


def test_param_mapping_rules(scratch_db):
    # --- Coverage: prove ooevv-assay inherits kefed-node-type:node-type from ooevv-process ---
    # An assay definition can type a kefed-model-node, which then carries variables via kefed-node-variable.
    w(scratch_db, 'insert $a isa ooevv-assay, has id "assay-gap-cover", has name "gap-assay";')
    w(scratch_db, 'insert $v isa ooevv-variable, has id "var-gap-meas", has name "gap-measurement",'
                  '  has ooevv-variable-role "measurement";')
    w(scratch_db, 'match $a isa ooevv-assay, has id "assay-gap-cover";'
                  'insert $n isa kefed-model-node, has id "knode-gap-cover", has name "assay-node";'
                  ' (node: $n, node-type: $a) isa kefed-node-type;')
    w(scratch_db, 'match $n isa kefed-model-node, has id "knode-gap-cover";'
                  ' $v isa ooevv-variable, has id "var-gap-meas";'
                  'insert (node: $n, variable: $v) isa kefed-node-variable;')
    gap_rows = r(scratch_db, 'match $n isa kefed-model-node, has id "knode-gap-cover";'
                             ' (node: $n, variable: $v) isa kefed-node-variable;'
                             ' $v has name $nm; fetch {"nm": $nm};')
    assert gap_rows and gap_rows[0]["nm"] == "gap-measurement", \
        f"ooevv-assay kefed-node-type inheritance via node-variable failed: {gap_rows!r}"

    # --- Main test: data-transformation parameter-mapping rules ---
    w(scratch_db, 'insert $t isa ooevv-data-transformation, has id "dt-mean", has name "mean over replicates";')
    w(scratch_db, 'insert $i isa ooevv-variable, has id "var-rep", has name "replicate",'
                  '  has ooevv-variable-role "parameter";')
    w(scratch_db, 'insert $o isa ooevv-variable, has id "var-mean", has name "mean-expr",'
                  '  has ooevv-variable-role "measurement", has ooevv-ice-kind "derived";')
    # mean DESTROYS the replicate index: in-parameter present, out-parameter absent, kind=aggregate-collapse-destroy
    w(scratch_db, 'match $t isa ooevv-data-transformation, has id "dt-mean";'
                  ' $i isa ooevv-variable, has id "var-rep";'
                  ' insert (transformation: $t, in-parameter: $i) isa ooevv-param-mapping,'
                  '  has ooevv-param-rule-kind "aggregate-collapse-destroy";')
    rows = r(scratch_db, 'match (transformation: $t, in-parameter: $i) isa ooevv-param-mapping,'
                         '  has ooevv-param-rule-kind $k; $i has name $n; fetch {"k": $k, "n": $n};')
    assert rows[0]["k"] == "aggregate-collapse-destroy" and rows[0]["n"] == "replicate"


def test_instance_data_and_warrant(scratch_db):
    w(scratch_db, 'insert $m isa kefed-model, has id "kefedm-t", has name "design", has kefed-model-state "template";')
    w(scratch_db, 'insert $v isa ooevv-variable, has id "v-expr", has name "expr", has ooevv-variable-role "measurement";')
    w(scratch_db, 'match $m isa kefed-model, has id "kefedm-t";'
                  'insert $inst isa kefed-instance, has id "kefedi-1", has name "paperA run",'
                  '  has scilit-warrant "supports a WT-vs-KO contrast";'
                  ' (instance: $inst, model: $m) isa kefed-instance-of;')
    w(scratch_db, 'match $inst isa kefed-instance, has id "kefedi-1"; $v isa ooevv-variable, has id "v-expr";'
                  'insert $d isa kefed-row, has id "dat-1";'
                  ' (instance: $inst, datum: $d) isa kefed-instance-datum;'
                  ' (datum: $d, cell-variable: $v) isa kefed-cell, has kefed-cell-value "12.3", has kefed-cell-number 12.3;')
    rows = r(scratch_db, 'match $inst isa kefed-instance, has id "kefedi-1", has scilit-warrant $war;'
                         ' (instance: $inst, datum: $d) isa kefed-instance-datum;'
                         ' (datum: $d, cell-variable: $v) isa kefed-cell, has kefed-cell-number $num;'
                         ' fetch {"war": $war, "num": $num};')
    assert rows[0]["war"].startswith("supports") and rows[0]["num"] == 12.3


def test_investigation_iterations(scratch_db):
    w(scratch_db, 'insert $i isa scilit-investigation, has id "scinv-1", has name "inv", has content "goal";')
    w(scratch_db, 'insert $c isa scilit-corpus, has id "collection-1", has name "corpus";')
    w(scratch_db, 'match $i isa scilit-investigation, has id "scinv-1";'
                  'insert $it isa scilit-iteration, has id "scit-1", has name "iteration 1", has scilit-iteration-index 1;'
                  ' (investigation: $i, iteration: $it) isa scilit-investigation-iteration;')
    w(scratch_db, 'match $it isa scilit-iteration, has id "scit-1"; $c isa scilit-corpus, has id "collection-1";'
                  'insert (iteration: $it, corpus: $c) isa scilit-iteration-corpus;')
    w(scratch_db, 'match $it isa scilit-iteration, has id "scit-1";'
                  'insert $ph isa scilit-investigation-phase, has id "scph-1", has name "discovery", has scilit-phase "discovery";'
                  ' (iteration: $it, stage: $ph) isa scilit-iteration-stage;')
    rows = r(scratch_db, 'match $i isa scilit-investigation, has id "scinv-1";'
                         ' (investigation: $i, iteration: $it) isa scilit-investigation-iteration;'
                         ' $it has scilit-iteration-index $idx;'
                         ' (iteration: $it, stage: $ph) isa scilit-iteration-stage; $ph has scilit-phase $stage;'
                         ' fetch {"idx": $idx, "stage": $stage};')
    assert rows[0]["idx"] == 1 and rows[0]["stage"] == "discovery"


def test_rhetorical_span_anchored(scratch_db):
    # a paper + sentence fragment (offset/length present), a claim anchored to it, AZ + obs link
    w(scratch_db, 'insert $p isa scilit-paper, has id "scilit-paper-r", has name "paperR";')
    w(scratch_db, 'insert $f isa scilit-sentence, has id "frag-1", has content "SIRT3 is required.", has offset 100, has length 18;')
    w(scratch_db, 'insert $c isa scilit-claim, has id "claim-1", has name "SIRT3 necessity",'
                  '  has scilit-claim-statement "SIRT3 is required for X", has scilit-claim-type "primary",'
                  '  has scilit-rhetorical-role "own-claim";')
    w(scratch_db, 'match $c isa scilit-claim, has id "claim-1"; $f isa scilit-sentence, has id "frag-1";'
                  'insert (derivative: $c, derived-from-source: $f) isa alh-derivation;')
    w(scratch_db, 'insert $o isa scilit-observation, has id "obs-1", has name "obs",'
                  '  has scilit-knowledge-level "association", has scilit-bio-scale "cellular";')
    w(scratch_db, 'match $c isa scilit-claim, has id "claim-1"; $o isa scilit-observation, has id "obs-1";'
                  'insert (claim: $c, observation: $o) isa scilit-claim-observation;')
    # claim -> anchored fragment offset
    rows = r(scratch_db, 'match $c isa scilit-claim, has id "claim-1", has scilit-rhetorical-role $az;'
                         ' (derivative: $c, derived-from-source: $f) isa alh-derivation;'
                         ' $f has offset $off, has length $len; fetch {"az": $az, "off": $off, "len": $len};')
    assert rows[0]["az"] == "own-claim" and rows[0]["off"] == 100 and rows[0]["len"] == 18
    # claim -> observation provenance hop
    obs = r(scratch_db, 'match (claim: $c, observation: $o) isa scilit-claim-observation; $o has id $oid; fetch {"oid": $oid};')
    assert obs[0]["oid"] == "obs-1"


def test_no_retired_types_remain():
    """Guard: ensure retired type definitions are absent from schema.tql.

    Uses precise definition-level patterns (e.g. 'entity kefed-variable ')
    to avoid matching substring occurrences in comments or attribute names.
    ooevv-quality is intentionally KEPT (it is the measurand a variable measures).
    """
    import pathlib
    txt = pathlib.Path(__file__).resolve().parent.parent.joinpath("schema.tql").read_text()
    retired_patterns = [
        "entity kefed-slot ",
        "entity kefed-template ",
        "entity kefed-variable ",
        "relation kefed-element,",
        "relation kefed-observed-via",
        "entity scilit-reported-claim",
        "entity scilit-reported-gap",
        "relation ooevv-set-process",
        "relation ooevv-set-entity",
        # Retired in kefed-model-node graph redesign (2b.1):
        "relation ooevv-parameter-binding,",
        "relation ooevv-produced-by,",
    ]
    present = [p for p in retired_patterns if p in txt]
    assert not present, f"retired types still referenced as definitions: {present}"


def test_kefed_model_element_membership(scratch_db):
    """Round-trip: kefed-model-element links a kefed-model to a kefed-model-node (not OOEVV def directly)."""
    w(scratch_db, 'insert $m isa kefed-model, has id "kefedm-mem-1", has name "membrane-model";')
    w(scratch_db, 'insert $me isa ooevv-material-entity, has id "ooevv-me-mem", has name "SIRT3 protein";')
    w(scratch_db,
      'match $m isa kefed-model, has id "kefedm-mem-1"; $me isa ooevv-material-entity, has id "ooevv-me-mem";'
      'insert $n isa kefed-model-node, has id "knode-mem-1", has name "SIRT3 node";'
      ' (node: $n, node-type: $me) isa kefed-node-type;'
      ' (model: $m, element: $n) isa kefed-model-element;')
    rows = r(
        scratch_db,
        'match $m isa kefed-model, has id "kefedm-mem-1";'
        ' (model: $m, element: $n) isa kefed-model-element; $n has name $nn; fetch {"nn": $nn};',
    )
    assert rows, "Expected kefed-model-element membership row but got none"
    assert rows[0]["nn"] == "SIRT3 node", f"Expected 'SIRT3 node' but got {rows[0]['nn']!r}"


def test_kefed_model_node_graph(scratch_db):
    """Round-trip: kefed-model-node graph with node-type, node-variable, and process-input edge."""
    # 1. Create a kefed-model
    w(scratch_db, 'insert $m isa kefed-model, has id "kefedm-ng-1", has name "node-graph-model";')

    # 2. Create element-set with an ooevv-material-entity def and an ooevv-assay def
    w(scratch_db, 'insert $s isa ooevv-element-set, has id "ooevv-es-ng", has name "NodeGraph";')
    w(scratch_db,
      'match $s isa ooevv-element-set, has id "ooevv-es-ng";'
      'insert $me isa ooevv-material-entity, has id "ooevv-me-ng", has name "cell line";'
      ' (element-set: $s, element: $me) isa ooevv-set-element;')
    w(scratch_db,
      'match $s isa ooevv-element-set, has id "ooevv-es-ng";'
      'insert $assay isa ooevv-assay, has id "ooevv-assay-ng", has name "western blot";'
      ' (element-set: $s, element: $assay) isa ooevv-set-element;')

    # 3. Create kefed-model-node for the material-entity def; add to model; set as subject
    w(scratch_db,
      'match $me isa ooevv-material-entity, has id "ooevv-me-ng";'
      ' $m isa kefed-model, has id "kefedm-ng-1";'
      'insert $n1 isa kefed-model-node, has id "knode-ng-1", has name "cell line node";'
      ' (node: $n1, node-type: $me) isa kefed-node-type;'
      ' (model: $m, element: $n1) isa kefed-model-element;')
    w(scratch_db,
      'match $m isa kefed-model, has id "kefedm-ng-1";'
      ' $n1 isa kefed-model-node, has id "knode-ng-1";'
      'insert (model: $m, subject-node: $n1) isa ooevv-subject;')

    # 4. Create kefed-model-node for the assay def; add to model
    w(scratch_db,
      'match $assay isa ooevv-assay, has id "ooevv-assay-ng";'
      ' $m isa kefed-model, has id "kefedm-ng-1";'
      'insert $n2 isa kefed-model-node, has id "knode-ng-2", has name "western blot node";'
      ' (node: $n2, node-type: $assay) isa kefed-node-type;'
      ' (model: $m, element: $n2) isa kefed-model-element;')

    # 5. Link nodes via ooevv-process-input (renamed roles)
    w(scratch_db,
      'match $n1 isa kefed-model-node, has id "knode-ng-1";'
      ' $n2 isa kefed-model-node, has id "knode-ng-2";'
      'insert (input-node: $n1, consuming-node: $n2) isa ooevv-process-input;')

    # 6. Attach a measurement variable to the assay node via kefed-node-variable
    w(scratch_db,
      'insert $vmeas isa ooevv-variable, has id "var-ng-meas", has name "measurement",'
      '  has ooevv-variable-role "measurement";')
    w(scratch_db,
      'match $n2 isa kefed-model-node, has id "knode-ng-2";'
      ' $vmeas isa ooevv-variable, has id "var-ng-meas";'
      'insert (node: $n2, variable: $vmeas) isa kefed-node-variable;')

    # 7. Attach a parameter variable to the subject node via kefed-node-variable
    w(scratch_db,
      'insert $vparam isa ooevv-variable, has id "var-ng-param", has name "parameter",'
      '  has ooevv-variable-role "parameter";')
    w(scratch_db,
      'match $n1 isa kefed-model-node, has id "knode-ng-1";'
      ' $vparam isa ooevv-variable, has id "var-ng-param";'
      'insert (node: $n1, variable: $vparam) isa kefed-node-variable;')

    # Assert: model -> node membership (both nodes)
    members = r(scratch_db,
                'match $m isa kefed-model, has id "kefedm-ng-1";'
                ' (model: $m, element: $n) isa kefed-model-element; $n has name $nn; fetch {"nn": $nn};')
    assert sorted(x["nn"] for x in members) == ["cell line node", "western blot node"], \
        f"model element membership wrong: {[x['nn'] for x in members]}"

    # Assert: subject node -> type name (via kefed-node-type -> ooevv def)
    types = r(scratch_db,
              'match $n1 isa kefed-model-node, has id "knode-ng-1";'
              ' (node: $n1, node-type: $t) isa kefed-node-type; $t has name $tn; fetch {"tn": $tn};')
    assert types and types[0]["tn"] == "cell line", f"node-type name wrong: {types!r}"

    # Assert: assay node carries measurement variable
    n2_vars = r(scratch_db,
                'match $n2 isa kefed-model-node, has id "knode-ng-2";'
                ' (node: $n2, variable: $v) isa kefed-node-variable;'
                ' $v has ooevv-variable-role $role; fetch {"role": $role};')
    assert n2_vars and n2_vars[0]["role"] == "measurement", f"assay node variable role wrong: {n2_vars!r}"

    # Assert: subject node carries parameter variable
    n1_vars = r(scratch_db,
                'match $n1 isa kefed-model-node, has id "knode-ng-1";'
                ' (node: $n1, variable: $v) isa kefed-node-variable;'
                ' $v has ooevv-variable-role $role; fetch {"role": $role};')
    assert n1_vars and n1_vars[0]["role"] == "parameter", f"subject node variable role wrong: {n1_vars!r}"

    # Assert: process-input edge round-trips (subject node -> assay node)
    edge = r(scratch_db,
             'match $n1 isa kefed-model-node, has id "knode-ng-1";'
             ' $n2 isa kefed-model-node, has id "knode-ng-2";'
             ' (input-node: $n1, consuming-node: $n2) isa ooevv-process-input;'
             ' $n1 has id $id1; fetch {"id1": $id1};')
    assert edge and edge[0]["id1"] == "knode-ng-1", \
        f"ooevv-process-input edge between nodes missing: {edge!r}"


def test_model_definition_and_elementset(scratch_db):
    """Round-trip: kefed-model owns ooevv-definition/ooevv-long-form; two models share one element-set."""
    # 1. Create a shared element-set
    w(scratch_db,
      'insert $es isa ooevv-element-set, has id "ooevv-es-shared", has name "shared vocab";')
    # 2. Create first kefed-model with definition + long-form
    w(scratch_db,
      'insert $m isa kefed-model, has id "kefedm-def",'
      '  has name "model-def",'
      '  has ooevv-definition "a qPCR model measuring SIRT3 expression",'
      '  has ooevv-long-form "Quantitative PCR model";')
    # 3. Link model 1 to the element-set via kefed-model-elementset
    w(scratch_db,
      'match $m isa kefed-model, has id "kefedm-def";'
      '  $es isa ooevv-element-set, has id "ooevv-es-shared";'
      'insert (model: $m, element-set: $es) isa kefed-model-elementset;')
    # 4. Create second kefed-model and link it to the SAME element-set
    w(scratch_db,
      'insert $m2 isa kefed-model, has id "kefedm-def-2", has name "model-def-2";')
    w(scratch_db,
      'match $m2 isa kefed-model, has id "kefedm-def-2";'
      '  $es isa ooevv-element-set, has id "ooevv-es-shared";'
      'insert (model: $m2, element-set: $es) isa kefed-model-elementset;')
    # 5. Assert: both models resolve the shared element-set (independent queries)
    es1 = r(scratch_db,
            'match $m isa kefed-model, has id "kefedm-def";'
            '  (model: $m, element-set: $es) isa kefed-model-elementset;'
            '  $es has id $esid; fetch {"esid": $esid};')
    assert es1 and es1[0]["esid"] == "ooevv-es-shared", \
        f"model 1 -> element-set resolution failed: {es1!r}"
    es2 = r(scratch_db,
            'match $m2 isa kefed-model, has id "kefedm-def-2";'
            '  (model: $m2, element-set: $es) isa kefed-model-elementset;'
            '  $es has id $esid; fetch {"esid": $esid};')
    assert es2 and es2[0]["esid"] == "ooevv-es-shared", \
        f"model 2 -> shared element-set resolution failed: {es2!r}"
    # 6. Assert: model 1's definition + long-form round-trip
    defn = r(scratch_db,
             'match $m isa kefed-model, has id "kefedm-def",'
             '  has ooevv-definition $def, has ooevv-long-form $lf;'
             '  fetch {"def": $def, "lf": $lf};')
    assert defn, "Expected definition/long-form rows but got none"
    assert "SIRT3" in defn[0]["def"], f"definition round-trip failed: {defn[0]['def']!r}"
    assert defn[0]["lf"] == "Quantitative PCR model", \
        f"long-form round-trip failed: {defn[0]['lf']!r}"


def test_datum_observation_bridge(scratch_db):
    """Round-trip: kefed-datum-observation is the sole bridge from a datum row to its observation."""
    # create a template model + instance + datum
    w(scratch_db, 'insert $m isa kefed-model, has id "kefedm-dob-1", has name "bridge-model",'
                  '  has kefed-model-state "template";')
    w(scratch_db,
      'match $m isa kefed-model, has id "kefedm-dob-1";'
      'insert $inst isa kefed-instance, has id "kefedi-dob-1", has name "bridge-run";'
      ' (instance: $inst, model: $m) isa kefed-instance-of;')
    w(scratch_db,
      'match $inst isa kefed-instance, has id "kefedi-dob-1";'
      'insert $d isa kefed-row, has id "dat-dob-1";'
      ' (instance: $inst, datum: $d) isa kefed-instance-datum;')
    # create an observation and link datum -> observation via kefed-datum-observation
    w(scratch_db,
      'insert $o isa scilit-observation, has id "obs-dob-1", has name "bridge-obs",'
      '  has scilit-knowledge-level "association", has scilit-bio-scale "molecular";')
    w(scratch_db,
      'match $d isa kefed-row, has id "dat-dob-1"; $o isa scilit-observation, has id "obs-dob-1";'
      'insert (datum: $d, observation: $o) isa kefed-datum-observation;')
    # match it back asserting the observation id
    rows = r(
        scratch_db,
        'match $d isa kefed-row, has id "dat-dob-1";'
        ' (datum: $d, observation: $o) isa kefed-datum-observation; $o has id $oid; fetch {"oid": $oid};',
    )
    assert rows, "Expected kefed-datum-observation bridge row but got none"
    assert rows[0]["oid"] == "obs-dob-1", f"Expected 'obs-dob-1' but got {rows[0]['oid']!r}"
