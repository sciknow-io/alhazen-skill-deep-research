#!/usr/bin/env python3
"""
DisMech — Disease Mechanism Knowledge Graph CLI.

Bulk-ingests the dismech knowledge base into TypeDB 3.x and provides
query commands for exploring disease mechanisms, phenotypes, and genes.

Usage:
    python dismech.py ingest --source /path/to/dismech/kb/disorders [--max N]
    python dismech.py show-disease --name "Achondroplasia"
    python dismech.py list-diseases [--category Genetic]
    python dismech.py search --query "FGFR3 growth plate"
    python dismech.py stats
    python dismech.py serve [--port 7777]

TypeDB must be running with the dismech schema loaded (run alhazen_core.py init first).
"""

import argparse
import http.server
import json
import os
import re
import sys
import threading
import urllib.parse
from pathlib import Path

import yaml
from tqdm import tqdm

TYPEDB_HOST = os.getenv("TYPEDB_HOST", "localhost")
TYPEDB_PORT = int(os.getenv("TYPEDB_PORT", "1729"))
TYPEDB_DATABASE = os.getenv("TYPEDB_DATABASE", "dismech")
TYPEDB_USERNAME = os.getenv("TYPEDB_USERNAME", "admin")
TYPEDB_PASSWORD = os.getenv("TYPEDB_PASSWORD", "password")


# ── TypeDB helpers ─────────────────────────────────────────────────────────────


def _get_driver():
    """Return a TypeDB driver connection."""
    from typedb.driver import Credentials, DriverOptions, TypeDB
    return TypeDB.driver(
        f"{TYPEDB_HOST}:{TYPEDB_PORT}",
        Credentials(TYPEDB_USERNAME, TYPEDB_PASSWORD),
        DriverOptions(is_tls_enabled=False),
    )


def _escape(s: str) -> str:
    """Escape backslashes and double-quotes for TypeQL string literals."""
    if not isinstance(s, str):
        s = str(s)
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _truncate(s: str, max_len: int = 2000) -> str:
    """Truncate a string to max_len characters."""
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def _count_query(driver, query: str) -> int:
    """Run a reduce count query and return the integer result."""
    from typedb.driver import TransactionType
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        results = list(tx.query(query).resolve())
    if not results:
        return 0
    v = results[0].get("c")
    return v.get_integer() if v is not None else 0


def _iso_to_typedb_datetime(iso_string: str) -> str | None:
    """Convert ISO 8601 datetime string to TypeDB datetime format.

    TypeDB expects format: YYYY-MM-DDTHH:MM:SS (no timezone suffix)
    Input example: "2025-12-19T01:18:09Z"
    Output example: "2025-12-19T01:18:09"
    """
    if not iso_string or not isinstance(iso_string, str):
        return None
    cleaned = re.sub(r'[Z]$|[+-]\d{2}:?\d{2}$', '', iso_string.strip())
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$', cleaned):
        return cleaned
    return None


def _get_or_create_term(driver, term_id: str, term_label: str = "") -> None:
    """Ensure a term entity with the given ID exists (get-or-create, keyed by id)."""
    from typedb.driver import TransactionType
    if not term_id:
        return
    esc_id = _escape(term_id)
    count = _count_query(driver, f'match $t isa term, has id "{esc_id}"; reduce $c = count;')
    if count > 0:
        return
    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
        attrs = [f'has id "{esc_id}"']
        if term_label:
            attrs.append(f'has label-attr "{_escape(term_label)}"')
        tx.query(f'insert $t isa term, {", ".join(attrs)};').resolve()
        tx.commit()


# ── Ingestion: shared evidence helper ─────────────────────────────────────────


def _ingest_evidence_items(driver, parent_match: str, parent_role: str, evidence_list) -> list:
    """Insert evidenceitem entities linked to a parent entity via the evidence relation.

    parent_match: TypeQL fragment that binds $parent, e.g.
        '$d isa disease, has name "X"; (disease: $d, pathophysiology: $parent) isa pathophysiology-rel; $parent has name "Y";'
    parent_role: the role name $parent plays in the evidence relation, e.g. 'pathophysiology'
    """
    from typedb.driver import TransactionType
    errors = []
    for ev in (evidence_list or []):
        if not isinstance(ev, dict):
            continue
        ref = (ev.get("reference") or "").strip()
        if not ref:
            continue
        try:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                attrs = [f'has reference "{_escape(ref)}"']
                if ev.get("reference_title"):
                    attrs.append(f'has reference-title "{_escape(_truncate(str(ev["reference_title"]), 500))}"')
                if ev.get("supports"):
                    attrs.append(f'has supports "{_escape(str(ev["supports"]))}"')
                if ev.get("evidence_source"):
                    attrs.append(f'has evidence-source "{_escape(str(ev["evidence_source"]))}"')
                if ev.get("snippet"):
                    attrs.append(f'has snippet "{_escape(_truncate(str(ev["snippet"]), 500))}"')
                if ev.get("explanation"):
                    attrs.append(f'has explanation "{_escape(_truncate(str(ev["explanation"])))}"')
                q = (
                    f'match {parent_match} '
                    f'insert $ev isa evidenceitem, {", ".join(attrs)}; '
                    f'(evidenceitem: $ev, {parent_role}: $parent) isa evidence;'
                )
                tx.query(q).resolve()
                tx.commit()
        except Exception as e:
            errors.append(f"evidence {ref}: {e}")
    return errors


# ── Ingestion: Tier 1 — Disease entity ────────────────────────────────────────


def _ingest_tier1_disease(driver, data: dict) -> list:
    """Insert disease entity with full scalar attributes."""
    from typedb.driver import TransactionType
    name = data.get("name", "").strip()
    errors = []
    try:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            attrs = [f'has name "{_escape(name)}"']
            if data.get("category"):
                attrs.append(f'has category "{_escape(str(data["category"]))}"')
            if data.get("description"):
                attrs.append(f'has description "{_escape(_truncate(str(data["description"])))}"')
            if data.get("creation_date"):
                attrs.append(f'has creation-date "{_escape(str(data["creation_date"]))}"')
            if data.get("updated_date"):
                attrs.append(f'has updated-date "{_escape(str(data["updated_date"]))}"')
            if data.get("notes"):
                attrs.append(f'has notes "{_escape(_truncate(str(data["notes"])))}"')
            for parent in (data.get("parents") or []):
                if isinstance(parent, str) and parent.strip():
                    attrs.append(f'has parents "{_escape(parent.strip())}"')
            for synonym in (data.get("synonyms") or []):
                if isinstance(synonym, str) and synonym.strip():
                    attrs.append(f'has synonyms "{_escape(synonym.strip())}"')
            tx.query(f'insert $d isa disease, {", ".join(attrs)};').resolve()
            tx.commit()
    except Exception as e:
        errors.append(f"disease entity: {e}")
    return errors


# ── Ingestion: Tier 2 — Disease term (MONDO binding) ──────────────────────────


