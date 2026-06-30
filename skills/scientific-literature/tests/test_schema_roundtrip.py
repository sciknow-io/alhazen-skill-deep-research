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
