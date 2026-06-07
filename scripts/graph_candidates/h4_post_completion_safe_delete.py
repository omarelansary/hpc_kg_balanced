#!/usr/bin/env python3
"""Run strict safe deletion after H4 labelled symmetric completion."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from h4_common import (
    DEFAULT_ALLOCATION,
    DEFAULT_B0_GRAPH,
    SCHEMA_VERSION,
    apply_h4_safe_deletions,
    command_metadata,
    compute_h4_metrics,
    constraints_summary,
    ensure_run_dir,
    load_allocation,
    load_b0_records,
    load_h4_graph_records,
    sha256_file,
    write_csv_rows,
    write_h4_graph_csv,
    write_h4_graph_jsonl,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir")
    parser.add_argument("--b0-graph", default=str(DEFAULT_B0_GRAPH))
    parser.add_argument("--allocation", default=str(DEFAULT_ALLOCATION))
    parser.add_argument("--completed-graph")
    parser.add_argument("--max-deletions", type=int, default=100000)
    parser.add_argument("--preserve-original-entities", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--allow-deficit-increase", action="store_true")
    parser.add_argument("--allow-singleton-connectivity-checks", action="store_true")
    parser.add_argument(
        "--allow_delete_base_triples_for_retained_synthetic",
        "--allow-delete-base-triples-for-retained-synthetic",
        action="store_true",
        help="Diagnostic mode: allow deleting B0 base triples that support retained synthetic H4 edges.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


DELETION_FIELDS = [
    "accepted_order",
    "h",
    "r",
    "t",
    "patterns",
    "relation_surplus_before_b0",
    "relation_surplus_after_addition",
    "relation_overfilled",
    "pattern_overfilled",
    "safe_before_additions",
    "safe_after_additions",
    "safe_after_not_before",
    "surplus_reduction_score",
    "deletes_edge_source",
    "synthetic_edges_available",
    "is_base_triple_for_retained_synthetic_edge",
]


def decision_state(before: dict, after_completion: dict, after_deletion: dict, constraints: dict, deletions: int) -> str:
    if not constraints["passed"]:
        return "failed_constraints"
    if deletions <= 0:
        return "diagnostic_only"
    if (
        after_deletion["total_surplus"] < before["total_surplus"]
        and after_deletion["symmetric_deficit"] < before["symmetric_deficit"]
        and after_deletion["triples_per_entity"] > before["triples_per_entity"]
    ):
        return "synthetic_augmented_candidate"
    if after_completion["symmetric_deficit"] < before["symmetric_deficit"]:
        return "diagnostic_only"
    return "failed_constraints"


def main() -> int:
    args = parse_args()
    run_dir = ensure_run_dir(args.run_id, args.run_dir)
    completed_graph = Path(args.completed_graph) if args.completed_graph else run_dir / "h4_generated_graph.jsonl"
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "run_dir": str(run_dir), "completed_graph": str(completed_graph)}, indent=2))
        return 0
    if not completed_graph.exists():
        raise FileNotFoundError(f"missing completed H4 graph: {completed_graph}")

    allocation = load_allocation(args.allocation)
    b0_records = load_b0_records(args.b0_graph)
    completed_records = load_h4_graph_records(completed_graph)
    before_metrics = compute_h4_metrics(b0_records, allocation)
    after_completion_metrics = compute_h4_metrics(completed_records, allocation)
    final_records, accepted, rejections, deletion_stats, deletion_candidates = apply_h4_safe_deletions(
        b0_records,
        completed_records,
        allocation,
        max_deletions=args.max_deletions,
        preserve_original_entities=args.preserve_original_entities,
        allow_deficit_increase=args.allow_deficit_increase,
        allow_singleton_connectivity_checks=args.allow_singleton_connectivity_checks,
        allow_delete_base_triples_for_retained_synthetic=args.allow_delete_base_triples_for_retained_synthetic,
    )
    after_deletion_metrics = compute_h4_metrics(final_records, allocation)
    constraints = constraints_summary(after_deletion_metrics, allocation)
    by_relation = Counter(row["r"] for row in accepted)

    write_csv_rows(run_dir / "h4_safe_deletions.csv", accepted, DELETION_FIELDS)
    write_h4_graph_csv(run_dir / "h4_add_delete_graph.csv", final_records)
    write_h4_graph_jsonl(run_dir / "h4_add_delete_graph.jsonl", final_records)
    report = {
        "schema_version": f"{SCHEMA_VERSION}.post-completion-safe-delete",
        **command_metadata(run_dir, "h4_post_completion_safe_delete"),
        "input_paths": {
            "b0_graph": args.b0_graph,
            "completed_graph": str(completed_graph),
            "allocation": args.allocation,
        },
        "input_hashes": {
            "b0_graph": sha256_file(args.b0_graph),
            "completed_graph": sha256_file(completed_graph),
            "allocation": sha256_file(args.allocation),
        },
        "max_deletions": args.max_deletions,
        "preserve_original_entities": args.preserve_original_entities,
        "allow_deficit_increase": args.allow_deficit_increase,
        "delete_synthetic_edges": False,
        "allow_singleton_connectivity_checks": args.allow_singleton_connectivity_checks,
        "allow_delete_base_triples_for_retained_synthetic": args.allow_delete_base_triples_for_retained_synthetic,
        "preserve_base_triples_for_retained_synthetic_edges": not args.allow_delete_base_triples_for_retained_synthetic,
        "before_b0_metrics": before_metrics,
        "after_completion_metrics": after_completion_metrics,
        "after_deletion_metrics": after_deletion_metrics,
        "hard_constraints": constraints,
        "safe_deletion_candidate_count": len(deletion_candidates),
        "safe_after_not_before_count": deletion_stats.get("safe_after_not_before_count", 0),
        "deletions_accepted": len(accepted),
        "accepted_safe_after_not_before_count": deletion_stats.get("accepted_safe_after_not_before_count", 0),
        "deletions_by_relation": dict(sorted(by_relation.items())),
        "deletions_rejected": rejections,
        **deletion_stats,
        "outputs": {
            "safe_deletions_csv": str(run_dir / "h4_safe_deletions.csv"),
            "add_delete_graph_csv": str(run_dir / "h4_add_delete_graph.csv"),
            "add_delete_graph_jsonl": str(run_dir / "h4_add_delete_graph.jsonl"),
            "add_delete_report": str(run_dir / "h4_add_delete_report.json"),
        },
        "claim_boundary": (
            "Safe deletion removes only original B0 canonical observed edges by default. "
            "Synthetic H4 edges remain labelled and separable. Base triples that support retained "
            "synthetic edges are preserved unless the explicit diagnostic override is enabled."
        ),
    }
    report["final_decision_state"] = decision_state(
        before_metrics,
        after_completion_metrics,
        after_deletion_metrics,
        constraints,
        len(accepted),
    )
    write_json(run_dir / "h4_add_delete_report.json", report)
    print(
        json.dumps(
            {
                "status": "passed" if constraints["passed"] else "failed_constraints",
                "run_dir": str(run_dir),
                "deletions_accepted": len(accepted),
                "accepted_safe_after_not_before_count": report["accepted_safe_after_not_before_count"],
                "total_surplus_after": after_deletion_metrics["total_surplus"],
                "symmetric_deficit_after": after_deletion_metrics["symmetric_deficit"],
                "weak_component_count": after_deletion_metrics["weak_component_count"],
                "final_decision_state": report["final_decision_state"],
            },
            indent=2,
        )
    )
    return 0 if constraints["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
