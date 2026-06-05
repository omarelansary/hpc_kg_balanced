from scripts.graph_candidates.c6_common import structurally_safe_to_remove


def test_bridge_deletion_is_rejected():
    triples = [("A", "R", "B"), ("B", "R", "C")]
    assert structurally_safe_to_remove(triples, ("A", "R", "B")) is False


def test_deletion_after_adding_alternative_path_becomes_safe():
    triples = [("A", "R", "B"), ("B", "R", "C"), ("A", "R2", "C")]
    assert structurally_safe_to_remove(triples, ("A", "R", "B")) is True

