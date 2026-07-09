---
name: dismech
description: Browse and query the DisMech disease mechanism knowledge graph (750+ curated disorders in TypeDB 3.x)
triggers:
  - "show me disease mechanisms for"
  - "what genes are associated with"
  - "list diseases with phenotype"
  - "pathophysiology of"
  - "dismech"
  - "disease mechanism"
  - "rare disease"
prerequisites:
  - Docker running (TypeDB auto-starts on session start)
  - uv installed
---

# Disease Mechanism Knowledge Graph (DisMech)

750+ curated disease entries with pathophysiology mechanisms, HPO phenotypes,
gene associations, and therapeutic targets — all stored in TypeDB 3.x.

**When to use:** Research disease mechanisms, find gene-disease associations,
explore pathophysiology, or query curated disorder data.

## Quick Start

The TypeDB database auto-initializes on session start via the SessionStart hook.
To manually ingest data, first obtain the disorders directory:

```bash
# If no local copy of the disorder YAML files exists, clone the source:
git clone https://github.com/monarch-initiative/dismech /tmp/dismech-kb
```

Then ingest:

```bash
uv run --project <skill-path> python <skill-path>/dismech.py ingest \
  --source /tmp/dismech-kb/kb/disorders
```

Query a disease:
```bash
uv run --project <skill-path> python <skill-path>/dismech.py show-disease \
  --name "Achondroplasia"
```

**For the full command reference, read USAGE.md.**