def _ingest_tier2_disease_term(driver, name: str, data: dict) -> list:
    """Insert diseasedescriptor + optional MONDO term entity + relations."""
    from typedb.driver import TransactionType
    errors = []
    disease_term = data.get("disease_term")
    if not disease_term or not isinstance(disease_term, dict):
        return errors
    preferred = (disease_term.get("preferred_term") or "").strip()
    if not preferred:
        return errors

    term_data = disease_term.get("term") or {}
    mondo_id = (term_data.get("id") or "").strip()
    mondo_label = (term_data.get("label") or "").strip()

    try:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            q = (
                f'match $d isa disease, has name "{_escape(name)}"; '
                f'insert $dt isa diseasedescriptor, has preferred-term "{_escape(preferred)}"; '
                f'(disease: $d, diseasedescriptor: $dt) isa disease-term;'
            )
            tx.query(q).resolve()
            tx.commit()
    except Exception as e:
        errors.append(f"disease-term: {e}")
        return errors

    if mondo_id:
        try:
            _get_or_create_term(driver, mondo_id, mondo_label)
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                q = (
                    f'match $d isa disease, has name "{_escape(name)}"; '
                    f'(disease: $d, diseasedescriptor: $dt) isa disease-term; '
                    f'$dt has preferred-term "{_escape(preferred)}"; '
                    f'$t isa term, has id "{_escape(mondo_id)}"; '
                    f'insert (descriptor: $dt, term: $t) isa term-rel;'
                )
                tx.query(q).resolve()
                tx.commit()
        except Exception as e:
            errors.append(f"mondo term-rel: {e}")

    return errors


# ── Ingestion: Tier 3 — Pathophysiology mechanisms ────────────────────────────


def _ingest_tier3_pathophysiology(driver, name: str, data: dict) -> tuple:
    """Insert pathophysiology mechanisms with genes, cell types, bio processes, evidence, downstream."""
    from typedb.driver import TransactionType
    errors = []
    count = 0

    for mech in (data.get("pathophysiology") or []):
        if not isinstance(mech, dict):
            continue
        mech_name = (mech.get("name") or "").strip()
        if not mech_name:
            continue

        # Insert pathophysiology entity + pathophysiology-rel
        try:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                mech_attrs = [f'has name "{_escape(mech_name)}"']
                if mech.get("description"):
                    mech_attrs.append(f'has description "{_escape(_truncate(str(mech["description"])))}"')
                if mech.get("mechanism_confidence"):
                    mech_attrs.append(f'has mechanism-confidence "{_escape(str(mech["mechanism_confidence"]))}"')
                if mech.get("consequence"):
                    mech_attrs.append(f'has consequence "{_escape(_truncate(str(mech["consequence"])))}"')
                if mech.get("notes"):
                    mech_attrs.append(f'has notes "{_escape(_truncate(str(mech["notes"])))}"')
                q = (
                    f'match $d isa disease, has name "{_escape(name)}"; '
                    f'insert $p isa pathophysiology, {", ".join(mech_attrs)}; '
                    f'(disease: $d, pathophysiology: $p) isa pathophysiology-rel;'
                )
                tx.query(q).resolve()
                tx.commit()
            count += 1
        except Exception as e:
            errors.append(f"pathophysiology '{mech_name}': {e}")
            continue

        # Match clause used for subsequent insertions linked to this mechanism
        mech_match = (
            f'$d isa disease, has name "{_escape(name)}"; '
            f'(disease: $d, pathophysiology: $parent) isa pathophysiology-rel; '
            f'$parent has name "{_escape(mech_name)}";'
        )

        # Primary gene (singular gene: field)
        gene_data = mech.get("gene")
        if isinstance(gene_data, dict):
            gene_preferred = (gene_data.get("preferred_term") or "").strip()
            gene_term = gene_data.get("term") or {}
            gene_term_id = (gene_term.get("id") or "").strip()
            gene_term_label = (gene_term.get("label") or "").strip()
            gene_modifier = (gene_data.get("modifier") or "").strip()
            if gene_preferred:
                try:
                    if gene_term_id:
                        _get_or_create_term(driver, gene_term_id, gene_term_label)
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        gd_attrs = [f'has preferred-term "{_escape(gene_preferred)}"']
                        if gene_modifier:
                            gd_attrs.append(f'has modifier "{_escape(gene_modifier)}"')
                        q = (
                            f'match {mech_match} '
                            f'insert $gd isa genedescriptor, {", ".join(gd_attrs)}; '
                            f'(pathophysiology: $parent, genedescriptor: $gd) isa gene;'
                        )
                        tx.query(q).resolve()
                        tx.commit()
                    if gene_term_id:
                        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                            q = (
                                f'match {mech_match} '
                                f'(pathophysiology: $parent, genedescriptor: $gd) isa gene; '
                                f'$gd has preferred-term "{_escape(gene_preferred)}"; '
                                f'$t isa term, has id "{_escape(gene_term_id)}"; '
                                f'insert (descriptor: $gd, term: $t) isa term-rel;'
                            )
                            tx.query(q).resolve()
                            tx.commit()
                except Exception as e:
                    errors.append(f"  gene descriptor '{gene_preferred}': {e}")

        # Multiple genes (genes: list)
        for g in (mech.get("genes") or []):
            if not isinstance(g, dict):
                continue
            gp = (g.get("preferred_term") or "").strip()
            gt = g.get("term") or {}
            gt_id = (gt.get("id") or "").strip()
            gt_label = (gt.get("label") or "").strip()
            if not gp:
                continue
            try:
                if gt_id:
                    _get_or_create_term(driver, gt_id, gt_label)
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    q = (
                        f'match {mech_match} '
                        f'insert $gd isa genedescriptor, has preferred-term "{_escape(gp)}"; '
                        f'(pathophysiology: $parent, genedescriptor: $gd) isa genes;'
                    )
                    tx.query(q).resolve()
                    tx.commit()
                if gt_id:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        q = (
                            f'match {mech_match} '
                            f'(pathophysiology: $parent, genedescriptor: $gd) isa genes; '
                            f'$gd has preferred-term "{_escape(gp)}"; '
                            f'$t isa term, has id "{_escape(gt_id)}"; '
                            f'insert (descriptor: $gd, term: $t) isa term-rel;'
                        )
                        tx.query(q).resolve()
                        tx.commit()
            except Exception as e:
                errors.append(f"  genes descriptor '{gp}': {e}")

        # Cell types
        for ct in (mech.get("cell_types") or []):
            if not isinstance(ct, dict):
                continue
            ct_preferred = (ct.get("preferred_term") or "").strip()
            ct_term = ct.get("term") or {}
            ct_id = (ct_term.get("id") or "").strip()
            ct_label = (ct_term.get("label") or "").strip()
            if not ct_preferred:
                continue
            try:
                if ct_id:
                    _get_or_create_term(driver, ct_id, ct_label)
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    q = (
                        f'match {mech_match} '
                        f'insert $ct isa celltypedescriptor, has preferred-term "{_escape(ct_preferred)}"; '
                        f'(pathophysiology: $parent, celltypedescriptor: $ct) isa cell-types;'
                    )
                    tx.query(q).resolve()
                    tx.commit()
                if ct_id:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        q = (
                            f'match {mech_match} '
                            f'(pathophysiology: $parent, celltypedescriptor: $ct) isa cell-types; '
                            f'$ct has preferred-term "{_escape(ct_preferred)}"; '
                            f'$t isa term, has id "{_escape(ct_id)}"; '
                            f'insert (descriptor: $ct, term: $t) isa term-rel;'
                        )
                        tx.query(q).resolve()
                        tx.commit()
            except Exception as e:
                errors.append(f"  cell_type '{ct_preferred}': {e}")

        # Biological processes
        for bp in (mech.get("biological_processes") or []):
            if not isinstance(bp, dict):
                continue
            bp_preferred = (bp.get("preferred_term") or "").strip()
            bp_term = bp.get("term") or {}
            bp_id = (bp_term.get("id") or "").strip()
            bp_label = (bp_term.get("label") or "").strip()
            bp_modifier = (bp.get("modifier") or "").strip()
            if not bp_preferred:
                continue
            try:
                if bp_id:
                    _get_or_create_term(driver, bp_id, bp_label)
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    bp_attrs = [f'has preferred-term "{_escape(bp_preferred)}"']
                    if bp_modifier:
                        bp_attrs.append(f'has modifier "{_escape(bp_modifier)}"')
                    q = (
                        f'match {mech_match} '
                        f'insert $bp isa biologicalprocessdescriptor, {", ".join(bp_attrs)}; '
                        f'(pathophysiology: $parent, biologicalprocessdescriptor: $bp) isa biological-processes;'
                    )
                    tx.query(q).resolve()
                    tx.commit()
                if bp_id:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        q = (
                            f'match {mech_match} '
                            f'(pathophysiology: $parent, biologicalprocessdescriptor: $bp) isa biological-processes; '
                            f'$bp has preferred-term "{_escape(bp_preferred)}"; '
                            f'$t isa term, has id "{_escape(bp_id)}"; '
                            f'insert (descriptor: $bp, term: $t) isa term-rel;'
                        )
                        tx.query(q).resolve()
                        tx.commit()
            except Exception as e:
                errors.append(f"  biological_process '{bp_preferred}': {e}")

        # Downstream causal edges (target is a string name of another mechanism)
        for ds in (mech.get("downstream") or []):
            if not isinstance(ds, dict):
                continue
            target = (ds.get("target") or "").strip()
            if not target:
                continue
            try:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    q = (
                        f'match {mech_match} '
                        f'insert $ce isa causaledge, has target "{_escape(target)}"; '
                        f'(pathophysiology: $parent, causaledge: $ce) isa downstream;'
                    )
                    tx.query(q).resolve()
                    tx.commit()
            except Exception as e:
                errors.append(f"  downstream '{target}': {e}")

        # Evidence items
        errors.extend(_ingest_evidence_items(driver, mech_match, "pathophysiology", mech.get("evidence")))

    return count, errors


