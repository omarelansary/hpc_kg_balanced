from scripts.graph_candidates.c6_common import candidate_score, select_additions


def toy_allocation():
    return {
        "relation_expected": {"R_sym": 2.0, "R_comp": 1.0},
        "relation_patterns": {
            "R_sym": [{"pattern": "symmetric", "eta": 2.0}],
            "R_comp": [{"pattern": "composition", "eta": 1.0}],
        },
        "pattern_expected": {"symmetric": 2.0, "composition": 1.0},
    }


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


def test_negative_score_candidate_is_rejected_by_default():
    rows = [
        {
            "h": "A",
            "r": "R_sym",
            "t": "C",
            "candidate_class": "internal",
            "candidate_score": -0.1,
            "pattern_memberships": "symmetric",
        }
    ]
    accepted, rejections, stats = select_additions(
        rows,
        [("A", "R_sym", "B"), ("B", "R_sym", "C")],
        toy_allocation(),
        {"min_score": 0.0, "composition_addition_policy": "forbid_if_overfilled"},
    )
    assert accepted == []
    assert rejections["score_below_threshold"] == 1
    assert stats["accepted_negative_score_count"] == 0


def test_overfilled_composition_candidate_is_rejected_when_forbidden():
    rows = [
        {
            "h": "A",
            "r": "R_comp",
            "t": "C",
            "candidate_class": "internal",
            "candidate_score": 1.0,
            "pattern_memberships": "composition",
        }
    ]
    accepted, rejections, _stats = select_additions(
        rows,
        [("A", "R_comp", "B"), ("B", "R_sym", "C")],
        toy_allocation(),
        {"composition_addition_policy": "forbid_if_overfilled"},
    )
    assert accepted == []
    assert rejections["composition_overfilled_forbidden"] == 1


def test_overfilled_composition_candidate_can_be_allowed_but_reported():
    rows = [
        {
            "h": "A",
            "r": "R_comp",
            "t": "C",
            "candidate_class": "internal",
            "candidate_score": 1.0,
            "pattern_memberships": "composition",
        }
    ]
    accepted, _rejections, stats = select_additions(
        rows,
        [("A", "R_comp", "B"), ("B", "R_sym", "C")],
        toy_allocation(),
        {"composition_addition_policy": "penalize_if_overfilled"},
    )
    assert len(accepted) == 1
    assert stats["accepted_composition_penalized_count"] == 1
