"""Render a paper's sensemaking curation as a self-contained, static HTML file.

This is a headless port of the dashboard's per-paper sensemaking view
(`dashboard/components/paper-detail.tsx` -> `paper-curation.tsx`, with `kefed-instance.tsx`
and `kefed-graph.tsx`). It consumes exactly the JSON the CLI already produces:

  - `show`               -> paper detail (header, abstract, notes, keyword facets)
  - `show-paper-curation`-> the sensemaking bundle (claims, observations, KEfED instances +
                            data, gaps) plus claim->observation and fragment-derivation edges
  - `lint-sensemaking`   -> the collapsible "sensemaking checks" box

The dashboard is a thin renderer over these CLI payloads (see `dashboard/lib.ts`), so the same
inputs reproduce the same view offline. The module has NO dependencies (stdlib only) and never
touches TypeDB or the network: pass it dicts, get back an HTML string. As in the dashboard,
System-3 mechanisms are deliberately absent from the sensemaking payload and are not rendered.

The visual language mirrors `dashboard/components/tokens.ts` (the "Starry Night" dark theme).
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional

# ── design tokens (mirror dashboard/components/tokens.ts) ───────────────────────
_CSS_VARS = {
    "bg": "#070d1c",
    "bg-raised": "#0c1628",
    "bg-sunken": "#050a16",
    "panel": "rgba(12, 22, 40, 0.72)",
    "panel-hi": "rgba(20, 34, 58, 0.85)",
    "border": "rgba(90, 173, 175, 0.18)",
    "border-hi": "rgba(90, 173, 175, 0.42)",
    "border-dim": "rgba(200, 221, 232, 0.08)",
    "fg": "#c8dde8",
    "fg-dim": "#8ba4b8",
    "fg-faint": "#5e7387",
    "teal": "#5aadaf",
    "teal-dim": "rgba(90, 173, 175, 0.18)",
    "blue": "#5b8ab8",
    "olive": "#b8c84a",
    "olive-dim": "rgba(184, 200, 74, 0.18)",
    "rust": "#c87a4a",
    "red": "#e05555",
    "mono": "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace",
    "serif": "'DM Serif Display', 'Iowan Old Style', Georgia, serif",
    "sans": "'DM Sans', -apple-system, system-ui, sans-serif",
}

# Claim-type -> accent, matching paper-curation.tsx TYPE_COLOR.
_TYPE_COLOR = {"primary": "var(--teal)", "secondary": "var(--blue)", "peripheral": "var(--fg-faint)"}
# KEfED process-type -> accent, matching kefed-graph.tsx TYPE_STYLE.
_PROC_STYLE = {
    "material-processing": ("var(--blue)", "6px", "material"),
    "assay": ("var(--teal)", "22px", "assay"),
    "data-transformation": ("var(--olive)", "6px", "compute"),
}


def _e(v: Any) -> str:
    """HTML-escape any value (None -> '')."""
    return html.escape("" if v is None else str(v))


# ── claim<->instance grouping heuristic (port of paper-curation.tsx nameMatches) ──
def _name_matches(datum_name: Optional[str], obs_name: Optional[str]) -> bool:
    """A datum-row observation name that starts with a rhetorical observation name on a
    word boundary (e.g. rhetorical "OF3A" ⊂ datum "OF3A frag2 …")."""
    if not datum_name or not obs_name:
        return False
    if datum_name == obs_name:
        return True
    if not datum_name.startswith(obs_name):
        return False
    nxt = datum_name[len(obs_name):len(obs_name) + 1]
    return nxt == "" or re.match(r"[^A-Za-z0-9]", nxt) is not None


# ── small building blocks ───────────────────────────────────────────────────────
def _panel(title: Optional[str], body: str, action: str = "") -> str:
    head = ""
    if title or action:
        head = (f'<header class="panel-head"><h3>{_e(title)}</h3><span class="spacer"></span>'
                f'{action}</header>')
    return f'<section class="panel">{head}{body}</section>'


def _subhead(text: str) -> str:
    return f'<div class="subhead">{_e(text)}</div>'


def _tag(text: str) -> str:
    return f'<span class="tag">{_e(text)}</span>'


def _claim_badge(ctype: Optional[str]) -> str:
    color = _TYPE_COLOR.get(ctype or "", "var(--fg-faint)")
    return (f'<span class="badge" style="color:{color};border-color:{color}">'
            f'{_e(ctype or "claim")}</span>')


# ── citation header (port of paper-detail.tsx CitationHeader) ─────────────────────
def _citation_header(paper: Dict[str, Any]) -> str:
    authors_raw = paper.get("authors") or ""
    authors = [a.strip() for a in authors_raw.split(";") if a.strip()] if authors_raw else []
    if authors:
        author_str = (", ".join(authors[:6]) + ", et al.") if len(authors) > 6 else ", ".join(authors)
    else:
        author_str = None
    year = paper.get("year")
    vol, issue, pages = paper.get("volume"), paper.get("issue"), paper.get("pages")
    locator = ""
    if vol:
        locator = f"{vol}({issue})" if issue else f"{vol}"
    if pages:
        locator = f"{locator}:{pages}" if locator else f"{pages}"

    rows = ['<div class="chip-row">'
            '<span class="type-chip">PAPER</span>'
            + (f'<span class="pmid">PMID {_e(paper.get("pmid"))}</span>' if paper.get("pmid") else "")
            + "</div>"]
    if author_str:
        rows.append(f'<div class="authors">{_e(author_str)}{f" ({_e(year)})" if year else ""}</div>')
    rows.append(f'<h1 class="paper-title">{_e(paper.get("name") or paper.get("id"))}</h1>')
    if paper.get("journal") or locator or (not author_str and year):
        jrow = ""
        if paper.get("journal"):
            jrow += f'<span class="journal">{_e(paper.get("journal"))}</span>'
        if locator:
            jrow += f" {_e(locator)}"
        if not author_str and year:
            jrow += f" ({_e(year)})"
        rows.append(f'<div class="journal-line">{jrow}</div>')
    if paper.get("doi"):
        doi = paper["doi"]
        rows.append(f'<a class="doi" href="https://doi.org/{_e(doi)}" '
                    f'target="_blank" rel="noopener noreferrer">doi:{_e(doi)}</a>')
    return f'<header class="citation">{"".join(rows)}</header>'


# ── one observation + its verbatim fragment quotes (ObservationBlock) ─────────────
def _observation_block(obs: Dict[str, Any], quotes: List[Dict[str, str]]) -> str:
    meta = ""
    if obs.get("name"):
        meta += f'<span class="obs-name">{_e(obs["name"])}</span>'
    if obs.get("knowledge_level"):
        meta += _tag(obs["knowledge_level"])
    if obs.get("bio_scale"):
        meta += _tag(obs["bio_scale"])
    body = f'<div class="obs-meta">{meta}</div>'
    if obs.get("content"):
        body += f'<p class="obs-content">{_e(obs["content"])}</p>'
    for q in quotes:
        frag = (f'<span class="frag-id">{_e(q.get("frag"))}</span>' if q.get("frag") else "")
        body += f'<blockquote class="frag">“{_e(q.get("quote"))}”{frag}</blockquote>'
    return f'<div class="obs">{body}</div>'


# ── KEfED protocol graph (port of kefed-graph.tsx), rendered only when present ────
def _kefed_graph(graph: Dict[str, Any], name: str) -> str:
    procs = graph.get("processes") or []
    if not procs:
        return ""
    by_parent: Dict[Optional[str], List[Dict]] = {}
    for p in procs:
        by_parent.setdefault(p.get("parent"), []).append(p)

    def rank(p):
        return (3 if (p.get("measurements")) else 0) + \
               ({"material-processing": 0, "assay": 1}.get(p.get("type"), 2)) * 0.1

    rows: List[tuple] = []

    def walk(p, depth):
        rows.append((p, depth))
        for c in by_parent.get(p.get("id"), []):
            walk(c, depth + 1)

    for p in sorted([p for p in procs if not p.get("parent")], key=rank):
        walk(p, 0)

    out = [f'<div class="kefed-graph"><div class="kg-title">{_e(name)}</div>']
    for p, depth in rows:
        color, radius, label = _PROC_STYLE.get(p.get("type") or "", _PROC_STYLE["material-processing"])
        params = ""
        for pm in (p.get("parameters") or []):
            vals = pm.get("scale", {}).get("values") or []
            vs = f' = [{_e(" | ".join(vals))}]' if vals else ""
            params += f'<div class="kg-param">{_e(pm.get("name"))}<span class="kg-vals">{vs}</span> →</div>'
        meas = ""
        for m in (p.get("measurements") or []):
            q = (m.get("quality") or {}).get("quality")
            scale = m.get("scale") or {}
            stxt = f' · {_e(scale.get("type"))}' if scale.get("type") else ""
            if scale.get("unit"):
                stxt += f' ({_e(scale.get("unit"))})'
            meas += (f'<div class="kg-meas">→ <span class="kg-grid"></span>'
                     f'<span>{_e(m.get("name"))}<br><span class="kg-quality">[{_e(q or "?")}]{stxt}</span></span></div>')
        io = ""
        ins, outs = p.get("inputs") or [], p.get("outputs") or []
        if ins or outs:
            io = ('<div class="kg-io">' +
                  (f'in: {_e(", ".join(ins))}' if ins else "") +
                  (" · " if ins and outs else "") +
                  (f'out: {_e(", ".join(outs))}' if outs else "") + "</div>")
        out.append(
            f'<div class="kg-row" style="margin-left:{depth * 28}px">'
            f'<div class="kg-params">{params}</div>'
            f'<div class="kg-node-wrap"><div class="kg-node" style="border-color:{color};border-radius:{radius}">'
            f'<div class="kg-node-name">{_e(p.get("name"))}</div>'
            f'<div class="kg-node-type" style="color:{color}">{_e(label)}</div></div>{io}</div>'
            f'<div class="kg-meases">{meas}</div>'
            f'</div>')
    out.append("</div>")
    return "".join(out)


# ── KEfED instance: template design + pivot data table (InstanceBlock/Spreadsheet) ──
def _spreadsheet(tpl: Optional[Dict[str, Any]], data: List[Dict[str, Any]]) -> str:
    if not data:
        return '<div class="empty">No data rows yet.</div>'
    variables = (tpl or {}).get("variables") or []
    # independents (parameter/constant) first, dependent (measurement) last
    variables = sorted(variables, key=lambda v: 1 if v.get("role") == "measurement" else 0)
    if variables:
        cols = [{
            "id": v.get("id"), "name": v.get("name"), "role": v.get("role"),
            "unit": (v.get("scale") or {}).get("unit"),
            "quality": (v.get("quality") or {}).get("quality"),
            "tip": "\n".join(x for x in [
                v.get("definition"),
                (f'measures: {(v.get("quality") or {}).get("quality")}'
                 if (v.get("quality") or {}).get("quality") else ""),
                (v.get("quality") or {}).get("definition"),
            ] if x),
        } for v in variables]
    else:  # fall back to columns discovered in the data
        seen, cols = set(), []
        for r in data:
            for c in r.get("cells", []):
                if c.get("variable") not in seen:
                    seen.add(c.get("variable"))
                    cols.append({"id": c.get("variable"), "name": c.get("name"),
                                 "role": c.get("role"), "unit": None, "quality": None, "tip": ""})

    ths = ""
    for c in cols:
        cls = "meas" if c["role"] == "measurement" else "indep"
        unit = f' <span class="col-unit">({_e(c["unit"])})</span>' if c.get("unit") else ""
        dep = "dependent" if c["role"] == "measurement" else "independent"
        tip = f' title="{_e(c["tip"])}"' if c.get("tip") else ""
        ths += f'<th class="{cls}"{tip}>{_e(c["name"])}{unit}<div class="col-role">{dep}</div></th>'
    ths += '<th class="expander"></th>'

    body = ""
    for i, row in enumerate(data):
        cells_by_var = {c.get("variable"): c for c in row.get("cells", [])}
        tds = ""
        for c in cols:
            cell = cells_by_var.get(c["id"])
            cls = "meas" if c["role"] == "measurement" else "indep"
            tds += f'<td class="{cls}">{_e((cell or {}).get("value"))}</td>'
        obs = row.get("observation")
        if obs:
            rid = f"r{i}"
            tds += '<td class="expander">▸</td>'
            body += f'<tr class="datum" data-row="{rid}" onclick="tog(this)">{tds}</tr>'
            src = _e(obs.get("content") or obs.get("name"))
            body += (f'<tr class="src" id="{rid}"><td colspan="{len(cols) + 1}">'
                     f'<div class="src-inner"><span class="src-label">source</span>{src}</div></td></tr>')
        else:
            tds += '<td class="expander"></td>'
            body += f'<tr class="datum nolink">{tds}</tr>'

    return (f'<div class="table-wrap"><table class="kefed-table">'
            f'<thead><tr>{ths}</tr></thead><tbody>{body}</tbody></table></div>')


def _instance_block(inst: Dict[str, Any]) -> str:
    tpl = inst.get("template_detail") or {}
    tname = (inst.get("template") or {}).get("name") or (inst.get("template") or {}).get("id")
    tpl_line = ""
    if tname:
        tpl_line = f'<span class="tpl-link" title="{_e(tpl.get("definition") or "")}">KEfED template: {_e(tname)} →</span>'
    defn = f'<p class="tpl-def">{_e(tpl.get("definition"))}</p>' if tpl.get("definition") else ""
    graph = ""
    if (tpl.get("graph") or {}).get("processes"):
        graph = (f'<div class="inst-sub">{_subhead("KEfED template design")}'
                 f'{_kefed_graph(tpl["graph"], tpl.get("name") or "")}</div>')
    table = (f'<div class="inst-sub">{_subhead("Data table")}'
             f'{_spreadsheet(tpl, inst.get("data") or [])}</div>')
    return (f'<div class="instance"><div class="inst-head">'
            f'<span class="inst-name">{_e(inst.get("name") or inst.get("id"))}</span>{tpl_line}</div>'
            f'{defn}{graph}{table}</div>')


# ── sensemaking checks box (port of SensemakingChecksBox) ─────────────────────────
def _checks_box(checks_payload: Optional[Dict[str, Any]]) -> str:
    if not checks_payload or not checks_payload.get("checks"):
        return ""
    s = checks_payload.get("summary") or {}
    summary = (f'<span class="ok">{s.get("passed", 0)} pass</span> · '
               f'<span class="warn">{s.get("warned", 0)} warn</span> · '
               f'<span class="fail">{s.get("failed", 0)} fail</span>')
    rows = ""
    glyph = {"pass": "✓", "warn": "!", "fail": "✗"}
    for c in checks_payload["checks"]:
        st = c.get("status")
        n = len(c.get("offenders") or [])
        rows += (f'<div class="chk chk-{st}">'
                 f'<span class="chk-glyph">{glyph.get(st, "?")}</span>'
                 f'<div class="chk-body"><span class="chk-name">{_e(c.get("name"))}</span>'
                 f'<span class="chk-cat">{_e(c.get("category"))}</span>'
                 f'<div class="chk-detail">{_e(c.get("detail"))}</div></div>'
                 f'<span class="chk-count">{n if n else ""}</span></div>')
    return (f'<details class="checks"><summary><span class="checks-title">Sensemaking checks</span>'
            f'<span class="checks-sum">{summary}</span></summary>'
            f'<div class="checks-body">{rows}</div></details>')


# ── main per-paper document ───────────────────────────────────────────────────────
_FACETS = {"topology", "stage", "concern", "contribution", "domain", "autonomy", "memory", "se-agent"}


def render_paper_html(curation: Dict[str, Any],
                      paper_full: Optional[Dict[str, Any]] = None,
                      checks: Optional[Dict[str, Any]] = None,
                      index_href: Optional[str] = None) -> str:
    """Render one paper's sensemaking curation as a self-contained HTML document.

    `curation`   = `show-paper-curation` payload (required; must have hasCuration).
    `paper_full` = `show` payload (optional; adds abstract, notes, keyword facets).
    `checks`     = `lint-sensemaking` payload (optional; the checks box).
    `index_href` = optional link back to an investigation index page.
    """
    bundle = curation.get("bundle") or {}
    paper = dict(curation.get("paper") or {})
    if paper_full and paper_full.get("paper"):
        # `show` carries abstract-text + fuller bibliographic fields; prefer it, keep curation as base
        paper = {**paper, **{k: v for k, v in paper_full["paper"].items() if v is not None}}
    detail = paper_full or {}

    claims = bundle.get("reported_claims") or []
    observations = bundle.get("observations") or []
    gaps = bundle.get("reported_gaps") or []
    instances = bundle.get("instances") or []
    obs_by_id = {o.get("id"): o for o in observations}

    # claim -> observation ids
    claim_obs_ids: Dict[str, List[str]] = {}
    for co in curation.get("claim_observations") or []:
        claim_obs_ids.setdefault(co.get("claim"), []).append(co.get("observation"))
    # observation id -> verbatim fragment quotes
    quotes_by_obs: Dict[str, List[Dict[str, str]]] = {}
    for dv in curation.get("derivations") or []:
        if dv.get("quote"):
            quotes_by_obs.setdefault(dv.get("note"), []).append(
                {"frag": dv.get("frag"), "quote": dv.get("quote")})

    # heuristic: an instance belongs to a claim when a datum-row observation name shares a
    # name-prefix with one of the claim's rhetorical observations.
    matched_ids = set()

    def instances_for_claim(cid: str) -> List[Dict]:
        names = [obs_by_id.get(oid, {}).get("name") for oid in claim_obs_ids.get(cid, [])]
        names = [n for n in names if n]
        if not names:
            return []
        hits = [inst for inst in instances
                if any(_name_matches((r.get("observation") or {}).get("name"), n)
                       for r in (inst.get("data") or []) for n in names)]
        matched_ids.update(i.get("id") for i in hits)
        return hits

    claim_blocks = [{
        "claim": c,
        "obs": [obs_by_id[o] for o in claim_obs_ids.get(c.get("id"), []) if o in obs_by_id],
        "insts": instances_for_claim(c.get("id")),
    } for c in claims]
    leftover = [i for i in instances if i.get("id") not in matched_ids]

    # ── assemble sections ──
    sections: List[str] = []
    if index_href:
        sections.append(f'<a class="backnav" href="{_e(index_href)}">← Investigation</a>')
    sections.append(_citation_header(paper))

    # facet tags (only the 8 known facets), from `show` keywords
    facet_tags = []
    for kw in (detail.get("keywords") or []):
        idx = kw.find(":")
        if idx > 0 and kw[:idx] in _FACETS:
            facet_tags.append((kw[:idx], kw[idx + 1:]))
    if facet_tags:
        chips = "".join(f'<span class="facet">{_e(f)}: {_e(v)}</span>' for f, v in facet_tags)
        sections.append(_panel("Facets", f'<div class="facet-row">{chips}</div>'))

    if paper.get("abstract-text"):
        sections.append(_panel("Abstract", f'<p class="abstract">{_e(paper["abstract-text"])}</p>'))

    notes = detail.get("notes") or []
    if notes:
        nbody = ""
        for n in notes:
            nm = f'<div class="note-name">{_e(n.get("name"))}</div>' if n.get("name") else ""
            nbody += f'<div class="note">{nm}<div class="note-content">{_e(n.get("content"))}</div></div>'
        sections.append(_panel(f"Notes ({len(notes)})", nbody))

    sections.append(_checks_box(checks))

    # sticky claims TOC
    toc = [f'<a href="#claim-{i}">Claim {i + 1}</a>' for i in range(len(claim_blocks))]
    if leftover:
        toc.append('<a href="#additional">Additional models</a>')
    if gaps:
        toc.append('<a href="#gaps">Gaps</a>')
    if len(toc) > 1:
        sections.append(f'<nav class="toc"><span class="toc-label">Claims:</span>{"".join(toc)}</nav>')

    # per-claim sections
    for i, cb in enumerate(claim_blocks):
        c = cb["claim"]
        obs_body = ""
        if cb["obs"]:
            obs_body = "".join(_observation_block(o, quotes_by_obs.get(o.get("id"), [])) for o in cb["obs"])
        else:
            obs_body = '<span class="none">— none linked —</span>'
        inst_body = ""
        if cb["insts"]:
            ev_head = _subhead("Evidence — KEfED models & data ({})".format(len(cb["insts"])))
            inst_body = ev_head + "".join(_instance_block(inst) for inst in cb["insts"])
        cites = ""
        if c.get("cites"):
            chips = "".join(f'<span class="cite">{_e(x.get("name") or x.get("id"))}</span>'
                            for x in c["cites"])
            cites = f'<div class="cites"><span class="cites-label">cites</span>{chips}</div>'
        obs_head = _subhead("Observations ({})".format(len(cb["obs"])))
        inner = (f'<p class="claim-stmt">{_e(c.get("statement"))}</p>{cites}'
                 f'<div>{obs_head}{obs_body}</div>'
                 f'{("<div>" + inst_body + "</div>") if inst_body else ""}')
        sections.append(
            f'<section id="claim-{i}" class="claim-sec">'
            f'{_panel(f"Claim {i + 1}", inner, action=_claim_badge(c.get("type")))}</section>')

    if leftover:
        body = ('<p class="leftover-note">KEfED instances not matched to a specific claim by '
                'observation name.</p>' + "".join(_instance_block(inst) for inst in leftover))
        sections.append(f'<section id="additional">{_panel(f"Additional evidence models ({len(leftover)})", body)}</section>')

    if gaps:
        gbody = ""
        for g in gaps:
            goal = f'<span class="gap-goal">{_e(g.get("goal"))}</span>' if g.get("goal") else ""
            gbody += f'<div class="gap"><p class="gap-name">{_e(g.get("name"))}</p>{goal}</div>'
        sections.append(f'<section id="gaps">{_panel(f"Gaps ({len(gaps)})", gbody)}</section>')

    title = paper.get("name") or paper.get("id") or "Sensemaking"
    return _document(title, "".join(sections))


def render_index_html(investigation: Dict[str, Any]) -> str:
    """Cover page for an investigation: metadata + a card per paper linking to its file."""
    name = investigation.get("name") or investigation.get("id")
    papers = investigation.get("papers") or []
    cards = ""
    for p in sorted(papers, key=lambda x: -(x.get("year") or 0)):
        year = f'<span class="pc-year">{_e(p.get("year"))}</span>' if p.get("year") else ""
        doi = f'<span class="pc-doi">doi:{_e(p.get("doi"))}</span>' if p.get("doi") else ""
        cards += (f'<a class="paper-card" href="{_e(p.get("id"))}.html">'
                  f'<div class="pc-title">{_e(p.get("name") or p.get("id"))}</div>'
                  f'<div class="pc-meta">{year}{doi}</div></a>')
    meta = ""
    if investigation.get("question"):
        meta += _panel("Question", f'<p class="abstract">{_e(investigation["question"])}</p>')
    if investigation.get("purpose"):
        meta += _panel("Purpose", f'<pre class="purpose">{_e(investigation["purpose"])}</pre>')
    header = (f'<header class="citation"><div class="chip-row">'
              f'<span class="type-chip">INVESTIGATION</span>'
              f'<span class="pmid">{_e(investigation.get("id"))}</span></div>'
              f'<h1 class="paper-title">{_e(name)}</h1></header>')
    body = header + meta + _panel(f"Papers ({len(papers)})", f'<div class="cards">{cards}</div>')
    return _document(name, body)


# ── document shell + stylesheet ───────────────────────────────────────────────────
def _document(title: str, body: str) -> str:
    css = _STYLE
    var_block = ":root{" + "".join(f"--{k}:{v};" for k, v in _CSS_VARS.items()) + "}"
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{_e(title)}</title>"
        "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">"
        "<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>"
        "<link href=\"https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&"
        "family=DM+Serif+Display&family=JetBrains+Mono:wght@400;600;700&display=swap\" rel=\"stylesheet\">"
        f"<style>{var_block}{css}</style></head><body><main class=\"shell\">{body}</main>"
        "<script>function tog(r){var s=document.getElementById(r.dataset.row);"
        "if(!s)return;var o=s.style.display==='table-row';s.style.display=o?'none':'table-row';"
        "r.querySelector('.expander').textContent=o?'▸':'▾';}</script>"
        "</body></html>\n")


_STYLE = """
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.shell{max-width:1100px;margin:0 auto;padding:24px;display:flex;flex-direction:column;gap:18px}
a{color:var(--teal)}
.backnav{font-family:var(--mono);font-size:11px;color:var(--fg-dim);text-decoration:none;letter-spacing:.5px}
.backnav:hover{color:var(--teal)}
/* panels */
.panel{background:var(--panel);border:1px solid var(--border);border-radius:4px;
  padding:14px 16px;display:flex;flex-direction:column;gap:12px}
