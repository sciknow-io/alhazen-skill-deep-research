# DisMech Notebook — Usage Reference

Maps the Monarch Initiative **DisMech** rare-disease corpus into the Alhazen
notebook's ICE (information-content-entity) model in TypeDB, then exposes CLI
commands to browse and search it alongside the rest of the notebook.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker | TypeDB runs as a container, started by `alhazen-core` |
| uv | Python environment manager — https://docs.astral.sh/uv/ |
| alhazen-core | Install first: `/plugin install alhazen-core@skillful-alhazen`, then `/alhazen-core:init` |

The SessionStart hook auto-runs `alhazen_core.py init` and loads this skill's
`schema.tql` on every session, so the notebook is ready before you run commands.

---

## CLI

```bash
CLI="${CLAUDE_PLUGIN_ROOT}/dismech_notebook.py"
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "$CLI" <command> [args]
```

(Standalone: replace `${CLAUDE_PLUGIN_ROOT}` with the skill directory.)

---

## Commands

| Command | Description |
|---|---|
| `stats` | Show entity counts in the notebook (diseases, mechanisms, terms) |
| `list-diseases [--category C] [--limit N] [--offset N]` | List diseases, optionally filtered by category |
| `show-disease --name NAME` | Show the full detail for one disease |
| `search --query TEXT [--limit N]` | Full-text search across diseases and mechanisms |

### Examples

```bash
DIR="${CLAUDE_PLUGIN_ROOT}"

# entity counts
uv run --project "$DIR" python "$DIR/dismech_notebook.py" stats

# browse a category
uv run --project "$DIR" python "$DIR/dismech_notebook.py" list-diseases --category metabolic --limit 20

# one disease in full
uv run --project "$DIR" python "$DIR/dismech_notebook.py" show-disease --name "Gaucher disease"

# search diseases + mechanisms
uv run --project "$DIR" python "$DIR/dismech_notebook.py" search --query lysosomal --limit 30
```

---

## Data model

The corpus is stored using the Alhazen notebook's shared ICE model (see
`schema.tql`), so DisMech disease-mechanism knowledge is queryable through the
same graph as other notebook content. Ingestion and mapping are handled by the
cross-database schema mapper referenced in `SKILL.md`.
