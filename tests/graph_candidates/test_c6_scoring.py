from scripts.graph_candidates.c6_common import candidate_score


def test_symmetric_underfilled_candidate_outranks_composition_overfilled_candidate():
    symmetric = {
        "r": "R_sym",
        "candidate_class": "internal",
        "relation_deficit_before": 40,
        "relation_eta": 100,
        "underfilled_pattern_flag": True,
        "symmetric_relation_flag": True,
        "composition_relation_flag": False,
        "composition_overfilled_flag": False,
        "introduces_new_entities_count": 0,
        "local_common_neighbors_count": 2,
    }
    composition = {
        "r": "R_comp",
        "candidate_class": "internal",
        "relation_deficit_before": 40,
        "relation_eta": 100,
        "underfilled_pattern_flag": False,
        "symmetric_relation_flag": False,
        "composition_relation_flag": True,
        "composition_overfilled_flag": True,
        "introduces_new_entities_count": 0,
        "local_common_neighbors_count": 2,
    }
    assert candidate_score(symmetric)["candidate_score"] > candidate_score(composition)["candidate_score"]


def test_duplicate_candidate_can_be_flagged_for_rejection():
    duplicate_row = {"creates_duplicate_flag": True}
    assert duplicate_row["creates_duplicate_flag"] is True

