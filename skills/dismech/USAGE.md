# DisMech CLI — Usage Reference

Disease Mechanism Knowledge Graph: 750+ curated disease entries with
pathophysiology mechanisms stored in TypeDB 3.x.

---

## Overview

DisMech ingests structured YAML disorder files into a TypeDB graph database and
exposes CLI commands for exploration and a browser-based dashboard.  Each
disorder entry has up to three tiers of data:

1. **Disease entity** — name, category, parent categories, synonyms
2. **Disease term** — preferred MONDO/OMIM term and identifier
3. **Pathophysiology mechanisms** — named mechanisms with prose descriptions

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker | TypeDB runs as a container (`typedb/typedb:3.8.0`) |
| uv | Python environment manager — [install](https://docs.astral.sh/uv/) |
| TypeDB Python driver | Installed automatically via `uv sync` |

TypeDB starts automatically when a Claude Code session begins (via the
`SessionStart` hook in `hooks/hooks.json`).  You can also start it manually
with the `init` command below.

---

## Environment Variables

All connection settings can be overridden via environment variables:

| Variable | Default | Description |
|---|---|---|
| `TYPEDB_HOST` | `localhost` | TypeDB server hostname |
| `TYPEDB_PORT` | `1729` | TypeDB server port |
| `TYPEDB_DATABASE` | `dismech` | Database name |
| `TYPEDB_USERNAME` | `admin` | TypeDB username |
| `TYPEDB_PASSWORD` | `password` | TypeDB password |

---

## Commands

All commands are run via `uv run` from the repo root, or use `make` targets
(see `Makefile`).

```
SKILL=plugins/dismech/skills/dismech
uv run --project $SKILL --python 3.12 python $SKILL/dismech.py <command> [options]
```

---

### `init`

Start the TypeDB Docker container, create the `dismech` database, and load the
TypeQL schema.  Safe to run multiple times — skips steps that are already done.

```bash
uv run --project $SKILL --python 3.12 python $SKILL/alhazen_core.py init
```

**Output:**
```json
{
  "success": true,
  "typedb": "running",
  "database": "dismech",
  "database_created": true,
  "schema": "loaded",
  "message": "DisMech ready. Run dismech.py ingest to load disease data."
}
```

**Additional subcommands** (`alhazen_core.py`):

```bash
# Check container and database state
python alhazen_core.py status

# Drop and recreate database (destroys all data — irreversible)
python alhazen_core.py reset --yes
```

---

### `ingest`

Bulk-ingest disorder YAML files from a directory.  Skips files that do not
conform to the expected structure.

If you do not have a local copy of the disorder YAML files, clone the source
repository first:

```bash
git clone https://github.com/monarch-initiative/dismech /tmp/dismech-kb
```

Then ingest from the `kb/disorders` subdirectory:

```bash
python dismech.py ingest --source /tmp/dismech-kb/kb/disorders
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--source` | *(required)* | Path to directory containing `*.yaml` disorder files |
| `--max N` | unlimited | Ingest at most N files (useful for testing) |
| `--quiet` | off | Suppress the tqdm progress bar |

**Output:**
```json
{
  "success": true,
  "total_files": 762,
  "inserted": 755,
  "skipped": 7,
  "mechanisms": 3241,
  "error_count": 0
}
```

---

### `list-diseases`

List all disease names in the database, optionally filtered by category.

```bash
python dismech.py list-diseases
python dismech.py list-diseases --category Mendelian
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--category` | all | Filter by category: `Mendelian`, `Complex`, `Infectious`, `Other` |

**Output:**
```json
{
  "success": true,
  "count": 312,
  "diseases": [
    "Achondroplasia",
    "Alagille Syndrome",
    "Alpha-1 Antitrypsin Deficiency",
    "..."
  ]
}
```

---

### `show-disease`

Show full details for a single disease: category, parents, disease term, and
all pathophysiology mechanisms with descriptions.

```bash
python dismech.py show-disease --name "Achondroplasia"
```

**Options:**

| Flag | Description |
|---|---|
| `--name` | Exact disease name (case-sensitive) |

**Output:**
```json
{
  "success": true,
  "disease": {
    "name": "Achondroplasia",
    "category": "Mendelian",
    "parents": ["Skeletal dysplasias", "Dwarfism"],
    "disease_term": "Achondroplasia",
    "mechanisms": [
      {
        "name": "FGFR3 gain-of-function mutation",
        "description": "Activating mutation p.Gly380Arg in FGFR3 constitutively activates the receptor, inhibiting chondrocyte proliferation and differentiation in the growth plate via the MAPK/ERK and STAT1 pathways."
      },
      {
        "name": "Impaired endochondral ossification",
        "description": "Reduced chondrocyte proliferation and premature differentiation in the growth plate lead to shortened long bones and characteristic rhizomelic shortening."
      }
    ]
  }
}
```

Exits with code 1 and an error JSON if the disease is not found.

---

### `search`

Full-text substring search over disease names and mechanism names.  Returns
matching diseases with the type of match and (for mechanism hits) the matching
mechanism name.

```bash
python dismech.py search --query "FGFR3"
python dismech.py search --query "growth plate" --limit 20
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--query` | *(required)* | Search text (case-insensitive substring) |
| `--limit N` | 50 | Maximum number of results to return |

**Output:**
```json
{
  "success": true,
  "query": "FGFR3",
  "count": 3,
  "results": [
    { "disease": "Achondroplasia",          "match_type": "mechanism", "mechanism": "FGFR3 gain-of-function mutation" },
    { "disease": "Hypochondroplasia",       "match_type": "mechanism", "mechanism": "FGFR3 hypomorphic mutation" },
    { "disease": "Thanatophoric dysplasia", "match_type": "mechanism", "mechanism": "FGFR3 severe gain-of-function" }
  ]
}
```

Match types:
- `name` — the search term appears in the disease name
- `mechanism` — the search term appears in a mechanism name

---

### `stats`

Print counts of diseases, pathophysiology mechanisms, and disease terms
currently stored in the database.

```bash
python dismech.py stats
```

**Output:**
```json
{
  "success": true,
  "diseases": 755,
  "mechanisms": 3241,
  "disease_terms": 748
}
```

---

### `serve`

Start a local HTTP server that hosts the interactive dashboard and a JSON REST
API.  Opens at `http://localhost:<port>`.

```bash
python dismech.py serve
python dismech.py serve --port 8080
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--port N` | 7777 | TCP port to listen on |

**Output** (then blocks):
```json
{"message": "DisMech dashboard at http://localhost:7777", "port": 7777}
```

---

## Dashboard

After running `serve`, open `http://localhost:7777` in a browser.

The dashboard has three tabs:

| Tab | Description |
|---|---|
| **Browse Diseases** | Paginated table of all diseases (50/page) with optional category filter |
| **Disease Detail** | Type any disease name to view its full record, including all mechanisms |
| **Search** | Free-text search over disease names and mechanism names |

The stats bar at the top shows live counts of diseases, mechanisms, and disease
terms.  Clicking any disease name in Browse or Search jumps directly to its
detail view.

---

## API Endpoints

The `serve` command also exposes a REST API at `/api/`:

| Endpoint | Parameters | Description |
|---|---|---|
| `GET /api/stats` | — | Disease, mechanism, and term counts |
| `GET /api/diseases` | `limit`, `offset`, `category` | Paginated disease list |
| `GET /api/disease` | `name` | Full disease detail record |
| `GET /api/search` | `q`, `limit` | Full-text search results |

All responses are JSON.

---

## Makefile Shortcuts

From the repo root:

```bash
make init        # Start TypeDB and load schema
make ingest      # Ingest from default disorders directory
make stats       # Print database statistics
make serve       # Start dashboard on port 7777
make demo        # init + ingest + stats
```

Override the disorders directory or port:

```bash
make ingest DISORDERS_DIR=/custom/path/to/disorders
make serve PORT=8080
```
