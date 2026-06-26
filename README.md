# alhazen-skill-deep-research

Deep-research skills for the [Alhazen](https://github.com/sciknow-io/skillful-alhazen) TypeDB-powered scientific notebook. These four skills **share one TypeDB database, `alh_deep_research`**, so their knowledge interlinks (papers, claims, technology systems, and disease mechanisms all reference the same `scilit-paper` entities).

## Skills

| Skill | Purpose | Namespace |
|-------|---------|-----------|
| **scientific-literature** | Multi-source literature search + ingestion (EPMC, PubMed, OpenAlex, bioRxiv). The **schema base** for this DB. | `scilit-`, `kefed-` |
| **literature-trends** | Abductive argumentation-based literature trend analysis | `trend-` |
| **tech-recon** | Goal-driven technology investigation with Observable Plot analysis | `trec-` |
| **dismech-notebook** | DisMech rare-disease mechanism knowledge (GLAV import from the `dismech` source DB) | `dm-` |

## Install

Requires the Alhazen base pair from the [`skillful-alhazen`](https://github.com/sciknow-io/skillful-alhazen) marketplace (`alhazen-core` + `typedb-notebook`), which install automatically as cross-marketplace dependencies.

```
/plugin marketplace add sciknow-io/skillful-alhazen
/plugin marketplace add sciknow-io/alhazen-skill-deep-research
/plugin install scientific-literature@alhazen-deep-research
```

## Schema ordering

`tech-recon`, `literature-trends`, and `dismech-notebook` extend `scilit-paper`, so **scientific-literature's schema must load first**. Each skill declares `scientific-literature` as a dependency; on a shared database the base schema loads before the extenders. `dismech-notebook`'s `dm-*` data is re-derived by running its GLAV rules with `--source-db dismech --target-db alh_deep_research`.
