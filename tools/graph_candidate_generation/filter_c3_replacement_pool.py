#!/usr/bin/env python3
"""Filter and rank C3 replacement pool v1 into an eligible subset.

This script reads the frozen C3 replacement pool and writes a ranked eligible
subset. It does not generate a graph candidate and does not query WDQS.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_POOL_ROOT = Path("artifacts/frozen_candidate_pools/C3_replacement_pool_v1")
DEFAULT_SOURCE_POOL = DEFAULT_POOL_ROOT / "replacement_candidates.jsonl"
DEFAULT_SOURCE_PROFILE = DEFAULT_POOL_ROOT / "pool_profile.json"
DEFAULT_OUTPUT_DIR = DEFAULT_POOL_ROOT / "eligible_v1"

TARGET_GENERIC_RELATIONS = {"P31", "P279", "P131"}
ALLOWED_ENDPOINT_OVERLAP = {"both", "one"}
ALLOWED_ALLOCATION_STATUS = {"underfilled", "near_target"}
EVENT_PROVENANCE = {"event_bridge_triples", "event_path_triples"}
STATE_ADDED_PROVENANCE = {"state_added_core_triples", "state_added_path_triples"}
QUERY_CACHE_PROVENANCE = "state_query_cache"
ALLOWED_PROVENANCE = EVENT_PROVENANCE | STATE_ADDED_PROVENANCE | {QUERY_CACHE_PROVENANCE}
TOO_SMALL_WARNING_THRESHOLD = 100


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def candidate_has_h_r_t(row: dict[str, Any]) -> bool:
    return all(isinstance(row.get(key), str) and row.get(key) for key in ("h", "r", "t"))


def exclusion_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    relation = row.get("r")
    endpoint = row.get("endpoint_overlap_with_b0")
    status = row.get("relation_allocation_status")
    provenance = row.get("provenance_type")

    if not candidate_has_h_r_t(row):
        reasons.append("missing_or_empty_h_r_t")

    if endpoint == "none":
        reasons.append("endpoint_overlap_none")
    elif endpoint not in ALLOWED_ENDPOINT_OVERLAP:
        reasons.append("endpoint_overlap_not_allowed")

    if status == "overfilled":
        reasons.append("relation_allocation_status_overfilled")
    elif status == "unallocated":
        reasons.append("relation_allocation_status_unallocated")
    elif status not in ALLOWED_ALLOCATION_STATUS:
        reasons.append("relation_allocation_status_not_allowed")

    if row.get("is_target_generic_relation") is True:
        reasons.append("is_target_generic_relation")
    if relation in TARGET_GENERIC_RELATIONS:
        reasons.append("relation_is_P31_P279_or_P131")

    if provenance not in ALLOWED_PROVENANCE:
        reasons.append("provenance_type_not_allowed")
    elif provenance == QUERY_CACHE_PROVENANCE and not (
        status == "underfilled" and endpoint == "both"
    ):
        reasons.append("state_query_cache_policy_exclusion")

    return reasons


def base_score(row: dict[str, Any], path_group_size: int) -> int:
    score = 0
    status = row.get("relation_allocation_status")
    endpoint = row.get("endpoint_overlap_with_b0")
    provenance = row.get("provenance_type")
    relation = row.get("r")

    if status == "underfilled":
        score += 100
    if status == "near_target":
        score += 40
    if endpoint == "both":
        score += 30
    if endpoint == "one":
        score += 10
    if provenance in EVENT_PROVENANCE:
        score += 30
    if provenance in STATE_ADDED_PROVENANCE:
        score += 20
    if provenance == QUERY_CACHE_PROVENANCE:
        score -= 20
    if row.get("path_group_id") is not None and path_group_size > 1:
        score -= 50
    if relation in TARGET_GENERIC_RELATIONS:
        score -= 1000
    if status in {"overfilled", "unallocated"}:
        score -= 1000
    return score


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create eligible_v1 subset from C3 replacement pool v1."
    )
    parser.add_argument("--source-pool", type=Path, default=DEFAULT_SOURCE_POOL)
    parser.add_argument("--source-profile", type=Path, default=DEFAULT_SOURCE_PROFILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    for path in (args.source_pool, args.source_profile):
        if not path.exists():
            raise SystemExit(f"Missing required input: {path}")

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    source_pool_sha = sha256_file(args.source_pool)
    source_profile_sha = sha256_file(args.source_profile)

    total_input = 0
    excluded_reason_counts: Counter[str] = Counter()
    excluded_primary_reason_counts: Counter[str] = Counter()
    eligible_rows: list[dict[str, Any]] = []
    path_group_sizes: Counter[str] = Counter()

    with args.source_pool.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            total_input += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                excluded_reason_counts["json_decode_error"] += 1
                excluded_primary_reason_counts["json_decode_error"] += 1
                continue
            if not isinstance(row, dict):
                excluded_reason_counts["record_is_not_object"] += 1
                excluded_primary_reason_counts["record_is_not_object"] += 1
                continue
            reasons = exclusion_reasons(row)
            if reasons:
                for reason in reasons:
                    excluded_reason_counts[reason] += 1
                excluded_primary_reason_counts[reasons[0]] += 1
                continue
            row = dict(row)
            row["_source_line_number"] = line_number
            eligible_rows.append(row)
            group_id = row.get("path_group_id")
            if isinstance(group_id, str) and group_id:
                path_group_sizes[group_id] += 1

    group_scores: dict[str, int] = {}
    scored_rows: list[dict[str, Any]] = []
    for row in eligible_rows:
        group_id = row.get("path_group_id")
        group_size = path_group_sizes.get(group_id, 0) if isinstance(group_id, str) else 0
        path_group_size = group_size if group_size else 1
        score = base_score(row, path_group_size)
        row["score"] = score
        row["path_group_size"] = path_group_size
        if isinstance(group_id, str) and group_id:
            current = group_scores.get(group_id)
            group_scores[group_id] = score if current is None else min(current, score)
        else:
            row["path_group_score"] = score
        scored_rows.append(row)

    for row in scored_rows:
        group_id = row.get("path_group_id")
        if isinstance(group_id, str) and group_id:
            row["path_group_score"] = group_scores[group_id]

    scored_rows.sort(
        key=lambda row: (
            -int(row["score"]),
            str(row.get("relation_allocation_status")),
            str(row.get("endpoint_overlap_with_b0")),
            str(row.get("provenance_type")),
            str(row.get("r")),
            str(row.get("candidate_id")),
        )
    )

    eligible_path = args.output_dir / "eligible_replacement_candidates.jsonl"
    with eligible_path.open("w", encoding="utf-8") as handle:
        for row in scored_rows:
            row.pop("_source_line_number", None)
            handle.write(stable_json(row) + "\n")

    eligible_counts_by_relation = Counter(row["r"] for row in scored_rows)
    eligible_counts_by_source_stage = Counter(row["source_stage"] for row in scored_rows)
    eligible_counts_by_provenance_type = Counter(row["provenance_type"] for row in scored_rows)
    eligible_counts_by_endpoint = Counter(row["endpoint_overlap_with_b0"] for row in scored_rows)
    eligible_counts_by_status = Counter(row["relation_allocation_status"] for row in scored_rows)
    score_distribution = Counter(str(row["score"]) for row in scored_rows)
    group_size_distribution = Counter(str(size) for size in path_group_sizes.values())
    rows_with_path_group = sum(1 for row in scored_rows if row.get("path_group_id"))
    unique_path_groups = len(path_group_sizes)

    warning = None
    if len(scored_rows) < TOO_SMALL_WARNING_THRESHOLD:
        warning = (
            f"Eligible pool has fewer than {TOO_SMALL_WARNING_THRESHOLD} candidates; "
            "C3 generator design may be underconstrained."
        )

    profile = {
        "created_on": datetime.now(timezone.utc).isoformat(),
        "source_pool": {"path": args.source_pool.as_posix(), "sha256": source_pool_sha},
        "source_pool_profile": {
            "path": args.source_profile.as_posix(),
            "sha256": source_profile_sha,
        },
        "outputs": {
            "eligible_replacement_candidates": eligible_path.as_posix(),
            "eligible_pool_profile": (args.output_dir / "eligible_pool_profile.json").as_posix(),
            "eligible_hashes": (args.output_dir / "eligible_hashes.tsv").as_posix(),
        },
        "filtering_policy": {
            "hard_include": {
                "endpoint_overlap_with_b0": sorted(ALLOWED_ENDPOINT_OVERLAP),
                "relation_allocation_status": sorted(ALLOWED_ALLOCATION_STATUS),
                "is_target_generic_relation": False,
                "relation_not_in": sorted(TARGET_GENERIC_RELATIONS),
                "h_r_t_present_and_non_empty": True,
            },
            "hard_exclude": {
                "endpoint_overlap_with_b0": ["none"],
                "relation_allocation_status": ["overfilled", "unallocated"],
                "is_target_generic_relation": True,
                "relation_in": sorted(TARGET_GENERIC_RELATIONS),
            },
            "provenance_policy": {
                "kept": sorted(EVENT_PROVENANCE | STATE_ADDED_PROVENANCE),
                "state_query_cache_rule": (
                    "excluded unless relation_allocation_status == underfilled "
                    "and endpoint_overlap_with_b0 == both"
                ),
            },
            "ranking": {
                "underfilled": 100,
                "near_target": 40,
                "endpoint_both": 30,
                "endpoint_one": 10,
                "event_bridge_or_path": 30,
                "state_added_core_or_path": 20,
                "state_query_cache": -20,
                "path_group_size_greater_than_one": -50,
                "target_generic_relation": -1000,
                "overfilled_or_unallocated": -1000,
            },
        },
        "total_input_candidates": total_input,
        "total_eligible_candidates": len(scored_rows),
        "excluded_counts_by_reason": dict(sorted(excluded_reason_counts.items())),
        "excluded_counts_by_primary_reason": dict(sorted(excluded_primary_reason_counts.items())),
        "eligible_counts_by_relation": dict(sorted(eligible_counts_by_relation.items())),
        "eligible_counts_by_source_stage": dict(sorted(eligible_counts_by_source_stage.items())),
        "eligible_counts_by_provenance_type": dict(
            sorted(eligible_counts_by_provenance_type.items())
        ),
        "eligible_counts_by_endpoint_overlap_with_b0": dict(sorted(eligible_counts_by_endpoint.items())),
        "eligible_counts_by_relation_allocation_status": dict(sorted(eligible_counts_by_status.items())),
        "top_30_relations_by_eligible_count": [
            {"relation": relation, "count": count}
            for relation, count in eligible_counts_by_relation.most_common(30)
        ],
        "score_distribution": dict(sorted(score_distribution.items(), key=lambda item: int(item[0]))),
        "path_group_counts": {
            "unique_path_groups": unique_path_groups,
            "rows_with_path_group": rows_with_path_group,
            "path_group_size_distribution": dict(sorted(group_size_distribution.items())),
        },
        "warning_if_eligible_count_too_small": warning,
        "notes": [
            "This is not C3 output.",
            "No graph was generated.",
            "No live WDQS query was made.",
            "docs/reconstruction/graph_candidates.tsv was not edited.",
            "eligible_hashes.tsv omits a self-hash because a stable self-referential file hash is not feasible.",
        ],
    }

    profile_path = args.output_dir / "eligible_pool_profile.json"
    profile_path.write_text(json.dumps(profile, ensure_ascii=True, indent=2, sort_keys=True) + "\n")

    eligible_hashes_path = args.output_dir / "eligible_hashes.tsv"
    with eligible_hashes_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "sha256", "role"])
        writer.writerow([eligible_path.as_posix(), sha256_file(eligible_path), "eligible_output"])
        writer.writerow([profile_path.as_posix(), sha256_file(profile_path), "eligible_output"])
        writer.writerow([args.source_pool.as_posix(), source_pool_sha, "source_pool"])
        writer.writerow([args.source_profile.as_posix(), source_profile_sha, "source_pool_profile"])

    print(
        json.dumps(
            {
                "eligible_output_dir": args.output_dir.as_posix(),
                "eligible_candidates": len(scored_rows),
                "total_input_candidates": total_input,
                "eligible_replacement_candidates": eligible_path.as_posix(),
                "eligible_pool_profile": profile_path.as_posix(),
                "eligible_hashes": eligible_hashes_path.as_posix(),
                "warning": warning,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
