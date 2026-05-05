#!/usr/bin/env python3
"""Sequential balance-first remove-and-replace skeleton.

This script extends the current pruning approach with swap logic:
1. score removal candidates using the existing balance-aware pruner scorer
2. if a removal keeps connectivity, accept it as a plain prune
3. if a removal disconnects the graph, search for a repair_core replacement
4. accept the swap only when connectivity is restored and the net score is positive

The implementation is intentionally conservative in scope:
- reuse the current pruning score model for removals
- use the existing WDQS relation-scope and one-hop neighbor helpers
- keep swap selection sequential and fully auditable

This is a first skeleton, not a finished optimizer.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

import networkx as nx


TripleTuple = Tuple[str, str, str]


def _load_module(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parent

PRUNER = _load_module("kg_balance_pruner_embedded", SCRIPT_DIR / "kg_balance_pruner.py")
REPAIR = _load_module("repair_kg_connectivity_embedded", SRC_DIR / "kg_building" / "repair_kg_connectivity.py")


@dataclass
class SwapConfig:
    protected_patterns: Set[str] = field(default_factory=lambda: {"symmetric"})
    hard_protect_patterns_below_target: bool = True
    allow_relation_level_pruning_even_if_pattern_neutral: bool = False
    relation_overcap_min_excess: int = 1
    pattern_surplus_weight: float = 10.0
    pattern_deficit_penalty_weight: float = 25.0
    protected_pattern_penalty_weight: float = 40.0
    relation_overcap_weight: float = 2.0
    bridge_penalty: float = 0.0
    low_degree_penalty: float = 0.0
    low_degree_threshold: int = 0
    articulation_endpoint_penalty: float = 0.0
    local_redundancy_bonus: float = 5.0
    common_neighbor_bonus_cap: int = 10
    same_component_cycle_bonus: float = 2.0
    max_swaps: int = 100
    max_removal_candidates_per_round: int = 100
    max_anchors_per_component: int = 3
    max_bridge_candidates_per_removal: int = 100
    max_hops: int = 2
    query_limit: int = 200
    timeout_sec: int = 60
    wikidata_sleep_sec: float = 0.2
    user_agent: str = "kg-remove-replace/1.0 (mailto:replace-me@example.com)"
    min_net_score: float = 0.0
    replacement_deficit_reward_weight: float = 30.0
    protected_pattern_reward_weight: float = 20.0
    replacement_surplus_penalty_weight: float = 20.0
    replacement_overcap_penalty_weight: float = 1000.0
    unlabeled_replacement_penalty_weight: float = 20.0
    hop_penalty_weight: float = 5.0
    new_entity_penalty_weight: float = 5.0
    allow_overcap_replacements: bool = False
    allow_plain_prune_when_connected: bool = True
    dry_run: bool = False
    verbose: bool = False


@dataclass
class ReplacementCandidate:
    bridge_triples: List[TripleTuple]
    bridge_nodes_new: List[str]
    anchor_node: str
    target_main_node: str
    depth_hops: int
    query_direction: str


@dataclass
class AcceptedMove:
    round_index: int
    mode: str
    removed_triple_id: str
    removed_relation: str
    removal_score: float
    removal_balance_gain: float
    removal_reasons: List[str]
    replacement_triples: List[List[str]]
    replacement_relations: List[str]
    replacement_score: float
    replacement_reasons: List[str]
    net_score: float
    weak_components_before: int
    weak_components_after_removal: int
    weak_components_after_accept: int


class NeighborCache:
    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, str, int], Optional[List[TripleTuple]]] = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self.queries_attempted = 0
        self.queries_succeeded = 0
        self.queries_failed = 0

    def get(self, *, qid: str, direction: str, limit: int, user_agent: str, timeout_sec: int) -> Optional[List[TripleTuple]]:
        key = (qid, direction, limit)
        cached = self._cache.get(key)
        if cached is not None or key in self._cache:
            self.cache_hits += 1
            return cached

        self.cache_misses += 1
        self.queries_attempted += 1
        try:
            triples = REPAIR.query_one_hop_neighbors(
                qid=qid,
                direction=direction,
                user_agent=user_agent,
                timeout_sec=timeout_sec,
                limit=limit,
            )
        except Exception:
            self.queries_failed += 1
            self._cache[key] = None
            return None

        self.queries_succeeded += 1
        self._cache[key] = list(triples)
        return self._cache[key]


def _log(enabled: bool, message: str) -> None:
    if enabled:
        print(message, flush=True)


def _clone_state(state: Any) -> Any:
    return PRUNER.KGState(
        triples=state.triples(),
        pattern_index=state.pattern_index,
        pattern_targets=state.pattern_targets,
        relation_targets=state.relation_targets,
    )


def _make_state(triples: Sequence[Any], pattern_index: Any, pattern_targets: Any, relation_targets: Mapping[str, int]) -> Any:
    return PRUNER.KGState(
        triples=triples,
        pattern_index=pattern_index,
        pattern_targets=pattern_targets,
        relation_targets=relation_targets,
    )


def _append_bridge_triples(state: Any, bridge_triples: Sequence[TripleTuple]) -> Any:
    triples = list(state.triples())
    triple_ids = {triple.triple_id for triple in triples}
    triple_keys = {(triple.h, triple.r, triple.t) for triple in triples}
    for h, r, t in bridge_triples:
        triple_key = (h, r, t)
        if triple_key in triple_keys:
            continue
        row = {
            "h": h,
            "r": r,
            "t": t,
            "source": "remove_replace",
        }
        triple = PRUNER.Triple.from_row(row)
        if triple.triple_id in triple_ids:
            continue
        triples.append(triple)
        triple_ids.add(triple.triple_id)
        triple_keys.add(triple_key)
    return _make_state(
        triples=triples,
        pattern_index=state.pattern_index,
        pattern_targets=state.pattern_targets,
        relation_targets=state.relation_targets,
    )


def _rank_anchors(graph: nx.Graph, component_nodes: Set[str], top_k: int) -> List[str]:
    ranked = sorted(component_nodes, key=lambda node: (graph.degree(node), node), reverse=True)
    return ranked[: max(1, top_k)]


def _relation_patterns(state: Any, relation: str) -> Tuple[str, ...]:
    return state.pattern_index.patterns_for_relation(relation)


def _score_replacement_candidate(state_after_removal: Any, candidate: ReplacementCandidate, config: SwapConfig) -> Tuple[float, List[str]] | None:
    pattern_surplus = state_after_removal.pattern_surplus()
    pattern_deficit = state_after_removal.pattern_deficit()
    relation_overcap = state_after_removal.relation_overcap()

    benefit = 0.0
    penalty = 0.0
    reasons: List[str] = []

    for _h, relation, _t in candidate.bridge_triples:
        rel_overcap = relation_overcap.get(relation, 0)
        if rel_overcap > 0 and not config.allow_overcap_replacements:
            return None
        if rel_overcap > 0:
            penalty += config.replacement_overcap_penalty_weight * rel_overcap
            reasons.append(f"replacement_overcap:{relation}:{rel_overcap}")

        patterns = _relation_patterns(state_after_removal, relation)
        if not patterns:
            penalty += config.unlabeled_replacement_penalty_weight
            reasons.append(f"replacement_unlabeled:{relation}")

        for pattern in patterns:
            # V1 hard safety rule: a replacement must not increase any bucket that
            # is already above target. This prevents composition-removal swaps from
            # silently reintroducing pressure through inverse/anti-symmetric edges.
            if pattern_surplus.get(pattern, 0) > 0:
                return None
            if pattern_deficit.get(pattern, 0) > 0:
                benefit += config.replacement_deficit_reward_weight
                reasons.append(f"replacement_helps_deficit:{pattern}")
                if pattern in config.protected_patterns:
                    benefit += config.protected_pattern_reward_weight
                    reasons.append(f"replacement_protected_deficit:{pattern}")
            if pattern_surplus.get(pattern, 0) > 0:
                penalty += config.replacement_surplus_penalty_weight
                reasons.append(f"replacement_adds_surplus:{pattern}")

    penalty += config.hop_penalty_weight * max(0, candidate.depth_hops - 1)
    if candidate.bridge_nodes_new:
        penalty += config.new_entity_penalty_weight * len(candidate.bridge_nodes_new)
        reasons.append(f"replacement_new_entities:{len(candidate.bridge_nodes_new)}")

    score = benefit - penalty
    return score, reasons


def _enumerate_one_hop_candidates(
    *,
    cache: NeighborCache,
    relation_scope: Dict[str, Any],
    anchor: str,
    main_nodes: Set[str],
    config: SwapConfig,
) -> Iterator[ReplacementCandidate]:
    if not anchor.startswith("Q"):
        return

    for direction in ("out", "in"):
        triples = cache.get(
            qid=anchor,
            direction=direction,
            limit=config.query_limit,
            user_agent=config.user_agent,
            timeout_sec=config.timeout_sec,
        )
        if triples is None:
            continue

        for triple in triples:
            h, relation, t = triple
            other = t if h == anchor else h
            if other not in main_nodes:
                continue
            scope_info = REPAIR.classify_relation_scope(relation, relation_scope)
            label = REPAIR.classify_bridge_label([scope_info])
            if label != "repair_core":
                continue
            yield ReplacementCandidate(
                bridge_triples=[triple],
                bridge_nodes_new=[],
                anchor_node=anchor,
                target_main_node=other,
                depth_hops=1,
                query_direction=direction,
            )


def _enumerate_two_hop_candidates(
    *,
    cache: NeighborCache,
    relation_scope: Dict[str, Any],
    anchor: str,
    main_nodes: Set[str],
    config: SwapConfig,
) -> Iterator[ReplacementCandidate]:
    if config.max_hops < 2 or not anchor.startswith("Q"):
        return

    for direction1 in ("out", "in"):
        first_hop = cache.get(
            qid=anchor,
            direction=direction1,
            limit=config.query_limit,
            user_agent=config.user_agent,
            timeout_sec=config.timeout_sec,
        )
        if first_hop is None:
            continue

        for triple1 in first_hop:
            h1, _r1, t1 = triple1
            mid = t1 if h1 == anchor else h1
            if not mid.startswith("Q") or mid in main_nodes:
                continue

            for direction2 in ("out", "in"):
                second_hop = cache.get(
                    qid=mid,
                    direction=direction2,
                    limit=config.query_limit,
                    user_agent=config.user_agent,
                    timeout_sec=config.timeout_sec,
                )
                if second_hop is None:
                    continue

                for triple2 in second_hop:
                    h2, _r2, t2 = triple2
                    other = t2 if h2 == mid else h2
                    if other not in main_nodes:
                        continue

                    scope_info_1 = REPAIR.classify_relation_scope(triple1[1], relation_scope)
                    scope_info_2 = REPAIR.classify_relation_scope(triple2[1], relation_scope)
                    label = REPAIR.classify_bridge_label([scope_info_1, scope_info_2])
                    if label != "repair_core":
                        continue

                    yield ReplacementCandidate(
                        bridge_triples=[triple1, triple2],
                        bridge_nodes_new=[mid],
                        anchor_node=anchor,
                        target_main_node=other,
                        depth_hops=2,
                        query_direction=f"{direction1}->{direction2}",
                    )


def _best_replacement_for_state(
    *,
    state_after_removal: Any,
    weak_components_before: int,
    removal: Any,
    relation_scope: Dict[str, Any],
    cache: NeighborCache,
    config: SwapConfig,
) -> Tuple[Optional[Any], Optional[ReplacementCandidate], float, List[str]]:
    components = [set(comp) for comp in nx.connected_components(state_after_removal.graph)]
    if len(components) <= weak_components_before:
        return None, None, 0.0, []

    components.sort(key=len, reverse=True)
    main_nodes = components[0]
    candidate_count = 0
    seen_signatures: Set[Tuple[TripleTuple, ...]] = set()
    best_state: Optional[Any] = None
    best_candidate: Optional[ReplacementCandidate] = None
    best_net_score: Optional[float] = None
    best_reasons: List[str] = []

    for component_nodes in components[1:]:
        anchors = _rank_anchors(state_after_removal.graph, component_nodes, config.max_anchors_per_component)
        for anchor in anchors:
            for candidate in _enumerate_one_hop_candidates(
                cache=cache,
                relation_scope=relation_scope,
                anchor=anchor,
                main_nodes=main_nodes,
                config=config,
            ):
                signature = tuple(candidate.bridge_triples)
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                candidate_count += 1
                scored = _score_replacement_candidate(state_after_removal, candidate, config)
                if scored is None:
                    continue
                replacement_score, replacement_reasons = scored
                candidate_state = _append_bridge_triples(state_after_removal, candidate.bridge_triples)
                if candidate_state.snapshot().weak_component_count != weak_components_before:
                    continue
                net_score = removal.balance_gain + replacement_score
                if net_score <= config.min_net_score:
                    continue
                if best_net_score is None or net_score > best_net_score:
                    best_state = candidate_state
                    best_candidate = candidate
                    best_net_score = net_score
                    best_reasons = replacement_reasons
                if candidate_count >= config.max_bridge_candidates_per_removal:
                    return best_state, best_candidate, best_net_score or 0.0, best_reasons

            for candidate in _enumerate_two_hop_candidates(
                cache=cache,
                relation_scope=relation_scope,
                anchor=anchor,
                main_nodes=main_nodes,
                config=config,
            ):
                signature = tuple(candidate.bridge_triples)
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                candidate_count += 1
                scored = _score_replacement_candidate(state_after_removal, candidate, config)
                if scored is None:
                    continue
                replacement_score, replacement_reasons = scored
                candidate_state = _append_bridge_triples(state_after_removal, candidate.bridge_triples)
                if candidate_state.snapshot().weak_component_count != weak_components_before:
                    continue
                net_score = removal.balance_gain + replacement_score
                if net_score <= config.min_net_score:
                    continue
                if best_net_score is None or net_score > best_net_score:
                    best_state = candidate_state
                    best_candidate = candidate
                    best_net_score = net_score
                    best_reasons = replacement_reasons
                if candidate_count >= config.max_bridge_candidates_per_removal:
                    return best_state, best_candidate, best_net_score or 0.0, best_reasons

            if config.wikidata_sleep_sec > 0:
                time.sleep(config.wikidata_sleep_sec)

    return best_state, best_candidate, best_net_score or 0.0, best_reasons


def _evaluate_candidate(
    *,
    state: Any,
    removal: Any,
    relation_scope: Dict[str, Any],
    cache: NeighborCache,
    config: SwapConfig,
    round_index: int,
) -> Tuple[Optional[Any], Optional[AcceptedMove]]:
    weak_components_before = state.snapshot().weak_component_count
    state_after_removal = _clone_state(state)
    state_after_removal.remove_triple(removal.triple_id)
    weak_components_after_removal = state_after_removal.snapshot().weak_component_count

    if weak_components_after_removal == weak_components_before and config.allow_plain_prune_when_connected:
        move = AcceptedMove(
            round_index=round_index,
            mode="plain_prune",
            removed_triple_id=removal.triple_id,
            removed_relation=removal.relation,
            removal_score=removal.score,
            removal_balance_gain=removal.balance_gain,
            removal_reasons=list(removal.reasons),
            replacement_triples=[],
            replacement_relations=[],
            replacement_score=0.0,
            replacement_reasons=[],
            net_score=removal.score,
            weak_components_before=weak_components_before,
            weak_components_after_removal=weak_components_after_removal,
            weak_components_after_accept=weak_components_after_removal,
        )
        return state_after_removal, move

    best_state, best_candidate, best_net_score, replacement_reasons = _best_replacement_for_state(
        state_after_removal=state_after_removal,
        weak_components_before=weak_components_before,
        removal=removal,
        relation_scope=relation_scope,
        cache=cache,
        config=config,
    )
    if best_state is None or best_candidate is None:
        return None, None

    replacement_relations = [relation for _h, relation, _t in best_candidate.bridge_triples]
    replacement_score = best_net_score - removal.balance_gain
    move = AcceptedMove(
        round_index=round_index,
        mode="remove_replace",
        removed_triple_id=removal.triple_id,
        removed_relation=removal.relation,
        removal_score=removal.score,
        removal_balance_gain=removal.balance_gain,
        removal_reasons=list(removal.reasons),
        replacement_triples=[list(triple) for triple in best_candidate.bridge_triples],
        replacement_relations=replacement_relations,
        replacement_score=replacement_score,
        replacement_reasons=replacement_reasons,
        net_score=best_net_score,
        weak_components_before=weak_components_before,
        weak_components_after_removal=weak_components_after_removal,
        weak_components_after_accept=best_state.snapshot().weak_component_count,
    )
    return best_state, move


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sequential balance-first remove-and-replace skeleton")
    parser.add_argument("--input_graph", type=Path, required=True, help="Input graph triples JSONL or CSV")
    parser.add_argument("--allocation_manifest", type=Path, required=True, help="Allocation manifest JSON")
    parser.add_argument("--out_graph", type=Path, required=True, help="Output graph JSONL")
    parser.add_argument("--out_report", type=Path, required=True, help="Output report JSON")

    parser.add_argument("--protected_pattern", action="append", default=None, help="Pattern to protect; repeatable")
    parser.add_argument("--disable_hard_protect_patterns_below_target", action="store_true")
    parser.add_argument("--allow_relation_level_pruning_even_if_pattern_neutral", action="store_true")
    parser.add_argument("--allow_overcap_replacements", action="store_true")
    parser.add_argument("--disable_plain_prune_when_connected", action="store_true")

    parser.add_argument("--relation_overcap_min_excess", type=int, default=1)
    parser.add_argument("--pattern_surplus_weight", type=float, default=10.0)
    parser.add_argument("--pattern_deficit_penalty_weight", type=float, default=25.0)
    parser.add_argument("--protected_pattern_penalty_weight", type=float, default=40.0)
    parser.add_argument("--relation_overcap_weight", type=float, default=2.0)
    parser.add_argument("--bridge_penalty", type=float, default=0.0)
    parser.add_argument("--low_degree_penalty", type=float, default=0.0)
    parser.add_argument("--low_degree_threshold", type=int, default=0)
    parser.add_argument("--articulation_endpoint_penalty", type=float, default=0.0)
    parser.add_argument("--local_redundancy_bonus", type=float, default=5.0)
    parser.add_argument("--common_neighbor_bonus_cap", type=int, default=10)
    parser.add_argument("--same_component_cycle_bonus", type=float, default=2.0)

    parser.add_argument("--max_swaps", type=int, default=100)
    parser.add_argument("--max_removal_candidates_per_round", type=int, default=100)
    parser.add_argument("--max_anchors_per_component", type=int, default=3)
    parser.add_argument("--max_bridge_candidates_per_removal", type=int, default=100)
    parser.add_argument("--max_hops", type=int, choices=[1, 2], default=2)
    parser.add_argument("--query_limit", type=int, default=200)
    parser.add_argument("--timeout_sec", type=int, default=60)
    parser.add_argument("--wikidata_sleep_sec", type=float, default=0.2)
    parser.add_argument("--user_agent", type=str, default="kg-remove-replace/1.0 (mailto:replace-me@example.com)")
    parser.add_argument("--min_net_score", type=float, default=0.0)
    parser.add_argument("--replacement_deficit_reward_weight", type=float, default=30.0)
    parser.add_argument("--protected_pattern_reward_weight", type=float, default=20.0)
    parser.add_argument("--replacement_surplus_penalty_weight", type=float, default=20.0)
    parser.add_argument("--replacement_overcap_penalty_weight", type=float, default=1000.0)
    parser.add_argument("--unlabeled_replacement_penalty_weight", type=float, default=20.0)
    parser.add_argument("--hop_penalty_weight", type=float, default=5.0)
    parser.add_argument("--new_entity_penalty_weight", type=float, default=5.0)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.input_graph.exists():
        parser.error(f"--input_graph does not exist: {args.input_graph}")
    if not args.allocation_manifest.exists():
        parser.error(f"--allocation_manifest does not exist: {args.allocation_manifest}")
    if args.out_graph.resolve() == args.input_graph.resolve():
        parser.error("--out_graph must differ from --input_graph.")
    if args.out_report.resolve() == args.input_graph.resolve():
        parser.error("--out_report must differ from --input_graph.")
    if args.out_graph.resolve() == args.out_report.resolve():
        parser.error("--out_graph and --out_report must differ.")
    numeric_non_negative = [
        args.pattern_surplus_weight,
        args.pattern_deficit_penalty_weight,
        args.protected_pattern_penalty_weight,
        args.relation_overcap_weight,
        args.bridge_penalty,
        args.low_degree_penalty,
        args.articulation_endpoint_penalty,
        args.local_redundancy_bonus,
        args.common_neighbor_bonus_cap,
        args.same_component_cycle_bonus,
        args.replacement_deficit_reward_weight,
        args.protected_pattern_reward_weight,
        args.replacement_surplus_penalty_weight,
        args.replacement_overcap_penalty_weight,
        args.unlabeled_replacement_penalty_weight,
        args.hop_penalty_weight,
        args.new_entity_penalty_weight,
    ]
    if any(value < 0 for value in numeric_non_negative):
        parser.error("All numeric weights and penalties must be >= 0.")
    positive_int_args = {
        "max_swaps": args.max_swaps,
        "max_removal_candidates_per_round": args.max_removal_candidates_per_round,
        "max_anchors_per_component": args.max_anchors_per_component,
        "max_bridge_candidates_per_removal": args.max_bridge_candidates_per_removal,
        "query_limit": args.query_limit,
        "timeout_sec": args.timeout_sec,
    }
    for name, value in positive_int_args.items():
        if value <= 0:
            parser.error(f"--{name} must be > 0.")
    if args.low_degree_threshold < 0:
        parser.error("--low_degree_threshold must be >= 0.")


def config_from_args(args: argparse.Namespace) -> SwapConfig:
    return SwapConfig(
        protected_patterns=set(args.protected_pattern or ["symmetric"]),
        hard_protect_patterns_below_target=not args.disable_hard_protect_patterns_below_target,
        allow_relation_level_pruning_even_if_pattern_neutral=args.allow_relation_level_pruning_even_if_pattern_neutral,
        allow_overcap_replacements=args.allow_overcap_replacements,
        allow_plain_prune_when_connected=not args.disable_plain_prune_when_connected,
        relation_overcap_min_excess=args.relation_overcap_min_excess,
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
        max_swaps=args.max_swaps,
        max_removal_candidates_per_round=args.max_removal_candidates_per_round,
        max_anchors_per_component=args.max_anchors_per_component,
        max_bridge_candidates_per_removal=args.max_bridge_candidates_per_removal,
        max_hops=args.max_hops,
        query_limit=args.query_limit,
        timeout_sec=args.timeout_sec,
        wikidata_sleep_sec=args.wikidata_sleep_sec,
        user_agent=args.user_agent,
        min_net_score=args.min_net_score,
        replacement_deficit_reward_weight=args.replacement_deficit_reward_weight,
        protected_pattern_reward_weight=args.protected_pattern_reward_weight,
        replacement_surplus_penalty_weight=args.replacement_surplus_penalty_weight,
        replacement_overcap_penalty_weight=args.replacement_overcap_penalty_weight,
        unlabeled_replacement_penalty_weight=args.unlabeled_replacement_penalty_weight,
        hop_penalty_weight=args.hop_penalty_weight,
        new_entity_penalty_weight=args.new_entity_penalty_weight,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


def pruner_config_from_swap_config(config: SwapConfig) -> Any:
    return PRUNER.PrunerConfig(
        protected_patterns=set(config.protected_patterns),
        hard_protect_patterns_below_target=config.hard_protect_patterns_below_target,
        hard_preserve_largest_component=False,
        relation_overcap_min_excess=config.relation_overcap_min_excess,
        pattern_surplus_weight=config.pattern_surplus_weight,
        pattern_deficit_penalty_weight=config.pattern_deficit_penalty_weight,
        protected_pattern_penalty_weight=config.protected_pattern_penalty_weight,
        relation_overcap_weight=config.relation_overcap_weight,
        bridge_penalty=config.bridge_penalty,
        low_degree_penalty=config.low_degree_penalty,
        low_degree_threshold=config.low_degree_threshold,
        articulation_endpoint_penalty=config.articulation_endpoint_penalty,
        local_redundancy_bonus=config.local_redundancy_bonus,
        common_neighbor_bonus_cap=config.common_neighbor_bonus_cap,
        same_component_cycle_bonus=config.same_component_cycle_bonus,
        allow_relation_level_pruning_even_if_pattern_neutral=config.allow_relation_level_pruning_even_if_pattern_neutral,
        dry_run=config.dry_run,
        verbose=config.verbose,
    )


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    validate_args(parser, args)
    config = config_from_args(args)

    relation_to_patterns, pattern_targets, relation_targets = PRUNER.load_allocation_manifest(args.allocation_manifest)
    triples = PRUNER.load_triples(args.input_graph)
    relation_scope = REPAIR.load_relation_scope_manifest(args.allocation_manifest)

    pattern_index = PRUNER.PatternIndex(relation_to_patterns=relation_to_patterns)
    state = _make_state(
        triples=triples,
        pattern_index=pattern_index,
        pattern_targets=pattern_targets,
        relation_targets=relation_targets,
    )
    scorer = PRUNER.TripleRemovalScorer(config=pruner_config_from_swap_config(config))
    cache = NeighborCache()

    started = time.time()
    initial_snapshot = state.snapshot()
    moves: List[AcceptedMove] = []
    total_added = 0
    stop_reason = "max_swaps_reached"

    for round_index in range(1, config.max_swaps + 1):
        decisions = scorer.score_candidates(state)
        if not decisions:
            stop_reason = "no_positive_removal_candidates"
            break

        accepted_state: Optional[Any] = None
        accepted_move: Optional[AcceptedMove] = None

        for removal in decisions[: config.max_removal_candidates_per_round]:
            candidate_state, candidate_move = _evaluate_candidate(
                state=state,
                removal=removal,
                relation_scope=relation_scope,
                cache=cache,
                config=config,
                round_index=round_index,
            )
            if candidate_state is None or candidate_move is None:
                continue
            accepted_state = candidate_state
            accepted_move = candidate_move
            break

        if accepted_state is None or accepted_move is None:
            stop_reason = "no_acceptable_swap_or_plain_prune"
            break

        _log(
            config.verbose,
            (
                f"[round {round_index}] mode={accepted_move.mode} removed={accepted_move.removed_relation} "
                f"replacement_relations={accepted_move.replacement_relations} net_score={accepted_move.net_score:.3f} "
                f"weak_components={accepted_move.weak_components_before}->{accepted_move.weak_components_after_accept}"
            ),
        )

        if not config.dry_run:
            state = accepted_state

        total_added += len(accepted_move.replacement_triples)
        moves.append(accepted_move)

    finished = time.time()

    if config.dry_run:
        final_state = _clone_state(state)
    else:
        final_state = state

    report = {
        "started_at_epoch": started,
        "finished_at_epoch": finished,
        "duration_sec": finished - started,
        "config": asdict(config),
        "initial_snapshot": asdict(initial_snapshot),
        "final_snapshot": asdict(final_state.snapshot()),
        "moves_completed": len(moves),
        "plain_prunes_completed": sum(1 for move in moves if move.mode == "plain_prune"),
        "remove_replace_swaps_completed": sum(1 for move in moves if move.mode == "remove_replace"),
        "total_removed": len(moves),
        "total_added": total_added,
        "stop_reason": stop_reason,
        "query_stats": {
            "cache_hits": cache.cache_hits,
            "cache_misses": cache.cache_misses,
            "queries_attempted": cache.queries_attempted,
            "queries_succeeded": cache.queries_succeeded,
            "queries_failed": cache.queries_failed,
        },
        "moves": [asdict(move) for move in moves],
    }

    PRUNER.write_jsonl(args.out_graph, PRUNER.export_state_rows(final_state))
    PRUNER.write_json(args.out_report, report)


if __name__ == "__main__":
    main()