.panel-head{display:flex;align-items:center;gap:10px}
.panel-head .spacer{flex:1}
.panel-head h3{margin:0;font-family:var(--mono);font-size:10.5px;font-weight:600;
  letter-spacing:1.4px;text-transform:uppercase;color:var(--fg-dim)}
.subhead{font-family:var(--mono);font-size:10px;font-weight:600;color:var(--fg-dim);
  text-transform:uppercase;letter-spacing:.7px;margin:0 0 6px}
.tag{font-family:var(--mono);font-size:9.5px;color:var(--fg-faint);text-transform:uppercase;
  letter-spacing:.5px;border:1px solid var(--border-dim);border-radius:3px;padding:1px 6px}
.badge{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.8px;
  border:1px solid;border-radius:3px;padding:2px 8px}
.empty,.none{font-family:var(--mono);font-size:11px;color:var(--fg-faint)}
/* citation header */
.citation{background:var(--bg-raised);border:1px solid var(--border);border-radius:4px;
  padding:20px 24px;display:flex;flex-direction:column;gap:10px}
.chip-row{display:flex;align-items:center;gap:10px}
.type-chip{font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:1px;
  color:var(--blue);border:1px solid var(--blue);border-radius:3px;padding:2px 8px}
.pmid{font-family:var(--mono);font-size:11px;color:var(--fg-faint)}
.authors{font-size:13.5px;color:var(--fg-dim);line-height:1.5}
.paper-title{margin:0;font-family:var(--serif);font-size:26px;line-height:1.2;font-weight:400;
  color:var(--fg);letter-spacing:-.3px}
