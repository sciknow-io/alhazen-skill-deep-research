"""
Tests for CLI/KQED re-alignment (Plan 2).

Task 1: scilit-sensemaking-experiment relation + authoring_db fixture.
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
