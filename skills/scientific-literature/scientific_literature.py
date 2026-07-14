#!/usr/bin/env python3
"""
Scientific Literature CLI - Multi-source paper search and ingestion for TypeDB.

Sources: Europe PMC (epmc), PubMed (pubmed), OpenAlex (openalex), bioRxiv/medRxiv

Usage:
    python scientific_literature.py search --source epmc --query "CRISPR" --collection "CRISPR Papers"
    python scientific_literature.py count --query "COVID-19 AND vaccine"
    python scientific_literature.py ingest --doi "10.1038/s41587-020-0700-8"
    python scientific_literature.py show --id "scilit-paper-abc123"
    python scientific_literature.py list [--collection "collection-abc123"]
    python scientific_literature.py list-collections
    python scientific_literature.py embed --collection "collection-abc123"
    python scientific_literature.py search-semantic --query "CDK8 stress response" --collection "col-abc"
    python scientific_literature.py cluster --collection "collection-abc123" --min-cluster-size 15 --dry-run

Environment:
    TYPEDB_HOST         TypeDB host (default: localhost)
    TYPEDB_PORT         TypeDB port (default: 1729)
    TYPEDB_DATABASE     Database name (default: alhazen_notebook)
    NCBI_API_KEY        NCBI Entrez API key (optional; raises rate limit to 10 req/s)
    OPENALEX_API_KEY    OpenAlex API key (optional; free at openalex.org/settings/api)
    VOYAGE_API_KEY      Voyage AI API key (required for embed/search-semantic/cluster)
    QDRANT_HOST         Qdrant host (default: localhost)
    QDRANT_PORT         Qdrant port (default: 6333)
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import sleep

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from typedb.driver import Credentials, DriverOptions, TransactionType, TypeDB
    TYPEDB_AVAILABLE = True
except ImportError:
    TYPEDB_AVAILABLE = False
    print("Warning: typedb-driver not installed. Install with: pip install 'typedb-driver>=3.8.0'",
          file=sys.stderr)

# paper_identity is a sibling module. Running this file as a script puts its dir on sys.path
# automatically, but the warm gateway loads it via importlib (which does not), so add it here.
try:
    from paper_identity import paper_identity
except ModuleNotFoundError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from paper_identity import paper_identity

try:
    from skillful_alhazen.utils.skill_helpers import escape_string, generate_id, get_timestamp
except ImportError:
    def escape_string(s):
        if s is None:
            return ""
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")

    def generate_id(prefix):
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    def get_timestamp():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: requests not installed. Run: uv add requests", file=sys.stderr)

try:
    import kreuzberg  # noqa: F401  (layout/table-aware full-text extraction)
    KREUZBERG_AVAILABLE = True
except ImportError:
    KREUZBERG_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    from pdf_layout_parser import (
        load_blocks, compute_doc_stats, classify_blocks, regroup_captions,
        assemble_reading_order, render_markdown, suppress_table_bodies,
    )
    import figure_extract
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# ---------------------------------------------------------------------------
# Cache utilities (inlined — no external package needed)
# ---------------------------------------------------------------------------

_CACHE_THRESHOLD = 50 * 1024  # 50KB

_MIME_TYPE_MAP = {
    "text/html": ("html", "html"),
    "application/xhtml+xml": ("html", "html"),
    "application/pdf": ("pdf", "pdf"),
    "image/png": ("image", "png"),
    "image/jpeg": ("image", "jpg"),
    "image/gif": ("image", "gif"),
    "image/webp": ("image", "webp"),
    "image/svg+xml": ("image", "svg"),
    "application/json": ("json", "json"),
    "text/plain": ("text", "txt"),
    "text/markdown": ("text", "md"),
    "text/csv": ("text", "csv"),
    "application/xml": ("text", "xml"),
    "text/xml": ("text", "xml"),
}


def _get_cache_dir():
    cache_env = os.getenv("ALHAZEN_CACHE_DIR")
    cache_dir = Path(cache_env).expanduser() if cache_env else Path.home() / ".alhazen" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def should_cache(content):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return len(content) >= _CACHE_THRESHOLD


def save_to_cache(artifact_id, content, mime_type, subdir=None):
    """Write a cached file. When `subdir` is given (e.g. "fulltext/<paper-id>"), the file
    lands at <subdir>/<artifact_id>.<ext> (the per-paper full-text layout); otherwise the
    legacy by-type layout <type_dir>/<artifact_id>.<ext>."""
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content
    type_dir, ext = _MIME_TYPE_MAP.get(mime_type, ("other", "bin"))
    cache_dir = _get_cache_dir()
    rel_dir = subdir if subdir else type_dir
    base = cache_dir / rel_dir
    base.mkdir(parents=True, exist_ok=True)
    filename = f"{artifact_id}.{ext}"
    full_path = base / filename
    full_path.write_bytes(content_bytes)
    return {
        "cache_path": f"{rel_dir}/{filename}",
        "file_size": len(content_bytes),
        "content_hash": hashlib.sha256(content_bytes).hexdigest(),
        "full_path": str(full_path),
    }


def load_from_cache_text(cache_path, encoding="utf-8"):
    return (_get_cache_dir() / cache_path).read_bytes().decode(encoding)


CACHE_AVAILABLE = True

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    def tqdm(iterable, **kwargs):
        return iterable


# =============================================================================
# CONFIGURATION
# =============================================================================

TYPEDB_HOST = os.getenv("TYPEDB_HOST", "localhost")
TYPEDB_PORT = int(os.getenv("TYPEDB_PORT", "1729"))
TYPEDB_DATABASE = os.getenv("TYPEDB_DATABASE", "alh_deep_research")
TYPEDB_USERNAME = os.getenv("TYPEDB_USERNAME", "admin")
TYPEDB_PASSWORD = os.getenv("TYPEDB_PASSWORD", "password")

NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

APT_SECTIONS_COLLECTION = "apt-sections"
APT_NOTES_COLLECTION = "apt-notes"
VECTOR_DIM_SECTIONS = 1024  # voyage-3 output dimension

EPMC_API_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OPENALEX_BASE = "https://api.openalex.org"
BIORXIV_BASE = "https://api.biorxiv.org/pubs"
MEDRXIV_BASE = "https://api.medrxiv.org/pubs"

DEFAULT_PAGE_SIZE = 1000
REQUEST_TIMEOUT = 60
HEADERS = {"User-Agent": "skillful-alhazen/0.1 (mailto:alhazen@example.com)"}

ESEARCH_PAGE_SIZE = 500   # PMIDs per esearch pagination page
EFETCH_BATCH_SIZE = 200   # PMIDs per efetch POST batch (avoids GET URL length limits)
NCBI_RATE_LIMIT   = 0.34  # minimum seconds between NCBI requests (3 req/sec without key)


# =============================================================================
# TYPEDB HELPERS
# =============================================================================

def get_driver():
    """Get TypeDB driver connection."""
    return TypeDB.driver(
        f"{TYPEDB_HOST}:{TYPEDB_PORT}",
        Credentials(TYPEDB_USERNAME, TYPEDB_PASSWORD),
        DriverOptions(is_tls_enabled=False),
    )


def paper_exists(driver, doi=None, pmid=None):
    """Check if a paper already exists by DOI or PMID. Returns existing ID or None."""
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        if doi:
            result = list(tx.query(
                f'match $p isa scilit-paper, has scilit-doi "{escape_string(doi)}"; fetch {{ "id": $p.id }};'
            ).resolve())
            if result:
                return result[0]["id"]
        if pmid:
            result = list(tx.query(
                f'match $p isa scilit-paper, has scilit-pmid "{escape_string(pmid)}"; fetch {{ "id": $p.id }};'
            ).resolve())
            if result:
                return result[0]["id"]
    return None


def insert_paper(driver, paper: dict) -> str:
    """Insert a normalized paper dict into TypeDB. Returns paper_id.

    Id is always the deterministic paper_identity() hash (DOI -> PMID -> arXiv ->
    content-hash) -- never a caller-supplied or randomly generated value. This is
    the single source of truth for scilit-paper identity (see SKILL.md); a paper
    already present under this id (created via this function, insert_epmc_paper,
    or kqed.upsert_paper) is returned as-is rather than duplicated."""
    identity_meta = dict(paper)
    identity_meta.setdefault("arxiv", paper.get("arxiv_id"))
    pid, tier, value = paper_identity(identity_meta)
    timestamp = get_timestamp()

    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        if list(tx.query(f'match $x has id "{escape_string(pid)}"; fetch {{ "id": $x.id }};').resolve()):
            return pid

    q = (f'insert $p isa scilit-paper, has id "{pid}", '
         f'has scilit-identity-basis "{escape_string(tier)}", '
         f'has scilit-identity-value "{escape_string(value)}", '
         f'has name "{escape_string(paper.get("title", ""))}"')
    if paper.get("abstract"):
        q += f', has abstract-text "{escape_string(paper["abstract"])}"'
    if paper.get("doi"):
        q += f', has scilit-doi "{escape_string(paper["doi"])}"'
    if paper.get("pmid"):
        q += f', has scilit-pmid "{escape_string(str(paper["pmid"]))}"'
    if paper.get("pmcid"):
        q += f', has scilit-pmcid "{escape_string(paper["pmcid"])}"'
    if paper.get("arxiv_id"):
        q += f', has scilit-arxiv-id "{escape_string(paper["arxiv_id"])}"'
    if paper.get("year"):
        q += f', has scilit-publication-year {int(paper["year"])}'
    if paper.get("journal"):
        q += f', has scilit-journal-name "{escape_string(paper["journal"])}"'
    if paper.get("journal_volume"):
        q += f', has scilit-journal-volume "{escape_string(paper["journal_volume"])}"'
    if paper.get("journal_issue"):
        q += f', has scilit-journal-issue "{escape_string(paper["journal_issue"])}"'
    if paper.get("page_range"):
        q += f', has scilit-page-range "{escape_string(paper["page_range"])}"'
    if paper.get("source_uri"):
        q += f', has source-uri "{escape_string(paper["source_uri"])}"'
    for kw in paper.get("keywords", []):
        q += f', has scilit-keyword "{escape_string(kw)}"'
    q += f', has created-at {timestamp};'

    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
        tx.query(q).resolve()
        tx.commit()

    return pid


def add_to_collection(driver, paper_id: str, collection_id: str):
    """Add a paper to a collection (idempotent — skips if already a member).

    Matches by alh-domain-thing, not scilit-paper: a scilit-preprint is a sibling
    type, not a subtype, so scoping to scilit-paper would silently fail to find it."""
    timestamp = get_timestamp()
    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
        existing = list(tx.query(
            f'match $c isa alh-collection, has id "{collection_id}"; '
            f'$p isa alh-domain-thing, has id "{paper_id}"; '
            f'(collection: $c, member: $p) isa alh-collection-membership; '
            f'fetch {{ "id": $p.id }};'
        ).resolve())
        if existing:
            return
        tx.query(
            f'match $c isa alh-collection, has id "{collection_id}"; '
            f'$p isa alh-domain-thing, has id "{paper_id}"; '
            f'insert (collection: $c, member: $p) isa alh-collection-membership, '
            f'has created-at {timestamp};'
        ).resolve()
        tx.commit()


# =============================================================================
# EPMC CONNECTOR
# =============================================================================

def map_publication_type(pub_types: list) -> tuple:
    """Map EPMC publication types to TypeDB entity types."""
    pub_types_lower = [t.lower() for t in pub_types]

    if "patent" in pub_types_lower:
        return None, None
    elif "clinical trial" in pub_types_lower:
        return "scilit-paper", "ClinicalTrial"
    elif any(t in pub_types_lower for t in [
        "review", "systematic review", "systematic-review", "meta-analysis", "review-article",
    ]):
        return "scilit-review", "ScientificReviewArticle"
    elif "preprint" in pub_types_lower:
        return "scilit-preprint", "ScientificPrimaryResearchPreprint"
    elif any(t in pub_types_lower for t in ["journal article", "research-article"]):
        return "scilit-paper", "ScientificPrimaryResearchArticle"
    elif any(t in pub_types_lower for t in ["case-report", "case reports"]):
        return "scilit-paper", "ClinicalCaseReport"
    elif "practice guideline" in pub_types_lower:
        return "scilit-paper", "ClinicalGuidelines"
    elif any(t in pub_types_lower for t in ["letter", "comment", "editorial"]):
        return "scilit-paper", "ScientificComment"
    elif any(t in pub_types_lower for t in [
        "published erratum", "correction", "retraction of publication",
    ]):
        return "scilit-paper", "ScientificErrata"
    else:
        return None, None


def run_epmc_query(query, page_size=DEFAULT_PAGE_SIZE, max_results=None, timeout=REQUEST_TIMEOUT):
    """Execute a search query against Europe PMC API."""
    params = {
        "format": "JSON",
        "pageSize": page_size,
        "synonym": "TRUE",
        "resultType": "core",
        "query": query,
    }

    response = requests.get(EPMC_API_URL, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    total_count = data["hitCount"]
    print(f"Found {total_count} results for query: {query}", file=sys.stderr)

    if total_count == 0:
        return 0, []

    fetch_count = min(total_count, max_results) if max_results else total_count
    publications = []
    cursor_mark = "*"

    for _i in tqdm(range(0, fetch_count, page_size), desc="Fetching", file=sys.stderr):
        params["cursorMark"] = cursor_mark
        response = requests.get(EPMC_API_URL, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        if data.get("nextCursorMark"):
            cursor_mark = data["nextCursorMark"]

        for record in data.get("resultList", {}).get("result", []):
            if len(publications) >= fetch_count:
                break
            publications.append(record)

        sleep(0.1)

    return total_count, publications


def parse_epmc_record(record: dict):
    """Parse an EPMC record into a normalized paper dict for TypeDB."""
    pub_types = record.get("pubTypeList", {}).get("pubType", [])
    typedb_type, pub_type_label = map_publication_type(pub_types)

    if typedb_type is None:
        return None

    doi = record.get("doi")
    if not doi:
        return None

    date_format = "%Y-%m-%d"
    pub_date = None
    if record.get("firstPublicationDate"):
        try:
            pub_date = datetime.strptime(record["firstPublicationDate"], date_format)
        except ValueError:
            pass
    elif record.get("dateOfCreation"):
        try:
            pub_date = datetime.strptime(record["dateOfCreation"], date_format)
        except ValueError:
            pass

    author_string = record.get("authorString", "")
    title = record.get("title", "")
    year = pub_date.year if pub_date else ""

    return {
        "doi": doi,
        "pmid": record.get("pmid"),
        "pmcid": record.get("pmcid"),
        "epmc_id": record.get("id"),
        "source": record.get("source"),
        "title": title,
        "abstract": record.get("abstractText", ""),
        "publication_date": pub_date,
        "year": pub_date.year if pub_date else None,
        "journal": record.get("journalTitle"),
        "journal_volume": record.get("journalVolume"),
        "journal_issue": record.get("issue"),
        "page_range": record.get("pageInfo"),
        "typedb_type": typedb_type,
        "pub_type_label": pub_type_label,
        "keywords": record.get("keywordList", {}).get("keyword", []),
        "pub_types": pub_types,
        "source_uri": f"https://europepmc.org/article/{record.get('source', 'MED')}/{record.get('id', doi)}",
    }


def insert_epmc_paper(driver, paper: dict, collection_id=None) -> str:
    """Insert an EPMC paper with full citation record and fragments. Returns paper_id.

    Id is always the deterministic paper_identity() hash (see insert_paper) -- never
    the legacy doi-<encoded-doi> scheme. The existence check matches by id alone
    (type-agnostic), so it correctly recognizes an existing scilit-preprint too."""
    paper_id, id_tier, id_value = paper_identity({"doi": paper.get("doi"), "pmid": paper.get("pmid")})
    timestamp = get_timestamp()

    # Build insert query
    query = (f'insert $p isa {paper["typedb_type"]}, has id "{paper_id}", '
             f'has scilit-identity-basis "{escape_string(id_tier)}", '
             f'has scilit-identity-value "{escape_string(id_value)}", '
             f'has name "{escape_string(paper["title"])}", has scilit-doi "{paper["doi"]}", has created-at {timestamp}')

    if paper.get("pmid"):
        query += f', has scilit-pmid "{paper["pmid"]}"'
    if paper.get("pmcid"):
        query += f', has scilit-pmcid "{paper["pmcid"]}"'
    if paper.get("abstract"):
        query += f', has abstract-text "{escape_string(paper["abstract"])}"'
    if paper.get("year") and paper.get("typedb_type") != "scilit-preprint":
        query += f', has scilit-publication-year {paper["year"]}'
    if paper.get("journal"):
        query += f', has scilit-journal-name "{escape_string(paper["journal"])}"'
    if paper.get("journal_volume"):
        query += f', has scilit-journal-volume "{escape_string(paper["journal_volume"])}"'
    if paper.get("journal_issue"):
        query += f', has scilit-journal-issue "{escape_string(paper["journal_issue"])}"'
    if paper.get("page_range"):
        query += f', has scilit-page-range "{escape_string(paper["page_range"])}"'
    for kw in paper.get("keywords", []):
        query += f', has scilit-keyword "{escape_string(kw)}"'
    query += ";"

    # Check if paper already exists -- match by the deterministic id alone (type-agnostic),
    # so an existing scilit-preprint is correctly recognized too (it is a sibling type of
    # scilit-paper, not a subtype, so a `has scilit-doi` match scoped to `isa scilit-paper`
    # would silently miss it and risk a duplicate insert).
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        check = f'match $p has id "{escape_string(paper_id)}"; fetch {{ "id": $p.id }};'
        if list(tx.query(check).resolve()):
            return paper_id

    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
        tx.query(query).resolve()
        tx.commit()

    # Create citation record artifact
    artifact_id = generate_id("artifact")
    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
        tx.query(f'insert $a isa scilit-citation-record, has id "{artifact_id}", has format "epmc-citation", has source-uri "{escape_string(paper["source_uri"])}", has created-at {timestamp};').resolve()
        tx.commit()

    # Link artifact to paper (match by alh-domain-thing, not scilit-paper: a
    # scilit-preprint is a sibling type, not a subtype, so scoping to scilit-paper
    # would silently fail to find it)
    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
        tx.query(f'match $p isa alh-domain-thing, has id "{paper_id}"; $a isa alh-artifact, has id "{artifact_id}"; insert (alh-artifact: $a, referent: $p) isa alh-representation;').resolve()
        tx.commit()

    # Create title fragment
    if paper.get("title"):
        title_frag_id = generate_id("fragment")
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'insert $f isa scilit-section, has id "{title_frag_id}", has content "{escape_string(paper["title"])}", has scilit-section-type "title", has offset 0, has length {len(paper["title"])}, has created-at {timestamp};').resolve()
            tx.commit()
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'match $a isa alh-artifact, has id "{artifact_id}"; $f isa alh-fragment, has id "{title_frag_id}"; insert (whole: $a, part: $f) isa alh-fragmentation;').resolve()
            tx.commit()

    # Create abstract fragment
    if paper.get("abstract"):
        abs_frag_id = generate_id("fragment")
        title_len = len(paper.get("title", "")) + 1
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'insert $f isa scilit-section, has id "{abs_frag_id}", has content "{escape_string(paper["abstract"])}", has scilit-section-type "abstract", has offset {title_len}, has length {len(paper["abstract"])}, has created-at {timestamp};').resolve()
            tx.commit()
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'match $a isa alh-artifact, has id "{artifact_id}"; $f isa alh-fragment, has id "{abs_frag_id}"; insert (whole: $a, part: $f) isa alh-fragmentation;').resolve()
            tx.commit()

    # Add to collection if specified (match by alh-domain-thing: see note above --
    # a scilit-preprint would silently fail to match `isa scilit-paper`)
    if collection_id:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'match $c isa alh-collection, has id "{collection_id}"; $p isa alh-domain-thing, has id "{paper_id}"; insert (collection: $c, member: $p) isa alh-collection-membership, has created-at {timestamp};').resolve()
            tx.commit()

    # Tag with publication type
    if paper.get("pub_type_label"):
        tag_name = paper["pub_type_label"]
        tag_id = generate_id("tag")
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            existing_tag = list(tx.query(f'match $t isa alh-tag, has name "{tag_name}"; fetch {{ "id": $t.id }};').resolve())
        if not existing_tag:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(f'insert $t isa alh-tag, has id "{tag_id}", has name "{tag_name}";').resolve()
                tx.commit()
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'match $p isa alh-domain-thing, has id "{paper_id}"; $t isa alh-tag, has name "{tag_name}"; insert (tagged-entity: $p, tag: $t) isa alh-tagging, has created-at {timestamp};').resolve()
            tx.commit()

    return paper_id


# =============================================================================
# PUBMED CONNECTOR
# =============================================================================

def _ncbi_params(**kwargs):
    params = {"retmode": "json", **kwargs}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    return params


def _esearch_paginated(query: str, max_results: int) -> list:
    """Collect PubMed IDs via paginated esearch (retstart/retmax chunks).

    Mirrors ESearchQuery.execute_query() from alhazen searchEngineUtils:
    - Gets total count first, then pages through results in ESEARCH_PAGE_SIZE chunks
    - Respects NCBI rate limit between pages
    - Returns up to max_results PMIDs
    """
    # First: get total hit count
    r = requests.get(
        f"{NCBI_BASE}/esearch.fcgi",
        params=_ncbi_params(db="pubmed", term=query, retmax=0),
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    total = int(r.json().get("esearchresult", {}).get("count", 0))
    to_fetch = min(total, max_results)
    if to_fetch == 0:
        return []

    ids = []
    for start in range(0, to_fetch, ESEARCH_PAGE_SIZE):
        batch_size = min(ESEARCH_PAGE_SIZE, to_fetch - start)
        time.sleep(NCBI_RATE_LIMIT)
        r = requests.get(
            f"{NCBI_BASE}/esearch.fcgi",
            params=_ncbi_params(db="pubmed", term=query, retmax=batch_size, retstart=start),
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        ids.extend(r.json().get("esearchresult", {}).get("idlist", []))

    return ids[:to_fetch]


def _efetch_batched(pmids: list) -> list:
    """Fetch PubMed records for a list of PMIDs using batched POST requests.

    Mirrors EFetchQuery.generate_data_frame_from_id_list() from alhazen searchEngineUtils:
    - Sends IDs as POST form data in EFETCH_BATCH_SIZE chunks
    - POST avoids HTTP 414 (Request-URI Too Long) from large ID lists in GET params
    - Respects NCBI rate limit between batches
    """
    papers = []
    for i in range(0, len(pmids), EFETCH_BATCH_SIZE):
        batch = pmids[i:i + EFETCH_BATCH_SIZE]
        data = {"db": "pubmed", "retmode": "xml", "rettype": "abstract", "id": ",".join(batch)}
        if NCBI_API_KEY:
            data["api_key"] = NCBI_API_KEY
        r = requests.post(
            f"{NCBI_BASE}/efetch.fcgi",
            data=data,
            headers=HEADERS,
            timeout=60,
        )
        r.raise_for_status()
        papers.extend(_parse_pubmed_xml(r.text))
        if i + EFETCH_BATCH_SIZE < len(pmids):
            time.sleep(NCBI_RATE_LIMIT)
    return papers


def search_pubmed(query: str, max_results: int = 20) -> list:
    """Search PubMed using paginated esearch + batched POST efetch.

    Handles queries returning any number of results:
    - esearch is paginated (ESEARCH_PAGE_SIZE per page with retstart/retmax)
    - efetch uses POST in batches of EFETCH_BATCH_SIZE, avoiding URL length limits
    Both patterns adapted from alhazen.utils.searchEngineUtils (ESearchQuery /
    EFetchQuery classes).
    """
    pmids = _esearch_paginated(query, max_results)
    if not pmids:
        return []
    time.sleep(NCBI_RATE_LIMIT)
    return _efetch_batched(pmids)


def _parse_pubmed_xml(xml_text: str) -> list:
    """Parse PubMed efetch XML into normalized dicts."""
    papers = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for article in root.findall(".//PubmedArticle"):
        medline = article.find(".//MedlineCitation")
        if medline is None:
            continue

        pmid_el = medline.find("PMID")
        pmid = pmid_el.text if pmid_el is not None else None

        art = medline.find("Article")
        if art is None:
            continue

        title_el = art.find("ArticleTitle")
        title = "".join(title_el.itertext()) if title_el is not None else ""

        abstract_el = art.find(".//AbstractText")
        abstract = "".join(abstract_el.itertext()) if abstract_el is not None else ""

        journal_el = art.find(".//Journal/Title")
        journal = journal_el.text if journal_el is not None else ""

        year_el = art.find(".//PubDate/Year")
        year = int(year_el.text) if year_el is not None and year_el.text else None

        doi = None
        for aid in article.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text
                break

        papers.append({
            "title": title.strip(),
            "abstract": abstract.strip(),
            "pmid": pmid,
            "doi": doi,
            "journal": journal,
            "year": year,
            "source_uri": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })

    return papers


# =============================================================================
# OPENALEX CONNECTOR
# =============================================================================

def search_openalex(query: str, max_results: int = 20, filter_str: str = None) -> list:
    """Search OpenAlex /works endpoint. Returns normalized paper dicts.

    If filter_str is provided (e.g. 'cites:W2565424224'), it is used instead of the
    search param, enabling citation lookups and other filter-based queries.
    Paginates automatically up to max_results.
    """
    select = "id,display_name,abstract_inverted_index,doi,ids,publication_year,primary_location,type"
    results = []
    cursor = "*"
    per_page = min(max_results, 200)

    while len(results) < max_results:
        params = {
            "per_page": min(per_page, max_results - len(results)),
            "select": select,
            "cursor": cursor,
        }
        if filter_str:
            params["filter"] = filter_str
        else:
            params["search"] = query
        if OPENALEX_API_KEY:
            params["api_key"] = OPENALEX_API_KEY

        r = requests.get(f"{OPENALEX_BASE}/works", params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        batch = data.get("results", [])
        results.extend(batch)
        next_cursor = data.get("meta", {}).get("next_cursor")
        if not next_cursor or not batch:
            break
        cursor = next_cursor

    return [_normalize_openalex(w) for w in results[:max_results]]


def _normalize_openalex(work: dict) -> dict:
    """Convert OpenAlex work dict to normalized paper dict."""
    abstract = ""
    aii = work.get("abstract_inverted_index")
    if aii:
        words = [""] * (max(max(v) for v in aii.values()) + 1)
        for word, positions in aii.items():
            for pos in positions:
                words[pos] = word
        abstract = " ".join(w for w in words if w)

    ids = work.get("ids", {})
    pmid = ids.get("pmid", "")
    if pmid and pmid.startswith("https://pubmed.ncbi.nlm.nih.gov/"):
        pmid = pmid.split("/")[-2] if pmid.endswith("/") else pmid.split("/")[-1]

    doi = work.get("doi", "") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    primary_loc = work.get("primary_location") or {}
    source = primary_loc.get("source") or {}
    journal = source.get("display_name", "")

    return {
        "title": work.get("display_name", ""),
        "abstract": abstract,
        "doi": doi,
        "pmid": pmid,
        "year": work.get("publication_year"),
        "journal": journal,
        "source_uri": work.get("id", ""),
    }


def fetch_by_doi_openalex(doi: str):
    """Fetch a single work by DOI from OpenAlex."""
    params = {"select": "id,display_name,abstract_inverted_index,doi,ids,publication_year,primary_location"}
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    try:
        r = requests.get(
            f"{OPENALEX_BASE}/works/https://doi.org/{doi}",
            params=params,
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        return _normalize_openalex(r.json())
    except Exception:
        return None


def fetch_by_doi_ncbi(doi: str):
    """Fetch a paper by DOI via NCBI esearch."""
    try:
        r = requests.get(
            f"{NCBI_BASE}/esearch.fcgi",
            params=_ncbi_params(db="pubmed", term=f"{doi}[doi]", retmax=1),
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return None
        time.sleep(0.34)
        papers = search_pubmed(f"{doi}[doi]", max_results=1)
        return papers[0] if papers else None
    except Exception:
        return None


def fetch_by_pmid_epmc(pmid: str):
    """Fetch a single paper by PMID via EPMC."""
    _, publications = run_epmc_query(f"EXT_ID:{pmid}", page_size=10, max_results=1)
    if not publications:
        return None
    return parse_epmc_record(publications[0])


# =============================================================================
# BIORXIV/MEDRXIV CONNECTOR
# =============================================================================

def search_biorxiv(query: str, max_results: int = 20, server: str = "biorxiv") -> list:
    """Search bioRxiv/medRxiv. Fetches recent preprints and filters by keyword."""
    base = BIORXIV_BASE if server == "biorxiv" else MEDRXIV_BASE
    papers = []
    cursor = 0
    query_lower = query.lower()

    while len(papers) < max_results:
        r = requests.get(f"{base}/{server}/30d/{cursor}", headers=HEADERS, timeout=30)
        r.raise_for_status()
        collection = r.json().get("collection", [])
        if not collection:
            break

        for item in collection:
            title = item.get("title", "")
            abstract = item.get("abstract", "")
            if query_lower in title.lower() or query_lower in abstract.lower():
                doi = item.get("doi", "")
                papers.append({
                    "title": title,
                    "abstract": abstract,
                    "doi": doi,
                    "year": int(item.get("date", "0000")[:4]) if item.get("date") else None,
                    "journal": f"{server.capitalize()} preprint",
                    "source_uri": f"https://doi.org/{doi}" if doi else "",
                })
            if len(papers) >= max_results:
                break

        cursor += 100
        if len(collection) < 100:
            break
        time.sleep(0.5)

    return papers[:max_results]


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_search(args):
    """Search a literature source and store results."""
    source = args.source.lower()
    query = args.query

    if source == "epmc":
        # EPMC: cursor-based pagination, creates collection, uses rich metadata
        total_count, publications = run_epmc_query(
            query, page_size=args.page_size, max_results=args.max_results
        )

        if not publications:
            print(json.dumps({
                "success": True, "total_count": total_count, "stored_count": 0,
                "message": "No results found",
            }))
            return

        collection_id = args.collection_id or generate_id("collection")
        collection_name = args.collection or f"EPMC Search: {query[:50]}"
        timestamp = get_timestamp()

        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(
                    f'insert $c isa scilit-corpus, has id "{collection_id}", '
                    f'has name "{escape_string(collection_name)}", '
                    f'has description "EPMC search results for: {escape_string(query)}", '
                    f'has alh-logical-query "{escape_string(query)}", '
                    f'has alh-is-extensional true, has created-at {timestamp};'
                ).resolve()
                tx.commit()

            stored_count = 0
            skipped_count = 0
            paper_ids = []

            for record in tqdm(publications, desc="Storing papers", file=sys.stderr):
                paper = parse_epmc_record(record)
                if paper:
                    try:
                        paper_id = insert_epmc_paper(driver, paper, collection_id)
                        paper_ids.append(paper_id)
                        stored_count += 1
                    except Exception as e:
                        print(f"Error storing paper {paper.get('doi')}: {e}", file=sys.stderr)
                        skipped_count += 1
                else:
                    skipped_count += 1

        print(json.dumps({
            "success": True,
            "collection_id": collection_id,
            "collection_name": collection_name,
            "query": query,
            "total_count": total_count,
            "fetched_count": len(publications),
            "stored_count": stored_count,
            "skipped_count": skipped_count,
        }, indent=2))

    else:
        # PubMed / OpenAlex / bioRxiv / medRxiv
        print(f"Searching {source} for: {query}", file=sys.stderr)

        if source == "pubmed":
            papers = search_pubmed(query, args.max_results or 20)
        elif source == "openalex":
            papers = search_openalex(query, args.max_results or 20, filter_str=getattr(args, "filter", None))
        elif source in ("biorxiv", "medrxiv"):
            papers = search_biorxiv(query, args.max_results or 20, server=source)
        else:
            print(json.dumps({"success": False, "error": f"Unknown source: {source}"}))
            sys.exit(1)

        if not papers:
            print(json.dumps({"success": True, "inserted": 0, "skipped": 0, "papers": []}))
            return

        inserted = 0
        skipped = 0
        result_papers = []
        collection_id = args.collection_id or args.collection

        with get_driver() as driver:
            for paper in papers:
                existing_id = paper_exists(driver, doi=paper.get("doi"), pmid=paper.get("pmid"))
                if existing_id:
                    skipped += 1
                    result_papers.append({"id": existing_id, "title": paper["title"], "status": "existing"})
                    if collection_id:
                        try:
                            add_to_collection(driver, existing_id, collection_id)
                        except Exception as e:
                            print(f"Warning: could not add {existing_id} to collection: {e}", file=sys.stderr)
                    continue

                pid = insert_paper(driver, paper)
                inserted += 1
                result_papers.append({"id": pid, "title": paper["title"], "status": "inserted"})

                if collection_id:
                    try:
                        add_to_collection(driver, pid, collection_id)
                    except Exception as e:
                        print(f"Warning: could not add {pid} to collection: {e}", file=sys.stderr)

        print(json.dumps({
            "success": True,
            "source": source,
            "query": query,
            "inserted": inserted,
            "skipped": skipped,
            "papers": result_papers,
        }, indent=2))


def cmd_count(args):
    """Count EPMC results for a query without storing."""
    params = {"format": "JSON", "pageSize": 1, "query": args.query}
    response = requests.get(EPMC_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    print(json.dumps({"success": True, "query": args.query, "count": data["hitCount"]}))


def cmd_ingest(args):
    """Fetch and store a single paper by DOI or PMID."""
    with get_driver() as driver:
        if args.doi:
            doi = args.doi.strip()
            if doi.startswith("https://doi.org/"):
                doi = doi[len("https://doi.org/"):]

            print(f"Ingesting DOI: {doi}", file=sys.stderr)
            existing_id = paper_exists(driver, doi=doi)
            if existing_id:
                if args.collection:
                    try:
                        add_to_collection(driver, existing_id, args.collection)
                    except Exception as e:
                        print(f"Warning: could not add to collection: {e}", file=sys.stderr)
                print(json.dumps({"success": True, "paper_id": existing_id, "status": "existing"}))
                return

            # Try OpenAlex first (JSON, richer abstract), then PubMed
            paper = fetch_by_doi_openalex(doi)
            if not paper or not paper.get("title"):
                paper = fetch_by_doi_ncbi(doi)
            if not paper:
                print(json.dumps({"success": False, "error": f"Could not find DOI: {doi}"}))
                sys.exit(1)

        elif args.pmid:
            pmid = str(args.pmid).strip()
            print(f"Ingesting PMID: {pmid}", file=sys.stderr)
            existing_id = paper_exists(driver, pmid=pmid)
            if existing_id:
                if args.collection:
                    try:
                        add_to_collection(driver, existing_id, args.collection)
                    except Exception as e:
                        print(f"Warning: could not add to collection: {e}", file=sys.stderr)
                print(json.dumps({"success": True, "paper_id": existing_id, "status": "existing"}))
                return

            epmc_paper = fetch_by_pmid_epmc(pmid)
            if epmc_paper:
                pid = insert_epmc_paper(driver, epmc_paper, getattr(args, "collection", None))
                print(json.dumps({
                    "success": True, "paper_id": pid,
                    "title": epmc_paper.get("title"), "status": "inserted",
                }, indent=2))
                return
            # Fallback: search PubMed directly
            papers = search_pubmed(f"{pmid}[uid]", max_results=1)
            if not papers:
                print(json.dumps({"success": False, "error": f"Could not find PMID: {pmid}"}))
                sys.exit(1)
            paper = papers[0]
            doi = paper.get("doi")
        else:
            print(json.dumps({"success": False, "error": "Must provide --doi or --pmid"}))
            sys.exit(1)

        pid = insert_paper(driver, paper)
        if getattr(args, "collection", None) and args.collection:
            try:
                add_to_collection(driver, pid, args.collection)
            except Exception as e:
                print(f"Warning: {e}", file=sys.stderr)

    print(json.dumps({
        "success": True,
        "paper_id": pid,
        "title": paper.get("title"),
        "doi": paper.get("doi"),
        "status": "inserted",
    }, indent=2))


def arxiv_pdf_url(doi: str) -> str | None:
    """Return arXiv PDF URL from a DOI like '10.48550/arxiv.2511.02824', else None."""
    doi_lower = doi.lower()
    if "arxiv." in doi_lower:
        arxiv_id = doi_lower.split("arxiv.")[-1]
        return f"https://arxiv.org/pdf/{arxiv_id}"
    return None


def _blockparse_fulltext(pdf_full_path):
    """Canonical full-text extraction: the LA-PDFText-derived, layout-aware block
    parser (`pdf_layout_parser`). Classifies blocks by geometry/typography, drops
    running heads/footers, the journal metadata sidebar, decorative noise and table
    interiors, and assembles column-aware reading order. Returns
    (markdown, page_count, type_counts). Replaces the former kreuzberg extraction,
    which garbled two-column/sidebar first pages and mangled unit glyphs."""
    doc = fitz.open(pdf_full_path)
    n_pages = doc.page_count
    doc.close()
    blocks = load_blocks(pdf_full_path)
    stats = compute_doc_stats(blocks, n_pages)
    classify_blocks(blocks, stats, n_pages)
    suppress_table_bodies(pdf_full_path, blocks, stats)
    blocks = regroup_captions(blocks, stats)
    ordered = assemble_reading_order(blocks, stats)
    return render_markdown(ordered), n_pages, dict(Counter(b.type for b in blocks))


def cmd_fetch_pdf(args):
    """Download a paper PDF, extract full text, save both to disk, store artifact in TypeDB."""
    if not PYMUPDF_AVAILABLE:
        print(json.dumps({"success": False,
                          "error": "pymupdf not installed (required for layout-aware text extraction). Run: uv add pymupdf"}))
        sys.exit(1)
    if not CACHE_AVAILABLE:
        print(json.dumps({"success": False,
                          "error": "skillful_alhazen.utils.cache not available"}))
        sys.exit(1)

    paper_id = args.id
    pdf_url = None
    paper_name = ""

    with get_driver() as driver:
        # Resolve paper from TypeDB
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                f'fetch {{ "name": $p.name, "doi": $p.scilit-doi, "arxiv-id": $p.scilit-arxiv-id }};'
            ).resolve())
        if not results:
            print(json.dumps({"success": False, "error": f"Paper not found: {paper_id}"}))
            sys.exit(1)

        p = results[0]
        paper_name = p.get("name") or ""
        doi = p.get("doi") or ""
        arxiv_id_attr = p.get("arxiv-id") or ""

        # Check for existing pdf artifact to avoid re-download
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            existing = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                f'$a isa scilit-pdf-fulltext; '
                f'(alh-artifact: $a, referent: $p) isa alh-representation; '
                f'fetch {{ "id": $a.id, "cache-path": $a.cache-path, "source-uri": $a.source-uri }};'
            ).resolve())
        if existing and not getattr(args, "force", False):
            art = existing[0]
            artifact_id = art.get("id")
            text_cache_path = art.get("cache-path") or ""
            # renditions are siblings sharing the artifact-id base; pdf = swap the suffix
            pdf_cache_path = text_cache_path.replace(".txt", ".pdf") if text_cache_path else ""
            print(json.dumps({
                "success": True,
                "paper_id": paper_id,
                "artifact_id": artifact_id,
                "status": "existing",
                "text_cache_path": text_cache_path,
                "pdf_cache_path": pdf_cache_path,
                "source_uri": art.get("source-uri"),
            }, indent=2))
            return

    # Local-file ingestion: read bytes from a PDF already on disk (e.g. a manually
    # downloaded paywalled paper) instead of fetching over the network.
    if getattr(args, "file", None):
        if not os.path.isfile(args.file):
            print(json.dumps({"success": False, "error": f"--file not found: {args.file}"})); sys.exit(1)
        with open(args.file, "rb") as fh:
            pdf_bytes = fh.read()
        pdf_url = f"file://{os.path.abspath(args.file)}"
    else:
        # Build PDF URL
        if arxiv_id_attr:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id_attr}"
        elif doi:
            pdf_url = arxiv_pdf_url(doi)
        if args.url:
            pdf_url = args.url  # explicit override
        if not pdf_url:
            print(json.dumps({"success": False,
                              "error": "Cannot determine PDF URL. Provide --url explicitly."}))
            sys.exit(1)

        print(f"Downloading PDF from {pdf_url} ...", file=sys.stderr)
        resp = requests.get(pdf_url, timeout=60, allow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0 (compatible; alhazen/1.0)"})
        resp.raise_for_status()
        pdf_bytes = resp.content

    if pdf_bytes[:4] != b"%PDF":
        print(json.dumps({"success": False,
                          "error": "Response is not a PDF (bad file/URL or access denied)"}))
        sys.exit(1)

    # Deterministic full-text artifact id; both renditions live in fulltext/<paper-id>/,
    # named by the artifact id and sharing the base (suffix = format).
    artifact_id = f"scilit-fulltext-{paper_id.split('-')[-1]}"
    subdir = f"fulltext/{paper_id}"

    # Save PDF source  ->  fulltext/<paper-id>/<artifact-id>.pdf
    pdf_cache = save_to_cache(artifact_id, pdf_bytes, "application/pdf", subdir=subdir)

    # Extract full text with the LA-PDFText-derived layout-aware block parser
    # (pdf_layout_parser) — the sole extractor. It preserves reading order and unit
    # glyphs, de-hyphenates, and drops running heads/footers, the journal metadata
    # sidebar, decorative noise and table interiors by structural signals. (The former
    # kreuzberg path was removed: it garbled two-column/sidebar first pages and mangled
    # units, e.g. "25 mM" -> "25 mtti".)
    print(f"Extracting text ({len(pdf_bytes):,} bytes, {pdf_cache['full_path']}) ...",
          file=sys.stderr)
    full_text, page_count, type_counts = _blockparse_fulltext(pdf_cache["full_path"])
    print(f"Extracted {len(full_text):,} chars; blocks={type_counts}.", file=sys.stderr)
    text_cache = save_to_cache(artifact_id, full_text, "text/plain", subdir=subdir)

    timestamp = get_timestamp()

    # Upsert the scilit-pdf-fulltext artifact (deterministic id). cache-path -> the .txt
    # rendition (indexable); the .pdf is the sibling by suffix.
    name_esc = escape_string(f"{paper_name} [full text]")
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            # idempotent (handles --force re-download): drop any prior artifact at this id
            tx.query(f'match $a isa alh-artifact, has id "{artifact_id}"; '
                     f'$r isa alh-fragmentation, links (whole: $a); delete $r;').resolve()
            tx.query(f'match $a isa alh-artifact, has id "{artifact_id}"; '
                     f'$r isa alh-representation, links (alh-artifact: $a); delete $r;').resolve()
            tx.query(f'match $a isa alh-artifact, has id "{artifact_id}"; delete $a;').resolve()
            tx.query(
                f'insert $a isa scilit-pdf-fulltext, '
                f'has id "{artifact_id}", '
                f'has name "{name_esc}", '
                f'has source-uri "{escape_string(pdf_url)}", '
                f'has cache-path "{escape_string(text_cache["cache_path"])}", '
                f'has scilit-fulltext-kind "pdf", '
                f'has mime-type "text/plain", '
                f'has file-size {text_cache["file_size"]}, '
                f'has content-hash "{text_cache["content_hash"]}", '
                f'has format "pdf-block-classified-markdown", '
                f'has created-at {timestamp};'
            ).resolve()
            tx.commit()

        # Link artifact -> paper via representation + mark the paper held
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                f'$a isa scilit-pdf-fulltext, has id "{artifact_id}"; '
                f'insert (alh-artifact: $a, referent: $p) isa alh-representation;'
            ).resolve()
            held = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(paper_id)}", '
                f'has scilit-acquisition-status $s; fetch {{ "s": $s }};').resolve())
            if not held:
                tx.query(f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                         f'insert $p has scilit-acquisition-status "held";').resolve()
            tx.commit()

    print(json.dumps({
        "success": True,
        "paper_id": paper_id,
        "paper_name": paper_name,
        "artifact_id": artifact_id,
        "status": "inserted",
        "source_uri": pdf_url,
        "pdf_cache_path": pdf_cache["cache_path"],
        "text_cache_path": text_cache["cache_path"],
        "pdf_full_path": pdf_cache["full_path"],
        "text_full_path": text_cache["full_path"],
        "page_count": page_count,
        "char_count": len(full_text),
        "file_size_bytes": text_cache["file_size"],
    }, indent=2))


def cmd_parse_pdf_blocks(args):
    """Re-extract a paper's CANONICAL full text from its already-cached PDF using the
    layout-aware block parser (LA-PDFText-derived, PyMuPDF — see pdf_layout_parser.py),
    without re-downloading. Updates the canonical scilit-pdf-fulltext artifact's text
    attributes IN PLACE, preserving its figure/table fragments and paper link. Use this
    to refresh full text after a parser change; `fetch-pdf` uses the same extractor on
    first ingest. (The block parser is now the sole extractor — kreuzberg was removed.)
    """
    if not PYMUPDF_AVAILABLE:
        print(json.dumps({"success": False,
                          "error": "pymupdf not installed. Run: uv add pymupdf"}))
        sys.exit(1)
    if not CACHE_AVAILABLE:
        print(json.dumps({"success": False,
                          "error": "skillful_alhazen.utils.cache not available"}))
        sys.exit(1)

    paper_id = args.id

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                f'fetch {{ "name": $p.name }};'
            ).resolve())
        if not results:
            print(json.dumps({"success": False, "error": f"Paper not found: {paper_id}"}))
            sys.exit(1)
        paper_name = results[0].get("name") or ""

        # Reuse the PDF `fetch-pdf` already downloaded — this command never fetches.
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            existing = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                f'$a isa scilit-pdf-fulltext; '
                f'(alh-artifact: $a, referent: $p) isa alh-representation; '
                f'fetch {{ "cache-path": $a.cache-path }};'
            ).resolve())

    pdf_cache_path = None
    for art in existing:
        cp = art.get("cache-path") or ""
        candidate = cp[:-4] + ".pdf" if cp.endswith(".txt") else cp
        if candidate.endswith(".pdf") and (_get_cache_dir() / candidate).exists():
            pdf_cache_path = candidate
            break
    if not pdf_cache_path:
        print(json.dumps({"success": False,
                          "error": f"No cached PDF found for {paper_id}. Run fetch-pdf first."}))
        sys.exit(1)
    pdf_full_path = str(_get_cache_dir() / pdf_cache_path)

    print(f"Re-extracting canonical text ({pdf_full_path}) ...", file=sys.stderr)
    full_text, n_pages, type_counts = _blockparse_fulltext(pdf_full_path)
    print(f"Classified blocks: {type_counts}", file=sys.stderr)

    # Write to the CANONICAL full-text artifact (same id fetch-pdf uses). Update its
    # text attributes IN PLACE — never delete/reinsert the artifact entity — so the
    # figure/table fragments attached via alh-fragmentation (from extract-floats) and
    # the paper representation link survive a re-extract.
    artifact_id = f"scilit-fulltext-{paper_id.split('-')[-1]}"
    subdir = f"fulltext/{paper_id}"
    text_cache = save_to_cache(artifact_id, full_text, "text/plain", subdir=subdir)

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            exists = list(tx.query(
                f'match $a isa scilit-pdf-fulltext, has id "{artifact_id}"; '
                f'fetch {{ "id": $a.id }};').resolve())
        if not exists:
            print(json.dumps({"success": False,
                              "error": f"No canonical full-text artifact for {paper_id}. Run fetch-pdf first."}))
            sys.exit(1)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            for attr, val in (
                ("cache-path", f'"{escape_string(text_cache["cache_path"])}"'),
                ("content-hash", f'"{text_cache["content_hash"]}"'),
                ("file-size", str(text_cache["file_size"])),
                ("format", '"pdf-block-classified-markdown"'),
                ("mime-type", '"text/plain"'),
            ):
                tx.query(f'match $a isa scilit-pdf-fulltext, has id "{artifact_id}", has {attr} $v; '
                         f'delete has $v of $a;').resolve()
                tx.query(f'match $a isa scilit-pdf-fulltext, has id "{artifact_id}"; '
                         f'insert $a has {attr} {val};').resolve()
            tx.commit()

    print(json.dumps({
        "success": True,
        "paper_id": paper_id,
        "artifact_id": artifact_id,
        "text_cache_path": text_cache["cache_path"],
        "block_type_counts": type_counts,
        "char_count": len(full_text),
    }, indent=2))


def cmd_extract_floats(args):
    """EXPERIMENTAL: render each figure/table to a PNG and store it as a scilit-figure /
    scilit-table fragment (number + caption + the cropped image + structured table rows),
    linked to the paper's full-text artifact via alh-fragmentation. Reuses the PDF that
    `fetch-pdf` downloaded; never re-downloads. Detection is caption-anchored +
    negative-space (see figure_extract.py) so it handles raster AND vector figures, ruled
    tables, cross-page legends, and multiple floats per page. Idempotent per (paper, number)."""
    if not PYMUPDF_AVAILABLE:
        print(json.dumps({"success": False,
                          "error": "pymupdf not installed. Run: uv add pymupdf"}))
        sys.exit(1)

    paper_id = args.id
    paper_hash = paper_id.split("-")[-1]
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            res = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                f'fetch {{ "name": $p.name }};').resolve())
        if not res:
            print(json.dumps({"success": False, "error": f"Paper not found: {paper_id}"}))
            sys.exit(1)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            existing = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                f'$a isa scilit-pdf-fulltext; '
                f'(alh-artifact: $a, referent: $p) isa alh-representation; '
                f'fetch {{ "id": $a.id, "cache-path": $a.cache-path }};').resolve())

    pdf_cache_path = None
    whole_artifact_id = None
    for art in existing:
        aid = art.get("id") or ""
        if aid == f"scilit-fulltext-{paper_hash}":
            whole_artifact_id = aid
        cp = art.get("cache-path") or ""
        cand = cp[:-4] + ".pdf" if cp.endswith(".txt") else cp
        if cand.endswith(".pdf") and (_get_cache_dir() / cand).exists():
            pdf_cache_path = cand
    if whole_artifact_id is None and existing:
        whole_artifact_id = existing[0].get("id")
    if not pdf_cache_path:
        print(json.dumps({"success": False,
                          "error": f"No cached PDF for {paper_id}. Run fetch-pdf first."}))
        sys.exit(1)
    if not whole_artifact_id:
        print(json.dumps({"success": False,
                          "error": f"No full-text artifact for {paper_id}."}))
        sys.exit(1)
    pdf_full_path = str(_get_cache_dir() / pdf_cache_path)

    print(f"Extracting floats ({pdf_full_path}) ...", file=sys.stderr)
    doc, floats = figure_extract.extract_floats(pdf_full_path)
    ts = get_timestamp()
    subdir = f"fulltext/{paper_id}"
    manifest = []
    with get_driver() as driver:
        for f in floats:
            entry = {"kind": f.kind, "number": f.number,
                     "caption_page": f.caption_page + 1,
                     "unpaired": f.unpaired, "reason": f.reason}
            if f.unpaired or f.region is None:
                manifest.append(entry)
                continue
            png = figure_extract.render_region(doc[f.region.page], f.region.rect)
            frag_id = f"scilit-{'fig' if f.kind == 'figure' else 'tbl'}-{paper_hash}-{f.number}"
            cache = save_to_cache(frag_id, png, "image/png", subdir=subdir)
            etype = "scilit-figure" if f.kind == "figure" else "scilit-table"
            numattr = "scilit-figure-number" if f.kind == "figure" else "scilit-table-number"
            content = (json.dumps(f.table_rows) if (f.kind == "table" and f.table_rows)
                       else f.caption_text)
            fmt = "figure-page-crop" if f.kind == "figure" else "table-page-crop"
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                # idempotent: drop any prior fragment at this id + its fragmentation link
                tx.query(f'match $f isa alh-fragment, has id "{frag_id}"; '
                         f'$r isa alh-fragmentation, links (part: $f); delete $r;').resolve()
                tx.query(f'match $f isa alh-fragment, has id "{frag_id}"; delete $f;').resolve()
                tx.query(
                    f'insert $f isa {etype}, has id "{frag_id}", '
                    f'has {numattr} "{escape_string(f.number)}", '
                    f'has scilit-caption "{escape_string(f.caption_text)}", '
                    f'has content "{escape_string(content)}", '
                    f'has cache-path "{escape_string(cache["cache_path"])}", '
                    f'has mime-type "image/png", '
                    f'has content-hash "{cache["content_hash"]}", '
                    f'has file-size {cache["file_size"]}, '
                    f'has format "{fmt}", '
                    f'has offset 0, has length {cache["file_size"]}, '
                    f'has created-at {ts};').resolve()
                tx.commit()
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(
                    f'match $a isa alh-artifact, has id "{whole_artifact_id}"; '
                    f'$f isa alh-fragment, has id "{frag_id}"; '
                    f'insert (whole: $a, part: $f) isa alh-fragmentation;').resolve()
                tx.commit()
            entry.update({"fragment_id": frag_id, "cache_path": cache["cache_path"],
                          "image_page": f.region.page + 1,
                          "table_rows": len(f.table_rows) if f.table_rows else None})
            manifest.append(entry)
    doc.close()
    paired = [m for m in manifest if not m["unpaired"]]
    print(json.dumps({"success": True, "paper_id": paper_id,
                      "whole_artifact": whole_artifact_id,
                      "n_paired": len(paired), "n_flagged": len(manifest) - len(paired),
                      "floats": manifest}, indent=2))


def cmd_show(args):
    """Show a paper's details for sensemaking."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            result = list(tx.query(
                f'match $p isa scilit-paper, has id "{args.id}"; '
                f'fetch {{ "id": $p.id, "name": $p.name, "abstract-text": $p.abstract-text, '
                f'"doi": $p.scilit-doi, "pmid": $p.scilit-pmid, "year": $p.scilit-publication-year, '
                f'"journal": $p.scilit-journal-name, "volume": $p.scilit-journal-volume, '
                f'"issue": $p.scilit-journal-issue, "pages": $p.scilit-page-range, '
                f'"authors": $p.scilit-author-list, "source-uri": $p.source-uri }};'
            ).resolve())

            if not result:
                print(json.dumps({"success": False, "error": "Paper not found"}))
                sys.exit(1)

            notes = list(tx.query(
                f'match $p isa scilit-paper, has id "{args.id}"; '
                f'(note: $n, subject: $p) isa alh-aboutness; '
                f'fetch {{ "id": $n.id, "name": $n.name, "content": $n.content }};'
            ).resolve())

            art_results = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(args.id)}"; '
                f'$a isa scilit-pdf-fulltext; '
                f'(alh-artifact: $a, referent: $p) isa alh-representation; '
                f'fetch {{ "id": $a.id, "source-uri": $a.source-uri, '
                f'"cache-path": $a.cache-path, "file-size": $a.file-size }};'
            ).resolve())

            kw_results = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(args.id)}", '
                f'has scilit-keyword $k; fetch {{ "k": $k }};'
            ).resolve())

    paper = {k: v for k, v in result[0].items() if v is not None}
    keywords = [r["k"] for r in kw_results]
    print(json.dumps({
        "success": True,
        "paper": paper,
        "keywords": keywords,
        "notes": [{k: v for k, v in n.items() if v is not None} for n in notes],
        "pdf_artifacts": [{k: v for k, v in a.items() if v is not None} for a in art_results],
    }, indent=2))