# ── Ingestion: Tier 4 — Phenotypes ────────────────────────────────────────────


def _ingest_tier4_phenotypes(driver, name: str, data: dict) -> list:
    """Insert phenotype entities with HPO terms and evidence."""
    from typedb.driver import TransactionType
    errors = []

    for ph in (data.get("phenotypes") or []):
        if not isinstance(ph, dict):
            continue
        ph_name = (ph.get("name") or "").strip()
        if not ph_name:
            continue

        try:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                ph_attrs = [f'has name "{_escape(ph_name)}"']
                if ph.get("description"):
                    ph_attrs.append(f'has description "{_escape(_truncate(str(ph["description"])))}"')
                if ph.get("frequency"):
                    # Store HP frequency code (e.g. HP_0040281) in subtype-attr
                    ph_attrs.append(f'has subtype-attr "{_escape(str(ph["frequency"]))}"')
                q = (
                    f'match $d isa disease, has name "{_escape(name)}"; '
                    f'insert $ph isa phenotype, {", ".join(ph_attrs)}; '
                    f'(disease: $d, phenotype: $ph) isa phenotypes;'
                )
                tx.query(q).resolve()
                tx.commit()
        except Exception as e:
            errors.append(f"phenotype '{ph_name}': {e}")
            continue

        ph_match = (
            f'$d isa disease, has name "{_escape(name)}"; '
            f'(disease: $d, phenotype: $parent) isa phenotypes; '
            f'$parent has name "{_escape(ph_name)}";'
        )

        # Phenotype term (HPO)
        pt_data = ph.get("phenotype_term")
        if isinstance(pt_data, dict):
            pt_preferred = (pt_data.get("preferred_term") or "").strip()
            pt_term = pt_data.get("term") or {}
            pt_id = (pt_term.get("id") or "").strip()
            pt_label = (pt_term.get("label") or "").strip()
            if pt_preferred:
                try:
                    if pt_id:
                        _get_or_create_term(driver, pt_id, pt_label)
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        q = (
                            f'match {ph_match} '
                            f'insert $pd isa phenotypedescriptor, has preferred-term "{_escape(pt_preferred)}"; '
                            f'(phenotype: $parent, phenotypedescriptor: $pd) isa phenotype-term;'
                        )
                        tx.query(q).resolve()
                        tx.commit()
                    if pt_id:
                        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                            q = (
                                f'match {ph_match} '
                                f'(phenotype: $parent, phenotypedescriptor: $pd) isa phenotype-term; '
                                f'$pd has preferred-term "{_escape(pt_preferred)}"; '
                                f'$t isa term, has id "{_escape(pt_id)}"; '
                                f'insert (descriptor: $pd, term: $t) isa term-rel;'
                            )
                            tx.query(q).resolve()
                            tx.commit()
                except Exception as e:
                    errors.append(f"  phenotype-term '{pt_preferred}': {e}")

        errors.extend(_ingest_evidence_items(driver, ph_match, "phenotype", ph.get("evidence")))

    return errors


# ── Ingestion: Tier 5 — Inheritance ───────────────────────────────────────────


def _ingest_tier5_inheritance(driver, name: str, data: dict) -> list:
    """Insert inheritance entities with evidence."""
    from typedb.driver import TransactionType
    errors = []

    for inh in (data.get("inheritance") or []):
        if not isinstance(inh, dict):
            continue
        inh_name = (inh.get("name") or "").strip()
        if not inh_name:
            continue

        try:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                inh_attrs = [f'has name "{_escape(inh_name)}"']
                if inh.get("penetrance"):
                    inh_attrs.append(f'has penetrance "{_escape(str(inh["penetrance"]))}"')
                if inh.get("de_novo_rate"):
                    inh_attrs.append(f'has de-novo-rate "{_escape(str(inh["de_novo_rate"]))}"')
                if inh.get("parent_of_origin_effect"):
                    inh_attrs.append(f'has parent-of-origin-effect "{_escape(_truncate(str(inh["parent_of_origin_effect"])))}"')
                if inh.get("description"):
                    inh_attrs.append(f'has description "{_escape(_truncate(str(inh["description"])))}"')
                q = (
                    f'match $d isa disease, has name "{_escape(name)}"; '
                    f'insert $i isa inheritance, {", ".join(inh_attrs)}; '
                    f'(disease: $d, inheritance: $i) isa inheritance-rel;'
                )
                tx.query(q).resolve()
                tx.commit()
        except Exception as e:
            errors.append(f"inheritance '{inh_name}': {e}")
            continue

        inh_match = (
            f'$d isa disease, has name "{_escape(name)}"; '
            f'(disease: $d, inheritance: $parent) isa inheritance-rel; '
            f'$parent has name "{_escape(inh_name)}";'
        )

        # Inheritance term
        it_data = inh.get("inheritance_term")
        if isinstance(it_data, dict):
            it_preferred = (it_data.get("preferred_term") or "").strip()
            it_term = it_data.get("term") or {}
            it_id = (it_term.get("id") or "").strip()
            it_label = (it_term.get("label") or "").strip()
            if it_preferred:
                try:
                    if it_id:
                        _get_or_create_term(driver, it_id, it_label)
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        q = (
                            f'match {inh_match} '
                            f'insert $id isa inheritancedescriptor, has preferred-term "{_escape(it_preferred)}"; '
                            f'(inheritance: $parent, inheritancedescriptor: $id) isa inheritance-term;'
                        )
                        tx.query(q).resolve()
                        tx.commit()
                    if it_id:
                        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                            q = (
                                f'match {inh_match} '
                                f'(inheritance: $parent, inheritancedescriptor: $id) isa inheritance-term; '
                                f'$id has preferred-term "{_escape(it_preferred)}"; '
                                f'$t isa term, has id "{_escape(it_id)}"; '
                                f'insert (descriptor: $id, term: $t) isa term-rel;'
                            )
                            tx.query(q).resolve()
                            tx.commit()
                except Exception as e:
                    errors.append(f"  inheritance-term '{it_preferred}': {e}")

        errors.extend(_ingest_evidence_items(driver, inh_match, "inheritance", inh.get("evidence")))

    return errors