.journal-line{font-size:13px;color:var(--fg-dim)}
.journal{font-style:italic}
.doi{font-family:var(--mono);font-size:12px;color:var(--teal);text-decoration:underline;
  text-underline-offset:2px}
.abstract{margin:0;font-size:13.5px;line-height:1.6;color:var(--fg-dim)}
.purpose{margin:0;font-family:var(--mono);font-size:12px;line-height:1.5;color:var(--fg-dim);
  white-space:pre-wrap}
.facet-row{display:flex;flex-wrap:wrap;gap:6px}
.facet{font-family:var(--mono);font-size:11px;color:var(--fg-dim);border:1px solid var(--border-dim);
  border-radius:3px;padding:2px 8px}
.note-name{font-family:var(--mono);font-size:11px;color:var(--fg-dim);margin-bottom:4px}
.note-content{font-size:13px;color:var(--fg-dim);white-space:pre-wrap}
.note{margin-bottom:12px}
/* checks box */
.checks{border:1px solid var(--border);border-radius:4px;background:var(--panel)}
.checks summary{cursor:pointer;padding:11px 16px;display:flex;align-items:center;gap:12px;
  font-family:var(--mono);font-size:10.5px;letter-spacing:1.2px;text-transform:uppercase;color:var(--fg-dim)}
