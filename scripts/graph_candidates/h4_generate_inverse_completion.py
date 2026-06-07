#!/usr/bin/env python3
"""Generate H4-B1 deficit-capped labelled inverse-pair completion outputs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Sequence

from h4_common import (
    DEFAULT_ALLOCATION,
    DEFAULT_B0_GRAPH,
    DEFAULT_EXPERIMENT_DIR,
    DEFAULT_H4_B_AUDIT,
    DEFAULT_STAGE2_SHARD_DIR,
    INVERSE_RULE_TYPE,
    SCHEMA_VERSION,
    SYNTHETIC_EDGE_SOURCE,
    command_metadata,
    compute_h4_metrics,
    constraints_summary,
    eligible_inverse_completion_edges,
    load_allocation,
    load_b0_records,
    load_json,
    now_run_id,
    select_deficit_capped_inverse_edges,
    sha256_file,
    stage2_observed_candidates_for_triples,
    top_counts,
    write_csv_rows,
    write_h4_graph_csv,
    write_h4_graph_jsonl,
    write_json,
)


GENERATED_EDGE_FIELDS = [
    "h",
    "r",
    "t",
    "edge_source",
    "rule_type",
    "source_relation",
    "target_inverse_relation",
    "orientation",
    "base_h",
    "base_r",
    "base_t",
    "generated_h",
    "generated_r",
    "generated_t",
    "verification_source",
    "confidence",
    "confidence_type",
    "confidence_source",
    "support",
    "observed_in_frozen_candidates",
    "evidence_status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir")
    parser.add_argument("--graph", default=str(DEFAULT_B0_GRAPH))
    parser.add_argument("--allocation", default=str(DEFAULT_ALLOCATION))
    parser.add_argument("--h4-b-audit", default=str(DEFAULT_H4_B_AUDIT))
    parser.add_argument("--stage2-shard-dir", default=str(DEFAULT_STAGE2_SHARD_DIR))
    parser.add_argument("--confidence-threshold", type=float, default=0.8)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def default_run_dir(run_id: str | None) -> Path:
    return DEFAULT_EXPERIMENT_DIR / "runs" / f"h4_B1_deficit_capped_{run_id or now_run_id()}"


def ensure_h4_b1_run_dir(run_id: str | None, run_dir: str | None, dry_run: bool) -> tuple[Path, str, str | None]:
    requested = Path(run_dir) if run_dir else default_run_dir(run_id)
    if dry_run:
        return requested, "dry_run_not_created", None
    try:
        requested.mkdir(parents=True, exist_ok=True)
        probe = requested / ".write_test"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
        return requested, "durable_repo_artifact", None
    except OSError as exc:
        fallback = Path("/tmp/H4_labelled_rule_completion/runs") / requested.name
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback, "temporary_not_durable", f"repo run directory unavailable: {exc}"


def h4_row(record) -> dict:
    from h4_common import h4_record_to_row

    return h4_record_to_row(record)


def generated_edge_rows(records) -> list[dict]:
    return [h4_row(record) for record in records]


def candidate_missing_inverse_triples(records, oriented_rules: Sequence[dict]) -> set[tuple[str, str, str]]:
    b0_triples = {record.triple for record in records}
    by_relation: dict[str, list] = {}
    for record in records:
        by_relation.setdefault(record.r, []).append(record)
    missing: set[tuple[str, str, str]] = set()
    for rule in oriented_rules:
        source = str(rule["source_relation"])
        target = str(rule["target_inverse_relation"])
        for base in by_relation.get(source, []):
            generated = (base.t, target, base.h)
            if generated not in b0_triples:
                missing.add(generated)
    return missing


def decision_state(before: dict, after: dict, constraints: dict, generated: int) -> str:
    if not constraints["passed"]:
        return "failed_constraints"
    if generated <= 0:
        return "diagnostic_only"
    if (
        after["total_deficit"] < before["total_deficit"]
        and after["inverse_deficit"] < before["inverse_deficit"]
        and after["triples_per_entity"] > before["triples_per_entity"]
        and after["total_surplus"] <= before["total_surplus"] + 1e-9
    ):
        return "synthetic_augmented_candidate_for_review"
    return "diagnostic_only"


def main() -> int:
    args = parse_args()
    audit = load_json(args.h4_b_audit)
    if audit.get("schema_version") != "h4-b-inverse-completion-opportunity-audit-v1":
        raise ValueError(f"unexpected H4-B audit schema: {audit.get('schema_version')}")
    if audit.get("h4_b_status") != "opportunity_audit_only":
        raise ValueError("H4-B1 expects an opportunity-audit-only source report")

    allocation = load_allocation(args.allocation)
    b0_records = load_b0_records(args.graph)
    oriented_rules = audit.get("oriented_rules", [])
    missing_inverse = candidate_missing_inverse_triples(b0_records, oriented_rules)
    observed_inverse = stage2_observed_candidates_for_triples(missing_inverse, args.stage2_shard_dir)
    eligible, eligibility_stats = eligible_inverse_completion_edges(
        b0_records,
        oriented_rules,
        observed_inverse_candidates=observed_inverse,
        confidence_threshold=args.confidence_threshold,
    )
    selected, selection_stats = select_deficit_capped_inverse_edges(eligible)
    run_dir, run_location_status, fallback_reason = ensure_h4_b1_run_dir(args.run_id, args.run_dir, args.dry_run)

    before_metrics = compute_h4_metrics(b0_records, allocation)
    completed_records = list(b0_records) + list(selected)
    after_metrics = compute_h4_metrics(completed_records, allocation)
    constraints = constraints_summary(after_metrics, allocation)

    by_relation = Counter(record.r for record in selected)
    by_orientation = Counter(str((record.provenance or {}).get("orientation")) for record in selected)
    by_confidence_type = Counter(str((record.provenance or {}).get("confidence_type")) for record in selected)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "run_dir": str(run_dir),
                    "run_location_status": run_location_status,
                    "eligible_before_deficit_cap": len(eligible),
                    "generated_synthetic_edges": len(selected),
                    "already_frozen_observed_skipped": eligibility_stats.get("already_frozen_observed", 0),
                    "below_confidence_threshold_skipped": eligibility_stats.get("below_confidence_threshold", 0),
                },
                indent=2,
            )
        )
        return 0

    write_csv_rows(run_dir / "h4_b1_generated_edges.csv", generated_edge_rows(selected), GENERATED_EDGE_FIELDS)
    write_h4_graph_csv(run_dir / "h4_b1_generated_graph.csv", completed_records)
    write_h4_graph_jsonl(run_dir / "h4_b1_generated_graph.jsonl", completed_records)

    report = {
        "schema_version": f"{SCHEMA_VERSION}.inverse-completion-b1",
        **command_metadata(run_dir, "h4_generate_inverse_completion"),
        "mode": "H4-B1_deficit_capped_inverse_completion",
        "run_location_status": run_location_status,
        "fallback_reason": fallback_reason,
        "input_paths": {
            "graph": args.graph,
            "allocation": args.allocation,
            "h4_b_audit": args.h4_b_audit,
            "stage2_shard_dir": args.stage2_shard_dir,
        },
        "input_hashes": {
            "graph": sha256_file(args.graph),
            "allocation": sha256_file(args.allocation),
            "h4_b_audit": sha256_file(args.h4_b_audit),
        },
        "confidence_threshold": args.confidence_threshold,
        "confidence_policy": "pair_level_if_orientation_specific_missing",
        "before_metrics": before_metrics,
        "after_metrics": after_metrics,
        "hard_constraints": constraints,
        "verified_inverse_pair_count": audit.get("totals", {}).get("verified_inverse_pair_count"),
        "oriented_rule_count": audit.get("totals", {}).get("oriented_rule_count"),
        "missing_inverse_opportunities_from_audit": audit.get("totals", {}).get("missing_inverse_opportunities"),
        "missing_inverse_triples_recomputed": len(missing_inverse),
        "skipped_already_frozen_observed": eligibility_stats.get("already_frozen_observed", 0),
        "skipped_below_confidence_threshold": eligibility_stats.get("below_confidence_threshold", 0),
        "skipped_target_relation_overfilled": eligibility_stats.get("target_relation_overfilled", 0),
        "skipped_target_relation_no_deficit_room": eligibility_stats.get("target_relation_no_deficit_room", 0),
        "skipped_target_relation_not_allocated": eligibility_stats.get("target_relation_not_allocated", 0),
        "skipped_by_deficit_cap_after_ordering": selection_stats.get("skipped_by_deficit_cap_after_ordering", 0),
        "eligible_before_deficit_cap": len(eligible),
        "generated_synthetic_edges": len(selected),
        "generated_edges_by_relation": dict(sorted(by_relation.items())),
        "generated_edges_by_orientation": dict(sorted(by_orientation.items())),
        "generated_edges_by_confidence_type": dict(sorted(by_confidence_type.items())),
        "top_generated_edges_by_relation": top_counts(by_relation),
        "eligibility_stats": eligibility_stats,
        "selection_stats": selection_stats,
        "all_generated_edges_labelled_synthetic_rule_completion": all(
            record.source == SYNTHETIC_EDGE_SOURCE
            and (record.provenance or {}).get("rule_type") == INVERSE_RULE_TYPE
            for record in selected
        ),
        "observed_in_frozen_candidates_for_generated_edges": 0,
        "outputs": {
            "generated_edges_csv": str(run_dir / "h4_b1_generated_edges.csv"),
            "generated_graph_csv": str(run_dir / "h4_b1_generated_graph.csv"),
            "generated_graph_jsonl": str(run_dir / "h4_b1_generated_graph.jsonl"),
            "completion_report": str(run_dir / "h4_b1_completion_report.json"),
        },
        "claim_boundary": (
            "H4-B1 generated edges are labelled synthetic_rule_completion inverse-pair edges. "
            "They are rule-derived, not canonical observed triples, not verified Wikidata facts, "
            "and not KGE evidence."
        ),
    }
    report["final_decision_state"] = decision_state(before_metrics, after_metrics, constraints, len(selected))
    write_json(run_dir / "h4_b1_completion_report.json", report)
    print(
        json.dumps(
            {
                "status": "passed" if constraints["passed"] else "failed_constraints",
                "run_dir": str(run_dir),
                "run_location_status": run_location_status,
                "generated_synthetic_edges": len(selected),
                "skipped_already_frozen_observed": report["skipped_already_frozen_observed"],
                "skipped_below_confidence_threshold": report["skipped_below_confidence_threshold"],
                "skipped_target_relation_overfilled_or_no_deficit_room": (
                    report["skipped_target_relation_overfilled"]
                    + report["skipped_target_relation_no_deficit_room"]
                    + report["skipped_by_deficit_cap_after_ordering"]
                ),
                "total_surplus_before": before_metrics["total_surplus"],
                "total_surplus_after": after_metrics["total_surplus"],
                "total_deficit_before": before_metrics["total_deficit"],
                "total_deficit_after": after_metrics["total_deficit"],
                "inverse_deficit_before": before_metrics["inverse_deficit"],
                "inverse_deficit_after": after_metrics["inverse_deficit"],
                "weak_component_count": after_metrics["weak_component_count"],
                "allocated_relation_coverage_count": after_metrics["allocated_relation_coverage_count"],
                "duplicate_triple_count": after_metrics["duplicate_triple_count"],
                "final_decision_state": report["final_decision_state"],
            },
            indent=2,
        )
    )
    return 0 if constraints["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
