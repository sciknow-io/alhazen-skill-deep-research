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
