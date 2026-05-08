#!/usr/bin/env python3
"""Build a frozen local replacement pool for the planned C3 experiment.

This script reads only local Stage11/Stage12 repair evidence. It does not
query WDQS and does not generate a graph candidate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_OUTPUT_DIR = Path("artifacts/frozen_candidate_pools/C3_replacement_pool_v1")
DEFAULT_B0 = Path(
    "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/"
    "stage12_path_repair_prod/largest_component.csv"
)
DEFAULT_ALLOCATION = Path("src/Pruning graph/bidirectional_allocation_results5k.json")
EXPECTED_B0_SHA256 = "c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9"
EXPECTED_ALLOCATION_SHA256 = "a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb"

SOURCE_SPECS = [
    {
        "stage": "stage11",
        "kind": "events",
        "path": Path("src/Pruning graph/stage11_eta_aware_connectivity_repair_full/events.jsonl"),
    },
    {
        "stage": "stage11",
        "kind": "state",
        "path": Path("src/Pruning graph/stage11_eta_aware_connectivity_repair_full/state.json"),
    },
    {
        "stage": "stage12",
        "kind": "events",
        "path": Path(
            "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/"
            "stage12_path_repair_prod/events.jsonl"
        ),
    },
    {
        "stage": "stage12",
        "kind": "state",
        "path": Path(
            "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/"
            "stage12_path_repair_prod/state.json"
        ),
    },
]

TARGET_GENERIC_RELATIONS = {"P31", "P279", "P131"}
EVENT_RANK = {
    "path_applied": 0,
    "core_bridge_added": 0,
    "path_selected": 1,
    "core_bridge_selected": 1,
    "candidate_classified": 2,
    "candidate_found": 3,
    "candidate_saved_noncore": 4,
}
PROVENANCE_RANK = {
    "state_added_path_triples": 0,
    "state_added_core_triples": 0,
    "event_path_triples": 1,
    "event_bridge_triples": 1,
    "state_query_cache": 3,
}
STAGE_RANK = {"stage12": 0, "stage11": 1}


@dataclass(frozen=True)
class ExtractedCandidate:
    source_artifact: str
    source_sha256: str
    source_stage: str
    provenance_type: str
    source_record_index: int
    source_event_type: str | None
    classification_label: str | None
    accepted: bool | None
    h: str
    r: str
    t: str
    path_role: str
    path_group_id: str | None
    query_hash: str | None
    notes: dict[str, Any]
    rank: tuple[Any, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(parts: Iterable[Any], length: int | None = None) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\0")
    value = digest.hexdigest()
    return value[:length] if length else value


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def is_triple(value: Any) -> bool:
    if isinstance(value, dict):
        return all(isinstance(value.get(key), str) and value.get(key) for key in ("h", "r", "t"))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return all(isinstance(value[index], str) and value[index] for index in range(3))
    return False


def normalize_triple(value: Any) -> tuple[str, str, str] | None:
    if isinstance(value, dict) and is_triple(value):
        return value["h"], value["r"], value["t"]
    if isinstance(value, (list, tuple)) and is_triple(value):
        return value[0], value[1], value[2]
    return None


def accepted_value(record: dict[str, Any]) -> bool | None:
    for key in ("accepted_into_core", "accepted_into_graph", "acceptance_decision"):
        if key in record and isinstance(record[key], bool):
            return record[key]
    return None


def candidate_rank(
    source_stage: str,
    provenance_type: str,
    source_order: int,
    source_record_index: int,
    triple_index: int,
    event_type: str | None,
    accepted: bool | None,
) -> tuple[Any, ...]:
    accepted_rank = 0 if accepted is True else 1 if accepted is False else 2
    event_rank = EVENT_RANK.get(event_type or "", 5)
    provenance_rank = PROVENANCE_RANK.get(provenance_type, 9)
    stage_rank = STAGE_RANK.get(source_stage, 9)
    return (
        accepted_rank,
        event_rank,
        provenance_rank,
        stage_rank,
        source_order,
        source_record_index,
        triple_index,
    )


def read_b0_graph(path: Path) -> tuple[set[tuple[str, str, str]], set[str], Counter[str]]:
    triples: set[tuple[str, str, str]] = set()
    entities: set[str] = set()
    relation_counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"h", "r", "t"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"B0 CSV must contain h,r,t columns: {path}")
        for row in reader:
            h, r, t = row["h"], row["r"], row["t"]
            triple = (h, r, t)
            if triple in triples:
                continue
            triples.add(triple)
            entities.add(h)
            entities.add(t)
            relation_counts[r] += 1
    return triples, entities, relation_counts


def load_allocation(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    allocations = data.get("allocations")
    if not isinstance(allocations, list):
        raise ValueError(f"Allocation JSON has no top-level allocations list: {path}")
    eta_by_relation: dict[str, int] = {}
    for row in allocations:
        if not isinstance(row, dict):
            continue
        relation = row.get("relation")
        if not isinstance(relation, str) or not relation:
            continue
        eta_value = None
        for key in ("eta_integer", "eta", "eta_expected"):
            if key in row and row[key] is not None:
                eta_value = row[key]
                break
        if eta_value is None:
            continue
        eta_by_relation[relation] = int(round(float(eta_value)))
    return eta_by_relation


def relation_status(relation: str, eta_by_relation: dict[str, int], b0_counts: Counter[str]) -> str:
    if relation not in eta_by_relation:
        return "unallocated"
    observed = b0_counts.get(relation, 0)
    expected = eta_by_relation[relation]
    if observed < expected:
        return "underfilled"
    if observed == expected:
        return "near_target"
    return "overfilled"


def endpoint_overlap(h: str, t: str, b0_entities: set[str]) -> str:
    overlap = int(h in b0_entities) + int(t in b0_entities)
    if overlap == 2:
        return "both"
    if overlap == 1:
        return "one"
    return "none"


def extract_from_events(
    path: Path,
    source_sha: str,
    source_stage: str,
    source_order: int,
    skipped: list[dict[str, Any]],
    source_record_counts: Counter[str],
) -> list[ExtractedCandidate]:
    candidates: list[ExtractedCandidate] = []
    relpath = path.as_posix()
    with path.open("r", encoding="utf-8") as handle:
        for record_index, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            source_record_counts[relpath] += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                skipped.append(
                    {
                        "source_artifact": relpath,
                        "field": "jsonl_record",
                        "source_record_index": record_index,
                        "reason": f"json_decode_error:{exc}",
                    }
                )
                continue
            if not isinstance(record, dict):
                skipped.append(
                    {
                        "source_artifact": relpath,
                        "field": "jsonl_record",
                        "source_record_index": record_index,
                        "reason": "record_is_not_object",
                    }
                )
                continue

            for field, provenance_type, path_role in (
                ("bridge_triples", "event_bridge_triples", "bridge_edge"),
                ("path_triples", "event_path_triples", "path_edge"),
            ):
                if field not in record:
                    continue
                triples_value = record[field]
                if not isinstance(triples_value, list):
                    skipped.append(
                        {
                            "source_artifact": relpath,
                            "field": field,
                            "source_record_index": record_index,
                            "reason": "field_is_not_list",
                        }
                    )
                    continue
                normalized = [normalize_triple(item) for item in triples_value]
                if any(item is None for item in normalized):
                    skipped.append(
                        {
                            "source_artifact": relpath,
                            "field": field,
                            "source_record_index": record_index,
                            "reason": "one_or_more_items_are_not_h/r/t_triples",
                        }
                    )
                    continue
                group_id = None
                if field == "path_triples":
                    group_id = "pg_" + stable_hash(
                        [relpath, record_index, field, stable_json(triples_value)], 24
                    )
                event_type = record.get("event_type")
                accepted = accepted_value(record)
                for triple_index, triple in enumerate(normalized):
                    assert triple is not None
                    h, r, t = triple
                    candidates.append(
                        ExtractedCandidate(
                            source_artifact=relpath,
                            source_sha256=source_sha,
                            source_stage=source_stage,
                            provenance_type=provenance_type,
                            source_record_index=record_index,
                            source_event_type=event_type if isinstance(event_type, str) else None,
                            classification_label=record.get("classification_label")
                            if isinstance(record.get("classification_label"), str)
                            else None,
                            accepted=accepted,
                            h=h,
                            r=r,
                            t=t,
                            path_role=path_role,
                            path_group_id=group_id,
                            query_hash=record.get("query_hash")
                            if isinstance(record.get("query_hash"), str)
                            else record.get("wdqs_query_hash")
                            if isinstance(record.get("wdqs_query_hash"), str)
                            else None,
                            notes={
                                "source_field": field,
                                "path_length": len(normalized),
                                "component_rank": record.get("component_rank"),
                                "anchor_node": record.get("anchor_node"),
                                "target_main_node": record.get("target_main_node"),
                                "relation_deficit_gain": record.get("relation_deficit_gain"),
                                "acceptance_reason": record.get("acceptance_reason"),
                            },
                            rank=candidate_rank(
                                source_stage,
                                provenance_type,
                                source_order,
                                record_index,
                                triple_index,
                                event_type if isinstance(event_type, str) else None,
                                accepted,
                            ),
                        )
                    )
    return candidates


def extract_list_field(
    data: dict[str, Any],
    path: Path,
    source_sha: str,
    source_stage: str,
    source_order: int,
    field: str,
    provenance_type: str,
    path_role: str,
    skipped: list[dict[str, Any]],
    source_record_counts: Counter[str],
) -> list[ExtractedCandidate]:
    relpath = path.as_posix()
    value = data.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        skipped.append(
            {
                "source_artifact": relpath,
                "field": field,
                "source_record_index": None,
                "reason": "field_is_not_list",
            }
        )
        return []
    candidates: list[ExtractedCandidate] = []
    for index, item in enumerate(value, start=1):
        source_record_counts[f"{relpath}:{field}"] += 1
        triple = normalize_triple(item)
        if triple is None:
            skipped.append(
                {
                    "source_artifact": relpath,
                    "field": field,
                    "source_record_index": index,
                    "reason": "item_is_not_h/r/t_triple",
                }
            )
            continue
        h, r, t = triple
        candidates.append(
            ExtractedCandidate(
                source_artifact=relpath,
                source_sha256=source_sha,
                source_stage=source_stage,
                provenance_type=provenance_type,
                source_record_index=index,
                source_event_type=None,
                classification_label=None,
                accepted=True,
                h=h,
                r=r,
                t=t,
                path_role=path_role,
                path_group_id=None,
                query_hash=None,
                notes={"source_field": field},
                rank=candidate_rank(
                    source_stage,
                    provenance_type,
                    source_order,
                    index,
                    0,
                    None,
                    True,
                ),
            )
        )
    return candidates


def extract_query_cache(
    data: dict[str, Any],
    path: Path,
    source_sha: str,
    source_stage: str,
    source_order: int,
    skipped: list[dict[str, Any]],
    source_record_counts: Counter[str],
) -> list[ExtractedCandidate]:
    relpath = path.as_posix()
    query_cache = data.get("query_cache")
    if query_cache is None:
        return []
    if not isinstance(query_cache, dict):
        skipped.append(
            {
                "source_artifact": relpath,
                "field": "query_cache",
                "source_record_index": None,
                "reason": "field_is_not_object",
            }
        )
        return []
    candidates: list[ExtractedCandidate] = []
    source_record_index = 0
    for cache_key in sorted(query_cache):
        values = query_cache[cache_key]
        source_record_counts[f"{relpath}:query_cache"] += 1
        if not isinstance(values, list):
            skipped.append(
                {
                    "source_artifact": relpath,
                    "field": "query_cache",
                    "source_record_index": cache_key,
                    "reason": "cache_value_is_not_list",
                }
            )
            continue
        for triple_index, item in enumerate(values):
            source_record_index += 1
            triple = normalize_triple(item)
            if triple is None:
                skipped.append(
                    {
                        "source_artifact": relpath,
                        "field": "query_cache",
                        "source_record_index": cache_key,
                        "reason": "cache_item_is_not_h/r/t_triple",
                    }
                )
                continue
            h, r, t = triple
            candidates.append(
                ExtractedCandidate(
                    source_artifact=relpath,
                    source_sha256=source_sha,
                    source_stage=source_stage,
                    provenance_type="state_query_cache",
                    source_record_index=source_record_index,
                    source_event_type=None,
                    classification_label=None,
                    accepted=None,
                    h=h,
                    r=r,
                    t=t,
                    path_role="query_cache_edge",
                    path_group_id=None,
                    query_hash=None,
                    notes={"source_field": "query_cache", "cache_key": cache_key},
                    rank=candidate_rank(
                        source_stage,
                        "state_query_cache",
                        source_order,
                        source_record_index,
                        triple_index,
                        None,
                        None,
                    ),
                )
            )
    return candidates


def extract_from_state(
    path: Path,
    source_sha: str,
    source_stage: str,
    source_order: int,
    skipped: list[dict[str, Any]],
    source_record_counts: Counter[str],
) -> list[ExtractedCandidate]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        skipped.append(
            {
                "source_artifact": path.as_posix(),
                "field": "state",
                "source_record_index": None,
                "reason": "state_json_is_not_object",
            }
        )
        return []

    candidates: list[ExtractedCandidate] = []
    if source_stage == "stage11":
        candidates.extend(
            extract_list_field(
                data,
                path,
                source_sha,
                source_stage,
                source_order,
                "added_core_triples",
                "state_added_core_triples",
                "bridge_edge",
                skipped,
                source_record_counts,
            )
        )
    if source_stage == "stage12":
        candidates.extend(
            extract_list_field(
                data,
                path,
                source_sha,
                source_stage,
                source_order,
                "added_path_triples",
                "state_added_path_triples",
                "path_edge",
                skipped,
                source_record_counts,
            )
        )
    candidates.extend(
        extract_query_cache(
            data, path, source_sha, source_stage, source_order, skipped, source_record_counts
        )
    )
    return candidates


def candidate_to_output(
    candidate_id: str,
    candidate: ExtractedCandidate,
    b0_entities: set[str],
    eta_by_relation: dict[str, int],
    b0_relation_counts: Counter[str],
    duplicate_provenance_count: int,
) -> dict[str, Any]:
    return {
        "source_artifact": candidate.source_artifact,
        "source_sha256": candidate.source_sha256,
        "candidate_id": candidate_id,
        "h": candidate.h,
        "r": candidate.r,
        "t": candidate.t,
        "path_role": candidate.path_role,
        "path_group_id": candidate.path_group_id,
        "source_stage": candidate.source_stage,
        "provenance_type": candidate.provenance_type,
        "source_record_index": candidate.source_record_index,
        "source_event_type": candidate.source_event_type,
        "classification_label": candidate.classification_label,
        "accepted": candidate.accepted,
        "query_hash": candidate.query_hash,
        "in_b0": False,
        "endpoint_overlap_with_b0": endpoint_overlap(candidate.h, candidate.t, b0_entities),
        "relation_allocation_status": relation_status(
            candidate.r, eta_by_relation, b0_relation_counts
        ),
        "is_target_generic_relation": candidate.r in TARGET_GENERIC_RELATIONS,
        "is_primary_source": True,
        "duplicate_provenance_count": duplicate_provenance_count,
        "notes": candidate.notes,
    }


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build C3_replacement_pool_v1 from frozen Stage11/Stage12 evidence."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--b0-graph", type=Path, default=DEFAULT_B0)
    parser.add_argument("--allocation", type=Path, default=DEFAULT_ALLOCATION)
    parser.add_argument("--expected-b0-sha256", default=EXPECTED_B0_SHA256)
    parser.add_argument("--expected-allocation-sha256", default=EXPECTED_ALLOCATION_SHA256)
    args = parser.parse_args()

    output_dir: Path = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    for path in [args.b0_graph, args.allocation, *(spec["path"] for spec in SOURCE_SPECS)]:
        if not path.exists():
            raise SystemExit(f"Missing required input: {path}")

    b0_sha = sha256_file(args.b0_graph)
    allocation_sha = sha256_file(args.allocation)
    if b0_sha != args.expected_b0_sha256:
        raise SystemExit(
            f"B0 SHA256 mismatch: expected {args.expected_b0_sha256}, observed {b0_sha}"
        )
    if allocation_sha != args.expected_allocation_sha256:
        raise SystemExit(
            "Allocation SHA256 mismatch: "
            f"expected {args.expected_allocation_sha256}, observed {allocation_sha}"
        )

    created_on = datetime.now(timezone.utc).isoformat()
    b0_triples, b0_entities, b0_relation_counts = read_b0_graph(args.b0_graph)
    eta_by_relation = load_allocation(args.allocation)
    source_hashes = {spec["path"].as_posix(): sha256_file(spec["path"]) for spec in SOURCE_SPECS}

    skipped: list[dict[str, Any]] = []
    source_record_counts: Counter[str] = Counter()
    raw_candidates: list[ExtractedCandidate] = []
    for source_order, spec in enumerate(SOURCE_SPECS):
        path = spec["path"]
        if spec["kind"] == "events":
            raw_candidates.extend(
                extract_from_events(
                    path,
                    source_hashes[path.as_posix()],
                    spec["stage"],
                    source_order,
                    skipped,
                    source_record_counts,
                )
            )
        elif spec["kind"] == "state":
            raw_candidates.extend(
                extract_from_state(
                    path,
                    source_hashes[path.as_posix()],
                    spec["stage"],
                    source_order,
                    skipped,
                    source_record_counts,
                )
            )
        else:
            skipped.append(
                {
                    "source_artifact": path.as_posix(),
                    "field": spec["kind"],
                    "source_record_index": None,
                    "reason": "unknown_source_kind",
                }
            )

    raw_triples = [(candidate.h, candidate.r, candidate.t) for candidate in raw_candidates]
    unique_before_b0 = set(raw_triples)
    excluded_b0 = {triple for triple in unique_before_b0 if triple in b0_triples}

    best_by_triple: dict[tuple[str, str, str], ExtractedCandidate] = {}
    provenance_counts: Counter[tuple[str, str, str]] = Counter()
    for candidate in raw_candidates:
        triple = (candidate.h, candidate.r, candidate.t)
        provenance_counts[triple] += 1
        if triple in b0_triples:
            continue
        previous = best_by_triple.get(triple)
        if previous is None or candidate.rank < previous.rank:
            best_by_triple[triple] = candidate

    output_records: list[dict[str, Any]] = []
    for triple, candidate in best_by_triple.items():
        candidate_id = "c3poolv1_" + stable_hash(triple, 24)
        output_records.append(
            candidate_to_output(
                candidate_id,
                candidate,
                b0_entities,
                eta_by_relation,
                b0_relation_counts,
                provenance_counts[triple],
            )
        )
    output_records.sort(key=lambda row: row["candidate_id"])

    candidates_path = output_dir / "replacement_candidates.jsonl"
    with candidates_path.open("w", encoding="utf-8") as handle:
        for row in output_records:
            handle.write(stable_json(row) + "\n")

    counts_by_source_stage = Counter(row["source_stage"] for row in output_records)
    counts_by_provenance_type = Counter(row["provenance_type"] for row in output_records)
    counts_by_relation = Counter(row["r"] for row in output_records)
    counts_by_endpoint = Counter(row["endpoint_overlap_with_b0"] for row in output_records)
    counts_by_allocation_status = Counter(row["relation_allocation_status"] for row in output_records)
    path_group_count = len({row["path_group_id"] for row in output_records if row["path_group_id"]})
    target_generic_count = sum(1 for row in output_records if row["is_target_generic_relation"])

    profile = {
        "created_on": created_on,
        "source_paths_and_hashes": [
            {
                "path": spec["path"].as_posix(),
                "source_stage": spec["stage"],
                "kind": spec["kind"],
                "sha256": source_hashes[spec["path"].as_posix()],
            }
            for spec in SOURCE_SPECS
        ],
        "b0_graph": {"path": args.b0_graph.as_posix(), "sha256": b0_sha},
        "allocation": {"path": args.allocation.as_posix(), "sha256": allocation_sha},
        "total_source_records_inspected": int(sum(source_record_counts.values())),
        "source_records_inspected_by_source_or_field": dict(sorted(source_record_counts.items())),
        "raw_candidate_triples_extracted": len(raw_candidates),
        "unique_candidate_triples_before_b0_exclusion": len(unique_before_b0),
        "candidates_excluded_because_already_in_b0": len(excluded_b0),
        "final_candidate_count": len(output_records),
        "counts_by_source_stage": dict(sorted(counts_by_source_stage.items())),
        "counts_by_provenance_type": dict(sorted(counts_by_provenance_type.items())),
        "counts_by_relation": dict(sorted(counts_by_relation.items())),
        "counts_by_endpoint_overlap_with_b0": dict(sorted(counts_by_endpoint.items())),
        "counts_by_relation_allocation_status": dict(sorted(counts_by_allocation_status.items())),
        "target_generic_relation_count": target_generic_count,
        "path_group_count": path_group_count,
        "skipped_sources_or_fields": skipped,
        "policy_notes": [
            "Trial9 excluded from v1.",
            "Live WDQS excluded.",
            "Only local Stage11/Stage12 events/state evidence used.",
            "Candidates already present in B0 excluded.",
            "No graph generation performed.",
            "relation_allocation_status is computed against B0 relation counts and canonical 5k eta: underfilled if observed < eta, near_target if observed == eta, overfilled if observed > eta, unallocated if absent from allocation.",
        ],
    }

    profile_path = output_dir / "pool_profile.json"
    write_json(profile_path, profile)

    source_manifest = {
        "created_on": created_on,
        "pool_id": "C3_replacement_pool_v1",
        "extraction_script_path": "tools/graph_candidate_generation/build_c3_replacement_pool.py",
        "extraction_command": " ".join([sys.executable, *sys.argv]),
        "source_files": [
            {
                "path": spec["path"].as_posix(),
                "source_stage": spec["stage"],
                "kind": spec["kind"],
                "sha256": source_hashes[spec["path"].as_posix()],
            }
            for spec in SOURCE_SPECS
        ],
        "b0_graph": {"path": args.b0_graph.as_posix(), "sha256": b0_sha},
        "allocation": {"path": args.allocation.as_posix(), "sha256": allocation_sha},
        "outputs": {
            "replacement_candidates": candidates_path.as_posix(),
            "pool_profile": profile_path.as_posix(),
            "hashes": (output_dir / "hashes.tsv").as_posix(),
        },
        "policy_decisions": {
            "trial9_excluded": True,
            "live_wdqs_excluded": True,
            "candidates_already_present_in_b0_excluded": True,
            "stage11_stage12_only": True,
            "no_graph_generation_performed": True,
            "raw_stage11_stage12_files_not_used_as_generator_inputs": True,
        },
    }
    manifest_path = output_dir / "source_manifest.json"
    write_json(manifest_path, source_manifest)

    output_hashes = {
        manifest_path.as_posix(): sha256_file(manifest_path),
        candidates_path.as_posix(): sha256_file(candidates_path),
        profile_path.as_posix(): sha256_file(profile_path),
    }
    hashes_path = output_dir / "hashes.tsv"
    with hashes_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "sha256", "role"])
        for path, digest in sorted(output_hashes.items()):
            writer.writerow([path, digest, "pool_output"])
        for source_path, digest in sorted(source_hashes.items()):
            writer.writerow([source_path, digest, "source_artifact"])
        writer.writerow([args.b0_graph.as_posix(), b0_sha, "b0_graph"])
        writer.writerow([args.allocation.as_posix(), allocation_sha, "allocation"])

    print(
        json.dumps(
            {
                "output_dir": output_dir.as_posix(),
                "replacement_candidates": candidates_path.as_posix(),
                "source_manifest": manifest_path.as_posix(),
                "pool_profile": profile_path.as_posix(),
                "hashes": hashes_path.as_posix(),
                "raw_candidate_triples_extracted": len(raw_candidates),
                "unique_candidate_triples_before_b0_exclusion": len(unique_before_b0),
                "candidates_excluded_because_already_in_b0": len(excluded_b0),
                "final_candidate_count": len(output_records),
                "path_group_count": path_group_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