.checks-sum{font-size:11px;text-transform:none;letter-spacing:0}
.checks-sum .ok{color:var(--olive)}.checks-sum .warn{color:var(--rust)}.checks-sum .fail{color:var(--red)}
.checks-body{padding:4px 16px 14px;display:flex;flex-direction:column;gap:6px}
.chk{display:grid;grid-template-columns:18px 1fr auto;gap:8px;align-items:baseline}
.chk-glyph{font-family:var(--mono);font-weight:700}
.chk-pass .chk-glyph{color:var(--olive)}.chk-warn .chk-glyph,.chk-warn .chk-count{color:var(--rust)}
.chk-fail .chk-glyph,.chk-fail .chk-count{color:var(--red)}.chk-pass .chk-count{color:var(--olive)}
.chk-name{font-size:13px;color:var(--fg)}
.chk-cat{margin-left:8px;font-family:var(--mono);font-size:10px;color:var(--fg-faint);text-transform:uppercase}
.chk-detail{font-size:12px;color:var(--fg-dim)}
.chk-count{font-family:var(--mono);font-size:10.5px}
/* claims TOC */
.toc{position:sticky;top:0;z-index:5;background:var(--panel-hi);backdrop-filter:blur(6px);
  border:1px solid var(--border);border-radius:4px;padding:10px 14px;display:flex;flex-wrap:wrap;gap:12px}
