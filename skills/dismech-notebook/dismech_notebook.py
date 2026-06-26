#!/usr/bin/env python3
"""
DisMech Notebook — Query CLI for dm-* entities in alhazen_notebook.

Reads disease mechanisms mapped into the Alhazen notebook's ICE model
via GLAV rules. All queries run against the alhazen_notebook database.

Usage:
    python dismech_notebook.py stats
    python dismech_notebook.py list-diseases [--category Mendelian] [--limit 50] [--offset 0]
    python dismech_notebook.py show-disease --name "Achondroplasia"
    python dismech_notebook.py search --query "FGFR3" [--limit 50]
"""

import argparse
import json
import os
import sys

def escape_string(s: str) -> str:
    """Escape special characters for TypeQL string literals."""
    if s is None:
        return ""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")

TYPEDB_HOST = os.getenv("TYPEDB_HOST", "localhost")
TYPEDB_PORT = int(os.getenv("TYPEDB_PORT", "1729"))
TYPEDB_DATABASE = os.getenv("TYPEDB_DATABASE", "alh_deep_research")
TYPEDB_USERNAME = os.getenv("TYPEDB_USERNAME", "admin")
TYPEDB_PASSWORD = os.getenv("TYPEDB_PASSWORD", "password")


def _get_driver():
    from typedb.driver import Credentials, DriverOptions, TypeDB
    return TypeDB.driver(
        f"{TYPEDB_HOST}:{TYPEDB_PORT}",
        Credentials(TYPEDB_USERNAME, TYPEDB_PASSWORD),
        DriverOptions(is_tls_enabled=False),
    )


def _count(driver, type_name: str) -> int:
    from typedb.driver import TransactionType
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        r = list(tx.query(f"match $x isa {type_name}; reduce $c = count;").resolve())
    return r[0].get("c").get_integer() if r else 0


def _safe(val, default=""):
    """Safely extract a value that might be None."""
    return val if val is not None else default


# ── stats ─────────────────────────────────────────────────────────────────────

def cmd_stats(args):
    driver = _get_driver()
    types = {
        "diseases": "dm-disease",
        "mechanisms": "dm-mechanism",
        "phenotypes": "dm-phenotype",
        "genetic": "dm-genetic",
        "treatments": "dm-treatment",
        "causal_edges": "dm-causal-edge",
        "evidence_notes": "dm-evidence-note",
        "papers": "scilit-paper",
        "gene_descriptors": "dm-gene-descriptor",
        "phenotype_descriptors": "dm-phenotype-descriptor",
        "celltype_descriptors": "dm-celltype-descriptor",
        "process_descriptors": "dm-process-descriptor",
    }
    result = {}
    for key, tname in types.items():
        result[key] = _count(driver, tname)
    driver.close()
    print(json.dumps({"success": True, **result}))


# ── list-diseases ─────────────────────────────────────────────────────────────

def cmd_list_diseases(args):
    from typedb.driver import TransactionType
    driver = _get_driver()

    # Build query
    match_clause = "$d isa dm-disease, has name $n"
    if args.category:
        match_clause += f', has dm-category "{escape_string(args.category)}"'
    match_clause += ";"

    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        results = list(tx.query(
            f'match {match_clause} fetch {{ "name": $n, "id": $d.id, "category": $d.dm-category, "mondo_id": $d.dm-mondo-id }};'
        ).resolve())

    # Sort by name
    diseases = sorted(results, key=lambda r: r.get("name", "").lower())
    total = len(diseases)

    # Apply pagination
    offset = args.offset or 0
    limit = args.limit or 50
    page = diseases[offset:offset + limit]

    driver.close()
    print(json.dumps({
        "success": True,
        "total": total,
        "offset": offset,
        "limit": limit,
        "diseases": page,
    }))


# ── show-disease ──────────────────────────────────────────────────────────────

