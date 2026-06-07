from scripts.graph_candidates.h4_common import (
    SYNTHETIC_EDGE_SOURCE,
    TripleRecord,
    apply_h4_safe_deletions,
    h4_safe_deletion_candidates,
)


def toy_allocation(expected=2.0):
    return {
        "relation_expected": {"R": expected},
        "relation_patterns": {"R": [{"pattern": "symmetric", "eta": expected}]},
        "pattern_expected": {"symmetric": expected},
    }


def test_h4_safe_delete_candidates_are_original_b0_edges_only():
    b0 = [TripleRecord("A", "R", "B"), TripleRecord("B", "R", "C")]
    synthetic = TripleRecord("B", "R", "A", SYNTHETIC_EDGE_SOURCE, {"rule_type": "symmetric_reverse_completion"})
    rows = h4_safe_deletion_candidates(b0, b0 + [synthetic], toy_allocation(expected=1.0))
    triples = {(row["h"], row["r"], row["t"]) for row in rows}
    assert ("A", "R", "C") not in triples
    assert all(row["deletes_edge_source"] == "canonical_observed" for row in rows)


def test_h4_safe_delete_preserves_synthetic_edges_by_default():
    b0 = [TripleRecord("A", "R", "B"), TripleRecord("B", "R", "C")]
    synthetic = TripleRecord("B", "R", "A", SYNTHETIC_EDGE_SOURCE, {"rule_type": "symmetric_reverse_completion"})
    final, accepted, _rejections, stats, _candidates = apply_h4_safe_deletions(
        b0,
        b0 + [synthetic],
        toy_allocation(expected=1.0),
        preserve_original_entities=True,
        allow_deficit_increase=True,
    )
    assert accepted
    assert synthetic.triple in {record.triple for record in final}
    assert stats["synthetic_edges_deleted"] == 0


def synthetic_reverse(base_h="A", base_r="R", base_t="B"):
    return TripleRecord(
        base_t,
        base_r,
        base_h,
        SYNTHETIC_EDGE_SOURCE,
        {
            "rule_type": "symmetric_reverse_completion",
            "base_h": base_h,
            "base_r": base_r,
            "base_t": base_t,
            "generated_h": base_t,
            "generated_r": base_r,
            "generated_t": base_h,
        },
    )


def test_h4_safe_delete_rejects_base_triple_deletion_by_default():
    b0 = [TripleRecord("A", "R", "B"), TripleRecord("C", "R", "D")]
    synthetic = synthetic_reverse("A", "R", "B")
    final, accepted, rejections, stats, _candidates = apply_h4_safe_deletions(
        b0,
        b0 + [synthetic],
        toy_allocation(expected=1.0),
        preserve_original_entities=True,
        allow_deficit_increase=True,
    )
    assert not accepted
    assert ("A", "R", "B") in {record.triple for record in final}
    assert synthetic.triple in {record.triple for record in final}
    assert rejections["deletes_base_triple_for_retained_synthetic_edge"] == 1
    assert stats["preserve_base_triples_for_retained_synthetic_edges"] is True
    assert stats["base_triples_supporting_retained_synthetic_edges_count"] == 1
    assert stats["deleted_base_triples_for_retained_synthetic_edges_count"] == 0
    assert stats["rejected_deletes_base_triple_for_retained_synthetic_edge_count"] == 1


def test_h4_safe_delete_explicit_allow_base_triple_deletion_reports_it():
    b0 = [TripleRecord("A", "R", "B"), TripleRecord("C", "R", "D")]
    synthetic = synthetic_reverse("A", "R", "B")
    final, accepted, _rejections, stats, _candidates = apply_h4_safe_deletions(
        b0,
        b0 + [synthetic],
        toy_allocation(expected=1.0),
        preserve_original_entities=True,
        allow_deficit_increase=True,
        allow_delete_base_triples_for_retained_synthetic=True,
    )
    assert accepted
    assert ("A", "R", "B") not in {record.triple for record in final}
    assert synthetic.triple in {record.triple for record in final}
    assert accepted[0]["is_base_triple_for_retained_synthetic_edge"] is True
    assert stats["preserve_base_triples_for_retained_synthetic_edges"] is False
    assert stats["allow_delete_base_triples_for_retained_synthetic"] is True
    assert stats["base_triples_supporting_retained_synthetic_edges_count"] == 1
    assert stats["deleted_base_triples_for_retained_synthetic_edges_count"] == 1
    assert stats["synthetic_edges_deleted"] == 0
