from scripts.graph_candidates.h4_common import (
    SYNTHETIC_EDGE_SOURCE,
    SYMMETRIC_RULE_TYPE,
    TripleRecord,
    eligible_symmetric_completion_edges,
    h4_record_to_row,
)


def test_generated_h4_edge_is_synthetic_rule_completion_not_canonical():
    records = [TripleRecord("A", "R", "B", "canonical_observed")]
    meta = {"R": {"relation": "R", "deficit_integer": 1, "confidence": 0.75, "support": 50}}
    edge = eligible_symmetric_completion_edges(records, meta)[0]
    row = h4_record_to_row(edge)
    assert row["edge_source"] == SYNTHETIC_EDGE_SOURCE
    assert row["edge_source"] != "canonical_observed"
    assert row["rule_type"] == SYMMETRIC_RULE_TYPE
    assert row["base_h"] == "A"
    assert row["base_r"] == "R"
    assert row["base_t"] == "B"
    assert row["generated_h"] == "B"
    assert row["generated_r"] == "R"
    assert row["generated_t"] == "A"
    assert row["evidence_status"] == "rule_derived_not_observed"


def test_canonical_h4_row_is_separable_from_synthetic_row():
    row = h4_record_to_row(TripleRecord("A", "R", "B", "canonical_observed"))
    assert row["edge_source"] == "canonical_observed"
    assert row["evidence_status"] == "frozen_observed"
    assert row["source"] == "B0_parent_graph"

