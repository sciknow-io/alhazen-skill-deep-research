"""Pure cross-paper synthesis: deterministic group-by on grounded relationship edges + stance
reconciliation from predicate agreement/opposition. No DB, no network — unit-testable.

An edge is a grounded relationship asserted by one paper:
    {id, paper_id, subject (CURIE), object (CURIE), predicate (CURIE), mech_type?}
Edges are grouped by the canonical (subject, object) pair. Within a group the predicates decide stance:
opposing predicates (e.g. positively vs negatively regulates) -> contested; agreement across >=2 papers
-> consensus; a single paper -> emerging.
"""
from collections import defaultdict

# Opposing RO/Biolink predicate pairs (order-independent). Extend per domain.
_OPPOSED = {
    frozenset({"RO:0002213", "RO:0002212"}),   # positively_regulates vs negatively_regulates
    frozenset({"RO:0002336", "RO:0002335"}),   # activates vs inhibits-ish (placeholder extension)
}


def _opposed(predicates):
    preds = {p for p in predicates if p}
    for a in preds:
        for b in preds:
            if a != b and frozenset({a, b}) in _OPPOSED:
                return True
    return False


def cluster_and_reconcile(edges):
    """Group grounded edges by (subject, object) and assign a stance. Edges missing a grounded
    subject or object are dropped into a single '__ungrounded__' cluster (stance 'emerging')."""
    groups = defaultdict(list)
    for e in edges:
        if e.get("subject") and e.get("object"):
            groups[(e["subject"], e["object"])].append(e)
        else:
            groups["__ungrounded__"].append(e)
    out = []
    for key, members in groups.items():
        papers = {m.get("paper_id") for m in members if m.get("paper_id")}
        predicates = {m.get("predicate") for m in members if m.get("predicate")}
        if key == "__ungrounded__":
            stance = "emerging"
        elif _opposed(predicates):
            stance = "contested"
        elif len(papers) >= 2:
            stance = "consensus"
        else:
            stance = "emerging"
        out.append({"key": key, "members": [m["id"] for m in members],
                    "papers": sorted(papers), "predicates": sorted(predicates), "stance": stance})
    return out