def cmd_list(args):
    """List papers, optionally filtered by collection."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            if args.collection:
                query = (
                    f'match $c isa alh-collection, has id "{args.collection}"; '
                    f'(collection: $c, member: $p) isa alh-collection-membership; '
                    f'$p isa scilit-paper; '
                    f'fetch {{ "id": $p.id, "name": $p.name, "doi": $p.scilit-doi, "year": $p.scilit-publication-year }};'
                )
            else:
                query = (
                    'match $p isa scilit-paper; '
                    'fetch { "id": $p.id, "name": $p.name, "doi": $p.scilit-doi, "year": $p.scilit-publication-year };'
                )
            results = list(tx.query(query).resolve())

    papers = [{k: v for k, v in r.items() if v is not None} for r in results]
    print(json.dumps({
        "success": True,
        "papers": papers,
        "count": len(papers),
        "collection": args.collection if hasattr(args, "collection") else None,
    }, indent=2))


def cmd_list_collections(args):
    """List all scilit-corpus collections — search corpora (with a logical query)
    and investigation paper sets (curated by trace, no logical query)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(
                'match $c isa scilit-corpus; '
                'fetch { "id": $c.id, "name": $c.name, "description": $c.description, '
                '"logical-query": $c.alh-logical-query };'
            ).resolve())

    collections = [{k: v for k, v in r.items() if v is not None} for r in results]
    print(json.dumps({"success": True, "collections": collections, "count": len(collections)}, indent=2))


def cmd_list_by_keyword(args):
    """List papers tagged with a keyword, optionally scoped to a collection."""
    keyword = args.keyword
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            if args.collection:
                query = (
                    f'match $c isa alh-collection, has id "{escape_string(args.collection)}"; '
                    f'(collection: $c, member: $p) isa alh-collection-membership; '
                    f'$p isa scilit-paper, has scilit-keyword "{escape_string(keyword)}", '
                    f'has scilit-publication-year $yr; '
                    f'fetch {{ "id": $p.id, "name": $p.name, "abstract": $p.abstract-text, '
                    f'"year": $yr, "doi": $p.scilit-doi, "journal": $p.scilit-journal-name }};'
                )
            else:
                query = (
                    f'match $p isa scilit-paper, has scilit-keyword "{escape_string(keyword)}", '
                    f'has scilit-publication-year $yr; '
                    f'fetch {{ "id": $p.id, "name": $p.name, "abstract": $p.abstract-text, '
                    f'"year": $yr, "doi": $p.scilit-doi, "journal": $p.scilit-journal-name }};'
                )
            results = list(tx.query(query).resolve())

    papers = [{k: v for k, v in r.items() if v is not None} for r in results]

    # Apply year-range filter in Python
    if args.year_from:
        papers = [p for p in papers if p.get("year") and int(p["year"]) >= args.year_from]
    if args.year_to:
        papers = [p for p in papers if p.get("year") and int(p["year"]) <= args.year_to]

    # Sort by year ascending
    papers.sort(key=lambda p: int(p.get("year", 0)))

    # Apply limit
    if args.limit:
        papers = papers[:args.limit]

    years = [int(p["year"]) for p in papers if p.get("year")]
    year_range = [min(years), max(years)] if years else []

    print(json.dumps({
        "success": True,
        "keyword": keyword,
        "collection": args.collection,
        "count": len(papers),
        "year_range": year_range,
        "papers": papers,
    }, indent=2))


# =============================================================================
# SEMANTIC SEARCH + CLUSTERING COMMANDS
# =============================================================================

def _get_collection_papers(driver, collection_id: str) -> list:
    """Fetch all scilit-papers in a collection from TypeDB."""
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        results = list(tx.query(
            f'match $c isa alh-collection, has id "{collection_id}"; '
            f'(collection: $c, member: $p) isa alh-collection-membership; '
            f'$p isa scilit-paper; '
            f'fetch {{ "id": $p.id, "name": $p.name, '
            f'"abstract-text": $p.abstract-text, '
            f'"doi": $p.scilit-doi, "year": $p.scilit-publication-year }};'
        ).resolve())
    return [{k: v for k, v in r.items() if v is not None} for r in results]


def cmd_embed(args):
    """Fetch papers from TypeDB, embed with Voyage AI, upsert into Qdrant."""
    try:
        from skillful_alhazen.utils.embeddings import VOYAGE_BATCH_SIZE, embed_texts
        from skillful_alhazen.utils.vector_store import (
            ensure_collection, get_existing_paper_ids, get_qdrant_client, upsert_papers,
        )
    except ImportError as e:
        print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
        sys.exit(1)

    if not VOYAGE_API_KEY:
        print(json.dumps({"success": False, "error": "VOYAGE_API_KEY not set"}))
        sys.exit(1)

    collection_id = args.collection
    print(f"Fetching papers for collection {collection_id}...", file=sys.stderr)

    with get_driver() as driver:
        papers = _get_collection_papers(driver, collection_id)

    if not papers:
        print(json.dumps({"success": False, "error": "No papers found in collection"}))
        sys.exit(1)

    print(f"Found {len(papers)} papers", file=sys.stderr)

    qdrant = get_qdrant_client()
    ensure_collection(qdrant)

    all_ids = [p["id"] for p in papers]
    if args.reembed:
        already_in_qdrant = 0
        to_embed = papers
    else:
        existing_ids = get_existing_paper_ids(qdrant, all_ids)
        already_in_qdrant = len(existing_ids)
        to_embed = [p for p in papers if p["id"] not in existing_ids]

    if args.limit > 0:
        to_embed = to_embed[:args.limit]

    print(f"Embedding {len(to_embed)} papers ({already_in_qdrant} already in Qdrant)...", file=sys.stderr)

    if not to_embed:
        print(json.dumps({
            "success": True, "embedded": 0, "skipped": already_in_qdrant,
            "collection_id": collection_id,
        }, indent=2))
        return

    texts = [f"{p.get('name', '')}\n\n{p.get('abstract-text', '')}" for p in to_embed]

    all_vectors = []
    for i in range(0, len(texts), VOYAGE_BATCH_SIZE):
        batch_end = min(i + VOYAGE_BATCH_SIZE, len(texts))
        print(f"  Embedding {i + 1}-{batch_end} / {len(texts)}...", file=sys.stderr)
        batch_vectors = embed_texts(texts[i:batch_end], input_type="document")
        all_vectors.extend(batch_vectors)

    points = [
        {
            "paper_id": p["id"],
            "vector": v,
            "title": p.get("name", ""),
            "collection_ids": [collection_id],
            "doi": p.get("doi", ""),
            "year": p.get("year"),
        }
        for p, v in zip(to_embed, all_vectors)
    ]
    upsert_papers(qdrant, points)

    print(json.dumps({
        "success": True,
        "embedded": len(to_embed),
        "skipped": already_in_qdrant,
        "collection_id": collection_id,
    }, indent=2))


def cmd_search_semantic(args):
    """Embed a query and return similar papers from Qdrant."""
    try:
        from skillful_alhazen.utils.embeddings import embed_texts
        from skillful_alhazen.utils.vector_store import get_qdrant_client, search_similar
    except ImportError as e:
        print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
        sys.exit(1)

    if not VOYAGE_API_KEY:
        print(json.dumps({"success": False, "error": "VOYAGE_API_KEY not set"}))
        sys.exit(1)

    print(f"Embedding query: {args.query}", file=sys.stderr)
    query_vector = embed_texts([args.query], input_type="query")[0]

    qdrant = get_qdrant_client()
    results = search_similar(qdrant, query_vector, collection_id=args.collection, limit=args.limit)

    print(json.dumps({
        "success": True,
        "query": args.query,
        "collection": args.collection,
        "results": results,
    }, indent=2))


def cmd_cluster(args):
    """Cluster collection embeddings with UMAP + HDBSCAN."""
    try:
        import hdbscan
        import numpy as np
        import umap
        from skillful_alhazen.utils.vector_store import get_collection_vectors, get_qdrant_client
    except ImportError as e:
        print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
        sys.exit(1)

    collection_id = args.collection
    print(f"Loading vectors for collection {collection_id}...", file=sys.stderr)

    qdrant = get_qdrant_client()
    points = get_collection_vectors(qdrant, collection_id)

    if not points:
        print(json.dumps({"success": False, "error": "No vectors found for collection"}))
        sys.exit(1)

    n = len(points)
    print(f"Reducing {n} papers with UMAP...", file=sys.stderr)

    vectors = np.array([p["vector"] for p in points], dtype=np.float32)
    reducer = umap.UMAP(
        n_components=50, n_neighbors=min(15, n - 1),
        min_dist=0.0, metric="cosine", random_state=42,
    )
    reduced = reducer.fit_transform(vectors)

    print(f"Clustering with HDBSCAN (min_cluster_size={args.min_cluster_size})...", file=sys.stderr)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=args.min_cluster_size, metric="euclidean")
    labels = clusterer.fit_predict(reduced)

    clusters = []
    for label in sorted(set(labels)):
        if label == -1:
            continue
        mask = labels == label
        cluster_indices = np.where(mask)[0]
        centroid = reduced[cluster_indices].mean(axis=0)
        dists = np.linalg.norm(reduced[cluster_indices] - centroid, axis=1)
        closest_idx = np.argsort(dists)[:5]
        representative_papers = [
            {
                "paper_id": points[cluster_indices[i]]["paper_id"],
                "title": points[cluster_indices[i]]["title"],
                "doi": points[cluster_indices[i]].get("doi", ""),
            }
            for i in closest_idx
        ]
        clusters.append({
            "cluster_id": int(label),
            "size": int(mask.sum()),
            "representative_papers": representative_papers,
        })

    noise_count = int((labels == -1).sum())

    if not args.dry_run and args.labels:
        label_map = {}
        for entry in args.labels:
            parts = entry.split(":", 1)
            if len(parts) == 2:
                try:
                    label_map[int(parts[0])] = parts[1]
                except ValueError:
                    pass

        if label_map:
            print("Writing theme tags to TypeDB...", file=sys.stderr)
            with get_driver() as driver:
                for cluster in clusters:
                    cid = cluster["cluster_id"]
                    theme = label_map.get(cid)
                    if not theme:
                        continue
                    cluster_paper_ids = [
                        points[i]["paper_id"] for i in np.where(labels == cid)[0]
                    ]
                    theme_escaped = escape_string(theme)
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        for pid in cluster_paper_ids:
                            try:
                                tx.query(
                                    f'match $p isa scilit-paper, has id "{pid}"; '
                                    f'insert $p has scilit-keyword "{theme_escaped}";'
                                ).resolve()
                            except Exception:
                                pass
                        tx.commit()
                    print(f"  Tagged {len(cluster_paper_ids)} papers with '{theme}'", file=sys.stderr)

    print(json.dumps({
        "success": True,
        "collection_id": collection_id,
        "total_papers": len(points),
        "clustered": len(points) - noise_count,
        "noise": noise_count,
        "num_clusters": len(clusters),
        "clusters": clusters,
    }, indent=2))


def cmd_plot_clusters(args):
    """Generate a 2D UMAP scatter plot coloured by HDBSCAN cluster."""
    try:
        import hdbscan
        import matplotlib.pyplot as plt
        import numpy as np
        import umap
        from skillful_alhazen.utils.vector_store import get_collection_vectors, get_qdrant_client
    except ImportError as e:
        print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
        sys.exit(1)

    collection_id = args.collection
    output = args.output

    print(f"Loading vectors for collection {collection_id}...", file=sys.stderr)
    qdrant = get_qdrant_client()
    points = get_collection_vectors(qdrant, collection_id)

    if not points:
        print(json.dumps({"success": False, "error": "No vectors found for collection"}))
        sys.exit(1)

    n = len(points)
    vectors = np.array([p["vector"] for p in points], dtype=np.float32)

    print("UMAP 50-dim for clustering...", file=sys.stderr)
    reducer_50 = umap.UMAP(
        n_components=50, n_neighbors=min(15, n - 1),
        min_dist=0.0, metric="cosine", random_state=42,
    )
    reduced_50 = reducer_50.fit_transform(vectors)

    print(f"HDBSCAN (min_cluster_size={args.min_cluster_size})...", file=sys.stderr)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=args.min_cluster_size, metric="euclidean")
    labels = clusterer.fit_predict(reduced_50)

    print("UMAP 2-dim for plot...", file=sys.stderr)
    reducer_2d = umap.UMAP(
        n_components=2, n_neighbors=min(15, n - 1),
        min_dist=0.1, metric="euclidean", random_state=42,
    )
    xy = reducer_2d.fit_transform(reduced_50)

    unique_labels = sorted(set(labels))
    cluster_labels = [l for l in unique_labels if l != -1]
    cmap = plt.colormaps["tab20"].resampled(max(len(cluster_labels), 1))
    colour_map = {l: cmap(i % 20) for i, l in enumerate(cluster_labels)}
    colour_map[-1] = (0.8, 0.8, 0.8, 0.3)
    colours = [colour_map[l] for l in labels]

    label_map = {}
    if args.labels:
        for entry in args.labels:
            parts = entry.split(":", 1)
            if len(parts) == 2:
                try:
                    label_map[int(parts[0])] = parts[1]
                except ValueError:
                    pass

    fig, ax = plt.subplots(figsize=(14, 10))
    ax.scatter(xy[:, 0], xy[:, 1], c=colours, s=6, linewidths=0)

    for label in cluster_labels:
        mask = labels == label
        cx, cy = xy[mask, 0].mean(), xy[mask, 1].mean()
        size = mask.sum()
        theme = label_map.get(label)
        text = f"{theme}\n(C{label}, n={size})" if theme else f"C{label} (n={size})"
        ax.annotate(text, (cx, cy), fontsize=7, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.75, lw=0))

    noise_count = (labels == -1).sum()
    clustered = n - noise_count
    ax.set_title(
        f"Literature corpus -- {n} papers, {len(cluster_labels)} clusters, "
        f"{clustered} assigned ({noise_count} noise)\n"
        f"UMAP(cosine->50d) + HDBSCAN(min_size={args.min_cluster_size})",
        fontsize=11,
    )
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()

    print(json.dumps({
        "success": True, "output": output,
        "num_clusters": len(cluster_labels),
        "clustered": int(clustered),
        "noise": int(noise_count),
        "total": n,
    }, indent=2))


# Facet namespaces written by the scilit-faceting pipeline (scilit-keyword "<ns>:<value>").
FACET_NAMESPACES = [
    "topology", "stage", "concern", "contribution",
    "domain", "autonomy", "memory", "se-agent",
]


def cmd_map(args):
    """2D UMAP embedding map (JSON) of one or more corpora for the dashboard.

    Reuses the plot-clusters pipeline (UMAP-50 cosine -> HDBSCAN -> UMAP-2D) but emits
    per-paper JSON instead of a PNG, joining in fresh TypeDB metadata: the 8 facet tags
    plus each paper's corpus membership. The client colours points by facet / cluster / corpus.
    """
    try:
        import hdbscan
        import numpy as np
        import umap
        from skillful_alhazen.utils.vector_store import get_collection_vectors, get_qdrant_client
    except ImportError as e:
        print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
        sys.exit(1)

    # Resolve target corpus ids: explicit --collection(s), or --all (every scilit-corpus).
    if args.all:
        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                rows = list(tx.query(
                    'match $c isa scilit-corpus; fetch { "id": $c.id };'
                ).resolve())
        collection_ids = [r["id"] for r in rows]
    else:
        collection_ids = args.collection or []

    if not collection_ids:
        print(json.dumps({"success": False, "error": "No collections (use --collection or --all)"}))
        sys.exit(1)

    # Load + dedup vectors across corpora; track per-paper corpus membership.
    qdrant = get_qdrant_client()
    paper_map = {}
    for cid in collection_ids:
        for p in get_collection_vectors(qdrant, cid):
            pid = p["paper_id"]
            entry = paper_map.get(pid)
            if entry is None:
                entry = {
                    "paper_id": pid,
                    "title": p.get("title", ""),
                    "year": p.get("year"),
                    "vector": p["vector"],
                    "corpus_ids": set(),
                }
                paper_map[pid] = entry
            entry["corpus_ids"].add(cid)

    points = list(paper_map.values())
    n = len(points)
    if n == 0:
        print(json.dumps({"success": False, "error": "No vectors found for the given collections"}))
        sys.exit(1)

    vectors = np.array([p["vector"] for p in points], dtype=np.float32)

    if n < 3:
        # Too few points to reduce/cluster; emit a degenerate layout.
        xy = np.zeros((n, 2), dtype=np.float32)
        labels = np.array([-1] * n)
    else:
        print(f"UMAP 50-dim for clustering ({n} papers)...", file=sys.stderr)
        reduced_50 = umap.UMAP(
            n_components=min(50, n - 1), n_neighbors=min(15, n - 1),
            min_dist=0.0, metric="cosine", random_state=42,
        ).fit_transform(vectors)

        print(f"HDBSCAN (min_cluster_size={args.min_cluster_size})...", file=sys.stderr)
        labels = hdbscan.HDBSCAN(
            min_cluster_size=args.min_cluster_size, metric="euclidean",
        ).fit_predict(reduced_50)

        print("UMAP 2-dim for layout...", file=sys.stderr)
        xy = umap.UMAP(
            n_components=2, n_neighbors=min(15, n - 1),
            min_dist=0.1, metric="euclidean", random_state=42,
        ).fit_transform(reduced_50)

    # Join in facet tags from TypeDB (one READ txn; a row per keyword per paper).
    facets_by_paper = {p["paper_id"]: {} for p in points}
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            for p in points:
                pid = p["paper_id"]
                rows = list(tx.query(
                    f'match $p isa scilit-paper, has id "{escape_string(pid)}", '
                    f'has scilit-keyword $k; fetch {{ "k": $k }};'
                ).resolve())
                for r in rows:
                    tag = r["k"]
                    if ":" not in tag:
                        continue
                    ns, value = tag.split(":", 1)
                    if ns in FACET_NAMESPACES:
                        facets_by_paper[pid][ns] = value

    items = []
    for i, p in enumerate(points):
        items.append({
            "paper_id": p["paper_id"],
            "x": float(xy[i][0]),
            "y": float(xy[i][1]),
            "cluster": int(labels[i]),
            "title": p["title"],
            "year": p["year"],
            "corpus_ids": sorted(p["corpus_ids"]),
            "facets": facets_by_paper[p["paper_id"]],
        })

    num_clusters = len({int(l) for l in labels if int(l) != -1})
    print(json.dumps({
        "success": True,
        "count": n,
        "num_clusters": num_clusters,
        "collection_ids": collection_ids,
        "items": items,
    }, indent=2))


# =============================================================================
# APT SECTION EMBEDDING COMMANDS
# =============================================================================

def cmd_embed_sections(args):
    """Fetch scilit-section fragments for a paper, embed them, upsert into apt-sections Qdrant collection."""
    try:
        from skillful_alhazen.utils.embeddings import VOYAGE_BATCH_SIZE, embed_texts
        from skillful_alhazen.utils.vector_store import get_qdrant_client
        from qdrant_client import models as qdrant_models
    except ImportError as e:
        print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
        sys.exit(1)

    if not VOYAGE_API_KEY:
        print(json.dumps({"success": False, "error": "VOYAGE_API_KEY not set"}))
        sys.exit(1)

    paper_id = args.paper_id
    collection_name = args.collection
    mondo_id = args.tag_mondo_id or ""

    print(f"Fetching sections for paper {paper_id}...", file=sys.stderr)

    query = (
        f'match '
        f'$paper isa scilit-paper, has id "{paper_id}"; '
        f'(alh-artifact: $artifact, referent: $paper) isa alh-representation; '
        f'$section isa scilit-section; '
        f'(whole: $artifact, part: $section) isa alh-fragmentation; '
        f'$section has id $sid; '
        f'$section has content $content; '
        f'fetch {{ "section_id": $sid, "content": $content }};'
    )

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(query).resolve())

    if not results:
        print(json.dumps({
            "success": False,
            "error": f"No scilit-section fragments found for paper {paper_id}",
            "paper_id": paper_id,
        }))
        sys.exit(1)

    section_count = len(results)
    print(f"Found {section_count} sections, embedding...", file=sys.stderr)

    texts = [r["content"] for r in results]
    section_ids = [r["section_id"] for r in results]

    all_vectors = []
    for i in range(0, len(texts), VOYAGE_BATCH_SIZE):
        batch_end = min(i + VOYAGE_BATCH_SIZE, len(texts))
        print(f"  Embedding {i + 1}-{batch_end} / {len(texts)}...", file=sys.stderr)
        batch_vectors = embed_texts(texts[i:batch_end], input_type="document")
        all_vectors.extend(batch_vectors)

    qdrant = get_qdrant_client()

    # Ensure collection exists
    existing_collections = [c.name for c in qdrant.get_collections().collections]
    if collection_name not in existing_collections:
        print(f"Creating Qdrant collection '{collection_name}'...", file=sys.stderr)
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=VECTOR_DIM_SECTIONS,
                distance=qdrant_models.Distance.COSINE,
            ),
        )

    # Upsert points
    points = []
    for section_id, vector, content in zip(section_ids, all_vectors, texts):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, section_id))
        points.append(qdrant_models.PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "section_id": section_id,
                "paper_id": paper_id,
                "mondo_id": mondo_id,
                "content_preview": content[:200] if content else "",
            },
        ))

    qdrant.upsert(collection_name=collection_name, points=points)
    print(f"Upserted {len(points)} section vectors into '{collection_name}'", file=sys.stderr)

    print(json.dumps({
        "success": True,
        "paper_id": paper_id,
        "collection": collection_name,
        "mondo_id": mondo_id,
        "section_count": section_count,
        "embedded_count": len(points),
    }, indent=2))