# ── Ingestion: Tier 6 — Genetic entries ───────────────────────────────────────


def _ingest_tier6_genetic(driver, name: str, data: dict) -> list:
    """Insert genetic entries with gene terms, variants, and evidence."""
    from typedb.driver import TransactionType
    errors = []

    for idx, gen in enumerate(data.get("genetic") or []):
        if not isinstance(gen, dict):
            continue
        gen_name = (gen.get("name") or f"genetic-{idx}").strip()

        try:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                gen_attrs = [f'has name "{_escape(gen_name)}"']
                if gen.get("association"):
                    gen_attrs.append(f'has association "{_escape(str(gen["association"]))}"')
                if gen.get("relationship_type"):
                    gen_attrs.append(f'has relationship-type "{_escape(str(gen["relationship_type"]))}"')
                if gen.get("notes"):
                    gen_attrs.append(f'has notes "{_escape(_truncate(str(gen["notes"])))}"')
                q = (
                    f'match $d isa disease, has name "{_escape(name)}"; '
                    f'insert $g isa genetic, {", ".join(gen_attrs)}; '
                    f'(disease: $d, genetic: $g) isa genetic-rel;'
                )
                tx.query(q).resolve()
                tx.commit()
        except Exception as e:
            errors.append(f"genetic '{gen_name}': {e}")
            continue

        gen_match = (
            f'$d isa disease, has name "{_escape(name)}"; '
            f'(disease: $d, genetic: $parent) isa genetic-rel; '
            f'$parent has name "{_escape(gen_name)}";'
        )

        # Gene term
        gt_data = gen.get("gene_term")
        if isinstance(gt_data, dict):
            gt_preferred = (gt_data.get("preferred_term") or "").strip()
            gt_term = gt_data.get("term") or {}
            gt_id = (gt_term.get("id") or "").strip()
            gt_label = (gt_term.get("label") or "").strip()
            if gt_preferred:
                try:
                    if gt_id:
                        _get_or_create_term(driver, gt_id, gt_label)
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        q = (
                            f'match {gen_match} '
                            f'insert $gd isa genedescriptor, has preferred-term "{_escape(gt_preferred)}"; '
                            f'(genetic: $parent, genedescriptor: $gd) isa gene-term;'
                        )
                        tx.query(q).resolve()
                        tx.commit()
                except Exception as e:
                    errors.append(f"  genetic gene-term '{gt_preferred}': {e}")

        # Variants
        for var in (gen.get("variants") or []):
            if not isinstance(var, dict):
                continue
            var_name = (var.get("name") or "").strip()
            if not var_name:
                continue
            try:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    var_attrs = [f'has name "{_escape(var_name)}"']
                    if var.get("description"):
                        var_attrs.append(f'has description "{_escape(_truncate(str(var["description"])))}"')
                    if var.get("clinical_significance"):
                        var_attrs.append(f'has clinical-significance "{_escape(str(var["clinical_significance"]))}"')
                    q = (
                        f'match {gen_match} '
                        f'insert $v isa variant, {", ".join(var_attrs)}; '
                        f'(genetic: $parent, variant: $v) isa variants;'
                    )
                    tx.query(q).resolve()
                    tx.commit()
            except Exception as e:
                errors.append(f"  variant '{var_name}': {e}")
                continue

            var_match = (
                f'{gen_match} '
                f'(genetic: $parent, variant: $vparent) isa variants; '
                f'$vparent has name "{_escape(var_name)}";'
            )
            errors.extend(_ingest_evidence_items(
                driver,
                var_match.replace("$parent", "$gparent").replace("$vparent", "$parent"),
                "variant",
                var.get("evidence"),
            ))

        errors.extend(_ingest_evidence_items(driver, gen_match, "genetic", gen.get("evidence")))

    return errors


# ── Ingestion: Tier 7 — Treatments ────────────────────────────────────────────


def _ingest_tier7_treatments(driver, name: str, data: dict) -> list:
    """Insert treatment entities with descriptors and evidence."""
    from typedb.driver import TransactionType
    errors = []

    for trt in (data.get("treatments") or []):
        if not isinstance(trt, dict):
            continue
        trt_name = (trt.get("name") or "").strip()
        if not trt_name:
            continue

        try:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                trt_attrs = [f'has name "{_escape(trt_name)}"']
                if trt.get("description"):
                    trt_attrs.append(f'has description "{_escape(_truncate(str(trt["description"])))}"')
                if trt.get("notes"):
                    trt_attrs.append(f'has notes "{_escape(_truncate(str(trt["notes"])))}"')
                q = (
                    f'match $d isa disease, has name "{_escape(name)}"; '
                    f'insert $t isa treatment, {", ".join(trt_attrs)}; '
                    f'(disease: $d, treatment: $t) isa treatments;'
                )
                tx.query(q).resolve()
                tx.commit()
        except Exception as e:
            errors.append(f"treatment '{trt_name}': {e}")
            continue

        trt_match = (
            f'$d isa disease, has name "{_escape(name)}"; '
            f'(disease: $d, treatment: $parent) isa treatments; '
            f'$parent has name "{_escape(trt_name)}";'
        )

        # Treatment term + therapeutic agents
        tt_data = trt.get("treatment_term")
        if isinstance(tt_data, dict):
            tt_preferred = (tt_data.get("preferred_term") or "").strip()
            if tt_preferred:
                try:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        q = (
                            f'match {trt_match} '
                            f'insert $td isa treatmentdescriptor, has preferred-term "{_escape(tt_preferred)}"; '
                            f'(treatment: $parent, treatmentdescriptor: $td) isa treatment-term;'
                        )
                        tx.query(q).resolve()
                        tx.commit()
                except Exception as e:
                    errors.append(f"  treatment-term '{tt_preferred}': {e}")

                for agent in (tt_data.get("therapeutic_agent") or []):
                    if not isinstance(agent, dict):
                        continue
                    agent_preferred = (agent.get("preferred_term") or "").strip()
                    agent_term = agent.get("term") or {}
                    agent_id = (agent_term.get("id") or "").strip()
                    agent_label = (agent_term.get("label") or "").strip()
                    if not agent_preferred:
                        continue
                    try:
                        if agent_id:
                            _get_or_create_term(driver, agent_id, agent_label)
                        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                            q = (
                                f'match {trt_match} '
                                f'(treatment: $parent, treatmentdescriptor: $td) isa treatment-term; '
                                f'$td has preferred-term "{_escape(tt_preferred)}"; '
                                f'insert $ca isa chemicalentitydescriptor, has preferred-term "{_escape(agent_preferred)}"; '
                                f'(treatmentdescriptor: $td, chemicalentitydescriptor: $ca) isa therapeutic-agent;'
                            )
                            tx.query(q).resolve()
                            tx.commit()
                    except Exception as e:
                        errors.append(f"  therapeutic-agent '{agent_preferred}': {e}")

        errors.extend(_ingest_evidence_items(driver, trt_match, "treatment", trt.get("evidence")))

    return errors


