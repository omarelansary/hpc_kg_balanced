#!/usr/bin/env python3
"""Validate the reusable graph candidate registry."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.candidate_report import evaluate_candidate  # noqa: E402
from src.kg_pipeline.registry.candidate_registry import (  # noqa: E402
    candidate_by_id,
    evidence_only_entries,
    graph_candidates,
    load_registry,
    summarize_registry,
    validate_candidate_hashes,
    validate_candidate_paths_exist,
    validate_registry_schema,
)

REGISTRY_PATH = REPO_ROOT / "artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json"

CORE_METRICS = [
    "total_triples",
    "unique_triples",
    "unique_entities",
    "unique_relations",
    "weak_component_count",
    "largest_weak_component_ratio",
    "duplicate_triple_count",
    "allocated_relations_observed",
    "zero_allocated_relations",
    "total_surplus",
    "total_deficit",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(path: str) -> Path:
    candidate_path = Path(path)
    if candidate_path.is_absolute():
        return candidate_path
    return REPO_ROOT / candidate_path


def is_close(left: Any, right: Any, abs_tol: float = 1e-9) -> bool:
    if isinstance(left, int) and isinstance(right, int):
        return left == right
    try:
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=abs_tol)
    except (TypeError, ValueError):
        return left == right


def metric_view(report: dict[str, Any]) -> dict[str, Any]:
    graph = report["graph_metrics"]
    allocation = report["allocation_metrics"]
    return {
        "total_triples": graph["total_triples"],
        "unique_triples": graph["unique_triples"],
        "unique_entities": graph["unique_entities"],
        "unique_relations": graph["unique_relations"],
        "weak_component_count": graph["weak_component_count"],
        "largest_weak_component_ratio": graph["largest_weak_component_ratio"],
        "duplicate_triple_count": graph["duplicate_triple_count"],
        "allocated_relations_observed": allocation["allocated_relations_observed"],
        "zero_allocated_relations": allocation["zero_allocated_relations"],
        "total_surplus": allocation["total_surplus"],
        "total_deficit": allocation["total_deficit"],
    }


def pattern_view(report: dict[str, Any]) -> dict[str, float]:
    rows = report["allocation_metrics"].get("pattern_level_expected_observed") or []
    return {
        str(row["pattern"]): float(row["observed_count_apportioned"])
        for row in rows
        if "pattern" in row and "observed_count_apportioned" in row
    }


def compare_standard_report(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    graph_path = resolve(candidate["graph_path"])
    allocation_path = resolve(candidate["allocation_path"])
    report_path = resolve(candidate["report_path"])

    new_report = evaluate_candidate(
        graph_path=graph_path,
        allocation_path=allocation_path,
        candidate_id=candidate["candidate_id"],
        label=candidate["label"],
    )
    historical_report = load_json(report_path)

    new_metrics = metric_view(new_report)
    historical_metrics = metric_view(historical_report)
    mismatches: list[dict[str, Any]] = []
    for key in CORE_METRICS:
        observed = new_metrics[key]
        expected = historical_metrics[key]
        if not is_close(observed, expected):
            mismatches.append({"metric": key, "new": observed, "historical": expected})

    new_patterns = pattern_view(new_report)
    historical_patterns = pattern_view(historical_report)
    for pattern, expected in sorted(historical_patterns.items()):
        observed = new_patterns.get(pattern)
        if observed is None or not is_close(observed, expected):
            mismatches.append(
                {"metric": f"pattern:{pattern}", "new": observed, "historical": expected}
            )
    return mismatches


def main() -> int:
    if not REGISTRY_PATH.is_file():
        fail(f"registry missing: {REGISTRY_PATH}")

    registry = load_registry(REGISTRY_PATH)
    schema_errors = validate_registry_schema(registry)
    if schema_errors:
        fail("registry schema errors: " + "; ".join(schema_errors))

    path_results = validate_candidate_paths_exist(registry, REPO_ROOT)
    if path_results["missing"]:
        fail("missing registry artifacts: " + json.dumps(path_results["missing"], sort_keys=True))

    hash_results = validate_candidate_hashes(registry, REPO_ROOT)
    if hash_results["missing"] or hash_results["mismatched"]:
        fail(
            "hash validation failed: "
            + json.dumps(
                {
                    "missing": hash_results["missing"],
                    "mismatched": hash_results["mismatched"],
                },
                sort_keys=True,
            )
        )

    b0 = candidate_by_id(registry, "B0")
    if not b0:
        fail("B0 missing from registry")
    if b0.get("role") != "selected_baseline":
        fail(f"B0 role mismatch: {b0.get('role')!r}")

    c3 = candidate_by_id(registry, "C3_probe_v1")
    if not c3:
        fail("C3_probe_v1 missing from registry")
    if c3.get("is_graph_candidate") is not False:
        fail("C3_probe_v1 must not be a graph candidate")
    if c3.get("graph_path") is not None:
        fail("C3_probe_v1 must not require graph_path")

    comparison_results: list[dict[str, Any]] = []
    for candidate in graph_candidates(registry):
        if candidate.get("report_schema") != "standard_evaluator":
            comparison_results.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "status": "skipped_schema",
                    "reason": candidate.get("report_schema"),
                }
            )
            continue
        mismatches = compare_standard_report(candidate)
        comparison_results.append(
            {
                "candidate_id": candidate["candidate_id"],
                "status": "matched" if not mismatches else "real_metric_mismatch",
                "mismatches": mismatches,
            }
        )

    mismatches = [row for row in comparison_results if row["status"] == "real_metric_mismatch"]
    if mismatches:
        fail("standard evaluator comparison mismatches: " + json.dumps(mismatches, sort_keys=True))

    summary = summarize_registry(registry)
    print("Candidate registry check passed.")
    print(
        "summary: "
        f"candidates={summary['candidate_count']}, "
        f"graph_candidates={summary['graph_candidate_count']}, "
        f"evidence_only={summary['evidence_only_count']}"
    )
    print(f"hashes_checked={len(hash_results['checked'])}")
    print("comparison_status:")
    for result in comparison_results:
        extra = result.get("reason") or ""
        print(f"- {result['candidate_id']}: {result['status']} {extra}".rstrip())
    print("evidence_only_entries:")
    for entry in evidence_only_entries(registry):
        print(f"- {entry['candidate_id']}: {entry['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

