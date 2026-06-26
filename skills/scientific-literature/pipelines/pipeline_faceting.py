"""Self-contained Hamilton pipeline: feature-faceting over one or more scilit corpora.

This is the worked example for the general ``alh-analysis-pipeline-note`` capability.
The module is stored verbatim as the ``alh-pipeline-script`` of a ``scilit-faceting-note``
and executed by the core ``run-pipeline-note`` runner (typedb-notebook). Because the
runner may live in a different venv, this module is intentionally self-contained: it
depends only on the stdlib + ``typedb-driver`` and opens its own TypeDB connection.

DAG (Hamilton derives edges from parameter names):

    collection_ids ─▶ corpus_items ─▶ written_tags ─▶ facet_rows ─▶ crosstab_markdown
    assignments  ───────────────────▶ written_tags
    facet_schema ───────────────────▶ written_tags
    facet_schema ──────────────────────────────────▶ crosstab_markdown
    collection_kinds ▶ corpus_items
    crosstabs ─────────────────────────────────────▶ crosstab_markdown

Terminal output: ``crosstab_markdown`` (mapped to the note's ``content`` via the config's
``output_attr_map``). Tag writing in ``written_tags`` is idempotent: a tag already present
on a paper is skipped, so re-running never duplicates or overwrites facet tags.
"""

import os
from collections import Counter, defaultdict


# --- TypeDB connection (self-contained; mirrors the skill's defaults) ----------

def _get_driver():
    from typedb.driver import Credentials, DriverOptions, TypeDB

    host = os.getenv("TYPEDB_HOST", "localhost")
    port = int(os.getenv("TYPEDB_PORT", "1729"))
    user = os.getenv("TYPEDB_USERNAME", "admin")
    pwd = os.getenv("TYPEDB_PASSWORD", "password")
    return TypeDB.driver(
        f"{host}:{port}", Credentials(user, pwd), DriverOptions(is_tls_enabled=False)
    )


def _db():
    return os.getenv("TYPEDB_DATABASE", "alh_deep_research")


def _esc(s: str) -> str:
    if s is None:
        return ""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


# --- Hamilton nodes ------------------------------------------------------------

def corpus_items(collection_ids: list, collection_kinds: dict) -> list:
    """Fetch the scilit-paper members of each source corpus.

    Returns a list of {"id": <paper-id>, "kind": <label>} where ``kind`` is the
    per-corpus label supplied in ``collection_kinds`` (e.g. "paper" / "demo").
    """
    from typedb.driver import TransactionType

    items = []
    seen = set()
    with _get_driver() as d:
        with d.transaction(_db(), TransactionType.READ) as tx:
            for cid in collection_ids:
                kind = collection_kinds.get(cid, cid)
                rows = list(tx.query(
                    f'match $c isa scilit-corpus, has id "{_esc(cid)}"; '
                    f'(collection: $c, member: $p) isa alh-collection-membership; '
                    f'$p isa scilit-paper, has id $pid; '
                    f'fetch {{ "id": $pid }};'
                ).resolve())
                for r in rows:
                    pid = r["id"]
                    if pid in seen:
                        continue
                    seen.add(pid)
                    items.append({"id": pid, "kind": kind})
    return items


def written_tags(corpus_items: list, assignments: dict, facet_schema: dict) -> dict:
    """Idempotently write facet:value scilit-keyword tags per paper.

    For each paper in ``assignments`` that is also present in the corpora, write one
    ``<namespace>:<value>`` tag per facet. Boolean facets (schema flag ``boolean``)
    only write ``<namespace>:true`` when the assigned value is truthy. Tags already
    present are skipped. Returns counts.
    """
    from typedb.driver import TransactionType

    corpus_ids = {it["id"] for it in corpus_items}
    written = 0
    skipped = 0
    with _get_driver() as d:
        for pid, facets in assignments.items():
            if pid not in corpus_ids:
                continue
            tags = []
            for facet, value in facets.items():
                spec = facet_schema.get(facet, {})
                ns = spec.get("namespace", facet)
                if spec.get("boolean"):
                    if value:
                        tags.append(f"{ns}:true")
                    continue
                if value in (None, "", "?"):
                    continue
                tags.append(f"{ns}:{value}")
            with d.transaction(_db(), TransactionType.READ) as tx:
                ex = list(tx.query(
                    f'match $p isa scilit-paper, has id "{_esc(pid)}", has scilit-keyword $k; '
                    f'fetch {{ "k": $k }};'
                ).resolve())
            have = {r["k"] for r in ex}
            new = [t for t in tags if t not in have]
            if new:
                with d.transaction(_db(), TransactionType.WRITE) as tx:
                    for t in new:
                        tx.query(
                            f'match $p isa scilit-paper, has id "{_esc(pid)}"; '
                            f'insert $p has scilit-keyword "{_esc(t)}";'
                        ).resolve()
                    tx.commit()
            written += len(new)
            skipped += len(tags) - len(new)
    return {"tags_written": written, "tags_skipped_existing": skipped}