def cmd_search_sections(args):
    """Semantic search over scilit-section fragments in the apt-sections Qdrant collection."""
    try:
        from skillful_alhazen.utils.embeddings import embed_texts
        from skillful_alhazen.utils.vector_store import get_qdrant_client
        from qdrant_client import models as qdrant_models
    except ImportError as e:
        print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
        sys.exit(1)

    if not VOYAGE_API_KEY:
        print(json.dumps({"success": False, "error": "VOYAGE_API_KEY not set"}))
        sys.exit(1)

    query_text = args.query
    collection_name = getattr(args, "collection", APT_SECTIONS_COLLECTION)
    mondo_id = args.mondo_id or ""
    top_k = args.top_k

    print(f"Embedding query: {query_text}", file=sys.stderr)
    query_vector = embed_texts([query_text], input_type="query")[0]

    qdrant = get_qdrant_client()

    # Build optional mondo_id filter
    search_filter = None
    if mondo_id:
        search_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="mondo_id",
                    match=qdrant_models.MatchValue(value=mondo_id),
                )
            ]
        )

    hits = qdrant.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=top_k,
        query_filter=search_filter,
        with_payload=True,
    )

    results = []
    for hit in hits:
        payload = hit.payload or {}
        results.append({
            "section_id": payload.get("section_id", ""),
            "paper_id": payload.get("paper_id", ""),
            "mondo_id": payload.get("mondo_id", ""),
            "score": hit.score,
            "content_preview": payload.get("content_preview", ""),
        })

    print(json.dumps({
        "success": True,
        "query": query_text,
        "collection": collection_name,
        "mondo_id": mondo_id,
        "results": results,
    }, indent=2))


# =============================================================================
# INVESTIGATION COMMANDS
# =============================================================================
# A scilit-investigation is a note ABOUT a scilit-corpus (via alh-aboutness):
# inherited `name`=title, `content`=purpose, `created-at`=start date, plus a
# scilit-investigation-status lifecycle attribute. Each phase is a single
# scilit-investigation-phase note threaded under it (alh-note-threading), tagged
# with a scilit-phase attribute. The analysis phase threads existing
# scilit-faceting-note pipelines under itself. Mirrors tech-recon, but explicit.

INVESTIGATION_PHASES = ["discovery", "ingest", "sensemaking", "analysis", "report"]


def _set_investigation_status(tx, inv_id, status):
    """Replace an investigation's status attribute (delete-has + insert)."""
    existing = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}", '
        f'has scilit-investigation-status $s; fetch {{ "s": $s }};'
    ).resolve())
    if existing:
        tx.query(
            f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}", '
            f'has scilit-investigation-status $old; delete has $old of $inv;'
        ).resolve()
    tx.query(
        f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
        f'insert $inv has scilit-investigation-status "{escape_string(status)}";'
    ).resolve()


def _ensure_phase_note(tx, inv_id, phase, content=None, iteration=1):
    """Find-or-create the stage note for (investigation, phase, iteration).

    New wiring: investigation -> scilit-iteration (by index) -> scilit-investigation-phase
    via scilit-investigation-iteration and scilit-iteration-stage respectively.
    The iteration is resolved-or-created by scilit-iteration-index.

    Returns (phase_id, created)."""
    # Step 1: resolve-or-create the scilit-iteration for this investigation + index
    its = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
        f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration; '
        f'$it isa scilit-iteration, has scilit-iteration-index {int(iteration)}; '
        f'fetch {{ "id": $it.id }};'
    ).resolve())
    if its:
        it_id = its[0]["id"]
    else:
        it_id = generate_id("scit")
        ts = get_timestamp()
        tx.query(
            f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
            f'insert $it isa scilit-iteration, has id "{it_id}", '
            f'has name "Iteration {int(iteration)}", '
            f'has scilit-iteration-index {int(iteration)}, has created-at {ts}; '
            f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration;'
        ).resolve()

    # Step 2: find-or-create the stage note under this iteration
    existing = list(tx.query(
        f'match $it isa scilit-iteration, has id "{escape_string(it_id)}"; '
        f'(iteration: $it, stage: $ph) isa scilit-iteration-stage; '
        f'$ph isa scilit-investigation-phase, has scilit-phase "{escape_string(phase)}"; '
        f'fetch {{ "id": $ph.id }};'
    ).resolve())
    if existing:
        return existing[0]["id"], False

    ph_id = generate_id("scphase")
    ts = get_timestamp()
    content_clause = f', has content "{escape_string(content)}"' if content else ""
    tx.query(
        f'match $it isa scilit-iteration, has id "{escape_string(it_id)}"; '
        f'insert $ph isa scilit-investigation-phase, has id "{ph_id}", '
        f'has name "{escape_string(phase.capitalize())} phase"{content_clause}, '
        f'has scilit-phase "{escape_string(phase)}", has created-at {ts}; '
        f'(iteration: $it, stage: $ph) isa scilit-iteration-stage;'
    ).resolve()
    return ph_id, True


def _ensure_investigation_collection(driver, inv_id, inv_name=None):
    """Resolve (or lazily create) the dedicated scilit-corpus that collects an
    investigation's papers. For a corpus investigation this is the source corpus
    (already aboutness-linked); for a deep-dive it is a dedicated traced corpus,
    created on first use. Returns the collection id. Idempotent."""
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        # the PRIMARY analyzed corpus is linked via scilit-investigation-scope specifically
        # (NOT generic aboutness) so auxiliary corpora attached via scilit-investigation-aux-corpus
        # never get mistaken for the scope corpus.
        existing = list(tx.query(
            f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
            f'(investigation: $inv, corpus: $c) isa scilit-investigation-scope; '
            f'fetch {{ "id": $c.id }};'
        ).resolve())
    if existing:
        return existing[0]["id"]

    if inv_name is None:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            inv = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
                f'fetch {{ "name": $inv.name }};'
            ).resolve())
        inv_name = (inv[0].get("name") if inv else None) or inv_id

    coll_id = generate_id("collection")
    ts = get_timestamp()
    name = f"{inv_name} - papers"
    desc = f"Papers traced by investigation {inv_id}"
    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
        tx.query(
            f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
            f'insert $c isa scilit-corpus, has id "{coll_id}", '
            f'has name "{escape_string(name)}", '
            f'has description "{escape_string(desc)}", '
            f'has alh-is-extensional false, '
            f'has created-at {ts}; '
            f'(investigation: $inv, corpus: $c) isa scilit-investigation-scope;'
        ).resolve()
        tx.commit()
    return coll_id


def cmd_create_investigation(args):
    """Create a named investigation note. Typed `corpus` (about a scilit-corpus) or
    `deep-dive` (about a single focal scilit-paper).

    Seeds iteration 1 (scilit-iteration index 1 + scilit-investigation-iteration link)
    in the same transaction so every investigation starts with a first-class iteration.
    """
    inv_type = getattr(args, "type", None) or "corpus"
    if inv_type not in ("corpus", "deep-dive"):
        print(json.dumps({"success": False,
                          "error": "Invalid --type. Use 'corpus' or 'deep-dive'"}))
        sys.exit(1)
    inv_id = generate_id("scinv")
    it1_id = generate_id("scit")
    ts = get_timestamp()
    status = args.status or "scoping"

    if inv_type == "deep-dive":
        if not getattr(args, "paper", None):
            print(json.dumps({"success": False,
                              "error": "--paper (DOI or scilit-paper id) is required for a deep-dive"}))
            sys.exit(1)
        with get_driver() as driver:
            focal_id = _resolve_paper_arg(driver, args.paper)
            if not focal_id:
                print(json.dumps({"success": False,
                                  "error": f"Could not resolve focal paper: {args.paper}"}))
                sys.exit(1)
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(
                    f'match $p isa scilit-paper, has id "{escape_string(focal_id)}"; '
                    f'insert $inv isa scilit-investigation, has id "{inv_id}", '
                    f'has name "{escape_string(args.name)}", '
                    f'has content "{escape_string(args.purpose)}", '
                    f'has scilit-investigation-status "{escape_string(status)}", '
                    f'has scilit-investigation-type "deep-dive", '
                    f'has created-at {ts}; '
                    f'(investigation: $inv, focal-paper: $p) isa scilit-investigation-focus; '
                    f'$it isa scilit-iteration, has id "{it1_id}", '
                    f'has name "Iteration 1", '
                    f'has scilit-iteration-index 1, has created-at {ts}; '
                    f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration;'
                ).resolve()
                tx.commit()
            coll_id = _ensure_investigation_collection(driver, inv_id, args.name)
            add_to_collection(driver, focal_id, coll_id)
        print(json.dumps({
            "success": True,
            "id": inv_id,
            "name": args.name,
            "type": "deep-dive",
            "focal_paper": focal_id,
            "collection": coll_id,
            "status": status,
        }, indent=2))
        return

    # corpus (default)
    if not getattr(args, "collection", None):
        print(json.dumps({"success": False,
                          "error": "--collection (scilit-corpus id) is required for a corpus investigation"}))
        sys.exit(1)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            corpus = list(tx.query(
                f'match $c isa scilit-corpus, has id "{escape_string(args.collection)}"; '
                f'fetch {{ "id": $c.id }};'
            ).resolve())
            if not corpus:
                print(json.dumps({"success": False, "error": "Corpus not found"}))
                sys.exit(1)
            tx.query(
                f'match $c isa scilit-corpus, has id "{escape_string(args.collection)}"; '
                f'insert $inv isa scilit-investigation, has id "{inv_id}", '
                f'has name "{escape_string(args.name)}", '
                f'has content "{escape_string(args.purpose)}", '
                f'has scilit-investigation-status "{escape_string(status)}", '
                f'has scilit-investigation-type "corpus", '
                f'has created-at {ts}; '
                f'(investigation: $inv, corpus: $c) isa scilit-investigation-scope; '
                f'$it isa scilit-iteration, has id "{it1_id}", '
                f'has name "Iteration 1", '
                f'has scilit-iteration-index 1, has created-at {ts}; '
                f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration;'
            ).resolve()
            tx.commit()
    print(json.dumps({
        "success": True,
        "id": inv_id,
        "name": args.name,
        "type": "corpus",
        "collection": args.collection,
        "status": status,
    }, indent=2))


def cmd_list_investigations(args):
    """List investigations, optionally scoped to one corpus, with status + phase count."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            if args.collection:
                query = (
                    f'match $c isa scilit-corpus, has id "{escape_string(args.collection)}"; '
                    f'(note: $inv, subject: $c) isa alh-aboutness; '
                    f'$inv isa scilit-investigation; '
                    f'fetch {{ "id": $inv.id, "name": $inv.name, "purpose": $inv.content, '
                    f'"status": $inv.scilit-investigation-status, '
                    f'"type": $inv.scilit-investigation-type, "created-at": $inv.created-at }};'
                )
            else:
                query = (
                    'match $inv isa scilit-investigation; '
                    'fetch { "id": $inv.id, "name": $inv.name, "purpose": $inv.content, '
                    '"status": $inv.scilit-investigation-status, '
                    '"type": $inv.scilit-investigation-type, "created-at": $inv.created-at };'
                )
            invs = [{k: v for k, v in r.items() if v is not None}
                    for r in tx.query(query).resolve()]

            for inv in invs:
                corpus = list(tx.query(
                    f'match $inv isa scilit-investigation, has id "{escape_string(inv["id"])}"; '
                    f'(note: $inv, subject: $c) isa alh-aboutness; $c isa scilit-corpus; '
                    f'fetch {{ "id": $c.id, "name": $c.name }};'
                ).resolve())
                inv["corpus"] = ({k: v for k, v in corpus[0].items() if v is not None}
                                 if corpus else None)
                if inv.get("type") == "deep-dive":
                    focal = list(tx.query(
                        f'match $inv isa scilit-investigation, has id "{escape_string(inv["id"])}"; '
                        f'(note: $inv, subject: $p) isa alh-aboutness; $p isa scilit-paper; '
                        f'fetch {{ "id": $p.id, "name": $p.name }};'
                    ).resolve())
                    inv["focal_paper"] = ({k: v for k, v in focal[0].items() if v is not None}
                                          if focal else None)
                iters = list(tx.query(
                    f'match $inv isa scilit-investigation, has id "{escape_string(inv["id"])}"; '
                    f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration; '
                    f'select $it;'
                ).resolve())
                inv["iteration_count"] = len(iters)

    print(json.dumps({"success": True, "investigations": invs, "count": len(invs)}, indent=2))


def _load_investigation(tx, inv_id):
    """Load a unified investigation dict: metadata, grounding, corpus/papers, staged
    structure (discovery..report, iteration-aware), per-paper sensemaking bundles,
    synthesized-claims with evidence warrants, and citation-impacts. None if not found."""
    esc = escape_string(inv_id)
    result = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{esc}"; '
        f'fetch {{ "id": $inv.id, "name": $inv.name, "purpose": $inv.content, '
        f'"status": $inv.scilit-investigation-status, '
        f'"question": $inv.scilit-investigation-question, '
        f'"type": $inv.scilit-investigation-type, '
        f'"created-at": $inv.created-at }};'
    ).resolve())
    if not result:
        return None
    investigation = {k: v for k, v in result[0].items() if v is not None}

    pol = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{esc}"; '
        f'(investigation: $inv, policy: $pp) isa scilit-investigation-grounding; '
        f'fetch {{ "content": $pp.content }};'
    ).resolve())
    if pol and pol[0].get("content"):
        try:
            investigation["grounding_policy"] = json.loads(pol[0]["content"])
        except Exception:
            investigation["grounding_policy"] = None

    corpus = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{esc}"; '
        f'(investigation: $inv, corpus: $c) isa scilit-investigation-scope; '
        f'fetch {{ "id": $c.id, "name": $c.name }};'
    ).resolve())
    investigation["corpus"] = ({k: v for k, v in corpus[0].items() if v is not None}
                               if corpus else None)
    focal = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{esc}"; '
        f'(investigation: $inv, focal-paper: $p) isa scilit-investigation-focus; '
        f'fetch {{ "id": $p.id, "name": $p.name, "doi": $p.scilit-doi, '
        f'"year": $p.scilit-publication-year }};'
    ).resolve())
    investigation["focal_paper"] = ({k: v for k, v in focal[0].items() if v is not None}
                                    if focal else None)

    coll = investigation.get("corpus")
    if coll:
        paper_rows = list(tx.query(
            f'match $c isa scilit-corpus, has id "{escape_string(coll["id"])}"; '
            f'(collection: $c, member: $p) isa alh-collection-membership; $p isa scilit-paper; '
            f'fetch {{ "id": $p.id, "name": $p.name, "doi": $p.scilit-doi, '
            f'"year": $p.scilit-publication-year }};'
        ).resolve())
        papers = [{k: v for k, v in r.items() if v is not None} for r in paper_rows]
        papers.sort(key=lambda p: p.get("year") or 0, reverse=True)
        investigation["papers"] = papers
        investigation["collection"] = {"id": coll["id"], "name": coll.get("name"),
                                       "count": len(papers)}

    # Stage notes: traverse iteration->stage chain (replaces retired scilit-investigation-phasing).
    # Path: investigation -> scilit-investigation-iteration -> scilit-iteration (index) ->
    #       scilit-iteration-stage -> scilit-investigation-phase.
    # Each phase dict carries 'iteration' from scilit-iteration-index.
    phase_rows = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{esc}"; '
        f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration; '
        f'$it isa scilit-iteration, has scilit-iteration-index $idx; '
        f'(iteration: $it, stage: $ph) isa scilit-iteration-stage; '
        f'$ph isa scilit-investigation-phase, has scilit-phase $phase; '
        f'fetch {{ "id": $ph.id, "name": $ph.name, "content": $ph.content, '
        f'"phase": $phase, "idx": $idx, "created-at": $ph.created-at }};'
    ).resolve())
    phases = []
    for r in phase_rows:
        ph = {k: v for k, v in r.items() if v is not None and k != "idx"}
        ph["iteration"] = r.get("idx")
        phases.append(ph)
    for ph in phases:
        if ph.get("phase") == "analysis":
            fn = list(tx.query(
                f'match $ph isa scilit-investigation-phase, has id "{escape_string(ph["id"])}"; '
                f'(phase: $ph, faceting: $fn) isa scilit-phase-faceting; '
                f'fetch {{ "id": $fn.id, "name": $fn.name }};'
            ).resolve())
            ph["faceting_notes"] = [{k: v for k, v in f.items() if v is not None} for f in fn]
        if ph.get("phase") == "sensemaking":
            ph["bundles"] = _load_bundles(tx, ph["id"])
    order = {p: i for i, p in enumerate(INVESTIGATION_PHASES)}
    phases.sort(key=lambda p: (p.get("iteration") or 0, order.get(p.get("phase"), 99)))
    investigation["phases"] = phases

    investigation["synthesized_claims"] = _load_synthesized_claims(tx, inv_id)
    investigation["citation_impacts"] = _load_impacts(tx, inv_id)
    return investigation


def _load_bundles(tx, phase_id):
    """Per-paper sensemaking bundles under a sensemaking stage note: each with its paper
    and counts of observations / reported-claims / reported-gaps."""
    rows = list(tx.query(
        f'match $ph isa scilit-investigation-phase, has id "{escape_string(phase_id)}"; '
        f'(phase: $ph, sensemaking: $b) isa scilit-phase-sensemaking; '
        f'fetch {{ "id": $b.id, "name": $b.name }};'
    ).resolve())
    bundles = [{k: v for k, v in r.items() if v is not None} for r in rows]
    for b in bundles:
        be = escape_string(b["id"])
        paper = list(tx.query(
            f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
            f'(sensemaking: $b, paper: $p) isa scilit-sensemaking-paper; '
            f'fetch {{ "id": $p.id, "name": $p.name, "doi": $p.scilit-doi, '
            f'"year": $p.scilit-publication-year }};'
        ).resolve())
        b["paper"] = ({k: v for k, v in paper[0].items() if v is not None} if paper else None)
        b["observation_count"] = len(list(tx.query(
            f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
            f'(sensemaking: $b, observation: $o) isa scilit-sensemaking-observation; select $o;').resolve()))
        b["reported_claim_count"] = len(list(tx.query(
            f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
            f'(sensemaking: $b, reported-claim: $c) isa scilit-sensemaking-reported-claim; select $c;').resolve()))
        b["reported_gap_count"] = len(list(tx.query(
            f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
            f'(sensemaking: $b, reported-gap: $g) isa scilit-sensemaking-reported-gap; select $g;').resolve()))
    bundles.sort(key=lambda b: (b.get("paper") or {}).get("year") or 0, reverse=True)
    return bundles


def _load_bundle(tx, bundle_id):
    """Full detail of one per-paper sensemaking bundle: paper, observations (plain
    sensemaking notes — no kefed_frame), reported-claims (with hinges), reported-gaps.
    KEfED experiments are read separately via _load_experiments/_load_instances."""
    be = escape_string(bundle_id)
    head = list(tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
        f'fetch {{ "id": $b.id, "name": $b.name }};').resolve())
    if not head:
        return None
    bundle = {k: v for k, v in head[0].items() if v is not None}
    paper = list(tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
        f'(sensemaking: $b, paper: $p) isa scilit-sensemaking-paper; '
        f'fetch {{ "id": $p.id, "name": $p.name, "doi": $p.scilit-doi, "year": $p.scilit-publication-year }};').resolve())
    bundle["paper"] = ({k: v for k, v in paper[0].items() if v is not None} if paper else None)

    # Observations are plain sensemaking notes: no kefed_frame (kefed-observed-via is retired).
    # KEfED models are now authored separately and attached via scilit-sensemaking-experiment.
    obs_rows = list(tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
        f'(sensemaking: $b, observation: $o) isa scilit-sensemaking-observation; '
        f'fetch {{ "id": $o.id, "name": $o.name, "content": $o.content, '
        f'"knowledge_level": $o.scilit-knowledge-level, "bio_scale": $o.scilit-bio-scale }};').resolve())
    bundle["observations"] = [{k: v for k, v in r.items() if v is not None} for r in obs_rows]

    rc_rows = list(tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
        f'(sensemaking: $b, reported-claim: $c) isa scilit-sensemaking-reported-claim; '
        f'fetch {{ "id": $c.id, "type": $c.scilit-claim-type, "statement": $c.scilit-claim-statement }};').resolve())
    reported_claims = [{k: v for k, v in r.items() if v is not None} for r in rc_rows]
    for c in reported_claims:
        # scilit-reported-claim retired -> scilit-claim (Task 3)
        hinges = list(tx.query(
            f'match $c isa scilit-claim, has id "{escape_string(c["id"])}"; '
            f'(hinging-claim: $c, hinged-to: $t) isa scilit-hinge; $t isa scilit-paper; '
            f'fetch {{ "id": $t.id, "name": $t.name, "doi": $t.scilit-doi }};').resolve())
        c["cites"] = [{k: v for k, v in h.items() if v is not None} for h in hinges]
    bundle["reported_claims"] = reported_claims

    rg_rows = list(tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
        f'(sensemaking: $b, reported-gap: $g) isa scilit-sensemaking-reported-gap; '
        f'fetch {{ "id": $g.id, "name": $g.name, "content": $g.content, '
        f'"goal": $g.scilit-knowledge-goal }};').resolve())
    bundle["reported_gaps"] = [{k: v for k, v in r.items() if v is not None} for r in rg_rows]

    mech_rows = list(tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{be}"; '
        f'(sensemaking: $b, mechanism: $ml) isa scilit-sensemaking-mechanism; '
        f'$ml links (mech-source: $s, mech-target: $t), has scilit-mech-type $mt; '
        f'$s has name $sn; $t has name $tn; '
        f'fetch {{ "source": $sn, "target": $tn, "type": $mt }};').resolve())
    bundle["mechanisms"] = [{k: v for k, v in r.items() if v is not None} for r in mech_rows]
    bundle["experiments"] = _load_experiments(tx, bundle_id)
    bundle["instances"] = _load_instances(tx, bundle_id)
    return bundle


def _tlabel(concept):
    """Robustly get a concept's type-label name as a plain string (driver-version tolerant)."""
    lbl = concept.get_type().get_label()
    return getattr(lbl, "name", None) or str(lbl)


def _load_experiments(tx, bundle_id):
    """Inline experiment (kefed-model) protocol graphs grouped under a bundle via
    scilit-sensemaking-experiment. Template-based instances are returned by _load_instances."""
    rows = list(tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{escape_string(bundle_id)}"; '
        f'(sensemaking: $b, experiment: $m) isa scilit-sensemaking-experiment; $m isa kefed-model; '
        f'fetch {{ "id": $m.id, "name": $m.name }};').resolve())
    exps = [{k: v for k, v in r.items() if v is not None} for r in rows]
    for e in exps:
        e["experiment"] = _load_experiment(tx, e["id"])
    return exps


def _load_instances(tx, bundle_id):
    """Template instances (kefed-instance) grouped under a bundle via
    scilit-sensemaking-experiment: each execution with its data spreadsheet."""
    rows = list(tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{escape_string(bundle_id)}"; '
        f'(sensemaking: $b, experiment: $i) isa scilit-sensemaking-experiment; $i isa kefed-instance; '
        f'fetch {{ "id": $i.id }};').resolve())
    insts = []
    seen_tpl = {}
    for r in rows:
        inst = _load_instance(tx, r["id"])
        if inst is None:
            continue
        tid = (inst.get("template") or {}).get("id")
        if tid and tid not in seen_tpl:
            seen_tpl[tid] = _load_template(tx, tid)
        inst["template_detail"] = seen_tpl.get(tid)
        insts.append(inst)
    return insts


def _bundle_model_ids(tx, bundle_id):
    """Every KEfED bigraph model reachable under a sensemaking bundle: inline experiments
    (kefed-model attached via scilit-sensemaking-experiment) PLUS the templates behind template
    instances (kefed-instance -> kefed-instance-of:model). De-duplicated, order-stable."""
    esc = escape_string(bundle_id)
    ids = []
    for r in tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{esc}"; '
        f'(sensemaking: $b, experiment: $m) isa scilit-sensemaking-experiment; $m isa kefed-model; '
        f'fetch {{ "id": $m.id }};').resolve():
        ids.append(r["id"])
    for r in tx.query(
        f'match $b isa scilit-paper-sensemaking, has id "{esc}"; '
        f'(sensemaking: $b, experiment: $i) isa scilit-sensemaking-experiment; $i isa kefed-instance; '
        f'(instance: $i, model: $t) isa kefed-instance-of; '
        f'fetch {{ "id": $t.id }};').resolve():
        ids.append(r["id"])
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i); out.append(i)
    return out


def _scale_of(tx, var_id):
    rows = list(tx.query(
        f'match $v isa ooevv-variable, has id "{escape_string(var_id)}"; '
        f'(scaled-variable: $v, scale: $s) isa ooevv-has-scale; '
        f'fetch {{ "id": $s.id, "unit": $s.ooevv-unit }};').resolve())
    if not rows:
        return None
    s = {k: v for k, v in rows[0].items() if v is not None}
    # scale subtype label via concept api
    sub = list(tx.query(f'match $s isa ooevv-scale, has id "{escape_string(s["id"])}"; select $s;').resolve())
    if sub:
        try:
            s["type"] = _tlabel(sub[0].get("s")).replace("ooevv-", "").replace("-scale", "")
        except Exception:
            pass
    vals = [r.get("v") for r in tx.query(
        f'match $s isa ooevv-scale, has id "{escape_string(s["id"])}"; '
        f'{{ $s has ooevv-allowed-value $v; }} or {{ $s has ooevv-named-rank $v; }}; '
        f'fetch {{ "v": $v }};').resolve()]
    if vals:
        s["values"] = [v for v in vals if v is not None]
    return s


def _var_brief(tx, var_id):
    """Brief dict for one ooevv-variable: id, name, role, definition, quality, scale, target.
    Dropped: 'slot' key (ooevv-param-slot / kefed-slot-role / kefed-slot-kind retired in Task 5)."""
    rows = list(tx.query(
        f'match $v isa ooevv-variable, has id "{escape_string(var_id)}", has name $n; '
        f'fetch {{ "name": $n, "role": $v.ooevv-variable-role, '
        f'"definition": $v.ooevv-definition, "long_form": $v.ooevv-long-form }};').resolve())
    v = {"id": var_id, **({k: x for k, x in rows[0].items() if x is not None} if rows else {})}
    ql = list(tx.query(
        f'match $v isa ooevv-variable, has id "{escape_string(var_id)}"; '
        f'(measured-variable: $v, quality: $q) isa ooevv-measures; '
        f'fetch {{ "quality": $q.name, "definition": $q.ooevv-definition, "long_form": $q.ooevv-long-form, '
        f'"quality_id": $q.id, "curie": $q.scilit-curie, "grounding_state": $q.scilit-grounding-state }};').resolve())
    if ql:
        v["quality"] = {k: x for k, x in ql[0].items() if x is not None}
    sc = _scale_of(tx, var_id)
    if sc:
        v["scale"] = sc
    # ooevv-parameter-target:target-entity is now played by both ooevv-material-entity
    # (owns ooevv-definition) and kefed-model-node (does not). Query each separately so
    # TypeDB 3.x type-checking doesn't reject the fetch for kefed-model-node targets.
    tgt = list(tx.query(
        f'match $v isa ooevv-variable, has id "{escape_string(var_id)}"; '
        f'(targeting-parameter: $v, target-entity: $e) isa ooevv-parameter-target; '
        f'$e isa ooevv-material-entity; '
        f'fetch {{ "id": $e.id, "name": $e.name, "definition": $e.ooevv-definition, "long_form": $e.ooevv-long-form }};').resolve())
    if not tgt:
        tgt = list(tx.query(
            f'match $v isa ooevv-variable, has id "{escape_string(var_id)}"; '
            f'(targeting-parameter: $v, target-entity: $e) isa ooevv-parameter-target; '
            f'$e isa kefed-model-node; '
            f'fetch {{ "id": $e.id, "name": $e.name }};').resolve())
    if tgt:
        v["target_entity"] = {k: x for k, x in tgt[0].items() if x is not None}
    return v


def _load_experiment(tx, exp_id):
    """Full protocol graph for one kefed-model: nodes (kefed-model-node) with their OOEVV type,
    input/output flow edges (ooevv-process-input/output node roles), and variables
    (parameters/measurements) via kefed-node-variable.
    2b.2 redesign: elements are kefed-model-node (not ooevv-process directly)."""
    esc = escape_string(exp_id)
    node_rows = list(tx.query(
        f'match $m isa kefed-model, has id "{esc}"; '
        f'(model: $m, element: $n) isa kefed-model-element; $n isa kefed-model-node; $n has name $nn; '
        f'fetch {{ "id": $n.id, "name": $nn }};').resolve())
    nodes = [{k: v for k, v in r.items() if v is not None} for r in node_rows]
    for p in nodes:
        ne = escape_string(p["id"])
        try:
            tlist = list(tx.query(
                f'match $n isa kefed-model-node, has id "{ne}"; '
                f'(node: $n, node-type: $nt) isa kefed-node-type; select $nt;').resolve())
            p["type"] = _tlabel(tlist[0].get("nt")).replace("ooevv-", "") if tlist else None
        except Exception:
            p["type"] = None
        p["parent"] = None  # hierarchy lives at OOEVV def level (ooevv-process-decomposition)
        p["inputs"] = [r.get("src") for r in tx.query(
            f'match $n isa kefed-model-node, has id "{ne}"; '
            f'(input-node: $src, consuming-node: $n) isa ooevv-process-input; '
            f'fetch {{ "src": $src.id }};').resolve()]
        p["outputs"] = [r.get("tgt") for r in tx.query(
            f'match $n isa kefed-model-node, has id "{ne}"; '
            f'(producing-node: $n, output-node: $tgt) isa ooevv-process-output; '
            f'fetch {{ "tgt": $tgt.id }};').resolve()]
        pbind = list(tx.query(
            f'match $n isa kefed-model-node, has id "{ne}"; '
            f'(node: $n, variable: $v) isa kefed-node-variable; '
            f'$v isa ooevv-variable, has ooevv-variable-role "parameter"; '
            f'fetch {{ "id": $v.id }};').resolve())
        p["parameters"] = [_var_brief(tx, r["id"]) for r in pbind]
        meas = list(tx.query(
            f'match $n isa kefed-model-node, has id "{ne}"; '
            f'(node: $n, variable: $v) isa kefed-node-variable; '
            f'$v isa ooevv-variable, has ooevv-variable-role "measurement"; '
            f'fetch {{ "id": $v.id }};').resolve())
        p["measurements"] = [_var_brief(tx, r["id"]) for r in meas]
    return {"id": exp_id, "processes": nodes}


def _model_graph(tx, model_id):
    """Load a KEfED model as an in-memory bigraph for signature/lint/export.

    Returns a dict with:
      nodes       : [node_id, ...] (all kefed-model-node ids in the model)
      klass       : {node_id: 'entity'|'process'|None}   (bigraph node class)
      is_dt       : {node_id: bool}                        (True iff data-transformation)
      local       : {node_id: [{id,name,role}, ...]}       (parameter/constant vars on the node)
      measures    : {node_id: [{id,name}, ...]}            (measurement vars on the node)
      feeders     : {node_id: {feeder_node_id, ...}}       (direct upstream nodes)
      edges       : [{"kind":"input"|"output","src":..,"dst":..}, ...]  (as curated)
      dt_drop     : {dt_node_id: {var_id, ...}}            (in-params consumed at this DT)
      dt_add      : {dt_node_id: {var_id, ...}}            (out-params introduced at this DT)
      dt_has_map  : {dt_node_id: bool}                     (any ooevv-param-mapping declared)
      var_info    : {var_id: {"name":..,"role":..}}        (every param/constant var in the model)
    """
    esc = escape_string(model_id)
    node_ids = [r["id"] for r in tx.query(
        f'match $m isa kefed-model, has id "{esc}"; '
        f'(model: $m, element: $n) isa kefed-model-element; $n isa kefed-model-node; '
        f'fetch {{ "id": $n.id }};').resolve()]
    node_set = set(node_ids)
    klass, is_dt, def_of = {}, {}, {}
    local, measures = {nid: [] for nid in node_ids}, {nid: [] for nid in node_ids}
    var_info = {}
    for nid in node_ids:
        did, lbl = _node_def(tx, nid)
        def_of[nid] = did
        klass[nid] = _node_class(lbl)
        is_dt[nid] = (lbl == "ooevv-data-transformation")
        ne = escape_string(nid)
        for r in tx.query(
            f'match $n isa kefed-model-node, has id "{ne}"; '
            f'(node: $n, variable: $v) isa kefed-node-variable; '
            f'$v isa ooevv-variable, has ooevv-variable-role $role, has name $vn; '
            f'fetch {{ "id": $v.id, "role": $role, "name": $vn }};').resolve():
            entry = {"id": r["id"], "name": r.get("name", ""), "role": r["role"]}
            if r["role"] in ("parameter", "constant"):
                local[nid].append(entry)
                var_info[r["id"]] = {"name": entry["name"], "role": entry["role"]}
            elif r["role"] == "measurement":
                measures[nid].append({"id": r["id"], "name": entry["name"]})

    # flow edges -> feeders (direct upstream). input: entity(input-node)->process(consuming-node);
    # output: process(producing-node)->entity(output-node).
    feeders = {nid: set() for nid in node_ids}
    edges = []
    for nid in node_ids:
        ne = escape_string(nid)
        for r in tx.query(
            f'match $n isa kefed-model-node, has id "{ne}"; '
            f'(input-node: $src, consuming-node: $n) isa ooevv-process-input; '
            f'fetch {{ "src": $src.id }};').resolve():
            if r["src"] in node_set:
                feeders[nid].add(r["src"]); edges.append({"kind": "input", "src": r["src"], "dst": nid})
        for r in tx.query(
            f'match $n isa kefed-model-node, has id "{ne}"; '
            f'(producing-node: $src, output-node: $n) isa ooevv-process-output; '
            f'fetch {{ "src": $src.id }};').resolve():
            if r["src"] in node_set:
                feeders[nid].add(r["src"]); edges.append({"kind": "output", "src": r["src"], "dst": nid})

    # param-mappings per DT node (transformation role played by the DT DEFINITION). Restrict to
    # this model's variables so a def shared across models resolves each model's mapping locally.
    model_var_ids = set(var_info)
    dt_drop, dt_add, dt_has_map = {}, {}, {}
    for nid in node_ids:
        if not is_dt[nid]:
            continue
        de = escape_string(def_of[nid])
        ins = {r["id"] for r in tx.query(
            f'match $t isa ooevv-data-transformation, has id "{de}"; '
            f'(transformation: $t, in-parameter: $v) isa ooevv-param-mapping; '
            f'fetch {{ "id": $v.id }};').resolve()}
        outs = {r["id"] for r in tx.query(
            f'match $t isa ooevv-data-transformation, has id "{de}"; '
            f'(transformation: $t, out-parameter: $v) isa ooevv-param-mapping; '
            f'fetch {{ "id": $v.id }};').resolve()}
        dt_has_map[nid] = bool(ins or outs)
        dt_drop[nid] = ins & model_var_ids     # every mapped in-param leaves the index here
        dt_add[nid] = outs & model_var_ids      # every mapped out-param enters the index here

    # subject (source) node of the model, if declared
    subj = list(tx.query(
        f'match $m isa kefed-model, has id "{esc}"; '
        f'(model: $m, subject-node: $n) isa ooevv-subject; fetch {{ "id": $n.id }};').resolve())
    subject = subj[0]["id"] if subj else None

    return {"model_id": model_id, "nodes": node_ids, "klass": klass, "is_dt": is_dt, "local": local,
            "measures": measures, "feeders": feeders, "edges": edges, "dt_drop": dt_drop,
            "dt_add": dt_add, "dt_has_map": dt_has_map, "var_info": var_info, "subject": subject}


def _carried_index(g, node_id, _cache=None, _path=None):
    """Set of parameter/constant var-ids that index the material/data AT node_id.

    Forward propagation over the bigraph: a node inherits the index sets of its feeders, then a
    DATA-TRANSFORMATION rewrites that set by its declared param-mapping (drop every mapped
    in-parameter, add every mapped out-parameter — this is how a correlation CONSUMES the
    per-sample index instead of carrying it forward), and finally the node's own local
    parameters/constants are unioned in. Non-transformation nodes just pass the union through.
    Unmapped incoming params on a data-transformation default to passthrough (kept) — the linter
    flags a data-transformation that leaves incoming index params unmapped.
    """
    _cache = {} if _cache is None else _cache
    _path = set() if _path is None else _path
    if node_id in _cache:
        return _cache[node_id]
    if node_id in _path:            # cycle guard — acyclicity is a separate lint check
        return set()
    inc = set()
    for f in g["feeders"].get(node_id, ()):  # DFS feeders
        inc |= _carried_index(g, f, _cache, _path | {node_id})
    if g["is_dt"].get(node_id):
        inc = (inc - g["dt_drop"].get(node_id, set())) | g["dt_add"].get(node_id, set())
    out = inc | {v["id"] for v in g["local"].get(node_id, [])}
    _cache[node_id] = out
    return out


def _upstream_closure(g, node_id):
    """All nodes reachable upstream from node_id via feeder edges (excludes node_id itself only if
    it has no self-loop)."""
    seen, queue = set(), [node_id]
    while queue:
        n = queue.pop()
        for f in g["feeders"].get(n, ()):
            if f not in seen:
                seen.add(f); queue.append(f)
    return seen


def _data_signature(tx, model_id):
    """Compute the data signature (index set) for every measurement in a KEfED model.

    The index set of a measurement is the set of parameter/constant variables that index its
    readout, computed by FORWARD propagation of index sets through the bigraph (see
    _carried_index) so that a data-transformation's declared ooevv-param-mapping correctly
    consumes/introduces index parameters. This replaces the old naive "union of everything
    upstream", which wrongly kept parameters that a computation (e.g. a correlation, a
    mean-over-replicates) actually destroys.

    Returns:
        dict: {measurement_var_id: {"name": <name>,
                                    "index": [{"id","name","role"}, ...],
                                    "consumed": [{"id","name","role"}, ...]}}
        where "consumed" lists parameters removed from the index by a data-transformation
        upstream of the measurement (index provenance, for legibility).
    """
    g = _model_graph(tx, model_id)
    vinfo = g["var_info"]

    def _render(vid):
        info = vinfo.get(vid, {})
        return {"id": vid, "name": info.get("name", ""), "role": info.get("role", "")}

    cache = {}
    result = {}
    for nid in g["nodes"]:
        for m in g["measures"].get(nid, []):
            idx = _carried_index(g, nid, cache)
            consumed = set()
            for up in _upstream_closure(g, nid) | {nid}:
                if g["is_dt"].get(up):
                    consumed |= g["dt_drop"].get(up, set())
            result[m["id"]] = {
                "name": m.get("name", ""),
                "index": [_render(v) for v in sorted(idx)],
                "consumed": [_render(v) for v in sorted(consumed)],
            }
    return result


def cmd_show_data_signature(args):
    """Show the data signature (index sets) for each measurement variable in a KEfED model.
    Prints the signature as a JSON dict: {measurement_var_id: {name, index: [{id, name, role}]}}."""
    model_id = args.model
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            sig = _data_signature(tx, model_id)
    print(json.dumps(sig, indent=2))


