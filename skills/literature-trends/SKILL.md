---
name: literature-trends
description: Abductive argumentation-based literature trend analysis — trace how explanatory hypotheses evolve over time within a tagged literature thread
triggers:
  - "analyze trends in [keyword/topic]"
  - "trace hypothesis evolution for [cluster]"
  - "create trend thread for [topic]"
  - "what hypotheses dominated [topic] in [year range]"
  - "show genealogy for [trend thread]"
prerequisites:
  - TypeDB running (install alhazen-core first and run /alhazen-core:init)
  - uv installed
  - scientific-literature skill installed and papers ingested with keyword tags
    (literature-trends queries scilit-paper entities and their keyword attributes)
---

# Literature Trends Skill

Use this skill to perform **abductive argumentation analysis** on a tagged set of scientific papers — tracing how explanatory hypotheses emerge, evolve, and replace each other over time.

**Core idea:** For each time window of papers, identify: (1) what phenomenon was observed and needed explaining, (2) what hypothesis was proposed, (3) what evidence supported it, (4) what it left unexplained, and (5) how it relates to the prior window's hypothesis.

**When to use:**
- Papers are clustered/tagged with a keyword (e.g., from `scientific_literature.py cluster` + keyword tagging)
- You want to understand how a research field's explanatory framework has evolved
- You want to identify open questions and research gaps systematically

## Quick Start

> **Path note:** Replace `<skill-path>` with your installation directory
> (e.g. `~/.claude/plugins/cache/literature-trends/` when installed as a plugin).

```bash
# 1. Create a trend thread for a tagged cluster
uv run --project <skill-path> python <skill-path>/literature_trends.py create-thread \
    --name "Partial Reprogramming Trend Analysis" \
    --keyword "partial-reprogramming" \
    --source-collection "collection-925280f3c398"

# 2. Record a hypothesis note for a time window
uv run --project <skill-path> python <skill-path>/literature_trends.py record-hypothesis \
    --thread "trend-thread-abc123" \
    --window "2016-2018" \
    --content "## Window 2016-2018\n\n**Phenomenon:** ..."

# 3. Link two hypotheses in genealogy
uv run --project <skill-path> python <skill-path>/literature_trends.py record-genealogy \
    --predecessor "note-abc123" --successor "note-def456" \
    --type "extends" --description "Extends to wild-type aging"

# 4. Show the full genealogy chain
uv run --project <skill-path> python <skill-path>/literature_trends.py show-thread \
    --thread "trend-thread-abc123"
```

**Before executing any commands, read `USAGE.md` in this directory for the complete command reference, workflows, data model, and abductive framework.**
