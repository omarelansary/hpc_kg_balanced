#!/usr/bin/env python3
"""Generate labelled H4-A symmetric reverse-completion outputs."""

from __future__ import annotations

import argparse
import json
from collections import Counter

from h4_common import (
    DEFAULT_ALLOCATION,
    DEFAULT_B0_GRAPH,
    DEFAULT_H4_AUDIT,
    SCHEMA_VERSION,
    command_metadata,
    compute_h4_metrics,
    constraints_summary,
    eligible_symmetric_completion_edges,
    ensure_run_dir,
    load_allocation,
    load_b0_records,
    load_h4_audit,
    select_completion_edges,
    sha256_file,
    stage2_observed_reverse_candidates,
    symmetric_relation_meta,
    top_counts,
    write_csv_rows,
    write_h4_graph_csv,
    write_h4_graph_jsonl,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir")
    parser.add_argument("--graph", default=str(DEFAULT_B0_GRAPH))
    parser.add_argument("--allocation", default=str(DEFAULT_ALLOCATION))
    parser.add_argument("--h4-audit", default=str(DEFAULT_H4_AUDIT))
    parser.add_argument("--mode", choices=["deficit-capped", "add-all"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


GENERATED_EDGE_FIELDS = [
    "h",
    "r",
    "t",
    "edge_source",
    "rule_type",
    "source_relation",
    "base_h",
    "base_r",
    "base_t",
    "generated_h",
    "generated_r",
    "generated_t",
    "verification_source",
    "confidence",
    "confidence_reason",
    "support",
    "evidence_status",
]


def generated_edge_rows(records) -> list[dict]:
    from h4_common import h4_record_to_row

    return [h4_record_to_row(record) for record in records]


def decision_state(mode: str, before: dict, after: dict, constraints: dict) -> str:
    if not constraints["passed"]:
        return "failed_constraints"
    if mode == "add-all":
        return "diagnostic_upper_bound_stress_test"
    if (
        after["symmetric_deficit"] < before["symmetric_deficit"]
        and after["triples_per_entity"] > before["triples_per_entity"]
    ):
        return "synthetic_augmented_candidate"
    return "diagnostic_only"


def main() -> int:
    args = parse_args()
    run_dir = ensure_run_dir(args.run_id, args.run_dir)
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "run_dir": str(run_dir), "mode": args.mode}, indent=2))
        return 0

    audit = load_h4_audit(args.h4_audit)
    relation_meta = symmetric_relation_meta(audit)
    allocation = load_allocation(args.allocation)
    b0_records = load_b0_records(args.graph)
    observed_reverses = stage2_observed_reverse_candidates(b0_records, relation_meta)
    eligible = eligible_symmetric_completion_edges(b0_records, relation_meta, observed_reverses)
    selected = select_completion_edges(eligible, relation_meta, args.mode)
    completed_records = list(b0_records) + list(selected)

    before_metrics = compute_h4_metrics(b0_records, allocation)
    after_metrics = compute_h4_metrics(completed_records, allocation)
    constraints = constraints_summary(after_metrics, allocation)
    by_relation = Counter(record.r for record in selected)

    write_csv_rows(run_dir / "h4_generated_edges.csv", generated_edge_rows(selected), GENERATED_EDGE_FIELDS)
    write_h4_graph_csv(run_dir / "h4_generated_graph.csv", completed_records)
    write_h4_graph_jsonl(run_dir / "h4_generated_graph.jsonl", completed_records)

    report = {
        "schema_version": f"{SCHEMA_VERSION}.symmetric-completion",
        **command_metadata(run_dir, "h4_generate_symmetric_completion"),
        "mode": args.mode,
        "input_paths": {
            "graph": args.graph,
            "allocation": args.allocation,
            "h4_audit": args.h4_audit,
        },
        "input_hashes": {
            "graph": sha256_file(args.graph),
            "allocation": sha256_file(args.allocation),
            "h4_audit": sha256_file(args.h4_audit),
        },
        "before_metrics": before_metrics,
        "after_metrics": after_metrics,
        "hard_constraints": constraints,
        "verified_symmetric_relation_count": len(relation_meta),
        "missing_reverse_observed_in_stage2_count": len(observed_reverses),
        "eligible_rule_completion_edges": len(eligible),
        "generated_synthetic_edges": len(selected),
        "generated_edges_by_relation": dict(sorted(by_relation.items())),
        "top_generated_edges_by_relation": top_counts(by_relation),
        "outputs": {
            "generated_edges_csv": str(run_dir / "h4_generated_edges.csv"),
            "generated_graph_csv": str(run_dir / "h4_generated_graph.csv"),
            "generated_graph_jsonl": str(run_dir / "h4_generated_graph.jsonl"),
            "completion_report": str(run_dir / "h4_completion_report.json"),
        },
        "claim_boundary": (
            "H4-A generated edges are labelled synthetic_rule_completion. They are rule-derived, "
            "not canonical observed triples and not verified Wikidata facts."
        ),
    }
    report["final_decision_state"] = decision_state(args.mode, before_metrics, after_metrics, constraints)
    write_json(run_dir / "h4_completion_report.json", report)
    print(
        json.dumps(
            {
                "status": "passed" if constraints["passed"] else "failed_constraints",
                "run_dir": str(run_dir),
                "mode": args.mode,
                "generated_synthetic_edges": len(selected),
                "symmetric_deficit_before": before_metrics["symmetric_deficit"],
                "symmetric_deficit_after": after_metrics["symmetric_deficit"],
                "weak_component_count": after_metrics["weak_component_count"],
                "allocated_relation_coverage_count": after_metrics["allocated_relation_coverage_count"],
                "final_decision_state": report["final_decision_state"],
            },
            indent=2,
        )
    )
    return 0 if constraints["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
