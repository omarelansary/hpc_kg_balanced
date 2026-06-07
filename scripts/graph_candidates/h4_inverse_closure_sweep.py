#!/usr/bin/env python3
"""Run the bounded H4-B inverse-completion closure sweep."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

try:  # Imported by tests as scripts.graph_candidates.h4_inverse_closure_sweep.
    from scripts.graph_candidates.h4_common import (  # type: ignore
        DEFAULT_ALLOCATION,
        DEFAULT_B0_GRAPH,
        DEFAULT_EXPERIMENT_DIR,
        DEFAULT_H4_B_AUDIT,
        DEFAULT_STAGE2_SHARD_DIR,
        INVERSE_RULE_TYPE,
        SCHEMA_VERSION,
        SYNTHETIC_EDGE_SOURCE,
        TripleRecord,
        apply_h4_safe_deletions,
        command_metadata,
        compute_h4_metrics,
        constraints_summary,
        h4_record_to_row,
        load_allocation,
        load_b0_records,
        load_json,
        now_run_id,
        sha256_file,
        stage2_observed_candidates_for_triples,
        top_counts,
        write_csv_rows,
        write_h4_graph_csv,
        write_h4_graph_jsonl,
        write_json,
    )
except ModuleNotFoundError:  # Executed directly from scripts/graph_candidates.
    from h4_common import (  # type: ignore
        DEFAULT_ALLOCATION,
        DEFAULT_B0_GRAPH,
        DEFAULT_EXPERIMENT_DIR,
        DEFAULT_H4_B_AUDIT,
        DEFAULT_STAGE2_SHARD_DIR,
        INVERSE_RULE_TYPE,
        SCHEMA_VERSION,
        SYNTHETIC_EDGE_SOURCE,
        TripleRecord,
        apply_h4_safe_deletions,
        command_metadata,
        compute_h4_metrics,
        constraints_summary,
        h4_record_to_row,
        load_allocation,
        load_b0_records,
        load_json,
        now_run_id,
        sha256_file,
        stage2_observed_candidates_for_triples,
        top_counts,
        write_csv_rows,
        write_h4_graph_csv,
        write_h4_graph_jsonl,
        write_json,
    )


GLOBAL_OPTIMUM_LIMITATION = (
    "This H4-B closure sweep is not a global optimum proof. It is a predeclared "
    "bounded sweep over inverse-completion modes; exact optimization over all "
    "additions and deletions was not performed on the real graph."
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
    "risk_flags",
]

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir")
    parser.add_argument("--graph", default=str(DEFAULT_B0_GRAPH))
    parser.add_argument("--allocation", default=str(DEFAULT_ALLOCATION))
    parser.add_argument("--h4-b-audit", default=str(DEFAULT_H4_B_AUDIT))
    parser.add_argument("--stage2-shard-dir", default=str(DEFAULT_STAGE2_SHARD_DIR))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def default_sweep_dir(run_id: str | None) -> Path:
    return DEFAULT_EXPERIMENT_DIR / "runs" / f"h4_B_inverse_closure_sweep_{run_id or now_run_id()}"


def ensure_sweep_dir(run_id: str | None, run_dir: str | None, dry_run: bool) -> tuple[Path, str, str | None]:
    requested = Path(run_dir) if run_dir else default_sweep_dir(run_id)
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


def confidence_tier(confidence: Any) -> str:
    if confidence is None:
        return "missing"
    value = float(confidence)
    if value >= 0.9:
        return "gte_0_9"
    if value >= 0.8:
        return "gte_0_8_lt_0_9"
    if value >= 0.7:
        return "gte_0_7_lt_0_8"
    return "lt_0_7"


def candidate_missing_inverse_triples(records: Sequence[TripleRecord], oriented_rules: Sequence[dict[str, Any]]) -> set[tuple[str, str, str]]:
    b0_triples = {record.triple for record in records}
    by_relation: dict[str, list[TripleRecord]] = defaultdict(list)
    for record in records:
        by_relation[record.r].append(record)
    missing: set[tuple[str, str, str]] = set()
    for rule in oriented_rules:
        source = str(rule["source_relation"])
        target = str(rule["target_inverse_relation"])
        for base in by_relation.get(source, []):
            generated = (base.t, target, base.h)
            if generated not in b0_triples:
                missing.add(generated)
    return missing


def synthetic_inverse_record(base: TripleRecord, rule: dict[str, Any]) -> TripleRecord:
    target = str(rule["target_inverse_relation"])
    risk_flags = list(rule.get("risk_flags") or [])
    provenance = {
        "rule_type": INVERSE_RULE_TYPE,
        "source_relation": base.r,
        "target_inverse_relation": target,
        "orientation": str(rule.get("orientation") or f"{base.r}_to_{target}"),
        "base_h": base.h,
        "base_r": base.r,
        "base_t": base.t,
        "generated_h": base.t,
        "generated_r": target,
        "generated_t": base.h,
        "verification_source": "artifacts/final_graph/selected_final_graph/rebuild/h4_b_inverse_completion_opportunity_audit.json",
        "confidence": rule.get("confidence"),
        "confidence_type": "pair_level_if_orientation_specific_missing",
        "confidence_source": rule.get("confidence_source"),
        "support": rule.get("support"),
        "observed_in_frozen_candidates": False,
        "evidence_status": "rule_derived_not_observed",
        "target_deficit": rule.get("target_deficit"),
        "target_surplus": rule.get("target_surplus"),
        "risk_flags": "|".join(risk_flags),
    }
    return TripleRecord(base.t, target, base.h, SYNTHETIC_EDGE_SOURCE, provenance)


def build_inverse_edges(
    b0_records: Sequence[TripleRecord],
    oriented_rules: Sequence[dict[str, Any]],
    observed_inverse_candidates: set[tuple[str, str, str]],
    *,
    confidence_threshold: float | None,
    require_underfilled: bool,
    allow_overfilled_targets: bool,
    deficit_capped: bool,
) -> tuple[list[TripleRecord], dict[str, int]]:
    b0_triples = {record.triple for record in b0_records}
    by_relation: dict[str, list[TripleRecord]] = defaultdict(list)
    for record in b0_records:
        by_relation[record.r].append(record)

    stats: Counter[str] = Counter()
    candidates: list[TripleRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for rule in oriented_rules:
        source = str(rule["source_relation"])
        target = str(rule["target_inverse_relation"])
        confidence = rule.get("confidence")
        target_eta = float(rule.get("target_eta") or 0.0)
        target_deficit = float(rule.get("target_deficit") or 0.0)
        target_surplus = float(rule.get("target_surplus") or 0.0)
        for base in sorted(by_relation.get(source, []), key=lambda record: (record.h, record.r, record.t)):
            generated = (base.t, target, base.h)
            if generated in b0_triples:
                stats["already_present_in_b0"] += 1
                continue
            if generated in observed_inverse_candidates:
                stats["already_frozen_observed"] += 1
                continue
            if target_eta <= 0:
                stats["target_relation_not_allocated"] += 1
                continue
            if confidence_threshold is not None and (confidence is None or float(confidence) < confidence_threshold):
                stats["below_confidence_threshold"] += 1
                continue
            if target_surplus > 0 and not allow_overfilled_targets:
                stats["target_relation_overfilled"] += 1
                continue
            if require_underfilled and target_deficit <= 0:
                stats["target_relation_no_deficit_room"] += 1
                continue
            if generated in seen:
                stats["duplicate_generated_candidate"] += 1
                continue
            seen.add(generated)
            candidates.append(synthetic_inverse_record(base, rule))
            if target_surplus > 0:
                stats["generated_targeting_overfilled_relation"] += 1
            if "composition_heavy_relation_involved" in set(rule.get("risk_flags") or []):
                stats["generated_composition_heavy"] += 1
            stats["eligible_before_deficit_cap"] += 1

    if not deficit_capped:
        return candidates, dict(stats)

    selected: list[TripleRecord] = []
    by_target: Counter[str] = Counter()
    for record in candidates:
        cap = int(float((record.provenance or {}).get("target_deficit") or 0.0))
        if cap <= 0:
            stats["target_relation_no_deficit_room"] += 1
            continue
        if by_target[record.r] >= cap:
            stats["skipped_by_deficit_cap_after_ordering"] += 1
            continue
        selected.append(record)
        by_target[record.r] += 1
        stats["selected"] += 1
    return selected, dict(stats)


def generated_rows(records: Sequence[TripleRecord]) -> list[dict[str, Any]]:
    return [h4_record_to_row(record) for record in records]


def generated_summary(records: Sequence[TripleRecord]) -> dict[str, Any]:
    by_relation = Counter(record.r for record in records)
    by_orientation = Counter(str((record.provenance or {}).get("orientation")) for record in records)
    by_tier = Counter(confidence_tier((record.provenance or {}).get("confidence")) for record in records)
    composition_heavy = sum(
        1
        for record in records
        if "composition_heavy_relation_involved" in str((record.provenance or {}).get("risk_flags", "")).split("|")
    )
    overfilled = sum(1 for record in records if float((record.provenance or {}).get("target_surplus") or 0.0) > 0)
    return {
        "generated_edges_by_target_relation": dict(sorted(by_relation.items())),
        "generated_edges_by_orientation": dict(sorted(by_orientation.items())),
        "generated_edges_by_confidence_tier": dict(sorted(by_tier.items())),
        "generated_edges_involving_composition_heavy_relations": composition_heavy,
        "generated_edges_targeting_overfilled_relations": overfilled,
        "top_generated_edges_by_target_relation": top_counts(by_relation),
    }


def classify_decision(
    *,
    mode_role: str,
    before_metrics: dict[str, Any],
    after_metrics: dict[str, Any],
    constraints: dict[str, Any],
    generated_edges: int,
    generated_observed_overlap: int,
    deleted_base_support_triples: int = 0,
) -> str:
    if not constraints["passed"] or generated_observed_overlap or deleted_base_support_triples:
        return "failed_constraints"
    if mode_role == "stress_test":
        return "stress_test_only"
    if generated_edges <= 0:
        return "diagnostic_only"
    if (
        after_metrics["total_deficit"] < before_metrics["total_deficit"]
        and after_metrics["triples_per_entity"] > before_metrics["triples_per_entity"]
        and after_metrics["total_surplus"] <= before_metrics["total_surplus"] + 1e-9
    ):
        return "synthetic_augmented_candidate_for_review"
    return "diagnostic_only"


def write_generation_mode(
    run_dir: Path,
    mode_id: str,
    mode_role: str,
    b0_records: Sequence[TripleRecord],
    selected: Sequence[TripleRecord],
    allocation: dict[str, Any],
    stats: dict[str, int],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    mode_dir = run_dir / mode_id
    mode_dir.mkdir(parents=True, exist_ok=True)
    completed_records = list(b0_records) + list(selected)
    before_metrics = compute_h4_metrics(b0_records, allocation)
    after_metrics = compute_h4_metrics(completed_records, allocation)
    constraints = constraints_summary(after_metrics, allocation)

    write_csv_rows(mode_dir / "h4_b_generated_edges.csv", generated_rows(selected), GENERATED_EDGE_FIELDS)
    write_h4_graph_csv(mode_dir / "h4_b_generated_graph.csv", completed_records)
    write_h4_graph_jsonl(mode_dir / "h4_b_generated_graph.jsonl", completed_records)

    report = {
        "schema_version": f"{SCHEMA_VERSION}.inverse-closure-sweep-mode",
        "mode_id": mode_id,
        "mode_role": mode_role,
        "mode_parameters": metadata,
        "before_metrics": before_metrics,
        "after_metrics": after_metrics,
        "hard_constraints": constraints,
        "generated_synthetic_edges": len(selected),
        "skip_and_selection_stats": stats,
        **generated_summary(selected),
        "generated_edges_excluded_because_already_frozen_observed": stats.get("already_frozen_observed", 0),
        "outputs": {
            "generated_edges_csv": str(mode_dir / "h4_b_generated_edges.csv"),
            "generated_graph_csv": str(mode_dir / "h4_b_generated_graph.csv"),
            "generated_graph_jsonl": str(mode_dir / "h4_b_generated_graph.jsonl"),
            "mode_report": str(mode_dir / "h4_b_mode_report.json"),
        },
    }
    report["decision_state"] = classify_decision(
        mode_role=mode_role,
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        constraints=constraints,
        generated_edges=len(selected),
        generated_observed_overlap=0,
    )
    write_json(mode_dir / "h4_b_mode_report.json", report)
    return report


def write_safe_delete_mode(
    run_dir: Path,
    mode_id: str,
    b0_records: Sequence[TripleRecord],
    completed_records: Sequence[TripleRecord],
    allocation: dict[str, Any],
    source_report: dict[str, Any],
) -> dict[str, Any]:
    mode_dir = run_dir / mode_id
    mode_dir.mkdir(parents=True, exist_ok=True)
    before_metrics = compute_h4_metrics(b0_records, allocation)
    after_completion_metrics = compute_h4_metrics(completed_records, allocation)
    final_records, accepted, rejections, deletion_stats, deletion_candidates = apply_h4_safe_deletions(
        b0_records,
        completed_records,
        allocation,
        preserve_original_entities=True,
        allow_deficit_increase=False,
        allow_delete_base_triples_for_retained_synthetic=False,
    )
    after_deletion_metrics = compute_h4_metrics(final_records, allocation)
    constraints = constraints_summary(after_deletion_metrics, allocation)

    write_csv_rows(mode_dir / "h4_b_safe_deletions.csv", accepted, DELETION_FIELDS)
    write_h4_graph_csv(mode_dir / "h4_b_add_delete_graph.csv", final_records)
    write_h4_graph_jsonl(mode_dir / "h4_b_add_delete_graph.jsonl", final_records)

    report = {
        "schema_version": f"{SCHEMA_VERSION}.inverse-closure-sweep-safe-delete-mode",
        "mode_id": mode_id,
        "mode_role": "stress_test",
        "source_mode_id": source_report["mode_id"],
        "before_metrics": before_metrics,
        "after_completion_metrics": after_completion_metrics,
        "after_deletion_metrics": after_deletion_metrics,
        "hard_constraints": constraints,
        "generated_synthetic_edges": source_report["generated_synthetic_edges"],
        "safe_deletion_candidate_count": len(deletion_candidates),
        "accepted_deletions": len(accepted),
        "deletions_rejected_by_reason": dict(sorted(rejections.items())),
        "deleted_synthetic_edges_count": deletion_stats.get("synthetic_edges_deleted", 0),
        "deleted_base_support_triples_count": deletion_stats.get("deleted_base_triples_for_retained_synthetic_edges_count", 0),
        "rejected_base_support_deletion_count": deletion_stats.get("rejected_deletes_base_triple_for_retained_synthetic_edge_count", 0),
        "accepted_safe_after_not_before_count": deletion_stats.get("accepted_safe_after_not_before_count", 0),
        "preserve_original_entities": deletion_stats.get("preserve_original_entities"),
        "dropped_original_entity_count": deletion_stats.get("dropped_original_entity_count"),
        "composition_surplus_delta_after_deletion": (
            after_deletion_metrics["composition_surplus"] - after_completion_metrics["composition_surplus"]
        ),
        "density_delta_after_deletion": (
            after_deletion_metrics["triples_per_entity"] - after_completion_metrics["triples_per_entity"]
        ),
        "total_surplus_delta_after_deletion": after_deletion_metrics["total_surplus"] - after_completion_metrics["total_surplus"],
        "total_deficit_delta_after_deletion": after_deletion_metrics["total_deficit"] - after_completion_metrics["total_deficit"],
        "outputs": {
            "safe_deletions_csv": str(mode_dir / "h4_b_safe_deletions.csv"),
            "add_delete_graph_csv": str(mode_dir / "h4_b_add_delete_graph.csv"),
            "add_delete_graph_jsonl": str(mode_dir / "h4_b_add_delete_graph.jsonl"),
            "mode_report": str(mode_dir / "h4_b_safe_delete_mode_report.json"),
        },
    }
    report["decision_state"] = classify_decision(
        mode_role="stress_test",
        before_metrics=before_metrics,
        after_metrics=after_deletion_metrics,
        constraints=constraints,
        generated_edges=source_report["generated_synthetic_edges"],
        generated_observed_overlap=0,
        deleted_base_support_triples=report["deleted_base_support_triples_count"],
    )
    write_json(mode_dir / "h4_b_safe_delete_mode_report.json", report)
    return report


def metric_row(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("after_deletion_metrics") or report.get("after_metrics")
    return {
        "mode_id": report["mode_id"],
        "decision_state": report["decision_state"],
        "triples": metrics["total_triples"],
        "entities": metrics["total_entities"],
        "triples_per_entity": metrics["triples_per_entity"],
        "average_participation": metrics["average_participation"],
        "weak_component_count": metrics["weak_component_count"],
        "largest_component_ratio": metrics["largest_component_ratio"],
        "duplicate_triple_count": metrics["duplicate_triple_count"],
        "coverage": metrics["allocated_relation_coverage_count"],
        "total_surplus": metrics["total_surplus"],
        "total_deficit": metrics["total_deficit"],
        "inverse_deficit": metrics["inverse_deficit"],
        "symmetric_deficit": metrics["symmetric_deficit"],
        "composition_surplus": metrics["composition_surplus"],
        "composition_share": metrics["composition_share"],
        "synthetic_edge_count": metrics["synthetic_edge_count"],
        "synthetic_edge_ratio": metrics["synthetic_edge_ratio"],
        "bridge_count": metrics["bridge_count"],
        "articulation_point_count": metrics["articulation_point_count"],
        "accepted_deletions": report.get("accepted_deletions", 0),
    }


def choose_best_observed(reports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    candidates = [report for report in reports if report.get("decision_state") == "synthetic_augmented_candidate_for_review"]
    if not candidates:
        return {"mode_id": None, "reason": "no mode qualified as synthetic_augmented_candidate_for_review"}
    ranked = sorted(
        candidates,
        key=lambda report: (
            (report.get("after_metrics") or report.get("after_deletion_metrics"))["total_deficit"],
            (report.get("after_metrics") or report.get("after_deletion_metrics"))["total_surplus"],
            (report.get("after_metrics") or report.get("after_deletion_metrics"))["synthetic_edge_count"],
        ),
    )
    best = ranked[0]
    return {
        "mode_id": best["mode_id"],
        "decision_state": best["decision_state"],
        "reason": "lowest total deficit among modes that qualified for review, then lower surplus and lower synthetic mass",
    }


def run_sweep(args: argparse.Namespace) -> dict[str, Any]:
    audit = load_json(args.h4_b_audit)
    if audit.get("schema_version") != "h4-b-inverse-completion-opportunity-audit-v1":
        raise ValueError(f"unexpected H4-B audit schema: {audit.get('schema_version')}")
    allocation = load_allocation(args.allocation)
    b0_records = load_b0_records(args.graph)
    oriented_rules = audit.get("oriented_rules", [])
    missing_inverse = candidate_missing_inverse_triples(b0_records, oriented_rules)
    observed_inverse = stage2_observed_candidates_for_triples(missing_inverse, args.stage2_shard_dir)
    run_dir, run_location_status, fallback_reason = ensure_sweep_dir(args.run_id, args.run_dir, args.dry_run)

    mode_specs = [
        {
            "mode_id": "H4-B1_strict_conservative",
            "mode_role": "candidate",
            "confidence_threshold": 0.8,
            "require_underfilled": True,
            "allow_overfilled_targets": False,
            "deficit_capped": True,
        },
        {
            "mode_id": "H4-B2_add_all_stress",
            "mode_role": "stress_test",
            "confidence_threshold": None,
            "require_underfilled": False,
            "allow_overfilled_targets": True,
            "deficit_capped": False,
        },
        {
            "mode_id": "H4-B4_confidence_gte_0_9_deficit_capped",
            "mode_role": "candidate",
            "confidence_threshold": 0.9,
            "require_underfilled": True,
            "allow_overfilled_targets": False,
            "deficit_capped": True,
        },
        {
            "mode_id": "H4-B4_confidence_gte_0_8_deficit_capped",
            "mode_role": "candidate",
            "confidence_threshold": 0.8,
            "require_underfilled": True,
            "allow_overfilled_targets": False,
            "deficit_capped": True,
        },
        {
            "mode_id": "H4-B4_confidence_gte_0_7_deficit_capped",
            "mode_role": "candidate",
            "confidence_threshold": 0.7,
            "require_underfilled": True,
            "allow_overfilled_targets": False,
            "deficit_capped": True,
        },
        {
            "mode_id": "H4-B4_all_verified_deficit_capped",
            "mode_role": "candidate",
            "confidence_threshold": None,
            "require_underfilled": True,
            "allow_overfilled_targets": False,
            "deficit_capped": True,
        },
    ]

    if args.dry_run:
        return {
            "status": "dry_run",
            "run_dir": str(run_dir),
            "run_location_status": run_location_status,
            "mode_ids": [spec["mode_id"] for spec in mode_specs] + ["H4-B3_add_all_strict_base_support_safe_delete"],
            "missing_inverse_triples": len(missing_inverse),
            "observed_inverse_candidates": len(observed_inverse),
        }

    mode_reports: list[dict[str, Any]] = []
    generated_by_mode: dict[str, list[TripleRecord]] = {}
    for spec in mode_specs:
        selected, stats = build_inverse_edges(b0_records, oriented_rules, observed_inverse, **{k: spec[k] for k in (
            "confidence_threshold", "require_underfilled", "allow_overfilled_targets", "deficit_capped"
        )})
        generated_by_mode[spec["mode_id"]] = selected
        report = write_generation_mode(run_dir, spec["mode_id"], spec["mode_role"], b0_records, selected, allocation, stats, spec)
        mode_reports.append(report)

    b2_records = list(b0_records) + generated_by_mode["H4-B2_add_all_stress"]
    b3_report = write_safe_delete_mode(
        run_dir,
        "H4-B3_add_all_strict_base_support_safe_delete",
        b0_records,
        b2_records,
        allocation,
        next(report for report in mode_reports if report["mode_id"] == "H4-B2_add_all_stress"),
    )
    mode_reports.append(b3_report)

    b1 = next(report for report in mode_reports if report["mode_id"] == "H4-B1_strict_conservative")
    prior_b1_path = Path("artifacts/final_graph/selected_final_graph/rebuild/h4_b1_inverse_completion_result.json")
    b1_reproduction = {"status": "prior_result_missing"}
    if prior_b1_path.exists():
        prior = load_json(prior_b1_path)
        b1_metrics = b1["after_metrics"]
        b1_reproduction = {
            "status": "matched" if (
                int(prior["generated_synthetic_inverse_edges"]) == int(b1["generated_synthetic_edges"])
                and float(prior["after_h4_b1_metrics"]["total_surplus"]) == float(b1_metrics["total_surplus"])
                and float(prior["after_h4_b1_metrics"]["total_deficit"]) == float(b1_metrics["total_deficit"])
                and float(prior["after_h4_b1_metrics"]["inverse_deficit"]) == float(b1_metrics["inverse_deficit"])
            ) else "mismatch",
            "prior_generated_edges": prior.get("generated_synthetic_inverse_edges"),
            "sweep_generated_edges": b1.get("generated_synthetic_edges"),
            "prior_total_surplus": prior.get("after_h4_b1_metrics", {}).get("total_surplus"),
            "sweep_total_surplus": b1_metrics["total_surplus"],
            "prior_total_deficit": prior.get("after_h4_b1_metrics", {}).get("total_deficit"),
            "sweep_total_deficit": b1_metrics["total_deficit"],
            "prior_inverse_deficit": prior.get("after_h4_b1_metrics", {}).get("inverse_deficit"),
            "sweep_inverse_deficit": b1_metrics["inverse_deficit"],
        }

    summary = {
        "schema_version": "h4-b-inverse-completion-closure-sweep-v1",
        **command_metadata(run_dir, "h4_inverse_closure_sweep"),
        "run_dir": str(run_dir),
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
        "global_optimum_limitation": GLOBAL_OPTIMUM_LIMITATION,
        "missing_inverse_triples_recomputed": len(missing_inverse),
        "observed_inverse_candidates_excluded": len(observed_inverse),
        "b1_reproduction": b1_reproduction,
        "mode_results": mode_reports,
        "metrics_table": [metric_row(report) for report in mode_reports],
        "best_observed_under_tested_h4_b_sweep": choose_best_observed(mode_reports),
        "candidate_for_review_modes": [
            report["mode_id"] for report in mode_reports if report.get("decision_state") == "synthetic_augmented_candidate_for_review"
        ],
        "stress_test_modes": [report["mode_id"] for report in mode_reports if report.get("decision_state") == "stress_test_only"],
        "claim_boundary": (
            "All H4-B generated edges are labelled synthetic_rule_completion inverse-pair edges. "
            "They are rule-derived, not canonical observed triples, not verified Wikidata facts, and not KGE evidence."
        ),
    }
    write_json(run_dir / "h4_b_inverse_completion_closure_sweep_report.json", summary)
    return summary


def main() -> int:
    args = parse_args()
    report = run_sweep(args)
    print(
        json.dumps(
            {
                "status": report.get("status", "passed"),
                "run_dir": report.get("run_dir"),
                "run_location_status": report.get("run_location_status"),
                "b1_reproduction": report.get("b1_reproduction"),
                "best_observed": report.get("best_observed_under_tested_h4_b_sweep"),
                "candidate_for_review_modes": report.get("candidate_for_review_modes"),
                "stress_test_modes": report.get("stress_test_modes"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
