from __future__ import annotations

"""
Connectivity-aware, pattern-aware pruning for an over-connected but imbalanced KG.

Purpose
-------
This module implements a production-style pruning pipeline for the specific case
where a graph is already structurally strong, but pattern balance is poor because
one or a few relations are heavily overrepresented, for example P31 driving a
composition surplus.

The algorithm is intentionally conservative:
- It only considers removing triples whose removal is expected to improve pattern
  balance.
- It protects weak pattern buckets, especially symmetric, by default.
- It avoids structurally dangerous removals, especially graph bridges and low
  redundancy edges.
- It runs in batches and periodically recomputes graph diagnostics.

Design goals
------------
1. Reproducibility
2. Auditability
3. Modularity
4. Incremental extensibility

This file is written to be usable as a standalone script, but it is also
structured so it can be imported into your pipeline later.

Important scope note
--------------------
This is not a global optimizer. It is a principled greedy local pruning engine.
That is deliberate: the thesis problem is multi-objective and conflicting, so a
local edit framework is easier to defend and iterate on than a large opaque
optimizer.

Expected input graph format
---------------------------
JSONL rows with at least:
- h: head entity id
- r: relation id
- t: tail entity id

Optional fields are preserved verbatim.

Expected metadata inputs
------------------------
1. relation -> pattern set mapping
2. target counts by pattern, for example composition=5000
3. optional relation target caps, if you want relation-level pruning pressure

Known TODOs
-----------
- TODO: Integrate with your existing run manifests and stage directories.
- TODO: Replace simple local redundancy proxies with more domain-specific graph diagnostics if needed.
- TODO: Add optional directed-graph checks if weak connectivity is not sufficient for your final criterion.
- TODO: Add relation genericity penalties from stage01 if you want pruning to favor removing generic relations.
- TODO: Add exact per-component preservation constraints if a component-sensitive pruning policy is required.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple
import argparse
import collections
import csv
import json
import math
import statistics
import time

import networkx as nx


# -----------------------------------------------------------------------------
# IO utilities
# -----------------------------------------------------------------------------


def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {e}") from e



def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)



def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)



def write_json(path: Path, payload: dict) -> None:
    def _jsonable(value: object) -> object:
        if isinstance(value, dict):
            return {str(k): _jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_jsonable(v) for v in value]
        if isinstance(value, tuple):
            return [_jsonable(v) for v in value]
        if isinstance(value, set):
            return sorted(_jsonable(v) for v in value)
        return value

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(_jsonable(payload), f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


# -----------------------------------------------------------------------------
# Core data models
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Triple:
    h: str
    r: str
    t: str
    row: dict
    triple_id: str

    @staticmethod
    def from_row(row: Mapping[str, object]) -> "Triple":
        h = str(row["h"])
        r = str(row["r"])
        t = str(row["t"])
        triple_id = str(row.get("triple_id") or f"{h}|{r}|{t}")
        return Triple(h=h, r=r, t=t, row=dict(row), triple_id=triple_id)


@dataclass
class PatternTargets:
    expected: Dict[str, int]


@dataclass
class PrunerConfig:
    protected_patterns: Set[str] = field(default_factory=lambda: {"symmetric"})
    hard_protect_patterns_below_target: bool = True
    relation_overcap_min_excess: int = 1
    pattern_surplus_weight: float = 10.0
    pattern_deficit_penalty_weight: float = 25.0
    protected_pattern_penalty_weight: float = 40.0
    relation_overcap_weight: float = 2.0
    bridge_penalty: float = 1_000_000.0
    low_degree_penalty: float = 50.0
    low_degree_threshold: int = 2
    articulation_endpoint_penalty: float = 20.0
    local_redundancy_bonus: float = 5.0
    common_neighbor_bonus_cap: int = 10
    same_component_cycle_bonus: float = 2.0
    max_batch_removals: int = 250
    max_rounds: int = 100
    max_total_removals: Optional[int] = None
    recompute_every_batch: bool = True
    stop_when_all_pattern_surpluses_zero: bool = False
    allow_relation_level_pruning_even_if_pattern_neutral: bool = False
    selection_mode: str = "sequential"
    dry_run: bool = False
    verbose: bool = False


@dataclass
class RemovalDecision:
    triple_id: str
    relation: str
    score: float
    balance_gain: float
    structural_penalty: float
    reasons: List[str]


@dataclass
class GraphSnapshot:
    total_triples: int
    total_entities: int
    support_edge_count: int
    parallel_edge_pair_count: int
    weak_component_count: int
    largest_component_size: int
    largest_component_ratio: float
    relation_counts: Dict[str, int]
    pattern_counts: Dict[str, int]
    relation_overcap: Dict[str, int]
    pattern_surplus: Dict[str, int]
    pattern_deficit: Dict[str, int]


# -----------------------------------------------------------------------------
# Pattern and relation accounting
# -----------------------------------------------------------------------------


class PatternIndex:
    """
    Stores relation -> pattern-set mappings and computes observed pattern counts.
    A triple contributes once to every pattern attached to its relation.
    """

    def __init__(self, relation_to_patterns: Mapping[str, Sequence[str]]) -> None:
        self.relation_to_patterns: Dict[str, Tuple[str, ...]] = {
            rel: tuple(sorted({str(p) for p in patterns}))
            for rel, patterns in relation_to_patterns.items()
        }

    def patterns_for_relation(self, relation: str) -> Tuple[str, ...]:
        return self.relation_to_patterns.get(relation, tuple())

    def compute_pattern_counts(self, triples: Sequence[Triple]) -> Dict[str, int]:
        counts: Dict[str, int] = collections.Counter()
        for triple in triples:
            for pattern in self.patterns_for_relation(triple.r):
                counts[pattern] += 1
        return dict(counts)


# -----------------------------------------------------------------------------
# Graph state
# -----------------------------------------------------------------------------


class KGState:
    def __init__(
        self,
        triples: Sequence[Triple],
        pattern_index: PatternIndex,
        pattern_targets: PatternTargets,
        relation_targets: Optional[Mapping[str, int]] = None,
    ) -> None:
        self.pattern_index = pattern_index
        self.pattern_targets = pattern_targets
        self.relation_targets: Dict[str, int] = dict(relation_targets or {})

        self.triples_by_id: Dict[str, Triple] = {t.triple_id: t for t in triples}
        if len(self.triples_by_id) != len(triples):
            raise ValueError("Duplicate triple_id detected in input graph.")

        self.relation_counts: Dict[str, int] = collections.Counter(t.r for t in triples)
        self.pattern_counts: Dict[str, int] = self.pattern_index.compute_pattern_counts(triples)
        self.pair_counts: Dict[frozenset[str], int] = collections.Counter()

        self.graph = nx.Graph()
        for t in triples:
            edge_key = self.edge_key(t.h, t.t)
            self.pair_counts[edge_key] += 1
            if self.pair_counts[edge_key] == 1:
                self.graph.add_edge(t.h, t.t)

    @staticmethod
    def edge_key(h: str, t: str) -> frozenset[str]:
        return frozenset((h, t))

    def triples(self) -> List[Triple]:
        return list(self.triples_by_id.values())

    def pattern_surplus(self) -> Dict[str, int]:
        return {
            p: max(0, self.pattern_counts.get(p, 0) - expected)
            for p, expected in self.pattern_targets.expected.items()
        }

    def pattern_deficit(self) -> Dict[str, int]:
        return {
            p: max(0, expected - self.pattern_counts.get(p, 0))
            for p, expected in self.pattern_targets.expected.items()
        }

    def relation_overcap(self) -> Dict[str, int]:
        return {
            rel: max(0, self.relation_counts.get(rel, 0) - cap)
            for rel, cap in self.relation_targets.items()
        }

    def snapshot(self) -> GraphSnapshot:
        components = list(nx.connected_components(self.graph))
        largest_size = max((len(c) for c in components), default=0)
        total_entities = self.graph.number_of_nodes()
        return GraphSnapshot(
            total_triples=len(self.triples_by_id),
            total_entities=total_entities,
            support_edge_count=self.graph.number_of_edges(),
            parallel_edge_pair_count=sum(1 for count in self.pair_counts.values() if count > 1),
            weak_component_count=len(components),
            largest_component_size=largest_size,
            largest_component_ratio=(largest_size / total_entities if total_entities else 0.0),
            relation_counts=dict(self.relation_counts),
            pattern_counts=dict(self.pattern_counts),
            relation_overcap=self.relation_overcap(),
            pattern_surplus=self.pattern_surplus(),
            pattern_deficit=self.pattern_deficit(),
        )

    def remove_triple(self, triple_id: str) -> None:
        triple = self.triples_by_id.pop(triple_id)
        self.relation_counts[triple.r] -= 1
        if self.relation_counts[triple.r] <= 0:
            self.relation_counts.pop(triple.r, None)

        for pattern in self.pattern_index.patterns_for_relation(triple.r):
            self.pattern_counts[pattern] = self.pattern_counts.get(pattern, 0) - 1
            if self.pattern_counts[pattern] <= 0:
                self.pattern_counts.pop(pattern, None)

        edge_key = self.edge_key(triple.h, triple.t)
        self.pair_counts[edge_key] -= 1
        if self.pair_counts[edge_key] <= 0:
            self.pair_counts.pop(edge_key, None)
            if self.graph.has_edge(triple.h, triple.t):
                self.graph.remove_edge(triple.h, triple.t)

                if self.graph.degree(triple.h) == 0:
                    self.graph.remove_node(triple.h)
                if self.graph.has_node(triple.t) and self.graph.degree(triple.t) == 0:
                    self.graph.remove_node(triple.t)


# -----------------------------------------------------------------------------
# Candidate scoring
# -----------------------------------------------------------------------------


class TripleRemovalScorer:
    def __init__(self, config: PrunerConfig) -> None:
        self.config = config

    def score_candidates(self, state: KGState) -> List[RemovalDecision]:
        graph = state.graph
        bridges: Set[frozenset[str]] = {
            frozenset((u, v)) for u, v in nx.bridges(graph)
        }
        articulation_points: Set[str] = set(nx.articulation_points(graph))
        pattern_surplus = state.pattern_surplus()
        pattern_deficit = state.pattern_deficit()
        relation_overcap = state.relation_overcap()

        decisions: List[RemovalDecision] = []
        for triple in state.triples():
            decision = self._score_one(
                triple=triple,
                state=state,
                bridges=bridges,
                articulation_points=articulation_points,
                pattern_surplus=pattern_surplus,
                pattern_deficit=pattern_deficit,
                relation_overcap=relation_overcap,
            )
            if decision is not None:
                decisions.append(decision)

        decisions.sort(key=lambda d: d.score, reverse=True)
        return decisions

    def _score_one(
        self,
        triple: Triple,
        state: KGState,
        bridges: Set[frozenset[str]],
        articulation_points: Set[str],
        pattern_surplus: Mapping[str, int],
        pattern_deficit: Mapping[str, int],
        relation_overcap: Mapping[str, int],
    ) -> Optional[RemovalDecision]:
        reasons: List[str] = []
        patterns = state.pattern_index.patterns_for_relation(triple.r)
        if not patterns and not self.config.allow_relation_level_pruning_even_if_pattern_neutral:
            return None

        # Hard protect relations that do not currently help reduce any surplus and
        # are not relation-overcap, unless explicitly allowed.
        contributes_to_surplus = any(pattern_surplus.get(p, 0) > 0 for p in patterns)
        rel_overcap = relation_overcap.get(triple.r, 0)
        if not contributes_to_surplus and rel_overcap < self.config.relation_overcap_min_excess:
            return None

        if self.config.hard_protect_patterns_below_target:
            for p in patterns:
                if p in self.config.protected_patterns and pattern_deficit.get(p, 0) > 0:
                    return None

        balance_gain = 0.0
        for p in patterns:
            surplus = pattern_surplus.get(p, 0)
            deficit = pattern_deficit.get(p, 0)
            if surplus > 0:
                balance_gain += self.config.pattern_surplus_weight
                reasons.append(f"reduces_surplus:{p}")
            if deficit > 0:
                balance_gain -= self.config.pattern_deficit_penalty_weight
                reasons.append(f"hurts_deficit:{p}")
            if p in self.config.protected_patterns:
                balance_gain -= self.config.protected_pattern_penalty_weight
                reasons.append(f"protected_pattern:{p}")

        if rel_overcap >= self.config.relation_overcap_min_excess:
            balance_gain += self.config.relation_overcap_weight * rel_overcap
            reasons.append(f"relation_overcap:{triple.r}:{rel_overcap}")

        structural_penalty = 0.0
        edge_key = state.edge_key(triple.h, triple.t)
        pair_count = int(state.pair_counts.get(edge_key, 0))
        if pair_count <= 1 and edge_key in bridges:
            structural_penalty += self.config.bridge_penalty
            reasons.append("bridge")

        deg_h = state.graph.degree(triple.h)
        deg_t = state.graph.degree(triple.t)
        if deg_h <= self.config.low_degree_threshold:
            structural_penalty += self.config.low_degree_penalty
            reasons.append(f"low_degree_head:{deg_h}")
        if deg_t <= self.config.low_degree_threshold:
            structural_penalty += self.config.low_degree_penalty
            reasons.append(f"low_degree_tail:{deg_t}")

        if triple.h in articulation_points:
            structural_penalty += self.config.articulation_endpoint_penalty
            reasons.append("articulation_head")
        if triple.t in articulation_points:
            structural_penalty += self.config.articulation_endpoint_penalty
            reasons.append("articulation_tail")

        common_neighbors = len(list(nx.common_neighbors(state.graph, triple.h, triple.t)))
        common_neighbor_bonus = min(common_neighbors, self.config.common_neighbor_bonus_cap) * self.config.local_redundancy_bonus
        if common_neighbor_bonus > 0:
            structural_penalty -= common_neighbor_bonus
            reasons.append(f"common_neighbors:{common_neighbors}")

        # Cheap cycle / local redundancy proxy. If endpoints are still connected by
        # some short path in the graph after edge removal, the edge is more redundant.
        # TODO: For very large graphs, benchmark whether this should be skipped or sampled.
        if pair_count > 1:
            alt_path_len = 1
            reasons.append(f"parallel_support:{pair_count}")
        elif state.graph.has_edge(triple.h, triple.t):
            state.graph.remove_edge(triple.h, triple.t)
            try:
                alt_path_len = nx.shortest_path_length(state.graph, source=triple.h, target=triple.t)
            except nx.NetworkXNoPath:
                alt_path_len = None
            finally:
                state.graph.add_edge(triple.h, triple.t)
        else:
            alt_path_len = None

        if alt_path_len is not None and alt_path_len <= 4:
            structural_penalty -= self.config.same_component_cycle_bonus * (5 - alt_path_len)
            reasons.append(f"alt_path_len:{alt_path_len}")

        score = balance_gain - structural_penalty
        if score <= 0:
            return None

        return RemovalDecision(
            triple_id=triple.triple_id,
            relation=triple.r,
            score=score,
            balance_gain=balance_gain,
            structural_penalty=structural_penalty,
            reasons=reasons,
        )


# -----------------------------------------------------------------------------
# Pruning engine
# -----------------------------------------------------------------------------


@dataclass
class BatchLog:
    round_index: int
    candidate_count: int
    selected_count: int
    selection_mode: str
    removed_triple_ids: List[str]
    pre_snapshot: GraphSnapshot
    post_snapshot: GraphSnapshot
    top_selected_preview: List[dict]


@dataclass
class RunReport:
    started_at_epoch: float
    finished_at_epoch: float
    duration_sec: float
    config: dict
    initial_snapshot: dict
    final_snapshot: dict
    total_removed: int
    rounds_completed: int
    batch_logs: List[dict]


class BalanceAwarePruner:
    def __init__(self, config: PrunerConfig) -> None:
        self.config = config
        self.scorer = TripleRemovalScorer(config=config)

    def run(self, state: KGState) -> Tuple[KGState, RunReport]:
        started = time.time()
        initial_snapshot = state.snapshot()
        batch_logs: List[BatchLog] = []
        total_removed = 0

        for round_index in range(1, self.config.max_rounds + 1):
            pre = state.snapshot()
            if self.config.stop_when_all_pattern_surpluses_zero and all(v == 0 for v in pre.pattern_surplus.values()):
                break

            if self.config.max_total_removals is not None:
                remaining_budget = self.config.max_total_removals - total_removed
                if remaining_budget <= 0:
                    break
            else:
                remaining_budget = self.config.max_batch_removals

            round_budget = min(self.config.max_batch_removals, remaining_budget)
            if round_budget <= 0:
                break

            selected: List[RemovalDecision]
            candidate_count: int
            mutated_during_selection = False
            if self.config.selection_mode == "sequential" and not self.config.dry_run:
                selected, candidate_count = self._select_round_sequential(state=state, round_budget=round_budget)
                mutated_during_selection = True
            else:
                decisions = self.scorer.score_candidates(state)
                candidate_count = len(decisions)
                selected = decisions[:round_budget]

            if not selected:
                if self.config.verbose:
                    print(f"[round {round_index}] no removable candidates remain")
                break

            if self.config.verbose:
                top = selected[0]
                print(
                    f"[round {round_index}] candidate_count={candidate_count} selected={len(selected)} "
                    f"top_score={top.score:.3f} top_relation={top.relation}"
                )

            if not self.config.dry_run and not mutated_during_selection:
                for decision in selected:
                    state.remove_triple(decision.triple_id)

            total_removed += len(selected)
            post = state.snapshot()
            batch_logs.append(
                BatchLog(
                    round_index=round_index,
                    candidate_count=candidate_count,
                    selected_count=len(selected),
                    selection_mode=self.config.selection_mode if not self.config.dry_run else "dry_run_preview",
                    removed_triple_ids=[d.triple_id for d in selected],
                    pre_snapshot=pre,
                    post_snapshot=post,
                    top_selected_preview=[
                        {
                            "triple_id": d.triple_id,
                            "relation": d.relation,
                            "score": d.score,
                            "balance_gain": d.balance_gain,
                            "structural_penalty": d.structural_penalty,
                            "reasons": d.reasons,
                        }
                        for d in selected[: min(20, len(selected))]
                    ],
                )
            )

            if self.config.max_total_removals is not None and total_removed >= self.config.max_total_removals:
                break

        finished = time.time()
        report = RunReport(
            started_at_epoch=started,
            finished_at_epoch=finished,
            duration_sec=finished - started,
            config=asdict(self.config),
            initial_snapshot=asdict(initial_snapshot),
            final_snapshot=asdict(state.snapshot()),
            total_removed=total_removed,
            rounds_completed=len(batch_logs),
            batch_logs=[
                {
                    "round_index": b.round_index,
                    "candidate_count": b.candidate_count,
                    "selected_count": b.selected_count,
                    "selection_mode": b.selection_mode,
                    "removed_triple_ids": b.removed_triple_ids,
                    "pre_snapshot": asdict(b.pre_snapshot),
                    "post_snapshot": asdict(b.post_snapshot),
                    "top_selected_preview": b.top_selected_preview,
                }
                for b in batch_logs
            ],
        )
        return state, report

    def _select_round_sequential(self, state: KGState, round_budget: int) -> Tuple[List[RemovalDecision], int]:
        selected: List[RemovalDecision] = []
        candidate_count = 0
        for step_idx in range(round_budget):
            decisions = self.scorer.score_candidates(state)
            if step_idx == 0:
                candidate_count = len(decisions)
            if not decisions:
                break
            decision = decisions[0]
            selected.append(decision)
            state.remove_triple(decision.triple_id)
        return selected, candidate_count


# -----------------------------------------------------------------------------
# Input loaders
# -----------------------------------------------------------------------------



def load_relation_to_patterns(path: Path) -> Dict[str, List[str]]:
    payload = load_json(path)

    if isinstance(payload, dict):
        if "relation_to_patterns" in payload and isinstance(payload["relation_to_patterns"], dict):
            return {
                str(rel): [str(p) for p in patterns]
                for rel, patterns in payload["relation_to_patterns"].items()
            }
        return {str(rel): [str(p) for p in patterns] for rel, patterns in payload.items()}

    raise ValueError("Unsupported relation-to-pattern mapping format.")


def load_allocation_manifest(path: Path) -> Tuple[Dict[str, List[str]], PatternTargets, Dict[str, int]]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Allocation manifest must be a JSON object.")

    relation_to_patterns: Dict[str, Set[str]] = collections.defaultdict(set)
    pattern_targets: Dict[str, int] = {}
    relation_targets: Dict[str, int] = collections.Counter()

    pattern_groups = payload.get("pattern_groups")
    if isinstance(pattern_groups, dict):
        for pattern, relations in pattern_groups.items():
            for relation in relations:
                relation_to_patterns[str(relation)].add(str(pattern))

    eta_per_group = payload.get("eta_per_group")
    if isinstance(eta_per_group, dict):
        pattern_targets.update({str(pattern): int(value) for pattern, value in eta_per_group.items()})

    allocations = payload.get("allocations")
    if isinstance(allocations, list):
        fallback_pattern_targets: Dict[str, int] = {}
        for row in allocations:
            relation = str(row["relation"])
            pattern = str(row.get("pattern", ""))
            if pattern:
                relation_to_patterns[relation].add(pattern)

            eta = int(row.get("eta_integer", row.get("target", 0)) or 0)
            relation_targets[relation] += eta

            eta_total = row.get("eta_total")
            if pattern and eta_total is not None:
                fallback_pattern_targets[pattern] = max(
                    int(fallback_pattern_targets.get(pattern, 0)),
                    int(eta_total),
                )

        if not pattern_targets:
            pattern_targets.update(fallback_pattern_targets)

    if not relation_to_patterns:
        raise ValueError("Allocation manifest did not expose any relation->pattern mapping.")
    if not pattern_targets:
        raise ValueError("Allocation manifest did not expose any pattern targets.")

    return (
        {relation: sorted(patterns) for relation, patterns in relation_to_patterns.items()},
        PatternTargets(expected=pattern_targets),
        dict(relation_targets),
    )



def load_pattern_targets(path: Path) -> PatternTargets:
    payload = load_json(path)
    if "expected" in payload and isinstance(payload["expected"], dict):
        return PatternTargets(expected={str(k): int(v) for k, v in payload["expected"].items()})
    return PatternTargets(expected={str(k): int(v) for k, v in payload.items()})



def load_relation_targets(path: Optional[Path]) -> Dict[str, int]:
    if path is None:
        return {}

    payload = load_json(path)
    if isinstance(payload, dict):
        if "relation_targets" in payload and isinstance(payload["relation_targets"], dict):
            return {str(k): int(v) for k, v in payload["relation_targets"].items()}
        return {str(k): int(v) for k, v in payload.items()}

    if isinstance(payload, list):
        out: Dict[str, int] = collections.Counter()
        for row in payload:
            rel = str(row["relation"])
            eta = int(row.get("eta_integer", row.get("target", 0)))
            out[rel] += eta
        return dict(out)

    raise ValueError("Unsupported relation target format.")



def normalize_graph_row(row: Mapping[str, object], source: Path, row_no: int) -> dict:
    field_map = {str(key).strip().lower(): key for key in row.keys()}

    def get_field(*candidates: str) -> str:
        for candidate in candidates:
            if candidate in field_map:
                value = row[field_map[candidate]]
                if value is None:
                    break
                return str(value)
        raise ValueError(f"Missing required graph field {candidates} in {source}:{row_no}")

    normalized = dict(row)
    normalized["h"] = get_field("h", "head")
    normalized["r"] = get_field("r", "relation", "rel")
    normalized["t"] = get_field("t", "tail")
    return normalized


def load_triples(path: Path) -> List[Triple]:
    if path.suffix.lower() == ".csv":
        rows: List[Triple] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row_no, row in enumerate(reader, start=2):
                rows.append(Triple.from_row(normalize_graph_row(row, source=path, row_no=row_no)))
        return rows
    return [Triple.from_row(row) for row in iter_jsonl(path)]


# -----------------------------------------------------------------------------
# Output helpers
# -----------------------------------------------------------------------------



def export_state_rows(state: KGState) -> Iterator[dict]:
    for triple in state.triples():
        row = dict(triple.row)
        row.setdefault("triple_id", triple.triple_id)
        yield row


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------



def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Connectivity-aware, pattern-aware KG pruner")
    p.add_argument("--input_graph", type=Path, required=True, help="Input graph triples JSONL or CSV")
    p.add_argument("--allocation_manifest", type=Path, default=None, help="Single JSON source with allocations, pattern_groups, and eta_per_group.")
    p.add_argument("--relation_patterns", type=Path, default=None, help="JSON mapping relation -> pattern list")
    p.add_argument("--pattern_targets", type=Path, default=None, help="JSON mapping pattern -> expected target")
    p.add_argument("--relation_targets", type=Path, default=None, help="Optional JSON mapping relation -> cap")
    p.add_argument("--out_graph", type=Path, required=True, help="Output pruned graph JSONL")
    p.add_argument("--out_report", type=Path, required=True, help="Output pruning report JSON")

    p.add_argument("--protected_pattern", action="append", default=None, help="Pattern to protect; repeatable")
    p.add_argument("--disable_hard_protect_patterns_below_target", action="store_true")

    p.add_argument("--max_batch_removals", type=int, default=250)
    p.add_argument("--max_rounds", type=int, default=100)
    p.add_argument("--max_total_removals", type=int, default=None)
    p.add_argument("--stop_when_all_pattern_surpluses_zero", action="store_true")
    p.add_argument("--allow_relation_level_pruning_even_if_pattern_neutral", action="store_true")
    p.add_argument(
        "--selection_mode",
        choices=("sequential", "batch"),
        default="sequential",
        help="Sequential is safer because each accepted removal is rescored on the updated graph; batch is faster but riskier.",
    )

    p.add_argument("--pattern_surplus_weight", type=float, default=10.0)
    p.add_argument("--pattern_deficit_penalty_weight", type=float, default=25.0)
    p.add_argument("--protected_pattern_penalty_weight", type=float, default=40.0)
    p.add_argument("--relation_overcap_weight", type=float, default=2.0)
    p.add_argument("--bridge_penalty", type=float, default=1_000_000.0)
    p.add_argument("--low_degree_penalty", type=float, default=50.0)
    p.add_argument("--low_degree_threshold", type=int, default=2)
    p.add_argument("--articulation_endpoint_penalty", type=float, default=20.0)
    p.add_argument("--local_redundancy_bonus", type=float, default=5.0)
    p.add_argument("--common_neighbor_bonus_cap", type=int, default=10)
    p.add_argument("--same_component_cycle_bonus", type=float, default=2.0)

    p.add_argument("--dry_run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.allocation_manifest is not None:
        if args.relation_patterns is not None or args.pattern_targets is not None or args.relation_targets is not None:
            parser.error("Use either --allocation_manifest or the explicit relation/pattern target files, not both.")
    else:
        if args.relation_patterns is None or args.pattern_targets is None:
            parser.error("Provide --allocation_manifest or both --relation_patterns and --pattern_targets.")

    if not args.input_graph.exists():
        parser.error(f"--input_graph does not exist: {args.input_graph}")

    for attr in ("allocation_manifest", "relation_patterns", "pattern_targets", "relation_targets"):
        value = getattr(args, attr)
        if value is not None and not value.exists():
            parser.error(f"--{attr} does not exist: {value}")

    if args.out_graph.resolve() == args.input_graph.resolve():
        parser.error("--out_graph must differ from --input_graph.")
    if args.out_report.resolve() == args.input_graph.resolve():
        parser.error("--out_report must differ from --input_graph.")
    if args.out_graph.resolve() == args.out_report.resolve():
        parser.error("--out_graph and --out_report must differ.")

    if args.max_batch_removals <= 0:
        parser.error("--max_batch_removals must be > 0.")
    if args.max_rounds <= 0:
        parser.error("--max_rounds must be > 0.")
    if args.max_total_removals is not None and args.max_total_removals <= 0:
        parser.error("--max_total_removals must be > 0 when provided.")
    if args.low_degree_threshold < 0:
        parser.error("--low_degree_threshold must be >= 0.")

    numeric_must_be_non_negative = [
        ("pattern_surplus_weight", args.pattern_surplus_weight),
        ("pattern_deficit_penalty_weight", args.pattern_deficit_penalty_weight),
        ("protected_pattern_penalty_weight", args.protected_pattern_penalty_weight),
        ("relation_overcap_weight", args.relation_overcap_weight),
        ("bridge_penalty", args.bridge_penalty),
        ("low_degree_penalty", args.low_degree_penalty),
        ("articulation_endpoint_penalty", args.articulation_endpoint_penalty),
        ("local_redundancy_bonus", args.local_redundancy_bonus),
        ("common_neighbor_bonus_cap", args.common_neighbor_bonus_cap),
        ("same_component_cycle_bonus", args.same_component_cycle_bonus),
    ]
    for name, value in numeric_must_be_non_negative:
        if value < 0:
            parser.error(f"--{name} must be >= 0.")


def config_from_args(args: argparse.Namespace) -> PrunerConfig:
    return PrunerConfig(
        protected_patterns=set(args.protected_pattern or ["symmetric"]),
        hard_protect_patterns_below_target=not args.disable_hard_protect_patterns_below_target,
        pattern_surplus_weight=args.pattern_surplus_weight,
        pattern_deficit_penalty_weight=args.pattern_deficit_penalty_weight,
        protected_pattern_penalty_weight=args.protected_pattern_penalty_weight,
        relation_overcap_weight=args.relation_overcap_weight,
        bridge_penalty=args.bridge_penalty,
        low_degree_penalty=args.low_degree_penalty,
        low_degree_threshold=args.low_degree_threshold,
        articulation_endpoint_penalty=args.articulation_endpoint_penalty,
        local_redundancy_bonus=args.local_redundancy_bonus,
        common_neighbor_bonus_cap=args.common_neighbor_bonus_cap,
        same_component_cycle_bonus=args.same_component_cycle_bonus,
        max_batch_removals=args.max_batch_removals,
        max_rounds=args.max_rounds,
        max_total_removals=args.max_total_removals,
        stop_when_all_pattern_surpluses_zero=args.stop_when_all_pattern_surpluses_zero,
        allow_relation_level_pruning_even_if_pattern_neutral=args.allow_relation_level_pruning_even_if_pattern_neutral,
        selection_mode=args.selection_mode,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )



def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    validate_args(parser, args)

    if args.allocation_manifest is not None:
        relation_to_patterns, pattern_targets, relation_targets = load_allocation_manifest(args.allocation_manifest)
    else:
        relation_to_patterns = load_relation_to_patterns(args.relation_patterns)
        pattern_targets = load_pattern_targets(args.pattern_targets)
        relation_targets = load_relation_targets(args.relation_targets)
    triples = load_triples(args.input_graph)

    pattern_index = PatternIndex(relation_to_patterns=relation_to_patterns)
    state = KGState(
        triples=triples,
        pattern_index=pattern_index,
        pattern_targets=pattern_targets,
        relation_targets=relation_targets,
    )

    pruner = BalanceAwarePruner(config=config_from_args(args))
    final_state, report = pruner.run(state)

    write_jsonl(args.out_graph, export_state_rows(final_state))
    write_json(args.out_report, asdict(report))


if __name__ == "__main__":
    main()