.toc-label{font-family:var(--mono);font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:var(--fg-dim)}
.toc a{font-family:var(--mono);font-size:10.5px;color:var(--teal);text-decoration:none}
.claim-sec{scroll-margin-top:60px}
.claim-stmt{margin:0;font-family:var(--serif);font-size:16px;line-height:1.55;color:var(--fg)}
.cites{display:flex;gap:8px;flex-wrap:wrap;align-items:baseline}
.cites-label{font-family:var(--mono);font-size:9.5px;color:var(--fg-faint);text-transform:uppercase}
.cite{font-family:var(--mono);font-size:10.5px;color:var(--fg-dim)}
/* observations */
.obs{margin-bottom:12px}
.obs-meta{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.obs-name{font-family:var(--mono);font-size:11px;color:var(--olive)}
.obs-content{margin:4px 0 0;font-size:13px;line-height:1.55;color:var(--fg)}
.frag{margin:6px 0 0;padding:2px 0 2px 10px;border-left:2px solid var(--olive-dim);
  font-size:12.5px;line-height:1.5;color:var(--fg-dim);font-style:italic}
.frag-id{font-family:var(--mono);font-size:9.5px;color:var(--fg-faint);font-style:normal;margin-left:6px}
/* instance */
.instance{border:1px solid var(--border-dim);border-radius:6px;padding:12px 14px;
  background:var(--bg-raised);margin-bottom:12px}
.inst-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap}
.inst-name{font-family:var(--serif);font-size:14.5px;color:var(--fg)}
.tpl-link{font-family:var(--mono);font-size:10.5px;color:var(--olive);white-space:nowrap;cursor:help}
.tpl-def{margin:8px 0 0;font-size:12px;line-height:1.55;color:var(--fg-dim)}
.inst-sub{margin-top:10px}
/* data table */
.table-wrap{overflow-x:auto}
.kefed-table{border-collapse:collapse;font-family:var(--mono);font-size:11.5px}
.kefed-table th{text-align:left;padding:5px 10px;border-bottom:2px solid var(--border);white-space:nowrap}
.kefed-table th.meas{color:var(--teal)}.kefed-table th.indep{color:var(--blue)}
.kefed-table th.expander{width:24px;border-bottom:2px solid var(--border)}
.col-unit{color:var(--fg-faint)}
.col-role{font-size:8.5px;color:var(--fg-faint);text-transform:uppercase;letter-spacing:.4px}
.kefed-table td{padding:4px 10px;border-bottom:1px solid var(--border-dim);white-space:nowrap}
.kefed-table td.meas{color:var(--fg);font-weight:600}.kefed-table td.indep{color:var(--fg-dim)}
.kefed-table td.expander{color:var(--fg-faint);text-align:center}
tr.datum{cursor:pointer}tr.datum.nolink{cursor:default}
tr.datum:hover:not(.nolink){background:var(--bg-raised)}
tr.src{display:none}
tr.src td{background:var(--bg-raised);padding:6px 10px 10px}
.src-inner{font-size:12px;color:var(--fg-dim);border-left:2px solid var(--olive-dim);padding-left:8px}
.src-label{font-family:var(--mono);font-size:9.5px;color:var(--fg-faint);text-transform:uppercase;margin-right:6px}
/* kefed graph */
.kefed-graph{border:1px solid var(--border);border-radius:8px;padding:14px 16px;background:var(--bg-raised)}
.kg-title{font-family:var(--serif);font-size:14px;color:var(--fg);margin-bottom:12px}
.kg-row{display:flex;align-items:center;gap:12px;padding:6px 0}
.kg-params{flex:0 0 280px;display:flex;flex-direction:column;gap:4px;text-align:right;
  font-family:var(--mono);font-size:10.5px;color:var(--fg-dim)}
