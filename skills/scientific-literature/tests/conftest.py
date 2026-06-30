"""
Pytest harness for scientific-literature schema tests.

Provides:
  - scratch_db fixture: yields a typedb driver connected to a freshly-provisioned
    `alh_scilit_schema_test` DB (core alh- schema + current schema.tql), dropped on teardown.
  - w(driver, q): write transaction helper (executes query and commits).
  - r(driver, q): read transaction helper (returns list of rows).

The scratch DB is NEVER `alh_deep_research` -- always `alh_scilit_schema_test`.
"""
import os
import subprocess
import pytest
from pathlib import Path
from typedb.driver import TypeDB, Credentials, DriverOptions, TransactionType

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRATCH_DB = "alh_scilit_schema_test"


def _alhazen_core() -> Path:
    """Resolve alhazen_core.py from the local registry build."""
    candidates = [
        SKILL_DIR.parent / "alhazen-core" / "alhazen_core.py",
        Path.home() / "skillful-alhazen" / "local_skills" / "alhazen-core" / "alhazen_core.py",
        Path.home() / "skillful-alhazen" / ".claude" / "skills" / "alhazen-core" / "alhazen_core.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise RuntimeError(
        "alhazen-core not found; build the registry (make build-skills) first.\n"
        f"Tried: {[str(c) for c in candidates]}"
    )


def _run_core(*args):
    """Run alhazen_core.py with TYPEDB_DATABASE=SCRATCH_DB, using alhazen-core's uv env."""
    core = _alhazen_core()
    env = {**os.environ, "TYPEDB_DATABASE": SCRATCH_DB, "PYTHONWARNINGS": "ignore::SyntaxWarning"}
    env.pop("VIRTUAL_ENV", None)  # prevent conflict with alhazen-core's own venv
    result = subprocess.run(
        ["uv", "run", "--project", str(core.parent), "python", str(core), *args],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alhazen_core.py {' '.join(args)} failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def _driver():
    """Open a new TypeDB driver connection to localhost:1729."""
    return TypeDB.driver(
        "localhost:1729",
        Credentials("admin", "password"),
        DriverOptions(is_tls_enabled=False),
    )


@pytest.fixture
def scratch_db():
    """
    Provision a fresh `alh_scilit_schema_test` DB for one test, then drop it.

    Setup:
      1. Drop any stale scratch DB via the driver.
      2. Run `alhazen_core.py init` to create the DB + load core alh- schema.
      3. Run `alhazen_core.py load-schema schema.tql` to load the scilit schema.

    Yields a connected TypeDB driver. Teardown always drops the scratch DB.
    """
    # Drop stale scratch DB if present
    d0 = _driver()
    if d0.databases.contains(SCRATCH_DB):
        d0.databases.get(SCRATCH_DB).delete()
    d0.close()

    # Provision: core schema first, then scilit schema
    _run_core("init")
    _run_core("load-schema", str(SKILL_DIR / "schema.tql"))

    d = _driver()
    try:
        yield d
    finally:
        d.close()
        # Always drop the scratch DB on teardown
        d2 = _driver()
        if d2.databases.contains(SCRATCH_DB):
            d2.databases.get(SCRATCH_DB).delete()
        d2.close()


def w(driver, q: str) -> None:
    """Execute a write query against SCRATCH_DB and commit."""
    with driver.transaction(SCRATCH_DB, TransactionType.WRITE) as tx:
        tx.query(q).resolve()
        tx.commit()


def r(driver, q: str) -> list:
    """Execute a read/fetch query against SCRATCH_DB and return rows as a list."""
    with driver.transaction(SCRATCH_DB, TransactionType.READ) as tx:
        return list(tx.query(q).resolve())
