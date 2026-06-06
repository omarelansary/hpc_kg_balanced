#!/usr/bin/env python3
"""C6.4 deterministic add-then-safe-delete generator."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from c6_common import (
    DEFAULT_ALLOCATION,
    DEFAULT_B0_GRAPH,
    SCHEMA_VERSION,
    apply_safe_deletions,
    command_metadata,
    compute_graph_metrics,
    ensure_run_dir,
    load_allocation,
    load_graph_records,
    sha256_file,
    write_csv_rows,
    write_graph_csv,
    write_graph_jsonl,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir")
    parser.add_argument("--b0-graph", default=str(DEFAULT_B0_GRAPH))
    parser.add_argument("--allocation", default=str(DEFAULT_ALLOCATION))
    parser.add_argument("--added-graph")
    parser.add_argument("--safe-deletion-candidates")
    parser.add_argument("--max-deletions", type=int, default=2000)
    parser.add_argument("--allow_unverified_safe_deletions", action="store_true")
    parser.add_argument("--preserve_original_entities", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--allow_deficit_increase", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_deletion_rows(path: str | Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    args = parse_args()
    run_dir = ensure_run_dir(args.run_id, args.run_dir)
    added_graph = Path(args.added_graph) if args.added_graph else run_dir / "c6_added_graph.jsonl"
    safe_path = (
        Path(args.safe_deletion_candidates)
        if args.safe_deletion_candidates
        else run_dir / "c6_safe_deletion_candidates.csv"
    )
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "run_dir": str(run_dir),
                    "added_graph": str(added_graph),
                    "safe_deletion_candidates": str(safe_path),
                    "max_deletions": args.max_deletions,
                    "allow_unverified_safe_deletions": args.allow_unverified_safe_deletions,
                    "preserve_original_entities": args.preserve_original_entities,
                    "allow_deficit_increase": args.allow_deficit_increase,
                },
                indent=2,
            )
        )
        return 0
    if not added_graph.exists():
        raise FileNotFoundError(f"missing added graph: {added_graph}")
    if not safe_path.exists():
        raise FileNotFoundError(f"missing safe deletion candidates: {safe_path}")
    allocation = load_allocation(args.allocation)
    b0_records = load_graph_records(args.b0_graph)
    original_entities = {entity for record in b0_records for entity in (record.h, record.t)}
    added_records = load_graph_records(added_graph, source="c6_added_graph")
    deletion_rows = read_deletion_rows(safe_path)
    final_records, accepted_deletions, rejection_reasons, deletion_stats = apply_safe_deletions(
        added_records,
        deletion_rows,
        allocation,
        max_deletions=args.max_deletions,
        original_entities=original_entities,
        preserve_original_entities=args.preserve_original_entities,
        allow_unverified_safe_deletions=args.allow_unverified_safe_deletions,
        allow_deficit_increase=args.allow_deficit_increase,
    )
    before_metrics = compute_graph_metrics([record.triple for record in b0_records], allocation)
    after_addition_metrics = compute_graph_metrics([record.triple for record in added_records], allocation)
    after_deletion_metrics = compute_graph_metrics([record.triple for record in final_records], allocation)
    by_relation = Counter(row["r"] for row in accepted_deletions)
    write_graph_jsonl(run_dir / "c6_add_delete_graph.jsonl", final_records)
    write_graph_csv(run_dir / "c6_add_delete_graph.csv", final_records)
    write_csv_rows(
        run_dir / "c6_deletions.csv",
        accepted_deletions,
        [
            "accepted_order",
            "h",
            "r",
            "t",
            "patterns",
            "relation_surplus_before_b0",
            "relation_surplus_after_addition",
            "safe_before_additions",
            "safe_after_additions",
            "safe_after_not_before",
            "surplus_reduction_score",
        ],
    )
    if (
        after_deletion_metrics["weak_component_count"] != 1
        or after_deletion_metrics["allocated_relation_coverage_count"]
        != before_metrics["allocated_relation_coverage_count"]
        or deletion_stats["dropped_original_entity_count"] > 0
    ):
        final_decision = "failed_constraints"
    elif (
        after_deletion_metrics["total_surplus"] < before_metrics["total_surplus"]
        and after_deletion_metrics["total_deficit"] <= before_metrics["total_deficit"]
    ):
        final_decision = "promoted_candidate"
    else:
        final_decision = "diagnostic_only"

    report = {
        "schema_version": f"{SCHEMA_VERSION}.add-then-safe-delete",
        **command_metadata(run_dir, "c6_add_then_safe_delete"),
        "input_paths": {
            "b0_graph": args.b0_graph,
            "added_graph": str(added_graph),
            "safe_deletion_candidates": str(safe_path),
            "allocation": args.allocation,
        },
        "input_hashes": {
            "b0_graph": sha256_file(args.b0_graph),
            "added_graph": sha256_file(added_graph),
            "safe_deletion_candidates": sha256_file(safe_path),
            "allocation": sha256_file(args.allocation),
        },
        "max_deletions": args.max_deletions,
        "allow_unverified_safe_deletions": args.allow_unverified_safe_deletions,
        "preserve_original_entities": args.preserve_original_entities,
        "allow_deficit_increase": args.allow_deficit_increase,
        "before_b0_metrics": before_metrics,
        "after_addition_metrics": after_addition_metrics,
        "after_deletion_metrics": after_deletion_metrics,
        "deletions_accepted": len(accepted_deletions),
        "deletions_rejected": rejection_reasons,
        **deletion_stats,
        "deletions_by_relation": dict(sorted(by_relation.items())),
        "final_decision": final_decision,
    }
    write_json(run_dir / "c6_add_delete_report.json", report)
    print(
        json.dumps(
            {
                "status": "passed",
                "run_dir": str(run_dir),
                "deletions_accepted": len(accepted_deletions),
                "weak_component_count": after_deletion_metrics["weak_component_count"],
                "allocated_relation_coverage_count": after_deletion_metrics["allocated_relation_coverage_count"],
                "total_surplus": after_deletion_metrics["total_surplus"],
                "final_decision": report["final_decision"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
