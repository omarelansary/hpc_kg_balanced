#!/usr/bin/env python3
"""Generate the constrained C5-H2 auxiliary-connectivity graph candidate."""

from __future__ import annotations

import argparse
import csv
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
from src.kg_pipeline.evaluation.candidate_report import evaluate_candidate, sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.connectivity_metrics import summarize_connectivity  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, count_relations, load_graph_triples  # noqa: E402
from src.kg_pipeline.evaluation.pattern_balance import compare_pattern_totals  # noqa: E402
from tools.graph_candidate_generation.c4_probe_bridge_aware_replace_add import (  # noqa: E402
    relation_delta,
    repo_relative,
    resolve_path,
)
from tools.graph_candidate_generation.c4_search_local_cut_crossing_candidates import (  # noqa: E402
    prepare_tested_cuts,
)
from tools.graph_candidate_generation.c5_probe_h1_h2_connectivity_support import (  # noqa: E402
    classify_h2,
    collect_cut_crossing_pairs,
    load_c5_config,
)

DEFAULT_CONFIG = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/config.template.json")
DEFAULT_POLICY = Path(
    "experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/"
    "h2_generator_policy.template.json"
)
DEFAULT_C5_REPORT = Path(
    "experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/"
    "c5_h1_h2_probe_report.json"
)
DEFAULT_SCORE_AUDIT = Path(
    "experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/"
    "c5_candidate_score_provenance_audit.json"
)
DEFAULT_C4_2_REPORT = Path(
    "experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/"
    "local_cut_crossing_candidate_search.json"
)
EXPERIMENT_DIR = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix")
OUTPUT_DIR = EXPERIMENT_DIR / "outputs"
REPORT_DIR = EXPERIMENT_DIR / "reports"
TARGET_RELATIONS = {"P31", "P279", "P131"}
ALLOWED_EDGE_CLASSES = {"canonical_allocated_observed", "auxiliary_unallocated_observed"}
DISALLOWED_EDGE_CLASSES = {"synthetic_pattern_derived", "live_verified_observed", "synthetic_unverified"}
GENERATED_BY = "tools/graph_candidate_generation/c5_generate_h2_auxiliary_connectivity_candidate.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--max-auxiliary-edges", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def load_policy(path: Path) -> dict[str, Any]:
    policy = load_json(path)
    if policy.get("schema_version") != "c5-h2-generator-policy-v1":
        raise ValueError(f"Unexpected C5-H2 policy schema_version: {policy.get('schema_version')!r}")
    acceptance = policy.get("methodological_acceptance") or {}
    if acceptance.get("h2_accepted_as_experimental_auxiliary_branch") is not True:
        raise ValueError("C5-H2 policy does not accept H2 as an experimental auxiliary branch")
    if set(policy.get("allowed_edge_classes") or []) != ALLOWED_EDGE_CLASSES:
        raise ValueError("C5-H2 policy must allow only canonical_allocated_observed and auxiliary_unallocated_observed")
    if not DISALLOWED_EDGE_CLASSES.issubset(set(policy.get("disallowed_edge_classes") or [])):
        raise ValueError("C5-H2 policy must disallow synthetic, live-verified, and unverified edge classes")
    if acceptance.get("count_toward_canonical_allocation_surplus_deficit") is not False:
        raise ValueError("C5-H2 auxiliary edges must not count toward canonical allocation surplus/deficit")
    return policy


def validate_config(config: dict[str, Any]) -> None:
    for key in ("allowed_live_sources", "allowed_wdqs", "allowed_llm", "allowed_synthetic_pattern_derived"):
        if config.get(key) is not False:
            raise ValueError(f"C5-H2 generator requires {key}=false")


def output_paths() -> dict[str, Path]:
    return {
        "graph": OUTPUT_DIR / "graph.jsonl",
        "canonical_edges": OUTPUT_DIR / "canonical_edges.jsonl",
        "auxiliary_edges": OUTPUT_DIR / "auxiliary_edges.jsonl",
        "removed_canonical_edges": OUTPUT_DIR / "removed_canonical_edges.jsonl",
        "report": REPORT_DIR / "report.json",
        "summary": REPORT_DIR / "summary.md",
        "relation_quota_report": REPORT_DIR / "relation_quota_report.tsv",
        "pattern_balance_report": REPORT_DIR / "pattern_balance_report.tsv",
        "manifest": REPORT_DIR / "manifest.json",
        "auxiliary_edge_report": REPORT_DIR / "auxiliary_edge_report.tsv",
        "removed_edge_report": REPORT_DIR / "removed_edge_report.tsv",
    }