def _to_hgraph(g):
    """Serialize a KEfED bigraph (a _model_graph dict) into a Bolinas-style rooted hypergraph term:
    a PENMAN/AMR-like bracketed form `(node/label :edge child ...)` rooted at the subject, with
    directed :input / :output hyperedges and reentrancy (a node mentioned again is emitted by id
    alone). Node concept labels are the bigraph class (entity|process) refined by OOEVV type. This
    is the export path for a future graph-grammar (SHRG) DESIGN-PATTERN validation layer — Bolinas
    itself is Python 2 and out of scope now, so this emits the graph; it does not yet parse it.
    """
    children = {n: [] for n in g["nodes"]}
    for e in g["edges"]:
        children.setdefault(e["src"], []).append((e["kind"], e["dst"]))
    root = g.get("subject") or (g["nodes"][0] if g["nodes"] else None)
    if root is None:
        return "()"
    seen = set()

    def _nid(n):
        return n.replace("knode-", "n_")

    def emit(n):
        if n in seen:
            return _nid(n)                       # reentrant reference (shared node)
        seen.add(n)
        lbl = g["klass"].get(n) or "node"
        parts = [f"{_nid(n)}/{lbl}"]
        for kind, dst in children.get(n, []):
            parts.append(f":{kind} {emit(dst)}")
        return "(" + " ".join(parts) + ")"

    term = emit(root)
    extra = [emit(n) for n in g["nodes"] if n not in seen]  # unreachable-from-root fragments
    return term if not extra else term + " " + " ".join(extra)


def cmd_show_experiment(args):
    """Show one experiment's full protocol graph (processes, hierarchy, parameters, measurements).
    --format hgraph emits the Bolinas-style hypergraph term instead (for the future SHRG layer)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            head = list(tx.query(f'match $m isa kefed-model, has id "{escape_string(args.id)}"; '
                                 f'fetch {{ "name": $m.name }};').resolve())
            if not head:
                print(json.dumps({"success": False, "error": "Experiment not found"})); sys.exit(1)
            if getattr(args, "format", "json") == "hgraph":
                g = _model_graph(tx, args.id)
                print(_to_hgraph(g))
                return
            exp = _load_experiment(tx, args.id)
            exp["name"] = head[0].get("name")
    print(json.dumps({"success": True, **exp}, indent=2))


def _load_template(tx, template_id):
    """Full reusable design: name and the protocol graph (processes + variable definitions)
    shared by every instance. Template is a kefed-model with kefed-model-state 'template'.
    Retired: kefed-template type, kefed-template-slot, kefed-slot-role/kind (Task 8, Jun 2026)."""
    esc = escape_string(template_id)
    head = list(tx.query(
        f'match $t isa kefed-model, has id "{esc}", has kefed-model-state "template"; '
        f'fetch {{ "id": $t.id, "name": $t.name, '
        f'"definition": $t.ooevv-definition, "long_form": $t.ooevv-long-form }};').resolve())
    if not head:
        return None
    tpl = {k: v for k, v in head[0].items() if v is not None}
    # variables via kefed-model-element (replaces retired kefed-element/kefed-template-slot)
    # variables via model -> kefed-model-element -> kefed-model-node -> kefed-node-variable -> variable
    # (replaces retired: model -> kefed-model-element -> ooevv-variable directly)
    var_rows = list(tx.query(
        f'match $t isa kefed-model, has id "{esc}"; '
        f'(model: $t, element: $n) isa kefed-model-element; $n isa kefed-model-node; '
        f'(node: $n, variable: $v) isa kefed-node-variable; '
        f'fetch {{ "id": $v.id }};').resolve())
    tpl["variables"] = [_var_brief(tx, r["id"]) for r in var_rows]
    tpl["graph"] = _load_experiment(tx, template_id)
    return tpl


def cmd_show_template(args):
    """Show one reusable KEfED template (design graph + slots)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            tpl = _load_template(tx, args.id)
    if tpl is None:
        print(json.dumps({"success": False, "error": "Template not found"})); sys.exit(1)
    print(json.dumps({"success": True, **tpl}, indent=2))


def _load_instance(tx, instance_id):
    """One paper's execution of a template: the template ref (via kefed-model role) and the
    data rows (cells: per-variable values) each linked to its provenance observation.
    Retired: ooevv-slot-binding, kefed-slot-role/kind, kefed-variable-role (Task 8, Jun 2026)."""
    esc = escape_string(instance_id)
    head = list(tx.query(f'match $i isa kefed-instance, has id "{esc}"; '
                         f'fetch {{ "id": $i.id, "name": $i.name }};').resolve())
    if not head:
        return None
    inst = {k: v for k, v in head[0].items() if v is not None}
    # template ref: kefed-instance-of role renamed template -> model (Task 8)
    tpl = list(tx.query(
        f'match $i isa kefed-instance, has id "{esc}"; '
        f'(instance: $i, model: $t) isa kefed-instance-of; '
        f'fetch {{ "id": $t.id, "name": $t.name }};').resolve())
    inst["template"] = ({k: v for k, v in tpl[0].items() if v is not None} if tpl else None)
    # data rows (kefed-instance-datum / kefed-cell / kefed-datum-observation unchanged)
    datum_rows = list(tx.query(
        f'match $i isa kefed-instance, has id "{esc}"; '
        f'(instance: $i, datum: $d) isa kefed-instance-datum; '
        f'fetch {{ "id": $d.id }};').resolve())
    data = []
    for dr in datum_rows:
        did = dr["id"]; de = escape_string(did)
        # cell variable role: kefed-variable-role -> ooevv-variable-role (Task 8)
        cells = list(tx.query(
            f'match $d isa kefed-row, has id "{de}"; '
            f'$c isa kefed-cell, links (datum: $d, cell-variable: $v), has kefed-cell-value $val; '
            f'$v has name $vn, has ooevv-variable-role $vr; '
            f'fetch {{ "variable": $v.id, "name": $vn, "role": $vr, "value": $val, '
            f'"number": $c.kefed-cell-number, "n": $c.kefed-cell-n, "error": $c.kefed-cell-error, '
            f'"error_type": $c.kefed-cell-error-type, "unit": $c.kefed-cell-unit }};').resolve())
        row = {"id": did, "cells": [{k: v for k, v in c.items() if v is not None} for c in cells]}
        obs = list(tx.query(
            f'match $d isa kefed-row, has id "{de}"; '
            f'(datum: $d, observation: $o) isa kefed-datum-observation; '
            f'fetch {{ "id": $o.id, "name": $o.name, "content": $o.content }};').resolve())
        if obs:
            row["observation"] = {k: v for k, v in obs[0].items() if v is not None}
        data.append(row)
    inst["data"] = data
    return inst


def cmd_show_instance(args):
    """Show one paper's template instance: filled slots + data spreadsheet."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            inst = _load_instance(tx, args.id)
    if inst is None:
        print(json.dumps({"success": False, "error": "Instance not found"})); sys.exit(1)
    print(json.dumps({"success": True, **inst}, indent=2))


def _load_synthesized_claims(tx, inv_id):
    """Synthesized-claims (cross-paper, analysis) with their evidence warrants
    (reasoned argument + confidence + grounding reported-claims)."""
    claim_rows = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
        f'(investigation: $inv, synthesized-claim: $cl) isa scilit-investigation-synthesized-claim; '
        f'fetch {{ "id": $cl.id, "type": $cl.scilit-claim-type, '
        f'"statement": $cl.scilit-claim-statement }};'
    ).resolve())
    claims = [{k: v for k, v in r.items() if v is not None} for r in claim_rows]
    for cl in claims:
        ev_rows = list(tx.query(
            f'match $cl isa scilit-synthesized-claim, has id "{escape_string(cl["id"])}"; '
            f'(synthesized-claim: $cl, evidence: $e) isa scilit-claim-evidence; '
            f'fetch {{ "id": $e.id, "argument": $e.content, "confidence": $e.confidence, '
            f'"evidence_type": $e.scilit-evidence-type }};'
        ).resolve())
        warrants = [{k: v for k, v in r.items() if v is not None} for r in ev_rows]
        for w in warrants:
            grounds = list(tx.query(
                f'match $e isa scilit-evidence, has id "{escape_string(w["id"])}"; '
                f'(evidence: $e, ground-claim: $rc) isa scilit-evidence-grounds; '
                f'fetch {{ "id": $rc.id, "statement": $rc.scilit-claim-statement }};').resolve())
            w["grounds"] = [{k: v for k, v in g.items() if v is not None} for g in grounds]
            # grounding in structured data: the template instances (and their papers) this warrant rests on
            inst = list(tx.query(
                f'match $e isa scilit-evidence, has id "{escape_string(w["id"])}"; '
                f'(evidence: $e, grounding-instance: $i) isa scilit-evidence-instance; '
                f'(sensemaking: $b, experiment: $i) isa scilit-sensemaking-experiment; '
                f'(sensemaking: $b, paper: $p) isa scilit-sensemaking-paper; '
                f'fetch {{ "id": $i.id, "name": $i.name, "bundle": $b.id, "paper": $p.name }};').resolve())
            w["grounding_instances"] = [{k: v for k, v in g.items() if v is not None} for g in inst]
        cl["evidence"] = warrants
    tier = {t: i for i, t in enumerate(CLAIM_TYPES)}
    claims.sort(key=lambda c: tier.get(c.get("type"), 99))
    return claims


def _load_impacts(tx, inv_id):
    """Load citation-impact notes with their citing papers."""
    imp_rows = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
        f'(investigation: $inv, impact: $imp) isa scilit-investigation-impact; '
        f'fetch {{ "id": $imp.id, "impact_type": $imp.scilit-impact-type, '
        f'"impact_summary": $imp.scilit-impact-summary }};'
    ).resolve())
    impacts = [{k: v for k, v in r.items() if v is not None} for r in imp_rows]
    for imp in impacts:
        cit = list(tx.query(
            f'match $imp isa scilit-citation-impact, has id "{escape_string(imp["id"])}"; '
            f'(impact: $imp, citing-paper: $p) isa scilit-impact-citation; '
            f'fetch {{ "id": $p.id, "name": $p.name, "doi": $p.scilit-doi }};'
        ).resolve())
        imp["citing_paper"] = ({k: v for k, v in cit[0].items() if v is not None}
                               if cit else None)
    return impacts


def cmd_frame_investigation(args):
    """Capture an investigation's goals: its question + (optional) grounding policy, stored IN the KG."""
    import kqed as K
    policy = None
    if args.policy:
        policy = json.load(open(args.policy, encoding="utf-8")) if os.path.exists(args.policy) \
            else json.loads(args.policy)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            exists = list(tx.query(
                f'match $i isa scilit-investigation, has id "{escape_string(args.id)}"; '
                f'fetch {{ "id": $i.id }};').resolve())
        if not exists:
            print(json.dumps({"success": False, "error": "Investigation not found"}))
            sys.exit(1)
        K.set_investigation_question(driver, args.id, args.question)
        if policy is not None:
            K.set_grounding_policy(driver, args.id, policy)
    print(json.dumps({
        "success": True, "id": args.id, "question": args.question,
        "grounding_policy_set": policy is not None,
        "trusted_sources": (policy or {}).get("trusted_sources"),
    }, indent=2))


# Default relationship-predicate grounding (verbatim mech-type -> RO predicate CURIE).
_PREDICATE_RO = {
    "activates": "RO:0002213", "maintains": "RO:0002213", "promotes": "RO:0002213",
    "inhibits": "RO:0002212", "suppresses": "RO:0002212", "represses": "RO:0002212",
}


def cmd_ground_predicates(args):
    """Ground relationship types: set scilit-predicate-curie on mechanistic links from their
    verbatim scilit-mech-type via the RO mapping (idempotent)."""
    n = 0
    with get_driver() as driver:
        for mt, ro in _PREDICATE_RO.items():
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(
                    f'match $r isa scilit-mechanistic-link, has scilit-mech-type "{escape_string(mt)}"; '
                    f'not {{ $r has scilit-predicate-curie $x; }}; '
                    f'insert $r has scilit-predicate-curie "{ro}";'
                ).resolve()
                tx.commit()
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                n += len(list(tx.query(
                    f'match $r isa scilit-mechanistic-link, has scilit-mech-type "{escape_string(mt)}", '
                    f'has scilit-predicate-curie "{ro}"; select $r;').resolve()))
    print(json.dumps({"success": True, "predicates_grounded_links": n,
                      "mapping": _PREDICATE_RO}, indent=2))


def cmd_analyze_investigation(args):
    """Synthesize: group grounded mechanism edges by (subject, predicate, object), reconcile stance,
    and write one scilit-synthesis-note per cluster addressing the investigation. Reads only edges whose
    BOTH endpoints are grounded and whose predicate is grounded."""
    import kqed as K
    from cluster_synthesis import cluster_and_reconcile
    with get_driver() as driver:
        # idempotent: clear prior synthesis notes threaded under this investigation
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            prior = [row["sid"] for row in tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.id)}"; '
                f'$s isa scilit-synthesis-note; (parent-note: $inv, child-note: $s) isa alh-note-threading; '
                f'$s has id $sid; fetch {{ "sid": $sid }};').resolve()]
        for sid in prior:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(f'match $s isa scilit-synthesis-note, has id "{escape_string(sid)}"; '
                         f'$rel isa alh-note-threading, links (child-note: $s); delete $rel;').resolve()
                tx.query(f'match $s isa scilit-synthesis-note, has id "{escape_string(sid)}"; '
                         f'$rel isa alh-aboutness, links (note: $s); delete $rel;').resolve()
                tx.query(f'match $s isa scilit-synthesis-note, has id "{escape_string(sid)}"; delete $s;').resolve()
                tx.commit()
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            rows = list(tx.query(
                'match '
                '$s isa scilit-bioentity, has name $sn; '
                '(classified-entity: $s, type-facet: $st) isa alh-classification; '
                '$st isa scilit-ontology-term, has scilit-curie $sc; '
                '$o isa scilit-bioentity, has name $on; '
                '(classified-entity: $o, type-facet: $ot) isa alh-classification; '
                '$ot isa scilit-ontology-term, has scilit-curie $oc; '
                '$r isa scilit-mechanistic-link, links (mech-source: $s, mech-target: $o), '
                'has scilit-predicate-curie $pc, has scilit-mech-type $mt; '
                'fetch { "sc": $sc, "oc": $oc, "pc": $pc, "mt": $mt, "sn": $sn, "on": $on };'
            ).resolve())
        edges, meta = [], {}
        for i, row in enumerate(rows):
            eid = f'{row["sc"]}|{row["pc"]}|{row["oc"]}'
            edges.append({"id": f"e{i}", "paper_id": None, "subject": row["sc"],
                          "object": row["oc"], "predicate": row["pc"]})
            meta[(row["sc"], row["oc"])] = row
        clusters = cluster_and_reconcile(edges)
        written = []
        for c in clusters:
            if c["key"] == "__ungrounded__":
                continue
            sc, oc = c["key"]; m = meta.get((sc, oc), {})
            verb = m.get("mt", "relates to")
            statement = f'{m.get("sn", sc)} {verb} {m.get("on", oc)}.'
            sid = K.add_synthesis_note(driver, args.id, statement, c["stance"], concept_curies=[sc, oc])
            written.append({"id": sid, "statement": statement, "stance": c["stance"],
                            "subject": sc, "object": oc, "predicates": c["predicates"]})
    print(json.dumps({"success": True, "investigation": args.id,
                      "grounded_edges": len(edges), "synthesis_notes": len(written),
                      "notes": written[:30]}, indent=2))


def cmd_show_synthesis(args):
    """Read an investigation's KQED analysis for the dashboard: question, synthesis notes (with stance +
    grounded concepts), and the grounded mechanism edges (for the graph). Read-only."""
    import kqed as K
    with get_driver() as driver:
        question = K.get_investigation_question(driver, args.id)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            notes = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.id)}"; '
                f'$s isa scilit-synthesis-note; (parent-note: $inv, child-note: $s) isa alh-note-threading; '
                f'$s has id $sid, has content $c, has scilit-synthesis-stance $st; '
                f'fetch {{ "id": $sid, "statement": $c, "stance": $st }};').resolve())
            for n in notes:
                cons = list(tx.query(
                    f'match $s isa scilit-synthesis-note, has id "{escape_string(n["id"])}"; '
                    f'$t isa scilit-ontology-term, has scilit-curie $cu, has name $nm; '
                    f'(note: $s, subject: $t) isa alh-aboutness; '
                    f'fetch {{ "curie": $cu, "name": $nm }};').resolve())
                n["concepts"] = cons
    # Mechanism edge graph removed from the synthesis view (mechanism is no longer curated/surfaced);
    # `edges` kept as an empty list for payload back-compat.
    print(json.dumps({"success": True, "investigation": args.id, "question": question,
                      "synthesis": notes, "edges": []}, indent=2))


def cmd_survey_entities(args):
    """Survey entity mentions against the investigation's grounding policy: what grounds (and to which
    category), what needs review, what's ungrounded. Dry-run (no writes) — produces the coverage +
    grounding worklist that decides what to commit. Scopes to distinct scilit-bioentity mentions."""
    import kqed as K
    from ontology_grounding import survey_term
    with get_driver() as driver:
        policy = K.get_grounding_policy(driver, args.investigation)
        if not policy:
            print(json.dumps({"success": False, "error": "Investigation has no grounding policy"}))
            sys.exit(1)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            rows = list(tx.query(
                'match $b isa scilit-bioentity, has id $i, has name $n; '
                'fetch { "id": $i, "name": $n, '
                '"label": $b.scilit-grounding-label };').resolve())
        # mention = canonical grounding-label when present, else verbatim name; distinct, bounded by --limit
        seen, items = set(), []
        for row in rows:
            mention = row.get("label") or row["name"]
            if mention not in seen:
                seen.add(mention); items.append({"id": row["id"], "mention": mention})
        items = items[: int(getattr(args, "limit", 0) or len(items))]
        results = []
        for it in items:
            g = survey_term(it["mention"], policy)
            results.append({"id": it["id"], **g})
    by_state = {"grounded": 0, "needs-review": 0, "ungrounded": 0}
    by_source = {}
    for r in results:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
        if r["state"] == "grounded":
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
    worklist = [r for r in results if r["state"] == "grounded"]
    print(json.dumps({
        "success": True, "investigation": args.investigation,
        "surveyed": len(results), "coverage": by_state, "grounded_by_source": by_source,
        "worklist": worklist[:50],
        "needs_review_sample": [r for r in results if r["state"] == "needs-review"][:15],
        "ungrounded_sample": [r["mention"] for r in results if r["state"] == "ungrounded"][:15],
    }, indent=2))


def cmd_ground_entity(args):
    """Ground one entity to an ontology term, using an investigation's grounding policy (from the KG)."""
    import kqed as K
    from ontology_grounding import ground_term
    with get_driver() as driver:
        policy = K.get_grounding_policy(driver, args.investigation)
        if not policy:
            print(json.dumps({"success": False,
                              "error": "Investigation has no grounding policy; run frame-investigation first"}))
            sys.exit(1)
        mention = args.mention
        if not mention:
            # prefer the canonical full expression (scilit-grounding-label) over the verbatim name
            gl = K.r(driver, f'match $e isa scilit-entity, has id "{escape_string(args.id)}", has scilit-grounding-label $g; fetch {{"g": $g}};')
            if gl:
                mention = gl[0]["g"]
            else:
                hit = K.r(driver, f'match $e isa scilit-entity, has id "{escape_string(args.id)}", has name $n; fetch {{"n": $n}};')
                mention = hit[0]["n"] if hit else args.id
        g = ground_term(mention, args.kind, policy)
        state = K.persist_grounding(driver, args.id, g, policy_version=policy.get("policy_version"))
    print(json.dumps({"success": True, "id": args.id, "mention": mention, "kind": args.kind,
                      "state": state, "curie": g.get("curie"), "source": g.get("source"),
                      "reason": g.get("reason")}, indent=2))


def cmd_list_ungrounded(args):
    """List entities not yet grounded (no scilit-grounding-state == grounded)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            rows = list(tx.query(
                'match $e isa scilit-entity, has id $eid, has name $n; '
                'not { $e has scilit-grounding-state "grounded"; }; '
                'fetch { "id": $eid, "name": $n };'
            ).resolve())
    print(json.dumps({"success": True, "count": len(rows), "ungrounded": rows[:200]}, indent=2))


def cmd_show_investigation(args):
    """Show an investigation: metadata, subject, phase notes, and (deep-dive) claims/impacts."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            investigation = _load_investigation(tx, args.id)
    if investigation is None:
        print(json.dumps({"success": False, "error": "Investigation not found"}))
        sys.exit(1)
    print(json.dumps({"success": True, **investigation}, indent=2))


# ---------------------------------------------------------------------------
# Stage + paper-curation aggregators (dashboard: investigation-centric IA)
# ---------------------------------------------------------------------------

def _load_fragments(tx, paper_id):
    """Verbatim full-text fragments (scilit-sentence / -section) for a paper, reached
    from its scilit-pdf-fulltext artifact via alh-fragmentation. Each carries offset +
    verbatim content; kind is the concrete fragment subtype label."""
    esc = escape_string(paper_id)
    rows = list(tx.query(
        f'match $p isa scilit-paper, has id "{esc}"; '
        f'$a isa scilit-pdf-fulltext; (alh-artifact: $a, referent: $p) isa alh-representation; '
        f'(whole: $a, part: $f) isa alh-fragmentation; $f isa alh-fragment; '
        f'fetch {{ "id": $f.id, "content": $f.content, "offset": $f.offset, "length": $f.length }};').resolve())
    frags = [{k: v for k, v in r.items() if v is not None} for r in rows]
    for fr in frags:
        sub = list(tx.query(
            f'match $f isa alh-fragment, has id "{escape_string(fr["id"])}"; select $f;').resolve())
        if sub:
            try:
                fr["kind"] = _tlabel(sub[0].get("f")).replace("scilit-", "")
            except Exception:
                fr["kind"] = None
    frags.sort(key=lambda f: f.get("offset") if f.get("offset") is not None else 1 << 30)
    return frags


def _load_derivations(tx, paper_id):
    """Span-anchoring edges (alh-derivation): each rhetorical note (derivative) tied to the
    verbatim fragment (derived-from-source) that justifies it. Returns note->fragment rows."""
    esc = escape_string(paper_id)
    rows = list(tx.query(
        f'match $p isa scilit-paper, has id "{esc}"; '
        f'$a isa scilit-pdf-fulltext; (alh-artifact: $a, referent: $p) isa alh-representation; '
        f'(whole: $a, part: $f) isa alh-fragmentation; '
        f'(derivative: $n, derived-from-source: $f) isa alh-derivation; '
        f'fetch {{ "note": $n.id, "frag": $f.id, "offset": $f.offset, "quote": $f.content }};').resolve())
    return [{k: v for k, v in r.items() if v is not None} for r in rows]


def cmd_list_databases(args):
    """List TypeDB databases for the dashboard DB switcher, each annotated with whether it
    holds scientific-literature data (the scilit dashboard is only meaningful where it does).
    Different databases carry different skills' data, so the UI filters to scilit-bearing DBs.
    `databases` keeps the flat name list for back-compat; `info` adds the per-DB lookup."""
    info = []
    with get_driver() as driver:
        names = sorted(db.name for db in driver.databases.all())
        for name in names:
            entry = {"name": name, "hasScilit": False, "investigations": 0, "papers": 0}
            try:
                with driver.transaction(name, TransactionType.READ) as tx:
                    invs = list(tx.query('match $i isa scilit-investigation; select $i;').resolve())
                    entry["investigations"] = len(invs)
                    papers = list(tx.query(
                        'match $p isa scilit-paper; select $p; limit 1;').resolve())
                    entry["papers"] = len(papers)
                    entry["hasScilit"] = bool(invs) or bool(papers)
            except Exception:
                # scilit types not defined in this DB (or unreadable) -> not scilit-bearing
                pass
            info.append(entry)
    print(json.dumps({
        "success": True,
        "databases": [e["name"] for e in info],
        "info": info,
    }, indent=2))


def cmd_show_stage(args):
    """Show one investigation stage (scilit-investigation-phase) with kind-specific data:
    discovery (corpora + note), ingest (papers + artifact status + doi + suggested pdf filename),
    sensemaking (per-paper bundles + counts), analysis (pipeline/faceting notes), report (note)."""
    pid = args.id
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            head = list(tx.query(
                f'match $ph isa scilit-investigation-phase, has id "{escape_string(pid)}"; '
                f'fetch {{ "id": $ph.id, "name": $ph.name, "content": $ph.content, '
                f'"kind": $ph.scilit-phase }};').resolve())
            if not head:
                print(json.dumps({"success": False, "error": "Stage not found"})); sys.exit(1)
            stage = {k: v for k, v in head[0].items() if v is not None}
            kind = stage.get("kind")
            inv = list(tx.query(
                f'match $ph isa scilit-investigation-phase, has id "{escape_string(pid)}"; '
                f'(iteration: $it, stage: $ph) isa scilit-iteration-stage; '
                f'(investigation: $iv, iteration: $it) isa scilit-investigation-iteration; '
                f'$it has scilit-iteration-index $idx; '
                f'fetch {{ "id": $iv.id, "name": $iv.name, "iteration": $idx }};').resolve())
            stage["investigation"] = ({k: v for k, v in inv[0].items() if v is not None} if inv else None)
            inv_id = inv[0]["id"] if inv else None

            if kind in ("discovery", "ingest"):
                corpora = []
                if inv_id:
                    crows = list(tx.query(
                        f'match $iv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
                        f'(investigation: $iv, corpus: $c) isa scilit-investigation-scope; '
                        f'fetch {{ "id": $c.id, "name": $c.name, "description": $c.description, '
                        f'"logical-query": $c.alh-logical-query }};').resolve())
                    corpora = [{k: v for k, v in r.items() if v is not None} for r in crows]
                stage["corpora"] = corpora
                if kind == "ingest":
                    papers = []
                    for c in corpora:
                        prows = list(tx.query(
                            f'match $c isa scilit-corpus, has id "{escape_string(c["id"])}"; '
                            f'(collection: $c, member: $p) isa alh-collection-membership; $p isa scilit-paper; '
                            f'fetch {{ "id": $p.id, "name": $p.name, "doi": $p.scilit-doi, '
                            f'"year": $p.scilit-publication-year, '
                            f'"acquisition_status": $p.scilit-acquisition-status }};').resolve())
                        for r in prows:
                            pp = {k: v for k, v in r.items() if v is not None}
                            fe = list(tx.query(
                                f'match $p isa scilit-paper, has id "{escape_string(pp["id"])}"; '
                                f'$a isa scilit-pdf-fulltext; '
                                f'(alh-artifact: $a, referent: $p) isa alh-representation; '
                                f'fetch {{ "id": $a.id }};').resolve())
                            pp["fulltextPresent"] = bool(fe)
                            pp["corpus"] = c["id"]
                            # canonical save name for a manually downloaded PDF; feed via
                            #   fetch-pdf --id <paper> --file <pdfFilename>
                            pp["pdfFilename"] = f'{pp["id"]}.pdf'
                            papers.append(pp)
                    papers.sort(key=lambda p: p.get("year") or 0, reverse=True)
                    stage["papers"] = papers
                # verifier findings relevant to this stage (discovery-description / ingestion checks)
                if inv_id:
                    _lc = _lint_ctx_investigation(tx, inv_id)
                    _cat = "discovery" if kind == "discovery" else "ingest"
                    stage["checks"] = [c for c in (fn(_lc) for fn in INVESTIGATION_CHECKS) if c["category"] == _cat]
            elif kind == "sensemaking":
                stage["bundles"] = _load_bundles(tx, pid)
            elif kind == "analysis":
                fn = list(tx.query(
                    f'match $ph isa scilit-investigation-phase, has id "{escape_string(pid)}"; '
                    f'(phase: $ph, faceting: $fn) isa scilit-phase-faceting; '
                    f'fetch {{ "id": $fn.id, "name": $fn.name }};').resolve())
                stage["pipeline_notes"] = [{k: v for k, v in f.items() if v is not None} for f in fn]
            elif kind == "report" and inv_id:
                # the investigation outcome: synthesized claims (+ evidence warrants) and citation impacts
                stage["synthesized_claims"] = _load_synthesized_claims(tx, inv_id)
                stage["citation_impacts"] = _load_impacts(tx, inv_id)
    print(json.dumps({"success": True, **stage}, indent=2))


def cmd_show_paper_curation(args):
    """One-shot payload for the single-paper curation walkthrough: paper + full-text artifact,
    verbatim fragments, span-anchoring (alh-derivation), the full sensemaking bundle
    (observations / claims / gaps / mechanisms / KEfED experiments / data instances), and a
    data signature per experiment. hasCuration=False when the paper has no bundle."""
    pid = args.id
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            head = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(pid)}"; '
                f'fetch {{ "id": $p.id, "name": $p.name, "doi": $p.scilit-doi, "pmid": $p.scilit-pmid, '
                f'"year": $p.scilit-publication-year, "journal": $p.scilit-journal-name, '
                f'"volume": $p.scilit-journal-volume, "issue": $p.scilit-journal-issue, '
                f'"pages": $p.scilit-page-range, "authors": $p.scilit-author-list, '
                f'"acquisition_status": $p.scilit-acquisition-status }};').resolve())
            if not head:
                print(json.dumps({"success": False, "error": "Paper not found"})); sys.exit(1)
            paper = {k: v for k, v in head[0].items() if v is not None}
            art = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(pid)}"; $a isa scilit-pdf-fulltext; '
                f'(alh-artifact: $a, referent: $p) isa alh-representation; '
                f'fetch {{ "id": $a.id, "cache-path": $a.cache-path, "file-size": $a.file-size, '
                f'"format": $a.format, "source-uri": $a.source-uri }};').resolve())
            fulltext = ({k: v for k, v in art[0].items() if v is not None} if art else None)

            b = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(pid)}"; '
                f'(sensemaking: $bn, paper: $p) isa scilit-sensemaking-paper; '
                f'fetch {{ "id": $bn.id }};').resolve())
            if not b:
                print(json.dumps({"success": True, "hasCuration": False,
                                  "paper": paper, "fulltext": fulltext}, indent=2))
                return
            bundle_id = b[0]["id"]
            bundle = _load_bundle(tx, bundle_id)
            # Mechanism graph is no longer part of the sensemaking view — drop it from the
            # walkthrough payload (schema + show-bundle keep it, dormant).
            bundle.pop("mechanisms", None)
            fragments = _load_fragments(tx, pid)
            derivations = _load_derivations(tx, pid)
            # claim -> observation grounding edges (scilit-claim-observation)
            co_rows = list(tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(bundle_id)}"; '
                f'(sensemaking: $b, reported-claim: $c) isa scilit-sensemaking-reported-claim; '
                f'(claim: $c, observation: $o) isa scilit-claim-observation; '
                f'fetch {{ "claim": $c.id, "observation": $o.id }};').resolve())
            claim_observations = [{k: v for k, v in r.items() if v is not None} for r in co_rows]
            spine_rows = list(tx.query(
                f'match $bn isa scilit-paper-sensemaking, has id "{escape_string(bundle_id)}"; '
                f'(phase: $ph, sensemaking: $bn) isa scilit-phase-sensemaking; '
                f'(iteration: $it, stage: $ph) isa scilit-iteration-stage; '
                f'(investigation: $iv, iteration: $it) isa scilit-investigation-iteration; '
                f'$it has scilit-iteration-index $idx; '
                f'fetch {{ "id": $iv.id, "name": $iv.name, "iteration": $idx, "phase": $ph.id }};').resolve())
            spine = ({k: v for k, v in spine_rows[0].items() if v is not None} if spine_rows else None)
            signatures = {}
            for e in bundle.get("experiments", []):
                try:
                    signatures[e["id"]] = _data_signature(tx, e["id"])
                except Exception:
                    signatures[e["id"]] = {}
    print(json.dumps({
        "success": True, "hasCuration": True, "paper": paper, "fulltext": fulltext,
        "bundle_id": bundle_id, "spine": spine, "fragments": fragments,
        "derivations": derivations, "claim_observations": claim_observations,
        "bundle": bundle, "signatures": signatures,
    }, indent=2))


# ---------------------------------------------------------------------------
# Sensemaking linter — verify a paper's KQED/KEfED/OOEVV curation is well-formed
# so Claude can self-check. Each check returns a finding dict:
#   {id, name, category, severity, status: pass|warn|fail, detail, offenders:[ids]}
# SENSEMAKING_CHECKS is the extension point — add checks as the criteria evolve.
# ---------------------------------------------------------------------------

def _finding(cid, name, category, severity, offenders, ok_detail, bad_detail, warn=False):
    offenders = [o for o in offenders if o]
    status = "pass" if not offenders else ("warn" if warn else "fail")
    detail = ok_detail if not offenders else bad_detail.format(n=len(offenders))
    return {"id": cid, "name": name, "category": category, "severity": severity,
            "status": status, "detail": detail, "offenders": offenders[:50]}


def _bundle_variables(bundle):
    """All ooevv-variable briefs across the bundle's experiments."""
    out = []
    for e in bundle.get("experiments", []) or []:
        for p in ((e.get("experiment") or {}).get("processes") or []):
            out.extend((p.get("parameters") or []) + (p.get("measurements") or []))
    return out


def _chk_has_observations(ctx):
    obs = ctx["bundle"].get("observations") or []
    return _finding("has-observations", "Bundle has observations", "rhetoric", "high",
                    [] if obs else [ctx["bundle"]["id"]], f"{len(obs)} observations",
                    "no observations in the bundle")


def _chk_has_claims(ctx):
    cl = ctx["bundle"].get("reported_claims") or []
    return _finding("has-claims", "Bundle has reported claims", "rhetoric", "high",
                    [] if cl else [ctx["bundle"]["id"]], f"{len(cl)} claims",
                    "no reported claims in the bundle")


def _chk_claims_grounded(ctx):
    offenders = [c["id"] for c in (ctx["bundle"].get("reported_claims") or [])
                 if not ctx["claim_obs"].get(c["id"])]
    return _finding("claims-grounded", "Claims grounded in observations", "rhetoric", "medium",
                    offenders, "every claim cites >=1 observation",
                    "{n} claim(s) cite no observation (scilit-claim-observation)", warn=True)


def _chk_notes_anchored(ctx):
    anchored = {d["note"] for d in ctx["derivations"]}
    notes = ([n["id"] for n in (ctx["bundle"].get("observations") or [])]
             + [c["id"] for c in (ctx["bundle"].get("reported_claims") or [])]
             + [g["id"] for g in (ctx["bundle"].get("reported_gaps") or [])])
    offenders = [nid for nid in notes if nid not in anchored]
    return _finding("notes-anchored", "Notes span-anchored to full text", "rhetoric", "medium",
                    offenders, "every claim/gap/observation has a fragment anchor",
                    "{n} note(s) lack an alh-derivation fragment anchor", warn=True)


def _chk_experiments_measurement(ctx):
    offenders = []
    for e in ctx["bundle"].get("experiments") or []:
        has_meas = any((p.get("measurements") for p in ((e.get("experiment") or {}).get("processes") or [])))
        if not has_meas:
            offenders.append(e["id"])
    return _finding("exp-has-measurement", "Experiments declare a measurement", "kefed", "high",
                    offenders, "every experiment declares >=1 measurement",
                    "{n} experiment(s) have no measurement variable")


def _chk_measurement_signature(ctx):
    offenders = []
    for sig in ctx["signatures"].values():
        for vid, s in (sig or {}).items():
            if not s.get("index"):
                offenders.append(vid)
    return _finding("measurement-signature", "Measurements are indexed (data signature)", "kefed", "medium",
                    offenders, "every measurement is indexed by >=1 parameter",
                    "{n} measurement(s) have an empty data signature", warn=True)


def _chk_variables_quality_scale(ctx):
    offenders = [v.get("id") for v in _bundle_variables(ctx["bundle"])
                 if not (v.get("quality") and v.get("scale"))]
    return _finding("var-quality-scale", "Variables have quality + value-spec", "ooevv", "high",
                    offenders, "every variable has a quality and a value-spec",
                    "{n} variable(s) missing a quality or scale")


def _chk_quality_grounding_state(ctx):
    offenders, seen = [], set()
    for v in _bundle_variables(ctx["bundle"]):
        q = v.get("quality") or {}
        qid = q.get("quality_id") or q.get("quality")
        if qid and qid not in seen:
            seen.add(qid)
            if not q.get("grounding_state"):
                offenders.append(qid)
    return _finding("quality-grounding-state", "Qualities carry a grounding state", "ooevv", "low",
                    offenders, "every quality has grounding-state set",
                    "{n} quality(ies) have no grounding-state", warn=True)


def _chk_instances_cells(ctx):
    offenders = []
    for inst in ctx["bundle"].get("instances") or []:
        for row in inst.get("data") or []:
            if not row.get("cells"):
                offenders.append(row.get("id"))
    return _finding("instance-rows-cells", "Data rows have cells", "kefed", "medium",
                    offenders, "every data row has >=1 cell", "{n} data row(s) have no cells")


def _chk_fragments_located(ctx):
    offenders = [f["id"] for f in ctx["fragments"] if f.get("offset") is None]
    return _finding("fragments-located", "Fragments have a resolved offset", "fulltext", "low",
                    offenders, "every fragment has a character offset",
                    "{n} fragment(s) could not be located in the full text", warn=True)


# --- KEfED bigraph structural checks (operate over ctx["graphs"] = {model_id: _model_graph}) ---
# The bigraph models under a bundle are the inline experiments AND the templates behind instances;
# ctx["graphs"] gathers them all, so these checks cover template-based curation too (where the
# earlier experiment-only checks were silent).

def _edge_key(mid, e):
    return f"{mid}:{e['src']}-{e['kind']}->{e['dst']}"


def _chk_bipartite(ctx):
    """No flow edge joins two nodes of the SAME class — entities never flow into entities and
    processes never flow into processes (the defining bigraph invariant)."""
    offenders = []
    for mid, g in ctx["graphs"].items():
        for e in g["edges"]:
            sc, tc = g["klass"].get(e["src"]), g["klass"].get(e["dst"])
            if sc is not None and sc == tc:
                offenders.append(_edge_key(mid, e))
    return _finding("bigraph-bipartite", "Flow graph is bipartite (entity<->process)", "kefed", "high",
                    offenders, "every flow edge joins an entity to a process",
                    "{n} flow edge(s) join two nodes of the same class (entity-entity or process-process)")


def _chk_flow_roles(ctx):
    """Flow edges run the correct direction for their role: input edges go entity->process
    (input-node is the entity consumed BY the process), output edges go process->entity."""
    offenders = []
    for mid, g in ctx["graphs"].items():
        for e in g["edges"]:
            sc, tc = g["klass"].get(e["src"]), g["klass"].get(e["dst"])
            if sc is None or tc is None or sc == tc:
                continue  # untyped or same-class handled by bipartite check
            want = ("entity", "process") if e["kind"] == "input" else ("process", "entity")
            if (sc, tc) != want:
                offenders.append(_edge_key(mid, e))
    return _finding("bigraph-flow-roles", "Flow edges are correctly directed", "kefed", "high",
                    offenders, "every input edge is entity->process and every output edge process->entity",
                    "{n} flow edge(s) are wired in the wrong direction for their role")


