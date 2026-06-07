from scripts.graph_candidates.h4_common import (
    SYNTHETIC_EDGE_SOURCE,
    TripleRecord,
    apply_h4_safe_deletions,
)
from scripts.graph_candidates.h4_inverse_closure_sweep import (
    GLOBAL_OPTIMUM_LIMITATION,
    build_inverse_edges,
    classify_decision,
    synthetic_inverse_record,
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
        "risk_flags": [],
    }


def toy_allocation(expected_r1=1.0, expected_r2=1.0):
    return {
        "relation_expected": {"R1": expected_r1, "R2": expected_r2},
        "relation_patterns": {
            "R1": [{"pattern": "inverse", "eta": expected_r1}],
            "R2": [{"pattern": "inverse", "eta": expected_r2}],
        },
        "pattern_expected": {"inverse": expected_r1 + expected_r2},
    }


def test_b1_excludes_frozen_observed_inverse_edges():
    records = [TripleRecord("A", "R1", "B", "canonical_observed")]
    selected, stats = build_inverse_edges(
        records,
        [inverse_rule()],
        {("B", "R2", "A")},
        confidence_threshold=0.8,
        require_underfilled=True,
        allow_overfilled_targets=False,
        deficit_capped=True,
    )
    assert selected == []
    assert stats["already_frozen_observed"] == 1


def test_b1_respects_confidence_threshold():
    records = [TripleRecord("A", "R1", "B", "canonical_observed")]
    selected, stats = build_inverse_edges(
        records,
        [inverse_rule(confidence=0.79)],
        set(),
        confidence_threshold=0.8,
        require_underfilled=True,
        allow_overfilled_targets=False,
        deficit_capped=True,
    )
    assert selected == []
    assert stats["below_confidence_threshold"] == 1


def test_b1_respects_target_deficit_cap():
    records = [
        TripleRecord("A", "R1", "B", "canonical_observed"),
        TripleRecord("C", "R1", "D", "canonical_observed"),
        TripleRecord("E", "R1", "F", "canonical_observed"),
    ]
    selected, stats = build_inverse_edges(
        records,
        [inverse_rule(target_deficit=2)],
        set(),
        confidence_threshold=0.8,
        require_underfilled=True,
        allow_overfilled_targets=False,
        deficit_capped=True,
    )
    assert len(selected) == 2
    assert stats["selected"] == 2
    assert stats["skipped_by_deficit_cap_after_ordering"] == 1


def test_b2_add_all_allows_larger_synthetic_mass_and_is_stress():
    records = [TripleRecord("A", "R1", "B", "canonical_observed")]
    selected, stats = build_inverse_edges(
        records,
        [inverse_rule(confidence=0.6, target_deficit=0, target_surplus=5)],
        set(),
        confidence_threshold=None,
        require_underfilled=False,
        allow_overfilled_targets=True,
        deficit_capped=False,
    )
    assert len(selected) == 1
    assert stats["generated_targeting_overfilled_relation"] == 1
    assert classify_decision(
        mode_role="stress_test",
        before_metrics={"total_deficit": 10, "triples_per_entity": 1, "total_surplus": 1},
        after_metrics={"total_deficit": 9, "triples_per_entity": 2, "total_surplus": 1},
        constraints={"passed": True},
        generated_edges=1,
        generated_observed_overlap=0,
    ) == "stress_test_only"


def test_b3_safe_delete_preserves_base_triples_and_synthetic_edges_by_default():
    b0 = [TripleRecord("A", "R1", "B"), TripleRecord("C", "R1", "D")]
    synthetic = synthetic_inverse_record(b0[0], inverse_rule())
    final, accepted, rejections, stats, _candidates = apply_h4_safe_deletions(
        b0,
        b0 + [synthetic],
        toy_allocation(),
        preserve_original_entities=True,
        allow_deficit_increase=True,
        allow_delete_base_triples_for_retained_synthetic=False,
    )
    final_triples = {record.triple for record in final}
    assert not accepted
    assert ("A", "R1", "B") in final_triples
    assert synthetic.triple in final_triples
    assert rejections["deletes_base_triple_for_retained_synthetic_edge"] == 1
    assert stats["deleted_base_triples_for_retained_synthetic_edges_count"] == 0
    assert stats["synthetic_edges_deleted"] == 0


def test_candidate_decision_label_requires_non_stress_good_metrics():
    assert classify_decision(
        mode_role="candidate",
        before_metrics={"total_deficit": 10, "triples_per_entity": 1, "total_surplus": 1},
        after_metrics={"total_deficit": 9, "triples_per_entity": 2, "total_surplus": 1},
        constraints={"passed": True},
        generated_edges=1,
        generated_observed_overlap=0,
    ) == "synthetic_augmented_candidate_for_review"
    assert classify_decision(
        mode_role="candidate",
        before_metrics={"total_deficit": 10, "triples_per_entity": 1, "total_surplus": 1},
        after_metrics={"total_deficit": 9, "triples_per_entity": 2, "total_surplus": 1},
        constraints={"passed": True},
        generated_edges=1,
        generated_observed_overlap=1,
    ) == "failed_constraints"


def test_report_json_global_optimum_limitation_text_is_available():
    assert "not a global optimum proof" in GLOBAL_OPTIMUM_LIMITATION
    assert "bounded sweep" in GLOBAL_OPTIMUM_LIMITATION
