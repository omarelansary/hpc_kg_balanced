from scripts.graph_candidates.c6_common import compute_graph_metrics


def toy_allocation():
    return {
        "relation_expected": {"R_sym": 2.0, "R_comp": 1.0},
        "relation_patterns": {
            "R_sym": [{"pattern": "symmetric", "eta": 2.0}],
            "R_comp": [{"pattern": "composition", "eta": 1.0}],
        },
        "pattern_expected": {"symmetric": 2.0, "composition": 1.0},
    }


def test_metrics_include_density_connectivity_and_balance():
    triples = [("A", "R_sym", "B"), ("B", "R_comp", "C")]
    metrics = compute_graph_metrics(triples, toy_allocation())
    assert metrics["total_triples"] == 2
    assert metrics["total_entities"] == 3
    assert metrics["weak_component_count"] == 1
    assert metrics["allocated_relation_coverage_count"] == 2
    assert metrics["symmetric_deficit"] == 1.0
    assert metrics["composition_total"] == 1.0

