from __future__ import annotations

"""
Connectivity-aware, pattern-aware pruning for an over-connected but imbalanced KG.

Purpose
-------
This module implements a production-style pruning pipeline for the specific case
where a graph is already structurally strong, but pattern balance is poor because
one or a few relations are heavily overrepresented, for example P31 driving a
composition surplus.

The algorithm is intentionally lexicographic in spirit:
- It only considers removing triples whose removal is expected to improve pattern
  balance.
- It then discounts removals that are likely to damage density and local path
  structure.
- It still protects structurally dangerous cases, especially graph bridges and
  low-redundancy edges.
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

Extension points
----------------
- The local redundancy proxies are intentionally simple so the pruning logic stays
  auditable.
- The script uses weak connectivity on the undirected entity projection because
  that is the structural criterion used by the surrounding pipeline.
- Relation genericity or per-component preservation rules can be layered on top
  later without changing the core pruning workflow.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Set, Tuple
import argparse
import collections
import csv
import json
import math
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
    protected_relations: Set[str] = field(default_factory=set)
    hard_relation_min_count: Dict[str, int] = field(default_factory=dict)
    hard_protect_patterns_below_target: bool = True
    hard_preserve_largest_component: bool = True
    relation_overcap_min_excess: int = 1
    pattern_surplus_weight: float = 10.0
    pattern_deficit_penalty_weight: float = 25.0
    protected_pattern_penalty_weight: float = 40.0
    relation_overcap_weight: float = 2.0
    # Default changed from implicit linear pressure to a saturated log1p signal so
    # a single dominant relation does not absorb an entire round by raw overcap.
    relation_overcap_mode: str = "log1p"
    relation_overcap_cap: float = 25.0
    bridge_penalty: float = 1_000_000.0
    low_degree_penalty: float = 50.0
    low_degree_threshold: int = 2
    articulation_endpoint_penalty: float = 20.0
    local_redundancy_bonus: float = 5.0
    common_neighbor_bonus_cap: int = 10
    same_component_cycle_bonus: float = 2.0
    # Relative density penalties are anchored to the current graph and protect
    # against sudden local collapse.
    density_triples_per_entity_penalty: float = 10.0
    density_entities_per_triple_penalty: float = 10.0
    # Absolute target-aware floors are separate from the relative penalties.
    # Leaving them as None means the run does not enforce benchmark density goals.
    target_min_triples_per_entity: Optional[float] = None
    target_max_entities_per_triple: Optional[float] = None
    target_min_average_participation: Optional[float] = None
    projected_low_degree_creation_penalty: float = 15.0
    two_path_loss_penalty: float = 1.0
    hard_guard_projected_triples_gt_entities: bool = False
    max_batch_removals: int = 250
    max_rounds: int = 100
    max_total_removals: Optional[int] = None
    max_fraction_per_relation_per_round: Optional[float] = 0.25
    max_removals_per_relation_per_round: Optional[int] = None
    # Final runs should prefer reject_round so a bad batch does not mutate the graph.
    batch_guard_action: str = "reject_round"
    min_post_round_triples_per_entity: Optional[float] = None
    max_post_round_entities_per_triple: Optional[float] = None
    min_post_round_average_participation: Optional[float] = None
    max_post_round_weak_component_count: Optional[int] = None
    min_post_round_largest_component_ratio: Optional[float] = None
    recompute_every_batch: bool = True
    stop_when_all_pattern_surpluses_zero: bool = False
    allow_relation_level_pruning_even_if_pattern_neutral: bool = False
    selection_mode: str = "sequential"
    debug_top_candidates: int = 0
    debug_relations: Set[str] = field(default_factory=set)
    debug_dump_path: Optional[str] = None
    dry_run: bool = False
    verbose: bool = False


@dataclass
class RemovalDecision:
    triple_id: str
    relation: str
    score: float
    balance_gain: float
    structural_penalty: float
    relative_density_penalty: float
    target_density_penalty: float
    density_penalty: float
    estimated_two_path_loss: float
    reasons: List[str]


@dataclass
class GraphSnapshot:
    total_triples: int
    total_entities: int
    triples_minus_entities: int
    support_edge_count: int
    parallel_edge_pair_count: int
    weak_component_count: int
    largest_component_size: int
    largest_component_ratio: float
    triples_per_entity: float
    entities_per_triple: float
    average_participation: float
    low_degree_node_count: int
    low_degree_node_ratio: float
    two_path_proxy: int
    relation_counts: Dict[str, int]
    pattern_counts: Dict[str, int]
    relation_overcap: Dict[str, int]
    pattern_surplus: Dict[str, int]
    pattern_deficit: Dict[str, int]


@dataclass(frozen=True)
class CandidateProjection:
    projected_triples: int
    projected_entities: int
    projected_triples_per_entity: float
    projected_entities_per_triple: float
    projected_average_participation: float
    low_degree_nodes_created: int
    estimated_two_path_loss: int


@dataclass
class RoundSelectionResult:
    selected: List[RemovalDecision]
    removed_triples: List[Triple]
    candidate_count: int
    guard_rejections: int
    throttle_rejections: int
    relation_floor_rejections: int
    guard_rejections_by_relation: Dict[str, int]
    throttle_rejections_by_relation: Dict[str, int]
    relation_floor_rejections_by_relation: Dict[str, int]
    debug_summary: Optional[dict] = None


@dataclass
class RoundGuardStatus:
    triggered: bool
    stop_pruning: bool
    reject_round: bool
    density_guard_triggered: bool
    connectivity_guard_triggered: bool
    target_floor_guard_triggered: bool
    messages: List[str]


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

    def two_path_proxy(self) -> int:
        return sum((deg * (deg - 1)) // 2 for _, deg in self.graph.degree())

    def low_degree_node_count(self, threshold: int) -> int:
        if threshold < 0:
            return 0
        return sum(1 for _, deg in self.graph.degree() if deg <= threshold)

    def snapshot(self, low_degree_threshold: int) -> GraphSnapshot:
        components = list(nx.connected_components(self.graph))
        largest_size = max((len(c) for c in components), default=0)
        total_entities = self.graph.number_of_nodes()
        total_triples = len(self.triples_by_id)
        triples_per_entity = (total_triples / total_entities) if total_entities else 0.0
        entities_per_triple = (total_entities / total_triples) if total_triples else 0.0
        average_participation = (2.0 * total_triples / total_entities) if total_entities else 0.0
        low_degree_nodes = self.low_degree_node_count(low_degree_threshold)
        return GraphSnapshot(
            total_triples=total_triples,
            total_entities=total_entities,
            triples_minus_entities=total_triples - total_entities,
            support_edge_count=self.graph.number_of_edges(),
            parallel_edge_pair_count=sum(1 for count in self.pair_counts.values() if count > 1),
            weak_component_count=len(components),
            largest_component_size=largest_size,
            largest_component_ratio=(largest_size / total_entities if total_entities else 0.0),
            triples_per_entity=triples_per_entity,
            entities_per_triple=entities_per_triple,
            average_participation=average_participation,
            low_degree_node_count=low_degree_nodes,
            low_degree_node_ratio=(low_degree_nodes / total_entities if total_entities else 0.0),
            two_path_proxy=self.two_path_proxy(),
            relation_counts=dict(self.relation_counts),
            pattern_counts=dict(self.pattern_counts),
            relation_overcap=self.relation_overcap(),
            pattern_surplus=self.pattern_surplus(),
            pattern_deficit=self.pattern_deficit(),
        )

    def largest_component_nodes(self) -> Set[str]:
        components = list(nx.connected_components(self.graph))
        if not components:
            return set()
        return set(max(components, key=len))

    def removal_preserves_largest_component(self, triple_id: str) -> bool:
        triple = self.triples_by_id[triple_id]
        edge_key = self.edge_key(triple.h, triple.t)
        pair_count = int(self.pair_counts.get(edge_key, 0))

        if pair_count > 1:
            return True
        if not self.graph.has_edge(triple.h, triple.t):
            return True

        largest_nodes = self.largest_component_nodes()
        if not largest_nodes:
            return True
        if triple.h not in largest_nodes or triple.t not in largest_nodes:
            return True

        self.graph.remove_edge(triple.h, triple.t)
        try:
            return nx.has_path(self.graph, triple.h, triple.t)
        finally:
            self.graph.add_edge(triple.h, triple.t)

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

    def add_triple(self, triple: Triple) -> None:
        if triple.triple_id in self.triples_by_id:
            raise ValueError(f"Cannot re-add existing triple_id: {triple.triple_id}")

        self.triples_by_id[triple.triple_id] = triple
        self.relation_counts[triple.r] += 1

        for pattern in self.pattern_index.patterns_for_relation(triple.r):
            self.pattern_counts[pattern] = self.pattern_counts.get(pattern, 0) + 1

        edge_key = self.edge_key(triple.h, triple.t)
        self.pair_counts[edge_key] += 1
        if self.pair_counts[edge_key] == 1:
            self.graph.add_edge(triple.h, triple.t)


# -----------------------------------------------------------------------------
# Candidate scoring
# -----------------------------------------------------------------------------


class TripleRemovalScorer:
    def __init__(self, config: PrunerConfig) -> None:
        self.config = config

    @staticmethod
    def reason_key(reason: str) -> str:
        return reason.split(":", 1)[0]

    def relation_overcap_reward(self, excess: int) -> float:
        if excess < self.config.relation_overcap_min_excess:
            return 0.0

        if self.config.relation_overcap_mode == "linear":
            scaled = float(excess)
        elif self.config.relation_overcap_mode == "sqrt":
            scaled = math.sqrt(float(excess))
        elif self.config.relation_overcap_mode == "log1p":
            scaled = math.log1p(float(excess))
        elif self.config.relation_overcap_mode == "capped_linear":
            scaled = min(float(excess), self.config.relation_overcap_cap)
        else:
            raise ValueError(f"Unsupported relation_overcap_mode: {self.config.relation_overcap_mode}")

        return self.config.relation_overcap_weight * scaled

    def relation_min_count(self, relation: str) -> Optional[int]:
        if relation in self.config.hard_relation_min_count:
            return self.config.hard_relation_min_count[relation]
        return None

    def project_candidate_removal(
        self,
        *,
        triple: Triple,
        state: KGState,
        degrees: Mapping[str, int],
        pair_count: int,
    ) -> CandidateProjection:
        total_triples = len(state.triples_by_id)
        total_entities = state.graph.number_of_nodes()
        edge_removed = pair_count <= 1

        removed_nodes: Set[str] = set()
        if edge_removed:
            if degrees.get(triple.h, 0) <= 1:
                removed_nodes.add(triple.h)
            if degrees.get(triple.t, 0) <= 1:
                removed_nodes.add(triple.t)

        projected_triples = max(0, total_triples - 1)
        projected_entities = max(0, total_entities - len(removed_nodes))

        projected_tpe = (projected_triples / projected_entities) if projected_entities else 0.0
        projected_et = (projected_entities / projected_triples) if projected_triples else 0.0
        projected_avg_participation = (2.0 * projected_triples / projected_entities) if projected_entities else 0.0

        low_degree_nodes_created = 0
        if edge_removed:
            unique_nodes = {triple.h, triple.t}
            for node in unique_nodes:
                before_deg = degrees.get(node, 0)
                if before_deg <= 0:
                    continue
                after_deg = before_deg - 1
                before_low = before_deg <= self.config.low_degree_threshold
                after_low = after_deg > 0 and after_deg <= self.config.low_degree_threshold
                if after_low and not before_low:
                    low_degree_nodes_created += 1

        estimated_two_path_loss = 0
        if edge_removed:
            deg_h = degrees.get(triple.h, 0)
            deg_t = degrees.get(triple.t, 0)
            estimated_two_path_loss = max(0, deg_h - 1) + max(0, deg_t - 1)

        return CandidateProjection(
            projected_triples=projected_triples,
            projected_entities=projected_entities,
            projected_triples_per_entity=projected_tpe,
            projected_entities_per_triple=projected_et,
            projected_average_participation=projected_avg_participation,
            low_degree_nodes_created=low_degree_nodes_created,
            estimated_two_path_loss=estimated_two_path_loss,
        )

    def _decision_debug_record(self, decision: RemovalDecision) -> dict:
        return {
            "triple_id": decision.triple_id,
            "relation": decision.relation,
            "score": decision.score,
            "balance_gain": decision.balance_gain,
            "structural_penalty": decision.structural_penalty,
            "relative_density_penalty": decision.relative_density_penalty,
            "target_density_penalty": decision.target_density_penalty,
            "density_penalty": decision.density_penalty,
            "estimated_two_path_loss": decision.estimated_two_path_loss,
            "reasons": decision.reasons,
        }

    def _build_debug_summary(
        self,
        *,
        debug_records: Sequence[RemovalDecision],
        debug_top_candidates: int,
        debug_relations: Set[str],
    ) -> dict:
        per_relation_scores: Dict[str, List[float]] = collections.defaultdict(list)
        positive_counts: Dict[str, int] = collections.Counter()
        for record in debug_records:
            per_relation_scores[record.relation].append(record.score)
            if record.score > 0:
                positive_counts[record.relation] += 1

        per_relation_stats: Dict[str, dict] = {}
        for relation in sorted(per_relation_scores):
            scores = per_relation_scores[relation]
            per_relation_stats[relation] = {
                "candidate_count": len(scores),
                "positive_score_candidate_count": positive_counts.get(relation, 0),
                "max_score": max(scores),
                "mean_score": (sum(scores) / len(scores) if scores else 0.0),
            }

        sorted_records = sorted(debug_records, key=lambda record: record.score, reverse=True)
        top_n = max(0, debug_top_candidates)
        top_candidates_overall = [
            self._decision_debug_record(record) for record in sorted_records[:top_n]
        ]
        if debug_relations:
            debug_relation_records = [
                record for record in sorted_records if record.relation in debug_relations
            ]
        else:
            debug_relation_records = []

        top_candidates_debug_relations = [
            self._decision_debug_record(record) for record in debug_relation_records[:top_n]
        ]

        return {
            "total_candidate_count": len(debug_records),
            "per_relation_candidate_count": {
                relation: stats["candidate_count"] for relation, stats in per_relation_stats.items()
            },
            "per_relation_positive_score_candidate_count": {
                relation: stats["positive_score_candidate_count"] for relation, stats in per_relation_stats.items()
            },
            "per_relation_max_score": {
                relation: stats["max_score"] for relation, stats in per_relation_stats.items()
            },
            "per_relation_mean_score": {
                relation: stats["mean_score"] for relation, stats in per_relation_stats.items()
            },
            "per_relation_stats": per_relation_stats,
            "top_candidates_overall": top_candidates_overall,
            "top_candidates_debug_relations": top_candidates_debug_relations,
        }

    def score_candidates(self, state: KGState, include_debug: bool = False) -> Tuple[List[RemovalDecision], Optional[dict]]:
        graph = state.graph
        bridges: Set[frozenset[str]] = {
            frozenset((u, v)) for u, v in nx.bridges(graph)
        }
        articulation_points: Set[str] = set(nx.articulation_points(graph))
        pattern_surplus = state.pattern_surplus()
        pattern_deficit = state.pattern_deficit()
        relation_overcap = state.relation_overcap()
        degrees = dict(graph.degree())
        total_triples = len(state.triples_by_id)
        total_entities = graph.number_of_nodes()
        current_triples_per_entity = (total_triples / total_entities) if total_entities else 0.0
        current_entities_per_triple = (total_entities / total_triples) if total_triples else 0.0

        decisions: List[RemovalDecision] = []
        debug_records: List[RemovalDecision] = []
        for triple in state.triples():
            decision = self._score_one(
                triple=triple,
                state=state,
                bridges=bridges,
                articulation_points=articulation_points,
                pattern_surplus=pattern_surplus,
                pattern_deficit=pattern_deficit,
                relation_overcap=relation_overcap,
                degrees=degrees,
                current_triples_per_entity=current_triples_per_entity,
                current_entities_per_triple=current_entities_per_triple,
            )
            if include_debug and decision is not None:
                debug_records.append(decision)
            if decision is not None and decision.score > 0:
                decisions.append(decision)

        decisions.sort(key=lambda d: d.score, reverse=True)
        debug_summary = None
        if include_debug:
            debug_summary = self._build_debug_summary(
                debug_records=debug_records,
                debug_top_candidates=self.config.debug_top_candidates,
                debug_relations=self.config.debug_relations,
            )
        return decisions, debug_summary

    def _score_one(
        self,
        triple: Triple,
        state: KGState,
        bridges: Set[frozenset[str]],
        articulation_points: Set[str],
        pattern_surplus: Mapping[str, int],
        pattern_deficit: Mapping[str, int],
        relation_overcap: Mapping[str, int],
        degrees: Mapping[str, int],
        current_triples_per_entity: float,
        current_entities_per_triple: float,
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

        relation_pressure = self.relation_overcap_reward(rel_overcap)
        if relation_pressure > 0:
            balance_gain += relation_pressure
            reasons.append(
                f"relation_overcap:{triple.r}:{rel_overcap}:mode={self.config.relation_overcap_mode}"
            )

        structural_penalty = 0.0
        edge_key = state.edge_key(triple.h, triple.t)
        pair_count = int(state.pair_counts.get(edge_key, 0))
        projection = self.project_candidate_removal(
            triple=triple,
            state=state,
            degrees=degrees,
            pair_count=pair_count,
        )

        if (
            self.config.hard_guard_projected_triples_gt_entities
            and projection.projected_triples <= projection.projected_entities
        ):
            return None

        if pair_count <= 1 and edge_key in bridges:
            structural_penalty += self.config.bridge_penalty
            reasons.append("bridge")

        deg_h = degrees.get(triple.h, 0)
        deg_t = degrees.get(triple.t, 0)
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

        relative_density_penalty = 0.0
        triples_per_entity_shortfall = max(
            0.0,
            (current_triples_per_entity * projection.projected_entities) - projection.projected_triples,
        )
        if triples_per_entity_shortfall > 0:
            relative_density_penalty += (
                self.config.density_triples_per_entity_penalty * triples_per_entity_shortfall
            )
            reasons.append(f"relative_density_tpe_shortfall:{triples_per_entity_shortfall:.6f}")

        entities_per_triple_excess = max(
            0.0,
            projection.projected_entities - (current_entities_per_triple * projection.projected_triples),
        )
        if entities_per_triple_excess > 0:
            relative_density_penalty += (
                self.config.density_entities_per_triple_penalty * entities_per_triple_excess
            )
            reasons.append(f"relative_density_et_excess:{entities_per_triple_excess:.6f}")

        target_density_penalty = 0.0
        if (
            self.config.target_min_triples_per_entity is not None
            and projection.projected_triples_per_entity < self.config.target_min_triples_per_entity
        ):
            gap = self.config.target_min_triples_per_entity - projection.projected_triples_per_entity
            target_density_penalty += self.config.density_triples_per_entity_penalty * gap
            reasons.append(f"target_tpe_floor_gap:{gap:.6f}")

        if (
            self.config.target_max_entities_per_triple is not None
            and projection.projected_entities_per_triple > self.config.target_max_entities_per_triple
        ):
            gap = projection.projected_entities_per_triple - self.config.target_max_entities_per_triple
            target_density_penalty += self.config.density_entities_per_triple_penalty * gap
            reasons.append(f"target_et_ceiling_gap:{gap:.6f}")

        if (
            self.config.target_min_average_participation is not None
            and projection.projected_average_participation < self.config.target_min_average_participation
        ):
            gap = self.config.target_min_average_participation - projection.projected_average_participation
            target_density_penalty += self.config.density_triples_per_entity_penalty * gap
            reasons.append(f"target_average_participation_gap:{gap:.6f}")

        if projection.low_degree_nodes_created > 0:
            relative_density_penalty += (
                self.config.projected_low_degree_creation_penalty * projection.low_degree_nodes_created
            )
            reasons.append(f"projected_low_degree_created:{projection.low_degree_nodes_created}")

        if projection.estimated_two_path_loss > 0:
            relative_density_penalty += self.config.two_path_loss_penalty * projection.estimated_two_path_loss
            reasons.append(f"projected_two_path_loss:{projection.estimated_two_path_loss}")

        density_penalty = relative_density_penalty + target_density_penalty
        score = balance_gain - structural_penalty - density_penalty

        return RemovalDecision(
            triple_id=triple.triple_id,
            relation=triple.r,
            score=score,
            balance_gain=balance_gain,
            structural_penalty=structural_penalty,
            relative_density_penalty=relative_density_penalty,
            target_density_penalty=target_density_penalty,
            density_penalty=density_penalty,
            estimated_two_path_loss=float(projection.estimated_two_path_loss),
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
    accepted_selected_count: int
    selection_mode: str
    guard_rejections: int
    throttle_rejections: int
    relation_floor_rejections: int
    removed_triple_ids: List[str]
    pre_snapshot: GraphSnapshot
    post_snapshot: GraphSnapshot
    attempted_post_snapshot: Optional[GraphSnapshot]
    accepted_post_snapshot: GraphSnapshot
    round_accepted: bool
    guard_triggered: bool
    density_guard_triggered: bool
    connectivity_guard_triggered: bool
    target_floor_guard_triggered: bool
    relation_floor_guard_triggered: bool
    guard_messages: List[str]
    reason_histogram: Dict[str, int]
    relation_removal_counts: Dict[str, int]
    round_estimated_two_path_loss: float
    cumulative_estimated_two_path_loss: float
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
    relation_removal_counts: Dict[str, int]
    reason_histogram: Dict[str, int]
    cumulative_estimated_two_path_loss: float
    any_guard_triggered: bool
    any_density_guard_triggered: bool
    any_connectivity_guard_triggered: bool
    any_target_floor_guard_triggered: bool
    any_relation_floor_guard_triggered: bool
    protected_relation_removal_counts: Dict[str, int]
    initial_objective_metrics: Dict[str, float]
    final_objective_metrics: Dict[str, float]
    guard_messages: List[str]
    batch_logs: List[dict]


class BalanceAwarePruner:
    def __init__(self, config: PrunerConfig) -> None:
        self.config = config
        self.scorer = TripleRemovalScorer(config=config)

    def _round_relation_limit(self, round_budget: int) -> Optional[int]:
        limits: List[int] = []
        if self.config.max_fraction_per_relation_per_round is not None:
            limits.append(max(1, math.ceil(round_budget * self.config.max_fraction_per_relation_per_round)))
        if self.config.max_removals_per_relation_per_round is not None:
            limits.append(self.config.max_removals_per_relation_per_round)
        return min(limits) if limits else None

    def _relation_histogram(self, decisions: Sequence[RemovalDecision]) -> Dict[str, int]:
        return dict(collections.Counter(d.relation for d in decisions))

    def _reason_histogram(self, decisions: Sequence[RemovalDecision]) -> Dict[str, int]:
        hist: Dict[str, int] = collections.Counter()
        for decision in decisions:
            for reason in decision.reasons:
                hist[self.scorer.reason_key(reason)] += 1
        return dict(hist)

    @property
    def debug_enabled(self) -> bool:
        return self.config.debug_top_candidates > 0 or bool(self.config.debug_relations)

    @staticmethod
    def _objective_metrics(snapshot: GraphSnapshot) -> Dict[str, float]:
        return {
            "triples_minus_entities": snapshot.triples_minus_entities,
            "triples_per_entity": snapshot.triples_per_entity,
            "entities_per_triple": snapshot.entities_per_triple,
            "average_participation": snapshot.average_participation,
            "weak_component_count": snapshot.weak_component_count,
            "largest_component_ratio": snapshot.largest_component_ratio,
        }

    def _would_violate_relation_floor(
        self,
        *,
        state: KGState,
        triple: Triple,
        already_selected_for_relation: int,
    ) -> bool:
        min_count = self.scorer.relation_min_count(triple.r)
        if min_count is None:
            return False
        projected_count = state.relation_counts.get(triple.r, 0) - already_selected_for_relation - 1
        return projected_count < min_count

    def _evaluate_round_guards(self, snapshot: GraphSnapshot) -> RoundGuardStatus:
        messages: List[str] = []
        density_guard = False
        connectivity_guard = False

        if self.config.hard_guard_projected_triples_gt_entities and snapshot.total_triples <= snapshot.total_entities:
            density_guard = True
            messages.append(
                f"triples_le_entities:{snapshot.total_triples}<={snapshot.total_entities}"
            )
        if (
            self.config.min_post_round_triples_per_entity is not None
            and snapshot.triples_per_entity < self.config.min_post_round_triples_per_entity
        ):
            density_guard = True
            messages.append(
                f"triples_per_entity_below_min:{snapshot.triples_per_entity:.6f}"
            )
        if (
            self.config.max_post_round_entities_per_triple is not None
            and snapshot.entities_per_triple > self.config.max_post_round_entities_per_triple
        ):
            density_guard = True
            messages.append(
                f"entities_per_triple_above_max:{snapshot.entities_per_triple:.6f}"
            )
        if (
            self.config.min_post_round_average_participation is not None
            and snapshot.average_participation < self.config.min_post_round_average_participation
        ):
            density_guard = True
            messages.append(
                f"average_participation_below_min:{snapshot.average_participation:.6f}"
            )
        if (
            self.config.max_post_round_weak_component_count is not None
            and snapshot.weak_component_count > self.config.max_post_round_weak_component_count
        ):
            connectivity_guard = True
            messages.append(
                f"weak_component_count_above_max:{snapshot.weak_component_count}"
            )
        if (
            self.config.min_post_round_largest_component_ratio is not None
            and snapshot.largest_component_ratio < self.config.min_post_round_largest_component_ratio
        ):
            connectivity_guard = True
            messages.append(
                f"largest_component_ratio_below_min:{snapshot.largest_component_ratio:.6f}"
            )

        triggered = bool(messages)
        reject_round = triggered and self.config.batch_guard_action == "reject_round"
        stop_pruning = triggered and self.config.batch_guard_action == "stop"
        return RoundGuardStatus(
            triggered=triggered,
            stop_pruning=stop_pruning,
            reject_round=reject_round,
            density_guard_triggered=density_guard,
            connectivity_guard_triggered=connectivity_guard,
            target_floor_guard_triggered=triggered,
            messages=messages,
        )

    def _write_debug_dump(
        self,
        *,
        path: Path,
        rounds: Sequence[dict],
    ) -> None:
        payload = {
            "config": {
                "debug_top_candidates": self.config.debug_top_candidates,
                "debug_relations": sorted(self.config.debug_relations),
            },
            "rounds": list(rounds),
        }
        write_json(path, payload)

    def run(self, state: KGState) -> Tuple[KGState, RunReport]:
        started = time.time()
        initial_snapshot = state.snapshot(self.config.low_degree_threshold)
        batch_logs: List[BatchLog] = []
        total_removed = 0
        relation_removal_counts: Dict[str, int] = collections.Counter()
        reason_histogram: Dict[str, int] = collections.Counter()
        cumulative_estimated_two_path_loss = 0.0
        any_guard_triggered = False
        any_density_guard_triggered = False
        any_connectivity_guard_triggered = False
        any_target_floor_guard_triggered = False
        any_relation_floor_guard_triggered = False
        guard_messages_seen: List[str] = []
        debug_rounds: List[dict] = []

        for round_index in range(1, self.config.max_rounds + 1):
            pre = state.snapshot(self.config.low_degree_threshold)
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

            effective_selection_mode = (
                "sequential"
                if (self.config.selection_mode == "sequential" or self.config.hard_preserve_largest_component)
                else "batch"
            )
            if effective_selection_mode == "sequential" and not self.config.dry_run:
                selection = self._select_round_sequential(
                    state=state,
                    round_budget=round_budget,
                )
            else:
                selection = self._select_round_batch(
                    state=state,
                    round_budget=round_budget,
                )

            if not selection.selected:
                if self.config.verbose:
                    print(f"[round {round_index}] no removable candidates remain")
                break

            if self.config.verbose:
                top = selection.selected[0]
                print(
                    f"[round {round_index}] candidate_count={selection.candidate_count} selected={len(selection.selected)} "
                    f"top_score={top.score:.3f} top_relation={top.relation}"
                )

            if not self.config.dry_run and effective_selection_mode == "batch":
                selection.removed_triples = []
                for decision in selection.selected:
                    triple = state.triples_by_id[decision.triple_id]
                    selection.removed_triples.append(triple)
                    state.remove_triple(decision.triple_id)

            attempted_post = state.snapshot(self.config.low_degree_threshold)
            guard_status = self._evaluate_round_guards(attempted_post)
            round_accepted = True
            final_post = attempted_post

            if guard_status.triggered:
                any_guard_triggered = True
                any_density_guard_triggered = any_density_guard_triggered or guard_status.density_guard_triggered
                any_connectivity_guard_triggered = (
                    any_connectivity_guard_triggered or guard_status.connectivity_guard_triggered
                )
                any_target_floor_guard_triggered = (
                    any_target_floor_guard_triggered or guard_status.target_floor_guard_triggered
                )
                for message in guard_status.messages:
                    if message not in guard_messages_seen:
                        guard_messages_seen.append(message)
            if selection.guard_rejections > 0:
                any_guard_triggered = True
                any_connectivity_guard_triggered = True
                guard_message = f"largest_component_guard_rejections:{selection.guard_rejections}"
                if guard_message not in guard_messages_seen:
                    guard_messages_seen.append(guard_message)
            if selection.relation_floor_rejections > 0:
                any_guard_triggered = True
                any_relation_floor_guard_triggered = True
                floor_message = f"relation_floor_rejections:{selection.relation_floor_rejections}"
                if floor_message not in guard_messages_seen:
                    guard_messages_seen.append(floor_message)

            if self.debug_enabled and selection.debug_summary is not None:
                debug_round = {
                    "round_index": round_index,
                    "total_candidate_count": selection.debug_summary["total_candidate_count"],
                    "candidate_counts_by_relation": selection.debug_summary["per_relation_candidate_count"],
                    "per_relation_max_score": selection.debug_summary["per_relation_max_score"],
                    "per_relation_mean_score": selection.debug_summary["per_relation_mean_score"],
                    "per_relation_positive_score_count": selection.debug_summary[
                        "per_relation_positive_score_candidate_count"
                    ],
                    "top_candidates_overall": selection.debug_summary["top_candidates_overall"],
                    "top_candidates_debug_relations": selection.debug_summary["top_candidates_debug_relations"],
                    "selection_summary": {
                        "selected_count": len(selection.selected),
                        "relation_floor_rejections_total": selection.relation_floor_rejections,
                        "relation_floor_rejections_by_relation": selection.relation_floor_rejections_by_relation,
                        "throttle_rejections_total": selection.throttle_rejections,
                        "throttle_rejections_by_relation": selection.throttle_rejections_by_relation,
                        "largest_component_guard_rejections_total": selection.guard_rejections,
                        "largest_component_guard_rejections_by_relation": selection.guard_rejections_by_relation,
                    },
                }
                debug_rounds.append(debug_round)
                if self.config.debug_dump_path:
                    self._write_debug_dump(path=Path(self.config.debug_dump_path), rounds=debug_rounds)

            if guard_status.reject_round and not self.config.dry_run:
                round_accepted = False
                for triple in reversed(selection.removed_triples):
                    state.add_triple(triple)
                final_post = state.snapshot(self.config.low_degree_threshold)

            accepted_count = len(selection.selected) if round_accepted else 0
            round_two_path_loss = (
                sum(d.estimated_two_path_loss for d in selection.selected) if round_accepted else 0.0
            )
            if round_accepted:
                total_removed += len(selection.selected)
                cumulative_estimated_two_path_loss += round_two_path_loss
                round_relation_counts = self._relation_histogram(selection.selected)
                round_reason_hist = self._reason_histogram(selection.selected)
                for relation, count in round_relation_counts.items():
                    relation_removal_counts[relation] += count
                for reason, count in round_reason_hist.items():
                    reason_histogram[reason] += count
            else:
                round_relation_counts = self._relation_histogram(selection.selected)
                round_reason_hist = self._reason_histogram(selection.selected)

            batch_logs.append(
                BatchLog(
                    round_index=round_index,
                    candidate_count=selection.candidate_count,
                    selected_count=len(selection.selected),
                    accepted_selected_count=accepted_count,
                    selection_mode=effective_selection_mode if not self.config.dry_run else "dry_run_preview",
                    guard_rejections=selection.guard_rejections,
                    throttle_rejections=selection.throttle_rejections,
                    relation_floor_rejections=selection.relation_floor_rejections,
                    removed_triple_ids=[d.triple_id for d in selection.selected],
                    pre_snapshot=pre,
                    post_snapshot=final_post,
                    attempted_post_snapshot=attempted_post,
                    accepted_post_snapshot=final_post,
                    round_accepted=round_accepted,
                    guard_triggered=(
                        guard_status.triggered
                        or selection.guard_rejections > 0
                        or selection.relation_floor_rejections > 0
                    ),
                    density_guard_triggered=guard_status.density_guard_triggered,
                    connectivity_guard_triggered=(
                        guard_status.connectivity_guard_triggered or selection.guard_rejections > 0
                    ),
                    target_floor_guard_triggered=guard_status.target_floor_guard_triggered,
                    relation_floor_guard_triggered=(selection.relation_floor_rejections > 0),
                    guard_messages=(
                        guard_status.messages
                        + (
                            [f"largest_component_guard_rejections:{selection.guard_rejections}"]
                            if selection.guard_rejections > 0
                            else []
                        )
                        + (
                            [f"relation_floor_rejections:{selection.relation_floor_rejections}"]
                            if selection.relation_floor_rejections > 0
                            else []
                        )
                    ),
                    reason_histogram=round_reason_hist,
                    relation_removal_counts=round_relation_counts,
                    round_estimated_two_path_loss=round_two_path_loss,
                    cumulative_estimated_two_path_loss=cumulative_estimated_two_path_loss,
                    top_selected_preview=[
                        {
                            "triple_id": d.triple_id,
                            "relation": d.relation,
                            "score": d.score,
                            "balance_gain": d.balance_gain,
                            "structural_penalty": d.structural_penalty,
                            "relative_density_penalty": d.relative_density_penalty,
                            "target_density_penalty": d.target_density_penalty,
                            "density_penalty": d.density_penalty,
                            "estimated_two_path_loss": d.estimated_two_path_loss,
                            "reasons": d.reasons,
                        }
                        for d in selection.selected[: min(20, len(selection.selected))]
                    ],
                )
            )

            if self.config.max_total_removals is not None and total_removed >= self.config.max_total_removals:
                break
            if guard_status.triggered and guard_status.stop_pruning:
                break
            if guard_status.triggered and guard_status.reject_round:
                break

        finished = time.time()
        report = RunReport(
            started_at_epoch=started,
            finished_at_epoch=finished,
            duration_sec=finished - started,
            config=asdict(self.config),
            initial_snapshot=asdict(initial_snapshot),
            final_snapshot=asdict(state.snapshot(self.config.low_degree_threshold)),
            total_removed=total_removed,
            rounds_completed=len(batch_logs),
            relation_removal_counts=dict(relation_removal_counts),
            reason_histogram=dict(reason_histogram),
            cumulative_estimated_two_path_loss=cumulative_estimated_two_path_loss,
            any_guard_triggered=any_guard_triggered,
            any_density_guard_triggered=any_density_guard_triggered,
            any_connectivity_guard_triggered=any_connectivity_guard_triggered,
            any_target_floor_guard_triggered=any_target_floor_guard_triggered,
            any_relation_floor_guard_triggered=any_relation_floor_guard_triggered,
            protected_relation_removal_counts={
                relation: relation_removal_counts.get(relation, 0)
                for relation in sorted(self.config.protected_relations)
            },
            initial_objective_metrics=self._objective_metrics(initial_snapshot),
            final_objective_metrics=self._objective_metrics(state.snapshot(self.config.low_degree_threshold)),
            guard_messages=guard_messages_seen,
            batch_logs=[
                {
                    "round_index": b.round_index,
                    "candidate_count": b.candidate_count,
                    "selected_count": b.selected_count,
                    "accepted_selected_count": b.accepted_selected_count,
                    "selection_mode": b.selection_mode,
                    "guard_rejections": b.guard_rejections,
                    "throttle_rejections": b.throttle_rejections,
                    "relation_floor_rejections": b.relation_floor_rejections,
                    "removed_triple_ids": b.removed_triple_ids,
                    "pre_snapshot": asdict(b.pre_snapshot),
                    "post_snapshot": asdict(b.post_snapshot),
                    "attempted_post_snapshot": asdict(b.attempted_post_snapshot),
                    "accepted_post_snapshot": asdict(b.accepted_post_snapshot),
                    "round_accepted": b.round_accepted,
                    "guard_triggered": b.guard_triggered,
                    "density_guard_triggered": b.density_guard_triggered,
                    "connectivity_guard_triggered": b.connectivity_guard_triggered,
                    "target_floor_guard_triggered": b.target_floor_guard_triggered,
                    "relation_floor_guard_triggered": b.relation_floor_guard_triggered,
                    "guard_messages": b.guard_messages,
                    "reason_histogram": b.reason_histogram,
                    "relation_removal_counts": b.relation_removal_counts,
                    "round_estimated_two_path_loss": b.round_estimated_two_path_loss,
                    "cumulative_estimated_two_path_loss": b.cumulative_estimated_two_path_loss,
                    "top_selected_preview": b.top_selected_preview,
                }
                for b in batch_logs
            ],
        )
        return state, report

    def _select_round_batch(self, state: KGState, round_budget: int) -> RoundSelectionResult:
        decisions, debug_summary = self.scorer.score_candidates(state, include_debug=self.debug_enabled)
        limit = self._round_relation_limit(round_budget)
        selected: List[RemovalDecision] = []
        removed_triples: List[Triple] = []
        guard_rejections = 0
        throttle_rejections = 0
        relation_floor_rejections = 0
        relation_counts: Dict[str, int] = collections.Counter()
        throttle_rejections_by_relation: Dict[str, int] = collections.Counter()
        relation_floor_rejections_by_relation: Dict[str, int] = collections.Counter()

        for candidate in decisions:
            if len(selected) >= round_budget:
                break
            if limit is not None and relation_counts[candidate.relation] >= limit:
                throttle_rejections += 1
                throttle_rejections_by_relation[candidate.relation] += 1
                continue
            triple = state.triples_by_id[candidate.triple_id]
            if self._would_violate_relation_floor(
                state=state,
                triple=triple,
                already_selected_for_relation=relation_counts[candidate.relation],
            ):
                relation_floor_rejections += 1
                relation_floor_rejections_by_relation[candidate.relation] += 1
                continue
            selected.append(candidate)
            relation_counts[candidate.relation] += 1

        return RoundSelectionResult(
            selected=selected,
            removed_triples=removed_triples,
            candidate_count=len(decisions),
            guard_rejections=guard_rejections,
            throttle_rejections=throttle_rejections,
            relation_floor_rejections=relation_floor_rejections,
            guard_rejections_by_relation={},
            throttle_rejections_by_relation=dict(throttle_rejections_by_relation),
            relation_floor_rejections_by_relation=dict(relation_floor_rejections_by_relation),
            debug_summary=debug_summary,
        )

    def _select_round_sequential(self, state: KGState, round_budget: int) -> RoundSelectionResult:
        selected: List[RemovalDecision] = []
        removed_triples: List[Triple] = []
        candidate_count = 0
        guard_rejections = 0
        throttle_rejections = 0
        relation_floor_rejections = 0
        relation_counts: Dict[str, int] = collections.Counter()
        guard_rejections_by_relation: Dict[str, int] = collections.Counter()
        throttle_rejections_by_relation: Dict[str, int] = collections.Counter()
        relation_floor_rejections_by_relation: Dict[str, int] = collections.Counter()
        relation_limit = self._round_relation_limit(round_budget)
        debug_summary: Optional[dict] = None
        for step_idx in range(round_budget):
            decisions, round_debug_summary = self.scorer.score_candidates(
                state,
                include_debug=(self.debug_enabled and step_idx == 0),
            )
            if step_idx == 0:
                candidate_count = len(decisions)
                debug_summary = round_debug_summary
            if not decisions:
                break
            decision: Optional[RemovalDecision] = None
            for candidate in decisions:
                if relation_limit is not None and relation_counts[candidate.relation] >= relation_limit:
                    throttle_rejections += 1
                    throttle_rejections_by_relation[candidate.relation] += 1
                    continue
                triple = state.triples_by_id[candidate.triple_id]
                if self._would_violate_relation_floor(
                    state=state,
                    triple=triple,
                    already_selected_for_relation=relation_counts[candidate.relation],
                ):
                    relation_floor_rejections += 1
                    relation_floor_rejections_by_relation[candidate.relation] += 1
                    continue
                if self.config.hard_preserve_largest_component and not state.removal_preserves_largest_component(candidate.triple_id):
                    guard_rejections += 1
                    guard_rejections_by_relation[candidate.relation] += 1
                    continue
                decision = candidate
                break
            if decision is None:
                break
            selected.append(decision)
            removed_triples.append(state.triples_by_id[decision.triple_id])
            relation_counts[decision.relation] += 1
            state.remove_triple(decision.triple_id)
        return RoundSelectionResult(
            selected=selected,
            removed_triples=removed_triples,
            candidate_count=candidate_count,
            guard_rejections=guard_rejections,
            throttle_rejections=throttle_rejections,
            relation_floor_rejections=relation_floor_rejections,
            guard_rejections_by_relation=dict(guard_rejections_by_relation),
            throttle_rejections_by_relation=dict(throttle_rejections_by_relation),
            relation_floor_rejections_by_relation=dict(relation_floor_rejections_by_relation),
            debug_summary=debug_summary,
        )


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


def parse_relation_min_count_args(values: Optional[Sequence[str]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for raw in values or []:
        if "=" not in raw:
            raise ValueError(
                f"Invalid relation floor '{raw}'. Expected format RELATION_ID=MIN_COUNT."
            )
        relation, raw_count = raw.split("=", 1)
        relation = relation.strip()
        raw_count = raw_count.strip()
        if not relation:
            raise ValueError(f"Invalid relation floor '{raw}': empty relation id.")
        try:
            min_count = int(raw_count)
        except ValueError as exc:
            raise ValueError(
                f"Invalid relation floor '{raw}': MIN_COUNT must be an integer."
            ) from exc
        if min_count < 0:
            raise ValueError(
                f"Invalid relation floor '{raw}': MIN_COUNT must be >= 0."
            )
        out[relation] = min_count
    return out


def parse_debug_relations(value: Optional[str]) -> Set[str]:
    if value is None:
        return set()
    out = {
        relation.strip()
        for relation in value.split(",")
        if relation.strip()
    }
    return out


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
    p.add_argument(
        "--debug_top_candidates",
        type=int,
        default=0,
        help="If > 0, dump top-N scored candidates per round for diagnostics.",
    )
    p.add_argument(
        "--debug_relations",
        type=str,
        default=None,
        help="Comma-separated relations to inspect in per-round debug dumps, e.g. P31,P279.",
    )
    p.add_argument(
        "--debug_dump_path",
        type=Path,
        default=None,
        help="Optional JSON path for per-round debug dumps. If omitted, a .debug.json file is written next to --out_report when debug mode is enabled.",
    )

    p.add_argument("--protected_pattern", action="append", default=None, help="Pattern to protect; repeatable")
    p.add_argument(
        "--protected_relation",
        action="append",
        default=None,
        help="Relation to treat as semantic backbone for reporting / floor enforcement; repeatable.",
    )
    p.add_argument(
        "--hard_relation_min_count",
        action="append",
        default=None,
        metavar="REL=MIN",
        help="Hard relation floor. Reject removals that would take REL below MIN. Repeatable.",
    )
    p.add_argument("--disable_hard_protect_patterns_below_target", action="store_true")
    p.add_argument("--disable_hard_preserve_largest_component", action="store_true")

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
    p.add_argument(
        "--relation_overcap_mode",
        choices=("linear", "sqrt", "log1p", "capped_linear"),
        default="log1p",
        help="Saturated relation-overcap reward mode. Final benchmark runs should prefer log1p.",
    )
    p.add_argument(
        "--relation_overcap_cap",
        type=float,
        default=25.0,
        help="Cap used only when --relation_overcap_mode=capped_linear.",
    )
    p.add_argument("--bridge_penalty", type=float, default=1_000_000.0)
    p.add_argument("--low_degree_penalty", type=float, default=50.0)
    p.add_argument("--low_degree_threshold", type=int, default=2)
    p.add_argument("--articulation_endpoint_penalty", type=float, default=20.0)
    p.add_argument("--local_redundancy_bonus", type=float, default=5.0)
    p.add_argument("--common_neighbor_bonus_cap", type=int, default=10)
    p.add_argument("--same_component_cycle_bonus", type=float, default=2.0)
    p.add_argument("--density_triples_per_entity_penalty", type=float, default=10.0)
    p.add_argument("--density_entities_per_triple_penalty", type=float, default=10.0)
    p.add_argument(
        "--target_min_triples_per_entity",
        type=float,
        default=None,
        help="Absolute benchmark floor for triples/entities. None means no target-aware T/E floor enforcement.",
    )
    p.add_argument(
        "--target_max_entities_per_triple",
        type=float,
        default=None,
        help="Absolute benchmark ceiling for entities/triples. None means no target-aware E/T ceiling enforcement.",
    )
    p.add_argument(
        "--target_min_average_participation",
        type=float,
        default=None,
        help="Absolute benchmark floor for average participation 2T/E. None means no target-aware participation floor enforcement.",
    )
    p.add_argument("--projected_low_degree_creation_penalty", type=float, default=15.0)
    p.add_argument("--two_path_loss_penalty", type=float, default=1.0)
    p.add_argument(
        "--hard_guard_projected_triples_gt_entities",
        action="store_true",
        help="Reject candidate removals and stop rounds that would drive triples <= entities.",
    )
    p.add_argument(
        "--max_fraction_per_relation_per_round",
        type=float,
        default=0.25,
        help="Maximum fraction of a round budget that one relation may consume. Set negative to disable.",
    )
    p.add_argument(
        "--max_removals_per_relation_per_round",
        type=int,
        default=None,
        help="Absolute per-round removal cap for any single relation.",
    )
    p.add_argument(
        "--batch_guard_action",
        choices=("stop", "reject_round"),
        default="reject_round",
        help="Action when post-round density/connectivity diagnostics violate configured thresholds. Final benchmark runs should prefer reject_round.",
    )
    p.add_argument(
        "--min_post_round_triples_per_entity",
        type=float,
        default=None,
        help="Post-round floor for triples/entities. None means no post-round T/E benchmark enforcement.",
    )
    p.add_argument(
        "--max_post_round_entities_per_triple",
        type=float,
        default=None,
        help="Post-round ceiling for entities/triples. None means no post-round E/T benchmark enforcement.",
    )
    p.add_argument(
        "--min_post_round_average_participation",
        type=float,
        default=None,
        help="Post-round floor for average participation 2T/E. None means no post-round participation benchmark enforcement.",
    )
    p.add_argument(
        "--max_post_round_weak_component_count",
        type=int,
        default=None,
        help="Post-round ceiling for weak component count. None means no component-count guard.",
    )
    p.add_argument(
        "--min_post_round_largest_component_ratio",
        type=float,
        default=None,
        help="Post-round floor for largest-component ratio. None means no largest-component guard.",
    )

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

    try:
        args._parsed_hard_relation_min_count = parse_relation_min_count_args(args.hard_relation_min_count)
    except ValueError as exc:
        parser.error(str(exc))
    args._parsed_debug_relations = parse_debug_relations(args.debug_relations)

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
    if args.debug_top_candidates < 0:
        parser.error("--debug_top_candidates must be >= 0.")
    if args.max_rounds <= 0:
        parser.error("--max_rounds must be > 0.")
    if args.max_total_removals is not None and args.max_total_removals <= 0:
        parser.error("--max_total_removals must be > 0 when provided.")
    if args.low_degree_threshold < 0:
        parser.error("--low_degree_threshold must be >= 0.")
    if args.relation_overcap_cap < 0:
        parser.error("--relation_overcap_cap must be >= 0.")
    if args.relation_overcap_mode == "capped_linear" and args.relation_overcap_cap <= 0:
        parser.error("--relation_overcap_cap must be > 0 when --relation_overcap_mode=capped_linear.")
    if args.max_fraction_per_relation_per_round is not None and args.max_fraction_per_relation_per_round < 0:
        args.max_fraction_per_relation_per_round = None
    if (
        args.max_fraction_per_relation_per_round is not None
        and not (0 < args.max_fraction_per_relation_per_round <= 1.0)
    ):
        parser.error("--max_fraction_per_relation_per_round must be in (0, 1] or negative to disable.")
    if args.max_removals_per_relation_per_round is not None and args.max_removals_per_relation_per_round <= 0:
        parser.error("--max_removals_per_relation_per_round must be > 0 when provided.")
    if args.max_post_round_weak_component_count is not None and args.max_post_round_weak_component_count <= 0:
        parser.error("--max_post_round_weak_component_count must be > 0 when provided.")
    if args.min_post_round_triples_per_entity is not None and args.min_post_round_triples_per_entity < 0:
        parser.error("--min_post_round_triples_per_entity must be >= 0 when provided.")
    if args.max_post_round_entities_per_triple is not None and args.max_post_round_entities_per_triple < 0:
        parser.error("--max_post_round_entities_per_triple must be >= 0 when provided.")
    if args.min_post_round_average_participation is not None and args.min_post_round_average_participation < 0:
        parser.error("--min_post_round_average_participation must be >= 0 when provided.")
    if args.target_min_triples_per_entity is not None and args.target_min_triples_per_entity < 0:
        parser.error("--target_min_triples_per_entity must be >= 0 when provided.")
    if args.target_max_entities_per_triple is not None and args.target_max_entities_per_triple < 0:
        parser.error("--target_max_entities_per_triple must be >= 0 when provided.")
    if args.target_min_average_participation is not None and args.target_min_average_participation < 0:
        parser.error("--target_min_average_participation must be >= 0 when provided.")
    if args.min_post_round_largest_component_ratio is not None and not (0 <= args.min_post_round_largest_component_ratio <= 1):
        parser.error("--min_post_round_largest_component_ratio must be in [0, 1].")

    debug_enabled = args.debug_top_candidates > 0 or bool(args._parsed_debug_relations)
    if debug_enabled and args.debug_dump_path is None:
        args.debug_dump_path = args.out_report.with_name(f"{args.out_report.stem}.debug.json")

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
        ("density_triples_per_entity_penalty", args.density_triples_per_entity_penalty),
        ("density_entities_per_triple_penalty", args.density_entities_per_triple_penalty),
        ("projected_low_degree_creation_penalty", args.projected_low_degree_creation_penalty),
        ("two_path_loss_penalty", args.two_path_loss_penalty),
    ]
    for name, value in numeric_must_be_non_negative:
        if value < 0:
            parser.error(f"--{name} must be >= 0.")


def config_from_args(args: argparse.Namespace) -> PrunerConfig:
    hard_relation_min_count = dict(getattr(args, "_parsed_hard_relation_min_count", {}))
    debug_relations = set(getattr(args, "_parsed_debug_relations", set()))
    protected_relations = set(args.protected_relation or [])
    protected_relations.update(hard_relation_min_count.keys())
    return PrunerConfig(
        protected_patterns=set(args.protected_pattern or ["symmetric"]),
        protected_relations=protected_relations,
        hard_relation_min_count=hard_relation_min_count,
        hard_protect_patterns_below_target=not args.disable_hard_protect_patterns_below_target,
        hard_preserve_largest_component=not args.disable_hard_preserve_largest_component,
        pattern_surplus_weight=args.pattern_surplus_weight,
        pattern_deficit_penalty_weight=args.pattern_deficit_penalty_weight,
        protected_pattern_penalty_weight=args.protected_pattern_penalty_weight,
        relation_overcap_weight=args.relation_overcap_weight,
        relation_overcap_mode=args.relation_overcap_mode,
        relation_overcap_cap=args.relation_overcap_cap,
        bridge_penalty=args.bridge_penalty,
        low_degree_penalty=args.low_degree_penalty,
        low_degree_threshold=args.low_degree_threshold,
        articulation_endpoint_penalty=args.articulation_endpoint_penalty,
        local_redundancy_bonus=args.local_redundancy_bonus,
        common_neighbor_bonus_cap=args.common_neighbor_bonus_cap,
        same_component_cycle_bonus=args.same_component_cycle_bonus,
        density_triples_per_entity_penalty=args.density_triples_per_entity_penalty,
        density_entities_per_triple_penalty=args.density_entities_per_triple_penalty,
        target_min_triples_per_entity=args.target_min_triples_per_entity,
        target_max_entities_per_triple=args.target_max_entities_per_triple,
        target_min_average_participation=args.target_min_average_participation,
        projected_low_degree_creation_penalty=args.projected_low_degree_creation_penalty,
        two_path_loss_penalty=args.two_path_loss_penalty,
        hard_guard_projected_triples_gt_entities=args.hard_guard_projected_triples_gt_entities,
        max_batch_removals=args.max_batch_removals,
        max_rounds=args.max_rounds,
        max_total_removals=args.max_total_removals,
        max_fraction_per_relation_per_round=args.max_fraction_per_relation_per_round,
        max_removals_per_relation_per_round=args.max_removals_per_relation_per_round,
        batch_guard_action=args.batch_guard_action,
        min_post_round_triples_per_entity=args.min_post_round_triples_per_entity,
        max_post_round_entities_per_triple=args.max_post_round_entities_per_triple,
        min_post_round_average_participation=args.min_post_round_average_participation,
        max_post_round_weak_component_count=args.max_post_round_weak_component_count,
        min_post_round_largest_component_ratio=args.min_post_round_largest_component_ratio,
        stop_when_all_pattern_surpluses_zero=args.stop_when_all_pattern_surpluses_zero,
        allow_relation_level_pruning_even_if_pattern_neutral=args.allow_relation_level_pruning_even_if_pattern_neutral,
        selection_mode=args.selection_mode,
        debug_top_candidates=args.debug_top_candidates,
        debug_relations=debug_relations,
        debug_dump_path=(str(args.debug_dump_path) if args.debug_dump_path is not None else None),
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
