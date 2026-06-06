from scripts.graph_candidates.c6_common import TripleRecord, apply_safe_deletions, structurally_safe_to_remove


def toy_allocation(expected=3.0):
    return {
        "relation_expected": {"R": expected},
        "relation_patterns": {"R": [{"pattern": "symmetric", "eta": expected}]},
        "pattern_expected": {"symmetric": expected},
    }


def test_bridge_deletion_is_rejected():
    triples = [("A", "R", "B"), ("B", "R", "C")]
    assert structurally_safe_to_remove(triples, ("A", "R", "B")) is False


def test_deletion_after_adding_alternative_path_becomes_safe():
    triples = [("A", "R", "B"), ("B", "R", "C"), ("A", "R2", "C")]
    assert structurally_safe_to_remove(triples, ("A", "R", "B")) is True


def test_multiple_ht_triples_can_be_structurally_safe_if_entities_remain():
    triples = [("A", "R", "B"), ("A", "R2", "B"), ("B", "R", "C")]
    assert structurally_safe_to_remove(triples, ("A", "R", "B")) is True


def test_add_then_delete_ignores_unverified_safe_rows_by_default():
    records = [TripleRecord("A", "R", "B"), TripleRecord("B", "R", "C"), TripleRecord("A", "R", "C")]
    final, accepted, rejections, stats = apply_safe_deletions(
        records,
        [{"h": "A", "r": "R", "t": "B", "safe_after_additions": "False"}],
        toy_allocation(),
        original_entities={"A", "B", "C"},
    )
    assert final == records
    assert accepted == []
    assert rejections["safe_after_additions_false"] == 1
    assert stats["safe_after_additions_false_skipped_count"] == 1


def test_deletion_increasing_total_deficit_is_rejected_by_default():
    records = [TripleRecord("A", "R", "B"), TripleRecord("B", "R", "C"), TripleRecord("A", "R", "C")]
    final, accepted, rejections, stats = apply_safe_deletions(
        records,
        [{"h": "A", "r": "R", "t": "B", "safe_after_additions": "True"}],
        toy_allocation(expected=3.0),
        original_entities={"A", "B", "C"},
    )
    assert final == records
    assert accepted == []
    assert rejections["increases_total_deficit"] == 1
    assert stats["increases_total_deficit_rejected_count"] == 1
