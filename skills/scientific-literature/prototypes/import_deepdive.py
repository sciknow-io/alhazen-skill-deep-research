#!/usr/bin/env python3
"""
Generic importer for an agent-produced KQED deep-dive record of a primary paper.

Persists, idempotently, under a per-paper deep-dive investigation:
  claims (one flagged origin), observations (each via a kefed-model, carrying
  knowledge-level + bio-scale), gaps, and a System-3 mechanistic graph.
Then sets the paper's acquisition-status -> "sensemade" and, for every review
citing-claim that cites this paper (paper-level hinge), adds the CLAIM-LEVEL
hinge review-claim --[CFC]--> origin-claim. That is the review->origin mapping
the whole exercise is about, now created automatically at scale.

Used by the WF2 deep-dive workflow's persistence step (called from the main loop).
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kqed as K
from kqed import escape_string, get_timestamp

EXPTYPE_VOCAB = "vocab-kefed-exptype"


def _slug(s, n=24):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:n] or "x"


def _set_single(d, pid, attr, value):
    if K._has(d, f'$p isa scilit-paper, has id "{pid}", has {attr} "{escape_string(value)}";'):
        return
    if K._has(d, f'$p isa scilit-paper, has id "{pid}", has {attr} $v;'):
        K.w(d, f'match $p isa scilit-paper, has id "{pid}", has {attr} $v; delete has $v of $p;')
    K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has {attr} "{escape_string(value)}";')


def _ensure_investigation(d, inv_id, title, paper_id):
    if K._exists(d, inv_id):
        return inv_id
    ts = get_timestamp()
    K.w(d, f'insert $i isa scilit-investigation, has id "{inv_id}", '
           f'has name "{escape_string("Deep dive (KQED): " + title[:90])}", '
           f'has scilit-investigation-status "analysis", has scilit-investigation-type "deep-dive", '
           f'has created-at {ts};')
    K.w(d, f'match $i isa scilit-investigation, has id "{inv_id}"; $p isa scilit-paper, has id "{paper_id}"; '
           f'insert (note: $i, subject: $p) isa alh-aboutness;')
    return inv_id


def _ensure_exptype_term(d, label, doi):
    """Create/lookup an experiment-type vocab term (grows the curated library)."""
    tid = f"exp-{_slug(label)}"
    if not K._exists(d, tid):
        try:
            K.add_vocab_term(d, EXPTYPE_VOCAB, label, tid=tid,
                             provenance=f"observed in {doi}")
        except Exception:
            return None
    return tid


def import_record(d, paper_id, doi, title, record):
    inv = _ensure_investigation(d, f"scinv-dd-{paper_id.split('-')[-1]}", title, paper_id)
    out = {"paper": paper_id, "investigation": inv, "claims": 0, "observations": 0,
           "gaps": 0, "mech_links": 0, "claim_level_hinges": 0}

    # ---- claims ----
    origin_claim = None
    claims = record.get("claims", [])
    for c in claims:
        key = c.get("key") or _slug(c.get("statement", ""), 8)
        cid = f"scclaim-dd-{paper_id.split('-')[-1]}-{key}"
        stmt = (c.get("statement") or "").strip()
        if not stmt:
            continue
        if not K._exists(d, cid):
            ts = get_timestamp()
            K.w(d, f'match $inv isa scilit-investigation, has id "{inv}"; '
                   f'insert $c isa scilit-claim, has id "{cid}", has name "{escape_string(stmt[:60])}", '
                   f'has scilit-claim-type "{escape_string(c.get("type","primary"))}", '
                   f'has scilit-claim-statement "{escape_string(stmt)}", has created-at {ts}; '
                   f'(parent-note: $inv, child-note: $c) isa alh-note-threading;')
            K.w(d, f'match $c isa scilit-claim, has id "{cid}"; $p isa scilit-paper, has id "{paper_id}"; '
                   f'insert (note: $c, subject: $p) isa alh-aboutness;')
            out["claims"] += 1
        if c.get("is_origin") and origin_claim is None:
            origin_claim = cid
    if origin_claim is None and claims:  # fall back to first claim
        k0 = claims[0].get("key") or _slug(claims[0].get("statement", ""), 8)
        origin_claim = f"scclaim-dd-{paper_id.split('-')[-1]}-{k0}"

    # ---- observations (grouped by experiment-type into kefed-models) ----
    models = {}
    for o in record.get("observations", []):
        stmt = (o.get("statement") or "").strip()
        if not stmt:
            continue
        et = o.get("experiment_type") or "unspecified-assay"
        if et not in models:
            mid = f"kefedm-dd-{paper_id.split('-')[-1]}-{_slug(et)}"
            if not K._exists(d, mid):
                ts = get_timestamp()
                K.w(d, f'insert $m isa kefed-model, has id "{mid}", has name "{escape_string(et)}", '
                       f'has content "{escape_string(o.get("experiment_detail", et))}", '
                       f'has format "kefed-protocol", has created-at {ts};')
                term = _ensure_exptype_term(d, et, doi)
                if term:
                    try:
                        K.classify(d, mid, term, provenance=f"deep-dive {doi}", confidence=0.8)
                    except Exception:
                        pass
            models[et] = mid
        # content-idempotent: skip if an observation with this statement already
        # exists under this investigation (add_observation uses a random id, so we
        # must dedupe on content, not id)
        if not K._has(d, f'$i isa scilit-investigation, has id "{inv}"; '
                        f'$o isa scilit-observation, has content "{escape_string(stmt)}"; '
                        f'(parent-note: $i, child-note: $o) isa alh-note-threading;'):
            K.add_observation(d, inv, models[et], stmt,
                              o.get("knowledge_level", "assertion"),
                              o.get("bio_scale", "molecular"), about=paper_id)
            out["observations"] += 1

    # ---- gaps (direct insert; no vocab dependency) ----
    for g in record.get("gaps", []):
        stmt = (g.get("statement") or "").strip()
        if not stmt:
            continue
        gid = f"scgap-dd-{paper_id.split('-')[-1]}-{_slug(stmt,10)}"
        if not K._exists(d, gid):
            ts = get_timestamp()
            K.w(d, f'match $inv isa scilit-investigation, has id "{inv}"; '
                   f'insert $g isa scilit-gap, has id "{gid}", has name "{escape_string(stmt[:60])}", '
                   f'has content "{escape_string(stmt)}", '
                   f'has scilit-knowledge-goal "{escape_string(g.get("knowledge_goal","")[:200])}", '
                   f'has scilit-gap-provenance "{escape_string(g.get("provenance","inferred"))}", '
                   f'has created-at {ts}; (parent-note: $inv, child-note: $g) isa alh-note-threading;')
            out["gaps"] += 1

    # ---- System 3 mechanistic graph ----
    for ml in record.get("mech_links", []):
        s, t = (ml.get("source") or "").strip(), (ml.get("target") or "").strip()
        if not s or not t:
            continue
        sid = K.add_bioentity(d, s)
        tid = K.add_bioentity(d, t)
        mtype = ml.get("type", "activates")
        # edge-idempotent: skip if this (source, target, type) link already exists
        if not K._has(d, f'$s isa scilit-bioentity, has id "{sid}"; $t isa scilit-bioentity, has id "{tid}"; '
                        f'$r isa scilit-mechanistic-link, links (mech-source: $s, mech-target: $t), '
                        f'has scilit-mech-type "{escape_string(mtype)}";'):
            K.add_mech_link(d, sid, mtype, tid, confidence=ml.get("confidence", 0.8))
            out["mech_links"] += 1

    # ---- status + claim-level hinges back to the review ----
    _set_single(d, paper_id, "scilit-acquisition-status", "sensemade")
    if origin_claim:
        cites = K.r(d, f'match $rc isa scilit-claim; $p isa scilit-paper, has id "{paper_id}"; '
                       f'$h isa scilit-hinge, links (hinging-claim: $rc, hinged-to: $p), '
                       f'has scilit-hinge-term-id $cfc; fetch {{"rc": $rc.id, "cfc": $cfc}};')
        for row in cites:
            rc = row["rc"]
            if rc == origin_claim:
                continue
            K.add_hinge(d, rc, origin_claim, str(row["cfc"]), target_kind="scilit-claim")
            out["claim_level_hinges"] += 1
    return out