def facet_rows(written_tags: dict, corpus_items: list, facet_schema: dict) -> list:
    """Read the facet tags back per paper into row dicts (one per corpus item).

    Depends on ``written_tags`` so the read happens after the (idempotent) write.
    """
    from typedb.driver import TransactionType

    def pick(ks, ns):
        return next((k.split(":", 1)[1] for k in ks if k.startswith(ns + ":")), "?")

    rows = []
    with _get_driver() as d:
        with d.transaction(_db(), TransactionType.READ) as tx:
            for it in corpus_items:
                r = list(tx.query(
                    f'match $p isa scilit-paper, has id "{_esc(it["id"])}", has scilit-keyword $k; '
                    f'fetch {{ "k": $k }};'
                ).resolve())
                ks = {x["k"] for x in r}
                row = {"kind": it["kind"]}
                for facet, spec in facet_schema.items():
                    ns = spec.get("namespace", facet)
                    if spec.get("boolean"):
                        row[facet] = f"{ns}:true" in ks
                    else:
                        row[facet] = pick(ks, ns)
                rows.append(row)
    return rows


def crosstab_markdown(facet_rows: list, facet_schema: dict, crosstabs: list) -> str:
    """Render marginal distributions + the requested cross-tabulations as markdown."""
    rows = facet_rows
    n = len(rows)
    n_paper = sum(1 for r in rows if r["kind"] == "paper")
    n_demo = sum(1 for r in rows if r["kind"] == "demo")

    boolean_facets = [f for f, s in facet_schema.items() if s.get("boolean")]
    categorical = [f for f in facet_schema if f not in boolean_facets]

    out = []
    out.append(f"# Feature Faceting Cross-Tabulation\n")
    out.append(f"**{n} items** ({n_paper} papers / {n_demo} demos)\n")

    out.append("## Marginal distributions\n")
    for facet in categorical:
        c = Counter(r[facet] for r in rows)
        out.append(f"### {facet}\n")
        out.append("| value | count |")
        out.append("|---|---|")
        for k, v in c.most_common():
            out.append(f"| {k} | {v} |")
        out.append("")
    for facet in boolean_facets:
        t = sum(1 for r in rows if r[facet])
        out.append(f"### {facet}\n")
        out.append(f"- true: {t}")
        out.append(f"- false: {n - t}\n")

    def render_crosstab(rowf, colf):
        cells = defaultdict(Counter)
        rowvals, colvals = set(), set()
        for r in rows:
            rv, cv = r[rowf], r[colf]
            rv = "true" if rv is True else ("false" if rv is False else rv)
            cv = "true" if cv is True else ("false" if cv is False else cv)
            cells[rv][cv] += 1
            rowvals.add(rv)
            colvals.add(cv)
        colvals = sorted(colvals)
        rowvals = sorted(rowvals)
        lines = [f"### {rowf} x {colf}\n"]
        lines.append("| " + rowf + " | " + " | ".join(colvals) + " | total |")
        lines.append("|" + "---|" * (len(colvals) + 2))
        coltot = Counter()
        for rv in rowvals:
            tot = sum(cells[rv].values())
            cellvals = [str(cells[rv].get(c, 0)) for c in colvals]
            lines.append("| " + rv + " | " + " | ".join(cellvals) + f" | {tot} |")
            for c in colvals:
                coltot[c] += cells[rv].get(c, 0)
        lines.append("| **TOTAL** | " + " | ".join(str(coltot[c]) for c in colvals) + f" | {n} |")
        lines.append("")
        return lines

    if crosstabs:
        out.append("## Cross-tabulations\n")
        for pair in crosstabs:
            rowf, colf = pair[0], pair[1]
            if rowf in rows[0] and colf in rows[0]:
                out.extend(render_crosstab(rowf, colf))

    return "\n".join(out)
