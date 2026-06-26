---
name: dismech-notebook
description: DisMech rare disease knowledge mapped into Alhazen notebook memory
triggers:
  - disease mechanism curation
  - DisMech
  - rare disease knowledge graph
---

# DisMech Notebook

Maps the Monarch Initiative **DisMech** rare-disease corpus into the Alhazen
notebook's ICE (information-content-entity) model in TypeDB, using the
cross-database schema mapper, so disease-mechanism knowledge is browsable and
searchable alongside the rest of the notebook.

**Triggers:** disease mechanism curation, DisMech, rare disease knowledge graph

## Prerequisites

- Docker + `uv`.
- `alhazen-core` installed and initialized:
  `/plugin install alhazen-core@skillful-alhazen` then `/alhazen-core:init`.
  (The SessionStart hook auto-runs init and loads this skill's `schema.tql`.)

## Quick start

```bash
CLI="${CLAUDE_PLUGIN_ROOT}/dismech_notebook.py"
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "$CLI" stats
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "$CLI" search --query lysosomal
```

## Commands

| Command | Description |
|---|---|
| `stats` | Entity counts (diseases, mechanisms, terms) |
| `list-diseases [--category C] [--limit N] [--offset N]` | List diseases |
| `show-disease --name NAME` | Full detail for one disease |
| `search --query TEXT [--limit N]` | Search diseases and mechanisms |

**Read `USAGE.md` for the full reference.**
