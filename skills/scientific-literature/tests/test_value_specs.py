"""
First-class, shared value-specifications + grounding-gated qualities.

- ensure-value-spec: find-or-create a named reusable ooevv-scale, linked to a quality via
  ooevv-quality-scale (a quality enumerates its canonical value-specs).
- add-variable --value-spec: a variable REFERENCES a shared value-spec (one scale, many variables),
  measuring the value-spec's quality.
- ensure-quality --curie: grounding is correctness-gated; without a curie the quality is 'ungrounded'.
"""
import json, os, sys, types
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import w, r, SCRATCH_DB

TS = "2026-01-01T00:00:00"


def _out(capsys):
    return json.loads(capsys.readouterr().out)


def test_ensure_value_spec_creates_and_links_and_is_idempotent(authoring_db, capsys):
    import scientific_literature as sl
    w(authoring_db, f'insert $q isa ooevv-quality, has id "q-age", has name "age", '
                    f'has ooevv-definition "the age of the organism";')
    args = types.SimpleNamespace(quality="q-age", name="age (young/old)", scale_type="ordinal",
                                 values="young|old", unit=None, min=None, max=None,
                                 definition="ordinal age classes", long_form=None, curie=None)
    sl.cmd_ensure_value_spec(args)
    d1 = _out(capsys)
    assert d1["success"] is True
    vs = d1["value_spec_id"]
    # linked to the quality via ooevv-quality-scale
    link = r(authoring_db, f'match $q isa ooevv-quality, has id "q-age"; '
                           f'$s isa ooevv-scale, has id "{vs}"; '
                           f'(quality: $q, scale: $s) isa ooevv-quality-scale; fetch {{"id": $s.id}};')
    assert link and link[0]["id"] == vs
    # ordinal ranks round-trip
    ranks = r(authoring_db, f'match $s isa ooevv-ordinal-scale, has id "{vs}", has ooevv-named-rank $rk; fetch {{"rk": $rk}};')
    assert sorted(x["rk"] for x in ranks) == ["old", "young"]
    # idempotent: same name -> same id, reused
    sl.cmd_ensure_value_spec(args)
    d2 = _out(capsys)
    assert d2["value_spec_id"] == vs and d2.get("reused") is True


def test_add_variable_value_spec_is_shared(authoring_db, capsys):
    import scientific_literature as sl
    w(authoring_db, 'insert $q isa ooevv-quality, has id "q-age2", has name "age";')
    sl.cmd_ensure_value_spec(types.SimpleNamespace(
        quality="q-age2", name="age (young/old) v2", scale_type="ordinal", values="young|old",
        unit=None, min=None, max=None, definition="d", long_form=None, curie=None))
    vs = _out(capsys)["value_spec_id"]
    # two nodes
    w(authoring_db, 'insert $n isa kefed-model-node, has id "node-A", has name "mouse A";')
    w(authoring_db, 'insert $n isa kefed-model-node, has id "node-B", has name "mouse B";')
    for node in ("node-A", "node-B"):
        sl.cmd_add_variable(types.SimpleNamespace(
            node=node, name="age", role="parameter", value_spec=vs,
            quality=None, scale_type=None, values=None, unit=None, min=None, max=None,
            definition="age parameter", long_form=None))
        assert _out(capsys)["success"] is True
    # ONE shared scale is referenced by TWO variables via ooevv-has-scale
    refs = r(authoring_db, f'match $s isa ooevv-scale, has id "{vs}"; '
                           f'(scaled-variable: $v, scale: $s) isa ooevv-has-scale; fetch {{"v": $v.id}};')
    assert len(refs) == 2, f"expected the value-spec shared by 2 variables, got {len(refs)}"
    # both variables measure the same quality
    meas = r(authoring_db, 'match $q isa ooevv-quality, has id "q-age2"; '
                           '(measured-variable: $v, quality: $q) isa ooevv-measures; fetch {"v": $v.id};')
    assert len(meas) == 2


def test_role_is_derived_from_value_spec_cardinality(authoring_db, capsys):
    """A variable's parameter/constant role is fixed by its value-spec's cardinality:
    one possible value -> constant; two or more -> parameter (regardless of --role requested)."""
    import scientific_literature as sl
    w(authoring_db, 'insert $q isa ooevv-quality, has id "q-geno", has name "genotype";')
    w(authoring_db, 'insert $q isa ooevv-quality, has id "q-spec", has name "organism species";')
    # 2-value spec (genotype WT|KO) and 1-value spec (species mouse)
    sl.cmd_ensure_value_spec(types.SimpleNamespace(quality="q-geno", name="WT/KO", scale_type="nominal",
        values="WT|SIRT3-KO", unit=None, min=None, max=None, definition="d", long_form=None, curie=None))
    vs_geno = _out(capsys)["value_spec_id"]
    sl.cmd_ensure_value_spec(types.SimpleNamespace(quality="q-spec", name="mouse", scale_type="nominal",
        values="mouse", unit=None, min=None, max=None, definition="d", long_form=None, curie=None))
    vs_spec = _out(capsys)["value_spec_id"]
    w(authoring_db, 'insert $n isa kefed-model-node, has id "node-geno", has name "mouse";')
    # ask for CONSTANT on the 2-value genotype spec -> corrected to PARAMETER
    sl.cmd_add_variable(types.SimpleNamespace(node="node-geno", name="genotype", role="constant",
        value_spec=vs_geno, quality=None, scale_type=None, values=None, unit=None, min=None, max=None,
        definition="genotype", long_form=None))
    d = _out(capsys)
    assert d["role"] == "parameter", f"genotype (2 values) must be a parameter, got {d['role']}"
    assert d["role_corrected_from"] == "constant"
    # species (1 value) stays constant
    sl.cmd_add_variable(types.SimpleNamespace(node="node-geno", name="species", role="constant",
        value_spec=vs_spec, quality=None, scale_type=None, values=None, unit=None, min=None, max=None,
        definition="species", long_form=None))
    d2 = _out(capsys)
    assert d2["role"] == "constant" and d2["role_corrected_from"] is None


def test_ensure_quality_grounding_is_gated(authoring_db, capsys):
    import scientific_literature as sl
    # with a (verified) curie -> grounded
    sl.cmd_ensure_quality(types.SimpleNamespace(name="age", definition="the age of the organism",
                                                long_form=None, curie="PATO:0000011"))
    q1 = _out(capsys)["quality_id"]
    g = r(authoring_db, f'match $q isa ooevv-quality, has id "{q1}", has scilit-curie $c, '
                        f'has scilit-grounding-state $s; fetch {{"c": $c, "s": $s}};')
    assert g and g[0]["c"] == "PATO:0000011" and g[0]["s"] == "grounded"
    # without a curie -> explicitly ungrounded, no curie
    sl.cmd_ensure_quality(types.SimpleNamespace(name="colony-forming ability",
                                                definition="colonies in a CFC assay", long_form=None, curie=None))
    q2 = _out(capsys)["quality_id"]
    st = r(authoring_db, f'match $q isa ooevv-quality, has id "{q2}", has scilit-grounding-state $s; fetch {{"s": $s}};')
    assert st and st[0]["s"] == "ungrounded"
    nocurie = r(authoring_db, f'match $q isa ooevv-quality, has id "{q2}"; not {{ $q has scilit-curie $c; }}; fetch {{"id": $q.id}};')
    assert nocurie, "ungrounded quality must not carry a curie"
