from scripts.graph_candidates.c6_common import classify_candidate, candidate_score


def test_internal_candidate_adds_no_entities_and_scores_existing_endpoints():
    row = {
        "r": "R1",
        "candidate_class": "internal",
        "relation_deficit_before": 10,
        "relation_eta": 20,
        "underfilled_pattern_flag": True,
        "symmetric_relation_flag": False,
        "composition_relation_flag": False,
        "composition_overfilled_flag": False,
        "introduces_new_entities_count": 0,
        "local_common_neighbors_count": 1,
    }
    assert classify_candidate("A", "B", {"A", "B", "C"}) == "internal"
    score = candidate_score(row)
    assert score["existing_endpoint_score"] == 1.0
    assert score["new_entity_penalty"] == 0.0
    assert score["candidate_score"] > 0


def test_external_candidate_introduces_two_entities_and_is_penalized():
    row = {
        "r": "R1",
        "candidate_class": "external",
        "relation_deficit_before": 10,
        "relation_eta": 20,
        "underfilled_pattern_flag": True,
        "symmetric_relation_flag": False,
        "composition_relation_flag": False,
        "composition_overfilled_flag": False,
        "introduces_new_entities_count": 2,
        "local_common_neighbors_count": 0,
    }
    assert classify_candidate("X", "Y", {"A", "B", "C"}) == "external"
    score = candidate_score(row)
    assert score["existing_endpoint_score"] == 0.0
    assert score["new_entity_penalty"] == 2.0