.kg-vals{color:var(--fg-faint)}
.kg-node-wrap{flex:0 0 220px}
.kg-node{border:1.5px solid;padding:10px 14px;text-align:center}
.kg-node-name{font-size:12.5px;color:var(--fg)}
.kg-node-type{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.5px}
.kg-io{font-family:var(--mono);font-size:9.5px;color:var(--fg-faint);text-align:center;margin-top:3px}
.kg-meases{flex:1;display:flex;flex-direction:column;gap:6px}
.kg-meas{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11px;color:var(--fg)}
.kg-quality{color:var(--teal)}
.kg-grid{display:inline-block;width:30px;height:30px;background:var(--teal-dim);border:1px solid var(--border)}
/* gaps + cards */
.gap{margin-bottom:8px}
.gap-name{margin:0;font-size:13px;color:var(--fg)}
.gap-goal{font-family:var(--mono);font-size:10.5px;color:var(--fg-faint)}
.leftover-note{margin:0 0 8px;font-size:12.5px;color:var(--fg-dim)}
.cards{display:flex;flex-direction:column;gap:10px}
.paper-card{display:block;background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;
  padding:14px 16px;text-decoration:none}
.paper-card:hover{border-color:var(--border-hi)}
.pc-title{font-family:var(--serif);font-size:16px;color:var(--fg)}
.pc-meta{margin-top:6px;display:flex;gap:12px;font-family:var(--mono);font-size:11px;color:var(--fg-faint)}
.pc-doi{color:var(--teal)}
"""