def _has_cycle(feeders):
    """DFS cycle detection over a feeders adjacency map."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in feeders}
    def visit(n):
        color[n] = GREY
        for m in feeders.get(n, ()):
            if color.get(m, WHITE) == GREY:
                return True
            if color.get(m, WHITE) == WHITE and visit(m):
                return True
        color[n] = BLACK
        return False
    return any(color[n] == WHITE and visit(n) for n in feeders)


def _chk_acyclic(ctx):
    """Each model's flow graph is a DAG — a cycle makes the data-signature traversal ill-defined."""
    offenders = [mid for mid, g in ctx["graphs"].items() if _has_cycle(g["feeders"])]
    return _finding("bigraph-acyclic", "Flow graph is acyclic (a DAG)", "kefed", "high",
                    offenders, "every model's flow graph is a DAG",
                    "{n} model(s) contain a cycle in their flow graph")


def _chk_transformation_mapping(ctx):
    """Every data-transformation whose inputs carry index parameters must DECLARE how it maps them
    (ooevv-param-mapping). Without it the signature falls back to naive passthrough — the exact bug
    where a correlation/mean keeps an index it actually consumes. Curation must be explicit."""
    offenders = []
    for mid, g in ctx["graphs"].items():
        cache = {}
        for n in g["nodes"]:
            if not g["is_dt"].get(n):
                continue
            incoming = set()
            for f in g["feeders"].get(n, ()):
                incoming |= _carried_index(g, f, cache)
            if incoming and not g["dt_has_map"].get(n):
                offenders.append(f"{mid}:{n}")
    return _finding("transformation-mapping", "Data-transformations declare their param mapping",
                    "kefed", "high", offenders,
                    "every index-consuming data-transformation declares an ooevv-param-mapping",
                    "{n} data-transformation(s) with indexed inputs declare no param mapping "
                    "(use map-params; index defaults to naive passthrough)")


def _chk_experiment_has_subject(ctx):
    """Every KEfED model declares a subject (source) node — the experimental material the protocol
    starts from. Without it the protocol spine has no defined beginning."""
    offenders = [mid for mid, g in ctx["graphs"].items() if g["nodes"] and not g["subject"]]
    return _finding("experiment-has-subject", "Experiments declare a subject node", "kefed", "high",
                    offenders, "every model declares an ooevv-subject source node",
                    "{n} model(s) declare no subject node")


def _chk_nodes_connected(ctx):
    """No island nodes: every node participates in at least one flow edge (a lone subject in a
    single-node model is allowed)."""
    offenders = []
    for mid, g in ctx["graphs"].items():
        incident = {e["src"] for e in g["edges"]} | {e["dst"] for e in g["edges"]}
        for n in g["nodes"]:
            if n not in incident and not (len(g["nodes"]) == 1 and n == g["subject"]):
                offenders.append(f"{mid}:{n}")
    return _finding("nodes-connected", "No island nodes in the flow graph", "kefed", "medium",
                    offenders, "every node participates in >=1 flow edge",
                    "{n} node(s) are disconnected from the flow graph", warn=True)


def _measurement_cells(ctx):
    """Yield (instance_id, row_id, cell) for every measurement-role cell across the bundle's
    instance data rows — the recorded readout values."""
    for inst in ctx["bundle"].get("instances") or []:
        for row in inst.get("data") or []:
            for c in row.get("cells") or []:
                if c.get("role") == "measurement":
                    yield inst.get("id"), row.get("id"), c


def _chk_measurement_units(ctx):
    """Every numeric readout value carries a unit (per-row kefed-cell-unit) — a bare number is not
    interpretable. Dimensionless readouts should say so explicitly (unit 'ratio'/'dimensionless')."""
    offenders = [f"{iid}:{rid}:{c.get('variable')}"
                 for iid, rid, c in _measurement_cells(ctx)
                 if c.get("number") is not None and not c.get("unit")]
    return _finding("measurement-units", "Numeric readouts carry a unit", "ooevv", "medium",
                    offenders, "every numeric readout value has a unit",
                    "{n} numeric readout value(s) have no unit (set 'unit' on the datum cell)", warn=True)


def _chk_readout_sample_size(ctx):
    """Every summary readout value records its sample size (kefed-cell-n) so the reader knows how
    many observations back it — Eric Wang: 'needs number of animals / sample size'."""
    offenders = [f"{iid}:{rid}:{c.get('variable')}"
                 for iid, rid, c in _measurement_cells(ctx)
                 if c.get("number") is not None and c.get("n") is None]
    return _finding("readout-sample-size", "Readouts record a sample size (n)", "kefed", "low",
                    offenders, "every numeric readout records its sample size (n)",
                    "{n} readout value(s) record no sample size (set 'n' on the datum cell)", warn=True)


SENSEMAKING_CHECKS = [
    _chk_has_observations, _chk_has_claims, _chk_claims_grounded, _chk_notes_anchored,
    _chk_experiments_measurement, _chk_measurement_signature, _chk_variables_quality_scale,
    _chk_quality_grounding_state, _chk_instances_cells, _chk_fragments_located,
    # KEfED bigraph structural checks (over ctx["graphs"])
    _chk_bipartite, _chk_flow_roles, _chk_acyclic, _chk_transformation_mapping,
    _chk_experiment_has_subject, _chk_nodes_connected,
    # readout-quality checks (over instance data cells)
    _chk_measurement_units, _chk_readout_sample_size,
]


def cmd_lint_sensemaking(args):
    """Linter over a paper's sensemaking curation (KQED rhetoric + KEfED experiments + OOEVV vocab).
    Loads the bundle once and runs SENSEMAKING_CHECKS; each finding carries status pass|warn|fail +
    offending ids so Claude (or the dashboard) can verify the curation is well-formed."""
    pid = args.id
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            b = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(pid)}"; '
                f'(sensemaking: $bn, paper: $p) isa scilit-sensemaking-paper; '
                f'fetch {{ "id": $bn.id }};').resolve())
            if not b:
                print(json.dumps({"success": True, "hasCuration": False, "paper": pid,
                                  "checks": [], "summary": {"passed": 0, "warned": 0, "failed": 0}}, indent=2))
                return
            bundle_id = b[0]["id"]
            bundle = _load_bundle(tx, bundle_id)
            fragments = _load_fragments(tx, pid)
            derivations = _load_derivations(tx, pid)
            co_rows = list(tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(bundle_id)}"; '
                f'(sensemaking: $b, reported-claim: $c) isa scilit-sensemaking-reported-claim; '
                f'(claim: $c, observation: $o) isa scilit-claim-observation; '
                f'fetch {{ "claim": $c.id, "observation": $o.id }};').resolve())
            claim_obs = {}
            for r in co_rows:
                claim_obs.setdefault(r["claim"], []).append(r["observation"])
            # Gather every KEfED bigraph model under this bundle: inline experiments (kefed-model)
            # AND the templates behind instances (kefed-instance -> kefed-instance-of -> model).
            # This is what the structural/signature checks run over — template-based curation was
            # invisible to the earlier experiment-only checks.
            model_ids = _bundle_model_ids(tx, bundle_id)
            graphs = {mid: _model_graph(tx, mid) for mid in model_ids}
            signatures = {mid: _data_signature(tx, mid) for mid in model_ids}
    ctx = {"paper": pid, "bundle": bundle, "fragments": fragments, "derivations": derivations,
           "claim_obs": claim_obs, "signatures": signatures, "graphs": graphs}
    checks = [fn(ctx) for fn in SENSEMAKING_CHECKS]
    summary = {
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "warned": sum(1 for c in checks if c["status"] == "warn"),
        "failed": sum(1 for c in checks if c["status"] == "fail"),
    }
    print(json.dumps({"success": True, "hasCuration": True, "paper": pid, "bundle_id": bundle_id,
                      "checks": checks, "summary": summary}, indent=2))


# ---------------------------------------------------------------------------
# Investigation linter — verify the process stages (discovery describes how the
# corpora were built; ingestion lists corpora + papers with full-text / DOI checks).
# INVESTIGATION_CHECKS is the extension point. Findings share the _finding shape.
# ---------------------------------------------------------------------------

def _lint_ctx_investigation(tx, inv_id):
    """Load the discovery description + corpora (with papers, each flagged for full text + DOI)."""
    esc = escape_string(inv_id)
    disc = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{esc}"; '
        f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration; '
        f'(iteration: $it, stage: $ph) isa scilit-iteration-stage; $ph has scilit-phase "discovery"; '
        f'fetch {{ "id": $ph.id, "content": $ph.content }};').resolve())
    discovery = ({k: v for k, v in disc[0].items() if v is not None} if disc else None)
    crows = list(tx.query(
        f'match $inv isa scilit-investigation, has id "{esc}"; '
        f'(investigation: $inv, corpus: $c) isa scilit-investigation-scope; '
        f'fetch {{ "id": $c.id, "name": $c.name }};').resolve())
    corpora = []
    for cr in crows:
        c = {k: v for k, v in cr.items() if v is not None}
        prows = list(tx.query(
            f'match $c isa scilit-corpus, has id "{escape_string(c["id"])}"; '
            f'(collection: $c, member: $p) isa alh-collection-membership; $p isa scilit-paper; '
            f'fetch {{ "id": $p.id, "doi": $p.scilit-doi }};').resolve())
        papers = []
        for pr in prows:
            p = {k: v for k, v in pr.items() if v is not None}
            ft = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(p["id"])}"; $a isa scilit-pdf-fulltext; '
                f'(alh-artifact: $a, referent: $p) isa alh-representation; fetch {{ "id": $a.id }};').resolve())
            p["fulltext"] = bool(ft)
            papers.append(p)
        c["papers"] = papers
        corpora.append(c)
    return {"investigation": inv_id, "discovery": discovery, "corpora": corpora}


def _chk_discovery_described(ctx):
    d = ctx.get("discovery")
    ok = bool(d and (d.get("content") or "").strip())
    return _finding("discovery-described", "Discovery describes how the corpora were built", "discovery", "high",
                    [] if ok else [ctx["investigation"]],
                    "the discovery stage has a description",
                    "the discovery stage has no description of how the corpora were built")


def _chk_ingestion_corpora(ctx):
    return _finding("ingestion-corpora", "Ingestion lists at least one corpus", "ingest", "high",
                    [] if ctx["corpora"] else [ctx["investigation"]],
                    f"{len(ctx['corpora'])} corpus/corpora in scope",
                    "the investigation has no corpus in scope")


def _chk_corpora_have_papers(ctx):
    offenders = [c["id"] for c in ctx["corpora"] if not c["papers"]]
    return _finding("corpora-have-papers", "Every corpus lists its papers", "ingest", "medium",
                    offenders, "every corpus lists papers", "{n} corpus/corpora have no papers")


def _chk_papers_have_doi(ctx):
    offenders = [p["id"] for c in ctx["corpora"] for p in c["papers"] if not p.get("doi")]
    return _finding("papers-have-doi", "Papers carry a DOI (for manual download)", "ingest", "medium",
                    offenders, "every paper has a DOI url", "{n} paper(s) have no DOI", warn=True)


def _chk_papers_fulltext(ctx):
    all_papers = [p for c in ctx["corpora"] for p in c["papers"]]
    offenders = [p["id"] for p in all_papers if not p.get("fulltext")]
    total = len(all_papers)
    return _finding("papers-fulltext", "Full text is available for papers", "ingest", "low",
                    offenders, f"full text held for all {total} paper(s)",
                    f"{{n}} of {total} paper(s) have no full text", warn=True)


INVESTIGATION_CHECKS = [
    _chk_discovery_described, _chk_ingestion_corpora, _chk_corpora_have_papers,
    _chk_papers_have_doi, _chk_papers_fulltext,
]


def cmd_lint_investigation(args):
    """Linter over an investigation's process stages: discovery must describe how the corpora
    were built; ingestion must list corpora + papers with full-text and DOI checks."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            head = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.id)}"; '
                f'fetch {{ "id": $inv.id }};').resolve())
            if not head:
                print(json.dumps({"success": False, "error": "Investigation not found"})); sys.exit(1)
            ctx = _lint_ctx_investigation(tx, args.id)
    checks = [fn(ctx) for fn in INVESTIGATION_CHECKS]
    summary = {
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "warned": sum(1 for c in checks if c["status"] == "warn"),
        "failed": sum(1 for c in checks if c["status"] == "fail"),
    }
    print(json.dumps({"success": True, "investigation": args.id, "checks": checks, "summary": summary}, indent=2))


def _render_investigation_md(inv):
    """Render an investigation dict as markdown."""
    lines = [f"# {inv.get('name', inv['id'])}", ""]
    meta = []
    if inv.get("type"):
        meta.append(f"**Type:** {inv['type']}")
    if inv.get("status"):
        meta.append(f"**Status:** {inv['status']}")
    if inv.get("created-at"):
        meta.append(f"**Started:** {inv['created-at']}")
    if meta:
        lines += [" · ".join(meta), ""]
    if inv.get("focal_paper"):
        fp = inv["focal_paper"]
        doi = f" ({fp['doi']})" if fp.get("doi") else ""
        lines += [f"**Focal paper:** {fp.get('name', fp['id'])}{doi}", ""]
    elif inv.get("corpus"):
        lines += [f"**Corpus:** {inv['corpus'].get('name', inv['corpus']['id'])}", ""]
    if inv.get("purpose"):
        lines += ["## Purpose", "", inv["purpose"], ""]

    if inv.get("synthesized_claims"):
        lines += ["## Synthesized claims & evidence warrants", ""]
        for cl in inv["synthesized_claims"]:
            lines.append(f"### [{cl.get('type', '?')}] {cl.get('statement', '')}")
            for ev in cl.get("evidence", []):
                conf = ev.get("confidence")
                conf_label = f" (confidence {conf})" if conf is not None else ""
                lines.append(f"- **Warrant{conf_label}:** {ev.get('argument', '')}")
                for g in ev.get("grounds", []):
                    lines.append(f"  - grounds: {g.get('statement', g.get('id'))}")
            lines.append("")

    if inv.get("citation_impacts"):
        counts = {}
        for imp in inv["citation_impacts"]:
            t = imp.get("impact_type", "?")
            counts[t] = counts.get(t, 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        lines += ["## Citation Impact", "", f"_{len(inv['citation_impacts'])} citing papers: {summary}_", ""]
        for imp in inv["citation_impacts"]:
            cit = imp.get("citing_paper")
            cit_label = ""
            if cit:
                doi = f" ({cit['doi']})" if cit.get("doi") else ""
                cit_label = f" {cit.get('name', cit['id'])}{doi}"
            lines.append(f"- **[{imp.get('impact_type', '?')}]**{cit_label}: {imp.get('impact_summary', '')}")
        lines.append("")

    if inv.get("phases"):
        lines += ["## Stages", ""]
        for ph in inv["phases"]:
            it = ph.get("iteration")
            it_label = f" (iteration {it})" if it is not None else ""
            lines.append(f"### {ph.get('phase', '?').capitalize()}{it_label}")
            if ph.get("content"):
                lines += [ph["content"], ""]
            for fn in ph.get("faceting_notes", []):
                lines.append(f"- Faceting pipeline: {fn.get('name', fn['id'])}")
            for b in ph.get("bundles", []):
                pap = b.get("paper") or {}
                lines.append(
                    f"- Sensemaking bundle: {pap.get('name', b.get('name', b['id']))} "
                    f"[{b.get('observation_count', 0)} obs, "
                    f"{b.get('reported_claim_count', 0)} reported-claims, "
                    f"{b.get('reported_gap_count', 0)} gaps]"
                )
            lines.append("")
    return "\n".join(lines)


def cmd_export_investigation(args):
    """Export an investigation as markdown (default) or JSON."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            investigation = _load_investigation(tx, args.id)
    if investigation is None:
        print(json.dumps({"success": False, "error": "Investigation not found"}))
        sys.exit(1)
    if getattr(args, "format", "md") == "json":
        print(json.dumps({"success": True, **investigation}, indent=2))
    else:
        print(_render_investigation_md(investigation))


def cmd_record_phase(args):
    """Upsert a phase note (one per investigation+phase+iteration); optionally advance status.

    Uses the iteration path: resolve-or-create scilit-iteration (by index) under the
    investigation, then resolve-or-create the scilit-investigation-phase under that iteration
    via scilit-iteration-stage. Content is set during creation or updated on upsert.
    """
    if args.phase not in INVESTIGATION_PHASES:
        print(json.dumps({"success": False,
                          "error": f"Invalid phase. Use one of: {', '.join(INVESTIGATION_PHASES)}"}))
        sys.exit(1)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            inv = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.investigation)}"; '
                f'fetch {{ "id": $inv.id }};'
            ).resolve())
            if not inv:
                print(json.dumps({"success": False, "error": "Investigation not found"}))
                sys.exit(1)

            iteration = int(getattr(args, "iteration", 1) or 1)
            # _ensure_phase_note handles resolve-or-create for both the iteration and the phase.
            # Pass content so it is set atomically during creation.
            ph_id, created = _ensure_phase_note(
                tx, args.investigation, args.phase, args.content, iteration
            )
            action = "created" if created else "updated"

            if not created:
                # Phase already existed — update its content (delete old value, insert new).
                if args.content is not None:
                    has_content = list(tx.query(
                        f'match $ph isa scilit-investigation-phase, has id "{escape_string(ph_id)}", '
                        f'has content $c; fetch {{ "c": $c }};'
                    ).resolve())
                    if has_content:
                        tx.query(
                            f'match $ph isa scilit-investigation-phase, has id "{escape_string(ph_id)}", '
                            f'has content $old; delete has $old of $ph;'
                        ).resolve()
                    tx.query(
                        f'match $ph isa scilit-investigation-phase, has id "{escape_string(ph_id)}"; '
                        f'insert $ph has content "{escape_string(args.content)}";'
                    ).resolve()

            if args.status:
                _set_investigation_status(tx, args.investigation, args.status)
            tx.commit()

    print(json.dumps({
        "success": True,
        "investigation": args.investigation,
        "phase": args.phase,
        "phase_note_id": ph_id,
        "action": action,
        "status": args.status,
    }, indent=2))


def cmd_link_analysis(args):
    """Thread a scilit-faceting-note under the investigation's analysis phase (idempotent)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            inv = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.investigation)}"; '
                f'fetch {{ "id": $inv.id }};'
            ).resolve())
            if not inv:
                print(json.dumps({"success": False, "error": "Investigation not found"}))
                sys.exit(1)
            fn = list(tx.query(
                f'match $fn isa scilit-faceting-note, has id "{escape_string(args.faceting_note)}"; '
                f'fetch {{ "id": $fn.id }};'
            ).resolve())
            if not fn:
                print(json.dumps({"success": False, "error": "Faceting note not found"}))
                sys.exit(1)

            ph_id, created = _ensure_phase_note(tx, args.investigation, "analysis")

            already = list(tx.query(
                f'match $ph isa scilit-investigation-phase, has id "{escape_string(ph_id)}"; '
                f'$fn isa scilit-faceting-note, has id "{escape_string(args.faceting_note)}"; '
                f'(parent-note: $ph, child-note: $fn) isa alh-note-threading; '
                f'fetch {{ "id": $fn.id }};'
            ).resolve())
            if not already:
                tx.query(
                    f'match $ph isa scilit-investigation-phase, has id "{escape_string(ph_id)}"; '
                    f'$fn isa scilit-faceting-note, has id "{escape_string(args.faceting_note)}"; '
                    f'insert (phase: $ph, faceting: $fn) isa scilit-phase-faceting;'
                ).resolve()
            tx.commit()

    print(json.dumps({
        "success": True,
        "investigation": args.investigation,
        "analysis_phase_id": ph_id,
        "faceting_note": args.faceting_note,
        "linked": not already,
        "phase_created": created,
    }, indent=2))


def cmd_set_status(args):
    """Set an investigation's lifecycle status."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            inv = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.investigation)}"; '
                f'fetch {{ "id": $inv.id }};'
            ).resolve())
            if not inv:
                print(json.dumps({"success": False, "error": "Investigation not found"}))
                sys.exit(1)
            _set_investigation_status(tx, args.investigation, args.status)
            tx.commit()
    print(json.dumps({
        "success": True,
        "investigation": args.investigation,
        "status": args.status,
    }, indent=2))


# =============================================================================
# DEEP-DIVE (single-paper) INVESTIGATIONS
# =============================================================================
# A `deep-dive` investigation resolves every claim in one focal scilit-paper down
# to primary evidence (tracing cited papers) and surveys how citing papers received
# those claims. It reuses the investigation spine (phases, status) but its aboutness
# subject is a single scilit-paper (not a corpus), and it threads scilit-claim /
# scilit-citation-impact notes under it. Source/citing papers are real scilit-paper
# entities, found-or-ingested on trace, linked via alh-aboutness.

CLAIM_TYPES = ["primary", "secondary", "peripheral"]
EVIDENCE_TYPES = ["experimental", "observational", "computational",
                  "review", "theoretical", "anecdotal"]
IMPACT_TYPES = ["supports", "refutes", "extends", "nuances", "uses", "unrelated"]


def _find_or_ingest_paper(driver, doi=None, pmid=None, paper_id=None):
    """Resolve a paper to a scilit-paper id, ingesting it if absent.

    Returns the scilit-paper id, or None if it could not be resolved.
    - paper_id: verify it exists and return it.
    - doi/pmid: return the existing paper, else fetch + insert a new one.
    """
    if paper_id:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            found = list(tx.query(
                f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                f'fetch {{ "id": $p.id }};'
            ).resolve())
        return found[0]["id"] if found else None

    if doi:
        doi = doi.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]
        existing = paper_exists(driver, doi=doi)
        if existing:
            return existing
        paper = fetch_by_doi_openalex(doi)
        if not paper or not paper.get("title"):
            paper = fetch_by_doi_ncbi(doi)
        if not paper:
            return None
        return insert_paper(driver, paper)

    if pmid:
        pmid = str(pmid).strip()
        existing = paper_exists(driver, pmid=pmid)
        if existing:
            return existing
        epmc_paper = fetch_by_pmid_epmc(pmid)
        if epmc_paper:
            return insert_epmc_paper(driver, epmc_paper, None)
        papers = search_pubmed(f"{pmid}[uid]", max_results=1)
        if papers:
            return insert_paper(driver, papers[0])
        return None

    return None


def _resolve_paper_arg(driver, paper_arg):
    """Resolve a --paper / --source / --citing argument (a scilit-paper id or a DOI)."""
    if paper_arg.startswith("scilit-paper") or paper_arg.startswith("scilit-preprint"):
        return _find_or_ingest_paper(driver, paper_id=paper_arg)
    return _find_or_ingest_paper(driver, doi=paper_arg)


def cmd_add_synthesized_claim(args):
    """Add a scilit-synthesized-claim (cross-paper, analysis) to an investigation."""
    if args.type not in CLAIM_TYPES:
        print(json.dumps({"success": False,
                          "error": f"Invalid claim type. Use one of: {', '.join(CLAIM_TYPES)}"}))
        sys.exit(1)
    claim_id = generate_id("scsynth")
    ts = get_timestamp()
    name = args.statement[:60]
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            inv = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.investigation)}"; '
                f'fetch {{ "id": $inv.id }};'
            ).resolve())
            if not inv:
                print(json.dumps({"success": False, "error": "Investigation not found"}))
                sys.exit(1)
            tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.investigation)}"; '
                f'insert $cl isa scilit-synthesized-claim, has id "{claim_id}", '
                f'has name "{escape_string(name)}", '
                f'has scilit-claim-type "{escape_string(args.type)}", '
                f'has scilit-claim-statement "{escape_string(args.statement)}", '
                f'has created-at {ts}; '
                f'(investigation: $inv, synthesized-claim: $cl) isa scilit-investigation-synthesized-claim;'
            ).resolve()
            tx.commit()
    print(json.dumps({"success": True, "synthesized_claim_id": claim_id,
                      "investigation": args.investigation, "type": args.type,
                      "statement": args.statement}, indent=2))


def cmd_add_evidence(args):
    """Add a scilit-evidence WARRANT supporting a synthesized-claim: a reasoned argument
    (content) + confidence score, grounded in one or more reported-claims (--grounds)."""
    ev_id = generate_id("scev")
    ts = get_timestamp()
    try:
        confidence = float(args.confidence)
    except (TypeError, ValueError):
        print(json.dumps({"success": False, "error": "--confidence must be a number 0..1"}))
        sys.exit(1)
    ground_ids = [g.strip() for g in (args.grounds or "").split(",") if g.strip()]
    name = args.argument[:60]
    type_clause = (f', has scilit-evidence-type "{escape_string(args.evidence_type)}"'
                   if getattr(args, "evidence_type", None) else "")
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            claim = list(tx.query(
                f'match $cl isa scilit-synthesized-claim, has id "{escape_string(args.claim_id)}"; '
                f'fetch {{ "id": $cl.id }};').resolve())
        if not claim:
            print(json.dumps({"success": False, "error": "Synthesized-claim not found"}))
            sys.exit(1)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(
                f'match $cl isa scilit-synthesized-claim, has id "{escape_string(args.claim_id)}"; '
                f'insert $ev isa scilit-evidence, has id "{ev_id}", has name "{escape_string(name)}", '
                f'has content "{escape_string(args.argument)}", has confidence {confidence}{type_clause}, '
                f'has created-at {ts}; '
                f'(synthesized-claim: $cl, evidence: $ev) isa scilit-claim-evidence;'
            ).resolve()
            linked = 0
            for gid in ground_ids:
                rc = list(tx.query(
                    f'match $rc isa scilit-claim, has id "{escape_string(gid)}"; '
                    f'fetch {{ "id": $rc.id }};').resolve())
                if rc:
                    tx.query(
                        f'match $ev isa scilit-evidence, has id "{ev_id}"; '
                        f'$rc isa scilit-claim, has id "{escape_string(gid)}"; '
                        f'insert (evidence: $ev, ground-claim: $rc) isa scilit-evidence-grounds;'
                    ).resolve()
                    linked += 1
            # ground the warrant in the structured data: the template instances it rests on
            inst_ids = [i.strip() for i in (getattr(args, "instances", None) or "").split(",") if i.strip()]
            inst_linked = 0
            for iid in inst_ids:
                ie = list(tx.query(
                    f'match $i isa kefed-instance, has id "{escape_string(iid)}"; fetch {{ "id": $i.id }};').resolve())
                if ie:
                    tx.query(
                        f'match $ev isa scilit-evidence, has id "{ev_id}"; '
                        f'$i isa kefed-instance, has id "{escape_string(iid)}"; '
                        f'insert (evidence: $ev, grounding-instance: $i) isa scilit-evidence-instance;'
                    ).resolve()
                    inst_linked += 1
            tx.commit()
    print(json.dumps({"success": True, "evidence_id": ev_id, "synthesized_claim_id": args.claim_id,
                      "confidence": confidence, "grounds_linked": linked,
                      "instances_linked": inst_linked}, indent=2))


def _paper_has_fulltext(driver, paper_id):
    """True iff the paper has an alh-representation to a fulltext artifact
    (an alh-artifact bearing scilit-fulltext-kind, e.g. scilit-pdf-fulltext /
    scilit-jats-fulltext). This is the marker that fetch-pdf/full-text ingest ran."""
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        rows = list(tx.query(
            f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; '
            f'$a isa alh-artifact, has scilit-fulltext-kind $k; '
            f'(alh-artifact: $a, referent: $p) isa alh-representation; '
            f'fetch {{ "k": $k }};').resolve())
    return bool(rows)


def cmd_create_bundle(args):
    """Create a per-paper sensemaking bundle for a paper, in an investigation's sensemaking
    stage (a single-paper KQED run persists into THIS, not its own investigation)."""
    iteration = int(getattr(args, "iteration", 1) or 1)
    with get_driver() as driver:
        paper_id = _resolve_paper_arg(driver, args.paper)
        if not paper_id:
            print(json.dumps({"success": False, "error": f"Could not resolve paper: {args.paper}"}))
            sys.exit(1)
        # KQED ingestion requires the paper's full text -- you cannot sense-make what you
        # haven't got. Refuse until fetch-pdf has attached a fulltext artifact.
        if not _paper_has_fulltext(driver, paper_id):
            print(json.dumps({"success": False,
                              "error": f"KQED ingestion blocked: paper {paper_id} has no full text. "
                                       f"Run 'fetch-pdf --id {paper_id}' (or 'fetch-pdf --id {paper_id} "
                                       f"--file <pdf>') first."}))
            sys.exit(1)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            inv = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.investigation)}"; '
                f'fetch {{ "id": $inv.id }};').resolve())
            if not inv:
                print(json.dumps({"success": False, "error": "Investigation not found"}))
                sys.exit(1)
            ph_id, _ = _ensure_phase_note(tx, args.investigation, "sensemaking", iteration=iteration)
            bundle_id = generate_id("scsense")
            ts = get_timestamp()
            name = (args.name or f"Sensemaking: {paper_id}")[:120]
            tx.query(
                f'match $ph isa scilit-investigation-phase, has id "{escape_string(ph_id)}"; '
                f'$p isa scilit-paper, has id "{escape_string(paper_id)}"; '
                f'insert $b isa scilit-paper-sensemaking, has id "{bundle_id}", '
                f'has name "{escape_string(name)}", has created-at {ts}; '
                f'(phase: $ph, sensemaking: $b) isa scilit-phase-sensemaking; '
                f'(sensemaking: $b, paper: $p) isa scilit-sensemaking-paper;'
            ).resolve()
            tx.commit()
    print(json.dumps({"success": True, "bundle_id": bundle_id, "paper": paper_id,
                      "investigation": args.investigation, "iteration": iteration}, indent=2))


# Observation source-locator label grammar (see docs/observation-source-labeling.md).
# A source token = optional 'S' (supplemental/supporting-info) + a type letter
# (F figure | T table | E experiment | X free-text) + optional number + optional
# panel letters (ranges allowed, e.g. D-F). Multiple loci join with '+'. Legacy
# SIRT3-seed form used a bare figure digit (O4DF == OF4DF), still accepted.
_SRCLBL_TOKEN = re.compile(r'^S?[FTEX]\d*(?:[A-Z](?:-[A-Z])?)*$')
_SRCLBL_LEGACY = re.compile(r'^\d+(?:[A-Z](?:-[A-Z])?)*$')


def validate_source_label(label):
    """Loosely validate an observation source-locator label.

    Returns (ok: bool, note: str | None). This is a *convention*, not a schema
    constraint: a note is advisory and the caller should still store the label
    (warn, don't block). See docs/observation-source-labeling.md for the grammar.
    """
    if not label or label[0] != 'O':
        return False, "source-label should start with 'O' (observation)"
    body = label[1:]
    if not body:
        return False, "source-label needs at least one source token after 'O'"
    for tok in body.split('+'):
        if _SRCLBL_TOKEN.match(tok):
            continue
        if _SRCLBL_LEGACY.match(tok):
            return True, (f"token '{tok}' uses the legacy bare-figure form; prefer explicit "
                          f"'F{tok}' (main figure). See docs/observation-source-labeling.md")
        return False, (f"token '{tok}' is not a valid source locator "
                       f"(expected e.g. F4DF, SF3B, T2, E5, X). See docs/observation-source-labeling.md")
    return True, None


def cmd_add_observation(args):
    """Add a scilit-observation (measurement-in-context) to a sensemaking bundle.

    Inserts a scilit-observation (knowledge-level, bio-scale) threaded under the
    scilit-paper-sensemaking bundle via scilit-sensemaking-observation.

    The KEfED experiment frame (kefed-model + ooevv-variable bigraph) is authored
    SEPARATELY via cmd_add_experiment / cmd_add_variable; this handler no longer
    builds it. The --experiment-type and --variables flags are accepted but ignored
    so that existing call sites do not error on unrecognised arguments.
    """
    obs_id = generate_id("scobs")
    ts = get_timestamp()
    # A source-locator label (e.g. OF4DF) becomes the observation's `name` verbatim
    # so its evidence locus is legible at a glance; the full text always lives in
    # `content`. Absent a label, fall back to --name or a truncated statement.
    label = getattr(args, "source_label", None)
    if label:
        ok, note = validate_source_label(label)
        if note:
            print(f"[warn] source-label: {note}", file=sys.stderr)
        name = label
    else:
        name = (args.name or args.statement)[:60]
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            b = list(tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'fetch {{ "id": $b.id }};').resolve())
            if not b:
                print(json.dumps({"success": False, "error": "Bundle not found"}))
                sys.exit(1)
            tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'insert $o isa scilit-observation, has id "{obs_id}", has name "{escape_string(name)}", '
                f'has content "{escape_string(args.statement)}", '
                f'has scilit-knowledge-level "{escape_string(args.knowledge_level)}", '
                f'has scilit-bio-scale "{escape_string(args.bio_scale)}", has created-at {ts}; '
                f'(sensemaking: $b, observation: $o) isa scilit-sensemaking-observation;'
            ).resolve()
            tx.commit()
    out = {"success": True, "observation_id": obs_id, "bundle": args.bundle}
    if label:
        out["source_label"] = label
    print(json.dumps(out, indent=2))


def cmd_add_mechanism(args):
    """Add a System-3 mechanistic edge (bioentity --[mech-type]--> bioentity) scoped to a
    sensemaking bundle. Bioentities are found-or-created by name."""
    ts = get_timestamp()

    def _ensure_bioentity(tx, label):
        rows = list(tx.query(
            f'match $e isa scilit-bioentity, has name "{escape_string(label)}"; '
            f'fetch {{ "id": $e.id }};').resolve())
        if rows:
            return rows[0]["id"]
        eid = generate_id("scbe")
        tx.query(
            f'insert $e isa scilit-bioentity, has id "{eid}", has name "{escape_string(label)}", '
            f'has created-at {ts};').resolve()
        return eid

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            b = list(tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'fetch {{ "id": $b.id }};').resolve())
            if not b:
                print(json.dumps({"success": False, "error": "Bundle not found"}))
                sys.exit(1)
            src = _ensure_bioentity(tx, args.source)
            tgt = _ensure_bioentity(tx, args.target)
            conf = ""
            if getattr(args, "confidence", None):
                try:
                    conf = f', has confidence {float(args.confidence)}'
                except ValueError:
                    conf = ""
            claim_match = (f'$cl isa scilit-claim, has id "{escape_string(args.claim)}"; '
                           if getattr(args, "claim", None) else "")
            claim_insert = ('(claim: $cl, mechanism: $ml) isa scilit-claim-mechanism; '
                            if getattr(args, "claim", None) else "")
            tx.query(
                f'match $s isa scilit-bioentity, has id "{src}"; $t isa scilit-bioentity, has id "{tgt}"; '
                f'$b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; {claim_match}'
                f'insert $ml isa scilit-mechanistic-link, links (mech-source: $s, mech-target: $t), '
                f'has scilit-mech-type "{escape_string(args.type)}"{conf}; '
                f'(sensemaking: $b, mechanism: $ml) isa scilit-sensemaking-mechanism; {claim_insert}'
            ).resolve()
            tx.commit()
    print(json.dumps({"success": True, "source": src, "target": tgt, "type": args.type,
                      "bundle": args.bundle, "claim": getattr(args, "claim", None)}, indent=2))


def cmd_ground_bundle(args):
    """Ground a bundle's KEfED variables and mechanistic bioentities to real ontology terms
    (OLS4/HGNC) under the investigation's grounding policy, persisting curie + label + state +
    confidence. CURIEs are looked up, never invented; low-confidence -> needs-review."""
    import ontology_grounding as G
    bid = escape_string(args.bundle)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            pol = list(tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{bid}"; '
                f'(phase: $ph, sensemaking: $b) isa scilit-phase-sensemaking; '
                f'(iteration: $it, stage: $ph) isa scilit-iteration-stage; '
                f'(investigation: $inv, iteration: $it) isa scilit-investigation-iteration; '
                f'(investigation: $inv, policy: $pp) isa scilit-investigation-grounding; '
                f'fetch {{ "content": $pp.content }};').resolve())
            if not pol or not pol[0].get("content"):
                print(json.dumps({"success": False, "error": "No grounding policy on this bundle's investigation"}))
                sys.exit(1)
            policy = json.loads(pol[0]["content"])
            onts = []
            for cfg in policy.get("kinds", {}).values():
                for o in cfg.get("ontologies", []):
                    if o not in onts:
                        onts.append(o)
            thr = float(policy.get("confidence_threshold", 0.5))
            reground = bool(getattr(args, "reground", False))
            gfilter_v = "" if reground else "not { $v has scilit-grounding-state $g; };"
            gfilter_e = "" if reground else "not { $e has scilit-grounding-state $g; };"
            # collect targets: (typelabel, id, name)
            # Variables: bundle -> scilit-sensemaking-experiment -> (kefed-model directly, OR
            #            kefed-instance -> kefed-instance-of -> kefed-model) -> kefed-model-element
            #            -> kefed-model-node -> kefed-node-variable -> ooevv-variable.
            # (Templates-first path: the bundle's experiment is a kefed-instance whose variables
            # live on the template model's nodes; the add-experiment path links a kefed-model directly.)
            targets = {}
            var_rows = list(tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{bid}"; '
                f'(sensemaking: $b, experiment: $x) isa scilit-sensemaking-experiment; '
                f'{{ $x isa kefed-model; (model: $x, element: $n) isa kefed-model-element; }} '
                f'or {{ $x isa kefed-instance; (instance: $x, model: $mm) isa kefed-instance-of; '
                f'(model: $mm, element: $n) isa kefed-model-element; }}; '
                f'(node: $n, variable: $v) isa kefed-node-variable; '
                f'$v isa ooevv-variable, has name $nm; '
                f'{gfilter_v} '
                f'fetch {{ "id": $v.id, "name": $nm }};').resolve())
            for r in var_rows:
                targets[r["id"]] = ("ooevv-variable", r["name"])
            for role in ("mech-source", "mech-target"):
                ent_rows = list(tx.query(
                    f'match $b isa scilit-paper-sensemaking, has id "{bid}"; '
                    f'(sensemaking: $b, mechanism: $ml) isa scilit-sensemaking-mechanism; '
                    f'$ml links ({role}: $e); $e has name $nm; '
                    f'{gfilter_e} '
                    f'fetch {{ "id": $e.id, "name": $nm }};').resolve())
                for r in ent_rows:
                    targets[r["id"]] = ("scilit-bioentity", r["name"])

    limit = getattr(args, "limit", None)
    items = list(targets.items())
    if limit:
        items = items[: int(limit)]
    import re
    # A gene/protein symbol is short, space-free, and carries an uppercase letter or digit
    # (FOXM1, AKT, PLK1, BCL-xL). Only such mentions may query HGNC, and only HGNC EXACT
    # symbol fetches are accepted - HGNC's free-text search returns spurious genes for any
    # phrase at high confidence (a hallucination source), so it is filtered out.
    def _is_symbol(m):
        return bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{1,9}', m or '')) and any(c.isupper() or c.isdigit() for c in m)
    summary = {"grounded": 0, "needs-review": 0, "ungrounded": 0, "errors": 0, "results": []}
    with get_driver() as driver:
        for eid, (typ, name) in items:
            try:
                srcs = onts + (["HGNC"] if _is_symbol(name) else [])
                cands = G.search_sources(name, srcs) or []
                cands = [c for c in cands if not (c.get("source") == "HGNC" and c.get("match_type") != "exact")]
                best = G._select_best(cands) if cands else None
                if not best:
                    curie, label, conf, state = "", name, 0.0, "ungrounded"
                else:
                    curie = G.normalize_curie(best.get("curie", "")) or ""
                    label = best.get("label", name)
                    conf = float(best.get("confidence", 0.0))
                    state = "grounded" if conf >= thr else ("needs-review" if conf > 0 else "ungrounded")
            except Exception as exc:
                summary["errors"] += 1
                summary["results"].append({"name": name, "error": str(exc)[:80]})
                continue
            summary[state] = summary.get(state, 0) + 1
            summary["results"].append({"name": name, "curie": curie, "confidence": round(conf, 2), "state": state})
            attrs = (f'has scilit-grounding-state "{escape_string(state)}", '
                     f'has scilit-grounding-confidence {conf}')
            if curie:
                attrs += f', has scilit-curie "{escape_string(curie)}"'
            if label:
                attrs += f', has scilit-grounding-label "{escape_string(label)}"'
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                if reground:
                    for a in ("scilit-grounding-state", "scilit-grounding-confidence",
                              "scilit-curie", "scilit-grounding-label"):
                        tx.query(f'match $x isa {typ}, has id "{escape_string(eid)}", has {a} $v; '
                                 f'delete has $v of $x;').resolve()
                tx.query(f'match $x isa {typ}, has id "{escape_string(eid)}"; insert $x {attrs};').resolve()
                tx.commit()
    summary["success"] = True
    summary["bundle"] = args.bundle
    summary["total"] = len(items)
    print(json.dumps(summary, indent=2))


