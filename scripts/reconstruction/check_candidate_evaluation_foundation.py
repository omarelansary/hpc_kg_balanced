#!/usr/bin/env python3
"""Golden-master check for reusable graph candidate evaluation helpers."""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.candidate_report import evaluate_candidate  # noqa: E402

B0_GRAPH = REPO_ROOT / "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv"
ALLOCATION = REPO_ROOT / "src/Pruning graph/bidirectional_allocation_results5k.json"

EXPECTED_GRAPH_METRICS = {
    "unique_triples": 24683,
    "unique_entities": 21893,
    "unique_relations": 139,
    "weak_component_count": 1,
    "duplicate_triple_count": 0,
}

EXPECTED_ALLOCATION_METRICS = {
    "allocated_relations_observed": 139,
    "zero_allocated_relations": 0,
    "total_surplus": 6702,
    "total_deficit": 2019,
}

EXPECTED_PATTERN_TOTALS = {
    "anti_symmetric": 4970,
    "composition": 11267,
    "inverse": 4824,
    "symmetric": 3622,
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def compare_number(label: str, observed: float, expected: float) -> None:
    if not math.isclose(float(observed), float(expected), rel_tol=0.0, abs_tol=1e-9):
        fail(f"{label}: observed {observed!r}, expected {expected!r}")


def main() -> int:
    for path in (B0_GRAPH, ALLOCATION):
        if not path.is_file():
            fail(f"required input missing: {path}")

    report = evaluate_candidate(
        graph_path=B0_GRAPH,
        allocation_path=ALLOCATION,
        candidate_id="B0",
        label="Stage12 repaired largest component",
    )

    graph_metrics = report["graph_metrics"]
    allocation_metrics = report["allocation_metrics"]
    for key, expected in EXPECTED_GRAPH_METRICS.items():
        observed = graph_metrics[key]
        compare_number(key, observed, expected)

    compare_number("largest_weak_component_ratio", graph_metrics["largest_weak_component_ratio"], 1.0)

    for key, expected in EXPECTED_ALLOCATION_METRICS.items():
        observed = allocation_metrics[key]
        compare_number(key, observed, expected)

    pattern_totals = report["pattern_balance_summary"]["pattern_observed_integer_totals"]
    for pattern, expected in EXPECTED_PATTERN_TOTALS.items():
        observed = pattern_totals.get(pattern)
        compare_number(f"pattern {pattern}", observed, expected)

    print("Candidate evaluation foundation check passed.")
    print(
        "B0 metrics: "
        f"unique_triples={graph_metrics['unique_triples']}, "
        f"unique_entities={graph_metrics['unique_entities']}, "
        f"unique_relations={graph_metrics['unique_relations']}, "
        f"weak_components={graph_metrics['weak_component_count']}, "
        f"duplicate_triples={graph_metrics['duplicate_triple_count']}, "
        f"total_surplus={allocation_metrics['total_surplus']:.12g}, "
        f"total_deficit={allocation_metrics['total_deficit']:.12g}"
    )
    print(
        "Pattern integer totals: "
        + ", ".join(f"{key}={pattern_totals[key]}" for key in sorted(EXPECTED_PATTERN_TOTALS))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

