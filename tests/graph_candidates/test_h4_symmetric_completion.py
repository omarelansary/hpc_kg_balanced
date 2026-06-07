from scripts.graph_candidates.h4_common import (
    TripleRecord,
    eligible_symmetric_completion_edges,
    select_completion_edges,
)


def test_eligible_symmetric_completion_generates_missing_reverse_only():
    records = [
        TripleRecord("A", "R", "B", "canonical_observed"),
        TripleRecord("C", "R", "D", "canonical_observed"),
        TripleRecord("D", "R", "C", "canonical_observed"),
        TripleRecord("A", "S", "C", "canonical_observed"),
    ]
    meta = {"R": {"relation": "R", "deficit_integer": 5, "confidence": 0.9, "support": 10}}
    edges = eligible_symmetric_completion_edges(records, meta)
    assert [(edge.h, edge.r, edge.t) for edge in edges] == [("B", "R", "A")]


def test_stage2_observed_reverse_is_excluded_from_rule_completion():
    records = [TripleRecord("A", "R", "B", "canonical_observed")]
    meta = {"R": {"relation": "R", "deficit_integer": 5, "confidence": 0.9, "support": 10}}
    edges = eligible_symmetric_completion_edges(records, meta, observed_reverse_candidates={("B", "R", "A")})
    assert edges == []


def test_deficit_capped_selection_stops_at_relation_deficit():
    records = [
        TripleRecord("A", "R", "B", "canonical_observed"),
        TripleRecord("C", "R", "D", "canonical_observed"),
        TripleRecord("E", "R", "F", "canonical_observed"),
    ]
    meta = {"R": {"relation": "R", "deficit_integer": 2, "confidence": 0.9, "support": 10}}
    edges = eligible_symmetric_completion_edges(records, meta)
    selected = select_completion_edges(edges, meta, "deficit-capped")
    assert len(edges) == 3
    assert len(selected) == 2