def cmd_add_reported_claim(args):
    """Add a scilit-claim (asserted within the paper) to a sensemaking bundle.
    Support: --cites <paper ids> (citation hinges) and/or --observations <obs ids> (internal)."""
    if args.type not in CLAIM_TYPES:
        print(json.dumps({"success": False,
                          "error": f"Invalid claim type. Use one of: {', '.join(CLAIM_TYPES)}"}))
        sys.exit(1)
    claim_id = generate_id("screp")
    ts = get_timestamp()
    name = args.statement[:60]
    cite_ids = [c.strip() for c in (getattr(args, "cites", "") or "").split(",") if c.strip()]
    obs_ids = [o.strip() for o in (getattr(args, "observations", "") or "").split(",") if o.strip()]
    role_clause = (f', has scilit-rhetorical-role "{escape_string(args.rhetorical_role)}"'
                   if getattr(args, "rhetorical_role", None) else "")
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            b = list(tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'fetch {{ "id": $b.id }};').resolve())
            if not b:
                print(json.dumps({"success": False, "error": "Bundle not found"}))
                sys.exit(1)
            tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'insert $cl isa scilit-claim, has id "{claim_id}", has name "{escape_string(name)}", '
                f'has scilit-claim-type "{escape_string(args.type)}", '
                f'has scilit-claim-statement "{escape_string(args.statement)}"{role_clause}, has created-at {ts}; '
                f'(sensemaking: $b, reported-claim: $cl) isa scilit-sensemaking-reported-claim;'
            ).resolve()
            for oid in obs_ids:
                tx.query(
                    f'match $cl isa scilit-claim, has id "{claim_id}"; '
                    f'$o isa scilit-observation, has id "{escape_string(oid)}"; '
                    f'insert (claim: $cl, observation: $o) isa scilit-claim-observation;').resolve()
            for pid in cite_ids:
                tx.query(
                    f'match $cl isa scilit-claim, has id "{claim_id}"; '
                    f'$t isa scilit-paper, has id "{escape_string(pid)}"; '
                    f'insert (hinging-claim: $cl, hinged-to: $t) isa scilit-hinge;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "reported_claim_id": claim_id, "bundle": args.bundle,
                      "cites": cite_ids, "observations": obs_ids}, indent=2))


def cmd_link_claim_observation(args):
    """Link an already-curated reported-claim to a supporting observation (scilit-claim-observation),
    idempotently. Use to ground existing claims in their evidence without recreating them."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            ok = list(tx.query(
                f'match $c isa scilit-claim, has id "{escape_string(args.claim)}"; '
                f'$o isa scilit-observation, has id "{escape_string(args.observation)}"; '
                f'fetch {{ "c": $c.id }};').resolve())
            if not ok:
                print(json.dumps({"success": False, "error": "claim or observation not found"})); sys.exit(1)
            exists = list(tx.query(
                f'match $c isa scilit-claim, has id "{escape_string(args.claim)}"; '
                f'$o isa scilit-observation, has id "{escape_string(args.observation)}"; '
                f'(claim: $c, observation: $o) isa scilit-claim-observation; fetch {{ "c": $c.id }};').resolve())
            if not exists:
                tx.query(
                    f'match $c isa scilit-claim, has id "{escape_string(args.claim)}"; '
                    f'$o isa scilit-observation, has id "{escape_string(args.observation)}"; '
                    f'insert (claim: $c, observation: $o) isa scilit-claim-observation;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "claim": args.claim, "observation": args.observation,
                      "already_linked": bool(exists)}))


def cmd_link_datum_observation(args):
    """Link an observation to a data row it is the measurement-in-context of (kefed-datum-observation),
    idempotently. Completes the traceability chain claim -> observation -> datum -> instance -> model."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            ok = list(tx.query(
                f'match $d isa kefed-row, has id "{escape_string(args.datum)}"; '
                f'$o isa scilit-observation, has id "{escape_string(args.observation)}"; '
                f'fetch {{ "d": $d.id }};').resolve())
            if not ok:
                print(json.dumps({"success": False, "error": "datum or observation not found"})); sys.exit(1)
            exists = list(tx.query(
                f'match $d isa kefed-row, has id "{escape_string(args.datum)}"; '
                f'$o isa scilit-observation, has id "{escape_string(args.observation)}"; '
                f'(datum: $d, observation: $o) isa kefed-datum-observation; fetch {{ "d": $d.id }};').resolve())
            if not exists:
                tx.query(
                    f'match $d isa kefed-row, has id "{escape_string(args.datum)}"; '
                    f'$o isa scilit-observation, has id "{escape_string(args.observation)}"; '
                    f'insert (datum: $d, observation: $o) isa kefed-datum-observation;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "datum": args.datum, "observation": args.observation,
                      "already_linked": bool(exists)}))


def _paper_fulltext(tx, paper_id):
    """Return (artifact_id, normalized_full_text) for a paper's scilit-pdf-fulltext, or (None, None).
    Reads the .txt rendition from the per-paper cache dir."""
    rows = list(tx.query(
        f'match $p isa scilit-paper, has id "{escape_string(paper_id)}"; $a isa scilit-pdf-fulltext; '
        f'(alh-artifact: $a, referent: $p) isa alh-representation; '
        f'fetch {{ "id": $a.id, "cp": $a.cache-path }};').resolve())
    if not rows:
        return None, None
    aid = rows[0]["id"]
    cp = rows[0].get("cp")
    cache = str(_get_cache_dir())
    path = os.path.join(cache, cp) if cp else None
    if not path or not os.path.exists(path):
        # deterministic fallback: fulltext/<pid>/<artifact>.txt
        cand = os.path.join(cache, "fulltext", paper_id, f"{aid}.txt")
        path = cand if os.path.exists(cand) else None
    text = open(path, encoding="utf-8").read() if path else None
    return aid, text


def cmd_anchor_note(args):
    """Span-anchor a rhetorical note (claim/observation/gap) to a verbatim quote in the paper's full
    text: create a scilit-sentence fragment (with char offset+length) on the full-text artifact and
    link the note to it via alh-derivation. The --quote must appear (whitespace-normalized) in the
    cached full text; the offset is computed, so the claim traces to the exact supporting sentence(s)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            note = list(tx.query(
                f'match $n isa alh-information-content-entity, has id "{escape_string(args.note)}"; '
                f'fetch {{ "id": $n.id }};').resolve())
            if not note:
                print(json.dumps({"success": False, "error": "note not found"})); sys.exit(1)
            aid, full = _paper_fulltext(tx, args.paper)
            if not aid:
                print(json.dumps({"success": False, "error": "no full-text artifact for paper"})); sys.exit(1)
            quote = args.quote
            offset, length = -1, len(quote)
            if full:
                norm = re.sub(r"\s+", " ", full)
                needle = re.sub(r"\s+", " ", quote).strip()
                i = norm.find(needle)
                if i < 0 and len(needle) > 40:
                    i = norm.find(needle[:40])
                offset, length = i, len(needle)
            if offset < 0 and not getattr(args, "force", False):
                print(json.dumps({"success": False, "error": "quote not found in full text; refine --quote or pass --force"}))
                sys.exit(1)
            fid = generate_id("frag"); ts = get_timestamp()
            tx.query(f'insert $f isa scilit-sentence, has id "{fid}", has content "{escape_string(quote)}", '
                     f'has offset {offset}, has length {length}, has created-at {ts};').resolve()
            tx.query(f'match $a isa alh-artifact, has id "{escape_string(aid)}"; $f isa alh-fragment, has id "{fid}"; '
                     f'insert (whole: $a, part: $f) isa alh-fragmentation;').resolve()
            tx.query(f'match $n isa alh-information-content-entity, has id "{escape_string(args.note)}"; '
                     f'$f isa alh-fragment, has id "{fid}"; '
                     f'insert (derivative: $n, derived-from-source: $f) isa alh-derivation, has created-at {ts};').resolve()
            tx.commit()
    print(json.dumps({"success": True, "note": args.note, "fragment": fid, "offset": offset, "located": offset >= 0}))


def cmd_add_reported_gap(args):
    """Add a scilit-gap (a gap stated within the paper) to a sensemaking bundle."""
    gap_id = generate_id("scgap")
    ts = get_timestamp()
    name = args.statement[:60]
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            b = list(tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'fetch {{ "id": $b.id }};').resolve())
            if not b:
                print(json.dumps({"success": False, "error": "Bundle not found"}))
                sys.exit(1)
            tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'insert $g isa scilit-gap, has id "{gap_id}", has name "{escape_string(name)}", '
                f'has content "{escape_string(args.statement)}", '
                f'has scilit-knowledge-goal "{escape_string(args.goal)}", has created-at {ts}; '
                f'(sensemaking: $b, reported-gap: $g) isa scilit-sensemaking-reported-gap;'
            ).resolve()
            tx.commit()
    print(json.dumps({"success": True, "reported_gap_id": gap_id, "bundle": args.bundle}, indent=2))


def cmd_show_bundle(args):
    """Show one per-paper sensemaking bundle in full (paper, observations with KEfED frames,
    reported-claims with citation hinges, reported-gaps)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            bundle = _load_bundle(tx, args.id)
    if bundle is None:
        print(json.dumps({"success": False, "error": "Bundle not found"}))
        sys.exit(1)
    print(json.dumps({"success": True, **bundle}, indent=2))


# =============================================================================
# OOEVV / KEfED protocol-graph curation verbs
# =============================================================================

def _require_definition(args, kind):
    """Curation standard: a NEW OOEVV element must carry a plain-English, undergraduate-level
    definition. Reusing an existing term skips this (no creation happens)."""
    if not (getattr(args, "definition", None) or "").strip():
        print(json.dumps({"success": False, "error": (
            f"--definition is required to CREATE a new {kind} (curation standard: an "
            f"undergraduate-level explanation of what it is and what it does). "
            f"If this term already exists, reuse it instead.")}))
        sys.exit(1)


def _grounding_clause(args):
    """Build a grounding attribute clause. Correctness-gated: a curie is recorded ONLY when supplied
    (the caller attaches it only after verifying the term's definition matches). Otherwise the element
    is explicitly marked 'ungrounded' (no curie). Never fabricate a grounding."""
    curie = getattr(args, "curie", None)
    if curie:
        c = f', has scilit-curie "{escape_string(curie)}", has scilit-grounding-state "grounded", has scilit-grounding-confidence 1.0'
        if getattr(args, "grounding_label", None):
            c += f', has scilit-grounding-label "{escape_string(args.grounding_label)}"'
        return c, True
    return ', has scilit-grounding-state "ungrounded"', False


def cmd_ensure_quality(args):
    """Find-or-create a reusable curated ooevv-quality (the generic measurand / semantic anchor) by name.
    Grounding is correctness-gated: pass --curie ONLY for a verified, definition-matching ontology term;
    otherwise the quality is recorded 'ungrounded' with its local definition."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            ex = list(tx.query(
                f'match $q isa ooevv-quality, has name "{escape_string(args.name)}"; '
                f'fetch {{ "id": $q.id }};').resolve())
        if ex:
            print(json.dumps({"success": True, "quality_id": ex[0]["id"], "reused": True}))
            return
        _require_definition(args, "quality")
        qid = generate_id("scqual")
        defn = f', has ooevv-definition "{escape_string(args.definition)}"' if getattr(args, "definition", None) else ""
        lf = f', has ooevv-long-form "{escape_string(args.long_form)}"' if getattr(args, "long_form", None) else ""
        gc, grounded = _grounding_clause(args)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'insert $q isa ooevv-quality, has id "{qid}", has name "{escape_string(args.name)}"{defn}{lf}{gc};').resolve()
            tx.commit()
    print(json.dumps({"success": True, "quality_id": qid, "reused": False, "grounded": grounded}))


_SCALE_TYPES = {"nominal": "ooevv-nominal-scale", "binary": "ooevv-binary-scale",
                "ordinal": "ooevv-ordinal-scale", "numeric": "ooevv-numeric-scale",
                "file": "ooevv-file-scale", "composite": "ooevv-composite-scale"}


def _scale_attr_clause(args):
    """Build the scale-attribute clause (unit/min/max/allowed-value/named-rank) from args."""
    sattrs = []
    if getattr(args, "unit", None):
        sattrs.append(f'has ooevv-unit "{escape_string(args.unit)}"')
    if args.scale_type == "numeric":
        if getattr(args, "min", None) is not None: sattrs.append(f'has ooevv-min {float(args.min)}')
        if getattr(args, "max", None) is not None: sattrs.append(f'has ooevv-max {float(args.max)}')
    allowed = [a.strip() for a in (getattr(args, "values", "") or "").split("|") if a.strip()]
    if args.scale_type in ("nominal", "binary"):
        sattrs += [f'has ooevv-allowed-value "{escape_string(a)}"' for a in allowed]
    if args.scale_type == "ordinal":
        sattrs += [f'has ooevv-named-rank "{escape_string(a)}"' for a in allowed]  # order preserved
    return (", " + ", ".join(sattrs)) if sattrs else ""


def cmd_ensure_value_spec(args):
    """Find-or-create a NAMED, REUSABLE value-specification (ooevv-scale) canonical to a quality,
    linked via ooevv-quality-scale. Idempotent by (quality, name). A quality thus enumerates its
    canonical value-specs (e.g. age -> {ordinal young<old} + {numeric days})."""
    if args.scale_type not in _SCALE_TYPES:
        print(json.dumps({"success": False, "error": f"--scale-type must be one of {list(_SCALE_TYPES)}"})); sys.exit(1)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            q = list(tx.query(f'match $q isa ooevv-quality, has id "{escape_string(args.quality)}"; fetch {{ "id": $q.id }};').resolve())
            if not q:
                print(json.dumps({"success": False, "error": f"Quality not found: {args.quality}"})); sys.exit(1)
            ex = list(tx.query(
                f'match $q isa ooevv-quality, has id "{escape_string(args.quality)}"; '
                f'$s isa ooevv-scale, has name "{escape_string(args.name)}"; '
                f'(quality: $q, scale: $s) isa ooevv-quality-scale; fetch {{ "id": $s.id }};').resolve())
        if ex:
            print(json.dumps({"success": True, "value_spec_id": ex[0]["id"], "reused": True}))
            return
        _require_definition(args, "value-spec")
        vsid = generate_id("scvspec")
        defn = f', has ooevv-definition "{escape_string(args.definition)}"' if getattr(args, "definition", None) else ""
        lf = f', has ooevv-long-form "{escape_string(args.long_form)}"' if getattr(args, "long_form", None) else ""
        gc, grounded = _grounding_clause(args)
        sclause = _scale_attr_clause(args)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(
                f'match $q isa ooevv-quality, has id "{escape_string(args.quality)}"; '
                f'insert $s isa {_SCALE_TYPES[args.scale_type]}, has id "{vsid}", '
                f'has name "{escape_string(args.name)}"{defn}{lf}{gc}{sclause}; '
                f'(quality: $q, scale: $s) isa ooevv-quality-scale;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "value_spec_id": vsid, "reused": False, "grounded": grounded}))


def cmd_list_value_specs(args):
    """List value-specifications (ooevv-scale linked to a quality), optionally for one quality."""
    qfilter = f', has id "{escape_string(args.quality)}"' if getattr(args, "quality", None) else ""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            rows = list(tx.query(
                f'match $q isa ooevv-quality{qfilter}, has name $qn; '
                f'(quality: $q, scale: $s) isa ooevv-quality-scale; '
                f'$s has name $sn; '
                f'fetch {{ "quality": $qn, "quality_id": $q.id, "value_spec": $sn, "value_spec_id": $s.id, '
                f'"grounding": $s.scilit-grounding-state, "curie": $s.scilit-curie }};').resolve())
    m = (getattr(args, "match", None) or "").lower()
    out = [r for r in rows if not m or m in str(r.get("value_spec", "")).lower() or m in str(r.get("quality", "")).lower()]
    print(json.dumps({"success": True, "count": len(out), "value_specs": out}, indent=2))


def cmd_ensure_entity(args):
    """Find-or-create a reusable curated entity (scilit-entity) by name + kind (the specificity/material target)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            ex = list(tx.query(
                f'match $e isa scilit-entity, has name "{escape_string(args.name)}"; '
                f'fetch {{ "id": $e.id }};').resolve())
        if ex:
            print(json.dumps({"success": True, "entity_id": ex[0]["id"], "reused": True}))
            return
        _require_definition(args, "entity")
        eid = generate_id("scent")
        ts = get_timestamp()
        kind = f', has scilit-entity-kind "{escape_string(args.kind)}"' if getattr(args, "kind", None) else ""
        defn = f', has ooevv-definition "{escape_string(args.definition)}"' if getattr(args, "definition", None) else ""
        lf = f', has ooevv-long-form "{escape_string(args.long_form)}"' if getattr(args, "long_form", None) else ""
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'insert $e isa scilit-entity, has id "{eid}", has name "{escape_string(args.name)}"{kind}{defn}{lf}, '
                     f'has created-at {ts};').resolve()
            tx.commit()
    print(json.dumps({"success": True, "entity_id": eid, "reused": False}))


def _model_elementset(tx, model_id, model_name=""):
    """Within a WRITE transaction: return the element-set id linked to model_id via
    kefed-model-elementset, creating and linking a fresh ooevv-element-set if absent."""
    rows = list(tx.query(
        f'match $m isa kefed-model, has id "{escape_string(model_id)}"; '
        f'(model: $m, element-set: $es) isa kefed-model-elementset; '
        f'fetch {{"esid": $es.id}};').resolve())
    if rows:
        return rows[0]["esid"]
    eset_id = generate_id("eset")
    label = escape_string(model_name or model_id)
    tx.query(
        f'match $m isa kefed-model, has id "{escape_string(model_id)}"; '
        f'insert $es isa ooevv-element-set, has id "{eset_id}", '
        f'has name "{label} elements"; '
        f'(model: $m, element-set: $es) isa kefed-model-elementset;').resolve()
    return eset_id


def cmd_add_experiment(args):
    """Create one experiment (kefed-model + ooevv-element-set) under a paper's sensemaking bundle.
    A paper may have several separate experiments.  The element-set houses the OOEVV
    process/entity definitions used by cmd_add_process / cmd_add_entity_node and is linked
    via the kefed-model-elementset relation (retiring the eset-{model_id} naming convention).
    --element-set <id> reuses an existing element-set (shared across models)."""
    exp_id = generate_id("scexp")
    ts = get_timestamp()
    defn = f', has ooevv-definition "{escape_string(args.definition)}"' if getattr(args, "definition", None) else ""
    lf = f', has ooevv-long-form "{escape_string(args.long_form)}"' if getattr(args, "long_form", None) else ""
    existing_eset = getattr(args, "element_set", None)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            b = list(tx.query(f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                              f'fetch {{ "id": $b.id }};').resolve())
            if not b:
                print(json.dumps({"success": False, "error": "Bundle not found"})); sys.exit(1)
            if existing_eset:
                es_check = list(tx.query(
                    f'match $es isa ooevv-element-set, has id "{escape_string(existing_eset)}"; '
                    f'fetch {{ "id": $es.id }};').resolve())
                if not es_check:
                    print(json.dumps({"success": False, "error": f"element-set {existing_eset!r} not found"}))
                    sys.exit(1)
            tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'insert $m isa kefed-model, has id "{exp_id}", has name "{escape_string(args.name)}", '
                f'has created-at {ts}{defn}{lf}; '
                f'(sensemaking: $b, experiment: $m) isa scilit-sensemaking-experiment;').resolve()
            if existing_eset:
                eset_id = existing_eset
                tx.query(
                    f'match $m isa kefed-model, has id "{exp_id}"; '
                    f'$es isa ooevv-element-set, has id "{escape_string(existing_eset)}"; '
                    f'insert (model: $m, element-set: $es) isa kefed-model-elementset;').resolve()
            else:
                eset_id = generate_id("eset")
                tx.query(
                    f'match $m isa kefed-model, has id "{exp_id}"; '
                    f'insert $es isa ooevv-element-set, has id "{eset_id}", '
                    f'has name "{escape_string(args.name)} elements"; '
                    f'(model: $m, element-set: $es) isa kefed-model-elementset;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "experiment_id": exp_id, "element_set_id": eset_id, "bundle": args.bundle}))


def cmd_add_process(args):
    """Find-or-create an OOEVV process DEFINITION (ooevv-assay / ooevv-material-processing /
    ooevv-data-transformation) in the model's element-set (resolved via the
    kefed-model-elementset relation), then create a kefed-model-node typed by it
    (kefed-node-type) and add the node to the model (kefed-model-element).
    Returns the node id as 'process_id'."""
    proc_types = {"assay": "ooevv-assay", "material-processing": "ooevv-material-processing",
                  "data-transformation": "ooevv-data-transformation"}
    if args.type not in proc_types:
        print(json.dumps({"success": False, "error": f"--type must be one of {list(proc_types)}"})); sys.exit(1)
    proc_ent_type = proc_types[args.type]
    cid = getattr(args, "template", None) or getattr(args, "experiment", None)
    if not cid:
        print(json.dumps({"success": False, "error": "Provide --template or --experiment"})); sys.exit(1)
    defn = f', has ooevv-definition "{escape_string(args.definition)}"' if getattr(args, "definition", None) else ""
    lf = f', has ooevv-long-form "{escape_string(args.long_form)}"' if getattr(args, "long_form", None) else ""
    ts = get_timestamp()
    node_id = generate_id("knode")
    proc_def_id = None
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            # Verify model exists
            m = list(tx.query(f'match $m isa kefed-model, has id "{escape_string(cid)}"; '
                              f'fetch {{ "id": $m.id }};').resolve())
            if not m:
                print(json.dumps({"success": False, "error": "kefed-model not found"})); sys.exit(1)
            # Resolve element-set via kefed-model-elementset relation (creating+linking if absent)
            eset_id = _model_elementset(tx, cid, getattr(args, "name", ""))
            # Find or create OOEVV process def by name in the element-set
            pd = list(tx.query(
                f'match $es isa ooevv-element-set, has id "{eset_id}"; '
                f'(element-set: $es, element: $p) isa ooevv-set-element; '
                f'$p isa {proc_ent_type}, has name "{escape_string(args.name)}"; '
                f'fetch {{ "id": $p.id }};').resolve())
            if pd:
                proc_def_id = pd[0]["id"]
            else:
                _require_definition(args, "process")
                proc_def_id = generate_id("ooevv")
                tx.query(
                    f'match $es isa ooevv-element-set, has id "{eset_id}"; '
                    f'insert $p isa {proc_ent_type}, has id "{proc_def_id}", '
                    f'has name "{escape_string(args.name)}"{defn}{lf}; '
                    f'(element-set: $es, element: $p) isa ooevv-set-element;').resolve()
            # Create kefed-model-node typed by the def; add to model
            tx.query(
                f'match $m isa kefed-model, has id "{escape_string(cid)}"; '
                f'$pd isa {proc_ent_type}, has id "{proc_def_id}"; '
                f'insert $n isa kefed-model-node, has id "{node_id}", '
                f'has name "{escape_string(args.name)}", has created-at {ts}; '
                f'(node: $n, node-type: $pd) isa kefed-node-type; '
                f'(model: $m, element: $n) isa kefed-model-element;').resolve()
            # Optional sub-process decomposition at the OOEVV def level
            if getattr(args, "parent", None):
                # parent is a node id; find its OOEVV process def
                par_def = list(tx.query(
                    f'match $pn isa kefed-model-node, has id "{escape_string(args.parent)}"; '
                    f'(node: $pn, node-type: $pd) isa kefed-node-type; $pd isa ooevv-process; '
                    f'fetch {{ "id": $pd.id }};').resolve())
                if par_def:
                    par_def_id = par_def[0]["id"]
                    tx.query(
                        f'match $par isa ooevv-process, has id "{par_def_id}"; '
                        f'$p isa ooevv-process, has id "{proc_def_id}"; '
                        f'insert (parent-process: $par, sub-process: $p) isa ooevv-process-decomposition;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "process_id": node_id, "process_def_id": proc_def_id,
                      "type": args.type, "parent": getattr(args, "parent", None)}))


def cmd_add_entity_node(args):
    """Find-or-create an ooevv-material-entity DEFINITION in the model's element-set, create a
    kefed-model-node typed by it (kefed-node-type), add to the model (kefed-model-element), and
    optionally mark it as the model's subject (ooevv-subject). Returns 'entity_node_id' (node id)."""
    cid = getattr(args, "template", None) or getattr(args, "experiment", None)
    if not cid:
        print(json.dumps({"success": False, "error": "Provide --template or --experiment"})); sys.exit(1)
    defn = f', has ooevv-definition "{escape_string(args.definition)}"' if getattr(args, "definition", None) else ""
    ts = get_timestamp()
    node_id = generate_id("knode")
    ent_def_id = None
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            # Verify model
            m = list(tx.query(f'match $m isa kefed-model, has id "{escape_string(cid)}"; '
                              f'fetch {{ "id": $m.id }};').resolve())
            if not m:
                print(json.dumps({"success": False, "error": "kefed-model not found"})); sys.exit(1)
            # Resolve element-set via kefed-model-elementset relation (creating+linking if absent)
            eset_id = _model_elementset(tx, cid, getattr(args, "name", ""))
            # Find or create ooevv-material-entity def by name
            ed = list(tx.query(
                f'match $es isa ooevv-element-set, has id "{eset_id}"; '
                f'(element-set: $es, element: $e) isa ooevv-set-element; '
                f'$e isa ooevv-material-entity, has name "{escape_string(args.name)}"; '
                f'fetch {{ "id": $e.id }};').resolve())
            if ed:
                ent_def_id = ed[0]["id"]
            else:
                _require_definition(args, "entity node")
                ent_def_id = generate_id("ooevv")
                tx.query(
                    f'match $es isa ooevv-element-set, has id "{eset_id}"; '
                    f'insert $e isa ooevv-material-entity, has id "{ent_def_id}", '
                    f'has name "{escape_string(args.name)}"{defn}; '
                    f'(element-set: $es, element: $e) isa ooevv-set-element;').resolve()
            # Create kefed-model-node typed by the def; add to model
            tx.query(
                f'match $m isa kefed-model, has id "{escape_string(cid)}"; '
                f'$ed isa ooevv-material-entity, has id "{ent_def_id}"; '
                f'insert $n isa kefed-model-node, has id "{node_id}", '
                f'has name "{escape_string(args.name)}", has created-at {ts}; '
                f'(node: $n, node-type: $ed) isa kefed-node-type; '
                f'(model: $m, element: $n) isa kefed-model-element;').resolve()
            # Optionally mark as model subject
            if getattr(args, "subject", False):
                tx.query(
                    f'match $m isa kefed-model, has id "{escape_string(cid)}"; '
                    f'$n isa kefed-model-node, has id "{node_id}"; '
                    f'insert (model: $m, subject-node: $n) isa ooevv-subject;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "entity_node_id": node_id, "entity_def_id": ent_def_id,
                      "subject": getattr(args, "subject", False)}))


def cmd_link_nodes(args):
    """Connect two kefed-model-nodes via ooevv-process-input (from_node is input-node,
    to_node is consuming-node) or ooevv-process-output (from_node is producing-node,
    to_node is output-node). --role input|output.

    The bigraph is BIPARTITE: entities are the inputs/outputs of processes, so a flow edge always
    joins an entity to a process. This verb ENFORCES that at write-time:
      --role input   requires  entity(from) -> process(to)   (material/data consumed BY a process)
      --role output  requires  process(from) -> entity(to)   (material/data produced BY a process)
    An edge that would join two entities or two processes (or run the wrong direction) is refused
    unless --force is given. Both nodes must already be typed (add-entity-node / add-process).
    Replaces cmd_link_entity (which incorrectly linked scilit-entity directly)."""
    if args.role not in ("input", "output"):
        print(json.dumps({"success": False, "error": "--role must be input|output"})); sys.exit(1)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            ok = list(tx.query(
                f'match $src isa kefed-model-node, has id "{escape_string(args.from_node)}"; '
                f'$tgt isa kefed-model-node, has id "{escape_string(args.to_node)}"; '
                f'fetch {{ "src": $src.id }};').resolve())
            if not ok:
                print(json.dumps({"success": False, "error": "Source or target node not found"})); sys.exit(1)
            # bipartite / direction enforcement (skippable with --force)
            src_cls = _node_class(_node_def(tx, args.from_node)[1])
            tgt_cls = _node_class(_node_def(tx, args.to_node)[1])
            want = ("entity", "process") if args.role == "input" else ("process", "entity")
            if not getattr(args, "force", False) and (src_cls, tgt_cls) != want:
                print(json.dumps({"success": False, "error": (
                    f"--role {args.role} requires {want[0]}->{want[1]}, but from_node is "
                    f"{src_cls or 'untyped'} and to_node is {tgt_cls or 'untyped'}. The KEfED bigraph "
                    f"is bipartite (entities flow into/out of processes; never entity->entity or "
                    f"process->process). Fix the edge, retype a node, or pass --force to override."),
                    "from_class": src_cls, "to_class": tgt_cls, "expected": list(want)}))
                sys.exit(1)
            if args.role == "input":
                rel = f'(input-node: $src, consuming-node: $tgt) isa ooevv-process-input'
            else:
                rel = f'(producing-node: $src, output-node: $tgt) isa ooevv-process-output'
            tx.query(
                f'match $src isa kefed-model-node, has id "{escape_string(args.from_node)}"; '
                f'$tgt isa kefed-model-node, has id "{escape_string(args.to_node)}"; '
                f'insert {rel};').resolve()
            tx.commit()
    print(json.dumps({"success": True, "from_node": args.from_node, "to_node": args.to_node,
                      "role": args.role, "from_class": src_cls, "to_class": tgt_cls}))


def _spec_enum_count(tx, scale_id):
    """Number of enumerated values in a value-spec (nominal/binary allowed-value or ordinal named-rank);
    0 for numeric/file/composite (no fixed value list)."""
    for attr in ("ooevv-allowed-value", "ooevv-named-rank"):
        try:
            r = list(tx.query(f'match $s isa ooevv-scale, has id "{escape_string(scale_id)}", has {attr} $v; reduce $c = count;').resolve())
            n = r[0].get("c").get_integer() if r else 0
            if n > 0:
                return n
        except Exception:
            pass
    return 0


def _role_from_cardinality(requested, enum_n):
    """A variable's role is fixed by its value-spec's cardinality: exactly one possible value -> constant;
    two or more (or an unbounded numeric range) -> parameter. 'measurement' (the readout) is respected as-is.
    Returns (role, corrected_from_or_None)."""
    if requested == "measurement":
        return "measurement", None
    derived = "constant" if enum_n == 1 else "parameter"
    return derived, (requested if derived != requested else None)


def cmd_add_variable(args):
    """Attach an ooevv-variable (role + quality + value-spec) to a kefed-model-node.

    PREFERRED: --value-spec <id> references a shared value-specification (its quality is used;
    one scale, many variables). LEGACY: --quality + --scale-type creates an inline scale, which is
    ALSO registered as a value-spec on the quality (ooevv-quality-scale) so it is never orphaned.

    The parameter/constant role is DERIVED from the value-spec's cardinality (one possible value ->
    constant; two or more -> parameter), so e.g. genotype {WT|SIRT3-KO} is always a parameter."""
    if args.role not in ("parameter", "constant", "measurement"):
        print(json.dumps({"success": False, "error": "--role must be parameter|constant|measurement"})); sys.exit(1)
    node_id = getattr(args, "node", None)
    if not node_id:
        print(json.dumps({"success": False, "error": "Provide --node (kefed-model-node id)"})); sys.exit(1)
    value_spec = getattr(args, "value_spec", None)
    _require_definition(args, "variable")
    var_id = generate_id("scvar"); ts = get_timestamp()
    defn = f', has ooevv-definition "{escape_string(args.definition)}"' if getattr(args, "definition", None) else ""
    lf = f', has ooevv-long-form "{escape_string(args.long_form)}"' if getattr(args, "long_form", None) else ""
    def _var_ins(role):
        return (f'$v isa ooevv-variable, has id "{var_id}", has name "{escape_string(args.name)}", '
                f'has ooevv-variable-role "{escape_string(role)}"{defn}{lf}, has created-at {ts}')
    corrected = None
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            if value_spec:
                # reference a shared value-spec; its quality comes via ooevv-quality-scale
                ok = list(tx.query(
                    f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                    f'$s isa ooevv-scale, has id "{escape_string(value_spec)}"; '
                    f'(quality: $q, scale: $s) isa ooevv-quality-scale; fetch {{ "nid": $n.id }};').resolve())
                if not ok:
                    print(json.dumps({"success": False, "error": "Node not found, or value-spec not found / not linked to a quality"})); sys.exit(1)
                role, corrected = _role_from_cardinality(args.role, _spec_enum_count(tx, value_spec))
                tx.query(
                    f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                    f'$s isa ooevv-scale, has id "{escape_string(value_spec)}"; '
                    f'(quality: $q, scale: $s) isa ooevv-quality-scale; '
                    f'insert {_var_ins(role)}; '
                    f'(node: $n, variable: $v) isa kefed-node-variable; '
                    f'(scaled-variable: $v, scale: $s) isa ooevv-has-scale; '
                    f'(measured-variable: $v, quality: $q) isa ooevv-measures;').resolve()
                tx.commit()
                scale_id = value_spec
            else:
                if args.scale_type not in _SCALE_TYPES:
                    print(json.dumps({"success": False, "error": f"--scale-type must be one of {list(_SCALE_TYPES)} (or use --value-spec)"})); sys.exit(1)
                if not getattr(args, "quality", None):
                    print(json.dumps({"success": False, "error": "Provide --quality (or --value-spec)"})); sys.exit(1)
                ok = list(tx.query(
                    f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                    f'$q isa ooevv-quality, has id "{escape_string(args.quality)}"; fetch {{ "nid": $n.id }};').resolve())
                if not ok:
                    print(json.dumps({"success": False, "error": "Node or quality not found"})); sys.exit(1)
                enum_n = len([a for a in (getattr(args, "values", "") or "").split("|") if a.strip()])
                role, corrected = _role_from_cardinality(args.role, enum_n)
                scale_id = generate_id("scvspec")
                sclause = _scale_attr_clause(args)
                # inline scale is named + registered as a value-spec on the quality (never orphaned)
                tx.query(
                    f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                    f'$q isa ooevv-quality, has id "{escape_string(args.quality)}"; '
                    f'insert {_var_ins(role)}; '
                    f'$s isa {_SCALE_TYPES[args.scale_type]}, has id "{scale_id}", '
                    f'has name "{escape_string(args.name)}", has created-at {ts}{sclause}; '
                    f'(node: $n, variable: $v) isa kefed-node-variable; '
                    f'(scaled-variable: $v, scale: $s) isa ooevv-has-scale; '
                    f'(measured-variable: $v, quality: $q) isa ooevv-measures; '
                    f'(quality: $q, scale: $s) isa ooevv-quality-scale;').resolve()
                tx.commit()
    print(json.dumps({"success": True, "variable_id": var_id, "scale_id": scale_id, "role": role,
                      "role_corrected_from": corrected, "value_spec_referenced": bool(value_spec)}))


def cmd_bind_parameter(args):
    """Attach a parameter/constant to a kefed-model-node via kefed-node-variable (idempotent).
    --target-entity (kefed-model-node id) adds specificity via ooevv-parameter-target.
    Retired: ooevv-parameter-binding / binding-bearer role."""
    node_id = getattr(args, "node", None)
    if not node_id:
        print(json.dumps({"success": False, "error": "Provide --node (kefed-model-node id)"})); sys.exit(1)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            ok = list(tx.query(
                f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                f'$v isa ooevv-variable, has id "{escape_string(args.parameter)}"; '
                f'fetch {{ "nid": $n.id }};').resolve())
            if not ok:
                print(json.dumps({"success": False, "error": "Node or parameter not found"})); sys.exit(1)
            existing = list(tx.query(
                f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                f'$v isa ooevv-variable, has id "{escape_string(args.parameter)}"; '
                f'(node: $n, variable: $v) isa kefed-node-variable; '
                f'fetch {{ "nid": $n.id }};').resolve())
            if not existing:
                tx.query(
                    f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                    f'$v isa ooevv-variable, has id "{escape_string(args.parameter)}"; '
                    f'insert (node: $n, variable: $v) isa kefed-node-variable;').resolve()
            if getattr(args, "target_entity", None):
                tx.query(
                    f'match $v isa ooevv-variable, has id "{escape_string(args.parameter)}"; '
                    f'$e isa kefed-model-node, has id "{escape_string(args.target_entity)}"; '
                    f'insert (targeting-parameter: $v, target-entity: $e) isa ooevv-parameter-target;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "node": node_id, "parameter": args.parameter,
                      "target_entity": getattr(args, "target_entity", None)}))


