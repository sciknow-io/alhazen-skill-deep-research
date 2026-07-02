#!/usr/bin/env python3
"""
KQED prototype operations for the scientific-literature skill.

Reusable verbs for the three-system / four-arc model (see docs/architecture-kqed.md):
controlled-vocabulary libraries (provenance-bearing), fragments, grounding edges
(alh-derivation), KEfED models + observations, gaps, hinges, and a System-3
mechanism graph. Importable functions + a thin CLI.

Typing of published taxonomies uses core alh-vocabulary / alh-vocabulary-type +
alh-classification (which carries provenance + confidence) — not inline enums.
"""
import os, sys, json, re, argparse
from typedb.driver import TypeDB, Credentials, DriverOptions, TransactionType
from paper_identity import paper_identity

try:
    from skillful_alhazen.utils.skill_helpers import escape_string, generate_id, get_timestamp
except Exception:  # pragma: no cover
    import uuid, datetime
    def escape_string(s):
        return (s or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
    def generate_id(prefix):
        return f"{prefix}-{uuid.uuid4().hex[:12]}"
    def get_timestamp():
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

DB = os.getenv("TYPEDB_DATABASE", "alh_deep_research")
CACHE = os.path.expanduser("~/.alhazen/cache")


def get_driver():
    return TypeDB.driver("localhost:1729", Credentials("admin", "password"),
                         DriverOptions(is_tls_enabled=False))


def w(driver, q):
    with driver.transaction(DB, TransactionType.WRITE) as tx:
        tx.query(q).resolve(); tx.commit()


def r(driver, q):
    with driver.transaction(DB, TransactionType.READ) as tx:
        return list(tx.query(q).resolve())


def _exists(driver, eid):
    # matches ANY entity owning this id (incl. alh-vocabulary/-type which aren't identifiable-entities)
    return bool(r(driver, f'match $x has id "{escape_string(eid)}";'))


def _has(driver, match_body):
    """True if `match {match_body}` yields >=1 row (idempotency guard for edges)."""
    try:
        return bool(r(driver, f'match {match_body}'))
    except Exception:
        return False


# ---------------------------------------------------------------- vocabularies
def add_vocab(driver, name, source, iri=None, vid=None):
    vid = vid or generate_id("vocab")
    if _exists(driver, vid):
        return vid
    q = (f'insert $v isa alh-vocabulary, has id "{vid}", has name "{escape_string(name)}", '
         f'has description "{escape_string(name)}", has alh-vocabulary-source "{escape_string(source)}"')
    if iri:
        q += f', has iri "{escape_string(iri)}"'
    w(driver, q + ";")
    return vid


def add_vocab_term(driver, vocab_id, name, iri=None, source_uri=None, provenance=None,
                   parent=None, licenses=None, tid=None):
    """provenance: str or list[str] (multi-source)."""
    tid = tid or generate_id("term")
    if not _exists(driver, tid):
        q = f'insert $t isa alh-vocabulary-type, has id "{tid}", has name "{escape_string(name)}", has description "{escape_string(name)}"'
        if iri:
            q += f', has iri "{escape_string(iri)}"'
        if source_uri:
            q += f', has source-uri "{escape_string(source_uri)}"'
        provs = provenance if isinstance(provenance, (list, tuple)) else ([provenance] if provenance else [])
        for p in provs:
            q += f', has provenance "{escape_string(p)}"'
        w(driver, q + ";")
        w(driver, f'match $v isa alh-vocabulary, has id "{escape_string(vocab_id)}"; '
                  f'$t isa alh-vocabulary-type, has id "{tid}"; '
                  f'insert (vocab: $v, vocab-type: $t) isa alh-vocabulary-membership;')
    if parent:
        w(driver, f'match $c isa alh-vocabulary-type, has id "{tid}"; $p isa alh-vocabulary-type, has id "{escape_string(parent)}"; '
                  f'insert (subtype: $c, supertype: $p) isa alh-type-hierarchy;')
    if licenses and not _has(driver, f'$t isa alh-vocabulary-type, has id "{tid}"; $w isa alh-vocabulary-type, has id "{escape_string(licenses)}"; (licensing-type: $t, licensed-warrant: $w) isa kefed-licenses;'):
        w(driver, f'match $t isa alh-vocabulary-type, has id "{tid}"; $war isa alh-vocabulary-type, has id "{escape_string(licenses)}"; '
                  f'insert (licensing-type: $t, licensed-warrant: $war) isa kefed-licenses;')
    return tid


def classify(driver, entity_id, term_id, provenance=None, confidence=None):
    if _has(driver, f'$e isa alh-identifiable-entity, has id "{escape_string(entity_id)}"; $t isa alh-vocabulary-type, has id "{escape_string(term_id)}"; (classified-entity: $e, type-facet: $t) isa alh-classification;'):
        return
    ts = get_timestamp()
    opt = ""
    if provenance:
        opt += f', has provenance "{escape_string(provenance)}"'
    if confidence is not None:
        opt += f', has confidence {confidence}'
    w(driver, f'match $e isa alh-identifiable-entity, has id "{escape_string(entity_id)}"; '
              f'$t isa alh-vocabulary-type, has id "{escape_string(term_id)}"; '
              f'insert (classified-entity: $e, type-facet: $t) isa alh-classification, has created-at {ts}{opt};')


def list_vocab(driver, vocab_id):
    rows = r(driver, f'match $v isa alh-vocabulary, has id "{escape_string(vocab_id)}"; '
                     f'(vocab: $v, vocab-type: $t) isa alh-vocabulary-membership; '
                     f'$t has name $n; fetch {{"id": $t.id, "name": $n, "iri": $t.iri, "prov": [$t.provenance]}};')
    return rows


# ---------------------------------------------------------------- fragments
FRAG_ENT = {"sentence": "scilit-sentence", "methods-step": "scilit-section", "figure": "scilit-figure"}


def _artifact_text(driver, artifact_id):
    rows = r(driver, f'match $a isa alh-artifact, has id "{escape_string(artifact_id)}"; fetch {{"cp": $a.cache-path}};')
    cp = rows[0].get("cp") if rows else None
    if not cp:
        return None
    path = os.path.join(CACHE, cp)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def add_fragment(driver, artifact_id, ftype, text, fid=None):
    fid = fid or generate_id("frag")
    if _exists(driver, fid):
        return fid
    full = _artifact_text(driver, artifact_id)
    offset, length = -1, len(text)
    if full:
        norm = re.sub(r"\s+", " ", full)
        needle = re.sub(r"\s+", " ", text).strip()
        i = norm.find(needle)
        if i < 0 and len(needle) > 40:           # retry on a shorter anchor
            i = norm.find(needle[:40])
        offset, length = i, len(needle)
    ent = FRAG_ENT[ftype]
    extra = ', has scilit-section-type "methods-step"' if ftype == "methods-step" else ""
    ts = get_timestamp()
    w(driver, f'insert $f isa {ent}, has id "{fid}", has content "{escape_string(text)}", '
              f'has offset {offset}, has length {length}{extra}, has created-at {ts};')
    w(driver, f'match $a isa alh-artifact, has id "{escape_string(artifact_id)}"; $f isa alh-fragment, has id "{fid}"; '
              f'insert (whole: $a, part: $f) isa alh-fragmentation;')
    return fid


def ground_note(driver, note_id, fragment_ids):
    ts = get_timestamp()
    for fragid in fragment_ids:
        if _has(driver, f'$n isa alh-information-content-entity, has id "{escape_string(note_id)}"; $f isa alh-fragment, has id "{escape_string(fragid)}"; (derivative: $n, derived-from-source: $f) isa alh-derivation;'):
            continue
        w(driver, f'match $n isa alh-information-content-entity, has id "{escape_string(note_id)}"; '
                  f'$f isa alh-fragment, has id "{escape_string(fragid)}"; '
                  f'insert (derivative: $n, derived-from-source: $f) isa alh-derivation, has created-at {ts};')


# ---------------------------------------------------------------- KEfED
def add_kefed_model(driver, name, experiment_type_term, variables=None, mid=None, definition=None):
    """Insert a kefed-model (bigraph template) with a subject kefed-model-node
    (typed by a fresh ooevv-material-entity def) carrying ooevv-variable elements
    via kefed-node-variable.

    2b.2 redesign: variables are no longer inserted directly into kefed-model-element;
    they are attached to the subject kefed-model-node via kefed-node-variable.
    The ooevv-element-set is linked via kefed-model-elementset relation
    (retiring the eset-{mid} naming convention).

    variables: list of (role, name, efo_label).
      A 4-tuple (role, name, value_set, efo_label) is also accepted for backward
      compatibility; value_set has no successor in the clean schema and is dropped.
    definition: optional plain-English definition persisted on the kefed-model.
    State is always 'template'.
    """
    mid = mid or generate_id("kefedm")
    if not _exists(driver, mid):
        ts = get_timestamp()
        eset_id = generate_id("eset")
        subject_def_id = generate_id("ooevv")
        subject_node_id = generate_id("knode")
        defn_clause = f', has ooevv-definition "{escape_string(definition)}"' if definition else ""
        w(driver, f'insert $m isa kefed-model, has id "{mid}", has name "{escape_string(name)}", '
                  f'has kefed-model-state "template", has created-at {ts}{defn_clause};')
        classify(driver, mid, experiment_type_term, provenance="kefed experiment-type", confidence=0.9)
        w(driver, f'insert $es isa ooevv-element-set, has id "{eset_id}", '
                  f'has name "{escape_string(name)} elements";')
        w(driver, f'match $m isa kefed-model, has id "{mid}"; '
                  f'$es isa ooevv-element-set, has id "{eset_id}"; '
                  f'insert (model: $m, element-set: $es) isa kefed-model-elementset;')
        w(driver, f'match $es isa ooevv-element-set, has id "{eset_id}"; '
                  f'insert $me isa ooevv-material-entity, has id "{subject_def_id}", '
                  f'has name "{escape_string(name)} entity"; '
                  f'(element-set: $es, element: $me) isa ooevv-set-element;')
        w(driver, f'match $m isa kefed-model, has id "{mid}"; '
                  f'$me isa ooevv-material-entity, has id "{subject_def_id}"; '
                  f'insert $n isa kefed-model-node, has id "{subject_node_id}", '
                  f'has name "{escape_string(name)} node", has created-at {ts}; '
                  f'(node: $n, node-type: $me) isa kefed-node-type; '
                  f'(model: $m, element: $n) isa kefed-model-element; '
                  f'(model: $m, subject-node: $n) isa ooevv-subject;')
        for var_tuple in (variables or []):
            if len(var_tuple) == 4:
                role, vname, _value_set, efo = var_tuple  # value_set dropped (no successor)
            else:
                role, vname, efo = var_tuple
            vid = generate_id("ooevv")
            q = (f'insert $v isa ooevv-variable, has id "{vid}", '
                 f'has name "{escape_string(vname)}", '
                 f'has ooevv-variable-role "{escape_string(role)}", '
                 f'has created-at {ts}')
            if efo:
                q += f', has kefed-efo-label "{escape_string(efo)}"'
            w(driver, q + ';')
            w(driver, f'match $n isa kefed-model-node, has id "{subject_node_id}"; '
                      f'$v isa ooevv-variable, has id "{vid}"; '
                      f'insert (node: $n, variable: $v) isa kefed-node-variable;')
    return mid


def add_observation(driver, sensemaking_bundle, statement, knowledge_level, bio_scale,
                    about=None, oid=None, source_label=None):
    """Insert a scilit-observation threaded under a scilit-paper-sensemaking bundle.

    `about` (a paper id) is accepted for backward compatibility but unused; the
    bundle already carries its paper via scilit-sensemaking-paper.
    Threading is via scilit-sensemaking-observation (NOT the retired scilit-investigation-observation).

    `source_label` is the evidence source-locator (e.g. "OF4DF" = Figure 4 panels D,F;
    "OSF3B" = Supplemental Figure 3 panel B; "OE5" = Experiment 5; "OX" = text-only).
    When given it becomes the observation `name` verbatim; the full text always lives
    in `content`. See docs/observation-source-labeling.md for the grammar.
    """
    oid = oid or generate_id("scobs")
    if _exists(driver, oid):
        return oid
    ts = get_timestamp()
    name = source_label or statement[:60]
    w(driver, f'match $b isa scilit-paper-sensemaking, has id "{escape_string(sensemaking_bundle)}"; '
              f'insert $o isa scilit-observation, has id "{oid}", '
              f'has name "{escape_string(name)}", '
              f'has content "{escape_string(statement)}", '
              f'has scilit-knowledge-level "{escape_string(knowledge_level)}", '
              f'has scilit-bio-scale "{escape_string(bio_scale)}", has created-at {ts}; '
              f'(sensemaking: $b, observation: $o) isa scilit-sensemaking-observation;')
    return oid


# ---------------------------------------------------------------- gaps / hinges
def add_gap(driver, sensemaking_bundle, category_term, knowledge_goal, provenance, statement, gid=None):
    """Insert a scilit-gap threaded under a scilit-paper-sensemaking bundle.

    Threading is via scilit-sensemaking-reported-gap (NOT the retired scilit-investigation-gap).
    `scilit-gap-provenance` is owned by scilit-gap; accepted values: explicit-cue | inferred-from-hinge | both.
    """
    gid = gid or generate_id("scgap")
    if not _exists(driver, gid):
        ts = get_timestamp()
        w(driver, f'match $b isa scilit-paper-sensemaking, has id "{escape_string(sensemaking_bundle)}"; '
                  f'insert $g isa scilit-gap, has id "{gid}", '
                  f'has name "{escape_string(statement[:60])}", '
                  f'has content "{escape_string(statement)}", '
                  f'has scilit-knowledge-goal "{escape_string(knowledge_goal)}", '
                  f'has scilit-gap-provenance "{escape_string(provenance)}", has created-at {ts}; '
                  f'(sensemaking: $b, reported-gap: $g) isa scilit-sensemaking-reported-gap;')
        classify(driver, gid, category_term, provenance="Boguslav et al. 2023", confidence=0.85)
    return gid


def add_addresses(driver, note_id, gap_id):
    # addressing-note is played by scilit-claim / scilit-observation (not alh-note broadly)
    if _has(driver, f'$n isa scilit-claim, has id "{escape_string(note_id)}"; $g isa scilit-gap, has id "{escape_string(gap_id)}"; (addressing-note: $n, gap: $g) isa scilit-addresses;'):
        return
    w(driver, f'match $n isa scilit-claim, has id "{escape_string(note_id)}"; $g isa scilit-gap, has id "{escape_string(gap_id)}"; '
              f'insert (addressing-note: $n, gap: $g) isa scilit-addresses;')


def upsert_paper(driver, meta):
    """Find-or-create a scilit-paper by deterministic identity. Returns its id."""
    pid, tier, value = paper_identity(meta)
    if not _exists(driver, pid):
        ts = get_timestamp()
        attrs = [f'has id "{pid}"',
                 f'has scilit-identity-basis "{escape_string(tier)}"',
                 f'has scilit-identity-value "{escape_string(value)}"',
                 f'has created-at {ts}']
        if meta.get("name") or meta.get("title"):
            attrs.append(f'has name "{escape_string((meta.get("name") or meta.get("title"))[:200])}"')
        if meta.get("doi"):
            attrs.append(f'has scilit-doi "{escape_string(str(meta["doi"]))}"')
        if meta.get("pmid"):
            attrs.append(f'has scilit-pmid "{escape_string(str(meta["pmid"]))}"')
        w(driver, f'insert $p isa scilit-paper, {", ".join(attrs)};')
    else:
        # fill only-missing identity attrs (older rows created before this change)
        if not _has(driver, f'$p isa scilit-paper, has id "{pid}", has scilit-identity-basis $b;'):
            w(driver, f'match $p isa scilit-paper, has id "{pid}"; '
                      f'insert $p has scilit-identity-basis "{escape_string(tier)}", '
                      f'has scilit-identity-value "{escape_string(value)}";')
    return pid


def add_synthesis_note(driver, inv_id, statement, stance, concept_curies=None):
    """Write a cross-paper synthesis note (analysis) addressing the investigation, with a stance,
    threaded under the investigation, and linked (alh-aboutness) to the grounded concepts it concerns."""
    sid = generate_id("scsyn"); ts = get_timestamp()
    w(driver, f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
              f'insert $s isa scilit-synthesis-note, has id "{sid}", has name "{escape_string(statement[:60])}", '
              f'has content "{escape_string(statement)}", has scilit-synthesis-stance "{escape_string(stance)}", '
              f'has created-at {ts}; (investigation: $inv, synthesis: $s) isa scilit-investigation-synthesis;')
    for curie in (concept_curies or []):
        hit = r(driver, f'match $t isa scilit-ontology-term, has scilit-curie "{escape_string(curie)}"; fetch {{"id": $t.id}};')
        if hit:
            w(driver, f'match $s isa scilit-synthesis-note, has id "{sid}"; '
                      f'$t isa scilit-ontology-term, has id "{escape_string(hit[0]["id"])}"; '
                      f'insert (synthesis: $s, concept: $t) isa scilit-synthesis-concept;')
    return sid


def upsert_ontology_term(driver, g):
    """Create-or-find a scilit-ontology-term from a ground_term() dict. Idempotent on CURIE."""
    from entity_identity import normalize_curie
    curie = normalize_curie(g["curie"])
    hit = r(driver, f'match $t isa scilit-ontology-term, has scilit-curie "{escape_string(curie)}"; fetch {{"id": $t.id}};')
    if hit:
        return hit[0]["id"]
    tid = generate_id("scterm")
    q = (f'insert $t isa scilit-ontology-term, has id "{tid}", '
         f'has name "{escape_string(g.get("label") or curie)}", '
         f'has description "{escape_string(g.get("label") or curie)}", '
         f'has scilit-curie "{escape_string(curie)}", '
         f'has scilit-ontology-source "{escape_string(g.get("source", ""))}", '
         f'has scilit-obsolete false')
    if g.get("iri"):
        q += f', has iri "{escape_string(g["iri"])}"'
    w(driver, q + ";")
    return tid


def persist_grounding(driver, entity_id, g, policy_version=None):
    """Classify an entity to its ontology term (when grounded), THEN stamp grounding-state, so a
    lookup/insert failure never leaves a premature 'grounded' state. Reuses alh-classification."""
    state = g.get("state", "ungrounded")
    if state == "grounded" and g.get("curie"):
        tid = upsert_ontology_term(driver, g)
        prov = f'OLS/{g.get("source", "")}'
        if policy_version:
            prov += f' policy={policy_version}'
        classify(driver, entity_id, tid, provenance=prov, confidence=g.get("confidence"))
    if _has(driver, f'$e has id "{escape_string(entity_id)}", has scilit-grounding-state $s;'):
        w(driver, f'match $e has id "{escape_string(entity_id)}", has scilit-grounding-state $s; delete has $s of $e;')
    w(driver, f'match $e isa scilit-entity, has id "{escape_string(entity_id)}"; '
              f'insert $e has scilit-grounding-state "{escape_string(state)}";')
    return state


def set_investigation_question(driver, inv_id, question):
    """Set/replace the investigation's driving question."""
    if _has(driver, f'$i isa scilit-investigation, has id "{escape_string(inv_id)}", has scilit-investigation-question $q;'):
        w(driver, f'match $i isa scilit-investigation, has id "{escape_string(inv_id)}", has scilit-investigation-question $q; delete has $q of $i;')
    w(driver, f'match $i isa scilit-investigation, has id "{escape_string(inv_id)}"; '
              f'insert $i has scilit-investigation-question "{escape_string(question)}";')


def get_investigation_question(driver, inv_id):
    rows = r(driver, f'match $i isa scilit-investigation, has id "{escape_string(inv_id)}", '
                     f'has scilit-investigation-question $q; fetch {{"q": $q}};')
    return rows[0]["q"] if rows else None


def set_grounding_policy(driver, inv_id, policy):
    """Store the investigation's grounding policy (domain profile) IN the knowledge graph as a
    scilit-grounding-policy note threaded under the investigation. `policy` is a dict; serialized
    with ensure_ascii=False so raw UTF-8 (no \\uXXXX, which crashes TypeDB 3.8). Replaces any prior."""
    body = json.dumps(policy, ensure_ascii=False)
    for row in (r(driver, f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
                          f'$p isa scilit-grounding-policy; (parent-note: $inv, child-note: $p) isa alh-note-threading; '
                          f'$p has id $pid; fetch {{"pid": $pid}};') or []):
        pid = row["pid"]
        w(driver, f'match $p isa scilit-grounding-policy, has id "{escape_string(pid)}"; '
                  f'$rel isa alh-note-threading, links (child-note: $p); delete $rel;')
        w(driver, f'match $p isa scilit-grounding-policy, has id "{escape_string(pid)}"; delete $p;')
    newid = generate_id("scpol"); ts = get_timestamp()
    w(driver, f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
              f'insert $p isa scilit-grounding-policy, has id "{newid}", has name "grounding-policy", '
              f'has content "{escape_string(body)}", has created-at {ts}; '
              f'(investigation: $inv, policy: $p) isa scilit-investigation-grounding;')
    return newid


def get_grounding_policy(driver, inv_id):
    """Return the investigation's grounding policy dict from the KG, or None."""
    rows = r(driver, f'match $inv isa scilit-investigation, has id "{escape_string(inv_id)}"; '
                     f'$p isa scilit-grounding-policy; (parent-note: $inv, child-note: $p) isa alh-note-threading; '
                     f'$p has content $c; fetch {{"c": $c}};')
    if not rows:
        return None
    try:
        return json.loads(rows[0]["c"])
    except Exception:
        return None


def find_or_make_stub_paper(driver, citation):
    """Lightweight scilit-paper stub for a hinge target (cited existing KC)."""
    hit = r(driver, f'match $p isa scilit-paper, has name $n; $n == "{escape_string(citation)}"; fetch {{"id": $p.id}};')
    if hit:
        return hit[0]["id"]
    # Route through upsert_paper for deterministic identity; provenance set after.
    new_pid = upsert_paper(driver, {"name": citation})
    w(driver, f'match $p isa scilit-paper, has id "{new_pid}"; insert $p has provenance "hinge-target-stub";')
    return new_pid


def _hinge_target_kind(driver, target_id):
    """hinged-to is played by scilit-paper (paper-level citation) and scilit-claim
    (claim-level mapping to a cited origin claim). Probe which the id is."""
    if _has(driver, f'$t isa scilit-claim, has id "{escape_string(target_id)}";'):
        return "scilit-claim"
    if _has(driver, f'$t isa scilit-paper, has id "{escape_string(target_id)}";'):
        return "scilit-paper"
    return None


def add_hinge(driver, claim_id, target_id, cfc_term_id, target_kind=None):
    # hinged-to is played by scilit-claim (origin-claim mapping) OR scilit-paper (citation).
    kind = target_kind or _hinge_target_kind(driver, target_id)
    if kind is None:
        raise ValueError(f"hinge target {target_id} is neither a scilit-claim nor a scilit-paper")
    if _has(driver, f'$c isa scilit-claim, has id "{escape_string(claim_id)}"; $t isa {kind}, has id "{escape_string(target_id)}"; (hinging-claim: $c, hinged-to: $t) isa scilit-hinge;'):
        return
    w(driver, f'match $c isa scilit-claim, has id "{escape_string(claim_id)}"; '
              f'$t isa {kind}, has id "{escape_string(target_id)}"; '
              f'insert (hinging-claim: $c, hinged-to: $t) isa scilit-hinge, has scilit-hinge-term-id "{escape_string(cfc_term_id)}";')


# ---------------------------------------------------------------- System 3
def add_bioentity(driver, name, bid=None):
    hit = r(driver, f'match $b isa scilit-bioentity, has name $n; $n == "{escape_string(name)}"; fetch {{"id": $b.id}};')
    if hit:
        return hit[0]["id"]
    bid = bid or generate_id("scbio")
    ts = get_timestamp()
    w(driver, f'insert $b isa scilit-bioentity, has id "{bid}", has name "{escape_string(name)}", has created-at {ts};')
    return bid


def add_mech_link(driver, source_id, mtype, target_id, confidence=0.8):
    w(driver, f'match $s isa scilit-bioentity, has id "{escape_string(source_id)}"; $t isa scilit-bioentity, has id "{escape_string(target_id)}"; '
              f'insert (mech-source: $s, mech-target: $t) isa scilit-mechanistic-link, '
              f'has scilit-mech-type "{escape_string(mtype)}", has confidence {confidence};')


# ---------------------------------------------------------------- show / verify
def show_kqed(driver, investigation):
    out = {"investigation": investigation}
    out["claims"] = r(driver, f'match $inv isa scilit-investigation, has id "{escape_string(investigation)}"; '
                              f'$c isa scilit-claim, has scilit-claim-statement $s; (parent-note: $inv, child-note: $c) isa alh-note-threading; '
                              f'fetch {{"id": $c.id, "stmt": $s}};')
    out["observations"] = r(driver, f'match $inv isa scilit-investigation, has id "{escape_string(investigation)}"; '
                                    f'$o isa scilit-observation, has scilit-knowledge-level $kl, has scilit-bio-scale $bs; '
                                    f'(parent-note: $inv, child-note: $o) isa alh-note-threading; '
                                    f'fetch {{"id": $o.id, "kl": $kl, "scale": $bs, "name": $o.name}};')
    out["gaps"] = r(driver, f'match $inv isa scilit-investigation, has id "{escape_string(investigation)}"; '
                            f'$g isa scilit-gap, has scilit-knowledge-goal $kg; (parent-note: $inv, child-note: $g) isa alh-note-threading; '
                            f'fetch {{"id": $g.id, "goal": $kg, "name": $g.name}};')
    out["mech_links"] = r(driver, 'match (mech-source: $s, mech-target: $t) isa scilit-mechanistic-link, has scilit-mech-type $mt; '
                                  '$s has name $sn; $t has name $tn; fetch {"src": $sn, "type": $mt, "tgt": $tn};')
    print(json.dumps(out, indent=2, default=str))


# ---------------------------------------------------------------- CLI
def main():
    p = argparse.ArgumentParser(description="KQED prototype operations")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("list-vocab"); sp.add_argument("--vocab", required=True)
    sp = sub.add_parser("show-kqed"); sp.add_argument("--investigation", required=True)
    sp = sub.add_parser("add-hinge")
    sp.add_argument("--claim", required=True)
    sp.add_argument("--target", required=True, help="scilit-paper (citation) or scilit-claim (origin-claim mapping)")
    sp.add_argument("--term", required=True, help="Teufel-CFC term id, e.g. PUse / CoCoGM / PMot")
    args = p.parse_args()
    d = get_driver()
    try:
        if args.cmd == "list-vocab":
            print(json.dumps(list_vocab(d, args.vocab), indent=2, default=str))
        elif args.cmd == "show-kqed":
            show_kqed(d, args.investigation)
        elif args.cmd == "add-hinge":
            add_hinge(d, args.claim, args.target, args.term)
            kind = _hinge_target_kind(d, args.target)
            print(f"hinge[{args.term}] {args.claim} -> {args.target} ({kind})")
    finally:
        d.close()


if __name__ == "__main__":
    main()
