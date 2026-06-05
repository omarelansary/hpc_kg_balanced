from scripts.graph_candidates.c6_common import exact_best_subset, greedy_score_subset


def test_exact_enumeration_validates_greedy_on_simple_additive_case():
    candidates = [
        {"id": "a", "candidate_score": 5.0},
        {"id": "b", "candidate_score": 3.0},
        {"id": "c", "candidate_score": 1.0},
    ]

    def objective(subset):
        return sum(row["candidate_score"] for row in subset)

    exact, exact_score = exact_best_subset(candidates, 2, objective)
    greedy = greedy_score_subset(candidates, 2)
    assert [row["id"] for row in exact] == [row["id"] for row in greedy]
    assert exact_score == 8.0


def test_exact_enumeration_documents_non_global_optimality_counterexample():
    candidates = [
        {"id": "high_score_narrow", "candidate_score": 10.0, "covers": {"x"}},
        {"id": "medium_score_wide_1", "candidate_score": 9.0, "covers": {"a", "b"}},
        {"id": "medium_score_wide_2", "candidate_score": 8.0, "covers": {"c", "d"}},
    ]

    def coverage_objective(subset):
        covered = set()
        for row in subset:
            covered.update(row["covers"])
        return len(covered)

    exact, exact_score = exact_best_subset(candidates, 2, coverage_objective)
    greedy = greedy_score_subset(candidates, 2)
    assert exact_score == 4
    assert {row["id"] for row in exact} == {"medium_score_wide_1", "medium_score_wide_2"}
    assert {row["id"] for row in greedy} != {row["id"] for row in exact}