# ── Ingestion: Tier 8 — Animal models ─────────────────────────────────────────


def _ingest_tier8_animal_models(driver, name: str, data: dict) -> list:
    """Insert animal model entities with evidence."""
    from typedb.driver import TransactionType
    errors = []

    for idx, am in enumerate(data.get("animal_models") or []):
        if not isinstance(am, dict):
            continue
        species = (am.get("species") or "").strip()
        genotype = (am.get("genotype") or "").strip()
        am_name = f"{species} {genotype}".strip() or f"animal-model-{idx}"

        try:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                am_attrs = []
                if species:
                    am_attrs.append(f'has species "{_escape(species)}"')
                if genotype:
                    am_attrs.append(f'has genotype "{_escape(genotype)}"')
                if am.get("description"):
                    am_attrs.append(f'has description "{_escape(_truncate(str(am["description"])))}"')
                for ap in (am.get("associated_phenotypes") or []):
                    if isinstance(ap, str) and ap.strip():
                        am_attrs.append(f'has associated-phenotypes "{_escape(ap.strip())}"')
                if not am_attrs:
                    continue
                q = (
                    f'match $d isa disease, has name "{_escape(name)}"; '
                    f'insert $am isa animalmodel, {", ".join(am_attrs)}; '
                    f'(disease: $d, animalmodel: $am) isa animal-models;'
                )
                tx.query(q).resolve()
                tx.commit()
        except Exception as e:
            errors.append(f"animal_model '{am_name}': {e}")
            continue

        # For evidence matching, use species+genotype to identify the model
        if species and genotype:
            am_match = (
                f'$d isa disease, has name "{_escape(name)}"; '
                f'(disease: $d, animalmodel: $parent) isa animal-models; '
                f'$parent has species "{_escape(species)}"; '
                f'$parent has genotype "{_escape(genotype)}";'
            )
            errors.extend(_ingest_evidence_items(driver, am_match, "animalmodel", am.get("evidence")))

    return errors


# ── Ingestion: Tier 9 — Computational models ──────────────────────────────────


def _ingest_tier9_computational_models(driver, name: str, data: dict) -> list:
    """Insert computational model entities with findings and evidence."""
    from typedb.driver import TransactionType
    errors = []

    for cm in (data.get("computational_models") or []):
        if not isinstance(cm, dict):
            continue
        cm_name = (cm.get("name") or "").strip()
        if not cm_name:
            continue

        try:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                cm_attrs = [f'has name "{_escape(cm_name)}"']
                if cm.get("description"):
                    cm_attrs.append(f'has description "{_escape(_truncate(str(cm["description"])))}"')
                if cm.get("model_type"):
                    cm_attrs.append(f'has model-type "{_escape(str(cm["model_type"]))}"')
                if cm.get("publication"):
                    cm_attrs.append(f'has publication "{_escape(str(cm["publication"]))}"')
                q = (
                    f'match $d isa disease, has name "{_escape(name)}"; '
                    f'insert $cm isa computationalmodel, {", ".join(cm_attrs)}; '
                    f'(disease: $d, computationalmodel: $cm) isa computational-models;'
                )
                tx.query(q).resolve()
                tx.commit()
        except Exception as e:
            errors.append(f"computational_model '{cm_name}': {e}")
            continue

        cm_match = (
            f'$d isa disease, has name "{_escape(name)}"; '
            f'(disease: $d, computationalmodel: $parent) isa computational-models; '
            f'$parent has name "{_escape(cm_name)}";'
        )

        # Findings
        for finding in (cm.get("findings") or []):
            if not isinstance(finding, dict):
                continue
            stmt = (finding.get("statement") or "").strip()
            if not stmt:
                continue
            try:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    q = (
                        f'match {cm_match} '
                        f'insert $f isa finding, has statement "{_escape(_truncate(stmt))}"; '
                        f'(computationalmodel: $parent, finding: $f) isa findings;'
                    )
                    tx.query(q).resolve()
                    tx.commit()
            except Exception as e:
                errors.append(f"  finding '{stmt[:50]}': {e}")

        errors.extend(_ingest_evidence_items(driver, cm_match, "computationalmodel", cm.get("evidence")))

    return errors


# ── Ingestion: orchestrator ────────────────────────────────────────────────────


def _ingest_disease_file(driver, data: dict) -> dict:
    """Ingest one disorder YAML dict into TypeDB across all semantic tiers."""
    name = (data.get("name") or "").strip()
    if not name:
        return {"skipped": True, "reason": "no name"}

    all_errors = []
    counts = {"mechanisms": 0, "phenotypes": 0, "treatments": 0}

    all_errors.extend(_ingest_tier1_disease(driver, data))
    if all_errors:
        # Bail early if the disease entity itself failed (e.g. duplicate)
        return {"skipped": True, "reason": str(all_errors[0])}

    all_errors.extend(_ingest_tier2_disease_term(driver, name, data))

    mech_count, mech_errors = _ingest_tier3_pathophysiology(driver, name, data)
    counts["mechanisms"] = mech_count
    all_errors.extend(mech_errors)

    all_errors.extend(_ingest_tier4_phenotypes(driver, name, data))
    counts["phenotypes"] = len(data.get("phenotypes") or [])

    all_errors.extend(_ingest_tier5_inheritance(driver, name, data))
    all_errors.extend(_ingest_tier6_genetic(driver, name, data))

    all_errors.extend(_ingest_tier7_treatments(driver, name, data))
    counts["treatments"] = len(data.get("treatments") or [])

    all_errors.extend(_ingest_tier8_animal_models(driver, name, data))
    all_errors.extend(_ingest_tier9_computational_models(driver, name, data))

    return {"mechanisms": counts["mechanisms"], "phenotypes": counts["phenotypes"],
            "treatments": counts["treatments"], "errors": all_errors}


# ── Ingestion: command ─────────────────────────────────────────────────────────


def cmd_ingest(args):
    """Bulk-ingest disorder YAML files from the given directory."""
    source = Path(args.source)
    if not source.is_dir():
        print(json.dumps({"success": False, "error": f"Not a directory: {source}"}))
        sys.exit(1)

    files = sorted(p for p in source.glob("*.yaml") if not p.name.endswith(".history.yaml"))
    if args.max:
        files = files[: args.max]

    total = len(files)
    inserted = 0
    skipped = 0
    total_mechanisms = 0
    total_phenotypes = 0
    total_treatments = 0
    all_errors = []

    with _get_driver() as driver:
        for yaml_path in tqdm(files, desc="Ingesting", unit="disease", disable=args.quiet):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    skipped += 1
                    continue
                result = _ingest_disease_file(driver, data)
                if result.get("skipped"):
                    skipped += 1
                else:
                    inserted += 1
                    total_mechanisms += result.get("mechanisms", 0)
                    total_phenotypes += result.get("phenotypes", 0)
                    total_treatments += result.get("treatments", 0)
                    if result.get("errors"):
                        all_errors.extend(result["errors"])
            except Exception as e:
                all_errors.append(f"{yaml_path.name}: {e}")
                skipped += 1

    out = {
        "success": True,
        "total_files": total,
        "inserted": inserted,
        "skipped": skipped,
        "mechanisms": total_mechanisms,
        "phenotypes": total_phenotypes,
        "treatments": total_treatments,
        "error_count": len(all_errors),
    }
    if all_errors and not args.quiet:
        out["errors"] = all_errors[:20]
    print(json.dumps(out))


