#!/usr/bin/env python3
"""Audit score/provenance fields for C5 H2 auxiliary candidates."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import load_allocation  # noqa: E402
from src.kg_pipeline.evaluation.candidate_report import sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, load_graph_triples  # noqa: E402
from tools.graph_candidate_generation.c4_search_local_cut_crossing_candidates import (  # noqa: E402
    prepare_tested_cuts,
)
from tools.graph_candidate_generation.c5_probe_h1_h2_connectivity_support import (  # noqa: E402
    classify_h2,
    greedy_non_reuse,
    load_c5_config,
)

DEFAULT_CONFIG = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/config.template.json")
DEFAULT_C5_REPORT = Path(
    "experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/"
    "c5_h1_h2_probe_report.json"
)
DEFAULT_C4_2_REPORT = Path(
    "experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/"
    "local_cut_crossing_candidate_search.json"
)
DEFAULT_OUTPUT_DIR = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only")
STAGE02_SHARDS_DIR = Path("archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards")
STAGE04_DIR = Path("archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph")
RUN_MANIFEST = Path("archive/hetzner_version/runs/prod_refine_20260315_180520/manifest.json")
PIPELINE_SCRIPT = Path("archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py")
FROZEN_POOLS_DIR = Path("artifacts/frozen_candidate_pools")

ACTUAL_SCORE_FIELD_NAMES = {
    "score",
    "final_score",
    "candidate_score",
    "genericity_score",
    "relation_score",
    "support_score",
    "quota_score",
    "bridge_score",
    "rank",
    "priority",
    "quality_score",
    "relation_need_score",
    "attachability_score",
    "component_merge_score",
    "hub_penalty",
    "shortcut_risk",
    "genericity_penalty",
    "noise_penalty",
    "first_realization_bonus",
    "path_group_score",
    "path_group_size",
}
PROVENANCE_FIELD_NAMES = {
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
    "selection_reason",
    "source_artifact",
    "source_event_type",
    "source_record_index",
    "source_sha256",
    "source_stage",
}
SCORE_PROVENANCE_FIELD_NAMES = {
    *ACTUAL_SCORE_FIELD_NAMES,
    *PROVENANCE_FIELD_NAMES,
}
NUMERIC_SCORE_FIELD_PRIORITY = (
    "score",
    "final_score",
    "candidate_score",
    "path_group_score",
    "quality_score",
    "relation_need_score",
    "bridge_score",
    "attachability_score",
    "component_merge_score",
    "genericity_score",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--c5-report", type=Path, default=DEFAULT_C5_REPORT)
    parser.add_argument("--c4-2-report", type=Path, default=DEFAULT_C4_2_REPORT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def output_paths() -> dict[str, Path]:
    return {
        "json": DEFAULT_OUTPUT_DIR / "c5_candidate_score_provenance_audit.json",
        "markdown": DEFAULT_OUTPUT_DIR / "c5_candidate_score_provenance_audit.md",
    }


def refuse_overwrite(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite C5 score audit outputs without --force: {names}")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def extract_triple(row: dict[str, Any]) -> Triple | None:
    if all(isinstance(row.get(key), str) and row.get(key) for key in ("h", "r", "t")):
        return row["h"], row["r"], row["t"]
    return None


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


def source_schema_groups() -> dict[str, list[Path]]:
    stage02_dir = resolve_path(STAGE02_SHARDS_DIR)
    stage04_dir = resolve_path(STAGE04_DIR)
    frozen_dir = resolve_path(FROZEN_POOLS_DIR)
    return {
        "stage02_candidate_shards": sorted(stage02_dir.glob("*.jsonl")) if stage02_dir.is_dir() else [],
        "stage04_core_graph": [
            path
            for path in (
                stage04_dir / "core_graph_triples.jsonl",
                stage04_dir / "core_graph_selection_log.jsonl",
            )
            if path.is_file()
        ],
        "frozen_candidate_pools": sorted(frozen_dir.rglob("*.jsonl")) if frozen_dir.is_dir() else [],
    }


def score_provenance_fields(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        lowered = key.lower()
        if (
            key in SCORE_PROVENANCE_FIELD_NAMES
            or "score" in lowered
            or "rank" in lowered
            or "priority" in lowered
            or "selection_reason" in lowered
            or key in {"source_stage", "provenance_type"}
        ):
            out[key] = value
    return out


def actual_score_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in fields.items()
        if key in ACTUAL_SCORE_FIELD_NAMES
        or "score" in key.lower()
        or "rank" in key.lower()
        or "priority" in key.lower()
    }


def provenance_only_fields(fields: dict[str, Any]) -> dict[str, Any]:
    actual = set(actual_score_fields(fields))
    return {key: value for key, value in fields.items() if key not in actual}


def numeric_score_fields(fields: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in actual_score_fields(fields).items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


def preferred_score(fields: dict[str, Any]) -> dict[str, Any] | None:
    numeric = numeric_score_fields(fields)
    for key in NUMERIC_SCORE_FIELD_PRIORITY:
        if key in numeric:
            return {"field": key, "value": numeric[key]}
    if numeric:
        key = sorted(numeric)[0]
        return {"field": key, "value": numeric[key]}
    return None


def scan_source_schemas() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for group, paths in source_schema_groups().items():
        field_counts: Counter[str] = Counter()
        score_field_counts: Counter[str] = Counter()
        actual_score_field_counts: Counter[str] = Counter()
        provenance_field_counts: Counter[str] = Counter()
        numeric_values: dict[str, list[float]] = defaultdict(list)
        rows_scanned = 0
        files_scanned = 0
        example_score_rows: list[dict[str, Any]] = []
        for path in paths:
            files_scanned += 1
            for line_number, row in iter_jsonl_rows(path):
                if row is None:
                    continue
                rows_scanned += 1
                field_counts.update(row.keys())
                score_fields = score_provenance_fields(row)
                score_field_counts.update(score_fields.keys())
                actual_score_field_counts.update(actual_score_fields(score_fields).keys())
                provenance_field_counts.update(provenance_only_fields(score_fields).keys())
                for key, value in numeric_score_fields(score_fields).items():
                    numeric_values[key].append(value)
                if score_fields and len(example_score_rows) < 5:
                    example_score_rows.append(
                        {
                            "path": repo_relative(path),
                            "line_number": line_number,
                            "fields": score_fields,
                        }
                    )
        results[group] = {
            "file_count": len(paths),
            "files_scanned": files_scanned,
            "rows_scanned": rows_scanned,
            "field_names": sorted(field_counts),
            "score_or_provenance_field_names": sorted(score_field_counts),
            "score_or_provenance_field_counts": dict(sorted(score_field_counts.items())),
            "actual_score_field_names": sorted(actual_score_field_counts),
            "actual_score_field_counts": dict(sorted(actual_score_field_counts.items())),
            "provenance_field_names": sorted(provenance_field_counts),
            "provenance_field_counts": dict(sorted(provenance_field_counts.items())),
            "numeric_score_distribution": summarize_numeric_values(numeric_values),
            "example_score_rows": example_score_rows,
        }
    return results


def summarize_numeric_values(values: dict[str, list[float]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, vals in sorted(values.items()):
        if not vals:
            continue
        out[key] = {
            "count": len(vals),
            "min": min(vals),
            "max": max(vals),
            "mean": statistics.fmean(vals),
        }
    return out


def load_stage4_triples() -> set[Triple]:
    stage04_path = resolve_path(STAGE04_DIR / "core_graph_triples.jsonl")
    triples: set[Triple] = set()
    if not stage04_path.is_file():
        return triples
    for _line_number, row in iter_jsonl_rows(stage04_path):
        if row is None:
            continue
        triple = extract_triple(row)
        if triple is not None:
            triples.add(triple)
    return triples


def build_h2_feasible_rows(config: dict[str, Any], c5_report: dict[str, Any]) -> list[dict[str, Any]]:
    parent_graph = resolve_path(config["parent_graph_path"])
    allocation_path = resolve_path(config["allocation_path"])
    graph_triples = set(load_graph_triples(parent_graph))
    entities = {node for h, _r, t in graph_triples for node in (h, t)}
    relation_counts = Counter(r for _h, r, _t in graph_triples)
    allocation = load_allocation(allocation_path)
    relation_expected = allocation["relation_expected"]
    cuts, cut_index = prepare_tested_cuts(
        graph_triples,
        entities,
        relation_counts,
        relation_expected,
        {"P31", "P279", "P131"},
        int(c5_report["limits"]["max_cuts"]),
    )
    pairs, _scan_metadata = collect_pairs_for_audit(cuts, cut_index, graph_triples, entities, int(c5_report["limits"]["max_candidates"]))
    h2_pairs = [pair for pair in pairs if pair["candidate"]["r"] not in relation_expected]
    classified = [
        classify_h2(pair, graph_triples, relation_counts, relation_expected, allocation, len(graph_triples))
        for pair in h2_pairs
    ]
    return [row for row in classified if row["classification"].startswith("feasible_h2")]


def collect_pairs_for_audit(
    cuts: list[dict[str, Any]],
    cut_index: dict[str, set[int]],
    graph_triples: set[Triple],
    entities: set[str],
    max_candidates: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Importing the C5 function directly would work, but wrapping it keeps the
    # dependency explicit for this audit.
    from tools.graph_candidate_generation.c5_probe_h1_h2_connectivity_support import collect_cut_crossing_pairs

    return collect_cut_crossing_pairs(cuts, cut_index, graph_triples, entities, max_candidates)


def load_source_rows_for_h2(h2_rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any] | None]:
    wanted: dict[Path, set[int]] = defaultdict(set)
    for row in h2_rows:
        wanted[resolve_path(row["source_path"])].add(int(row["line_number"]))

    out: dict[tuple[str, int], dict[str, Any] | None] = {}
    for path, lines in wanted.items():
        remaining = set(lines)
        for line_number, source_row in iter_jsonl_rows(path):
            if line_number not in remaining:
                continue
            out[(repo_relative(path), line_number)] = source_row
            remaining.remove(line_number)
            if not remaining:
                break
        for missing in remaining:
            out[(repo_relative(path), missing)] = None
    return out


def enrich_h2_rows(h2_rows: list[dict[str, Any]], b0_triples: set[Triple], stage4_triples: set[Triple]) -> list[dict[str, Any]]:
    source_rows = load_source_rows_for_h2(h2_rows)
    enriched: list[dict[str, Any]] = []
    for row in h2_rows:
        source_key = (row["source_path"], int(row["line_number"]))
        source_row = source_rows.get(source_key)
        fields = score_provenance_fields(source_row or {})
        scores = actual_score_fields(fields)
        provenance = provenance_only_fields(fields)
        pref_score = preferred_score(fields)
        candidate = row["candidate"]
        triple = (candidate["h"], candidate["r"], candidate["t"])
        enriched.append(
            {
                "candidate": candidate,
                "target_edge": row["target_edge"],
                "cut_id": row["cut_id"],
                "source_id": row["source_id"],
                "source_path": row["source_path"],
                "line_number": row["line_number"],
                "classification": row["classification"],
                "canonical_surplus_delta": row["canonical_surplus_delta"],
                "canonical_deficit_delta": row["canonical_deficit_delta"],
                "pattern_total_delta": row["pattern_total_delta"],
                "source_metadata_from_probe": row.get("source_metadata", {}),
                "source_row_found": source_row is not None,
                "score_or_provenance_fields": fields,
                "actual_score_fields": scores,
                "provenance_fields": provenance,
                "score_field_names": sorted(scores),
                "has_any_score_field": bool(scores),
                "has_any_score_or_provenance_field": bool(fields),
                "preferred_score": pref_score,
                "selected_into_b0": triple in b0_triples,
                "selected_by_stage4": triple in stage4_triples,
                "previously_unselected_candidate_space": triple not in b0_triples and triple not in stage4_triples,
            }
        )
    return enriched


def source_category(row: dict[str, Any]) -> str:
    if row["source_id"] == "stage02_candidate_shards":
        return "stage02_candidate_shards"
    if row["source_id"] == "frozen_candidate_pools":
        return "frozen_candidate_pools"
    if row["source_id"] in {"stage11_graph_output", "stage12_graph_output"}:
        return row["source_id"]
    return "other"


def aggregate_h2(enriched: list[dict[str, Any]], greedy_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(enriched)
    with_score = [row for row in enriched if row["has_any_score_field"]]
    with_score_or_prov = [row for row in enriched if row["has_any_score_or_provenance_field"]]
    selected_stage4 = [row for row in enriched if row["selected_by_stage4"]]
    selected_b0 = [row for row in enriched if row["selected_into_b0"]]
    previously_unselected = [row for row in enriched if row["previously_unselected_candidate_space"]]

    fields = Counter()
    actual_fields = Counter()
    provenance_fields = Counter()
    numeric_values_by_source: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    source_counts = Counter()
    source_with_score = Counter()
    for row in enriched:
        category = source_category(row)
        source_counts[category] += 1
        if row["has_any_score_field"]:
            source_with_score[category] += 1
        fields.update(row["score_or_provenance_fields"].keys())
        actual_fields.update(row["actual_score_fields"].keys())
        provenance_fields.update(row["provenance_fields"].keys())
        for key, value in numeric_score_fields(row["score_or_provenance_fields"]).items():
            numeric_values_by_source[category][key].append(value)

    top_by_score = [
        row
        for row in sorted(
            (r for r in enriched if r["preferred_score"] is not None),
            key=lambda r: (-float(r["preferred_score"]["value"]), r["source_id"], r["candidate"]["r"]),
        )
    ][:25]

    greedy_keys = {
        (
            row["source_path"],
            int(row["line_number"]),
            row["cut_id"],
            row["candidate"]["h"],
            row["candidate"]["r"],
            row["candidate"]["t"],
        )
        for row in greedy_rows
    }
    greedy_enriched = [
        row
        for row in enriched
        if (
            row["source_path"],
            int(row["line_number"]),
            row["cut_id"],
            row["candidate"]["h"],
            row["candidate"]["r"],
            row["candidate"]["t"],
        )
        in greedy_keys
    ]

    return {
        "total_h2_feasible_candidate_cut_pairs": total,
        "h2_pairs_with_any_numeric_score_field": len(with_score),
        "h2_pairs_without_numeric_score_field": total - len(with_score),
        "h2_pairs_with_any_score_or_provenance_field": len(with_score_or_prov),
        "score_or_provenance_field_names_found": sorted(fields),
        "score_or_provenance_field_counts": dict(sorted(fields.items())),
        "actual_score_field_names_found": sorted(actual_fields),
        "actual_score_field_counts": dict(sorted(actual_fields.items())),
        "provenance_field_names_found": sorted(provenance_fields),
        "provenance_field_counts": dict(sorted(provenance_fields.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "source_counts_with_numeric_score": dict(sorted(source_with_score.items())),
        "numeric_score_distribution_by_source": {
            source: summarize_numeric_values(values) for source, values in sorted(numeric_values_by_source.items())
        },
        "selected_into_b0_count": len(selected_b0),
        "selected_by_stage4_count": len(selected_stage4),
        "previously_unselected_candidate_space_count": len(previously_unselected),
        "top_h2_candidates_by_available_score": compact_enriched(top_by_score),
        "top_h2_greedy_candidates_with_score_provenance": compact_enriched(greedy_enriched[:25]),
        "greedy_h2_candidates_with_any_numeric_score_field": sum(1 for row in greedy_enriched if row["has_any_score_field"]),
        "greedy_h2_candidates_without_numeric_score_field": len(greedy_enriched)
        - sum(1 for row in greedy_enriched if row["has_any_score_field"]),
    }


def compact_enriched(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        out.append(
            {
                "candidate": row["candidate"],
                "target_edge": row["target_edge"],
                "cut_id": row["cut_id"],
                "source_id": row["source_id"],
                "source_path": row["source_path"],
                "line_number": row["line_number"],
                "canonical_surplus_delta": row["canonical_surplus_delta"],
                "canonical_deficit_delta": row["canonical_deficit_delta"],
                "preferred_score": row["preferred_score"],
                "actual_score_fields": row["actual_score_fields"],
                "provenance_fields": row["provenance_fields"],
                "score_or_provenance_fields": row["score_or_provenance_fields"],
                "selected_by_stage4": row["selected_by_stage4"],
                "selected_into_b0": row["selected_into_b0"],
                "previously_unselected_candidate_space": row["previously_unselected_candidate_space"],
            }
        )
    return out


def score_semantics_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    pipeline_path = resolve_path(PIPELINE_SCRIPT)
    if pipeline_path.is_file():
        lines = pipeline_path.read_text(encoding="utf-8").splitlines()
        hits = []
        for idx, line in enumerate(lines, start=1):
            if any(token in line for token in ("def score_genericity", "def quality_score", "def candidate_total_score")):
                hits.append({"line": idx, "text": line.strip()})
        evidence["pipeline_script"] = {
            "path": repo_relative(pipeline_path),
            "sha256": sha256_file(pipeline_path),
            "score_function_references": hits,
        }
    manifest_path = resolve_path(RUN_MANIFEST)
    if manifest_path.is_file():
        evidence["run_manifest"] = {
            "path": repo_relative(manifest_path),
            "sha256": sha256_file(manifest_path),
        }
    return evidence


def classify_reuse(aggregate: dict[str, Any], schema_scan: dict[str, Any]) -> str:
    total = aggregate["total_h2_feasible_candidate_cut_pairs"]
    with_score = aggregate["h2_pairs_with_any_numeric_score_field"]
    if with_score > 0:
        if with_score == total and total > 0:
            return "score_semantics_unclear"
        return "partial_score_available"
    return "no_score_for_h2_candidates"


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    config_path = resolve_path(args.config)
    c5_report_path = resolve_path(args.c5_report)
    c4_2_report_path = resolve_path(args.c4_2_report)
    config = load_c5_config(config_path)
    c5_report = load_json(c5_report_path)
    c4_2_report = load_json(c4_2_report_path)

    parent_graph = resolve_path(config["parent_graph_path"])
    b0_triples = set(load_graph_triples(parent_graph))
    stage4_triples = load_stage4_triples()
    schema_scan = scan_source_schemas()
    h2_rows = build_h2_feasible_rows(config, c5_report)
    enriched = enrich_h2_rows(h2_rows, b0_triples, stage4_triples)
    greedy = greedy_non_reuse(h2_rows)["examples"]
    aggregate = aggregate_h2(enriched, greedy)
    reuse = classify_reuse(aggregate, schema_scan)
    finished = time.time()

    return {
        "schema_version": "c5-candidate-score-provenance-audit-v1",
        "audit_id": "C5_1_H2_candidate_score_provenance_audit",
        "status": "read_only_score_provenance_audit",
        "inputs": {
            "config": {"path": repo_relative(config_path), "sha256": sha256_file(config_path)},
            "c5_h1_h2_probe_report": {
                "path": repo_relative(c5_report_path),
                "sha256": sha256_file(c5_report_path),
                "h2_summary": c5_report.get("h2_summary"),
                "greedy_h2_upper_bound": {
                    key: value
                    for key, value in c5_report.get("greedy_h2_upper_bound", {}).items()
                    if key != "examples"
                },
            },
            "c4_2_local_cut_crossing_search": {
                "path": repo_relative(c4_2_report_path),
                "sha256": sha256_file(c4_2_report_path),
                "aggregate_counts": c4_2_report.get("aggregate_counts"),
            },
            "parent_graph": {"path": config["parent_graph_path"], "sha256": sha256_file(parent_graph)},
        },
        "source_schema_scan": schema_scan,
        "score_semantics_evidence": score_semantics_evidence(),
        "h2_candidate_score_audit": aggregate,
        "stage4_selection_context": {
            "stage4_core_graph_triples": len(stage4_triples),
            "h2_candidates_selected_by_stage4": aggregate["selected_by_stage4_count"],
            "h2_candidates_selected_into_b0": aggregate["selected_into_b0_count"],
            "h2_candidates_from_previously_unselected_candidate_space": aggregate[
                "previously_unselected_candidate_space_count"
            ],
        },
        "score_reuse_assessment": {
            "classification": reuse,
            "safe_to_rank_c5_h2_by_old_score": False,
            "reason": score_reuse_reason(reuse, aggregate),
        },
        "notes": [
            "Read-only audit; no graph candidate was generated.",
            "No WDQS query was made.",
            "No LLM call was made.",
            "candidate_registry.v1.json was not updated.",
            "H2 auxiliary candidates are observed unallocated triples and must remain separately accounted.",
        ],
        "runtime": {
            "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
            "elapsed_seconds": round(finished - started, 6),
        },
    }


def score_reuse_reason(classification: str, aggregate: dict[str, Any]) -> str:
    if classification == "partial_score_available":
        return (
            "Some H2 source rows expose numeric score fields, but field coverage is partial and mixes C3 pool "
            "score/provenance with historical Stage2 scoring semantics."
        )
    if classification == "score_semantics_unclear":
        return (
            "Historical scoring fields exist, but their semantics were designed for Stage2/Stage4 construction or "
            "C3 pool filtering rather than C5 auxiliary bridge support."
        )
    if classification == "no_score_for_h2_candidates":
        return (
            "The H2 candidates do not expose old Phase II numeric score fields in their source rows. "
            "They expose provenance fields such as duplicate_provenance_count, source_stage, and provenance_type."
        )
    return f"Score reuse classification {classification!r} requires manual review."


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    h2 = report["h2_candidate_score_audit"]
    reuse = report["score_reuse_assessment"]
    lines = [
        "# C5.1 Candidate Score Provenance Audit",
        "",
        "Status: read-only score/provenance audit. No graph candidate was generated.",
        "",
        "## H2 Score Coverage",
        "",
        f"- H2 feasible candidate-cut pairs: `{h2['total_h2_feasible_candidate_cut_pairs']}`",
        f"- H2 pairs with old Phase II numeric score fields: `{h2['h2_pairs_with_any_numeric_score_field']}`",
        f"- H2 pairs without old Phase II numeric score fields: `{h2['h2_pairs_without_numeric_score_field']}`",
        f"- H2 pairs with score or provenance fields: `{h2['h2_pairs_with_any_score_or_provenance_field']}`",
        f"- H2 pairs selected by Stage4: `{h2['selected_by_stage4_count']}`",
        f"- H2 pairs selected into B0: `{h2['selected_into_b0_count']}`",
        f"- H2 pairs from previously unselected candidate space: `{h2['previously_unselected_candidate_space_count']}`",
        "",
        "## Score And Provenance Fields Found",
        "",
    ]
    if h2["score_or_provenance_field_names_found"]:
        lines.extend(["| Field | Count |", "| --- | ---: |"])
        for field, count in h2["score_or_provenance_field_counts"].items():
            lines.append(f"| `{field}` | {count} |")
    else:
        lines.append("No score or provenance fields were found on H2 source rows.")

    lines.extend(
        [
            "",
            "## Source Counts",
            "",
            "| Source | H2 Pairs | H2 Pairs With Numeric Score |",
            "| --- | ---: | ---: |",
        ]
    )
    for source, count in h2["source_counts"].items():
        lines.append(f"| `{source}` | {count} | {h2['source_counts_with_numeric_score'].get(source, 0)} |")

    lines.extend(
        [
            "",
            "## Reuse Assessment",
            "",
            f"- Classification: `{reuse['classification']}`",
            f"- Safe to rank C5-H2 by old score: `{reuse['safe_to_rank_c5_h2_by_old_score']}`",
            f"- Reason: {reuse['reason']}",
            "",
            "Old Phase II scores should not be used as the primary C5-H2 ranking criterion. Existing fields are "
            "useful provenance, but C5-H2 needs bridge-cut support, auxiliary-edge accounting, "
            "relation-allocation separation, duplicate-provenance handling, and pruning benefit as explicit ranking "
            "factors.",
            "",
            "## Notes",
            "",
            "- No WDQS query was made.",
            "- No LLM call was made.",
            "- No graph candidate was generated.",
            "- `candidate_registry.v1.json` was not updated.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    paths = output_paths()
    refuse_overwrite(paths, args.force)
    report = run_audit(args)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(paths["markdown"], report)
    h2 = report["h2_candidate_score_audit"]
    print(f"audit_json={paths['json']}")
    print(f"audit_markdown={paths['markdown']}")
    print(f"total_h2_feasible_candidate_cut_pairs={h2['total_h2_feasible_candidate_cut_pairs']}")
    print(f"h2_pairs_with_old_phase2_numeric_score_field={h2['h2_pairs_with_any_numeric_score_field']}")
    print(f"h2_pairs_without_old_phase2_numeric_score_field={h2['h2_pairs_without_numeric_score_field']}")
    print(f"score_reuse_classification={report['score_reuse_assessment']['classification']}")
    print(f"safe_to_rank_c5_h2_by_old_score={report['score_reuse_assessment']['safe_to_rank_c5_h2_by_old_score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
