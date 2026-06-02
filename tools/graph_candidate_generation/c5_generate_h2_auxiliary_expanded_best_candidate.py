#!/usr/bin/env python3
"""Generate the best C5-H2 expanded auxiliary-support candidate package.

This script packages the best passing strategy from the expanded C5-H2
auxiliary saturation audit. It uses only frozen local evidence and writes the
experimental candidate package under the C5 experiment output directory.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import (  # noqa: E402
    compare_relation_counts_to_allocation,
    load_allocation,
)
from src.kg_pipeline.evaluation.candidate_report import sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.connectivity_metrics import summarize_connectivity  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, load_graph_triples, summarize_graph_triples  # noqa: E402
from src.kg_pipeline.evaluation.pattern_balance import compare_pattern_totals  # noqa: E402
from tools.graph_candidate_generation import c5_audit_h2_auxiliary_expanded_saturation as audit  # noqa: E402

EXPERIMENT_DIR = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix")
OUTPUT_DIR = EXPERIMENT_DIR / "outputs" / "auxiliary_expanded_best_candidate"
DEFAULT_AUDIT_REPORT = EXPERIMENT_DIR / "reports" / "auxiliary_expanded_saturation" / "expanded_auxiliary_saturation_report.json"
DEFAULT_CONFIG = EXPERIMENT_DIR / "configs" / "config.template.json"
DEFAULT_POLICY = EXPERIMENT_DIR / "configs" / "h2_generator_policy.template.json"
CANDIDATE_ID = "C5_H2_expanded_auxiliary_best_unregistered"
PARENT_CANDIDATE_ID = "B0"
SELECTED_EDGE_CLASS = "auxiliary_unallocated_observed"
RETAINED_EDGE_CLASS = "canonical_observed_retained"
REMOVED_EDGE_CLASS = "canonical_observed_removed"
GENERATED_BY = "tools/graph_candidate_generation/c5_generate_h2_auxiliary_expanded_best_candidate.py"
AUDIT_FLOAT_TOLERANCE = 1e-9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--strategy", default=None)
    parser.add_argument(
        "--allow-audit-mismatch",
        action="store_true",
        help="Write the package even if reconstructed metrics differ from the expanded audit report row.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def output_paths() -> dict[str, Path]:
    return {
        "readme": OUTPUT_DIR / "README.md",
        "full_graph": OUTPUT_DIR / "full_graph.jsonl",
        "full_graph_provenance": OUTPUT_DIR / "full_graph.provenance.jsonl",
        "canonical_only_graph": OUTPUT_DIR / "canonical_only_graph.jsonl",
        "canonical_only_graph_provenance": OUTPUT_DIR / "canonical_only_graph.provenance.jsonl",
        "auxiliary_edges": OUTPUT_DIR / "auxiliary_edges.jsonl",
        "auxiliary_edges_provenance": OUTPUT_DIR / "auxiliary_edges.provenance.jsonl",
        "removed_canonical_edges": OUTPUT_DIR / "removed_canonical_edges.jsonl",
        "removed_canonical_edges_provenance": OUTPUT_DIR / "removed_canonical_edges.provenance.jsonl",
        "edge_provenance": OUTPUT_DIR / "edge_provenance.jsonl",
        "candidate_manifest": OUTPUT_DIR / "candidate_manifest.json",
        "evaluation_report": OUTPUT_DIR / "evaluation_report.json",
        "evaluation_summary": OUTPUT_DIR / "evaluation_summary.md",
    }


def refuse_overwrite(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite C5-H2 expanded candidate package without --force: {names}")


def triple_dict(triple: Triple) -> dict[str, str]:
    h, r, t = triple
    return {"h": h, "r": r, "t": t}


def triple_from_edge(edge: dict[str, str]) -> Triple:
    return edge["h"], edge["r"], edge["t"]


def json_line(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json_line(row))


def bare_edge_row(row: dict[str, Any]) -> dict[str, str]:
    return {"h": row["h"], "r": row["r"], "t": row["t"]}


def relation_quota_row(metrics: dict[str, Any], relation: str) -> dict[str, Any] | None:
    for row in metrics["allocation_metrics"]["per_relation_expected_observed"]:
        if row["relation"] == relation:
            return row
    return None


def relation_surplus(metrics: dict[str, Any], relation: str) -> float:
    row = relation_quota_row(metrics, relation)
    return float(row["surplus"]) if row else 0.0


def relation_deficit(metrics: dict[str, Any], relation: str) -> float:
    row = relation_quota_row(metrics, relation)
    return float(row["deficit"]) if row else 0.0


def relation_observed(metrics: dict[str, Any], relation: str) -> int:
    row = relation_quota_row(metrics, relation)
    return int(row["observed_count"]) if row else 0


def composition_surplus(metrics: dict[str, Any]) -> float:
    for row in metrics["allocation_metrics"]["pattern_level_expected_observed"]:
        if row["pattern"] == "composition":
            return float(row["surplus"])
    return 0.0


def evaluate_triples(label: str, triples: list[Triple], allocation: dict[str, Any]) -> dict[str, Any]:
    graph_metrics = summarize_graph_triples(triples)
    connectivity = summarize_connectivity(triples)
    graph_metrics = {
        **graph_metrics,
        "weak_component_count": connectivity["weak_component_count"],
        "largest_weak_component_size": connectivity["largest_weak_component_size"],
        "largest_weak_component_ratio": connectivity["largest_weak_component_ratio"],
    }
    allocation_metrics = compare_relation_counts_to_allocation(graph_metrics["relation_counts"], allocation)
    allocation_metrics["pattern_level_expected_observed"] = compare_pattern_totals(graph_metrics["relation_counts"], allocation)
    return {
        "label": label,
        "graph_metrics": graph_metrics,
        "connectivity_metrics": connectivity,
        "allocation_metrics": allocation_metrics,
    }


def add_component_edge(
    edge_counts: Counter[tuple[int, int]],
    neighbors: dict[int, set[int]],
    edge: tuple[int, int],
    delta: int,
) -> None:
    audit.add_component_edge(edge_counts, neighbors, edge, delta)


def select_full_strategy(
    moves: list[dict[str, Any]],
    graph_triples: set[Triple],
    allocation: dict[str, Any],
    target_context: dict[str, Any],
    strategy: str,
) -> dict[str, Any]:
    relation_expected = allocation["relation_expected"]
    canonical_triples = set(graph_triples)
    auxiliary_triples: set[Triple] = set()
    relation_counts = Counter(r for _h, r, _t in canonical_triples)
    baseline_metrics = compare_relation_counts_to_allocation(relation_counts, allocation)
    baseline_surplus = float(baseline_metrics["total_surplus"])
    baseline_deficit = float(baseline_metrics["total_deficit"])
    selected: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    used_targets: set[Triple] = set()
    used_candidates: set[Triple] = set()
    aux_relation_counts: Counter[str] = Counter()
    component_edge_counts: Counter[tuple[int, int]] = Counter(
        {edge: 1 for edge in target_context["bridge_forest"]["bridge_edge_by_components"]}
    )
    component_neighbors: dict[int, set[int]] = defaultdict(set)
    for left, right in component_edge_counts:
        component_neighbors[left].add(right)
        component_neighbors[right].add(left)

    for move in audit.ordered_moves_for_strategy(moves, strategy):
        target = triple_from_edge(move["target_edge"])
        candidate = triple_from_edge(move["candidate"])
        relation = candidate[1]
        if target in used_targets:
            skipped["target_edge_already_used"] += 1
            continue
        if candidate in used_candidates:
            skipped["auxiliary_candidate_already_used"] += 1
            continue
        if target not in canonical_triples:
            skipped["target_edge_not_in_current_canonical_graph"] += 1
            continue
        if candidate in canonical_triples or candidate in auxiliary_triples:
            skipped["candidate_duplicate_in_current_graph"] += 1
            continue
        if relation in relation_expected:
            skipped["candidate_relation_is_allocated"] += 1
            continue
        block = audit.relation_block_reason(strategy, relation, aux_relation_counts, len(selected))
        if block:
            skipped[block] += 1
            continue
        delta = audit.current_remove_delta(relation_counts, relation_expected, target[1])
        if float(delta["surplus_delta"]) >= 0:
            skipped["target_relation_no_longer_surplus_reducing"] += 1
            continue
        if float(delta["deficit_delta"]) > 0:
            skipped["target_removal_would_increase_deficit"] += 1
            continue

        trial_canonical = set(canonical_triples)
        trial_auxiliary = set(auxiliary_triples)
        trial_canonical.remove(target)
        trial_auxiliary.add(candidate)
        full_triples = trial_canonical | trial_auxiliary
        duplicate_triples = len(trial_canonical) + len(trial_auxiliary) - len(full_triples)
        trial_counts = Counter(relation_counts)
        trial_counts[target[1]] -= 1
        allocation_metrics = compare_relation_counts_to_allocation(trial_counts, allocation)
        target_component_edge = tuple(sorted(int(value) for value in move["target_component_edge"]))
        candidate_component_edge = tuple(sorted(int(value) for value in move["candidate_component_edge"]))
        if duplicate_triples != 0:
            skipped["duplicate_triple_after_move"] += 1
            continue
        if not audit.connected_after_component_edge_swap(
            component_edge_counts,
            component_neighbors,
            target_component_edge,
            candidate_component_edge,
        ):
            skipped["full_graph_would_fragment"] += 1
            continue
        if allocation_metrics["allocated_relations_observed"] != len(relation_expected):
            skipped["canonical_relation_coverage_would_drop"] += 1
            continue
        if allocation_metrics["zero_allocated_relations"] != 0:
            skipped["zero_allocated_relation_would_appear"] += 1
            continue
        if float(allocation_metrics["total_deficit"]) - baseline_deficit > 0:
            skipped["cumulative_deficit_would_increase"] += 1
            continue

        canonical_triples = trial_canonical
        auxiliary_triples = trial_auxiliary
        relation_counts = trial_counts
        add_component_edge(component_edge_counts, component_neighbors, target_component_edge, -1)
        add_component_edge(component_edge_counts, component_neighbors, candidate_component_edge, 1)
        used_targets.add(target)
        used_candidates.add(candidate)
        aux_relation_counts[relation] += 1
        selected.append(
            {
                **move,
                "selection_rank": len(selected) + 1,
                "current_move_balance_delta": delta,
                "cumulative_canonical_surplus_delta": float(allocation_metrics["total_surplus"]) - baseline_surplus,
                "cumulative_canonical_deficit_delta": float(allocation_metrics["total_deficit"]) - baseline_deficit,
            }
        )

    full_triples = set(canonical_triples) | set(auxiliary_triples)
    final_metrics = compare_relation_counts_to_allocation(relation_counts, allocation)
    return {
        "selected": selected,
        "canonical_triples": canonical_triples,
        "auxiliary_triples": auxiliary_triples,
        "full_triples": full_triples,
        "removed_triples": set(graph_triples) - canonical_triples,
        "relation_counts": relation_counts,
        "final_allocation_metrics": final_metrics,
        "skipped_reason_counts": dict(sorted(skipped.items())),
        "canonical_surplus_delta": float(final_metrics["total_surplus"]) - baseline_surplus,
        "canonical_deficit_delta": float(final_metrics["total_deficit"]) - baseline_deficit,
    }


def reconstruct_selection(config: dict[str, Any], strategy: str) -> dict[str, Any]:
    parent_graph = audit.resolve_path(config["parent_graph_path"])
    allocation_path = audit.resolve_path(config["allocation_path"])
    graph_triples = set(load_graph_triples(parent_graph))
    allocation = load_allocation(allocation_path)
    print("phase=build_target_universe", file=sys.stderr, flush=True)
    target_context = audit.build_target_universe(graph_triples, allocation)
    print("phase=scan_expanded_sources", file=sys.stderr, flush=True)
    scan = audit.scan_sources_expanded(graph_triples, allocation, target_context)
    moves = scan.pop("moves")
    print(f"phase=select_best_strategy strategy={strategy} moves={len(moves)}", file=sys.stderr, flush=True)
    selection = select_full_strategy(moves, graph_triples, allocation, target_context, strategy)
    selection["scan_metadata"] = scan
    selection["move_count"] = len(moves)
    selection["target_context_summary"] = {
        "surplus_bridge_targets": target_context["target_stats"]["surplus_bridge_targets"],
        "surplus_non_bridge_targets": target_context["target_stats"]["surplus_non_bridge_targets"],
        "non_surplus_bridge_targets": target_context["target_stats"]["non_surplus_bridge_targets"],
    }
    return selection


def retained_edge_row(triple: Triple) -> dict[str, Any]:
    return {
        **triple_dict(triple),
        "edge_class": RETAINED_EDGE_CLASS,
        "source": "B0_parent_graph",
        "parent_candidate_id": PARENT_CANDIDATE_ID,
        "selection_strategy": None,
        "selection_rank": None,
        "removed_target_edge": None,
        "candidate_id": None,
        "source_path": None,
        "source_stage": None,
        "provenance_type": None,
        "duplicate_provenance_count": None,
        "counted_in_canonical_allocation": True,
        "counted_in_full_connectivity": True,
    }


def auxiliary_edge_row(move: dict[str, Any], strategy: str) -> dict[str, Any]:
    candidate = triple_from_edge(move["candidate"])
    return {
        **triple_dict(candidate),
        "edge_class": SELECTED_EDGE_CLASS,
        "source": "frozen_local_evidence",
        "parent_candidate_id": PARENT_CANDIDATE_ID,
        "selection_strategy": strategy,
        "selection_rank": move["selection_rank"],
        "removed_target_edge": move["target_edge"],
        "candidate_id": move.get("candidate_id"),
        "source_path": move.get("source_path"),
        "source_stage": move.get("source_stage"),
        "provenance_type": move.get("provenance_type"),
        "duplicate_provenance_count": move.get("duplicate_provenance_count"),
        "counted_in_canonical_allocation": False,
        "counted_in_full_connectivity": True,
    }


def removed_edge_row(move: dict[str, Any], strategy: str) -> dict[str, Any]:
    target = triple_from_edge(move["target_edge"])
    return {
        **triple_dict(target),
        "edge_class": REMOVED_EDGE_CLASS,
        "source": "B0_parent_graph",
        "parent_candidate_id": PARENT_CANDIDATE_ID,
        "selection_strategy": strategy,
        "selection_rank": move["selection_rank"],
        "replacement_auxiliary_edge": move["candidate"],
        "candidate_id": None,
        "source_path": None,
        "source_stage": None,
        "provenance_type": None,
        "duplicate_provenance_count": None,
        "counted_in_canonical_allocation": False,
        "counted_in_full_connectivity": False,
        "balance_delta_if_removed": move.get("current_move_balance_delta"),
    }


def top_relations(counter: Counter[str], limit: int = 20) -> list[dict[str, Any]]:
    return [{"relation": relation, "count": count} for relation, count in counter.most_common(limit)]


def build_evaluation(
    selection: dict[str, Any],
    allocation: dict[str, Any],
    baseline_metrics: dict[str, Any],
    strategy: str,
) -> dict[str, Any]:
    canonical_triples = sorted(selection["canonical_triples"])
    full_triples = sorted(selection["full_triples"])
    auxiliary_triples = sorted(selection["auxiliary_triples"])
    removed_triples = sorted(selection["removed_triples"])
    canonical_eval = evaluate_triples("canonical_only", canonical_triples, allocation)
    full_eval = evaluate_triples("full_experimental_graph", full_triples, allocation)
    aux_relation_counts = Counter(r for _h, r, _t in auxiliary_triples)
    removed_relation_counts = Counter(r for _h, r, _t in removed_triples)
    selected_count = len(auxiliary_triples)
    max_aux_count = max(aux_relation_counts.values(), default=0)
    max_aux_share = max_aux_count / selected_count if selected_count else 0.0

    canonical_allocation = canonical_eval["allocation_metrics"]
    full_graph_metrics = full_eval["graph_metrics"]
    canonical_graph_metrics = canonical_eval["graph_metrics"]
    baseline_graph = baseline_metrics["graph_metrics"]
    baseline_allocation = baseline_metrics["allocation_metrics"]
    canonical_surplus_delta = float(canonical_allocation["total_surplus"]) - float(baseline_allocation["total_surplus"])
    canonical_deficit_delta = float(canonical_allocation["total_deficit"]) - float(baseline_allocation["total_deficit"])
    p31_delta = relation_surplus(canonical_eval, "P31") - relation_surplus(baseline_metrics, "P31")
    p279_delta = relation_surplus(canonical_eval, "P279") - relation_surplus(baseline_metrics, "P279")
    p131_delta = relation_surplus(canonical_eval, "P131") - relation_surplus(baseline_metrics, "P131")
    key_relation_deltas = {
        relation: {
            "observed_delta": relation_observed(canonical_eval, relation) - relation_observed(baseline_metrics, relation),
            "surplus_delta": relation_surplus(canonical_eval, relation) - relation_surplus(baseline_metrics, relation),
            "deficit_delta": relation_deficit(canonical_eval, relation) - relation_deficit(baseline_metrics, relation),
        }
        for relation in ("P31", "P279", "P131")
    }
    composition_delta = composition_surplus(canonical_eval) - composition_surplus(baseline_metrics)
    duplicate_triples = full_graph_metrics["duplicate_triple_count"]
    policy_checks = {
        "full_graph_weak_components_eq_1": full_graph_metrics["weak_component_count"] == 1,
        "canonical_deficit_delta_le_0": canonical_deficit_delta <= 0,
        "canonical_allocated_relation_coverage_eq_139": canonical_allocation["allocated_relations_observed"] == 139,
        "canonical_zero_allocated_relations_eq_0": canonical_allocation["zero_allocated_relations"] == 0,
        "duplicate_triples_eq_0": duplicate_triples == 0,
        "canonical_surplus_reduction_gte_670": abs(canonical_surplus_delta) >= 670,
        "max_single_auxiliary_relation_share_le_0_40": max_aux_share <= 0.40,
    }
    policy_valid = all(policy_checks.values())
    return {
        "schema_version": "c5-h2-expanded-auxiliary-best-evaluation-v2",
        "candidate_id": CANDIDATE_ID,
        "parent_candidate_id": PARENT_CANDIDATE_ID,
        "selected_strategy": strategy,
        "policy_validation_status": "passed" if policy_valid else "failed",
        "policy_validation_checks": policy_checks,
        "canonical_only_metrics": {
            "unique_triples": canonical_graph_metrics["unique_triples"],
            "unique_entities": canonical_graph_metrics["unique_entities"],
            "unique_relations": canonical_graph_metrics["unique_relations"],
            "weak_components": canonical_graph_metrics["weak_component_count"],
            "largest_weak_component_ratio": canonical_graph_metrics["largest_weak_component_ratio"],
            "duplicate_triple_count": canonical_graph_metrics["duplicate_triple_count"],
            "allocated_relations_observed": canonical_allocation["allocated_relations_observed"],
            "zero_allocated_relations": canonical_allocation["zero_allocated_relations"],
            "total_surplus": canonical_allocation["total_surplus"],
            "total_deficit": canonical_allocation["total_deficit"],
            "composition_surplus": composition_surplus(canonical_eval),
            "P31_surplus_delta": p31_delta,
            "P279_surplus_delta": p279_delta,
            "P131_surplus_delta": p131_delta,
        },
        "full_graph_metrics": {
            "unique_triples": full_graph_metrics["unique_triples"],
            "unique_entities": full_graph_metrics["unique_entities"],
            "unique_relations": full_graph_metrics["unique_relations"],
            "weak_components": full_graph_metrics["weak_component_count"],
            "largest_weak_component_ratio": full_graph_metrics["largest_weak_component_ratio"],
            "duplicate_triple_count": full_graph_metrics["duplicate_triple_count"],
            "auxiliary_edge_count": selected_count,
            "auxiliary_relation_count": len(aux_relation_counts),
            "max_single_auxiliary_relation_count": max_aux_count,
            "max_single_auxiliary_relation_share": max_aux_share,
            "P17_auxiliary_count": aux_relation_counts.get("P17", 0),
            "P17_auxiliary_share": aux_relation_counts.get("P17", 0) / selected_count if selected_count else 0.0,
            "top_20_auxiliary_relations": top_relations(aux_relation_counts),
            "top_20_removed_canonical_relations": top_relations(removed_relation_counts),
        },
        "comparison_to_B0": {
            "canonical_surplus_before": baseline_allocation["total_surplus"],
            "canonical_surplus_after": canonical_allocation["total_surplus"],
            "canonical_surplus_delta": canonical_surplus_delta,
            "canonical_deficit_before": baseline_allocation["total_deficit"],
            "canonical_deficit_after": canonical_allocation["total_deficit"],
            "canonical_deficit_delta": canonical_deficit_delta,
            "composition_surplus_delta": composition_delta,
            "full_graph_weak_components_delta": full_graph_metrics["weak_component_count"] - baseline_graph["weak_component_count"],
            "canonical_only_weak_components_delta": canonical_graph_metrics["weak_component_count"] - baseline_graph["weak_component_count"],
            "relation_coverage_change": canonical_allocation["allocated_relations_observed"] - baseline_allocation["allocated_relations_observed"],
            "duplicate_change": duplicate_triples - baseline_graph["duplicate_triple_count"],
            "entity_count_change_full": full_graph_metrics["unique_entities"] - baseline_graph["unique_entities"],
            "entity_count_change_canonical_only": canonical_graph_metrics["unique_entities"] - baseline_graph["unique_entities"],
            "triple_count_change_full": full_graph_metrics["unique_triples"] - baseline_graph["unique_triples"],
            "triple_count_change_canonical_only": canonical_graph_metrics["unique_triples"] - baseline_graph["unique_triples"],
            "triples_per_entity_canonical_only": canonical_graph_metrics["unique_triples"] / canonical_graph_metrics["unique_entities"],
            "triples_per_entity_full_graph": full_graph_metrics["unique_triples"] / full_graph_metrics["unique_entities"],
            "key_relation_deltas": key_relation_deltas,
        },
        "selected_auxiliary_edge_count": selected_count,
        "removed_canonical_edge_count": len(removed_triples),
        "downstream_kge_evaluation_justified": bool(policy_valid),
        "downstream_kge_evaluation_note": (
            "Justified only as an experimental auxiliary-support graph with explicit edge-class accounting."
            if policy_valid
            else "Not justified until policy validation passes."
        ),
        "not_final_kg_note": "This experimental package is not a final KG and does not replace B0 without a later supervisor decision.",
    }


def baseline_evaluation(parent_graph: Path, allocation: dict[str, Any]) -> dict[str, Any]:
    return evaluate_triples("B0", load_graph_triples(parent_graph), allocation)


def audit_strategy_row(audit_report: dict[str, Any], strategy: str) -> dict[str, Any]:
    for row in audit_report.get("strategy_results", []):
        if row.get("strategy") == strategy:
            return row
    raise ValueError(f"Expanded audit report has no strategy_results row for strategy: {strategy}")


def reconstructed_audit_metrics(evaluation: dict[str, Any]) -> dict[str, Any]:
    canonical = evaluation["canonical_only_metrics"]
    full = evaluation["full_graph_metrics"]
    comparison = evaluation["comparison_to_B0"]
    return {
        "selected_auxiliary_edge_count": evaluation["selected_auxiliary_edge_count"],
        "removed_canonical_edge_count": evaluation["removed_canonical_edge_count"],
        "canonical_surplus_before": comparison["canonical_surplus_before"],
        "canonical_surplus_after": comparison["canonical_surplus_after"],
        "canonical_surplus_delta": comparison["canonical_surplus_delta"],
        "canonical_deficit_before": comparison["canonical_deficit_before"],
        "canonical_deficit_after": comparison["canonical_deficit_after"],
        "canonical_deficit_delta": comparison["canonical_deficit_delta"],
        "composition_surplus_delta": comparison["composition_surplus_delta"],
        "full_graph_weak_components": full["weak_components"],
        "canonical_only_weak_components": canonical["weak_components"],
        "duplicate_triple_count": full["duplicate_triple_count"],
        "allocated_relations_observed": canonical["allocated_relations_observed"],
        "zero_allocated_relations": canonical["zero_allocated_relations"],
        "remaining_total_surplus": canonical["total_surplus"],
        "remaining_total_deficit": canonical["total_deficit"],
        "auxiliary_relation_count": full["auxiliary_relation_count"],
        "max_single_auxiliary_relation_count": full["max_single_auxiliary_relation_count"],
        "max_single_auxiliary_relation_share": full["max_single_auxiliary_relation_share"],
        "p17_count": full["P17_auxiliary_count"],
        "p17_share": full["P17_auxiliary_share"],
        "key_relation_deltas": comparison["key_relation_deltas"],
    }


def values_match(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) <= AUDIT_FLOAT_TOLERANCE
    return actual == expected


def compare_audit_row(evaluation: dict[str, Any], audit_row: dict[str, Any]) -> dict[str, Any]:
    reconstructed = reconstructed_audit_metrics(evaluation)
    scalar_fields = [
        "selected_auxiliary_edge_count",
        "removed_canonical_edge_count",
        "canonical_surplus_before",
        "canonical_surplus_after",
        "canonical_surplus_delta",
        "canonical_deficit_before",
        "canonical_deficit_after",
        "canonical_deficit_delta",
        "composition_surplus_delta",
        "full_graph_weak_components",
        "canonical_only_weak_components",
        "duplicate_triple_count",
        "allocated_relations_observed",
        "zero_allocated_relations",
        "remaining_total_surplus",
        "remaining_total_deficit",
        "auxiliary_relation_count",
        "max_single_auxiliary_relation_count",
        "max_single_auxiliary_relation_share",
        "p17_count",
        "p17_share",
    ]
    mismatches: list[dict[str, Any]] = []
    for field in scalar_fields:
        actual = reconstructed.get(field)
        expected = audit_row.get(field)
        if not values_match(actual, expected):
            mismatches.append({"field": field, "reconstructed": actual, "audit_report": expected})

    for relation in ("P31", "P279", "P131"):
        actual_delta = reconstructed["key_relation_deltas"].get(relation, {})
        expected_delta = audit_row.get("key_relation_deltas", {}).get(relation, {})
        for field in ("observed_delta", "surplus_delta", "deficit_delta"):
            actual = actual_delta.get(field)
            expected = expected_delta.get(field)
            if not values_match(actual, expected):
                mismatches.append(
                    {
                        "field": f"key_relation_deltas.{relation}.{field}",
                        "reconstructed": actual,
                        "audit_report": expected,
                    }
                )

    return {
        "status": "matched" if not mismatches else "mismatched",
        "strategy": evaluation["selected_strategy"],
        "float_tolerance": AUDIT_FLOAT_TOLERANCE,
        "checked_scalar_fields": scalar_fields,
        "checked_key_relation_fields": ["observed_delta", "surplus_delta", "deficit_delta"],
        "mismatches": mismatches,
        "reconstructed_metrics": reconstructed,
        "audit_report_metrics": {field: audit_row.get(field) for field in scalar_fields}
        | {"key_relation_deltas": audit_row.get("key_relation_deltas", {})},
    }


def file_hashes(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    out = {}
    for name, path in paths.items():
        if path.is_file():
            out[name] = {"path": str(path), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    return out


def build_rows(selection: dict[str, Any], strategy: str) -> dict[str, list[dict[str, Any]]]:
    selected = sorted(selection["selected"], key=lambda move: int(move["selection_rank"]))
    removed_by_target = {triple_from_edge(move["target_edge"]): move for move in selected}
    retained_rows = [retained_edge_row(triple) for triple in sorted(selection["canonical_triples"])]
    auxiliary_rows = [auxiliary_edge_row(move, strategy) for move in selected]
    removed_rows = [removed_edge_row(removed_by_target[triple], strategy) for triple in sorted(selection["removed_triples"])]
    return {
        "canonical_only_graph": [bare_edge_row(row) for row in retained_rows],
        "canonical_only_graph_provenance": retained_rows,
        "auxiliary_edges": [bare_edge_row(row) for row in auxiliary_rows],
        "auxiliary_edges_provenance": auxiliary_rows,
        "removed_canonical_edges": [bare_edge_row(row) for row in removed_rows],
        "removed_canonical_edges_provenance": removed_rows,
        "full_graph": [bare_edge_row(row) for row in retained_rows + auxiliary_rows],
        "full_graph_provenance": retained_rows + auxiliary_rows,
        "edge_provenance": retained_rows + auxiliary_rows + removed_rows,
    }


def write_readme(path: Path, manifest: dict[str, Any], evaluation: dict[str, Any]) -> None:
    lines = [
        "# C5-H2 Expanded Auxiliary Best Candidate",
        "",
        "Status: experimental unregistered auxiliary-support candidate package.",
        "",
        f"- Candidate ID: `{manifest['candidate_id']}`",
        f"- Parent candidate: `{manifest['parent_candidate_id']}`",
        f"- Selected strategy: `{manifest['selected_strategy']}`",
        f"- Auxiliary edges: `{manifest['selected_auxiliary_edge_count']}`",
        f"- Removed canonical edges: `{manifest['removed_canonical_edge_count']}`",
        f"- Policy validation: `{evaluation['policy_validation_status']}`",
        f"- Audit strategy comparison: `{evaluation['audit_strategy_comparison']['status']}`",
        "",
        "## KGE Inputs",
        "",
        "Use this graph for the main downstream KGE comparison:",
        "",
        "```text",
        "full_graph.jsonl",
        "```",
        "",
        "The file is KGE-compatible JSONL with exactly `h`, `r`, and `t` keys per row.",
        "",
        "Optional diagnostic graph:",
        "",
        "```text",
        "canonical_only_graph.jsonl",
        "```",
        "",
        "This canonical-only graph excludes auxiliary support edges and is highly fragmented. It is useful for diagnosing whether any downstream gain depends on auxiliary support.",
        "",
        "## Edge Classes",
        "",
        "Auxiliary edges are observed in frozen local evidence but are unallocated relative to the canonical 139-relation allocation. They are not canonical allocation triples.",
        "",
        "The main graph JSONL files contain only bare `h`, `r`, and `t` rows. Provenance-rich rows are stored separately in:",
        "",
        "- `full_graph.provenance.jsonl`",
        "- `canonical_only_graph.provenance.jsonl`",
        "- `auxiliary_edges.provenance.jsonl`",
        "- `removed_canonical_edges.provenance.jsonl`",
        "- `edge_provenance.jsonl`",
        "",
        "## Regeneration",
        "",
        "Regenerate the expanded audit:",
        "",
        "```bash",
        "python tools/graph_candidate_generation/c5_audit_h2_auxiliary_expanded_saturation.py --force",
        "```",
        "",
        "Regenerate this package:",
        "",
        "```bash",
        "python tools/graph_candidate_generation/c5_generate_h2_auxiliary_expanded_best_candidate.py --force",
        "```",
        "",
        "The generator compares reconstructed selected-strategy metrics against the expanded audit report and fails on mismatch unless `--allow-audit-mismatch` is explicitly passed.",
        "",
        "## Reports",
        "",
        "- Manifest: `candidate_manifest.json`",
        "- Evaluation report: `evaluation_report.json`",
        "- Evaluation summary: `evaluation_summary.md`",
        "",
        "This package is not a final KG and does not replace B0 without a later supervisor decision.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_summary(path: Path, evaluation: dict[str, Any]) -> None:
    comp = evaluation["comparison_to_B0"]
    canonical = evaluation["canonical_only_metrics"]
    full = evaluation["full_graph_metrics"]
    lines = [
        "# C5-H2 Expanded Auxiliary Best Candidate Evaluation",
        "",
        f"Policy validation: `{evaluation['policy_validation_status']}`",
        "",
        "## Result",
        "",
        f"- Selected strategy: `{evaluation['selected_strategy']}`",
        f"- Auxiliary edges added: `{evaluation['selected_auxiliary_edge_count']}`",
        f"- Canonical edges removed: `{evaluation['removed_canonical_edge_count']}`",
        f"- Canonical surplus delta: `{comp['canonical_surplus_delta']}`",
        f"- Canonical deficit delta: `{comp['canonical_deficit_delta']}`",
        f"- Composition surplus delta: `{comp['composition_surplus_delta']}`",
        f"- Full graph weak components: `{full['weak_components']}`",
        f"- Canonical-only weak components: `{canonical['weak_components']}`",
        f"- Max auxiliary relation share: `{full['max_single_auxiliary_relation_share']}`",
        f"- P17 auxiliary share: `{full['P17_auxiliary_share']}`",
        f"- Audit strategy comparison: `{evaluation['audit_strategy_comparison']['status']}`",
        "",
        "## Interpretation",
        "",
        "Candidate generation succeeded and the package is ready for experimental review." if evaluation["policy_validation_status"] == "passed" else "Candidate generation completed, but policy validation failed.",
        "The reconstructed strategy metrics match the expanded saturation audit row." if evaluation["audit_strategy_comparison"]["status"] == "matched" else "The reconstructed strategy metrics differ from the expanded saturation audit row and require review.",
        "Full connectivity depends on auxiliary observed but unallocated support edges. The canonical-only view is highly fragmented and must be reported separately.",
        "This candidate is not a final KG and should not replace B0 unless a later decision changes the benchmark definition.",
        "",
        "## Next Decision",
        "",
        "Evaluate downstream utility as an experimental auxiliary-support graph, or reject due to auxiliary dependence and canonical-only fragmentation.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_package(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    audit_report_path = audit.resolve_path(args.audit_report)
    config_path = audit.resolve_path(args.config)
    policy_path = audit.resolve_path(args.policy)
    audit_report = load_json(audit_report_path)
    config = audit.load_c5_config(config_path)
    policy = load_json(policy_path)
    parent_graph = audit.resolve_path(config["parent_graph_path"])
    allocation_path = audit.resolve_path(config["allocation_path"])
    allocation = load_allocation(allocation_path)
    recommendation = audit_report.get("recommendation") or {}
    strategy = args.strategy or recommendation.get("best_strategy")
    if not strategy:
        raise ValueError("No selected strategy provided and audit report has no recommendation.best_strategy")
    if recommendation.get("step2_candidate_generation_justified") is not True and args.strategy is None:
        raise ValueError("Expanded audit report does not justify Step 2 generation")

    selection = reconstruct_selection(config, strategy)
    baseline = baseline_evaluation(parent_graph, allocation)
    evaluation = build_evaluation(selection, allocation, baseline, strategy)
    strategy_row = audit_strategy_row(audit_report, strategy)
    audit_comparison = compare_audit_row(evaluation, strategy_row)
    evaluation["audit_strategy_comparison"] = audit_comparison
    if audit_comparison["status"] != "matched" and not args.allow_audit_mismatch:
        mismatch_preview = json.dumps(audit_comparison["mismatches"][:10], indent=2, sort_keys=True)
        raise ValueError(
            "Reconstructed selected strategy metrics do not match expanded audit report row. "
            "Rerun with --allow-audit-mismatch only if the discrepancy is intentional. "
            f"First mismatches: {mismatch_preview}"
        )
    status = "experimental_unregistered" if evaluation["policy_validation_status"] == "passed" else "failed_policy_validation"
    paths = output_paths()
    rows = build_rows(selection, strategy)
    manifest_base = {
        "schema_version": "c5-h2-expanded-auxiliary-best-candidate-manifest-v2",
        "candidate_id": CANDIDATE_ID,
        "parent_candidate_id": PARENT_CANDIDATE_ID,
        "status": status,
        "selected_strategy": strategy,
        "audit_strategy_comparison": audit_comparison,
        "source_audit_report": {"path": str(args.audit_report), "sha256": sha256_file(audit_report_path)},
        "parent_graph": {"path": config["parent_graph_path"], "sha256": sha256_file(parent_graph)},
        "allocation": {"path": config["allocation_path"], "sha256": sha256_file(allocation_path)},
        "policy": {"path": str(args.policy), "sha256": sha256_file(policy_path)},
        "selected_auxiliary_edge_count": evaluation["selected_auxiliary_edge_count"],
        "removed_canonical_edge_count": evaluation["removed_canonical_edge_count"],
        "generated_by": GENERATED_BY,
        "notes": [
            "No candidate registry update was made.",
            "No WDQS query, LLM call, or SLURM job was used.",
            "No synthetic triples were used.",
            "Auxiliary edges are observed but unallocated.",
            "Main graph JSONL files contain bare h/r/t rows for KGE compatibility.",
            "Provenance-rich edge rows are preserved in .provenance.jsonl sidecars and edge_provenance.jsonl.",
            "This is not a canonical-only KG.",
            "This is not a B0 replacement.",
        ],
        "runtime": {"started_on": datetime.fromtimestamp(started, timezone.utc).isoformat()},
    }
    return {
        "paths": paths,
        "rows": rows,
        "evaluation": evaluation,
        "manifest_base": manifest_base,
    }


def write_package(package: dict[str, Any]) -> None:
    paths = package["paths"]
    rows = package["rows"]
    evaluation = package["evaluation"]
    manifest = dict(package["manifest_base"])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(paths["canonical_only_graph"], rows["canonical_only_graph"])
    write_jsonl(paths["canonical_only_graph_provenance"], rows["canonical_only_graph_provenance"])
    write_jsonl(paths["auxiliary_edges"], rows["auxiliary_edges"])
    write_jsonl(paths["auxiliary_edges_provenance"], rows["auxiliary_edges_provenance"])
    write_jsonl(paths["removed_canonical_edges"], rows["removed_canonical_edges"])
    write_jsonl(paths["removed_canonical_edges_provenance"], rows["removed_canonical_edges_provenance"])
    write_jsonl(paths["full_graph"], rows["full_graph"])
    write_jsonl(paths["full_graph_provenance"], rows["full_graph_provenance"])
    write_jsonl(paths["edge_provenance"], rows["edge_provenance"])
    paths["evaluation_report"].write_text(json.dumps(evaluation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_readme(paths["readme"], manifest, evaluation)
    write_summary(paths["evaluation_summary"], evaluation)
    hashable_paths = {name: path for name, path in paths.items() if name != "candidate_manifest"}
    manifest["generated_files"] = file_hashes(hashable_paths)
    manifest["generated_files"]["candidate_manifest"] = {
        "path": str(paths["candidate_manifest"]),
        "sha256": None,
        "self_hash_note": "The manifest does not embed its own SHA256 to avoid recursive hash instability.",
    }
    manifest["runtime"] = {
        **manifest["runtime"],
        "finished_on": datetime.now(timezone.utc).isoformat(),
    }
    paths["candidate_manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    paths = output_paths()
    if not args.dry_run:
        refuse_overwrite(paths, args.force)
    package = build_package(args)
    evaluation = package["evaluation"]
    if args.dry_run:
        print("dry_run=true")
        print(f"selected_strategy={evaluation['selected_strategy']}")
        print(f"selected_auxiliary_edge_count={evaluation['selected_auxiliary_edge_count']}")
        print(f"removed_canonical_edge_count={evaluation['removed_canonical_edge_count']}")
        print(f"canonical_surplus_delta={evaluation['comparison_to_B0']['canonical_surplus_delta']}")
        print(f"audit_strategy_comparison={evaluation['audit_strategy_comparison']['status']}")
        print(f"policy_validation_status={evaluation['policy_validation_status']}")
        print("outputs_written=false")
        return 0
    write_package(package)
    print(f"output_dir={OUTPUT_DIR}")
    print(f"selected_strategy={evaluation['selected_strategy']}")
    print(f"selected_auxiliary_edge_count={evaluation['selected_auxiliary_edge_count']}")
    print(f"removed_canonical_edge_count={evaluation['removed_canonical_edge_count']}")
    print(f"canonical_surplus_delta={evaluation['comparison_to_B0']['canonical_surplus_delta']}")
    print(f"canonical_deficit_delta={evaluation['comparison_to_B0']['canonical_deficit_delta']}")
    print(f"full_graph_weak_components={evaluation['full_graph_metrics']['weak_components']}")
    print(f"audit_strategy_comparison={evaluation['audit_strategy_comparison']['status']}")
    print(f"policy_validation_status={evaluation['policy_validation_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