# ── Querying ───────────────────────────────────────────────────────────────────


def _fetch_disease_names(driver) -> list:
    """Return all disease names in the database."""
    from typedb.driver import TransactionType
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        results = list(tx.query('match $d isa disease, has name $n; fetch {"n": $n};').resolve())
    return sorted(r["n"] for r in results)


def _fetch_disease_detail(driver, name: str):
    """Return full detail dict for a disease by name, or None if not found."""
    from typedb.driver import TransactionType

    if not name:
        return None
    escaped = _escape(name)

    if _count_query(driver, f'match $d isa disease, has name "{escaped}"; reduce $c = count;') == 0:
        return None

    # Category + description
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        r = list(tx.query(
            f'match $d isa disease, has name "{escaped}"; '
            f'fetch {{"cat": $d.category, "desc": $d.description}};'
        ).resolve())
    row = r[0] if r else {}
    detail = {
        "name": name,
        "category": row.get("cat"),
        "description": row.get("desc"),
        "mechanisms": [],
        "phenotypes": [],
        "treatments": [],
        "inheritance": [],
    }

    # Parents + synonyms
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        p_r = list(tx.query(
            f'match $d isa disease, has name "{escaped}", has parents $p; fetch {{"p": $p}};'
        ).resolve())
    detail["parents"] = [r["p"] for r in p_r]

    # Disease term + MONDO ID
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        dt_r = list(tx.query(
            f'match $d isa disease, has name "{escaped}"; '
            f'(disease: $d, diseasedescriptor: $dt) isa disease-term; '
            f'$dt has preferred-term $pt; '
            f'fetch {{"pt": $pt}};'
        ).resolve())
    if dt_r:
        detail["disease_term"] = dt_r[0]["pt"]
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            m_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, diseasedescriptor: $dt) isa disease-term; '
                f'(descriptor: $dt, term: $t) isa term-rel; '
                f'$t has id $tid; '
                f'fetch {{"tid": $tid}};'
            ).resolve())
        if m_r:
            detail["mondo_id"] = m_r[0]["tid"]

    # Pathophysiology mechanisms with enrichment
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        mn_r = list(tx.query(
            f'match $d isa disease, has name "{escaped}"; '
            f'(disease: $d, pathophysiology: $p) isa pathophysiology-rel; '
            f'$p has name $mn; '
            f'fetch {{"mn": $mn}};'
        ).resolve())
    for row in mn_r:
        mname = row["mn"]
        em = _escape(mname)
        mech = {"name": mname}

        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            d_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, pathophysiology: $p) isa pathophysiology-rel; '
                f'$p has name "{em}"; '
                f'fetch {{"desc": $p.description, "conf": $p.mechanism-confidence}};'
            ).resolve())
        if d_r:
            mech["description"] = d_r[0].get("desc")
            mech["mechanism_confidence"] = d_r[0].get("conf")

        # Genes via gene relation
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            g_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, pathophysiology: $p) isa pathophysiology-rel; '
                f'$p has name "{em}"; '
                f'(pathophysiology: $p, genedescriptor: $gd) isa gene; '
                f'$gd has preferred-term $gn; '
                f'fetch {{"gn": $gn}};'
            ).resolve())
        mech["genes"] = [r["gn"] for r in g_r]

        # Cell types
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            ct_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, pathophysiology: $p) isa pathophysiology-rel; '
                f'$p has name "{em}"; '
                f'(pathophysiology: $p, celltypedescriptor: $ct) isa cell-types; '
                f'$ct has preferred-term $cn; '
                f'fetch {{"cn": $cn}};'
            ).resolve())
        mech["cell_types"] = [r["cn"] for r in ct_r]

        # Biological processes
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            bp_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, pathophysiology: $p) isa pathophysiology-rel; '
                f'$p has name "{em}"; '
                f'(pathophysiology: $p, biologicalprocessdescriptor: $bp) isa biological-processes; '
                f'$bp has preferred-term $bn; '
                f'fetch {{"bn": $bn}};'
            ).resolve())
        mech["biological_processes"] = [r["bn"] for r in bp_r]

        # Evidence PMIDs
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            ev_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, pathophysiology: $p) isa pathophysiology-rel; '
                f'$p has name "{em}"; '
                f'(evidenceitem: $ev, pathophysiology: $p) isa evidence; '
                f'$ev has reference $ref; '
                f'fetch {{"ref": $ref}};'
            ).resolve())
        mech["evidence_pmids"] = [r["ref"] for r in ev_r]

        # Downstream causal edges
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            ds_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, pathophysiology: $p) isa pathophysiology-rel; '
                f'$p has name "{em}"; '
                f'(pathophysiology: $p, causaledge: $ce) isa downstream; '
                f'$ce has target $tgt; '
                f'fetch {{"tgt": $tgt}};'
            ).resolve())
        mech["downstream"] = [r["tgt"] for r in ds_r]

        detail["mechanisms"].append(mech)

    # Phenotypes
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        ph_r = list(tx.query(
            f'match $d isa disease, has name "{escaped}"; '
            f'(disease: $d, phenotype: $ph) isa phenotypes; '
            f'$ph has name $phn; '
            f'fetch {{"phn": $phn}};'
        ).resolve())
    for ph_row in ph_r:
        phn = ph_row["phn"]
        eph = _escape(phn)
        ph_entry = {"name": phn}
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            hpo_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, phenotype: $ph) isa phenotypes; '
                f'$ph has name "{eph}"; '
                f'(phenotype: $ph, phenotypedescriptor: $pd) isa phenotype-term; '
                f'(descriptor: $pd, term: $t) isa term-rel; '
                f'$t has id $hid; '
                f'fetch {{"hid": $hid}};'
            ).resolve())
        if hpo_r:
            ph_entry["hpo_id"] = hpo_r[0]["hid"]
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            freq_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, phenotype: $ph) isa phenotypes; '
                f'$ph has name "{eph}", has subtype-attr $f; '
                f'fetch {{"f": $f}};'
            ).resolve())
        if freq_r:
            ph_entry["frequency_code"] = freq_r[0]["f"]
        detail["phenotypes"].append(ph_entry)

    # Treatments
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        trt_r = list(tx.query(
            f'match $d isa disease, has name "{escaped}"; '
            f'(disease: $d, treatment: $t) isa treatments; '
            f'$t has name $tn; '
            f'fetch {{"tn": $tn}};'
        ).resolve())
    for trt_row in trt_r:
        tname = trt_row["tn"]
        etrt = _escape(tname)
        trt_entry = {"name": tname}
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            td_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, treatment: $t) isa treatments; '
                f'$t has name "{etrt}", has description $td; '
                f'fetch {{"td": $td}};'
            ).resolve())
        if td_r:
            trt_entry["description"] = td_r[0]["td"]
        detail["treatments"].append(trt_entry)

    # Inheritance
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        inh_r = list(tx.query(
            f'match $d isa disease, has name "{escaped}"; '
            f'(disease: $d, inheritance: $i) isa inheritance-rel; '
            f'$i has name $in; '
            f'fetch {{"in": $in}};'
        ).resolve())
    for inh_row in inh_r:
        iname = inh_row["in"]
        einh = _escape(iname)
        inh_entry = {"name": iname}
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            pen_r = list(tx.query(
                f'match $d isa disease, has name "{escaped}"; '
                f'(disease: $d, inheritance: $i) isa inheritance-rel; '
                f'$i has name "{einh}", has penetrance $pen; '
                f'fetch {{"pen": $pen}};'
            ).resolve())
        if pen_r:
            inh_entry["penetrance"] = pen_r[0]["pen"]
        detail["inheritance"].append(inh_entry)

    return detail