# --- node-class helpers (shared by link-nodes enforcement, the linter, and hgraph export) ---
# A kefed-model-node is either an ENTITY (material or information/dataset) or a PROCESS
# (assay / material-processing / data-transformation). The bigraph is bipartite between the
# two classes: entities are the inputs and outputs of processes; entities never flow into
# entities and processes never flow into processes.
_ENTITY_DEF_TYPES = {"ooevv-material-entity", "ooevv-information-content-entity"}
_PROCESS_DEF_TYPES = {"ooevv-assay", "ooevv-material-processing", "ooevv-data-transformation"}


def _node_class(type_label):
    """Map a concrete OOEVV def-type label to the bigraph node class ('entity'|'process'|None)."""
    if type_label in _ENTITY_DEF_TYPES:
        return "entity"
    if type_label in _PROCESS_DEF_TYPES:
        return "process"
    return None


def cmd_map_params(args):
    """Declare how a DATA-TRANSFORMATION maps its input parameters to output parameters
    (ooevv-param-mapping). This is what lets a data signature be computed CORRECTLY for
    computed data: the rule tells the traversal which incoming index parameters SURVIVE the
    computation, which are CONSUMED, which are FOLDED into a derived contrast, and which are
    freshly DERIVED — because a transformation can silently change or destroy an index and
    that cannot be inferred from the graph alone. Classic case: a correlation coefficient
    consumes (destroys) the per-sample index of the datasets it correlates.

    --transformation <knode>   data-transformation node (kefed-model-node typed ooevv-data-transformation)
    --rule <kind>              passthrough | aggregate-collapse-destroy | combine | derive
    --in  <var-ids>            comma-separated ooevv-variable ids (input parameters):
                                 passthrough -> exactly 1; aggregate-collapse-destroy -> >=1;
                                 combine -> >=2; derive -> none
    --out <var-id>             output parameter var id:
                                 passthrough/combine/derive -> required;
                                 aggregate-collapse-destroy -> omitted (the index is destroyed)

    One ooevv-param-mapping relation is written per rule (combine carries several in-parameter players).
    The transformation role is played by the node's OOEVV data-transformation DEFINITION; the in/out
    parameters are this model's variables, so the mapping is model-specific in practice.
    """
    RULES = {"passthrough", "aggregate-collapse-destroy", "combine", "derive"}
    if args.rule not in RULES:
        print(json.dumps({"success": False, "error": f"--rule must be one of {sorted(RULES)}"})); sys.exit(1)
    ins = [x.strip() for x in (getattr(args, "in_params", "") or "").split(",") if x.strip()]
    out = getattr(args, "out_param", None)
    errs = {
        "passthrough": (len(ins) == 1 and out, "passthrough needs exactly 1 --in and 1 --out"),
        "aggregate-collapse-destroy": (len(ins) >= 1 and not out,
            "aggregate-collapse-destroy needs >=1 --in and NO --out (the index is consumed)"),
        "combine": (len(ins) >= 2 and out, "combine needs >=2 --in and 1 --out"),
        "derive": (not ins and out, "derive needs NO --in and 1 --out"),
    }
    ok_arity, msg = errs[args.rule]
    if not ok_arity:
        print(json.dumps({"success": False, "error": msg})); sys.exit(1)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            def_id, klass = _node_def(tx, args.transformation)
            if klass != "ooevv-data-transformation":
                print(json.dumps({"success": False,
                                  "error": f"--transformation must be a data-transformation node (got type {klass})"}))
                sys.exit(1)
            for vid in ins + ([out] if out else []):
                if not list(tx.query(f'match $v isa ooevv-variable, has id "{escape_string(vid)}"; '
                                     f'fetch {{ "id": $v.id }};').resolve()):
                    print(json.dumps({"success": False, "error": f"variable {vid} not found"})); sys.exit(1)
            # transformation role is played by the OOEVV data-transformation DEFINITION, not the node
            clauses = [f'$t isa ooevv-data-transformation, has id "{escape_string(def_id)}";']
            roles = ["transformation: $t"]
            for i, vid in enumerate(ins):
                clauses.append(f'$in{i} isa ooevv-variable, has id "{escape_string(vid)}";')
                roles.append(f"in-parameter: $in{i}")
            if out:
                clauses.append(f'$out isa ooevv-variable, has id "{escape_string(out)}";')
                roles.append("out-parameter: $out")
            tx.query("match " + " ".join(clauses) + " insert (" + ", ".join(roles) +
                     f') isa ooevv-param-mapping, has ooevv-param-rule-kind "{escape_string(args.rule)}";').resolve()
            tx.commit()
    print(json.dumps({"success": True, "transformation": args.transformation, "transformation_def": def_id,
                      "rule": args.rule, "in": ins, "out": out}))


# =============================================================================
# KEfED model-EDIT verbs — correct an existing model in place (rename / retype /
# move a variable / delete a node / set a node's definition). The node id, its
# variables, and its flow edges survive a retype (only the kefed-node-type link
# is rewired). Use these to enforce the authoring rules in SKILL.md on models
# already curated (generic entity names, measurement-on-process, hidden
# generating/sorting processes).
# =============================================================================

_NODE_TYPES = {"material-entity": "ooevv-material-entity", "assay": "ooevv-assay",
               "material-processing": "ooevv-material-processing",
               "data-transformation": "ooevv-data-transformation"}


def _node_def(tx, node_id):
    """Return (def_id, concrete_ooevv_type_label) of the OOEVV definition typing a node."""
    rows = list(tx.query(
        f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
        f'(node: $n, node-type: $d) isa kefed-node-type; $d isa $dt; '
        f'fetch {{ "id": $d.id, "dt": $dt }};').resolve())
    if not rows:
        return None, None
    did = rows[0]["id"]
    labels = {(r["dt"] if isinstance(r["dt"], str) else r["dt"].get("label")) for r in rows}
    for t in ("ooevv-assay", "ooevv-material-processing", "ooevv-data-transformation", "ooevv-material-entity"):
        if t in labels:
            return did, t
    return did, None


def _node_def_use_count(tx, def_id):
    return len(list(tx.query(
        f'match $d isa ooevv-element, has id "{escape_string(def_id)}"; '
        f'(node: $n, node-type: $d) isa kefed-node-type; fetch {{ "id": $n.id }};').resolve()))


def cmd_rename_node(args):
    """Rename a kefed-model-node's display name AND its OOEVV definition's name (the def name is
    only changed when that def is used by this one node, so shared/reused defs are never disturbed)."""
    node_id = args.node
    new = escape_string(args.name)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            exists = list(tx.query(f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                                   f'fetch {{ "id": $n.id }};').resolve())
            if not exists:
                print(json.dumps({"success": False, "error": "Node not found"})); sys.exit(1)
            did, _ = _node_def(tx, node_id)
            tx.query(f'match $n isa kefed-model-node, has id "{escape_string(node_id)}", has name $o; '
                     f'delete has $o of $n; insert $n has name "{new}";').resolve()
            def_renamed = False
            if did and _node_def_use_count(tx, did) == 1:
                tx.query(f'match $d isa ooevv-element, has id "{escape_string(did)}", has name $o; '
                         f'delete has $o of $d; insert $d has name "{new}";').resolve()
                def_renamed = True
            tx.commit()
    print(json.dumps({"success": True, "node": node_id, "name": args.name,
                      "def": did, "def_renamed": def_renamed}))


def cmd_retype_node(args):
    """Change a node's OOEVV type by rewiring its kefed-node-type link to a def of the requested type
    (find-or-create by name within the model's element-set). The node id, its variables and its flow
    edges are preserved. Optionally rename the node with --name. Use e.g. to retype a trailing
    'result/profile' material-entity that carries measurements into the data-transformation that
    produced them."""
    node_id = args.node
    if args.type not in _NODE_TYPES:
        print(json.dumps({"success": False, "error": f"--type must be one of {list(_NODE_TYPES)}"})); sys.exit(1)
    tgt = _NODE_TYPES[args.type]
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            m = list(tx.query(f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                              f'(model: $mo, element: $n) isa kefed-model-element; $n has name $nn; '
                              f'fetch {{ "model": $mo.id, "name": $nn }};').resolve())
            if not m:
                print(json.dumps({"success": False, "error": "Node not found or not in a model"})); sys.exit(1)
            model_id = m[0]["model"]
            name = args.name or m[0]["name"]
            eset_id = _model_elementset(tx, model_id, name)
            ex = list(tx.query(
                f'match $es isa ooevv-element-set, has id "{eset_id}"; '
                f'(element-set: $es, element: $d) isa ooevv-set-element; '
                f'$d isa {tgt}, has name "{escape_string(name)}"; fetch {{ "id": $d.id }};').resolve())
            if ex:
                new_def = ex[0]["id"]
            else:
                new_def = generate_id("ooevv")
                tx.query(f'match $es isa ooevv-element-set, has id "{eset_id}"; '
                         f'insert $d isa {tgt}, has id "{new_def}", has name "{escape_string(name)}"; '
                         f'(element-set: $es, element: $d) isa ooevv-set-element;').resolve()
            tx.query(f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                     f'$r isa kefed-node-type, links (node: $n, node-type: $od); delete $r;').resolve()
            tx.query(f'match $n isa kefed-model-node, has id "{escape_string(node_id)}"; '
                     f'$d isa {tgt}, has id "{new_def}"; '
                     f'insert (node: $n, node-type: $d) isa kefed-node-type;').resolve()
            if args.name:
                tx.query(f'match $n isa kefed-model-node, has id "{escape_string(node_id)}", has name $o; '
                         f'delete has $o of $n; insert $n has name "{escape_string(args.name)}";').resolve()
            tx.commit()
    print(json.dumps({"success": True, "node": node_id, "type": args.type,
                      "new_def": new_def, "renamed": bool(args.name)}))


def cmd_move_variable(args):
    """Reassign a variable (measurement / parameter / constant) from its current node to another node
    via kefed-node-variable. Used to canonicalize a measurement onto the measuring process, or to move
    a specialization parameter onto the hidden process that sets it."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            ok = list(tx.query(
                f'match $v isa ooevv-variable, has id "{escape_string(args.variable)}"; '
                f'$n isa kefed-model-node, has id "{escape_string(args.to_node)}"; '
                f'fetch {{ "v": $v.id }};').resolve())
            if not ok:
                print(json.dumps({"success": False, "error": "Variable or target node not found"})); sys.exit(1)
            tx.query(f'match $v isa ooevv-variable, has id "{escape_string(args.variable)}"; '
                     f'$r isa kefed-node-variable, links (node: $on, variable: $v); delete $r;').resolve()
            tx.query(f'match $v isa ooevv-variable, has id "{escape_string(args.variable)}"; '
                     f'$n isa kefed-model-node, has id "{escape_string(args.to_node)}"; '
                     f'insert (node: $n, variable: $v) isa kefed-node-variable;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "variable": args.variable, "to_node": args.to_node}))


def cmd_delete_node(args):
    """Delete a kefed-model-node after detaching every relation it plays (type, model membership,
    flow edges, subject, parameter-target). REFUSES if the node still carries variables unless --force
    (which detaches them, leaving the variables orphaned). Move variables off first with move-variable."""
    node_id = args.node
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            e = escape_string(node_id)
            exists = list(tx.query(f'match $n isa kefed-model-node, has id "{e}"; fetch {{ "id": $n.id }};').resolve())
            if not exists:
                print(json.dumps({"success": False, "error": "Node not found"})); sys.exit(1)
            vs = list(tx.query(f'match $n isa kefed-model-node, has id "{e}"; '
                               f'(node: $n, variable: $v) isa kefed-node-variable; fetch {{ "id": $v.id }};').resolve())
            if vs and not getattr(args, "force", False):
                print(json.dumps({"success": False, "error": "Node still carries variables; move them "
                                  "off with move-variable first, or pass --force to detach (orphaning) them",
                                  "variables": [v["id"] for v in vs]})); sys.exit(1)
            for rel in ("kefed-node-type", "kefed-model-element", "kefed-node-variable",
                        "ooevv-subject", "ooevv-process-input", "ooevv-process-output",
                        "ooevv-parameter-target"):
                tx.query(f'match $n isa kefed-model-node, has id "{e}"; '
                         f'$r isa {rel}; $r links ($n); delete $r;').resolve()
            tx.query(f'match $n isa kefed-model-node, has id "{e}"; delete $n;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "deleted": node_id, "orphaned_variables": [v["id"] for v in vs]}))


def cmd_set_node_definition(args):
    """Set/replace the plain-English ooevv-definition on the OOEVV definition typing a node."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            did, _ = _node_def(tx, args.node)
            if not did:
                print(json.dumps({"success": False, "error": "Node or its definition not found"})); sys.exit(1)
            de = escape_string(did)
            has = list(tx.query(f'match $x isa ooevv-element, has id "{de}", has ooevv-definition $o; '
                                f'fetch {{ "o": $o }};').resolve())
            if has:
                tx.query(f'match $x isa ooevv-element, has id "{de}", has ooevv-definition $o; '
                         f'delete has $o of $x;').resolve()
            tx.query(f'match $x isa ooevv-element, has id "{de}"; '
                     f'insert $x has ooevv-definition "{escape_string(args.definition)}";').resolve()
            tx.commit()
    print(json.dumps({"success": True, "node": args.node, "def": did}))


def cmd_set_citation(args):
    """Set bibliographic citation fields on a scilit-paper: authors (semicolon-delimited,
    order-preserving), journal volume/issue, and page range. Each is optional; only the ones
    provided are replaced (delete-then-insert). Used to backfill a full academic citation from
    an external source (e.g. PubMed) for the dashboard's citation header."""
    fields = {
        "scilit-author-list": getattr(args, "authors", None),
        "scilit-journal-name": getattr(args, "journal", None),
        "scilit-journal-volume": getattr(args, "volume", None),
        "scilit-journal-issue": getattr(args, "issue", None),
        "scilit-page-range": getattr(args, "pages", None),
    }
    provided = {attr: val for attr, val in fields.items() if val is not None}
    if not provided:
        print(json.dumps({"success": False, "error": "No citation fields provided"})); sys.exit(1)
    pe = escape_string(args.id)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            exists = list(tx.query(
                f'match $p isa scilit-paper, has id "{pe}"; fetch {{ "id": $p.id }};').resolve())
            if not exists:
                print(json.dumps({"success": False, "error": "Paper not found"})); sys.exit(1)
            for attr, val in provided.items():
                has = list(tx.query(
                    f'match $p isa scilit-paper, has id "{pe}", has {attr} $x; '
                    f'fetch {{ "x": $x }};').resolve())
                if has:
                    tx.query(f'match $p isa scilit-paper, has id "{pe}", has {attr} $x; '
                             f'delete has $x of $p;').resolve()
                tx.query(f'match $p isa scilit-paper, has id "{pe}"; '
                         f'insert $p has {attr} "{escape_string(str(val))}";').resolve()
            tx.commit()
    print(json.dumps({"success": True, "id": args.id, "set": list(provided.keys())}))


# =============================================================================
# KEfED template / instance / data verbs (curation by recognize-reuse-fill)
# =============================================================================

def cmd_ensure_template(args):
    """Find-or-create a reusable experiment-design template:
    a kefed-model with kefed-model-state 'template', linked to an ooevv-element-set via
    kefed-model-elementset.  --definition/--long-form are persisted on the kefed-model.
    --element-set <id> reuses an existing element-set (shared across models)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            ex = list(tx.query(
                f'match $t isa kefed-model, has kefed-model-state "template", '
                f'has name "{escape_string(args.name)}"; '
                f'fetch {{ "id": $t.id }};').resolve())
        if ex:
            print(json.dumps({"success": True, "template_id": ex[0]["id"], "reused": True}))
            return
        tid = generate_id("sctpl"); ts = get_timestamp()
        defn = f', has ooevv-definition "{escape_string(args.definition)}"' if getattr(args, "definition", None) else ""
        lf = f', has ooevv-long-form "{escape_string(args.long_form)}"' if getattr(args, "long_form", None) else ""
        existing_eset = getattr(args, "element_set", None)
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            if existing_eset:
                es_check = list(tx.query(
                    f'match $es isa ooevv-element-set, has id "{escape_string(existing_eset)}"; '
                    f'fetch {{ "id": $es.id }};').resolve())
                if not es_check:
                    print(json.dumps({"success": False, "error": f"element-set {existing_eset!r} not found"}))
                    sys.exit(1)
            tx.query(
                f'insert $t isa kefed-model, has id "{tid}", has name "{escape_string(args.name)}", '
                f'has kefed-model-state "template", has created-at {ts}{defn}{lf};').resolve()
            if existing_eset:
                tx.query(
                    f'match $t isa kefed-model, has id "{tid}"; '
                    f'$es isa ooevv-element-set, has id "{escape_string(existing_eset)}"; '
                    f'insert (model: $t, element-set: $es) isa kefed-model-elementset;').resolve()
            else:
                eset_id = generate_id("eset")
                tx.query(
                    f'match $t isa kefed-model, has id "{tid}"; '
                    f'insert $es isa ooevv-element-set, has id "{eset_id}", '
                    f'has name "{escape_string(args.name)} elements"; '
                    f'(model: $t, element-set: $es) isa kefed-model-elementset;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "template_id": tid, "reused": False}))


def _match_filter(rows, term, *fields):
    """Case-insensitive substring filter over the named fields of fetched dict rows."""
    if not term:
        return rows
    t = term.lower()
    return [r for r in rows if any(t in str(r.get(f, "")).lower() for f in fields)]


def cmd_list_templates(args):
    """RECOGNITION / gap-check: list reusable templates (optionally --match a name substring)
    with process/variable/instance counts, so curation can decide reuse-vs-create.
    Template = kefed-model with kefed-model-state 'template'.
    Retired: kefed-template type, slot counts, kefed-element (Task 8, Jun 2026)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            rows = list(tx.query(
                'match $t isa kefed-model, has kefed-model-state "template"; '
                'fetch { "id": $t.id, "name": $t.name };').resolve())
            tpls = _match_filter([{k: v for k, v in r.items() if v is not None} for r in rows],
                                 getattr(args, "match", None), "name")
            for tp in tpls:
                e = escape_string(tp["id"])
                tp["process_count"] = sum(1 for _ in tx.query(
                    f'match $t isa kefed-model, has id "{e}"; '
                    f'(model: $t, element: $n) isa kefed-model-element; $n isa kefed-model-node; select $n;').resolve())
                tp["variable_count"] = sum(1 for _ in tx.query(
                    f'match $t isa kefed-model, has id "{e}"; '
                    f'(model: $t, element: $n) isa kefed-model-element; $n isa kefed-model-node; '
                    f'(node: $n, variable: $v) isa kefed-node-variable; select $v;').resolve())
                tp["instance_count"] = sum(1 for _ in tx.query(
                    f'match $t isa kefed-model, has id "{e}"; '
                    f'(instance: $i, model: $t) isa kefed-instance-of; select $i;').resolve())
    print(json.dumps({"success": True, "count": len(tpls), "templates": tpls}, indent=2))


def cmd_list_qualities(args):
    """RECOGNITION / gap-check: list curated qualities (optionally --match) for reuse-vs-create decisions."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            rows = list(tx.query(
                'match $q isa ooevv-quality; '
                'fetch { "id": $q.id, "name": $q.name, "definition": $q.ooevv-definition, "long_form": $q.ooevv-long-form };').resolve())
    qs = _match_filter([{k: v for k, v in r.items() if v is not None} for r in rows],
                       getattr(args, "match", None), "name", "definition")
    print(json.dumps({"success": True, "count": len(qs), "qualities": qs}, indent=2))


def cmd_list_entities(args):
    """RECOGNITION / gap-check: list curated entities (optionally --match) for reuse-vs-create decisions."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            rows = list(tx.query(
                'match $e isa scilit-entity; '
                'fetch { "id": $e.id, "name": $e.name, "kind": $e.scilit-entity-kind, '
                '"definition": $e.ooevv-definition, "long_form": $e.ooevv-long-form };').resolve())
    es = _match_filter([{k: v for k, v in r.items() if v is not None} for r in rows],
                       getattr(args, "match", None), "name", "definition")
    print(json.dumps({"success": True, "count": len(es), "entities": es}, indent=2))


def _looks_abbreviated(token):
    """Heuristic: a name token that reads like an abbreviation/symbol needing a long-form
    (>=2 uppercase letters, or a digit mixed with letters), e.g. HSC, LSK, qPCR, 5FU, SOD2."""
    if token.isdigit() or len(token) > 12:
        return False
    ncaps = sum(1 for c in token if c.isupper())
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    return ncaps >= 2 or (has_digit and has_alpha)


def cmd_audit_terms(args):
    """LINTER for the curation standard. Scans OOEVV elements and flags: terms missing a
    definition, definitions that are too short, and names with an abbreviation but no
    long-form. Read-only; fix flagged items by re-authoring with --definition/--long-form."""
    import re
    # kefed-variable -> ooevv-variable; kefed-template + kefed-slot retired (Task 8, Jun 2026)
    TYPES = [("ooevv-quality", "quality"), ("scilit-entity", "entity"),
             ("ooevv-process", "process"), ("ooevv-variable", "variable")]
    tok_re = re.compile(r"[A-Za-z0-9+]+")
    minlen = int(getattr(args, "min_def_len", None) or 40)
    only = getattr(args, "type", None)
    report = {"missing_definition": [], "short_definition": [], "unexpanded_abbreviation": []}
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            for tlabel, short in TYPES:
                if only and only != short:
                    continue
                rows = list(tx.query(
                    f'match $x isa {tlabel}, has name $n; '
                    f'fetch {{ "id": $x.id, "name": $n, "def": $x.ooevv-definition, '
                    f'"lf": $x.ooevv-long-form }};').resolve())
                for r in rows:
                    item = {"type": short, "id": r["id"], "name": r.get("name")}
                    d = (r.get("def") or "").strip()
                    lf = (r.get("lf") or "").strip()
                    if not d:
                        report["missing_definition"].append(item)
                        continue
                    if len(d) < minlen:
                        report["short_definition"].append({**item, "len": len(d)})
                    abbrevs = sorted({t for t in tok_re.findall(r.get("name") or "") if _looks_abbreviated(t)})
                    if abbrevs and not lf:
                        report["unexpanded_abbreviation"].append({**item, "abbreviations": abbrevs})
    summary = {k: len(v) for k, v in report.items()}
    summary["total_flagged"] = sum(summary.values())
    print(json.dumps({"success": True, "min_def_len": minlen, "summary": summary, **report}, indent=2))


def cmd_instantiate_template(args):
    """FILL: create a kefed-instance under a bundle, linked to a template-state kefed-model.
    The instance reuses the template's graph; it only adds data rows."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            ok = list(tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'$m isa kefed-model, has id "{escape_string(args.template)}"; '
                f'fetch {{ "b": $b.id }};').resolve())
            if not ok:
                print(json.dumps({"success": False, "error": "Bundle or template (kefed-model) not found"})); sys.exit(1)
            iid = generate_id("scinst"); ts = get_timestamp()
            name = getattr(args, "name", None) or args.template
            tx.query(
                f'match $b isa scilit-paper-sensemaking, has id "{escape_string(args.bundle)}"; '
                f'$m isa kefed-model, has id "{escape_string(args.template)}"; '
                f'insert $i isa kefed-instance, has id "{iid}", has name "{escape_string(name)}", has created-at {ts}; '
                f'(instance: $i, model: $m) isa kefed-instance-of; '
                f'(sensemaking: $b, experiment: $i) isa scilit-sensemaking-experiment;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "instance_id": iid, "bundle": args.bundle, "template": args.template}))


def cmd_add_datum(args):
    """FILL: add one data row to an instance. --cells is a JSON list of
    {"variable": <var id>, "value": <str>, "number"?: <float>, "n"?: <float>, "error"?: <float>,
     "error_type"?: "sd|sem|ci95|range|iqr", "unit"?: <str>} (independents + the measured value).
    n/error/error_type describe a summary readout (sample size + dispersion); unit is the per-row
    unit (lets one generic "response" measurement carry a different unit per readout type).
    Provenance (coexistence): link an existing --observation, or pass --gloss to create one inline."""
    try:
        cells = json.loads(args.cells)
        assert isinstance(cells, list)
    except Exception as e:
        print(json.dumps({"success": False, "error": f"--cells must be a JSON list: {e}"})); sys.exit(1)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            inst = list(tx.query(f'match $i isa kefed-instance, has id "{escape_string(args.instance)}"; '
                                 f'fetch {{ "id": $i.id }};').resolve())
            if not inst:
                print(json.dumps({"success": False, "error": "Instance not found"})); sys.exit(1)
            # Validate cell variable ids against the model (if instance has one via kefed-instance-of).
            # If no model is linked, skip validation for backward compatibility.
            model_rows = list(tx.query(
                f'match $i isa kefed-instance, has id "{escape_string(args.instance)}"; '
                f'(instance: $i, model: $m) isa kefed-instance-of; '
                f'fetch {{ "mid": $m.id }};').resolve())
            if model_rows:
                mid = escape_string(model_rows[0]["mid"])
                var_rows = list(tx.query(
                    f'match $m isa kefed-model, has id "{mid}"; '
                    f'(model: $m, element: $n) isa kefed-model-element; $n isa kefed-model-node; '
                    f'(node: $n, variable: $v) isa kefed-node-variable; '
                    f'fetch {{ "vid": $v.id }};').resolve())
                model_vars = {r["vid"] for r in var_rows}
                for c in cells:
                    cell_vid = str(c["variable"])
                    if cell_vid not in model_vars:
                        print(json.dumps({"success": False,
                                          "error": f"unknown variable {cell_vid!r} for this model"}))
                        sys.exit(1)
            did = generate_id("scdatum"); ts = get_timestamp()
            tx.query(
                f'match $i isa kefed-instance, has id "{escape_string(args.instance)}"; '
                f'insert $d isa kefed-row, has id "{did}", has created-at {ts}; '
                f'(instance: $i, datum: $d) isa kefed-instance-datum;').resolve()
            for c in cells:
                vid = escape_string(str(c["variable"]))
                val = escape_string(str(c.get("value", "")))
                extra = ""
                if c.get("number", None) is not None:
                    extra += f', has kefed-cell-number {float(c["number"])}'
                if c.get("n", None) is not None:
                    extra += f', has kefed-cell-n {float(c["n"])}'
                if c.get("error", None) is not None:
                    extra += f', has kefed-cell-error {float(c["error"])}'
                if c.get("error_type", None):
                    extra += f', has kefed-cell-error-type "{escape_string(str(c["error_type"]))}"'
                if c.get("unit", None):
                    extra += f', has kefed-cell-unit "{escape_string(str(c["unit"]))}"'
                tx.query(
                    f'match $d isa kefed-row, has id "{did}"; '
                    f'$v isa ooevv-variable, has id "{vid}"; '
                    f'insert (datum: $d, cell-variable: $v) isa kefed-cell, '
                    f'has kefed-cell-value "{val}"{extra};').resolve()
            obs_id = getattr(args, "observation", None)
            if not obs_id and getattr(args, "gloss", None):
                obs_id = generate_id("scobs")
                kl = escape_string(getattr(args, "knowledge_level", None) or "observation")
                bs = escape_string(getattr(args, "bio_scale", None) or "molecular")
                tx.query(
                    f'insert $o isa scilit-observation, has id "{obs_id}", '
                    f'has name "{escape_string(args.gloss[:60])}", has content "{escape_string(args.gloss)}", '
                    f'has scilit-knowledge-level "{kl}", has scilit-bio-scale "{bs}", has created-at {ts};').resolve()
            if obs_id:
                tx.query(
                    f'match $d isa kefed-row, has id "{did}"; '
                    f'$o isa scilit-observation, has id "{escape_string(obs_id)}"; '
                    f'insert (datum: $d, observation: $o) isa kefed-datum-observation;').resolve()
            tx.commit()
    print(json.dumps({"success": True, "datum_id": did, "instance": args.instance,
                      "cells": len(cells), "observation": obs_id}))


def cmd_set_cell(args):
    """Upsert one variable's cell across data rows without rebuilding them. Scope = one --datum row,
    or ALL rows of an --instance. Updates the given attributes on an existing cell, or ADDS the
    variable as a new column (cell) to rows that lack it (a --value is required to create). Use to
    backfill statistics/units (n/error/error_type/unit) or a newly-added variable's value onto
    already-curated rows. Only the attributes you pass are changed; others are left as-is."""
    num_updates, str_updates = {}, {}
    if getattr(args, "number", None) is not None: num_updates["kefed-cell-number"] = float(args.number)
    if getattr(args, "n", None) is not None: num_updates["kefed-cell-n"] = float(args.n)
    if getattr(args, "error", None) is not None: num_updates["kefed-cell-error"] = float(args.error)
    if getattr(args, "value", None) is not None: str_updates["kefed-cell-value"] = str(args.value)
    if getattr(args, "error_type", None): str_updates["kefed-cell-error-type"] = str(args.error_type)
    if getattr(args, "unit", None): str_updates["kefed-cell-unit"] = str(args.unit)
    all_attrs = {**num_updates, **str_updates}
    if not all_attrs:
        print(json.dumps({"success": False, "error": "provide at least one of "
                          "--value/--number/--n/--error/--error-type/--unit"})); sys.exit(1)
    vid = escape_string(args.variable)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            if getattr(args, "datum", None):
                datum_ids = [args.datum]
            elif getattr(args, "instance", None):
                datum_ids = [r["id"] for r in tx.query(
                    f'match $i isa kefed-instance, has id "{escape_string(args.instance)}"; '
                    f'(instance: $i, datum: $d) isa kefed-instance-datum; fetch {{ "id": $d.id }};').resolve()]
            else:
                print(json.dumps({"success": False, "error": "provide --datum or --instance"})); sys.exit(1)
            created, updated = 0, 0
            for did in datum_ids:
                de = escape_string(did)
                cellq = (f'$d isa kefed-row, has id "{de}"; $v isa ooevv-variable, has id "{vid}"; '
                         f'$c isa kefed-cell, links (datum: $d, cell-variable: $v);')
                exists = bool(list(tx.query(f'match {cellq} fetch {{ "x": $v.id }};').resolve()))
                if not exists:
                    if "kefed-cell-value" not in str_updates:
                        print(json.dumps({"success": False,
                                          "error": f"cell for {args.variable} absent on row {did}; --value required to create it"}))
                        sys.exit(1)
                    clauses = [f'has kefed-cell-value "{escape_string(str_updates["kefed-cell-value"])}"']
                    for a, val in num_updates.items():
                        clauses.append(f'has {a} {val}')
                    for a, val in str_updates.items():
                        if a != "kefed-cell-value":
                            clauses.append(f'has {a} "{escape_string(val)}"')
                    tx.query(f'match $d isa kefed-row, has id "{de}"; $v isa ooevv-variable, has id "{vid}"; '
                             f'insert (datum: $d, cell-variable: $v) isa kefed-cell, {", ".join(clauses)};').resolve()
                    created += 1
                else:
                    for a, val in all_attrs.items():
                        # delete existing value of this attr on the cell (no-op if absent), then insert
                        tx.query(f'match {cellq} $c has {a} $old; delete has $old of $c;').resolve()
                        lit = f'{val}' if a in num_updates else f'"{escape_string(val)}"'
                        tx.query(f'match {cellq} insert $c has {a} {lit};').resolve()
                    updated += 1
            tx.commit()
    print(json.dumps({"success": True, "variable": args.variable, "rows_created": created,
                      "rows_updated": updated, "attributes": list(all_attrs)}))


def cmd_add_citation_impact(args):
    """Record how a citing paper received the focal paper, threaded under the investigation."""
    if args.impact_type not in IMPACT_TYPES:
        print(json.dumps({"success": False,
                          "error": f"Invalid impact type. Use one of: {', '.join(IMPACT_TYPES)}"}))
        sys.exit(1)
    imp_id = generate_id("scimpact")
    ts = get_timestamp()
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            inv = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.investigation)}"; '
                f'fetch {{ "id": $inv.id }};'
            ).resolve())
        if not inv:
            print(json.dumps({"success": False, "error": "Investigation not found"}))
            sys.exit(1)

        citing_id = _resolve_paper_arg(driver, args.citing_id or args.citing_doi)
        if not citing_id:
            print(json.dumps({"success": False,
                              "error": f"Could not resolve citing paper: "
                                       f"{args.citing_id or args.citing_doi}"}))
            sys.exit(1)

        name = args.impact_summary[:60]
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.investigation)}"; '
                f'$cit isa scilit-paper, has id "{escape_string(citing_id)}"; '
                f'insert $imp isa scilit-citation-impact, has id "{imp_id}", '
                f'has name "{escape_string(name)}", '
                f'has scilit-impact-type "{escape_string(args.impact_type)}", '
                f'has scilit-impact-summary "{escape_string(args.impact_summary)}", '
                f'has created-at {ts}; '
                f'(investigation: $inv, impact: $imp) isa scilit-investigation-impact; '
                f'(impact: $imp, citing-paper: $cit) isa scilit-impact-citation;'
            ).resolve()
            tx.commit()
        coll_id = _ensure_investigation_collection(driver, args.investigation)
        add_to_collection(driver, citing_id, coll_id)
    print(json.dumps({
        "success": True,
        "impact_id": imp_id,
        "investigation": args.investigation,
        "impact_type": args.impact_type,
        "citing_paper": citing_id,
    }, indent=2))


def cmd_backfill_investigation_collection(args):
    """Backfill an investigation's paper collection from its existing aboutness
    links: focal paper (deep-dive), evidence source papers, and citing papers.
    Idempotent — safe to re-run."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            inv = list(tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.id)}"; '
                f'fetch {{ "id": $inv.id, "name": $inv.name }};'
            ).resolve())
        if not inv:
            print(json.dumps({"success": False, "error": "Investigation not found"}))
            sys.exit(1)
        inv_name = inv[0].get("name") or args.id
        coll_id = _ensure_investigation_collection(driver, args.id, inv_name)

        paper_ids = set()
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            # Focal paper (deep-dive): investigation -> aboutness -> scilit-paper.
            for r in tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.id)}"; '
                f'(note: $inv, subject: $p) isa alh-aboutness; $p isa scilit-paper; '
                f'fetch {{ "id": $p.id }};'
            ).resolve():
                paper_ids.add(r["id"])
            # Evidence source papers: inv -> claim -> evidence -> aboutness -> paper.
            for r in tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.id)}"; '
                f'(parent-note: $inv, child-note: $cl) isa alh-note-threading; $cl isa scilit-claim; '
                f'(parent-note: $cl, child-note: $ev) isa alh-note-threading; $ev isa scilit-evidence; '
                f'(note: $ev, subject: $p) isa alh-aboutness; $p isa scilit-paper; '
                f'fetch {{ "id": $p.id }};'
            ).resolve():
                paper_ids.add(r["id"])
            # Citing papers: inv -> citation-impact -> aboutness -> paper.
            for r in tx.query(
                f'match $inv isa scilit-investigation, has id "{escape_string(args.id)}"; '
                f'(parent-note: $inv, child-note: $imp) isa alh-note-threading; $imp isa scilit-citation-impact; '
                f'(note: $imp, subject: $p) isa alh-aboutness; $p isa scilit-paper; '
                f'fetch {{ "id": $p.id }};'
            ).resolve():
                paper_ids.add(r["id"])

        for pid in paper_ids:
            add_to_collection(driver, pid, coll_id)

    print(json.dumps({
        "success": True,
        "investigation": args.id,
        "collection": coll_id,
        "papers_added": len(paper_ids),
    }, indent=2))


