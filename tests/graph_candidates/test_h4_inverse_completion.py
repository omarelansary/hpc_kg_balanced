from scripts.graph_candidates.h4_common import (
    INVERSE_RULE_TYPE,
    SYNTHETIC_EDGE_SOURCE,
    TripleRecord,
    eligible_inverse_completion_edges,
    h4_record_to_row,
    select_deficit_capped_inverse_edges,
)


def inverse_rule(source="R1", target="R2", confidence=0.9, target_deficit=2, target_surplus=0):
    return {
        "source_relation": source,
        "target_inverse_relation": target,
        "orientation": f"{source}_to_{target}",
        "confidence": confidence,
        "confidence_source": "test_inverse_confidence",
        "support": 10,
        "target_eta": 5,
        "target_deficit": target_deficit,
        "target_surplus": target_surplus,
    }


def test_h4_b1_generates_labelled_inverse_edge_with_base_provenance():
    records = [TripleRecord("A", "R1", "B", "canonical_observed")]
    edges, stats = eligible_inverse_completion_edges(records, [inverse_rule()])
    selected, selection_stats = select_deficit_capped_inverse_edges(edges)
    assert stats["eligible_before_deficit_cap"] == 1
    assert selection_stats["selected"] == 1
    edge = selected[0]
    row = h4_record_to_row(edge)
    assert edge.triple == ("B", "R2", "A")
    assert row["edge_source"] == SYNTHETIC_EDGE_SOURCE
    assert row["edge_source"] != "canonical_observed"
    assert row["rule_type"] == INVERSE_RULE_TYPE
    assert row["source_relation"] == "R1"
    assert row["target_inverse_relation"] == "R2"
    assert row["orientation"] == "R1_to_R2"
    assert row["base_h"] == "A"
    assert row["base_r"] == "R1"
    assert row["base_t"] == "B"
    assert row["generated_h"] == "B"
    assert row["generated_r"] == "R2"
    assert row["generated_t"] == "A"
    assert row["confidence_type"] == "pair_level_if_orientation_specific_missing"
    assert row["observed_in_frozen_candidates"] is False


def test_h4_b1_excludes_inverse_edge_already_in_b0():
    records = [
        TripleRecord("A", "R1", "B", "canonical_observed"),
        TripleRecord("B", "R2", "A", "canonical_observed"),
    ]
    edges, stats = eligible_inverse_completion_edges(records, [inverse_rule()])
    assert edges == []
    assert stats["already_present_in_b0"] == 1


def test_h4_b1_excludes_frozen_observed_candidate_from_synthetic_generation():
    records = [TripleRecord("A", "R1", "B", "canonical_observed")]
    edges, stats = eligible_inverse_completion_edges(
        records,
        [inverse_rule()],
        observed_inverse_candidates={("B", "R2", "A")},
    )
    assert edges == []
    assert stats["already_frozen_observed"] == 1


def test_h4_b1_confidence_threshold_blocks_low_confidence_rule():
    records = [TripleRecord("A", "R1", "B", "canonical_observed")]
    edges, stats = eligible_inverse_completion_edges(records, [inverse_rule(confidence=0.79)], confidence_threshold=0.8)
    assert edges == []
    assert stats["below_confidence_threshold"] == 1


def test_h4_b1_rejects_overfilled_or_no_deficit_target_relation():
    records = [TripleRecord("A", "R1", "B", "canonical_observed")]
    edges, stats = eligible_inverse_completion_edges(records, [inverse_rule(target_deficit=0, target_surplus=3)])
    assert edges == []
    assert stats["target_relation_overfilled"] == 1


def test_h4_b1_deficit_cap_selection_stops_at_target_relation_deficit():
    records = [
        TripleRecord("A", "R1", "B", "canonical_observed"),
        TripleRecord("C", "R1", "D", "canonical_observed"),
        TripleRecord("E", "R1", "F", "canonical_observed"),
    ]
    edges, stats = eligible_inverse_completion_edges(records, [inverse_rule(target_deficit=2)])
    selected, selection_stats = select_deficit_capped_inverse_edges(edges)
    assert stats["eligible_before_deficit_cap"] == 3
    assert len(selected) == 2
    assert selection_stats["selected"] == 2
    assert selection_stats["skipped_by_deficit_cap_after_ordering"] == 1