def refuse_overwrite(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite C5-H2 outputs without --force: {names}")


def triple_dict(triple: Triple) -> dict[str, str]:
    h, r, t = triple
    return {"h": h, "r": r, "t": t}


def triple_key(edge: dict[str, str]) -> Triple:
    return edge["h"], edge["r"], edge["t"]


def fmt(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def iter_jsonl_rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                yield line_number, None
                continue
            yield line_number, row if isinstance(row, dict) else None


def load_source_rows(moves: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any] | None]:
    wanted: dict[Path, set[int]] = defaultdict(set)
    for move in moves:
        wanted[resolve_path(move["source_path"])].add(int(move["line_number"]))

    out: dict[tuple[str, int], dict[str, Any] | None] = {}
    for path, lines in wanted.items():
        remaining = set(lines)
        if not path.is_file():
            for line in remaining:
                out[(repo_relative(path), line)] = None
            continue
        for line_number, row in iter_jsonl_rows(path):
            if line_number not in remaining:
                continue
            out[(repo_relative(path), line_number)] = row
            remaining.remove(line_number)
            if not remaining:
                break
        for line in remaining:
            out[(repo_relative(path), line)] = None
    return out


def provenance_fields(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = (
        "accepted",
        "candidate_id",
        "classification_label",
        "duplicate_provenance_count",
        "endpoint_overlap_with_b0",
        "in_b0",
        "is_primary_source",
        "is_target_generic_relation",
        "notes",
        "path_group_id",
        "path_role",
        "provenance_type",
        "relation_allocation_status",
        "source_artifact",
        "source_event_type",
        "source_record_index",
        "source_sha256",
        "source_stage",
    )
    return {key: row.get(key) for key in keys if row.get(key) is not None}


def build_h2_moves(config: dict[str, Any], c5_report: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parent_graph = resolve_path(config["parent_graph_path"])
    allocation_path = resolve_path(config["allocation_path"])
    graph_triples = set(load_graph_triples(parent_graph))
    entities = {node for h, _r, t in graph_triples for node in (h, t)}
    relation_counts = Counter(r for _h, r, _t in graph_triples)
    allocation = load_allocation(allocation_path)
    relation_expected = allocation["relation_expected"]
    max_cuts = int(c5_report["limits"]["max_cuts"])
    max_candidates = int(c5_report["limits"]["max_candidates"])
    cuts, cut_index = prepare_tested_cuts(
        graph_triples,
        entities,
        relation_counts,
        relation_expected,
        TARGET_RELATIONS,
        max_cuts,
    )
    pairs, scan_metadata = collect_cut_crossing_pairs(cuts, cut_index, graph_triples, entities, max_candidates)
    h2_pairs = [pair for pair in pairs if pair["candidate"]["r"] not in relation_expected]
    classified = [
        classify_h2(pair, graph_triples, relation_counts, relation_expected, allocation, len(graph_triples))
        for pair in h2_pairs
    ]
    feasible = [row for row in classified if row["classification"] == "feasible_h2_auxiliary_enables_prune"]

    source_rows = load_source_rows(feasible)
    enriched: list[dict[str, Any]] = []
    for move in feasible:
        source_key = (move["source_path"], int(move["line_number"]))
        row = source_rows.get(source_key)
        prov = provenance_fields(row)
        enriched.append(
            {
                **move,
                "source_row_found": row is not None,
                "provenance_fields": prov,
                "duplicate_provenance_count": int(prov.get("duplicate_provenance_count") or 0),
                "source_stage": str(prov.get("source_stage") or ""),
                "provenance_type": str(prov.get("provenance_type") or ""),
                "candidate_id": prov.get("candidate_id"),
            }
        )
    return enriched, scan_metadata


def rank_move(move: dict[str, Any]) -> tuple[Any, ...]:
    target = triple_key(move["target_edge"])
    candidate = triple_key(move["candidate"])
    return (
        float(move["canonical_surplus_delta"]),
        float(move["canonical_deficit_delta"]),
        -int(move.get("duplicate_provenance_count") or 0),
        move.get("source_stage") or "",
        move.get("provenance_type") or "",
        1,
        int(move["cut_id"]),
        target,
        candidate,
    )


def current_relation_delta(
    relation_counts: Counter[str],
    relation_expected: dict[str, float],
    target_relation: str,
) -> dict[str, Any]:
    return relation_delta(relation_counts, relation_expected, target_relation, None)


def hard_constraint_check(
    canonical_triples: set[Triple],
    auxiliary_triples: set[Triple],
    allocation: dict[str, Any],
) -> dict[str, Any]:
    full_triples = set(canonical_triples) | set(auxiliary_triples)
    relation_counts = count_relations(canonical_triples)
    allocation_metrics = compare_relation_counts_to_allocation(relation_counts, allocation)
    full_connectivity = summarize_connectivity(full_triples)
    canonical_connectivity = summarize_connectivity(canonical_triples)
    duplicate_triples = len(canonical_triples) + len(auxiliary_triples) - len(full_triples)
    return {
        "passes": (
            full_connectivity["weak_component_count"] == 1
            and duplicate_triples == 0
            and allocation_metrics["allocated_relations_observed"] == len(allocation["relation_expected"])
            and allocation_metrics["zero_allocated_relations"] == 0
        ),
        "duplicate_triple_count": duplicate_triples,
        "allocated_relations_observed": allocation_metrics["allocated_relations_observed"],
        "zero_allocated_relations": allocation_metrics["zero_allocated_relations"],
        "weak_components_with_auxiliary": full_connectivity["weak_component_count"],
        "weak_components_without_auxiliary": canonical_connectivity["weak_component_count"],
        "canonical_total_surplus": allocation_metrics["total_surplus"],
        "canonical_total_deficit": allocation_metrics["total_deficit"],
    }


def select_moves(
    moves: list[dict[str, Any]],
    graph_triples: set[Triple],
    allocation: dict[str, Any],
    policy: dict[str, Any],
    max_auxiliary_edges: int,
) -> dict[str, Any]:
    relation_expected = allocation["relation_expected"]
    canonical_triples = set(graph_triples)
    auxiliary_triples: set[Triple] = set()
    relation_counts = Counter(r for _h, r, _t in canonical_triples)
    baseline_metrics = compare_relation_counts_to_allocation(relation_counts, allocation)
    baseline_surplus = float(baseline_metrics["total_surplus"])
    baseline_deficit = float(baseline_metrics["total_deficit"])
    thresholds = policy["thresholds"]
    selected: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    used_targets: set[Triple] = set()
    used_candidates: set[Triple] = set()

    for move in sorted(moves, key=rank_move):
        if len(selected) >= max_auxiliary_edges:
            break
        target = triple_key(move["target_edge"])
        candidate = triple_key(move["candidate"])
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
        if candidate[1] in relation_expected:
            skipped["candidate_relation_is_allocated"] += 1
            continue
        if not move.get("source_row_found"):
            skipped["source_row_missing"] += 1
            continue
        current_delta = current_relation_delta(relation_counts, relation_expected, target[1])
        if not (float(current_delta["surplus_delta"]) < float(thresholds["require_surplus_delta_lt"])):
            skipped["selected_move_not_surplus_reducing"] += 1
            continue
        if float(current_delta["deficit_delta"]) > float(thresholds["require_total_deficit_delta_le"]):
            skipped["selected_move_increases_deficit"] += 1
            continue

        trial_canonical = set(canonical_triples)
        trial_auxiliary = set(auxiliary_triples)
        trial_canonical.remove(target)
        trial_auxiliary.add(candidate)
        constraints = hard_constraint_check(trial_canonical, trial_auxiliary, allocation)
        if not constraints["passes"]:
            skipped["interaction_breaks_hard_constraints"] += 1
            continue
        trial_surplus_delta = float(constraints["canonical_total_surplus"]) - baseline_surplus
        trial_deficit_delta = float(constraints["canonical_total_deficit"]) - baseline_deficit
        if trial_deficit_delta > float(thresholds["require_total_deficit_delta_le"]):
            skipped["cumulative_deficit_increase"] += 1
            continue

        canonical_triples = trial_canonical
        auxiliary_triples = trial_auxiliary
        relation_counts[target[1]] -= 1
        used_targets.add(target)
        used_candidates.add(candidate)
        selected.append(
            {
                **move,
                "selection_rank": len(selected) + 1,
                "current_move_balance_delta": current_delta,
                "post_move_constraints": constraints,
                "cumulative_canonical_surplus_delta": trial_surplus_delta,
                "cumulative_canonical_deficit_delta": trial_deficit_delta,
            }
        )

    final_metrics = compare_relation_counts_to_allocation(relation_counts, allocation)
    return {
        "selected": selected,
        "skipped_reasons": dict(sorted(skipped.items())),
        "canonical_triples": canonical_triples,
        "auxiliary_triples": auxiliary_triples,
        "removed_triples": set(graph_triples) - canonical_triples,
        "baseline_surplus": baseline_surplus,
        "baseline_deficit": baseline_deficit,
        "final_surplus": float(final_metrics["total_surplus"]),
        "final_deficit": float(final_metrics["total_deficit"]),
        "canonical_surplus_delta": float(final_metrics["total_surplus"]) - baseline_surplus,
        "canonical_deficit_delta": float(final_metrics["total_deficit"]) - baseline_deficit,
    }


def edge_rows(
    canonical_triples: set[Triple],
    auxiliary_moves: list[dict[str, Any]],
    removed_moves: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    removed_targets = {triple_key(move["target_edge"]): move for move in removed_moves}
    auxiliary_by_triple = {triple_key(move["candidate"]): move for move in auxiliary_moves}
    canonical_rows = [
        {
            **triple_dict(triple),
            "edge_role": "canonical_allocated_observed",
            "evidence_status": "frozen_observed",
            "source": "B0_parent_graph",
            "parent_candidate_id": "B0",
        }
        for triple in sorted(canonical_triples)
    ]
    auxiliary_rows = []
    for triple in sorted(auxiliary_by_triple):
        move = auxiliary_by_triple[triple]
        auxiliary_rows.append(
            {
                **triple_dict(triple),
                "edge_role": "auxiliary_unallocated_observed",
                "evidence_status": "frozen_observed",
                "source": "frozen_candidate_pool",
                "candidate_id": move.get("candidate_id"),
                "cut_id": move["cut_id"],
                "selection_rank": move["selection_rank"],
                "source_path": move["source_path"],
                "line_number": move["line_number"],
                "target_edge": move["target_edge"],
                "duplicate_provenance_count": move.get("duplicate_provenance_count"),
                "source_stage": move.get("source_stage"),
                "provenance_type": move.get("provenance_type"),
                "source_metadata": move.get("provenance_fields", {}),
            }
        )
    removed_rows = []
    for triple in sorted(removed_targets):
        move = removed_targets[triple]
        removed_rows.append(
            {
                **triple_dict(triple),
                "edge_role": "canonical_allocated_observed",
                "evidence_status": "frozen_observed",
                "source": "B0_parent_graph",
                "removal_reason": "surplus_bridge_edge_pruned_after_auxiliary_support",
                "cut_id": move["cut_id"],
                "selection_rank": move["selection_rank"],
                "auxiliary_candidate": move["candidate"],
                "current_move_balance_delta": move["current_move_balance_delta"],
            }
        )
    graph_rows = canonical_rows + auxiliary_rows
    return {
        "graph": graph_rows,
        "canonical_edges": canonical_rows,
        "auxiliary_edges": auxiliary_rows,
        "removed_canonical_edges": removed_rows,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def relation_status(row: dict[str, Any]) -> str:
    if float(row["deficit"]) > 0:
        return "underfilled"
    if float(row["surplus"]) > 0:
        return "overfilled"
    return "met"


def write_relation_quota_report(report: dict[str, Any], path: Path) -> None:
    rows = report["allocation_metrics"]["per_relation_expected_observed"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["relation", "expected", "observed", "surplus", "deficit", "status"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "relation": row["relation"],
                    "expected": fmt(row["expected_eta"]),
                    "observed": row["observed_count"],
                    "surplus": fmt(row["surplus"]),
                    "deficit": fmt(row["deficit"]),
                    "status": relation_status(row),
                }
            )


def write_pattern_balance_report(report: dict[str, Any], path: Path) -> None:
    rows = report["allocation_metrics"]["pattern_level_expected_observed"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["pattern", "expected", "observed", "surplus", "deficit"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "pattern": row["pattern"],
                    "expected": fmt(row["expected_eta"]),
                    "observed": fmt(row["observed_count_apportioned"]),
                    "surplus": fmt(row["surplus"]),
                    "deficit": fmt(row["deficit"]),
                }
            )


def write_edge_report(path: Path, rows: list[dict[str, Any]], auxiliary: bool) -> None:
    if auxiliary:
        fields = [
            "selection_rank",
            "h",
            "r",
            "t",
            "cut_id",
            "candidate_id",
            "duplicate_provenance_count",
            "source_stage",
            "provenance_type",
            "source_path",
            "line_number",
        ]
    else:
        fields = ["selection_rank", "h", "r", "t", "cut_id", "auxiliary_h", "auxiliary_r", "auxiliary_t"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            if auxiliary:
                writer.writerow({field: row.get(field) for field in fields})
            else:
                aux = row.get("auxiliary_candidate") or {}
                writer.writerow(
                    {
                        "selection_rank": row.get("selection_rank"),
                        "h": row.get("h"),
                        "r": row.get("r"),
                        "t": row.get("t"),
                        "cut_id": row.get("cut_id"),
                        "auxiliary_h": aux.get("h"),
                        "auxiliary_r": aux.get("r"),
                        "auxiliary_t": aux.get("t"),
                    }
                )


def write_summary(path: Path, report: dict[str, Any]) -> None:
    summary = report["selection_summary"]
    evals = report["evaluation"]
    edge_accounting = report["edge_accounting"]
    lines = [
        "# C5-H2 Auxiliary Connectivity Candidate",
        "",
        f"Acceptance classification: `{report['acceptance_classification']}`",
        "",
        "## Selection",
        "",
        f"- Auxiliary edges selected: `{summary['selected_auxiliary_edges']}`",
        f"- Canonical edges removed: `{summary['removed_canonical_edges']}`",
        f"- Max auxiliary edge cap: `{summary['max_auxiliary_edges']}`",
        f"- Canonical surplus delta: `{summary['canonical_surplus_delta']}`",
        f"- Canonical deficit delta: `{summary['canonical_deficit_delta']}`",
        "",
        "## Edge Accounting",
        "",
        f"- Canonical allocated triples: `{edge_accounting['canonical_allocated_triples']}`",
        f"- Auxiliary unallocated observed edges: `{edge_accounting['auxiliary_unallocated_observed_edges']}`",
        f"- Full graph triples: `{edge_accounting['full_graph_triples']}`",
        f"- Unallocated auxiliary relation count: `{edge_accounting['unallocated_auxiliary_relation_count']}`",
        "",
        "## Connectivity",
        "",
        f"- Weak components with auxiliary: `{evals['full_graph']['graph_metrics']['weak_component_count']}`",
        f"- Weak components without auxiliary: `{evals['canonical_only']['graph_metrics']['weak_component_count']}`",
        "",
        "## Notes",
        "",
        "- This is an experimental auxiliary-connectivity graph candidate.",
        "- Auxiliary unallocated observed edges are not canonical benchmark triples.",
        "- Canonical allocation surplus/deficit is computed over canonical allocated edges only.",
        "- No WDQS query, LLM call, or synthetic triple generation was performed.",
        "- `candidate_registry.v1.json` was not updated.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def acceptance_classification(
    selected: list[dict[str, Any]],
    max_auxiliary_edges: int,
    canonical_eval: dict[str, Any],
    full_eval: dict[str, Any],
    selection_result: dict[str, Any],
) -> str:
    if not selected:
        return "c5_h2_no_moves_selected"
    allocation = canonical_eval["allocation_metrics"]
    graph = full_eval["graph_metrics"]
    passes = (
        len(selected) <= max_auxiliary_edges
        and selection_result["canonical_surplus_delta"] < 0
        and selection_result["canonical_deficit_delta"] <= 0
        and allocation["allocated_relations_observed"] == 139
        and allocation["zero_allocated_relations"] == 0
        and graph["duplicate_triple_count"] == 0
        and graph["weak_component_count"] == 1
    )
    return "c5_h2_candidate_passed_policy" if passes else "c5_h2_candidate_failed_constraints"


def build_report(
    args: argparse.Namespace,
    config_path: Path,
    policy_path: Path,
    config: dict[str, Any],
    policy: dict[str, Any],
    c5_report: dict[str, Any],
    score_audit: dict[str, Any],
    c4_2_report: dict[str, Any],
    scan_metadata: dict[str, Any],
    selection_result: dict[str, Any],
    paths: dict[str, Path],
    started: float,
    finished: float,
) -> dict[str, Any]:
    full_eval = evaluate_candidate(paths["graph"], resolve_path(config["allocation_path"]), config["candidate_id"], "C5-H2")
    canonical_eval = evaluate_candidate(
        paths["canonical_edges"],
        resolve_path(config["allocation_path"]),
        config["candidate_id"] + "_canonical_only",
        "C5-H2 canonical allocated view",
    )
    selected = selection_result["selected"]
    aux_relation_counts = Counter(move["candidate"]["r"] for move in selected)
    classification = acceptance_classification(
        selected,
        int(args.max_auxiliary_edges),
        canonical_eval,
        full_eval,
        selection_result,
    )
    report = {
        "schema_version": "c5-h2-auxiliary-connectivity-candidate-report-v1",
        "candidate_id": config["candidate_id"],
        "parent_candidate_id": config["parent_candidate_id"],
        "generated_by": GENERATED_BY,
        "acceptance_classification": classification,
        "status": "graph_candidate_generated_experimental_auxiliary_branch",
        "inputs": {
            "config": {"path": repo_relative(config_path), "sha256": sha256_file(config_path)},
            "policy": {"path": repo_relative(policy_path), "sha256": sha256_file(policy_path)},
            "c5_h1_h2_probe_report": {
                "path": str(DEFAULT_C5_REPORT),
                "sha256": sha256_file(resolve_path(DEFAULT_C5_REPORT)),
                "h2_summary": c5_report.get("h2_summary"),
                "greedy_h2_upper_bound": {
                    key: value
                    for key, value in (c5_report.get("greedy_h2_upper_bound") or {}).items()
                    if key != "examples"
                },
            },
            "c5_candidate_score_provenance_audit": {
                "path": str(DEFAULT_SCORE_AUDIT),
                "sha256": sha256_file(resolve_path(DEFAULT_SCORE_AUDIT)),
                "score_reuse_assessment": score_audit.get("score_reuse_assessment"),
            },
            "c4_2_local_cut_crossing_search": {
                "path": str(DEFAULT_C4_2_REPORT),
                "sha256": sha256_file(resolve_path(DEFAULT_C4_2_REPORT)),
                "aggregate_counts": c4_2_report.get("aggregate_counts"),
            },
            "parent_graph": {"path": config["parent_graph_path"], "sha256": sha256_file(resolve_path(config["parent_graph_path"]))},
            "allocation": {"path": config["allocation_path"], "sha256": sha256_file(resolve_path(config["allocation_path"]))},
        },
        "policy_enforcement": {
            "allowed_edge_classes": policy["allowed_edge_classes"],
            "disallowed_edge_classes": policy["disallowed_edge_classes"],
            "max_auxiliary_edges": args.max_auxiliary_edges,
            "wdqs_enabled": False,
            "llm_enabled": False,
            "synthetic_enabled": False,
            "old_phase2_scores_primary_ranking_input": False,
        },
        "candidate_scan_metadata": scan_metadata,
        "selection_summary": {
            "candidate_moves_available": len(selection_result.get("candidate_moves_available", [])),
            "selected_auxiliary_edges": len(selected),
            "removed_canonical_edges": len(selection_result["removed_triples"]),
            "max_auxiliary_edges": args.max_auxiliary_edges,
            "canonical_surplus_before": selection_result["baseline_surplus"],
            "canonical_surplus_after": selection_result["final_surplus"],
            "canonical_surplus_delta": selection_result["canonical_surplus_delta"],
            "canonical_deficit_before": selection_result["baseline_deficit"],
            "canonical_deficit_after": selection_result["final_deficit"],
            "canonical_deficit_delta": selection_result["canonical_deficit_delta"],
            "skipped_reasons": selection_result["skipped_reasons"],
        },
        "edge_accounting": {
            "canonical_allocated_triples": canonical_eval["graph_metrics"]["unique_triples"],
            "auxiliary_unallocated_observed_edges": len(selected),
            "full_graph_triples": full_eval["graph_metrics"]["unique_triples"],
            "unallocated_auxiliary_relation_count": len(aux_relation_counts),
            "auxiliary_relation_distribution": dict(sorted(aux_relation_counts.items())),
            "auxiliary_edges_sha256": sha256_file(paths["auxiliary_edges"]),
            "removed_canonical_edges_sha256": sha256_file(paths["removed_canonical_edges"]),
            "canonical_edges_sha256": sha256_file(paths["canonical_edges"]),
            "graph_sha256": sha256_file(paths["graph"]),
        },
        "evaluation": {
            "standard_evaluator_status": "full_and_canonical_views_evaluated",
            "schema_limitation": None,
            "full_graph": full_eval,
            "canonical_only": canonical_eval,
            "connectivity_after_removing_auxiliary_edges": canonical_eval["connectivity_metrics"],
            "canonical_allocation_scope_note": (
                "Canonical allocation surplus/deficit is evaluated over canonical_edges.jsonl only. "
                "Auxiliary unallocated observed edges are excluded from canonical allocation accounting."
            ),
        },
        "selected_moves": compact_moves(selected, limit=100),
        "notes": [
            "This is an experimental auxiliary-connectivity graph candidate.",
            "Auxiliary unallocated observed edges are not canonical benchmark triples.",
            "No WDQS query was made.",
            "No LLM call was made.",
            "No synthetic triples were created.",
            "candidate_registry.v1.json was not updated.",
        ],
        "runtime": {
            "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
            "elapsed_seconds": round(finished - started, 6),
        },
    }
    return report


def compact_moves(moves: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    out = []
    for move in moves[:limit]:
        out.append(
            {
                "selection_rank": move["selection_rank"],
                "candidate": move["candidate"],
                "target_edge": move["target_edge"],
                "cut_id": move["cut_id"],
                "source_path": move["source_path"],
                "line_number": move["line_number"],
                "candidate_id": move.get("candidate_id"),
                "duplicate_provenance_count": move.get("duplicate_provenance_count"),
                "source_stage": move.get("source_stage"),
                "provenance_type": move.get("provenance_type"),
                "current_move_balance_delta": move.get("current_move_balance_delta"),
                "cumulative_canonical_surplus_delta": move.get("cumulative_canonical_surplus_delta"),
                "cumulative_canonical_deficit_delta": move.get("cumulative_canonical_deficit_delta"),
            }
        )
    return out


def build_manifest(report: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "schema_version": "c5-h2-auxiliary-connectivity-manifest-v1",
        "candidate_id": report["candidate_id"],
        "parent_candidate_id": report["parent_candidate_id"],
        "acceptance_classification": report["acceptance_classification"],
        "outputs": {name: str(path) for name, path in sorted(paths.items())},
        "hashes": {
            "graph": sha256_file(paths["graph"]),
            "canonical_edges": sha256_file(paths["canonical_edges"]),
            "auxiliary_edges": sha256_file(paths["auxiliary_edges"]),
            "removed_canonical_edges": sha256_file(paths["removed_canonical_edges"]),
            "report": sha256_file(paths["report"]),
            "relation_quota_report": sha256_file(paths["relation_quota_report"]),
            "pattern_balance_report": sha256_file(paths["pattern_balance_report"]),
            "auxiliary_edge_report": sha256_file(paths["auxiliary_edge_report"]),
            "removed_edge_report": sha256_file(paths["removed_edge_report"]),
        },
        "generated_by": GENERATED_BY,
        "notes": [
            "No WDQS query was made.",
            "No LLM call was made.",
            "No synthetic triples were created.",
            "candidate_registry.v1.json was not updated.",
        ],
    }


def write_outputs(
    paths: dict[str, Path],
    rows: dict[str, list[dict[str, Any]]],
    report: dict[str, Any],
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(paths["graph"], rows["graph"])
    write_jsonl(paths["canonical_edges"], rows["canonical_edges"])
    write_jsonl(paths["auxiliary_edges"], rows["auxiliary_edges"])
    write_jsonl(paths["removed_canonical_edges"], rows["removed_canonical_edges"])
    paths["report"].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_summary(paths["summary"], report)
    write_relation_quota_report(report["evaluation"]["canonical_only"], paths["relation_quota_report"])
    write_pattern_balance_report(report["evaluation"]["canonical_only"], paths["pattern_balance_report"])
    write_edge_report(paths["auxiliary_edge_report"], rows["auxiliary_edges"], auxiliary=True)
    write_edge_report(paths["removed_edge_report"], rows["removed_canonical_edges"], auxiliary=False)
    manifest = build_manifest(report, paths)
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    started = time.time()
    config_path = resolve_path(args.config)
    policy_path = resolve_path(args.policy)
    c5_report_path = resolve_path(DEFAULT_C5_REPORT)
    score_audit_path = resolve_path(DEFAULT_SCORE_AUDIT)
    c4_2_path = resolve_path(DEFAULT_C4_2_REPORT)
    config = load_c5_config(config_path)
    validate_config(config)
    policy = load_policy(policy_path)
    c5_report = load_json(c5_report_path)
    score_audit = load_json(score_audit_path)
    c4_2_report = load_json(c4_2_path)

    if args.max_auxiliary_edges is None:
        args.max_auxiliary_edges = int(policy["thresholds"]["max_auxiliary_edges_default"])
    if args.max_auxiliary_edges <= 0:
        raise ValueError("--max-auxiliary-edges must be positive")
    if args.max_auxiliary_edges > int(policy["thresholds"]["max_auxiliary_edges_probe_upper_bound"]):
        raise ValueError("--max-auxiliary-edges exceeds the C5-H2 probe upper-bound cap")

    paths = output_paths()
    if not args.dry_run:
        refuse_overwrite(paths, args.force)

    parent_graph = resolve_path(config["parent_graph_path"])
    allocation_path = resolve_path(config["allocation_path"])
    graph_triples = set(load_graph_triples(parent_graph))
    allocation = load_allocation(allocation_path)
    moves, scan_metadata = build_h2_moves(config, c5_report)
    selection_result = select_moves(moves, graph_triples, allocation, policy, args.max_auxiliary_edges)
    selection_result["candidate_moves_available"] = moves
    rows = edge_rows(
        selection_result["canonical_triples"],
        selection_result["selected"],
        selection_result["selected"],
    )

    if args.dry_run:
        print("dry_run=true")
        print(f"candidate_id={config['candidate_id']}")
        print(f"h2_moves_available={len(moves)}")
        print(f"selected_auxiliary_edges={len(selection_result['selected'])}")
        print(f"canonical_surplus_delta={selection_result['canonical_surplus_delta']}")
        print(f"canonical_deficit_delta={selection_result['canonical_deficit_delta']}")
        print("outputs_written=false")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(paths["graph"], rows["graph"])
    write_jsonl(paths["canonical_edges"], rows["canonical_edges"])
    write_jsonl(paths["auxiliary_edges"], rows["auxiliary_edges"])
    write_jsonl(paths["removed_canonical_edges"], rows["removed_canonical_edges"])
    finished = time.time()
    report = build_report(
        args=args,
        config_path=config_path,
        policy_path=policy_path,
        config=config,
        policy=policy,
        c5_report=c5_report,
        score_audit=score_audit,
        c4_2_report=c4_2_report,
        scan_metadata=scan_metadata,
        selection_result=selection_result,
        paths=paths,
        started=started,
        finished=finished,
    )
    write_outputs(paths, rows, report)
    print(f"graph={paths['graph']}")
    print(f"report={paths['report']}")
    print(f"selected_auxiliary_edges={len(selection_result['selected'])}")
    print(f"removed_canonical_edges={len(selection_result['removed_triples'])}")
    print(f"canonical_surplus_delta={selection_result['canonical_surplus_delta']}")
    print(f"canonical_deficit_delta={selection_result['canonical_deficit_delta']}")
    print(f"acceptance_classification={report['acceptance_classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