def cmd_acquisition_worklist(args):
    """Citation-target registry for a citing paper: every cited reference with its
    acquisition status, genre, citation-load and (for needed papers) a DOI link
    the operator can use to download the PDF manually. Powers the dashboard
    download worklist. Defaults to the Hallmarks-2023 review."""
    citing = getattr(args, "citing", None) or "scilit-paper-21632e9ffb04"
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            rows = list(tx.query(
                'match $p isa scilit-paper, has scilit-acquisition-status $s; '
                'fetch { "id": $p.id, "name": $p.name, "doi": $p.scilit-doi, '
                '"status": $s, "genre": $p.scilit-target-genre, '
                '"load": $p.scilit-citation-load, "journal": $p.scilit-journal-name, '
                '"year": $p.scilit-publication-year, '
                '"refkeys": [ $p.scilit-reference-key ] };'
            ).resolve())

    prefix = f"{citing}:"
    items = []
    for r in rows:
        refkeys = [str(k) for k in (r.get("refkeys") or []) if k]
        mine = [k for k in refkeys if k.startswith(prefix)]
        if not mine:
            continue
        refnums = sorted(int(k.split(":")[-1]) for k in mine if k.split(":")[-1].isdigit())
        doi = r.get("doi")
        items.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "doi": doi,
            "doi_url": f"https://doi.org/{doi}" if doi else None,
            "status": r.get("status"),
            "genre": r.get("genre"),
            "load": r.get("load") or 0,
            "journal": r.get("journal"),
            "year": r.get("year"),
            "ref_numbers": refnums,
        })
    # needed first, then by citation-load desc, then ref number
    order = {"needed": 0, "held": 1, "ingested": 2, "rhetorical-done": 3, "sensemade": 4}
    items.sort(key=lambda x: (order.get(x["status"], 9), -(x["load"] or 0),
                              x["ref_numbers"][0] if x["ref_numbers"] else 9999))
    summary = {}
    for it in items:
        summary[it["status"]] = summary.get(it["status"], 0) + 1
    print(json.dumps({
        "success": True,
        "citing_paper": citing,
        "summary": summary,
        "total": len(items),
        "items": items,
    }, indent=2))


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scientific Literature CLI - multi-source paper search and ingestion"
    )
    # Global DB override (before the subcommand); threads through the gateway since it is
    # a plain arg. Lets the dashboard switch which TypeDB database it reads.
    parser.add_argument("--database", "--db", dest="database",
                        help="Override TYPEDB_DATABASE for this invocation")
    subparsers = parser.add_subparsers(dest="command")

    # list-databases (dashboard DB switcher)
    subparsers.add_parser("list-databases", help="List available TypeDB databases")

    # search
    p = subparsers.add_parser("search", help="Search a literature source and store results")
    p.add_argument("--source", required=True,
                   choices=["epmc", "pubmed", "openalex", "biorxiv", "medrxiv"],
                   help="Literature source to search")
    p.add_argument("--query", "-q", default="", help="Search query (required for epmc/pubmed/biorxiv; optional for openalex when --filter is used)")
    p.add_argument("--collection", "-c", help="Collection name (EPMC) or ID (others)")
    p.add_argument("--collection-id", help="Specific collection ID (EPMC: overrides auto-generated ID)")
    p.add_argument("--max-results", "-m", type=int, help="Maximum results to fetch")
    p.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="EPMC: results per page")
    p.add_argument("--filter", help="OpenAlex filter string (e.g. 'cites:W2565424224'); overrides --query for OpenAlex")

    # count
    p = subparsers.add_parser("count", help="Count EPMC results for a query (no storage)")
    p.add_argument("--query", "-q", required=True, help="EPMC search query")

    # ingest
    p = subparsers.add_parser("ingest", help="Fetch and store a paper by DOI or PMID")
    p.add_argument("--doi", help="DOI (with or without https://doi.org/ prefix)")
    p.add_argument("--pmid", help="PubMed ID")
    p.add_argument("--collection", help="Collection ID to add to")

    # fetch-pdf
    p = subparsers.add_parser("fetch-pdf",
        help="Download paper PDF, extract full text, store both to disk and TypeDB")
    p.add_argument("--id", required=True,
        help="scilit-paper TypeDB ID (e.g. scilit-paper-fd0a1617ef99)")
    p.add_argument("--url",
        help="Override PDF URL (default: derived from arXiv DOI)")
    p.add_argument("--file",
        help="Ingest a LOCAL PDF file already on disk (e.g. a manually downloaded paywalled paper) instead of downloading")
    p.add_argument("--force", action="store_true",
        help="Re-download/re-ingest even if artifact already exists")

    # parse-pdf-blocks (EXPERIMENTAL)
    p = subparsers.add_parser("parse-pdf-blocks",
        help="Re-extract canonical full text from the cached PDF with the layout-aware "
             "block parser (LA-PDFText-derived, PyMuPDF) — requires fetch-pdf first; "
             "updates the canonical fulltext artifact in place (preserves figures)")
    p.add_argument("--id", required=True,
        help="scilit-paper TypeDB ID (e.g. scilit-paper-fd0a1617ef99)")

    # extract-floats (EXPERIMENTAL)
    p = subparsers.add_parser("extract-floats",
        help="EXPERIMENTAL: render each figure/table to a PNG and store it as a "
             "scilit-figure/scilit-table fragment (caption-anchored + negative-space "
             "detection, PyMuPDF) — requires fetch-pdf to have run first")
    p.add_argument("--id", required=True,
        help="scilit-paper TypeDB ID (e.g. scilit-paper-abed567f5ca6)")

    # show
    p = subparsers.add_parser("show", help="Show a paper for sensemaking")
    p.add_argument("--id", required=True, help="Paper ID (scilit-paper-...)")

    p = subparsers.add_parser("set-citation",
        help="Set bibliographic citation fields (authors/volume/issue/pages) on a paper")
    p.add_argument("--id", required=True, help="Paper ID (scilit-paper-...)")
    p.add_argument("--authors", help="Author list, semicolon-delimited and order-preserving (e.g. 'Rong Y; Tang J')")
    p.add_argument("--journal", help="Journal name")
    p.add_argument("--volume", help="Journal volume")
    p.add_argument("--issue", help="Journal issue")
    p.add_argument("--pages", help="Page range (e.g. '1201-1217')")

    # list
    p = subparsers.add_parser("list", help="List papers in the knowledge graph")
    p.add_argument("--collection", help="Filter by collection ID")

    # list-collections
    subparsers.add_parser("list-collections", help="List all scilit search collections")

    # list-by-keyword
    p = subparsers.add_parser("list-by-keyword", help="List papers tagged with a keyword")
    p.add_argument("--keyword", "-k", required=True, help="Keyword tag to filter by")
    p.add_argument("--collection", "-c", help="Scope to this collection ID")
    p.add_argument("--year-from", type=int, dest="year_from", help="Earliest year (inclusive)")
    p.add_argument("--year-to", type=int, dest="year_to", help="Latest year (inclusive)")
    p.add_argument("--limit", "-n", type=int, help="Max results to return")

    # embed
    p = subparsers.add_parser("embed", help="Embed collection papers with Voyage AI into Qdrant")
    p.add_argument("--collection", required=True, help="Collection ID to embed")
    p.add_argument("--reembed", action="store_true", help="Re-embed even if paper already in Qdrant")
    p.add_argument("--limit", type=int, default=0, help="Max papers to embed (0=all)")

    # search-semantic
    p = subparsers.add_parser("search-semantic", help="Semantic similarity search via Qdrant")
    p.add_argument("--query", required=True, help="Natural language query")
    p.add_argument("--collection", help="Filter results to this collection ID")
    p.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    # cluster
    p = subparsers.add_parser("cluster", help="HDBSCAN clustering of collection embeddings")
    p.add_argument("--collection", required=True, help="Collection ID to cluster")
    p.add_argument("--min-cluster-size", type=int, default=15,
                   help="HDBSCAN min_cluster_size (default: 15)")
    p.add_argument("--dry-run", action="store_true",
                   help="Output cluster info without writing tags to TypeDB")
    p.add_argument("--labels", nargs="*",
                   help="Theme labels: 0:theme-name 1:other-theme ...")

    # plot-clusters
    p = subparsers.add_parser("plot-clusters", help="2D UMAP scatter plot coloured by cluster")
    p.add_argument("--collection", required=True, help="Collection ID")
    p.add_argument("--min-cluster-size", type=int, default=10,
                   help="HDBSCAN min_cluster_size (default: 10)")
    p.add_argument("--output", default="clusters.png", help="Output PNG path")
    p.add_argument("--labels", nargs="*", help="Theme labels: 0:theme-a 1:theme-b ...")

    # map
    p = subparsers.add_parser("map", help="2D UMAP embedding map (JSON) for the dashboard")
    p.add_argument("--collection", action="append",
                   help="Corpus ID to include (repeatable)")
    p.add_argument("--all", action="store_true", help="Include every scilit-corpus")
    p.add_argument("--min-cluster-size", type=int, default=10,
                   help="HDBSCAN min_cluster_size (default: 10)")

    # embed-sections
    p_embed_sections = subparsers.add_parser(
        "embed-sections",
        help="Embed scilit-section fragments for a paper into the apt-sections Qdrant collection",
    )
    p_embed_sections.add_argument("--paper-id", required=True,
        help="scilit-paper TypeDB ID (e.g. scilit-paper-abc123)")
    p_embed_sections.add_argument("--collection", default=APT_SECTIONS_COLLECTION,
        help=f"Qdrant collection name (default: {APT_SECTIONS_COLLECTION})")
    p_embed_sections.add_argument("--tag-mondo-id", default="",
        help="MONDO ID to tag all sections with (e.g. MONDO:0100135)")
    p_embed_sections.set_defaults(func=cmd_embed_sections)

    # search-sections
    p_search_sections = subparsers.add_parser(
        "search-sections",
        help="Semantic search over scilit-section fragments in the apt-sections Qdrant collection",
    )
    p_search_sections.add_argument("--query", required=True,
        help="Natural language query")
    p_search_sections.add_argument("--collection", default=APT_SECTIONS_COLLECTION,
        help=f"Qdrant collection name (default: {APT_SECTIONS_COLLECTION})")
    p_search_sections.add_argument("--mondo-id", default="",
        help="Filter results to sections tagged with this MONDO ID")
    p_search_sections.add_argument("--top-k", type=int, default=10,
        help="Number of results to return (default: 10)")
    p_search_sections.set_defaults(func=cmd_search_sections)

    # create-investigation
    p = subparsers.add_parser("create-investigation",
        help="Create a named investigation (corpus or deep-dive)")
    p.add_argument("--type", choices=["corpus", "deep-dive"], default="corpus",
        help="Investigation type (default: corpus)")
    p.add_argument("--collection", help="scilit-corpus ID (required for --type corpus)")
    p.add_argument("--paper", help="Focal paper DOI or scilit-paper ID (required for --type deep-dive)")
    p.add_argument("--name", required=True, help="Investigation title")
    p.add_argument("--purpose", required=True, help="Purpose/goal (markdown) -> note content")
    p.add_argument("--status", help="Initial lifecycle status (default: scoping)")

    # ground-entity / list-ungrounded
    p = subparsers.add_parser("ground-entity",
        help="Ground one entity to an ontology term using an investigation's grounding policy")
    p.add_argument("--id", required=True, help="Entity ID (scilit-bioentity-... / scilit-entity-...)")
    p.add_argument("--investigation", required=True, help="Investigation ID (supplies the grounding policy)")
    p.add_argument("--kind", required=True, help="Entity kind (must be a key in the policy's kinds map)")
    p.add_argument("--mention", help="Override the mention text (default: the entity's name)")
    p = subparsers.add_parser("list-ungrounded", help="List entities not yet grounded")
    p = subparsers.add_parser("survey-entities",
        help="Survey entity mentions vs an investigation's grounding policy (coverage + worklist; dry-run)")
    p.add_argument("--investigation", required=True, help="Investigation ID (supplies the grounding policy)")
    p.add_argument("--limit", type=int, default=0, help="Cap distinct mentions surveyed (0 = all)")
    p = subparsers.add_parser("ground-predicates",
        help="Ground relationship types: set scilit-predicate-curie on mech-links from mech-type (RO)")
    p = subparsers.add_parser("analyze-investigation",
        help="Synthesize grounded mechanism edges into stance-bearing synthesis notes")
    p.add_argument("--id", required=True, help="Investigation ID")
    p = subparsers.add_parser("show-synthesis",
        help="Read an investigation's KQED analysis (question + synthesis notes + grounded edges)")
    p.add_argument("--id", required=True, help="Investigation ID")

    # frame-investigation
    p = subparsers.add_parser("frame-investigation",
        help="Capture an investigation's goals: question + grounding policy (stored in the KG)")
    p.add_argument("--id", required=True, help="Investigation ID (scinv-...)")
    p.add_argument("--question", required=True, help="The investigation's driving question/goal")
    p.add_argument("--policy", help="Grounding policy: path to a JSON file, or inline JSON (domain profile)")

    # list-investigations
    p = subparsers.add_parser("list-investigations",
        help="List investigations with status + phase count")
    p.add_argument("--collection", help="Scope to one corpus ID")

    # show-investigation
    p = subparsers.add_parser("show-investigation",
        help="Show an investigation, its phases (canonical order), and analysis links")
    p.add_argument("--id", required=True, help="Investigation ID (scinv-...)")

    # record-phase
    p = subparsers.add_parser("record-phase",
        help="Upsert a phase note (discovery|ingest|sensemaking|analysis|report)")
    p.add_argument("--investigation", required=True, help="Investigation ID (scinv-...)")
    p.add_argument("--phase", required=True, choices=INVESTIGATION_PHASES, help="Stage name")
    p.add_argument("--content", required=True, help="Stage findings (markdown)")
    p.add_argument("--iteration", type=int, default=1, help="Iteration/cycle number (default 1)")
    p.add_argument("--status", help="Optionally advance the investigation status")

    # link-analysis
    p = subparsers.add_parser("link-analysis",
        help="Thread a faceting note under the investigation's analysis phase")
    p.add_argument("--investigation", required=True, help="Investigation ID (scinv-...)")
    p.add_argument("--faceting-note", required=True, dest="faceting_note",
        help="scilit-faceting-note ID (scfn-...)")

    # set-status
    p = subparsers.add_parser("set-status", help="Set an investigation's lifecycle status")
    p.add_argument("--investigation", required=True, help="Investigation ID (scinv-...)")
    p.add_argument("--status", required=True, help="New status value")

    # --- SENSEMAKING stage: per-paper bundles ---
    # create-bundle
    p = subparsers.add_parser("create-bundle",
        help="Create a per-paper sensemaking bundle in an investigation's sensemaking stage")
    p.add_argument("--investigation", required=True, help="Investigation ID (scinv-...)")
    p.add_argument("--paper", required=True, help="Paper id or DOI")
    p.add_argument("--iteration", type=int, default=1, help="Iteration/cycle number (default 1)")
    p.add_argument("--name", help="Bundle name (optional)")

    # add-observation
    p = subparsers.add_parser("add-observation",
        help="Add an observation (measurement-in-context) to a sensemaking bundle")
    p.add_argument("--bundle", required=True, help="Bundle id (scsense-...)")
    p.add_argument("--statement", required=True, help="The observation text")
    p.add_argument("--knowledge-level", required=True, dest="knowledge_level",
        help="observation|association|assertion|prediction")
    p.add_argument("--bio-scale", required=True, dest="bio_scale",
        help="molecular|cellular|tissue|organism")
    p.add_argument("--name", help="Short name (optional)")
    p.add_argument("--source-label", dest="source_label",
        help="Evidence source-locator (e.g. OF4DF=Fig4 panels D,F; OSF3B=Suppl Fig3 B; "
             "OT2=Table2; OE5=Experiment5; OX=text-only). Becomes the observation name. "
             "See docs/observation-source-labeling.md")
    p.add_argument("--experiment-type", dest="experiment_type",
        help="KEfED design frame: the experiment/assay type (creates a kefed-model)")
    p.add_argument("--variables",
        help='KEfED design variables: JSON list of {"name","role","values"?,"efo"?}; '
             'role in parameter|constant|measurement')

    # add-mechanism (System-3 mechanistic edge)
    p = subparsers.add_parser("add-mechanism",
        help="Add a mechanistic edge (source --[type]--> target) to a sensemaking bundle")
    p.add_argument("--bundle", required=True, help="Bundle id (scsense-...)")
    p.add_argument("--source", required=True, help="Source bioentity label")
    p.add_argument("--target", required=True, help="Target bioentity label")
    p.add_argument("--type", required=True, help="Mechanism type: activates|inhibits|maintains|suppresses")
    p.add_argument("--confidence", help="Optional confidence 0..1")
    p.add_argument("--claim", help="Optional reported-claim id that asserts this mechanism")

    # ground-bundle
    p = subparsers.add_parser("ground-bundle",
        help="Ground a bundle's KEfED variables + bioentities to ontology terms (curie+confidence)")
    p.add_argument("--bundle", required=True, help="Bundle id (scsense-...)")
    p.add_argument("--limit", type=int, help="Cap number of terms grounded (for testing)")
    p.add_argument("--reground", action="store_true", help="Re-ground terms that already have a state")

    # --- OOEVV / KEfED protocol-graph curation ---
    p = subparsers.add_parser("ensure-quality", help="Find-or-create a reusable curated quality")
    p.add_argument("--name", required=True, help="Quality name (concentration, signal-intensity...)")
    p.add_argument("--definition", help="Curated definition (plain-English, undergraduate-level: what it is + what it does)")
    p.add_argument("--long-form", dest="long_form", help="Expanded form of an abbreviated name (e.g. 'LSK' -> 'Lineage-negative, Sca-1+, c-Kit+')")
    p.add_argument("--curie", help="VERIFIED ontology curie (e.g. PATO:0000011). Attach ONLY if the term's definition matches; else omit -> stays ungrounded.")
    p.add_argument("--grounding-label", dest="grounding_label", help="Canonical label of the grounded ontology term")

    p = subparsers.add_parser("ensure-value-spec",
        help="Find-or-create a named reusable value-specification (scale) that a Quality can take")
    p.add_argument("--quality", required=True, help="ooevv-quality id (scqual-...) this value-spec is canonical for")
    p.add_argument("--name", required=True, help="Value-spec name (e.g. 'age (young/old)')")
    p.add_argument("--scale-type", required=True, dest="scale_type", help="nominal|binary|ordinal|numeric|file|composite")
    p.add_argument("--values", help="Pipe-separated allowed values (nominal/binary) or ORDERED ranks (ordinal)")
    p.add_argument("--unit", help="Numeric scale unit")
    p.add_argument("--min", help="Numeric scale min")
    p.add_argument("--max", help="Numeric scale max")
    p.add_argument("--definition", help="Curated definition (undergraduate-level)")
    p.add_argument("--long-form", dest="long_form")
    p.add_argument("--curie", help="VERIFIED curie (e.g. unit UO:0000033); attach only if correct, else omit")

    p = subparsers.add_parser("list-value-specs", help="RECOGNITION: list value-specifications (optionally for one quality)")
    p.add_argument("--quality", help="Filter to one quality id")
    p.add_argument("--match", help="Case-insensitive substring filter on name")

    p = subparsers.add_parser("ensure-entity", help="Find-or-create a reusable curated entity (specificity/material target)")
    p.add_argument("--name", required=True, help="Entity name (SIRT3, dasatinib, HSC...)")
    p.add_argument("--kind", help="gene|protein|chemical|cell-type|tissue|organism|reagent...")
    p.add_argument("--definition", help="Curated definition (plain-English, undergraduate-level: what it is + what it does)")
    p.add_argument("--long-form", dest="long_form", help="Expanded form of an abbreviated name (e.g. 'LSK' -> 'Lineage-negative, Sca-1+, c-Kit+')")

    p = subparsers.add_parser("add-experiment", help="Create one experiment (element-set) under a bundle")
    p.add_argument("--bundle", required=True, help="Bundle id (scsense-...)")
    p.add_argument("--name", required=True, help="Experiment label (e.g. 'Fig 1: SIRT3 expression')")
    p.add_argument("--definition", help="Curated definition of the experiment (undergraduate-level)")
    p.add_argument("--long-form", dest="long_form", help="Expanded form of an abbreviated experiment name")
    p.add_argument("--element-set", dest="element_set", help="Reuse an existing ooevv-element-set id")

    p = subparsers.add_parser("add-process", help="Add a protocol step to an experiment OR template (hierarchical via --parent)")
    p.add_argument("--experiment", help="Experiment id (scexp-...)")
    p.add_argument("--template", help="Template id (sctpl-...) — add the step to a reusable design instead")
    p.add_argument("--name", required=True, help="Process/step name")
    p.add_argument("--type", required=True, help="assay|material-processing|data-transformation")
    p.add_argument("--parent", help="Parent process id (nest as sub-process)")
    p.add_argument("--definition", help="Curated definition (plain-English, undergraduate-level: what it is + what it does)")
    p.add_argument("--long-form", dest="long_form", help="Expanded form of an abbreviated name (e.g. 'LSK' -> 'Lineage-negative, Sca-1+, c-Kit+')")

    p = subparsers.add_parser("add-entity-node",
        help="Add an entity node (ooevv-material-entity def + kefed-model-node) to an experiment or template")
    p.add_argument("--experiment", help="Experiment id (scexp-...)")
    p.add_argument("--template", help="Template id (sctpl-...)")
    p.add_argument("--name", required=True, help="Entity name (e.g. 'SIRT3 cell line')")
    p.add_argument("--subject", action="store_true", help="Mark as model subject via ooevv-subject")
    p.add_argument("--definition", help="Curated definition (plain-English, undergraduate-level)")

    p = subparsers.add_parser("link-entity",
        help="[DEPRECATED — use link-nodes] Link two kefed-model-nodes as input|output")
    p.add_argument("--from-node", dest="from_node", required=True, help="Source kefed-model-node id")
    p.add_argument("--to-node", dest="to_node", required=True, help="Target kefed-model-node id")
    p.add_argument("--role", required=True, help="input|output")

    p = subparsers.add_parser("link-nodes",
        help="Connect two kefed-model-nodes via ooevv-process-input (role=input) or ooevv-process-output "
             "(role=output). Enforces the bipartite bigraph (entity<->process); use --force to override.")
    p.add_argument("--from-node", dest="from_node", required=True, help="Source kefed-model-node id")
    p.add_argument("--to-node", dest="to_node", required=True, help="Target kefed-model-node id")
    p.add_argument("--role", required=True, help="input (entity->process) | output (process->entity)")
    p.add_argument("--force", action="store_true",
        help="Override the bipartite/direction check (records a non-well-formed edge anyway)")

    p = subparsers.add_parser("add-variable",
        help="Add an OOEVV experimental-variable (role + quality + scale) to a kefed-model-node")
    p.add_argument("--node", required=True, help="kefed-model-node id to attach the variable to")
    p.add_argument("--name", required=True, help="Variable name")
    p.add_argument("--role", required=True, help="parameter|constant|measurement")
    p.add_argument("--value-spec", dest="value_spec",
        help="REFERENCE a shared value-spec id (ooevv-scale). Its quality is used; --quality/--scale-type not needed. Preferred (reuse).")
    p.add_argument("--quality", help="ooevv-quality id (scqual-...) — required unless --value-spec is given")
    p.add_argument("--scale-type", dest="scale_type",
        help="nominal|binary|ordinal|numeric|file|composite — required unless --value-spec is given")
    p.add_argument("--unit", help="Numeric scale unit")
    p.add_argument("--min", help="Numeric scale min")
    p.add_argument("--max", help="Numeric scale max")
    p.add_argument("--values", help="Pipe-separated allowed values (nominal/binary) or ordered ranks (ordinal)")
    p.add_argument("--definition", help="Curated definition (plain-English, undergraduate-level: what it is + what it does)")
    p.add_argument("--long-form", dest="long_form",
        help="Expanded form of an abbreviated name (e.g. 'LSK' -> 'Lineage-negative, Sca-1+, c-Kit+')")

    p = subparsers.add_parser("bind-parameter",
        help="Bind a parameter at a kefed-model-node (idempotent kefed-node-variable; + optional specificity target)")
    p.add_argument("--node", required=True, help="kefed-model-node id")
    p.add_argument("--parameter", required=True, help="Parameter variable id (scvar-...)")
    p.add_argument("--target-entity", dest="target_entity",
        help="kefed-model-node id the parameter targets (specificity via ooevv-parameter-target)")

    p = subparsers.add_parser("map-params",
        help="Declare a data-transformation's input->output parameter mapping (ooevv-param-mapping) so "
             "the data signature is computed correctly (e.g. a correlation CONSUMES the per-sample index)")
    p.add_argument("--transformation", required=True, help="data-transformation node id (knode-...)")
    p.add_argument("--rule", required=True,
        help="passthrough | aggregate-collapse-destroy | combine | derive")
    p.add_argument("--in", dest="in_params",
        help="Comma-separated input parameter var ids (passthrough:1, aggregate-collapse-destroy:>=1, "
             "combine:>=2, derive:none)")
    p.add_argument("--out", dest="out_param",
        help="Output parameter var id (required for passthrough/combine/derive; omitted for "
             "aggregate-collapse-destroy)")

    # --- KEfED model-EDIT verbs (correct an existing model in place) ---
    p = subparsers.add_parser("rename-node",
        help="Rename a node (and its sole-use OOEVV def) — e.g. make an over-specific entity name generic")
    p.add_argument("--node", required=True, help="kefed-model-node id (knode-...)")
    p.add_argument("--name", required=True, help="New generic name")

    p = subparsers.add_parser("retype-node",
        help="Change a node's OOEVV type in place (variables + flow edges survive) — e.g. retype a "
             "measurement-bearing 'result' entity into the data-transformation that produced it")
    p.add_argument("--node", required=True, help="kefed-model-node id (knode-...)")
    p.add_argument("--type", required=True, help="material-entity|assay|material-processing|data-transformation")
    p.add_argument("--name", help="Optionally rename the node at the same time")

    p = subparsers.add_parser("move-variable",
        help="Move a variable (measurement/parameter/constant) to another node — e.g. canonicalize a "
             "measurement onto the measuring process, or a specialization param onto its generating process")
    p.add_argument("--variable", required=True, help="ooevv-variable id (scvar-...)")
    p.add_argument("--to-node", dest="to_node", required=True, help="Destination kefed-model-node id")

    p = subparsers.add_parser("delete-node",
        help="Delete a node (detaches type/membership/flow edges). Refuses if it still carries variables unless --force")
    p.add_argument("--node", required=True, help="kefed-model-node id (knode-...)")
    p.add_argument("--force", action="store_true", help="Detach (orphan) any remaining variables and delete anyway")

    p = subparsers.add_parser("set-node-definition",
        help="Set/replace the plain-English definition on a node's OOEVV def")
    p.add_argument("--node", required=True, help="kefed-model-node id (knode-...)")
    p.add_argument("--definition", required=True, help="Curated plain-English definition")

    # --- KEfED template / instance / data (curation by recognize-reuse-fill) ---
    p = subparsers.add_parser("ensure-template", help="Find-or-create a reusable experiment-design template")
    p.add_argument("--name", required=True, help="Template name (e.g. 'qPCR expression profiling')")
    p.add_argument("--definition", help="Curated definition of the design (undergraduate-level: what the assay measures + how)")
    p.add_argument("--long-form", dest="long_form", help="Expanded form of an abbreviated template name")
    p.add_argument("--element-set", dest="element_set", help="Reuse an existing ooevv-element-set id")

    p = subparsers.add_parser("list-templates", help="RECOGNITION/gap-check: list reusable templates (+ counts)")
    p.add_argument("--match", help="Case-insensitive substring filter on name/definition")

    p = subparsers.add_parser("list-qualities", help="RECOGNITION/gap-check: list curated qualities")
    p.add_argument("--match", help="Case-insensitive substring filter on name/definition")

    p = subparsers.add_parser("list-entities", help="RECOGNITION/gap-check: list curated entities")
    p.add_argument("--match", help="Case-insensitive substring filter on name/definition")

    p = subparsers.add_parser("audit-terms",
        help="LINTER: flag OOEVV terms with missing/short definitions or unexpanded abbreviations")
    p.add_argument("--type", choices=["quality", "entity", "process", "variable"],
        help="Restrict the audit to one element type")
    p.add_argument("--min-def-len", dest="min_def_len", type=int,
        help="Minimum acceptable definition length in characters (default 40)")

    p = subparsers.add_parser("instantiate-template", help="FILL: create an instance of a template under a bundle")
    p.add_argument("--bundle", required=True, help="Bundle id (scsense-...)")
    p.add_argument("--template", required=True, help="Template id (sctpl-...)")
    p.add_argument("--name", help="Instance label (optional)")

    p = subparsers.add_parser("add-datum", help="FILL: add one data row (cells + provenance observation) to an instance")
    p.add_argument("--instance", required=True, help="Instance id (scinst-...)")
    p.add_argument("--cells", required=True,
        help='JSON list of {"variable": <id>, "value": <str>, "number"?: <float>, "n"?: <float>, '
             '"error"?: <float>, "error_type"?: "sd|sem|ci95|range|iqr", "unit"?: <str>}')
    p.add_argument("--observation", help="Link an existing scilit-observation id (provenance)")
    p.add_argument("--gloss", help="Create a provenance observation inline (prose gloss + source quote)")
    p.add_argument("--knowledge-level", dest="knowledge_level", help="(inline obs) default 'observation'")
    p.add_argument("--bio-scale", dest="bio_scale", help="(inline obs) default 'molecular'")

    p = subparsers.add_parser("set-cell",
        help="Upsert one variable's cell across an instance's rows (or one --datum): backfill "
             "n/error/error_type/unit or a newly-added variable's value without rebuilding rows")
    p.add_argument("--instance", help="Instance id (scinst-...) — apply to ALL its data rows")
    p.add_argument("--datum", help="Single data row id (scdatum-...) — scope to one row")
    p.add_argument("--variable", required=True, help="ooevv-variable id (scvar-...) the cell holds")
    p.add_argument("--value", help="Cell string value (required when creating a new cell)")
    p.add_argument("--number", type=float, help="Numeric form of the value")
    p.add_argument("--n", type=float, help="Sample size behind this readout")
    p.add_argument("--error", type=float, help="Dispersion magnitude")
    p.add_argument("--error-type", dest="error_type", help="sd|sem|ci95|range|iqr")
    p.add_argument("--unit", help="Per-row unit of the value")

    # add-reported-claim
    p = subparsers.add_parser("add-reported-claim",
        help="Add a reported-claim (asserted within the paper) to a sensemaking bundle")
    p.add_argument("--bundle", required=True, help="Bundle id (scsense-...)")
    p.add_argument("--type", required=True, choices=CLAIM_TYPES, help="Claim type")
    p.add_argument("--statement", required=True, help="Claim text")
    p.add_argument("--rhetorical-role", dest="rhetorical_role",
        help="AZ zone: background|own-claim|own-method|own-result|contrast|basis|implication")
    p.add_argument("--cites", help="Comma-separated paper ids this claim cites (citation hinges)")
    p.add_argument("--observations", help="Comma-separated observation ids that support it")

    p = subparsers.add_parser("link-claim-observation",
        help="Link an existing reported-claim to a supporting observation (idempotent)")
    p.add_argument("--claim", required=True, help="scilit-claim id (screp-...)")
    p.add_argument("--observation", required=True, help="scilit-observation id (scobs-...)")

    p = subparsers.add_parser("link-datum-observation",
        help="Link an observation to the data row it interprets (kefed-datum-observation), completing "
             "claim -> observation -> datum -> instance -> model")
    p.add_argument("--observation", required=True, help="scilit-observation id (scobs-...)")
    p.add_argument("--datum", required=True, help="data row id (scdatum-...)")

    p = subparsers.add_parser("anchor-note",
        help="Span-anchor a note (claim/observation/gap) to a verbatim quote in the paper's full text "
             "(creates a fragment + alh-derivation)")
    p.add_argument("--note", required=True, help="note id (screp-/scobs-/scgap-...)")
    p.add_argument("--paper", required=True, help="paper id (scilit-paper-...)")
    p.add_argument("--quote", required=True, help="verbatim text span from the full text")
    p.add_argument("--force", action="store_true", help="anchor even if the quote isn't located (offset -1)")

    # add-reported-gap
    p = subparsers.add_parser("add-reported-gap",
        help="Add a reported-gap (a gap stated within the paper) to a sensemaking bundle")
    p.add_argument("--bundle", required=True, help="Bundle id (scsense-...)")
    p.add_argument("--statement", required=True, help="Gap text")
    p.add_argument("--goal", required=True, help="The knowledge-goal it implies")

    # show-stage (dashboard: investigation stage content)
    p = subparsers.add_parser("show-stage",
        help="Show one investigation stage (phase) with kind-specific data")
    p.add_argument("--id", required=True, help="Stage/phase id (scphase-...)")

    # show-paper-curation (dashboard: single-paper 5-layer walkthrough payload)
    p = subparsers.add_parser("show-paper-curation",
        help="One-shot curation walkthrough payload for a single paper (all layers)")
    p.add_argument("--id", required=True, help="Paper id (scilit-paper-...)")

    # lint-sensemaking (linter: verify a paper's KQED/KEfED/OOEVV curation is well-formed)
    p = subparsers.add_parser("lint-sensemaking",
        help="Run curation checks over a paper's sensemaking bundle (pass/warn/fail)")
    p.add_argument("--id", required=True, help="Paper id (scilit-paper-...)")

    # lint-investigation (verifier: discovery description + ingestion corpora/papers/full-text)
    p = subparsers.add_parser("lint-investigation",
        help="Run process checks over an investigation (discovery + ingestion)")
    p.add_argument("--id", required=True, help="Investigation id (scinv-...)")

    # show-bundle
    p = subparsers.add_parser("show-bundle", help="Show one per-paper sensemaking bundle in full")
    p.add_argument("--id", required=True, help="Bundle id (scsense-...)")

    p = subparsers.add_parser("show-experiment", help="Show one experiment's full KEfED protocol graph")
    p.add_argument("--id", required=True, help="Experiment id (scexp-...)")
    p.add_argument("--format", choices=["json", "hgraph"], default="json",
        help="json (default) | hgraph (Bolinas-style hypergraph term, for the future SHRG layer)")

    p = subparsers.add_parser("show-template", help="Show one reusable template (design graph + slots + variables)")
    p.add_argument("--id", required=True, help="Template id (sctpl-...)")

    p = subparsers.add_parser("show-instance", help="Show one template instance (filled slots + data spreadsheet)")
    p.add_argument("--id", required=True, help="Instance id (scinst-...)")

    p = subparsers.add_parser("show-data-signature",
        help="Show data signature (index sets) for each measurement variable in a KEfED model")
    p.add_argument("--model", "--experiment", dest="model", required=True,
        help="KEfED model id (kefedm-...)")

    # --- ANALYSIS stage: synthesized claims + evidence warrants ---
    # add-synthesized-claim
    p = subparsers.add_parser("add-synthesized-claim",
        help="Add a synthesized-claim (cross-paper, analysis) to an investigation")
    p.add_argument("--investigation", required=True, help="Investigation ID (scinv-...)")
    p.add_argument("--type", required=True, choices=CLAIM_TYPES, help="Claim type")
    p.add_argument("--statement", required=True, help="Precise, falsifiable claim text")

    # add-evidence (warrant)
    p = subparsers.add_parser("add-evidence",
        help="Add an evidence WARRANT (argument + confidence) supporting a synthesized-claim")
    p.add_argument("--claim-id", required=True, dest="claim_id", help="Synthesized-claim id (scsynth-...)")
    p.add_argument("--argument", required=True, help="Reasoned argument over the grounding reported-claims")
    p.add_argument("--confidence", required=True, help="Confidence score 0..1")
    p.add_argument("--grounds", help="Comma-separated reported-claim ids this warrant rests on")
    p.add_argument("--instances", help="Comma-separated kefed-instance ids whose data rows this warrant rests on")
    p.add_argument("--evidence-type", dest="evidence_type", choices=EVIDENCE_TYPES,
        help="Optional evidence-type qualifier")

    # add-citation-impact (deep-dive)
    p = subparsers.add_parser("add-citation-impact",
        help="Record how a citing paper received the focal paper")
    p.add_argument("--investigation", required=True, help="Investigation ID (scinv-...)")
    p.add_argument("--citing-doi", dest="citing_doi", help="Citing paper DOI (found-or-ingested)")
    p.add_argument("--citing-id", dest="citing_id", help="Citing scilit-paper ID")
    p.add_argument("--impact-type", required=True, dest="impact_type",
        choices=IMPACT_TYPES, help="Impact type")
    p.add_argument("--impact-summary", required=True, dest="impact_summary",
        help="1-2 sentence description")

    # export-investigation
    p = subparsers.add_parser("export-investigation",
        help="Export an investigation as markdown or JSON")
    p.add_argument("--id", required=True, help="Investigation ID (scinv-...)")
    p.add_argument("--format", choices=["md", "json"], default="md", help="Output format")

    # backfill-investigation-collection
    p = subparsers.add_parser("backfill-investigation-collection",
        help="Rebuild an investigation's paper collection from existing aboutness links")
    p.add_argument("--id", required=True, help="Investigation ID (scinv-...)")

    # acquisition-worklist
    p = subparsers.add_parser("acquisition-worklist",
        help="Citation-target registry / download worklist for a citing paper")
    p.add_argument("--citing", help="Citing paper ID (default: Hallmarks-2023 review)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Apply the global DB override (module-level attr read by get_driver et al.)
    if getattr(args, "database", None):
        globals()["TYPEDB_DATABASE"] = args.database

    SEMANTIC_COMMANDS = {"embed", "search-semantic", "cluster", "plot-clusters", "map",
                         "embed-sections", "search-sections"}
    NON_DB_COMMANDS = {"count"} | SEMANTIC_COMMANDS

    if args.command not in NON_DB_COMMANDS:
        if not TYPEDB_AVAILABLE:
            print(json.dumps({"success": False, "error": "typedb-driver not installed"}))
            sys.exit(1)

    if args.command not in SEMANTIC_COMMANDS and not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed. Run: uv add requests"}))
        sys.exit(1)

    commands = {
        "search": cmd_search,
        "count": cmd_count,
        "ingest": cmd_ingest,
        "fetch-pdf": cmd_fetch_pdf,
        "parse-pdf-blocks": cmd_parse_pdf_blocks,
        "extract-floats": cmd_extract_floats,
        "show": cmd_show,
        "set-citation": cmd_set_citation,
        "list": cmd_list,
        "list-collections": cmd_list_collections,
        "list-by-keyword": cmd_list_by_keyword,
        "embed": cmd_embed,
        "search-semantic": cmd_search_semantic,
        "cluster": cmd_cluster,
        "plot-clusters": cmd_plot_clusters,
        "map": cmd_map,
        "embed-sections": cmd_embed_sections,
        "search-sections": cmd_search_sections,
        "create-investigation": cmd_create_investigation,
        "frame-investigation": cmd_frame_investigation,
        "ground-entity": cmd_ground_entity,
        "list-ungrounded": cmd_list_ungrounded,
        "survey-entities": cmd_survey_entities,
        "ground-predicates": cmd_ground_predicates,
        "analyze-investigation": cmd_analyze_investigation,
        "show-synthesis": cmd_show_synthesis,
        "list-investigations": cmd_list_investigations,
        "show-investigation": cmd_show_investigation,
        "record-phase": cmd_record_phase,
        "link-analysis": cmd_link_analysis,
        "set-status": cmd_set_status,
        "create-bundle": cmd_create_bundle,
        "add-observation": cmd_add_observation,
        "add-mechanism": cmd_add_mechanism,
        "ground-bundle": cmd_ground_bundle,
        "ensure-quality": cmd_ensure_quality,
        "ensure-value-spec": cmd_ensure_value_spec,
        "list-value-specs": cmd_list_value_specs,
        "ensure-entity": cmd_ensure_entity,
        "add-experiment": cmd_add_experiment,
        "add-entity-node": cmd_add_entity_node,
        "add-process": cmd_add_process,
        "link-entity": cmd_link_nodes,   # deprecated alias — routes to cmd_link_nodes
        "link-nodes": cmd_link_nodes,
        "add-variable": cmd_add_variable,
        "bind-parameter": cmd_bind_parameter,
        "map-params": cmd_map_params,
        "rename-node": cmd_rename_node,
        "retype-node": cmd_retype_node,
        "move-variable": cmd_move_variable,
        "delete-node": cmd_delete_node,
        "set-node-definition": cmd_set_node_definition,
        "ensure-template": cmd_ensure_template,
        "list-templates": cmd_list_templates,
        "list-qualities": cmd_list_qualities,
        "list-entities": cmd_list_entities,
        "audit-terms": cmd_audit_terms,
        "instantiate-template": cmd_instantiate_template,
        "add-datum": cmd_add_datum,
        "set-cell": cmd_set_cell,
        "add-reported-claim": cmd_add_reported_claim,
        "link-claim-observation": cmd_link_claim_observation,
        "link-datum-observation": cmd_link_datum_observation,
        "anchor-note": cmd_anchor_note,
        "add-reported-gap": cmd_add_reported_gap,
        "list-databases": cmd_list_databases,
        "show-stage": cmd_show_stage,
        "show-paper-curation": cmd_show_paper_curation,
        "lint-sensemaking": cmd_lint_sensemaking,
        "lint-investigation": cmd_lint_investigation,
        "show-bundle": cmd_show_bundle,
        "show-experiment": cmd_show_experiment,
        "show-template": cmd_show_template,
        "show-instance": cmd_show_instance,
        "show-data-signature": cmd_show_data_signature,
        "add-synthesized-claim": cmd_add_synthesized_claim,
        "add-evidence": cmd_add_evidence,
        "add-citation-impact": cmd_add_citation_impact,
        "export-investigation": cmd_export_investigation,
        "backfill-investigation-collection": cmd_backfill_investigation_collection,
        "acquisition-worklist": cmd_acquisition_worklist,
    }

    try:
        commands[args.command](args)
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
