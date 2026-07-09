#!/usr/bin/env bash
# refresh.sh — Pull latest dismech data, drop/recreate DB, ingest, GLAV-map to notebook.
#
# Usage:
#   bash local_skills/dismech/refresh.sh [/path/to/dismech/repo]
#
# Defaults to DISMECH_REPO env var or ~/dismech.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILL="$SCRIPT_DIR"

DISMECH_REPO="${1:-${DISMECH_REPO:-$HOME/dismech}}"
DISORDERS_DIR="$DISMECH_REPO/kb/disorders"

TYPEDB_HOST="${TYPEDB_HOST:-localhost}"
TYPEDB_PORT="${TYPEDB_PORT:-1729}"
TYPEDB_DATABASE="${TYPEDB_DATABASE:-dismech}"

echo "=== DisMech Refresh ==="
echo "Repo:     $DISMECH_REPO"
echo "Database: $TYPEDB_DATABASE"
echo ""

# 1. Pull latest data
if [ -d "$DISMECH_REPO/.git" ]; then
    echo "[1/5] Pulling latest data..."
    git -C "$DISMECH_REPO" pull --ff-only
else
    echo "[1/5] Cloning dismech repo..."
    git clone https://github.com/monarch-initiative/dismech "$DISMECH_REPO"
fi

if [ ! -d "$DISORDERS_DIR" ]; then
    echo "ERROR: $DISORDERS_DIR not found"
    exit 1
fi

FILE_COUNT=$(ls "$DISORDERS_DIR"/*.yaml 2>/dev/null | grep -cv '\.history\.yaml$' || true)
echo "     $FILE_COUNT disorder files found"
echo ""

# 2. Drop existing database
echo "[2/5] Dropping database '$TYPEDB_DATABASE'..."
python3 -c "
from typedb.driver import TypeDB, Credentials, DriverOptions
d = TypeDB.driver('$TYPEDB_HOST:$TYPEDB_PORT', Credentials('admin','password'), DriverOptions(is_tls_enabled=False))
if d.databases.contains('$TYPEDB_DATABASE'):
    d.databases.get('$TYPEDB_DATABASE').delete()
    print('     Dropped')
else:
    print('     Did not exist')
d.close()
"
echo ""

# 3. Init (create DB + load schema)
echo "[3/5] Creating database and loading schema..."
cd "$REPO_ROOT"
uv run --project "$SKILL" --python 3.12 python "$SKILL/dismech.py" init
echo ""

# 4. Ingest
echo "[4/5] Ingesting disorders..."
uv run --project "$SKILL" --python 3.12 python "$SKILL/dismech.py" ingest --source "$DISORDERS_DIR"
echo ""

# 5. GLAV mapping to notebook
echo "[5/5] Running GLAV mapping (dismech -> alhazen_notebook)..."
uv run python "$REPO_ROOT/src/skillful_alhazen/utils/schema_mapper.py" run \
    --source-db dismech \
    --target-db alhazen_notebook \
    --rules-dir "$REPO_ROOT/local_skills/dismech-notebook/mapping/rules"
echo ""

echo "=== Done ==="
