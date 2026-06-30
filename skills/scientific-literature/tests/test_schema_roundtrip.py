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


def _seed_elementset(db):
    w(db, 'insert $s isa ooevv-element-set, has id "ooevv-es-x", has name "X";')


def test_kefed_bigraph(scratch_db):
    _seed_elementset(scratch_db)
    # model + subject material entity + a manipulation process + a measurement variable
    w(scratch_db, 'insert $m isa kefed-model, has id "kefedm-1", has name "qPCR run",'
                  '  has content "protocol", has format "kefed-bigraph";')
    w(scratch_db, 'match $m isa kefed-model, has id "kefedm-1";'
                  'insert $subj isa ooevv-material-entity, has id "me-subj", has name "mouse";'
                  ' (model: $m, subject-entity: $subj) isa ooevv-subject;')
    w(scratch_db, 'match $subj isa ooevv-material-entity, has id "me-subj";'
                  'insert $p isa ooevv-material-processing, has id "mp-1", has name "knockout";'
                  ' (input-entity: $subj, consuming-process: $p) isa ooevv-process-input;')
    # a treatment parameter bound at the manipulation process AND a genotype param on the entity
    w(scratch_db, 'match $p isa ooevv-material-processing, has id "mp-1";'
                  'insert $par isa ooevv-variable, has id "var-treat", has name "treatment",'
                  '  has ooevv-variable-role "parameter";'
                  ' (binding-bearer: $p, bound-parameter: $par) isa ooevv-parameter-binding;')
    w(scratch_db, 'match $subj isa ooevv-material-entity, has id "me-subj";'
                  'insert $g isa ooevv-variable, has id "var-geno", has name "genotype",'
                  '  has ooevv-variable-role "parameter";'
                  ' (binding-bearer: $subj, bound-parameter: $g) isa ooevv-parameter-binding;')
    # subject reads back
    sj = r(scratch_db, 'match $m isa kefed-model, has id "kefedm-1";'
                       ' (model: $m, subject-entity: $e) isa ooevv-subject; $e has name $n; fetch {"n": $n};')
    assert sj[0]["n"] == "mouse"
    # BOTH a process and an entity bear a parameter
    bearers = r(scratch_db, 'match (binding-bearer: $b, bound-parameter: $par) isa ooevv-parameter-binding;'
                            ' $par has name $pn; fetch {"pn": $pn};')
    assert sorted(x["pn"] for x in bearers) == ["genotype", "treatment"]


def test_param_mapping_rules(scratch_db):
    # --- Task-3 coverage gap: prove ooevv-assay inherits ooevv-produced-by roles ---
    w(scratch_db, 'insert $a isa ooevv-assay, has id "assay-gap-cover", has name "gap-assay";')
    w(scratch_db, 'insert $v isa ooevv-variable, has id "var-gap-meas", has name "gap-measurement",'
                  '  has ooevv-variable-role "measurement";')
    w(scratch_db, 'match $a isa ooevv-assay, has id "assay-gap-cover";'
                  ' $v isa ooevv-variable, has id "var-gap-meas";'
                  ' insert (produced-variable: $v, producing-process: $a) isa ooevv-produced-by;')
    gap_rows = r(scratch_db, 'match $a isa ooevv-assay, has id "assay-gap-cover";'
                             ' (produced-variable: $v, producing-process: $a) isa ooevv-produced-by;'
                             ' $v has name $n; fetch {"n": $n};')
    assert gap_rows and gap_rows[0]["n"] == "gap-measurement", \
        f"ooevv-assay bigraph role inheritance failed: {gap_rows!r}"

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
                  ' (instance: $inst, model: $m) isa ooevv-instance-of;')
    w(scratch_db, 'match $inst isa kefed-instance, has id "kefedi-1"; $v isa ooevv-variable, has id "v-expr";'
                  'insert $d isa ooevv-datum, has id "dat-1";'
                  ' (instance: $inst, datum: $d) isa ooevv-instance-datum;'
                  ' (datum: $d, cell-variable: $v) isa ooevv-cell, has ooevv-cell-value "12.3", has ooevv-cell-number 12.3;')
    rows = r(scratch_db, 'match $inst isa kefed-instance, has id "kefedi-1", has scilit-warrant $war;'
                         ' (instance: $inst, datum: $d) isa ooevv-instance-datum;'
                         ' (datum: $d, cell-variable: $v) isa ooevv-cell, has ooevv-cell-number $num;'
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
        "relation kefed-element",
        "relation kefed-observed-via",
        "entity scilit-reported-claim",
        "entity scilit-reported-gap",
    ]
    present = [p for p in retired_patterns if p in txt]
    assert not present, f"retired types still referenced as definitions: {present}"
