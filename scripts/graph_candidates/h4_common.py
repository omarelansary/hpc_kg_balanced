"""Shared helpers for H4 labelled rule-completion experiments.

H4 is a labelled synthetic/rule-completion branch. It never treats generated
edges as canonical observed evidence and writes only run-scoped outputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import networkx as nx

try:  # Imported by tests as scripts.graph_candidates.h4_common.
    from scripts.graph_candidates.c6_common import (  # type: ignore
        TripleRecord,
        compute_graph_metrics,
        count_relations,
        load_allocation,
        load_graph_records,
        relation_eta_map,
        safe_deletion_rows,
        write_csv_rows,
    )
except ModuleNotFoundError:  # Imported by scripts executed from scripts/graph_candidates.
    from c6_common import (  # type: ignore
        TripleRecord,
        compute_graph_metrics,
        count_relations,
        load_allocation,
        load_graph_records,
        relation_eta_map,
        safe_deletion_rows,
        write_csv_rows,
    )

DEFAULT_EXPERIMENT_DIR = Path("experiments/graph_candidates/H4_labelled_rule_completion")
DEFAULT_B0_GRAPH = Path(
    "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/"
    "stage12_path_repair_prod/largest_component.csv"
)
DEFAULT_ALLOCATION = Path("src/Pruning graph/bidirectional_allocation_results5k.json")
DEFAULT_H4_AUDIT = Path(
    "artifacts/final_graph/selected_final_graph/rebuild/"
    "h4_labelled_rule_completion_opportunity_audit.json"
)
DEFAULT_STAGE2_SHARD_DIR = Path(
    "archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards"
)
SCHEMA_VERSION = "h4-labelled-rule-completion-v1"
SYNTHETIC_EDGE_SOURCE = "synthetic_rule_completion"
CANONICAL_EDGE_SOURCE = "canonical_observed"
SYMMETRIC_RULE_TYPE = "symmetric_reverse_completion"


def now_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_run_dir(run_id: str | None = None, run_dir: str | Path | None = None) -> Path:
    if run_dir:
        return Path(run_dir)
    return DEFAULT_EXPERIMENT_DIR / "runs" / (run_id or now_run_id())


def ensure_run_dir(run_id: str | None = None, run_dir: str | Path | None = None) -> Path:
    path = resolve_run_dir(run_id, run_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def command_metadata(run_dir: str | Path, stage_id: str) -> dict[str, Any]:
    return {
        "command_line": list(sys.argv),
        "working_directory": os.getcwd(),
        "created_by": Path(sys.argv[0]).name if sys.argv else stage_id,
        "run_id": Path(run_dir).name,
        "stage_id": stage_id,
    }


def load_h4_audit(path: str | Path = DEFAULT_H4_AUDIT) -> dict[str, Any]:
    data = load_json(path)
    if data.get("schema_version") != "h4-labelled-rule-completion-opportunity-audit-v1":
        raise ValueError(f"unexpected H4 audit schema: {data.get('schema_version')}")
    return data


def symmetric_relation_meta(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = audit.get("h4_a_symmetric_opportunities", {}).get("relations", [])
    return {str(row["relation"]): dict(row) for row in rows}


def load_b0_records(path: str | Path = DEFAULT_B0_GRAPH) -> list[TripleRecord]:
    return [TripleRecord(r.h, r.r, r.t, CANONICAL_EDGE_SOURCE, {"evidence_status": "frozen_observed"}) for r in load_graph_records(path)]


def load_h4_graph_records(path: str | Path) -> list[TripleRecord]:
    graph_path = Path(path)
    if graph_path.suffix.lower() == ".jsonl":
        records: list[TripleRecord] = []
        with graph_path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                missing = {"h", "r", "t"} - set(row)
                if missing:
                    raise ValueError(f"H4 JSONL line {line_no} missing columns: {sorted(missing)}")
                edge_source = str(row.get("edge_source") or row.get("source") or CANONICAL_EDGE_SOURCE)
                provenance = {k: v for k, v in row.items() if k not in {"h", "r", "t", "source"}}
                records.append(TripleRecord(str(row["h"]), str(row["r"]), str(row["t"]), edge_source, provenance))
        return records
    return load_graph_records(graph_path)


def _base_h4_row(record: TripleRecord) -> dict[str, Any]:
    row = {
        "h": record.h,
        "r": record.r,
        "t": record.t,
        "edge_source": record.source if record.source else CANONICAL_EDGE_SOURCE,
    }
    row.update(record.provenance or {})
    if row["edge_source"] == CANONICAL_EDGE_SOURCE:
        row.setdefault("evidence_status", "frozen_observed")
        row.setdefault("source", "B0_parent_graph")
    return row


def h4_record_to_row(record: TripleRecord) -> dict[str, Any]:
    row = _base_h4_row(record)
    if row.get("edge_source") == SYNTHETIC_EDGE_SOURCE:
        row.setdefault("rule_type", SYMMETRIC_RULE_TYPE)
        row.setdefault("evidence_status", "rule_derived_not_observed")
    return row


H4_GRAPH_FIELDNAMES = [
    "h",
    "r",
    "t",
    "edge_source",
    "source",
    "evidence_status",
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
]


def write_h4_graph_jsonl(path: str | Path, records: Iterable[TripleRecord]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(h4_record_to_row(record), sort_keys=True) + "\n")


def write_h4_graph_csv(path: str | Path, records: Iterable[TripleRecord]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=H4_GRAPH_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(h4_record_to_row(record))


def stage2_observed_reverse_candidates(
    b0_records: Sequence[TripleRecord],
    relation_meta: dict[str, dict[str, Any]],
    shard_dir: str | Path = DEFAULT_STAGE2_SHARD_DIR,
) -> set[tuple[str, str, str]]:
    b0_triples = {record.triple for record in b0_records}
    missing_reverse_by_relation: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for record in b0_records:
        if record.r not in relation_meta:
            continue
        reverse = (record.t, record.r, record.h)
        if reverse not in b0_triples:
            missing_reverse_by_relation[record.r].add(reverse)

    observed: set[tuple[str, str, str]] = set()
    root = Path(shard_dir)
    for relation, missing in sorted(missing_reverse_by_relation.items()):
        path = root / f"{relation}.jsonl"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                triple = (str(row.get("h")), str(row.get("r")), str(row.get("t")))
                if triple in missing:
                    observed.add(triple)
    return observed


def _synthetic_record(base: TripleRecord, meta: dict[str, Any]) -> TripleRecord:
    confidence = meta.get("confidence")
    confidence_reason = None if confidence is not None else "confidence_not_available_in_h4_audit"
    provenance = {
        "rule_type": SYMMETRIC_RULE_TYPE,
        "source_relation": base.r,
        "base_h": base.h,
        "base_r": base.r,
        "base_t": base.t,
        "generated_h": base.t,
        "generated_r": base.r,
        "generated_t": base.h,
        "verification_source": "artifacts/final_graph/selected_final_graph/rebuild/h4_labelled_rule_completion_opportunity_audit.json",
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "support": meta.get("support"),
        "evidence_status": "rule_derived_not_observed",
    }
    return TripleRecord(base.t, base.r, base.h, SYNTHETIC_EDGE_SOURCE, provenance)


def eligible_symmetric_completion_edges(
    b0_records: Sequence[TripleRecord],
    relation_meta: dict[str, dict[str, Any]],
    observed_reverse_candidates: set[tuple[str, str, str]] | None = None,
) -> list[TripleRecord]:
    observed_reverse_candidates = set(observed_reverse_candidates or set())
    b0_triples = {record.triple for record in b0_records}
    generated_seen: set[tuple[str, str, str]] = set()
    relation_order = {relation: idx for idx, relation in enumerate(relation_meta)}
    candidates: list[TripleRecord] = []
    for base in b0_records:
        if base.r not in relation_meta:
            continue
        reverse = (base.t, base.r, base.h)
        if reverse in b0_triples or reverse in observed_reverse_candidates or reverse in generated_seen:
            continue
        generated_seen.add(reverse)
        candidates.append(_synthetic_record(base, relation_meta[base.r]))
    return sorted(candidates, key=lambda r: (relation_order.get(r.r, 10**9), r.r, r.h, r.t))


def select_completion_edges(
    eligible: Sequence[TripleRecord],
    relation_meta: dict[str, dict[str, Any]],
    mode: str,
) -> list[TripleRecord]:
    if mode == "add-all":
        return list(eligible)
    if mode != "deficit-capped":
        raise ValueError(f"unsupported H4-A mode: {mode}")
    selected: list[TripleRecord] = []
    by_relation: Counter[str] = Counter()
    for record in eligible:
        cap = int(relation_meta.get(record.r, {}).get("deficit_integer") or 0)
        if cap <= 0:
            continue
        if by_relation[record.r] >= cap:
            continue
        selected.append(record)
        by_relation[record.r] += 1
    return selected


def synthetic_edge_count(records: Sequence[TripleRecord]) -> int:
    return sum(1 for record in records if record.source == SYNTHETIC_EDGE_SOURCE)


def base_triples_for_retained_synthetic_edges(records: Sequence[TripleRecord]) -> set[tuple[str, str, str]]:
    """Return B0 base triples that support retained H4 synthetic edges."""
    base_triples: set[tuple[str, str, str]] = set()
    for record in records:
        if record.source != SYNTHETIC_EDGE_SOURCE:
            continue
        provenance = record.provenance or {}
        base_h = provenance.get("base_h")
        base_r = provenance.get("base_r")
        base_t = provenance.get("base_t")
        if base_h and base_r and base_t:
            base_triples.add((str(base_h), str(base_r), str(base_t)))
    return base_triples


def compute_h4_metrics(records: Sequence[TripleRecord], allocation: dict[str, Any]) -> dict[str, Any]:
    metrics = compute_graph_metrics([record.triple for record in records], allocation)
    synthetic_count = synthetic_edge_count(records)
    metrics["synthetic_edge_count"] = synthetic_count
    metrics["synthetic_edge_ratio"] = synthetic_count / metrics["total_triples"] if metrics["total_triples"] else 0.0
    metrics["canonical_observed_edge_count"] = metrics["total_triples"] - synthetic_count
    metrics["reciprocal_pairs_completed"] = synthetic_count
    return metrics


def constraints_summary(metrics: dict[str, Any], allocation: dict[str, Any]) -> dict[str, Any]:
    expected_coverage = len(allocation["relation_expected"])
    checks = {
        "weak_component_count_is_1": metrics["weak_component_count"] == 1,
        "allocated_relation_coverage_preserved": metrics["allocated_relation_coverage_count"] == expected_coverage,
        "duplicate_triple_count_is_0": metrics["duplicate_triple_count"] == 0,
        "synthetic_edges_labelled": metrics.get("synthetic_edge_count", 0) >= 0,
    }
    return {"passed": all(checks.values()), "checks": checks, "expected_relation_coverage": expected_coverage}


def h4_safe_deletion_candidates(
    b0_records: Sequence[TripleRecord],
    completed_records: Sequence[TripleRecord],
    allocation: dict[str, Any],
) -> list[dict[str, Any]]:
    completed_relation_counts = count_relations([record.triple for record in completed_records])
    b0_relation_counts = count_relations([record.triple for record in b0_records])
    expected = relation_eta_map(allocation)
    relation_patterns = {
        relation: [str(row["pattern"]) for row in rows]
        for relation, rows in allocation["relation_patterns"].items()
    }
    pattern_rows = {row["pattern"]: row for row in compute_graph_metrics([r.triple for r in completed_records], allocation)["pattern_level"]}
    completed_pair_counts = pair_counts(completed_records)
    b0_pair_counts = pair_counts(b0_records)
    rows: list[dict[str, Any]] = []
    for record in b0_records:
        relation = record.r
        pair = canonical_pair(record.h, record.t)
        if completed_pair_counts[pair] <= 1:
            continue
        patterns = relation_patterns.get(relation, [])
        relation_surplus = max(float(completed_relation_counts.get(relation, 0)) - float(expected.get(relation, 0.0)), 0.0)
        relation_overfilled = relation_surplus > 0
        pattern_overfilled = any(float(pattern_rows.get(pattern, {}).get("surplus", 0.0)) > 0 for pattern in patterns)
        if not relation_overfilled and not pattern_overfilled:
            continue
        if b0_relation_counts[relation] <= 1:
            continue
        safe_before = b0_pair_counts[pair] > 1
        rows.append(
            {
                "h": record.h,
                "r": relation,
                "t": record.t,
                "patterns": "|".join(patterns),
                "relation_surplus_before_b0": max(
                    float(b0_relation_counts.get(relation, 0)) - float(expected.get(relation, 0.0)),
                    0.0,
                ),
                "relation_surplus_after_addition": relation_surplus,
                "relation_overfilled": relation_overfilled,
                "pattern_overfilled": pattern_overfilled,
                "pair_count_after_addition": completed_pair_counts[pair],
                "bridge_before_additions": None,
                "bridge_after_additions": False,
                "safe_before_additions": safe_before,
                "safe_after_additions": True,
                "safe_after_not_before": not safe_before,
                "surplus_reduction_score": 1.0 if relation_overfilled else 0.5,
                "deletes_edge_source": CANONICAL_EDGE_SOURCE,
                "synthetic_edges_available": synthetic_edge_count(completed_records),
            }
        )
    return rows


def apply_h4_safe_deletions(
    b0_records: Sequence[TripleRecord],
    completed_records: Sequence[TripleRecord],
    allocation: dict[str, Any],
    max_deletions: int = 100000,
    preserve_original_entities: bool = True,
    allow_deficit_increase: bool = False,
    allow_singleton_connectivity_checks: bool = False,
    allow_delete_base_triples_for_retained_synthetic: bool = False,
) -> tuple[list[TripleRecord], list[dict[str, Any]], dict[str, int], dict[str, Any], list[dict[str, Any]]]:
    original_entities = {entity for record in b0_records for entity in (record.h, record.t)}
    base_support_triples = base_triples_for_retained_synthetic_edges(completed_records)
    deletion_rows = h4_safe_deletion_candidates(b0_records, completed_records, allocation)
    rows_sorted = sorted(
        deletion_rows,
        key=lambda row: (
            -float(row.get("surplus_reduction_score", 0.0)),
            not bool_from_value(row.get("safe_after_not_before", False)),
            str(row.get("r", "")),
            str(row.get("h", "")),
            str(row.get("t", "")),
        ),
    )

    current_triples = {record.triple for record in completed_records}
    current_by_triple = {record.triple: record for record in completed_records}
    relation_counts = count_relations(list(current_triples))
    relation_expected = relation_eta_map(allocation)
    allocated_relations = set(relation_expected)
    current_entity_counts = entity_counts(completed_records)
    current_pair_counts = pair_counts(completed_records)
    current_deficit = total_deficit_from_counts(relation_counts, relation_expected)

    accepted: list[dict[str, Any]] = []
    rejections: Counter[str] = Counter()
    for row in rows_sorted:
        if len(accepted) >= max_deletions:
            break
        if not bool_from_value(row.get("safe_after_additions", False)):
            rejections["safe_after_additions_false"] += 1
            continue
        triple = (str(row["h"]), str(row["r"]), str(row["t"]))
        if triple not in current_triples:
            rejections["already_absent"] += 1
            continue
        if not allow_delete_base_triples_for_retained_synthetic and triple in base_support_triples:
            rejections["deletes_base_triple_for_retained_synthetic_edge"] += 1
            continue
        relation = triple[1]
        if relation in allocated_relations and relation_counts[relation] <= 1:
            rejections["would_drop_relation_coverage"] += 1
            continue

        next_relation_counts = Counter(relation_counts)
        next_relation_counts[relation] -= 1
        next_deficit = total_deficit_from_counts(next_relation_counts, relation_expected)
        if not allow_deficit_increase and next_deficit > current_deficit + 1e-9:
            rejections["increases_total_deficit"] += 1
            continue

        h, _r, t = triple
        if preserve_original_entities:
            if h in original_entities and current_entity_counts[h] <= 1:
                rejections["drops_original_entity"] += 1
                continue
            if t in original_entities and current_entity_counts[t] <= 1:
                rejections["drops_original_entity"] += 1
                continue

        pair = canonical_pair(h, t)
        if current_pair_counts[pair] <= 1:
            if not allow_singleton_connectivity_checks:
                rejections["singleton_connectivity_check_skipped"] += 1
                continue
            required = original_entities if preserve_original_entities else None
            if not exact_connected_after_pair_removal(current_triples, triple, required):
                rejections["would_disconnect"] += 1
                continue

        current_triples.remove(triple)
        current_by_triple.pop(triple, None)
        relation_counts = next_relation_counts
        current_deficit = next_deficit
        current_entity_counts[h] -= 1
        current_entity_counts[t] -= 1
        current_pair_counts[pair] -= 1
        accepted_row = dict(row)
        accepted_row["accepted_order"] = len(accepted) + 1
        accepted_row["is_base_triple_for_retained_synthetic_edge"] = triple in base_support_triples
        accepted.append(accepted_row)

    final_records = [record for record in completed_records if record.triple in current_triples]
    final_entities = {entity for record in final_records for entity in (record.h, record.t)}
    stats = {
        "original_entity_count": len(original_entities),
        "final_original_entities_present_count": len(original_entities & final_entities),
        "dropped_original_entity_count": len(original_entities - final_entities),
        "preserve_original_entities": preserve_original_entities,
        "allow_deficit_increase": allow_deficit_increase,
        "allow_singleton_connectivity_checks": allow_singleton_connectivity_checks,
        "allow_delete_base_triples_for_retained_synthetic": allow_delete_base_triples_for_retained_synthetic,
        "preserve_base_triples_for_retained_synthetic_edges": not allow_delete_base_triples_for_retained_synthetic,
        "base_triples_supporting_retained_synthetic_edges_count": len(base_support_triples),
        "safe_after_additions_false_skipped_count": rejections.get("safe_after_additions_false", 0),
        "drops_original_entity_rejected_count": rejections.get("drops_original_entity", 0),
        "increases_total_deficit_rejected_count": rejections.get("increases_total_deficit", 0),
        "would_disconnect_rejected_count": rejections.get("would_disconnect", 0),
        "singleton_connectivity_check_skipped_count": rejections.get("singleton_connectivity_check_skipped", 0),
        "rejected_deletes_base_triple_for_retained_synthetic_edge_count": rejections.get(
            "deletes_base_triple_for_retained_synthetic_edge",
            0,
        ),
    }
    stats["safe_deletion_candidate_count"] = len(deletion_rows)
    stats["safe_after_not_before_count"] = sum(1 for row in deletion_rows if row.get("safe_after_not_before"))
    stats["accepted_safe_after_not_before_count"] = sum(1 for row in accepted if row.get("safe_after_not_before") in {True, "True", "true", "1"})
    stats["synthetic_edges_deleted"] = sum(1 for row in accepted if row.get("deletes_edge_source") == SYNTHETIC_EDGE_SOURCE)
    stats["deleted_base_triples_for_retained_synthetic_edges_count"] = sum(
        1 for row in accepted if row.get("is_base_triple_for_retained_synthetic_edge")
    )
    return final_records, accepted, rejections, stats, deletion_rows


def top_counts(counter: Counter[str], limit: int = 20) -> dict[str, int]:
    return dict(counter.most_common(limit))


def canonical_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def bool_from_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def total_deficit_from_counts(relation_counts: Counter[str], relation_expected: dict[str, float]) -> float:
    return sum(max(float(expected) - float(relation_counts.get(relation, 0)), 0.0) for relation, expected in relation_expected.items())


def entity_counts(records: Sequence[TripleRecord]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        counts[record.h] += 1
        counts[record.t] += 1
    return counts


def pair_counts(records: Sequence[TripleRecord]) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for record in records:
        counts[canonical_pair(record.h, record.t)] += 1
    return counts


def exact_connected_after_pair_removal(
    current_triples: set[tuple[str, str, str]],
    triple: tuple[str, str, str],
    required_entities: set[str] | None,
) -> bool:
    graph = nx.Graph()
    for h, _r, t in current_triples:
        if (h, _r, t) != triple:
            graph.add_edge(h, t)
    if required_entities:
        graph.add_nodes_from(required_entities)
    return graph.number_of_nodes() > 0 and nx.is_connected(graph)