def cmd_show_disease(args):
    """Show full details for a single disease by name."""
    with _get_driver() as driver:
        detail = _fetch_disease_detail(driver, args.name)
    if detail is None:
        print(json.dumps({"success": False, "error": f"Disease not found: {args.name}"}))
        sys.exit(1)
    print(json.dumps({"success": True, "disease": detail}, indent=2))


def cmd_list_diseases(args):
    """List all diseases, optionally filtered by category."""
    from typedb.driver import TransactionType
    with _get_driver() as driver:
        if args.category:
            cat = _escape(args.category)
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                results = list(tx.query(
                    f'match $d isa disease, has name $n, has category "{cat}"; '
                    f'fetch {{"n": $n}};'
                ).resolve())
        else:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                results = list(tx.query(
                    'match $d isa disease, has name $n; fetch {"n": $n};'
                ).resolve())
    names = sorted(r["n"] for r in results)
    print(json.dumps({"success": True, "count": len(names), "diseases": names}))


def cmd_search(args):
    """Full-text search over disease names and mechanism descriptions."""
    from typedb.driver import TransactionType
    query_lower = args.query.lower()

    hits = []
    with _get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query('match $d isa disease, has name $n; fetch {"n": $n};').resolve())
        for r in results:
            n = r["n"]
            if query_lower in n.lower():
                hits.append({"disease": n, "match_type": "name"})

        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            m_results = list(tx.query(
                'match $d isa disease, has name $dn; '
                '(disease: $d, pathophysiology: $p) isa pathophysiology-rel; '
                '$p has name $mn; '
                'fetch {"dn": $dn, "mn": $mn};'
            ).resolve())
        seen_diseases = {h["disease"] for h in hits}
        for r in m_results:
            dn = r["dn"]
            mn = r["mn"]
            if query_lower in mn.lower() and dn not in seen_diseases:
                hits.append({"disease": dn, "match_type": "mechanism", "mechanism": mn})
                seen_diseases.add(dn)

    hits = hits[:args.limit]
    print(json.dumps({"success": True, "query": args.query, "count": len(hits), "results": hits}))


def cmd_stats(args):
    """Print database statistics."""
    entity_counts = {
        "disease": "name",
        "pathophysiology": "name",
        "diseasedescriptor": "preferred-term",
        "phenotype": "name",
        "treatment": "name",
        "evidenceitem": "reference",
        "genetic": "name",
        "animalmodel": "species",
    }
    with _get_driver() as driver:
        counts = {
            et: _count_query(driver, f'match $e isa {et}, has {attr} $a; reduce $c = count;')
            for et, attr in entity_counts.items()
        }
    print(json.dumps({
        "success": True,
        "diseases": counts.get("disease", 0),
        "mechanisms": counts.get("pathophysiology", 0),
        "disease_terms": counts.get("diseasedescriptor", 0),
        "phenotypes": counts.get("phenotype", 0),
        "treatments": counts.get("treatment", 0),
        "evidence_items": counts.get("evidenceitem", 0),
        "genetic_entries": counts.get("genetic", 0),
        "animal_models": counts.get("animalmodel", 0),
    }))


# ── Dashboard server ───────────────────────────────────────────────────────────


# ── Add evidence command ───────────────────────────────────────────────────────


def cmd_add_evidence(args):
    """Add a new evidence item linked to a disease and/or mechanism."""
    from typedb.driver import TransactionType

    if not args.pmid:
        print(json.dumps({"success": False, "error": "PMID is required"}))
        sys.exit(1)

    if not args.disease and not args.mechanism:
        print(json.dumps({"success": False, "error": "Either --disease or --mechanism is required"}))
        sys.exit(1)

    reference = f"PMID:{args.pmid}"
    errors = []
    with _get_driver() as driver:
        if args.disease:
            disease_count = _count_query(driver, f'match $d isa disease, has name "{_escape(args.disease)}"; reduce $c = count;')
            if disease_count == 0:
                errors.append(f"Disease not found: {args.disease}")

        if args.mechanism:
            mech_count = _count_query(driver, f'match $p isa pathophysiology, has name "{_escape(args.mechanism)}"; reduce $c = count;')
            if mech_count == 0:
                errors.append(f"Mechanism not found: {args.mechanism}")

        if errors:
            print(json.dumps({"success": False, "errors": errors}))
            sys.exit(1)

        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            evidence_attrs = [
                f'has reference "{_escape(reference)}"',
                f'has supports "{_escape(args.supports)}"',
                f'has evidence-source "{_escape(args.evidence_source)}"',
            ]
            if args.reference_title:
                evidence_attrs.append(f'has reference-title "{_escape(args.reference_title)}"')
            if args.snippet:
                evidence_attrs.append(f'has snippet "{_escape(_truncate(args.snippet))}"')
            if args.explanation:
                evidence_attrs.append(f'has explanation "{_escape(_truncate(args.explanation))}"')
            try:
                tx.query(f"insert $ev isa evidenceitem, {', '.join(evidence_attrs)};").resolve()
                tx.commit()
            except Exception as e:
                print(json.dumps({"success": False, "error": str(e)}))
                sys.exit(1)

        evidence_relations = []
        if args.disease:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                q = (
                    f'match $d isa disease, has name "{_escape(args.disease)}"; '
                    f'$ev isa evidenceitem, has reference "{_escape(reference)}"; '
                    f'insert (disease: $d, evidenceitem: $ev) isa evidence;'
                )
                try:
                    tx.query(q).resolve()
                    tx.commit()
                    evidence_relations.append(f"disease: {args.disease}")
                except Exception as e:
                    errors.append(f"Failed to link evidence to disease: {e}")

        if args.mechanism:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                q = (
                    f'match $p isa pathophysiology, has name "{_escape(args.mechanism)}"; '
                    f'$ev isa evidenceitem, has reference "{_escape(reference)}"; '
                    f'insert (pathophysiology: $p, evidenceitem: $ev) isa evidence;'
                )
                try:
                    tx.query(q).resolve()
                    tx.commit()
                    evidence_relations.append(f"mechanism: {args.mechanism}")
                except Exception as e:
                    errors.append(f"Failed to link evidence to mechanism: {e}")

        if errors:
            print(json.dumps({"success": False, "errors": errors}))
            sys.exit(1)

        print(json.dumps({"success": True, "reference": reference, "linked_to": evidence_relations}))


