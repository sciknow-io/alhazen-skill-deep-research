"""One-shot, idempotent migration: re-type generic investigation wiring onto the
declarative typed relations introduced in schema.tql.

Every structural edge inside a scilit-investigation used to be a generic
`alh-note-threading` (note->note) or `alh-aboutness` (note->entity) relation, with its
meaning recoverable only from the endpoint types. This migration converts each such edge
to its dedicated subtype (e.g. scilit-investigation-claim, scilit-evidence-source).

Idempotency: only edges whose EXACT type is the generic supertype are migrated, matched
with the `isa!` (direct-type) operator - so already-migrated subtype instances are skipped
and re-running is a no-op. Insert + delete run in one transaction per edge class, so a
partial failure leaves no duplicates.

Run:  TYPEDB_DATABASE=alh_deep_research uv run python migrations/retype_investigation_edges.py
Add --dry-run to report counts without writing.
"""
import os
import sys
from typedb.driver import Credentials, DriverOptions, TransactionType, TypeDB

HOST = os.getenv("TYPEDB_HOST", "localhost")
PORT = int(os.getenv("TYPEDB_PORT", "1729"))
USER = os.getenv("TYPEDB_USERNAME", "admin")
PWD = os.getenv("TYPEDB_PASSWORD", "password")
DB = os.getenv("TYPEDB_DATABASE", "alh_deep_research")

# (parent/note type, child/subject type, supertype, base parent-role, base child-role,
#  new relation, new parent-role, new child-role)
THREAD = "alh-note-threading"
ABOUT = "alh-aboutness"

CLASSES = [
    # note -> note threading subtypes
    ("scilit-investigation", "scilit-grounding-policy", THREAD, "parent-note", "child-note",
     "scilit-investigation-grounding", "investigation", "policy"),
    ("scilit-investigation", "scilit-investigation-phase", THREAD, "parent-note", "child-note",
     "scilit-investigation-phasing", "investigation", "phase"),
    ("scilit-investigation-phase", "scilit-faceting-note", THREAD, "parent-note", "child-note",
     "scilit-phase-faceting", "phase", "faceting"),
    ("scilit-investigation", "scilit-claim", THREAD, "parent-note", "child-note",
     "scilit-investigation-claim", "investigation", "claim"),
    ("scilit-claim", "scilit-evidence", THREAD, "parent-note", "child-note",
     "scilit-claim-evidence", "claim", "evidence"),
    ("scilit-investigation", "scilit-citation-impact", THREAD, "parent-note", "child-note",
     "scilit-investigation-impact", "investigation", "impact"),
    ("scilit-investigation", "scilit-synthesis-note", THREAD, "parent-note", "child-note",
     "scilit-investigation-synthesis", "investigation", "synthesis"),
    ("scilit-investigation", "scilit-observation", THREAD, "parent-note", "child-note",
     "scilit-investigation-observation", "investigation", "observation"),
    ("scilit-investigation", "scilit-gap", THREAD, "parent-note", "child-note",
     "scilit-investigation-gap", "investigation", "gap"),
    # note -> entity aboutness subtypes
    ("scilit-investigation", "scilit-paper", ABOUT, "note", "subject",
     "scilit-investigation-focus", "investigation", "focal-paper"),
    ("scilit-investigation", "scilit-corpus", ABOUT, "note", "subject",
     "scilit-investigation-scope", "investigation", "corpus"),
    ("scilit-evidence", "scilit-paper", ABOUT, "note", "subject",
     "scilit-evidence-source", "evidence", "source-paper"),
    ("scilit-citation-impact", "scilit-paper", ABOUT, "note", "subject",
     "scilit-impact-citation", "impact", "citing-paper"),
    ("scilit-observation", "scilit-paper", ABOUT, "note", "subject",
     "scilit-observation-subject", "observation", "observed-paper"),
    ("scilit-synthesis-note", "scilit-ontology-term", ABOUT, "note", "subject",
     "scilit-synthesis-concept", "synthesis", "concept"),
]


def count_generic(tx, ptype, ctype, super_rel, bp, bc):
    q = (f'match $p isa {ptype}; $c isa {ctype}; '
         f'$r isa! {super_rel}, links ({bp}: $p, {bc}: $c); select $r;')
    return len(list(tx.query(q).resolve()))


def migrate_class(d, ptype, ctype, super_rel, bp, bc, newrel, np, nc):
    with d.transaction(DB, TransactionType.WRITE) as tx:
        # create the typed edge for every exact-generic instance...
        tx.query(
            f'match $p isa {ptype}; $c isa {ctype}; '
            f'$r isa! {super_rel}, links ({bp}: $p, {bc}: $c); '
            f'insert ({np}: $p, {nc}: $c) isa {newrel};'
        ).resolve()
        # ...then delete the exact-generic instances (isa! leaves the new subtype untouched)
        tx.query(
            f'match $p isa {ptype}; $c isa {ctype}; '
            f'$r isa! {super_rel}, links ({bp}: $p, {bc}: $c); '
            f'delete $r;'
        ).resolve()
        tx.commit()


def main():
    dry = "--dry-run" in sys.argv
    total = 0
    with TypeDB.driver(f"{HOST}:{PORT}", Credentials(USER, PWD),
                       DriverOptions(is_tls_enabled=False)) as d:
        for (ptype, ctype, super_rel, bp, bc, newrel, np, nc) in CLASSES:
            with d.transaction(DB, TransactionType.READ) as tx:
                n = count_generic(tx, ptype, ctype, super_rel, bp, bc)
            total += n
            print(f"  {newrel:<34} {ptype} -> {ctype}: {n} generic edge(s)"
                  + ("" if n == 0 else (" [dry-run]" if dry else " -> migrating")))
            if n and not dry:
                migrate_class(d, ptype, ctype, super_rel, bp, bc, newrel, np, nc)
    print(f"{'Would migrate' if dry else 'Migrated'} {total} edge(s) in {DB}.")


if __name__ == "__main__":
    main()
