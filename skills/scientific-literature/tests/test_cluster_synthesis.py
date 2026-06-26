"""Tests for the pure cross-paper synthesis clustering + stance reconciliation."""
from cluster_synthesis import cluster_and_reconcile


def test_groups_by_subject_object_pair():
    edges = [
        {"id": "a", "paper_id": "p1", "subject": "HGNC:14931", "object": "HGNC:11180", "predicate": "RO:0002213"},
        {"id": "b", "paper_id": "p2", "subject": "HGNC:14931", "object": "HGNC:11180", "predicate": "RO:0002213"},
        {"id": "c", "paper_id": "p3", "subject": "HGNC:11180", "object": "CHEBI:26523", "predicate": "RO:0002212"},
    ]
    cl = {c["key"]: c for c in cluster_and_reconcile(edges)}
    assert set(cl[("HGNC:14931", "HGNC:11180")]["members"]) == {"a", "b"}
    assert cl[("HGNC:11180", "CHEBI:26523")]["members"] == ["c"]


def test_consensus_when_multiple_papers_agree():
    edges = [
        {"id": "a", "paper_id": "p1", "subject": "X", "object": "Y", "predicate": "RO:0002213"},
        {"id": "b", "paper_id": "p2", "subject": "X", "object": "Y", "predicate": "RO:0002213"},
    ]
    assert cluster_and_reconcile(edges)[0]["stance"] == "consensus"


def test_contested_on_opposing_predicates():
    edges = [
        {"id": "a", "paper_id": "p1", "subject": "X", "object": "Y", "predicate": "RO:0002213"},
        {"id": "b", "paper_id": "p2", "subject": "X", "object": "Y", "predicate": "RO:0002212"},
    ]
    assert cluster_and_reconcile(edges)[0]["stance"] == "contested"


def test_emerging_on_single_paper():
    edges = [{"id": "a", "paper_id": "p1", "subject": "X", "object": "Y", "predicate": "RO:0002213"}]
    assert cluster_and_reconcile(edges)[0]["stance"] == "emerging"


def test_ungrounded_edges_bucketed():
    edges = [{"id": "a", "paper_id": "p1", "subject": "X", "object": None, "predicate": "RO:0002213"}]
    out = cluster_and_reconcile(edges)
    assert out[0]["key"] == "__ungrounded__" and out[0]["stance"] == "emerging"
