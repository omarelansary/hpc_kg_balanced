"""Shared helpers for C6 observed canonical densification.

C6 is a bounded, deterministic construction experiment. It reads frozen
artifacts, writes only run-scoped outputs, and keeps generated candidate
graphs distinct from B0 and historical graph artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

import networkx as nx

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import (  # noqa: E402
    compare_relation_counts_to_allocation,
    load_allocation,
)
from src.kg_pipeline.evaluation.graph_io import (  # noqa: E402
    Triple,
    count_entities,
    count_relations,
    load_graph_triples,
    summarize_graph_triples,
)
from src.kg_pipeline.evaluation.pattern_balance import (  # noqa: E402
    aggregate_observed_by_pattern_integer,
    compare_pattern_totals,
)

DEFAULT_EXPERIMENT_DIR = Path("experiments/graph_candidates/C6_observed_canonical_densification")
DEFAULT_B0_GRAPH = Path(
    "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/"
    "stage12_path_repair_prod/largest_component.csv"
)
DEFAULT_ALLOCATION = Path("src/Pruning graph/bidirectional_allocation_results5k.json")
DEFAULT_CANDIDATE_GLOB = (
    "archive/hetzner_version/runs/prod_refine_20260315_180520/"
    "stage02_candidates/shards/*.jsonl"
)
DEFAULT_RELATION_FULFILLMENT = Path(
    "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/"
    "stage12_path_repair_prod/largest_component_eta_analysis/relation_fulfillment.csv"
)
SCHEMA_VERSION = "c6-observed-canonical-densification-v1"
GENERIC_RELATIONS = {"P31", "P279", "P131"}
SUPPORTED_COMPOSITION_POLICIES = {"penalize_if_overfilled", "forbid_if_overfilled", "allow"}


@dataclass(frozen=True)
class TripleRecord:
    h: str
    r: str
    t: str
    source: str = "canonical_existing"
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def triple(self) -> Triple:
        return self.h, self.r, self.t

    @property
    def pair(self) -> tuple[str, str]:
        return canonical_pair(self.h, self.t)

    def to_json(self) -> dict[str, Any]:
        row = {"h": self.h, "r": self.r, "t": self.t, "source": self.source}
        if self.provenance:
            row["provenance"] = self.provenance
        return row


def canonical_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


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
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def command_metadata(run_dir: str | Path, stage_id: str) -> dict[str, Any]:
    return {
        "command_line": list(sys.argv),
        "working_directory": os.getcwd(),
        "created_by": Path(sys.argv[0]).name if sys.argv else stage_id,
        "run_id": Path(run_dir).name,
        "run_mode": os.environ.get("C6_RUN_MODE", "manual"),
        "stage_id": stage_id,
    }


def load_graph_records(path: str | Path, source: str = "canonical_existing") -> list[TripleRecord]:
    graph_path = Path(path)
    records: list[TripleRecord] = []
    if graph_path.suffix.lower() == ".csv":
        with graph_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            missing = {"h", "r", "t"} - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV graph missing columns: {sorted(missing)}")
            for row in reader:
                records.append(TripleRecord(str(row["h"]), str(row["r"]), str(row["t"]), source))
        return records
    if graph_path.suffix.lower() == ".jsonl":
        with graph_path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                missing = {"h", "r", "t"} - set(obj)
                if missing:
                    raise ValueError(f"JSONL graph line {line_no} missing columns: {sorted(missing)}")
                provenance = {k: v for k, v in obj.items() if k not in {"h", "r", "t", "source"}}
                records.append(
                    TripleRecord(
                        str(obj["h"]),
                        str(obj["r"]),
                        str(obj["t"]),
                        str(obj.get("source") or source),
                        provenance,
                    )
                )
        return records
    triples = load_graph_triples(graph_path)
    return [TripleRecord(h, r, t, source) for h, r, t in triples]


def write_graph_jsonl(path: str | Path, records: Iterable[TripleRecord]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record.to_json(), sort_keys=True) + "\n")


def write_graph_csv(path: str | Path, records: Iterable[TripleRecord]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["h", "r", "t"])
        writer.writeheader()
        for record in records:
            writer.writerow({"h": record.h, "r": record.r, "t": record.t})


def relation_pattern_map(allocation: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for relation, rows in allocation["relation_patterns"].items():
        patterns = sorted({str(row["pattern"]) for row in rows if row.get("pattern")})
        mapping[str(relation)] = patterns
    return mapping


def relation_eta_map(allocation: dict[str, Any]) -> dict[str, float]:
    return {str(k): float(v) for k, v in allocation["relation_expected"].items()}


def pattern_expected_map(allocation: dict[str, Any]) -> dict[str, float]:
    return {str(k): float(v) for k, v in allocation["pattern_expected"].items()}


def build_nx_graph(triples: Iterable[Triple]) -> nx.Graph:
    graph = nx.Graph()
    for h, _r, t in triples:
        graph.add_edge(h, t)
    return graph


def pair_counts(triples: Iterable[Triple]) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for h, _r, t in triples:
        counts[canonical_pair(h, t)] += 1
    return counts


def common_neighbor_count(graph: nx.Graph, h: str, t: str) -> int:
    if h not in graph or t not in graph:
        return 0
    return len(set(graph.neighbors(h)) & set(graph.neighbors(t)))


def graph_structural_metrics(triples: Sequence[Triple]) -> dict[str, Any]:
    graph = build_nx_graph(triples)
    if graph.number_of_nodes() == 0:
        return {
            "weak_component_count": 0,
            "largest_component_ratio": 0.0,
            "bridge_count": 0,
            "articulation_point_count": 0,
            "two_path_count": 0,
        }
    component_sizes = [len(component) for component in nx.connected_components(graph)]
    largest = max(component_sizes) if component_sizes else 0
    two_path_count = sum(degree * (degree - 1) // 2 for _node, degree in graph.degree())
    return {
        "weak_component_count": len(component_sizes),
        "largest_component_ratio": largest / graph.number_of_nodes(),
        "bridge_count": sum(1 for _edge in nx.bridges(graph)),
        "articulation_point_count": sum(1 for _node in nx.articulation_points(graph)),
        "two_path_count": int(two_path_count),
    }


def compute_graph_metrics(
    triples: Sequence[Triple],
    allocation: dict[str, Any],
) -> dict[str, Any]:
    unique_triples = sorted(set(triples))
    graph_summary = summarize_graph_triples(unique_triples)
    structural = graph_structural_metrics(unique_triples)
    relation_counts = graph_summary["relation_counts"]
    allocation_metrics = compare_relation_counts_to_allocation(relation_counts, allocation)
    pattern_level = compare_pattern_totals(relation_counts, allocation)
    pattern_integer = aggregate_observed_by_pattern_integer(relation_counts, allocation)
    pattern_by_name = {row["pattern"]: row for row in pattern_level}
    total_triples = graph_summary["total_triples"]
    total_entities = graph_summary["unique_entities"]
    composition_total = float(pattern_integer.get("composition", 0))
    symmetric_total = float(pattern_integer.get("symmetric", 0))
    composition_surplus = float(pattern_by_name.get("composition", {}).get("surplus", 0.0))
    symmetric_deficit = float(pattern_by_name.get("symmetric", {}).get("deficit", 0.0))
    return {
        "total_triples": total_triples,
        "total_entities": total_entities,
        "triples_per_entity": total_triples / total_entities if total_entities else 0.0,
        "entities_per_triple": total_entities / total_triples if total_triples else 0.0,
        "average_participation": (2 * total_triples) / total_entities if total_entities else 0.0,
        "weak_component_count": structural["weak_component_count"],
        "largest_component_ratio": structural["largest_component_ratio"],
        "duplicate_triple_count": graph_summary["duplicate_triple_count"],
        "allocated_relation_coverage_count": allocation_metrics["allocated_relations_observed"],
        "allocated_relation_coverage_ratio": (
            allocation_metrics["allocated_relations_observed"]
            / allocation_metrics["allocation_relation_count"]
            if allocation_metrics["allocation_relation_count"]
            else 0.0
        ),
        "relation_counts": relation_counts,
        "relation_balance": allocation_metrics,
        "total_surplus": allocation_metrics["total_surplus"],
        "total_deficit": allocation_metrics["total_deficit"],
        "pattern_level": pattern_level,
        "pattern_integer_totals": pattern_integer,
        "composition_total": composition_total,
        "composition_surplus": composition_surplus,
        "composition_share": composition_total / total_triples if total_triples else 0.0,
        "symmetric_total": symmetric_total,
        "symmetric_deficit": symmetric_deficit,
        "bridge_count": structural["bridge_count"],
        "articulation_point_count": structural["articulation_point_count"],
        "two_path_count": structural["two_path_count"],
    }


def load_relation_fulfillment(path: str | Path = DEFAULT_RELATION_FULFILLMENT) -> dict[str, dict[str, Any]]:
    relation_rows: dict[str, dict[str, Any]] = {}
    if not Path(path).exists():
        return relation_rows
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            relation = row.get("relation")
            if not relation:
                continue
            parsed: dict[str, Any] = dict(row)
            for key in ("eta_integer", "observed_count", "deficit", "surplus"):
                try:
                    parsed[key] = float(row.get(key, 0) or 0)
                except ValueError:
                    parsed[key] = 0.0
            relation_rows[str(relation)] = parsed
    return relation_rows


def discover_default_inputs() -> dict[str, Any]:
    registry_path = Path("artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json")
    registry = load_json(registry_path) if registry_path.exists() else {}
    b0 = next(
        (row for row in registry.get("candidates", []) if row.get("candidate_id") == "B0"),
        {},
    )
    candidate_files = sorted(str(path) for path in Path().glob(DEFAULT_CANDIDATE_GLOB))
    return {
        "b0_graph_path": b0.get("graph_path") or str(DEFAULT_B0_GRAPH),
        "b0_graph_sha256": b0.get("graph_sha256"),
        "allocation_path": registry.get("canonical_allocation_path") or str(DEFAULT_ALLOCATION),
        "allocation_sha256": registry.get("canonical_allocation_sha256"),
        "verified_allocated_relation_source": registry.get("canonical_allocation_path") or str(DEFAULT_ALLOCATION),
        "candidate_source_glob": DEFAULT_CANDIDATE_GLOB,
        "candidate_source_file_count": len(candidate_files),
        "candidate_source_files_first10": candidate_files[:10],
        "relation_fulfillment_path": str(DEFAULT_RELATION_FULFILLMENT),
        "registry_path": str(registry_path),
    }


def validate_discovered_inputs(inputs: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in ("b0_graph_path", "allocation_path"):
        path = inputs.get(key)
        if not path or not Path(path).exists():
            missing.append(f"{key}:{path}")
    if not inputs.get("candidate_source_file_count"):
        missing.append(f"candidate_source_glob:{inputs.get('candidate_source_glob')}")
    return missing


def iter_candidate_rows(
    candidate_glob: str = DEFAULT_CANDIDATE_GLOB,
    max_candidates: int | None = None,
) -> Iterator[dict[str, Any]]:
    count = 0
    for path in sorted(Path().glob(candidate_glob)):
        with path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if not {"h", "r", "t"} <= set(row):
                    continue
                row["_source_path"] = str(path)
                row["_source_line"] = line_no
                yield row
                count += 1
                if max_candidates is not None and max_candidates > 0 and count >= max_candidates:
                    return


def classify_candidate(h: str, t: str, b0_entities: set[str]) -> str:
    in_h = h in b0_entities
    in_t = t in b0_entities
    if in_h and in_t:
        return "internal"
    if in_h or in_t:
        return "semi_internal"
    return "external"


def relation_status(
    relation: str,
    relation_counts: Counter[str] | dict[str, int],
    relation_eta: dict[str, float],
) -> dict[str, float | bool]:
    observed = float(relation_counts.get(relation, 0))
    eta = float(relation_eta.get(relation, 0.0))
    deficit = max(eta - observed, 0.0)
    surplus = max(observed - eta, 0.0)
    return {
        "relation_eta": eta,
        "relation_observed_count_in_B0": observed,
        "relation_deficit_before": deficit,
        "relation_surplus_before": surplus,
        "underfilled_relation_flag": deficit > 0,
    }


def pattern_status(
    patterns: Sequence[str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    pattern_rows = {row["pattern"]: row for row in metrics["pattern_level"]}
    underfilled = False
    overfilled_composition = False
    memberships = list(patterns)
    for pattern in memberships:
        row = pattern_rows.get(pattern) or {}
        underfilled = underfilled or float(row.get("deficit", 0.0)) > 0
        if pattern == "composition" and float(row.get("surplus", 0.0)) > 0:
            overfilled_composition = True
    return {
        "pattern_memberships": "|".join(memberships),
        "underfilled_pattern_flag": underfilled,
        "composition_relation_flag": "composition" in memberships,
        "symmetric_relation_flag": "symmetric" in memberships,
        "composition_overfilled_flag": overfilled_composition,
    }


DEFAULT_SCORE_WEIGHTS = {
    "relation_deficit_weight": 5.0,
    "pattern_deficit_weight": 2.5,
    "symmetric_priority_weight": 4.0,
    "entity_reuse_weight": 1.0,
    "local_density_weight": 1.0,
    "redundancy_weight": 1.0,
    "composition_penalty_weight": 6.0,
    "generic_relation_penalty_weight": 1.5,
    "new_entity_penalty_weight": 2.0,
}


def candidate_score(row: dict[str, Any], weights: dict[str, float] | None = None) -> dict[str, float]:
    weights = {**DEFAULT_SCORE_WEIGHTS, **(weights or {})}
    relation_deficit = float(row.get("relation_deficit_before", 0.0))
    relation_eta = max(float(row.get("relation_eta", 0.0)), 1.0)
    relation_gain = min(relation_deficit / relation_eta, 1.0)
    pattern_gain = 1.0 if row.get("underfilled_pattern_flag") else 0.0
    symmetric_gain = 1.0 if row.get("symmetric_relation_flag") and row.get("underfilled_pattern_flag") else 0.0
    introduced = float(row.get("introduces_new_entities_count", 0.0))
    endpoint_score = 1.0 if row.get("candidate_class") == "internal" else (0.5 if introduced == 1 else 0.0)
    common_neighbors = float(row.get("local_common_neighbors_count", 0.0))
    local_density = min(common_neighbors / 10.0, 1.0)
    redundancy = 1.0 if common_neighbors > 0 else 0.0
    composition_penalty = 1.0 if row.get("composition_relation_flag") and row.get("composition_overfilled_flag") else 0.0
    generic_penalty = 1.0 if row.get("r") in GENERIC_RELATIONS else 0.0
    score = (
        weights["relation_deficit_weight"] * relation_gain
        + weights["pattern_deficit_weight"] * pattern_gain
        + weights["symmetric_priority_weight"] * symmetric_gain
        + weights["entity_reuse_weight"] * endpoint_score
        + weights["local_density_weight"] * local_density
        + weights["redundancy_weight"] * redundancy
        - weights["composition_penalty_weight"] * composition_penalty
        - weights["generic_relation_penalty_weight"] * generic_penalty
        - weights["new_entity_penalty_weight"] * introduced
    )
    return {
        "candidate_score": score,
        "relation_deficit_gain": relation_gain,
        "pattern_deficit_gain": pattern_gain,
        "symmetric_underfill_gain": symmetric_gain,
        "existing_endpoint_score": endpoint_score,
        "local_common_neighbors_score": local_density,
        "alternative_path_or_wedge_score": redundancy,
        "composition_overfill_penalty": composition_penalty,
        "generic_relation_penalty": generic_penalty,
        "new_entity_penalty": introduced,
    }


def bool_from_csv(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def float_from_csv(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_census(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key in (
                "relation_eta",
                "relation_observed_count_in_B0",
                "relation_deficit_before",
                "relation_surplus_before",
                "introduces_new_entities_count",
                "endpoint_degree_h",
                "endpoint_degree_t",
                "local_common_neighbors_count",
                "candidate_score",
            ):
                if key in row:
                    row[key] = float_from_csv(row[key])
            for key in (
                "underfilled_relation_flag",
                "underfilled_pattern_flag",
                "composition_relation_flag",
                "symmetric_relation_flag",
                "existing_pair_flag",
                "creates_duplicate_flag",
                "allocated_relation_flag",
            ):
                if key in row:
                    row[key] = bool_from_csv(row[key])
            rows.append(row)
    return rows


def candidate_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -float(row.get("candidate_score", 0.0)),
        float(row.get("introduces_new_entities_count", 0.0)),
        -float(row.get("relation_deficit_before", 0.0)),
        str(row.get("r", "")),
        str(row.get("h", "")),
        str(row.get("t", "")),
    )


def select_additions(
    census_rows: Sequence[dict[str, Any]],
    base_triples: Sequence[Triple],
    allocation: dict[str, Any],
    config: dict[str, Any],
) -> tuple[list[TripleRecord], dict[str, int], dict[str, Any]]:
    relation_counts = count_relations(base_triples)
    pattern_map = relation_pattern_map(allocation)
    pattern_counts = aggregate_observed_by_pattern_integer(relation_counts, allocation)
    accepted: list[TripleRecord] = []
    rejection_reasons: Counter[str] = Counter()
    current_triples = set(base_triples)
    entities = {entity for h, _r, t in base_triples for entity in (h, t)}
    allowed_classes = set(config.get("allowed_candidate_classes") or ["internal"])
    max_additions = int(config.get("max_additions", 2000))
    new_entity_budget = int(config.get("new_entity_budget", 0))
    allow_auxiliary = bool(config.get("allow_auxiliary", False))
    require_allocated = bool(config.get("require_allocated_relation", True))
    preserve_connected = bool(config.get("preserve_connected", True))
    composition_policy = str(config.get("composition_addition_policy", "forbid_if_overfilled"))
    if composition_policy not in SUPPORTED_COMPOSITION_POLICIES:
        raise ValueError(
            "unsupported composition_addition_policy "
            f"{composition_policy!r}; expected {sorted(SUPPORTED_COMPOSITION_POLICIES)}"
        )
    min_score = float(config.get("min_score", 0.0))
    require_underfilled_relation_or_pattern = bool(config.get("require_underfilled_relation_or_pattern", False))
    allocated_relations = set(relation_eta_map(allocation))
    accepted_scores: list[float] = []
    accepted_negative_score_count = 0
    accepted_composition_penalized_count = 0
    new_entities_used = 0

    for row in sorted(census_rows, key=candidate_sort_key):
        if len(accepted) >= max_additions:
            break
        triple = (str(row["h"]), str(row["r"]), str(row["t"]))
        relation = triple[1]
        if triple in current_triples:
            rejection_reasons["duplicate"] += 1
            continue
        if row.get("candidate_class") not in allowed_classes:
            rejection_reasons["candidate_class_not_allowed"] += 1
            continue
        if require_allocated and relation not in allocated_relations:
            rejection_reasons["unallocated_relation"] += 1
            continue
        if relation not in allocated_relations and not allow_auxiliary:
            rejection_reasons["auxiliary_disallowed"] += 1
            continue
        score = float(row.get("candidate_score", 0.0))
        if score <= min_score:
            rejection_reasons["score_below_threshold"] += 1
            continue
        if require_underfilled_relation_or_pattern and not (
            row.get("underfilled_relation_flag") or row.get("underfilled_pattern_flag")
        ):
            rejection_reasons["not_underfilled_relation_or_pattern"] += 1
            continue
        introduced = sum(1 for entity in (triple[0], triple[2]) if entity not in entities)
        if introduced > 0 and new_entities_used + introduced > new_entity_budget:
            rejection_reasons["new_entity_budget"] += 1
            continue
        relation_patterns = pattern_map.get(relation, [])
        composition_overfilled = "composition" in relation_patterns and pattern_counts.get("composition", 0) >= float(
            pattern_expected_map(allocation).get("composition", math.inf)
        )
        if composition_overfilled:
            if composition_policy == "forbid_if_overfilled":
                rejection_reasons["composition_overfilled_forbidden"] += 1
                continue
            if composition_policy == "penalize_if_overfilled":
                accepted_composition_penalized_count += 1
        tentative = list(current_triples) + [triple]
        if preserve_connected and graph_structural_metrics(tentative)["weak_component_count"] != 1:
            rejection_reasons["connectivity_not_preserved"] += 1
            continue
        accepted.append(
            TripleRecord(
                triple[0],
                relation,
                triple[2],
                "c6_observed_canonical_addition",
                {
                    "candidate_class": row.get("candidate_class"),
                    "candidate_score": score,
                    "source_path": row.get("source_path"),
                    "source_line": row.get("source_line"),
                    "pattern_memberships": row.get("pattern_memberships"),
                    "evidence_status": "frozen_observed",
                },
            )
        )
        accepted_scores.append(score)
        if score < 0:
            accepted_negative_score_count += 1
        current_triples.add(triple)
        relation_counts[relation] += 1
        new_entities_used += introduced
        entities.update([triple[0], triple[2]])
        pattern_counts = aggregate_observed_by_pattern_integer(relation_counts, allocation)

    stats = {
        "accepted_min_score": min(accepted_scores) if accepted_scores else None,
        "accepted_negative_score_count": accepted_negative_score_count,
        "accepted_composition_penalized_count": accepted_composition_penalized_count,
        "rejected_score_below_threshold_count": rejection_reasons.get("score_below_threshold", 0),
        "min_score": min_score,
        "composition_addition_policy": composition_policy,
        "require_underfilled_relation_or_pattern": require_underfilled_relation_or_pattern,
        "new_entities_used": new_entities_used,
        "new_entity_budget": new_entity_budget,
    }
    return accepted, dict(sorted(rejection_reasons.items())), stats


def relation_surplus_map(metrics: dict[str, Any]) -> dict[str, float]:
    return {
        row["relation"]: float(row["surplus"])
        for row in metrics["relation_balance"]["per_relation_expected_observed"]
    }


def relation_deficit_map(metrics: dict[str, Any]) -> dict[str, float]:
    return {
        row["relation"]: float(row["deficit"])
        for row in metrics["relation_balance"]["per_relation_expected_observed"]
    }


def bridge_pairs(triples: Sequence[Triple]) -> set[tuple[str, str]]:
    graph = build_nx_graph(triples)
    return {canonical_pair(left, right) for left, right in nx.bridges(graph)}


def structurally_safe_to_remove(
    triples: Sequence[Triple],
    triple: Triple,
    preserve_original_entities: bool = True,
    original_entities: set[str] | None = None,
) -> bool:
    original_entities = set(original_entities or {entity for h, _r, t in triples for entity in (h, t)})
    counts = pair_counts(triples)
    reduced = list(triples)
    try:
        reduced.remove(triple)
    except ValueError:
        return False
    if preserve_original_entities:
        reduced_entities = {entity for h, _r, t in reduced for entity in (h, t)}
        if not original_entities <= reduced_entities:
            return False
    if counts[canonical_pair(triple[0], triple[2])] > 1:
        return True
    return weakly_connected(reduced, original_entities if preserve_original_entities else None)


def weakly_connected(triples: Sequence[Triple], required_entities: set[str] | None = None) -> bool:
    graph = build_nx_graph(triples)
    if required_entities:
        graph.add_nodes_from(required_entities)
    if graph.number_of_nodes() == 0:
        return False
    return nx.is_connected(graph)


def safe_deletion_rows(
    b0_records: Sequence[TripleRecord],
    added_records: Sequence[TripleRecord],
    allocation: dict[str, Any],
) -> list[dict[str, Any]]:
    b0_triples = [record.triple for record in b0_records]
    added_triples = [record.triple for record in added_records]
    b0_metrics = compute_graph_metrics(b0_triples, allocation)
    added_metrics = compute_graph_metrics(added_triples, allocation)
    b0_surplus = relation_surplus_map(b0_metrics)
    added_surplus = relation_surplus_map(added_metrics)
    pattern_map = relation_pattern_map(allocation)
    b0_counts = count_relations(b0_triples)
    added_pair_counts = pair_counts(added_triples)
    b0_bridges = bridge_pairs(b0_triples)
    added_bridges = bridge_pairs(added_triples)

    rows: list[dict[str, Any]] = []
    for record in b0_records:
        triple = record.triple
        relation = record.r
        patterns = pattern_map.get(relation, [])
        relation_overfilled = added_surplus.get(relation, 0.0) > 0
        pattern_overfilled = "composition" in patterns and added_metrics["composition_surplus"] > 0
        if not relation_overfilled and not pattern_overfilled:
            continue
        if b0_counts[relation] <= 1:
            continue
        pair = record.pair
        structurally_safe_after = added_pair_counts[pair] > 1 or pair not in added_bridges
        structurally_safe_before = pair_counts(b0_triples)[pair] > 1 or pair not in b0_bridges
        rows.append(
            {
                "h": record.h,
                "r": relation,
                "t": record.t,
                "patterns": "|".join(patterns),
                "relation_surplus_before_b0": b0_surplus.get(relation, 0.0),
                "relation_surplus_after_addition": added_surplus.get(relation, 0.0),
                "relation_overfilled": relation_overfilled,
                "pattern_overfilled": pattern_overfilled,
                "pair_count_after_addition": added_pair_counts[pair],
                "bridge_before_additions": pair in b0_bridges,
                "bridge_after_additions": pair in added_bridges,
                "safe_before_additions": structurally_safe_before,
                "safe_after_additions": structurally_safe_after,
                "safe_after_not_before": structurally_safe_after and not structurally_safe_before,
                "surplus_reduction_score": 1.0 if relation_overfilled else 0.5,
            }
        )
    return rows


def apply_safe_deletions(
    added_records: Sequence[TripleRecord],
    deletion_rows: Sequence[dict[str, Any]],
    allocation: dict[str, Any],
    max_deletions: int = 2000,
    original_entities: set[str] | None = None,
    preserve_original_entities: bool = True,
    allow_unverified_safe_deletions: bool = False,
    allow_deficit_increase: bool = False,
) -> tuple[list[TripleRecord], list[dict[str, Any]], dict[str, int], dict[str, Any]]:
    current = list(added_records)
    current_triples = [record.triple for record in current]
    relation_counts = count_relations(current_triples)
    accepted: list[dict[str, Any]] = []
    rejections: Counter[str] = Counter()
    original_entities = set(original_entities or {entity for h, _r, t in current_triples for entity in (h, t)})
    current_metrics = compute_graph_metrics(current_triples, allocation)
    current_deficit = float(current_metrics["total_deficit"])
    rows_sorted = sorted(
        deletion_rows,
        key=lambda row: (
            -float(row.get("surplus_reduction_score", 0.0)),
            not bool_from_csv(row.get("safe_after_not_before", False)),
            str(row.get("r", "")),
            str(row.get("h", "")),
            str(row.get("t", "")),
        ),
    )
    allocated_relations = set(relation_eta_map(allocation))
    for row in rows_sorted:
        if len(accepted) >= max_deletions:
            break
        if not allow_unverified_safe_deletions and not bool_from_csv(row.get("safe_after_additions", False)):
            rejections["safe_after_additions_false"] += 1
            continue
        triple = (str(row["h"]), str(row["r"]), str(row["t"]))
        if triple not in current_triples:
            rejections["already_absent"] += 1
            continue
        relation = triple[1]
        if relation in allocated_relations and relation_counts[relation] <= 1:
            rejections["would_drop_relation_coverage"] += 1
            continue
        tentative = list(current_triples)
        tentative.remove(triple)
        tentative_entities = {entity for h, _r, t in tentative for entity in (h, t)}
        if preserve_original_entities and not original_entities <= tentative_entities:
            rejections["drops_original_entity"] += 1
            continue
        if not weakly_connected(tentative, original_entities if preserve_original_entities else None):
            rejections["would_disconnect"] += 1
            continue
        tentative_metrics = compute_graph_metrics(tentative, allocation)
        if tentative_metrics["allocated_relation_coverage_count"] != len(allocated_relations):
            rejections["would_drop_relation_coverage"] += 1
            continue
        if not allow_deficit_increase and float(tentative_metrics["total_deficit"]) > current_deficit + 1e-9:
            rejections["increases_total_deficit"] += 1
            continue
        current_triples = tentative
        current_deficit = float(tentative_metrics["total_deficit"])
        relation_counts[relation] -= 1
        current = [record for record in current if record.triple != triple]
        accepted_row = dict(row)
        accepted_row["accepted_order"] = len(accepted) + 1
        accepted.append(accepted_row)
    final_entities = {entity for h, _r, t in current_triples for entity in (h, t)}
    stats = {
        "original_entity_count": len(original_entities),
        "final_original_entities_present_count": len(original_entities & final_entities),
        "dropped_original_entity_count": len(original_entities - final_entities),
        "preserve_original_entities": preserve_original_entities,
        "allow_unverified_safe_deletions": allow_unverified_safe_deletions,
        "allow_deficit_increase": allow_deficit_increase,
        "safe_after_additions_false_skipped_count": rejections.get("safe_after_additions_false", 0),
        "drops_original_entity_rejected_count": rejections.get("drops_original_entity", 0),
        "increases_total_deficit_rejected_count": rejections.get("increases_total_deficit", 0),
    }
    return current, accepted, dict(sorted(rejections.items())), stats


def write_csv_rows(path: str | Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def exact_best_subset(
    candidates: Sequence[dict[str, Any]],
    max_additions: int,
    objective: Callable[[tuple[dict[str, Any], ...]], float],
) -> tuple[list[dict[str, Any]], float]:
    best_subset: tuple[dict[str, Any], ...] = ()
    best_score = float("-inf")
    for size in range(0, max_additions + 1):
        for subset in itertools.combinations(candidates, size):
            score = objective(subset)
            if score > best_score:
                best_score = score
                best_subset = subset
    return list(best_subset), best_score


def greedy_score_subset(candidates: Sequence[dict[str, Any]], max_additions: int) -> list[dict[str, Any]]:
    return sorted(candidates, key=lambda row: (-float(row.get("candidate_score", 0.0)), str(row)))[:max_additions]
