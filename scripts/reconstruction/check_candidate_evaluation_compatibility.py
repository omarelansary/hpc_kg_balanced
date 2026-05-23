#!/usr/bin/env python3
"""Compare reusable candidate evaluation helpers with historical reports."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.candidate_report import evaluate_candidate  # noqa: E402

ALLOCATION = REPO_ROOT / "src/Pruning graph/bidirectional_allocation_results5k.json"


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    graph_path: Path
    allocation_path: Path
    report_path: Path
    required: bool = False
    report_schema: str = "standard_evaluator"


CANDIDATES = [
    CandidateSpec(
        candidate_id="B0_reaudit",
        graph_path=REPO_ROOT / "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv",
        allocation_path=ALLOCATION,
        report_path=REPO_ROOT / "artifacts/final_graph/selected_final_graph/rebuild/B0_reaudit.report.json",
        required=True,
    ),
    CandidateSpec(
        candidate_id="B0_registry_report",
        graph_path=REPO_ROOT / "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv",
        allocation_path=ALLOCATION,
        report_path=REPO_ROOT / "docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json",
    ),
    CandidateSpec(
        candidate_id="C1_stage13_aggressive",
        graph_path=REPO_ROOT / "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl",
        allocation_path=ALLOCATION,
        report_path=REPO_ROOT / "docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json",
    ),
    CandidateSpec(
        candidate_id="C2_targeted_generic_pruning",
        graph_path=REPO_ROOT / "experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl",
        allocation_path=ALLOCATION,
        report_path=REPO_ROOT / "experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json",
    ),
    CandidateSpec(
        candidate_id="strict_balance_pruned_ablation",
        graph_path=REPO_ROOT / "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_ablation_20260322_215639/pruned_graph.jsonl",
        allocation_path=ALLOCATION,
        report_path=REPO_ROOT / "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_ablation_20260322_215639/pruned_graph.report.json",
        report_schema="pruner_final_snapshot",
    ),
]

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


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_close(left: Any, right: Any, abs_tol: float = 1e-9) -> bool:
    if isinstance(left, int) and isinstance(right, int):
        return left == right
    try:
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=abs_tol)
    except (TypeError, ValueError):
        return left == right


def pattern_observed_from_standard_report(report: dict[str, Any]) -> dict[str, float]:
    rows = report.get("allocation_metrics", {}).get("pattern_level_expected_observed") or []
    return {
        str(row["pattern"]): float(row["observed_count_apportioned"])
        for row in rows
        if "pattern" in row and "observed_count_apportioned" in row
    }


def extract_standard_metrics(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, float], list[str]]:
    graph = report.get("graph_metrics") or {}
    allocation = report.get("allocation_metrics") or {}
    metrics: dict[str, Any] = {}
    for key in (
        "total_triples",
        "unique_triples",
        "unique_entities",
        "unique_relations",
        "weak_component_count",
        "largest_weak_component_ratio",
        "duplicate_triple_count",
    ):
        if key in graph:
            metrics[key] = graph[key]
    for key in (
        "allocated_relations_observed",
        "zero_allocated_relations",
        "total_surplus",
        "total_deficit",
    ):
        if key in allocation:
            metrics[key] = allocation[key]
    return metrics, pattern_observed_from_standard_report(report), []


def extract_pruner_final_snapshot_metrics(
    report: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, float], list[str]]:
    snapshot = report.get("final_snapshot") or {}
    metrics: dict[str, Any] = {}
    if "total_triples" in snapshot:
        metrics["total_triples"] = snapshot["total_triples"]
    if "total_entities" in snapshot:
        metrics["unique_entities"] = snapshot["total_entities"]
    relation_counts = snapshot.get("relation_counts")
    if isinstance(relation_counts, dict):
        metrics["unique_relations"] = len(relation_counts)
    if "weak_component_count" in snapshot:
        metrics["weak_component_count"] = snapshot["weak_component_count"]
    if "largest_component_ratio" in snapshot:
        metrics["largest_weak_component_ratio"] = snapshot["largest_component_ratio"]

    notes: list[str] = []
    if "pattern_counts" in snapshot:
        notes.append(
            "historical pruner report has raw pattern_counts, not evaluator eta-apportioned pattern totals"
        )
    if "relation_overcap" in snapshot:
        notes.append(
            "historical pruner report does not expose the standard evaluator total_surplus/total_deficit fields"
        )
    return metrics, {}, notes


def extract_historical_metrics(
    spec: CandidateSpec,
    report: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, float], list[str]]:
    if spec.report_schema == "standard_evaluator":
        return extract_standard_metrics(report)
    if spec.report_schema == "pruner_final_snapshot":
        return extract_pruner_final_snapshot_metrics(report)
    raise ValueError(f"unknown report schema for {spec.candidate_id}: {spec.report_schema}")


def new_metric_view(report: dict[str, Any]) -> dict[str, Any]:
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


def new_pattern_view(report: dict[str, Any]) -> dict[str, float]:
    rows = report["allocation_metrics"]["pattern_level_expected_observed"]
    return {
        str(row["pattern"]): float(row["observed_count_apportioned"])
        for row in rows
    }


def compare_candidate(spec: CandidateSpec) -> dict[str, Any]:
    missing = [
        path for path in (spec.graph_path, spec.allocation_path, spec.report_path)
        if not path.is_file()
    ]
    if missing:
        status = "real_metric_mismatch" if spec.required else "skipped_missing_artifact"
        return {
            "candidate_id": spec.candidate_id,
            "status": status,
            "comparable_metrics": 0,
            "metric_mismatches": [],
            "notes": [f"missing artifact: {rel(path)}" for path in missing],
        }

    new_report = evaluate_candidate(
        graph_path=spec.graph_path,
        allocation_path=spec.allocation_path,
        candidate_id=spec.candidate_id,
        label=spec.candidate_id,
    )
    historical_report = load_json(spec.report_path)
    historical_metrics, historical_patterns, schema_notes = extract_historical_metrics(
        spec,
        historical_report,
    )

    observed_metrics = new_metric_view(new_report)
    mismatches: list[dict[str, Any]] = []
    rounding_differences: list[dict[str, Any]] = []
    comparable = 0
    for key in CORE_METRICS:
        if key not in historical_metrics:
            continue
        comparable += 1
        observed = observed_metrics[key]
        expected = historical_metrics[key]
        if is_close(observed, expected):
            continue
        if is_close(round(float(observed)), round(float(expected)), abs_tol=0.0):
            rounding_differences.append({"metric": key, "new": observed, "historical": expected})
        else:
            mismatches.append({"metric": key, "new": observed, "historical": expected})

    pattern_mismatches: list[dict[str, Any]] = []
    if historical_patterns:
        observed_patterns = new_pattern_view(new_report)
        for pattern, expected in sorted(historical_patterns.items()):
            comparable += 1
            observed = observed_patterns.get(pattern)
            if observed is not None and is_close(observed, expected):
                continue
            if observed is not None and is_close(round(float(observed)), round(float(expected)), abs_tol=0.0):
                rounding_differences.append(
                    {"metric": f"pattern:{pattern}", "new": observed, "historical": expected}
                )
            else:
                pattern_mismatches.append(
                    {"metric": f"pattern:{pattern}", "new": observed, "historical": expected}
                )

    mismatches.extend(pattern_mismatches)
    notes = schema_notes[:]
    if rounding_differences:
        notes.append(f"expected rounding differences: {len(rounding_differences)}")

    if mismatches:
        status = "real_metric_mismatch"
    elif rounding_differences:
        status = "expected_rounding_difference"
    elif schema_notes:
        status = "schema_only_difference"
    else:
        status = "matched"

    return {
        "candidate_id": spec.candidate_id,
        "status": status,
        "comparable_metrics": comparable,
        "metric_mismatches": mismatches,
        "rounding_differences": rounding_differences,
        "notes": notes,
        "graph_path": rel(spec.graph_path),
        "report_path": rel(spec.report_path),
    }


def main() -> int:
    results = [compare_candidate(spec) for spec in CANDIDATES]

    print("candidate\tstatus\tcomparable_metrics\tnotes")
    for result in results:
        notes = "; ".join(result.get("notes") or [])
        print(
            f"{result['candidate_id']}\t{result['status']}\t"
            f"{result['comparable_metrics']}\t{notes}"
        )

    mismatches = [result for result in results if result["status"] == "real_metric_mismatch"]
    if mismatches:
        print("\nReal metric mismatches:", file=sys.stderr)
        for result in mismatches:
            print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    required = {spec.candidate_id for spec in CANDIDATES if spec.required}
    failed_required = [
        result for result in results
        if result["candidate_id"] in required and result["status"] != "matched"
    ]
    if failed_required:
        print("\nRequired candidates did not match exactly:", file=sys.stderr)
        for result in failed_required:
            print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    print("\nCandidate evaluation compatibility check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