def cmd_serve(args):
    """Serve the dashboard at http://localhost:<port>."""
    skill_dir = Path(__file__).parent

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(skill_dir), **kw)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api(parsed)
            else:
                if parsed.path in ("/", ""):
                    self.path = "/dashboard/index.html"
                super().do_GET()

        def _handle_api(self, parsed):
            params = dict(urllib.parse.parse_qsl(parsed.query))
            try:
                result = self._dispatch_api(parsed.path, params)
                body = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        def _dispatch_api(self, path, params):
            with _get_driver() as driver:
                if path == "/api/stats":
                    return _api_stats(driver)
                elif path == "/api/diseases":
                    return _api_diseases(driver, params)
                elif path == "/api/disease":
                    return _fetch_disease_detail(driver, params.get("name", "")) or {}
                elif path == "/api/search":
                    return _api_search(driver, params.get("q", ""), int(params.get("limit", "50")))
                else:
                    return {"error": f"Unknown API endpoint: {path}"}

        def log_message(self, fmt, *a):
            pass

    port = args.port
    print(json.dumps({"message": f"DisMech dashboard at http://localhost:{port}", "port": port}))
    with http.server.HTTPServer(("", port), Handler) as srv:
        srv.serve_forever()


def _api_stats(driver) -> dict:
    entity_counts = {
        "disease": "name",
        "pathophysiology": "name",
        "diseasedescriptor": "preferred-term",
        "phenotype": "name",
        "treatment": "name",
        "evidenceitem": "reference",
    }
    counts = {
        et: _count_query(driver, f'match $e isa {et}, has {attr} $a; reduce $c = count;')
        for et, attr in entity_counts.items()
    }
    return {
        "diseases": counts.get("disease", 0),
        "mechanisms": counts.get("pathophysiology", 0),
        "disease_terms": counts.get("diseasedescriptor", 0),
        "phenotypes": counts.get("phenotype", 0),
        "treatments": counts.get("treatment", 0),
        "evidence_items": counts.get("evidenceitem", 0),
    }


def _api_diseases(driver, params: dict) -> dict:
    from typedb.driver import TransactionType
    category = params.get("category")
    limit = int(params.get("limit", "100"))
    offset = int(params.get("offset", "0"))

    if category:
        cat = _escape(category)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(
                f'match $d isa disease, has name $n, has category "{cat}"; '
                f'fetch {{"n": $n}};'
            ).resolve())
    else:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query('match $d isa disease, has name $n; fetch {"n": $n};').resolve())

    names = sorted(r["n"] for r in results)
    page = names[offset: offset + limit]
    return {"total": len(names), "offset": offset, "limit": limit, "diseases": page}


def _api_search(driver, query: str, limit: int = 50) -> dict:
    from typedb.driver import TransactionType
    if not query:
        return {"results": []}
    query_lower = query.lower()
    hits = []

    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        results = list(tx.query('match $d isa disease, has name $n; fetch {"n": $n};').resolve())
    for r in results:
        n = r["n"]
        if query_lower in n.lower():
            hits.append({"disease": n, "match_type": "name"})

    seen = {h["disease"] for h in hits}
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        m_results = list(tx.query(
            'match $d isa disease, has name $dn; '
            '(disease: $d, pathophysiology: $p) isa pathophysiology-rel; '
            '$p has name $mn; '
            'fetch {"dn": $dn, "mn": $mn};'
        ).resolve())
    for r in m_results:
        dn = r["dn"]
        mn = r["mn"]
        if query_lower in mn.lower() and dn not in seen:
            hits.append({"disease": dn, "match_type": "mechanism", "mechanism": mn})
            seen.add(dn)

    return {"query": query, "count": len(hits[:limit]), "results": hits[:limit]}


# ── Init: create database and load schema ─────────────────────────────────────


def cmd_init(args):
    """Create the dismech database and load schema.tql."""
    import subprocess

    # Ensure TypeDB container is running
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=alhazen-typedb", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    if "alhazen-typedb" not in (result.stdout or ""):
        print(json.dumps({"success": False, "error": "TypeDB container 'alhazen-typedb' is not running. Start it first."}))
        sys.exit(1)

    from typedb.driver import Credentials, DriverOptions, TransactionType, TypeDB

    driver = TypeDB.driver(
        f"{TYPEDB_HOST}:{TYPEDB_PORT}",
        Credentials(TYPEDB_USERNAME, TYPEDB_PASSWORD),
        DriverOptions(is_tls_enabled=False),
    )

    db_created = False
    if not driver.databases.contains(TYPEDB_DATABASE):
        driver.databases.create(TYPEDB_DATABASE)
        db_created = True

    schema_path = Path(__file__).parent / "schema.tql"
    if not schema_path.exists():
        driver.close()
        print(json.dumps({"success": False, "error": f"Schema not found: {schema_path}"}))
        sys.exit(1)

    schema = schema_path.read_text()
    try:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.SCHEMA) as tx:
            tx.query(schema).resolve()
            tx.commit()
        schema_status = "loaded"
    except Exception as e:
        schema_status = f"error: {e}"

    driver.close()

    print(json.dumps({
        "success": schema_status == "loaded",
        "typedb": "running",
        "database": TYPEDB_DATABASE,
        "database_created": db_created,
        "schema": schema_status,
        "message": "DisMech ready. Run dismech.py ingest to load disease data.",
    }, indent=2))


# ── CLI entry point ────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="DisMech — Disease Mechanism Knowledge Graph CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create dismech database and load schema")

    ingest_p = sub.add_parser("ingest", help="Bulk-ingest disorder YAML files")
    ingest_p.add_argument("--source", required=True, help="Path to kb/disorders directory")
    ingest_p.add_argument("--max", type=int, default=None, help="Maximum files to ingest (for testing)")
    ingest_p.add_argument("--quiet", action="store_true", help="Suppress progress bar")

    show_p = sub.add_parser("show-disease", help="Show full details for a disease")
    show_p.add_argument("--name", required=True, help="Disease name (exact match)")

    list_p = sub.add_parser("list-diseases", help="List all diseases")
    list_p.add_argument("--category", default=None, help="Filter by category")

    search_p = sub.add_parser("search", help="Full-text search over names and mechanism descriptions")
    search_p.add_argument("--query", required=True, help="Search query text")
    search_p.add_argument("--limit", type=int, default=50, help="Maximum results (default: 50)")

    sub.add_parser("stats", help="Show database statistics")

    serve_p = sub.add_parser("serve", help="Start the dashboard web server")
    serve_p.add_argument("--port", type=int, default=7777, help="Port to serve on (default: 7777)")

    evidence_p = sub.add_parser("add-evidence", help="Add a new evidence item")
    evidence_p.add_argument("--disease", default=None, help="Disease name to link evidence to")
    evidence_p.add_argument("--mechanism", default=None, help="Mechanism name to link evidence to")
    evidence_p.add_argument("--pmid", required=True, help="PubMed ID (e.g., 38234567)")
    evidence_p.add_argument("--supports", required=True, choices=["SUPPORT", "REFUTE", "NO_EVIDENCE", "PARTIAL", "WRONG_STATEMENT"], help="Evidence support level")
    evidence_p.add_argument("--evidence-source", required=True, dest="evidence_source", choices=["HUMAN_CLINICAL", "ANIMAL_MODEL", "IN_VITRO", "COMPUTATIONAL"], help="Evidence source type")
    evidence_p.add_argument("--snippet", default=None, help="Key quote from abstract or paper")
    evidence_p.add_argument("--reference-title", default=None, dest="reference_title", help="Paper title (optional)")
    evidence_p.add_argument("--explanation", default=None, help="Explanation of evidence relevance")

    args = parser.parse_args()
    dispatch = {
        "init": cmd_init,
        "ingest": cmd_ingest,
        "show-disease": cmd_show_disease,
        "list-diseases": cmd_list_diseases,
        "search": cmd_search,
        "stats": cmd_stats,
        "serve": cmd_serve,
        "add-evidence": cmd_add_evidence,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