def cmd_show_disease(args):
    from typedb.driver import TransactionType
    driver = _get_driver()
    name = args.name
    esc = escape_string(name)

    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        # Basic disease info
        basic = list(tx.query(
            f'match $d isa dm-disease, has name "{esc}"; '
            f'fetch {{ "name": $d.name, "id": $d.id, "description": $d.description, '
            f'"category": $d.dm-category, "mondo_id": $d.dm-mondo-id }};'
        ).resolve())
        if not basic:
            driver.close()
            print(json.dumps({"success": False, "error": f"Disease not found: {name}"}))
            sys.exit(1)
        disease = basic[0]

        # Mechanisms
        mechanisms = list(tx.query(
            f'match $d isa dm-disease, has name "{esc}"; '
            f'(dm-dhm-disease: $d, dm-dhm-mechanism: $m) isa dm-disease-has-mechanism; '
            f'fetch {{ "name": $m.name, "id": $m.id, "description": $m.description, '
            f'"confidence": $m.dm-mechanism-confidence }};'
        ).resolve())

        # For each mechanism, get genes, cell types, processes, downstream
        mech_details = []
        for mech in mechanisms:
            mech_name = mech.get("name", "")
            mech_esc = escape_string(mech_name)
            detail = {**mech}

            # Genes
            genes = list(tx.query(
                f'match $m isa dm-mechanism, has name "{mech_esc}"; '
                f'(dm-ga-subject: $m, dm-ga-gene: $g) isa dm-gene-annotation; '
                f'fetch {{ "gene": $g.name, "preferred_term": $g.dm-preferred-term }};'
            ).resolve())
            detail["genes"] = genes

            # Cell types
            cell_types = list(tx.query(
                f'match $m isa dm-mechanism, has name "{mech_esc}"; '
                f'(dm-mc-mechanism: $m, dm-mc-celltype: $ct) isa dm-mechanism-celltype; '
                f'fetch {{ "celltype": $ct.dm-preferred-term }};'
            ).resolve())
            detail["cell_types"] = [c.get("celltype", "") for c in cell_types]

            # Biological processes
            processes = list(tx.query(
                f'match $m isa dm-mechanism, has name "{mech_esc}"; '
                f'(dm-mp-mechanism: $m, dm-mp-process: $p) isa dm-mechanism-process; '
                f'fetch {{ "process": $p.dm-preferred-term }};'
            ).resolve())
            detail["processes"] = [p.get("process", "") for p in processes]

            # Downstream causal edges
            downstream = list(tx.query(
                f'match $m isa dm-mechanism, has name "{mech_esc}"; '
                f'(dm-md-mechanism: $m, dm-md-edge: $e) isa dm-mechanism-downstream; '
                f'fetch {{ "target": $e.name }};'
            ).resolve())
            detail["downstream"] = [d.get("target", "") for d in downstream]

            # Evidence for this mechanism
            evidence = list(tx.query(
                f'match $m isa dm-mechanism, has name "{mech_esc}"; '
                f'(note: $n, subject: $m) isa alh-aboutness; '
                f'$n isa dm-evidence-note; '
                f'fetch {{ "pmid": $n.dm-reference-pmid, "support": $n.dm-support-rating, '
                f'"snippet": $n.dm-snippet }};'
            ).resolve())
            detail["evidence"] = evidence

            mech_details.append(detail)

        # Phenotypes
        phenotypes = list(tx.query(
            f'match $d isa dm-disease, has name "{esc}"; '
            f'(dm-dhp-disease: $d, dm-dhp-phenotype: $p) isa dm-disease-has-phenotype; '
            f'fetch {{ "name": $p.name, "id": $p.id, "description": $p.description, '
            f'"hpo_id": $p.dm-hpo-id, "frequency": $p.dm-frequency, '
            f'"severity": $p.dm-severity, "onset": $p.dm-onset-category }};'
        ).resolve())

        # Genetic
        genetic = list(tx.query(
            f'match $d isa dm-disease, has name "{esc}"; '
            f'(dm-dhg-disease: $d, dm-dhg-genetic: $g) isa dm-disease-has-genetic; '
            f'fetch {{ "name": $g.name, "id": $g.id, "description": $g.description, '
            f'"relationship_type": $g.dm-relationship-type, '
            f'"association": $g.dm-association }};'
        ).resolve())

        # Treatments
        treatments = list(tx.query(
            f'match $d isa dm-disease, has name "{esc}"; '
            f'(dm-dht-disease: $d, dm-dht-treatment: $t) isa dm-disease-has-treatment; '
            f'fetch {{ "name": $t.name, "id": $t.id, "description": $t.description }};'
        ).resolve())

    driver.close()

    print(json.dumps({
        "success": True,
        "disease": disease,
        "mechanisms": mech_details,
        "phenotypes": phenotypes,
        "genetic": genetic,
        "treatments": treatments,
    }))


# ── search ────────────────────────────────────────────────────────────────────

def cmd_search(args):
    from typedb.driver import TransactionType
    driver = _get_driver()
    query = args.query.lower()
    limit = args.limit or 50

    hits = []
    seen = set()

    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        # Search disease names
        diseases = list(tx.query(
            'match $d isa dm-disease, has name $n; '
            'fetch { "name": $n, "category": $d.dm-category };'
        ).resolve())
        for d in diseases:
            n = d.get("name", "")
            if query in n.lower() and n not in seen:
                hits.append({"disease": n, "match_type": "name", "category": _safe(d.get("category"))})
                seen.add(n)

        # Search mechanism names (linked to disease)
        mechs = list(tx.query(
            'match $d isa dm-disease, has name $dn; '
            '(dm-dhm-disease: $d, dm-dhm-mechanism: $m) isa dm-disease-has-mechanism; '
            '$m has name $mn; '
            'fetch { "disease": $dn, "mechanism": $mn };'
        ).resolve())
        for m in mechs:
            mn = m.get("mechanism", "")
            dn = m.get("disease", "")
            if query in mn.lower() and dn not in seen:
                hits.append({"disease": dn, "match_type": "mechanism", "mechanism": mn})
                seen.add(dn)

    driver.close()

    print(json.dumps({
        "success": True,
        "query": args.query,
        "count": min(len(hits), limit),
        "results": hits[:limit],
    }))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DisMech Notebook — Query dm-* entities")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("stats", help="Show entity counts")

    list_p = sub.add_parser("list-diseases", help="List diseases")
    list_p.add_argument("--category", default=None, help="Filter by category")
    list_p.add_argument("--limit", type=int, default=50)
    list_p.add_argument("--offset", type=int, default=0)

    show_p = sub.add_parser("show-disease", help="Show full disease detail")
    show_p.add_argument("--name", required=True, help="Disease name")

    search_p = sub.add_parser("search", help="Search diseases and mechanisms")
    search_p.add_argument("--query", required=True, help="Search text")
    search_p.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    dispatch = {
        "stats": cmd_stats,
        "list-diseases": cmd_list_diseases,
        "show-disease": cmd_show_disease,
        "search": cmd_search,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
