#!/usr/bin/env python3
"""Repair weakly disconnected KG components with audit-safe run outputs.

This script reconnects non-LCC weak components by searching Wikidata for 1-hop
or 2-hop bridge paths into the largest weakly connected component (LCC).

Run-oriented output layout
--------------------------
All outputs are written under one run directory:

<output_dir>/
  manifest.json
  state.json
  events.jsonl
  graph_output.jsonl
  report.json

Design guarantees
-----------------
1. Append-safe auditing:
   - `events.jsonl` is append-only and records all useful discoveries.
2. Resumable execution:
   - `--resume` continues from `state.json` and skips completed component/anchor
     stages where possible.
3. Atomic checkpoints:
   - `state.json` and `report.json` are written atomically via temp-file rename.
4. Conservative graph mutation:
   - Only `repair_core` candidates are eligible for graph updates.
5. No silent non-core loss:
   - Non-core candidates are always logged as events for later analysis.
6. Dry-run transparency:
   - `--dry_run` still queries/classifies/logs everything, but applies no core
     bridge triples to the graph.

Bridge labels
-------------
- `repair_core`:
  relation in run-phase allocation with eta_integer > 0.
- `repair_pattern_only`:
  relation in pattern universe but not positively allocated.
- `repair_auxiliary`:
  relation outside the pattern relation universe.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import traceback
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

import networkx as nx

Triple = Tuple[str, str, str]
EdgeCounts = Dict[Triple, int]

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
DEFAULT_USER_AGENT = "kg-repair/1.0 (mailto:replace-me@example.com)"

SCRIPT_VERSION = "kg-repair-audit-safe-1.0"
STATE_SCHEMA_VERSION = 1

MANIFEST_FILENAME = "manifest.json"
STATE_FILENAME = "state.json"
EVENTS_FILENAME = "events.jsonl"
GRAPH_OUTPUT_FILENAME = "graph_output.jsonl"
REPORT_FILENAME = "report.json"

NONCORE_SAMPLE_LIMIT = 200


@dataclass(frozen=True)
class RunPaths:
    run_dir: Path
    manifest: Path
    state: Path
    events: Path
    graph_output: Path
    report: Path


@dataclass(frozen=True)
class RelationScopeInfo:
    relation: str
    in_core: bool
    in_pattern_universe: bool
    pattern: Optional[str]
    eta_integer: int
    scope_source: str
    relation_dom_rng_class: Optional[str] = None


@dataclass(frozen=True)
class BalanceSelectionPolicy:
    relation_to_patterns: Dict[str, Tuple[str, ...]]
    pattern_targets: Dict[str, int]
    relation_targets: Dict[str, int]
    protected_patterns: Set[str]


@dataclass
class BridgeCandidate:
    component_rank: int
    anchor_node: str
    bridge_triples: List[Triple]
    bridge_nodes_new: List[str]
    target_main_node: str
    label: str
    accepted_into_core: bool
    reason: str
    depth_hops: int
    query_direction: str
    selection_score: Optional[float] = None
    selection_reasons: List[str] = None


# -----------------------------------------------------------------------------
# Generic helpers
# -----------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    print(f"[{utc_now_iso()}] {msg}", flush=True)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl_atomic(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def emit_event(paths: RunPaths, event_type: str, **payload: Any) -> None:
    row: Dict[str, Any] = {
        "timestamp": utc_now_iso(),
        "event_type": event_type,
    }
    row.update(payload)
    append_jsonl(paths.events, row)


def serialize_triple(triple: Triple) -> List[str]:
    return [triple[0], triple[1], triple[2]]


def deserialize_triple(items: Sequence[str]) -> Triple:
    if len(items) != 3:
        raise ValueError(f"Expected triple list of len=3, got {items}")
    h, r, t = items
    if not all(isinstance(x, str) for x in (h, r, t)):
        raise ValueError(f"Triple list must contain strings, got: {items}")
    return (h, r, t)


def triple_to_row(triple: Triple, source: str) -> Dict[str, str]:
    h, r, t = triple
    return {"h": h, "r": r, "t": t, "source": source}


def stable_components(g: nx.DiGraph) -> List[Set[str]]:
    # Deterministic tie-break for resumable component ranks.
    comps = [set(comp) for comp in nx.weakly_connected_components(g)]
    return sorted(comps, key=lambda c: (-len(c), min(c) if c else ""))


def component_sizes(g: nx.DiGraph) -> List[int]:
    return [len(c) for c in stable_components(g)]


def counter_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    counters = state["counters"]
    return {
        "components_examined": counters["components_examined"],
        "components_repaired": counters["components_repaired"],
        "skipped_components": counters["skipped_components"],
        "bridge_candidates_examined": counters["bridge_candidates_examined"],
        "core_bridges_added": counters["core_bridges_added"],
        "candidate_counts": dict(counters["candidate_counts"]),
        "candidate_outcomes": dict(counters["candidate_outcomes"]),
        "wdqs_queries_attempted": counters["wdqs_queries_attempted"],
        "wdqs_queries_succeeded": counters["wdqs_queries_succeeded"],
        "wdqs_queries_failed": counters["wdqs_queries_failed"],
        "cache_hits": counters["cache_hits"],
        "cache_misses": counters["cache_misses"],
        "cache_entries": counters["cache_entries"],
    }


def checkpoint_state(
    paths: RunPaths,
    state: Dict[str, Any],
    reason: str,
    component_rank: Optional[int] = None,
    anchor_node: Optional[str] = None,
) -> None:
    state["updated_at"] = utc_now_iso()
    atomic_write_json(paths.state, state)
    emit_event(
        paths,
        "checkpoint_written",
        reason=reason,
        component_rank=component_rank,
        anchor_node=anchor_node,
        counts_snapshot=counter_snapshot(state),
    )
    log(f"Checkpoint saved: {reason}")


def path_or_none(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    return str(path.resolve())


def namespace_to_jsonable_dict(ns: argparse.Namespace) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in vars(ns).items():
        if isinstance(value, Path):
            out[key] = str(value.resolve())
        else:
            out[key] = value
    return out


def make_run_paths(output_dir: Path) -> RunPaths:
    run_dir = output_dir.resolve()
    return RunPaths(
        run_dir=run_dir,
        manifest=run_dir / MANIFEST_FILENAME,
        state=run_dir / STATE_FILENAME,
        events=run_dir / EVENTS_FILENAME,
        graph_output=run_dir / GRAPH_OUTPUT_FILENAME,
        report=run_dir / REPORT_FILENAME,
    )


# -----------------------------------------------------------------------------
# Data loading
# -----------------------------------------------------------------------------


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_no}, got {type(obj).__name__}")
            yield obj


def load_triples(path: Path, head_field: str = "h", rel_field: str = "r", tail_field: str = "t") -> List[Triple]:
    suffix = path.suffix.lower()

    def parse_obj(obj: dict) -> Triple:
        try:
            h = obj[head_field]
            r = obj[rel_field]
            t = obj[tail_field]
        except KeyError as exc:
            raise ValueError(
                f"Missing expected triple fields in object. Needed: {head_field}, {rel_field}, {tail_field}. "
                f"Object keys: {sorted(obj.keys())}"
            ) from exc
        if not all(isinstance(x, str) for x in (h, r, t)):
            raise ValueError(f"Triple fields must be strings, got: {(type(h).__name__, type(r).__name__, type(t).__name__)}")
        return (h, r, t)

    if suffix == ".jsonl":
        return [parse_obj(obj) for obj in _iter_jsonl(path)]

    data = _load_json(path)
    if isinstance(data, list):
        return [parse_obj(obj) for obj in data]
    if isinstance(data, dict):
        triples = data.get("triples") or data.get("triples_out")
        if not isinstance(triples, list):
            raise ValueError("JSON dict input must contain list key 'triples' or 'triples_out'.")
        return [parse_obj(obj) for obj in triples]

    raise ValueError(f"Unsupported input JSON structure in {path}")


def load_allowed_relations(path: Path, rel_field: str = "r") -> Dict[str, RelationScopeInfo]:
    """Backward-compatible flat relation loader.

    In this mode every loaded relation is treated as core-eligible.
    """
    suffix = path.suffix.lower()
    rels: Set[str]

    if suffix == ".jsonl":
        rels = set()
        for obj in _iter_jsonl(path):
            if rel_field in obj and isinstance(obj[rel_field], str):
                rels.add(obj[rel_field])
            elif "relation" in obj and isinstance(obj["relation"], str):
                rels.add(obj["relation"])
            else:
                raise ValueError(f"JSONL relation row missing '{rel_field}' or 'relation': {obj}")
    else:
        data = _load_json(path)
        if isinstance(data, list):
            if not all(isinstance(x, str) for x in data):
                raise ValueError("Allowed relations JSON list must contain only strings.")
            rels = set(data)
        elif isinstance(data, dict):
            rels = set()
            for key in ("allowed_relations", "relations"):
                value = data.get(key)
                if isinstance(value, list) and all(isinstance(x, str) for x in value):
                    rels = set(value)
                    break
            if not rels:
                raise ValueError("Allowed relations JSON dict must contain list key 'allowed_relations' or 'relations'.")
        else:
            raise ValueError(f"Unsupported allowed-relations format in {path}")

    return {
        rel: RelationScopeInfo(
            relation=rel,
            in_core=True,
            in_pattern_universe=True,
            pattern=None,
            eta_integer=1,
            scope_source="flat_allowed_relations",
            relation_dom_rng_class=None,
        )
        for rel in sorted(rels)
    }


def load_relation_scope_manifest(path: Path) -> Dict[str, RelationScopeInfo]:
    """Load relation scope from run-phase allocation manifest."""
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ValueError("Relation scope manifest must be a JSON object.")

    pattern_groups = data.get("pattern_groups")
    if not isinstance(pattern_groups, dict):
        raise ValueError("Manifest must contain a 'pattern_groups' object.")

    pattern_by_relation: Dict[str, str] = {}
    pattern_universe: Set[str] = set()
    for pattern_name, rels in pattern_groups.items():
        if not isinstance(rels, list) or not all(isinstance(x, str) for x in rels):
            raise ValueError(f"pattern_groups[{pattern_name!r}] must be a list of relation IDs.")
        for rel in rels:
            pattern_universe.add(rel)
            pattern_by_relation.setdefault(rel, pattern_name)

    allocation_rows: List[dict] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if {"pattern", "relation", "eta_integer"}.issubset(obj.keys()):
                allocation_rows.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)

    eta_by_relation: Dict[str, int] = {}
    dom_rng_by_relation: Dict[str, Optional[str]] = {}
    alloc_pattern_by_relation: Dict[str, str] = {}
    for row in allocation_rows:
        relation = row.get("relation")
        pattern = row.get("pattern")
        eta_integer = row.get("eta_integer")
        if not isinstance(relation, str) or not isinstance(pattern, str) or not isinstance(eta_integer, int):
            continue
        eta_by_relation[relation] = max(eta_by_relation.get(relation, 0), eta_integer)
        alloc_pattern_by_relation[relation] = pattern
        dom_rng = row.get("relation_dom_rng_class")
        dom_rng_by_relation[relation] = dom_rng if isinstance(dom_rng, str) else None
        pattern_universe.add(relation)
        pattern_by_relation.setdefault(relation, pattern)

    scope: Dict[str, RelationScopeInfo] = {}
    for relation in sorted(pattern_universe | set(eta_by_relation.keys())):
        eta_integer = int(eta_by_relation.get(relation, 0))
        in_core = eta_integer > 0
        in_pattern_universe = relation in pattern_universe
        if in_core:
            scope_source = "allocated_eta_positive"
        elif in_pattern_universe:
            scope_source = "pattern_group_only"
        else:
            scope_source = "out_of_scope"
        scope[relation] = RelationScopeInfo(
            relation=relation,
            in_core=in_core,
            in_pattern_universe=in_pattern_universe,
            pattern=alloc_pattern_by_relation.get(relation) or pattern_by_relation.get(relation),
            eta_integer=eta_integer,
            scope_source=scope_source,
            relation_dom_rng_class=dom_rng_by_relation.get(relation),
        )
    return scope


def load_balance_selection_policy(path: Path, protected_patterns: Optional[Iterable[str]] = None) -> Optional[BalanceSelectionPolicy]:
    data = _load_json(path)
    if not isinstance(data, dict):
        return None

    pattern_groups = data.get("pattern_groups")
    allocations = data.get("allocations")
    if not isinstance(pattern_groups, dict) or not isinstance(allocations, list):
        return None

    relation_to_patterns: Dict[str, Set[str]] = defaultdict(set)
    pattern_targets: Dict[str, int] = {}
    relation_targets: Dict[str, int] = defaultdict(int)

    for pattern_name, rels in pattern_groups.items():
        if pattern_name in {"universe", "relations_universe"}:
            continue
        if not isinstance(rels, list):
            continue
        for rel in rels:
            if isinstance(rel, str):
                relation_to_patterns[rel].add(str(pattern_name))

    eta_per_group = data.get("eta_per_group")
    if isinstance(eta_per_group, dict):
        for pattern_name, value in eta_per_group.items():
            try:
                pattern_targets[str(pattern_name)] = int(value)
            except (TypeError, ValueError):
                continue

    fallback_pattern_targets: Dict[str, int] = {}
    for row in allocations:
        if not isinstance(row, dict):
            continue
        relation = row.get("relation")
        if not isinstance(relation, str):
            continue

        pattern = row.get("pattern")
        if isinstance(pattern, str) and pattern:
            relation_to_patterns[relation].add(pattern)

        try:
            eta_integer = int(row.get("eta_integer", row.get("target", 0)) or 0)
        except (TypeError, ValueError):
            eta_integer = 0
        relation_targets[relation] += eta_integer

        if isinstance(pattern, str) and pattern:
            eta_total = row.get("eta_total")
            if eta_total is not None:
                try:
                    fallback_pattern_targets[pattern] = max(fallback_pattern_targets.get(pattern, 0), int(eta_total))
                except (TypeError, ValueError):
                    pass

    if not pattern_targets:
        pattern_targets.update(fallback_pattern_targets)

    if not relation_to_patterns or not pattern_targets:
        return None

    return BalanceSelectionPolicy(
        relation_to_patterns={rel: tuple(sorted(patterns)) for rel, patterns in relation_to_patterns.items()},
        pattern_targets=dict(pattern_targets),
        relation_targets=dict(relation_targets),
        protected_patterns=set(protected_patterns or {"symmetric"}),
    )


def compute_balance_observed_counts(
    edge_counts: EdgeCounts,
    policy: BalanceSelectionPolicy,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    relation_counts: Dict[str, int] = defaultdict(int)
    pattern_counts: Dict[str, int] = defaultdict(int)
    for (_h, relation, _t), count in edge_counts.items():
        relation_counts[relation] += count
        for pattern in policy.relation_to_patterns.get(relation, tuple()):
            pattern_counts[pattern] += count
    return dict(relation_counts), dict(pattern_counts)


def score_balance_aware_core_candidate(
    *,
    candidate: BridgeCandidate,
    policy: Optional[BalanceSelectionPolicy],
    current_relation_counts: Mapping[str, int],
    current_pattern_counts: Mapping[str, int],
) -> Tuple[float, List[str]] | None:
    if policy is None:
        return 0.0, []

    relation_adds: Dict[str, int] = defaultdict(int)
    pattern_adds: Dict[str, int] = defaultdict(int)
    for _h, relation, _t in candidate.bridge_triples:
        relation_adds[relation] += 1
        for pattern in policy.relation_to_patterns.get(relation, tuple()):
            pattern_adds[pattern] += 1

    reasons: List[str] = []
    score = 0.0

    for relation, add_count in relation_adds.items():
        cap = policy.relation_targets.get(relation)
        if cap is None:
            continue
        projected = current_relation_counts.get(relation, 0) + add_count
        if projected > cap:
            return None

    for pattern, add_count in pattern_adds.items():
        target = policy.pattern_targets.get(pattern)
        if target is None:
            continue
        current = current_pattern_counts.get(pattern, 0)
        projected = current + add_count
        if projected > target:
            return None

        deficit_before = max(0, target - current)
        deficit_after = max(0, target - projected)
        deficit_improvement = deficit_before - deficit_after
        if deficit_improvement > 0:
            score += 50.0 * deficit_improvement
            reasons.append(f"helps_deficit:{pattern}:{deficit_improvement}")
            if pattern in policy.protected_patterns:
                score += 25.0 * deficit_improvement
                reasons.append(f"helps_protected_deficit:{pattern}:{deficit_improvement}")

    score -= 5.0 * max(0, candidate.depth_hops - 1)
    if candidate.bridge_nodes_new:
        score -= 2.0 * len(candidate.bridge_nodes_new)
        reasons.append(f"new_entities:{len(candidate.bridge_nodes_new)}")

    return score, reasons


def is_better_core_candidate(candidate: BridgeCandidate, incumbent: Optional[BridgeCandidate]) -> bool:
    if incumbent is None:
        return True

    candidate_score = candidate.selection_score if candidate.selection_score is not None else float("-inf")
    incumbent_score = incumbent.selection_score if incumbent.selection_score is not None else float("-inf")
    if candidate_score != incumbent_score:
        return candidate_score > incumbent_score
    if candidate.depth_hops != incumbent.depth_hops:
        return candidate.depth_hops < incumbent.depth_hops
    if len(candidate.bridge_nodes_new) != len(incumbent.bridge_nodes_new):
        return len(candidate.bridge_nodes_new) < len(incumbent.bridge_nodes_new)
    return tuple(candidate.bridge_triples) < tuple(incumbent.bridge_triples)


# -----------------------------------------------------------------------------
# Graph helpers
# -----------------------------------------------------------------------------


def aggregate_triples(triples: Iterable[Triple]) -> EdgeCounts:
    counts: EdgeCounts = defaultdict(int)
    for triple in triples:
        counts[triple] += 1
    return dict(counts)


def build_digraph(edge_counts: EdgeCounts) -> nx.DiGraph:
    g = nx.DiGraph()
    for (h, r, t), count in edge_counts.items():
        if g.has_edge(h, t):
            g[h][t].setdefault("relations", set()).add(r)
            g[h][t]["weight"] = g[h][t].get("weight", 1) + count
        else:
            g.add_edge(h, t, weight=count, relations={r})
    return g


def node_total_degree(g: nx.DiGraph, node: str) -> int:
    return int(g.in_degree(node) + g.out_degree(node))


def pick_component_anchors(g: nx.DiGraph, component_nodes: Set[str], top_k: int) -> List[str]:
    ranked = sorted(component_nodes, key=lambda n: (node_total_degree(g, n), g.out_degree(n), g.in_degree(n), n), reverse=True)
    return ranked[:top_k]


def add_bridge_to_counts(edge_counts: EdgeCounts, candidate: BridgeCandidate) -> List[Triple]:
    added: List[Triple] = []
    for triple in candidate.bridge_triples:
        if triple not in edge_counts:
            edge_counts[triple] = 1
            added.append(triple)
    return added


# -----------------------------------------------------------------------------
# Scope / classification
# -----------------------------------------------------------------------------


def classify_relation_scope(relation: str, relation_scope: Dict[str, RelationScopeInfo]) -> RelationScopeInfo:
    info = relation_scope.get(relation)
    if info is not None:
        return info
    return RelationScopeInfo(
        relation=relation,
        in_core=False,
        in_pattern_universe=False,
        pattern=None,
        eta_integer=0,
        scope_source="out_of_scope",
        relation_dom_rng_class=None,
    )


def classify_bridge_label(scope_infos: List[RelationScopeInfo]) -> str:
    if all(info.in_core for info in scope_infos):
        return "repair_core"
    if all(info.in_pattern_universe for info in scope_infos):
        return "repair_pattern_only"
    return "repair_auxiliary"


# -----------------------------------------------------------------------------
# SPARQL / Wikidata querying
# -----------------------------------------------------------------------------


def qid_to_iri(qid: str) -> str:
    if not qid.startswith("Q"):
        raise ValueError(f"Expected Wikidata QID, got: {qid}")
    return f"wd:{qid}"


def uri_to_pid(uri: str) -> Optional[str]:
    prefix = "http://www.wikidata.org/prop/direct/"
    if uri.startswith(prefix):
        return uri[len(prefix):]
    return None


def uri_to_qid(uri: str) -> Optional[str]:
    prefix = "http://www.wikidata.org/entity/"
    if uri.startswith(prefix):
        tail = uri[len(prefix):]
        if tail.startswith("Q"):
            return tail
    return None


def run_sparql(query: str, user_agent: str, timeout_sec: int) -> dict:
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    url = f"{SPARQL_ENDPOINT}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": user_agent,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_bindings(result: dict) -> List[dict]:
    try:
        return result["results"]["bindings"]
    except KeyError as exc:
        raise ValueError(f"Unexpected SPARQL result shape: keys={sorted(result.keys())}") from exc


def query_one_hop_neighbors(qid: str, direction: str, user_agent: str, timeout_sec: int, limit: int) -> List[Triple]:
    if direction not in {"out", "in"}:
        raise ValueError(f"direction must be 'out' or 'in', got {direction}")

    if direction == "out":
        query = f"""
        SELECT ?p ?other WHERE {{
          {qid_to_iri(qid)} ?p ?other .
          FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct/"))
          FILTER(STRSTARTS(STR(?other), "http://www.wikidata.org/entity/Q"))
        }}
        LIMIT {limit}
        """
    else:
        query = f"""
        SELECT ?s ?p WHERE {{
          ?s ?p {qid_to_iri(qid)} .
          FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct/"))
          FILTER(STRSTARTS(STR(?s), "http://www.wikidata.org/entity/Q"))
        }}
        LIMIT {limit}
        """

    result = run_sparql(query=query, user_agent=user_agent, timeout_sec=timeout_sec)
    triples: List[Triple] = []
    for row in extract_bindings(result):
        if direction == "out":
            pid = uri_to_pid(row["p"]["value"])
            other = uri_to_qid(row["other"]["value"])
            if pid and other:
                triples.append((qid, pid, other))
        else:
            src = uri_to_qid(row["s"]["value"])
            pid = uri_to_pid(row["p"]["value"])
            if src and pid:
                triples.append((src, pid, qid))
    return triples


def cache_key(qid: str, direction: str, limit: int) -> str:
    return f"{qid}|{direction}|{limit}"


def get_neighbors_cached(
    *,
    state: Dict[str, Any],
    paths: RunPaths,
    qid: str,
    direction: str,
    limit: int,
    user_agent: str,
    timeout_sec: int,
    component_rank: int,
    anchor_node: str,
    query_depth: int,
    query_stage: str,
    mid_node: Optional[str] = None,
) -> Optional[List[Triple]]:
    counters = state["counters"]
    qcache: Dict[str, List[List[str]]] = state["query_cache"]
    key = cache_key(qid=qid, direction=direction, limit=limit)

    if key in qcache:
        counters["cache_hits"] += 1
        emit_event(
            paths,
            "cache_hit",
            cache_key=key,
            qid=qid,
            direction=direction,
            component_rank=component_rank,
            anchor_node=anchor_node,
            query_depth=query_depth,
            query_stage=query_stage,
            mid_node=mid_node,
        )
        return [deserialize_triple(x) for x in qcache[key]]

    counters["cache_misses"] += 1
    emit_event(
        paths,
        "cache_miss",
        cache_key=key,
        qid=qid,
        direction=direction,
        component_rank=component_rank,
        anchor_node=anchor_node,
        query_depth=query_depth,
        query_stage=query_stage,
        mid_node=mid_node,
    )

    counters["wdqs_queries_attempted"] += 1
    emit_event(
        paths,
        "wdqs_query_started",
        qid=qid,
        direction=direction,
        component_rank=component_rank,
        anchor_node=anchor_node,
        query_depth=query_depth,
        query_stage=query_stage,
        query_limit=limit,
        timeout_sec=timeout_sec,
        mid_node=mid_node,
    )

    try:
        triples = query_one_hop_neighbors(
            qid=qid,
            direction=direction,
            user_agent=user_agent,
            timeout_sec=timeout_sec,
            limit=limit,
        )
    except Exception as exc:
        counters["wdqs_queries_failed"] += 1
        counters["candidate_outcomes"]["query_failed"] += 1
        emit_event(
            paths,
            "wdqs_query_failed",
            qid=qid,
            direction=direction,
            component_rank=component_rank,
            anchor_node=anchor_node,
            query_depth=query_depth,
            query_stage=query_stage,
            mid_node=mid_node,
            error=str(exc),
        )
        return None

    counters["wdqs_queries_succeeded"] += 1
    qcache[key] = [serialize_triple(t) for t in triples]
    counters["cache_entries"] = len(qcache)
    emit_event(
        paths,
        "wdqs_query_finished",
        qid=qid,
        direction=direction,
        component_rank=component_rank,
        anchor_node=anchor_node,
        query_depth=query_depth,
        query_stage=query_stage,
        mid_node=mid_node,
        result_count=len(triples),
    )
    return triples


# -----------------------------------------------------------------------------
# Run state / reporting
# -----------------------------------------------------------------------------


def initial_state(original_stats: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "script_version": SCRIPT_VERSION,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "dry_run": dry_run,
        "completed": False,
        "successful": False,
        "interrupted": False,
        "run_finished_at": None,
        "current_component_rank": None,
        "current_anchor_node": None,
        "current_stage": None,
        "processed_component_ranks": [],
        "repaired_component_ranks": [],
        "components": {},
        "added_core_triples": [],
        "query_cache": {},
        "resumptions": 0,
        "component_outcome_breakdown": {
            "repairable_with_core": 0,
            "repairable_with_pattern_only": 0,
            "repairable_with_auxiliary_only": 0,
            "no_bridge_found": 0,
        },
        "counters": {
            "components_examined": 0,
            "components_repaired": 0,
            "skipped_components": 0,
            "bridge_candidates_examined": 0,
            "core_bridges_added": 0,
            "candidate_counts": {
                "repair_core": 0,
                "repair_pattern_only": 0,
                "repair_auxiliary": 0,
            },
            "candidate_outcomes": {
                "applied_core": 0,
                "rejected_balance_policy": 0,
                "duplicate_core_candidate": 0,
                "dry_run_not_applied": 0,
                "rejected_pattern_only": 0,
                "rejected_auxiliary": 0,
                "skipped_due_to_resume": 0,
                "query_failed": 0,
            },
            "wdqs_queries_attempted": 0,
            "wdqs_queries_succeeded": 0,
            "wdqs_queries_failed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_entries": 0,
        },
        "original_stats": original_stats,
        "warnings": [],
        "notes": [],
        "last_error": None,
        # Optional compatibility channel when --collect_noncore is set.
        "noncore_candidate_samples": [],
    }


def ensure_state_defaults(state: Dict[str, Any]) -> None:
    state.setdefault("processed_component_ranks", [])
    state.setdefault("repaired_component_ranks", [])
    state.setdefault("warnings", [])
    state.setdefault("notes", [])
    state.setdefault("last_error", None)
    state.setdefault("noncore_candidate_samples", [])
    state.setdefault("component_outcome_breakdown", {})
    cob = state["component_outcome_breakdown"]
    cob.setdefault("repairable_with_core", 0)
    cob.setdefault("repairable_with_pattern_only", 0)
    cob.setdefault("repairable_with_auxiliary_only", 0)
    cob.setdefault("no_bridge_found", 0)

    counters = state["counters"]
    counters.setdefault("candidate_counts", {})
    counters.setdefault("candidate_outcomes", {})
    counters["candidate_counts"].setdefault("repair_core", 0)
    counters["candidate_counts"].setdefault("repair_pattern_only", 0)
    counters["candidate_counts"].setdefault("repair_auxiliary", 0)
    counters["candidate_outcomes"].setdefault("applied_core", 0)
    counters["candidate_outcomes"].setdefault("rejected_balance_policy", 0)
    counters["candidate_outcomes"].setdefault("duplicate_core_candidate", 0)
    counters["candidate_outcomes"].setdefault("dry_run_not_applied", 0)
    counters["candidate_outcomes"].setdefault("rejected_pattern_only", 0)
    counters["candidate_outcomes"].setdefault("rejected_auxiliary", 0)
    counters["candidate_outcomes"].setdefault("skipped_due_to_resume", 0)
    counters["candidate_outcomes"].setdefault("query_failed", 0)
    counters.setdefault("components_examined", 0)
    counters.setdefault("components_repaired", 0)
    counters.setdefault("skipped_components", 0)
    counters.setdefault("bridge_candidates_examined", 0)
    counters.setdefault("core_bridges_added", 0)
    counters.setdefault("wdqs_queries_attempted", 0)
    counters.setdefault("wdqs_queries_succeeded", 0)
    counters.setdefault("wdqs_queries_failed", 0)
    counters.setdefault("cache_hits", 0)
    counters.setdefault("cache_misses", 0)
    counters.setdefault("cache_entries", len(state.get("query_cache", {})))


def ensure_component_state(state: Dict[str, Any], component_rank: int, anchors: List[str]) -> Dict[str, Any]:
    key = str(component_rank)
    comp = state["components"].get(key)
    if comp is None:
        comp = {
            "status": "pending",
            "anchors": list(anchors),
            "processed_anchors": [],
            "anchor_stages": {},
            "found_labels": {
                "repair_core": 0,
                "repair_pattern_only": 0,
                "repair_auxiliary": 0,
            },
            "selected_core_candidate": None,
            "outcome": None,
            "examined_counted": False,
            "outcome_counted": False,
            "applied_core": False,
        }
        state["components"][key] = comp
    else:
        if not comp.get("anchors"):
            comp["anchors"] = list(anchors)
    return comp


def ensure_anchor_state(component_state: Dict[str, Any], anchor: str) -> Dict[str, Any]:
    anchor_stages = component_state["anchor_stages"]
    info = anchor_stages.get(anchor)
    if info is None:
        info = {
            "one_hop_done": False,
            "two_hop_done": False,
            "completed": False,
            "selected_core": False,
        }
        anchor_stages[anchor] = info
    return info


def finalize_component_outcome(state: Dict[str, Any], component_state: Dict[str, Any]) -> str:
    if component_state.get("outcome_counted"):
        return str(component_state.get("outcome"))

    labels = component_state["found_labels"]
    if labels["repair_core"] > 0:
        outcome = "repairable_with_core"
    elif labels["repair_pattern_only"] > 0:
        outcome = "repairable_with_pattern_only"
    elif labels["repair_auxiliary"] > 0:
        outcome = "repairable_with_auxiliary_only"
    else:
        outcome = "no_bridge_found"

    component_state["outcome"] = outcome
    component_state["outcome_counted"] = True
    state["component_outcome_breakdown"][outcome] += 1
    return outcome


def candidate_to_event_payload(candidate: BridgeCandidate) -> Dict[str, Any]:
    payload = {
        "component_rank": candidate.component_rank,
        "anchor_node": candidate.anchor_node,
        "query_depth": candidate.depth_hops,
        "query_direction": candidate.query_direction,
        "bridge_triples": [serialize_triple(t) for t in candidate.bridge_triples],
        "bridge_nodes_new": list(candidate.bridge_nodes_new),
        "target_main_node": candidate.target_main_node,
        "classification_label": candidate.label,
        "accepted_into_core": candidate.accepted_into_core,
        "reason": candidate.reason,
    }
    if candidate.selection_score is not None:
        payload["selection_score"] = candidate.selection_score
    if candidate.selection_reasons:
        payload["selection_reasons"] = list(candidate.selection_reasons)
    return payload


def record_candidate(
    *,
    state: Dict[str, Any],
    paths: RunPaths,
    component_state: Dict[str, Any],
    candidate: BridgeCandidate,
    collect_noncore: bool,
) -> None:
    label = candidate.label
    counters = state["counters"]
    counters["candidate_counts"][label] += 1
    component_state["found_labels"][label] += 1

    emit_event(paths, "candidate_found", **candidate_to_event_payload(candidate))

    if label == "repair_core":
        emit_event(
            paths,
            "candidate_classified",
            **candidate_to_event_payload(candidate),
            acceptance_decision="eligible_for_core_scoring",
            final_outcome="pending_core_scoring",
        )
        return

    if label == "repair_pattern_only":
        outcome = "rejected_pattern_only"
    else:
        outcome = "rejected_auxiliary"

    counters["candidate_outcomes"][outcome] += 1
    emit_event(
        paths,
        "candidate_classified",
        **candidate_to_event_payload(candidate),
        acceptance_decision="rejected_for_core",
        final_outcome=outcome,
    )
    emit_event(
        paths,
        "candidate_saved_noncore",
        **candidate_to_event_payload(candidate),
        final_outcome=outcome,
    )

    if collect_noncore and len(state["noncore_candidate_samples"]) < NONCORE_SAMPLE_LIMIT:
        state["noncore_candidate_samples"].append(
            {
                "component_rank": candidate.component_rank,
                "anchor_node": candidate.anchor_node,
                "classification_label": label,
                "bridge_triples": [serialize_triple(t) for t in candidate.bridge_triples],
                "reason": candidate.reason,
            }
        )


def summarize_report(state: Dict[str, Any], final_graph: nx.DiGraph) -> Dict[str, Any]:
    final_sizes = component_sizes(final_graph)
    counters = state["counters"]
    report = {
        "script_version": SCRIPT_VERSION,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "dry_run": state["dry_run"],
        "completed": state["completed"],
        "successful": state["successful"],
        "interrupted": state["interrupted"],
        "resumptions": state["resumptions"],
        "original_graph": dict(state["original_stats"]),
        "final_graph": {
            "nodes": final_graph.number_of_nodes(),
            "weak_components": len(final_sizes),
            "top_component_sizes": final_sizes[:10],
            "largest_component_size": final_sizes[0] if final_sizes else 0,
        },
        "candidate_counts_by_label": dict(counters["candidate_counts"]),
        "candidate_outcomes": dict(counters["candidate_outcomes"]),
        "wdqs_queries": {
            "attempted": counters["wdqs_queries_attempted"],
            "succeeded": counters["wdqs_queries_succeeded"],
            "failed": counters["wdqs_queries_failed"],
        },
        "cache_stats": {
            "cache_hits": counters["cache_hits"],
            "cache_misses": counters["cache_misses"],
            "cache_entries": counters["cache_entries"],
        },
        "component_outcome_breakdown": dict(state["component_outcome_breakdown"]),
        "components_examined": counters["components_examined"],
        "components_repaired": counters["components_repaired"],
        "skipped_components": counters["skipped_components"],
        "bridge_candidates_examined": counters["bridge_candidates_examined"],
        "core_bridges_added": counters["core_bridges_added"],
        "added_core_triples_count": len(state["added_core_triples"]),
        "repaired_component_ranks": list(state["repaired_component_ranks"]),
        "processed_component_ranks": list(state["processed_component_ranks"]),
        "run_finished_at": state["run_finished_at"],
        "warnings": list(state["warnings"]),
        "notes": list(state["notes"]),
        "last_error": state["last_error"],
    }
    return report


def write_report_snapshot(paths: RunPaths, state: Dict[str, Any], edge_counts: EdgeCounts) -> None:
    final_graph = build_digraph(edge_counts)
    report = summarize_report(state=state, final_graph=final_graph)
    atomic_write_json(paths.report, report)


def initialize_or_recover_graph_output(
    *,
    paths: RunPaths,
    original_triples: List[Triple],
    added_core_triples: Set[Triple],
    resume: bool,
) -> None:
    if resume and paths.graph_output.exists():
        return

    original_triples_set = set(original_triples)
    rows: List[Dict[str, str]] = []
    for triple in sorted(original_triples_set):
        rows.append(triple_to_row(triple, source="original"))
    for triple in sorted(added_core_triples - original_triples_set):
        rows.append(triple_to_row(triple, source="repair_core"))
    write_jsonl_atomic(paths.graph_output, rows)


# -----------------------------------------------------------------------------
# Resume / manifest
# -----------------------------------------------------------------------------


def build_manifest(args: argparse.Namespace, relation_scope_source: str, paths: RunPaths) -> Dict[str, Any]:
    return {
        "script_version": SCRIPT_VERSION,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "output_dir": str(paths.run_dir),
        "hostname": socket.gethostname(),
        "python_version": sys.version,
        "dry_run": args.dry_run,
        "policy_summary": {
            "core_policy": "relation has eta_integer > 0 in run-phase allocation manifest "
            "(or always true in --allowed_relations compatibility mode)",
            "pattern_only_policy": "relation in pattern_groups but not positively allocated",
            "auxiliary_policy": "relation outside pattern relation universe",
            "graph_mutation_policy": "only repair_core triples may update graph, and never in dry_run",
            "core_selection_policy": "balance-aware best-core ranking when relation_scope_manifest is provided, unless --disable_balance_aware_core_selection is set",
            "non_core_retention_policy": "non-core discoveries are always persisted as events",
            "resume_policy": "resume from component/anchor/stage checkpoints where possible",
        },
        "inputs": {
            "input_triples": str(args.input_triples.resolve()),
            "relation_scope_manifest": path_or_none(args.relation_scope_manifest),
            "allowed_relations": path_or_none(args.allowed_relations),
            "relation_scope_source": relation_scope_source,
        },
        "cli_args": namespace_to_jsonable_dict(args),
    }


def assert_run_dir_for_new_run(paths: RunPaths) -> None:
    if paths.run_dir.exists():
        if any(paths.run_dir.iterdir()):
            raise ValueError(
                f"Output directory already exists and is non-empty: {paths.run_dir}. "
                "Use a fresh --output_dir or run with --resume."
            )
    else:
        paths.run_dir.mkdir(parents=True, exist_ok=True)


def validate_resume_compatibility(args: argparse.Namespace, manifest: Dict[str, Any], state: Dict[str, Any]) -> None:
    if not isinstance(state, dict):
        raise ValueError("state.json is not a JSON object.")
    if "schema_version" not in state or "components" not in state or "counters" not in state or "query_cache" not in state:
        raise ValueError("state.json is missing required resumable fields.")
    if state.get("completed"):
        raise ValueError("Run is already completed; refusing --resume.")

    cli_args = manifest.get("cli_args")
    if not isinstance(cli_args, dict):
        raise ValueError("manifest.json is missing 'cli_args'; cannot validate resume compatibility.")

    expected = namespace_to_jsonable_dict(args)
    must_match = [
        "input_triples",
        "relation_scope_manifest",
        "allowed_relations",
        "head_field",
        "rel_field",
        "tail_field",
        "max_components",
        "anchor_nodes_per_component",
        "query_limit",
        "timeout_sec",
        "disable_balance_aware_core_selection",
        "protected_pattern",
        "dry_run",
    ]
    for key in must_match:
        if cli_args.get(key) != expected.get(key):
            raise ValueError(
                f"Resume incompatible for argument '{key}': previous={cli_args.get(key)!r}, now={expected.get(key)!r}."
            )


def load_or_init_run(
    *,
    args: argparse.Namespace,
    paths: RunPaths,
    relation_scope_source: str,
    original_stats: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if args.resume:
        if not paths.run_dir.exists():
            raise ValueError(f"Cannot resume: output directory does not exist: {paths.run_dir}")
        if not paths.manifest.exists() or not paths.state.exists():
            raise ValueError("Cannot resume: manifest.json or state.json is missing.")
        manifest = _load_json(paths.manifest)
        state = _load_json(paths.state)
        validate_resume_compatibility(args=args, manifest=manifest, state=state)
        ensure_state_defaults(state)
        state["resumptions"] = int(state.get("resumptions", 0)) + 1
        state["notes"].append(f"Resumed at {utc_now_iso()}")
        log(f"Resuming run from {paths.run_dir}")
        emit_event(paths, "run_started", resume=True, resumptions=state["resumptions"], dry_run=args.dry_run)
        checkpoint_state(paths, state, reason="resume_loaded")
        return manifest, state

    assert_run_dir_for_new_run(paths)
    manifest = build_manifest(args=args, relation_scope_source=relation_scope_source, paths=paths)
    state = initial_state(original_stats=original_stats, dry_run=args.dry_run)
    atomic_write_json(paths.manifest, manifest)
    atomic_write_json(paths.state, state)
    emit_event(paths, "run_started", resume=False, dry_run=args.dry_run)
    log(f"Started new run in {paths.run_dir}")
    return manifest, state


# -----------------------------------------------------------------------------
# Candidate search
# -----------------------------------------------------------------------------


def find_one_hop_bridge(
    *,
    state: Dict[str, Any],
    paths: RunPaths,
    component_state: Dict[str, Any],
    component_rank: int,
    anchor: str,
    main_nodes: Set[str],
    relation_scope: Dict[str, RelationScopeInfo],
    balance_policy: Optional[BalanceSelectionPolicy],
    current_relation_counts: Mapping[str, int],
    current_pattern_counts: Mapping[str, int],
    user_agent: str,
    timeout_sec: int,
    query_limit: int,
    collect_noncore: bool,
) -> Optional[BridgeCandidate]:
    best_candidate: Optional[BridgeCandidate] = None
    best_score: Optional[float] = None
    for direction in ("out", "in"):
        triples = get_neighbors_cached(
            state=state,
            paths=paths,
            qid=anchor,
            direction=direction,
            limit=query_limit,
            user_agent=user_agent,
            timeout_sec=timeout_sec,
            component_rank=component_rank,
            anchor_node=anchor,
            query_depth=1,
            query_stage="one_hop",
            mid_node=None,
        )
        if triples is None:
            continue

        for triple in triples:
            h, r, t = triple
            other = t if h == anchor else h
            if other not in main_nodes:
                continue
            scope_info = classify_relation_scope(r, relation_scope)
            label = classify_bridge_label([scope_info])
            candidate = BridgeCandidate(
                component_rank=component_rank,
                anchor_node=anchor,
                bridge_triples=[triple],
                bridge_nodes_new=[],
                target_main_node=other,
                label=label,
                accepted_into_core=(label == "repair_core"),
                reason=f"one_hop_direct_main_connection::{scope_info.scope_source}",
                depth_hops=1,
                query_direction=direction,
            )
            record_candidate(
                state=state,
                paths=paths,
                component_state=component_state,
                candidate=candidate,
                collect_noncore=collect_noncore,
            )
            if not candidate.accepted_into_core:
                continue

            scored = score_balance_aware_core_candidate(
                candidate=candidate,
                policy=balance_policy,
                current_relation_counts=current_relation_counts,
                current_pattern_counts=current_pattern_counts,
            )
            if scored is None:
                state["counters"]["candidate_outcomes"]["rejected_balance_policy"] += 1
                emit_event(
                    paths,
                    "candidate_balance_rejected",
                    **candidate_to_event_payload(candidate),
                    final_outcome="rejected_balance_policy",
                )
                continue

            score, reasons = scored
            candidate.selection_score = score
            candidate.selection_reasons = reasons
            emit_event(
                paths,
                "candidate_scored_for_core",
                **candidate_to_event_payload(candidate),
            )
            if best_score is None or score > best_score:
                best_candidate = candidate
                best_score = score

    if best_candidate is not None:
        emit_event(paths, "core_bridge_selected", **candidate_to_event_payload(best_candidate))
    return best_candidate


def find_two_hop_bridge(
    *,
    state: Dict[str, Any],
    paths: RunPaths,
    component_state: Dict[str, Any],
    component_rank: int,
    anchor: str,
    main_nodes: Set[str],
    relation_scope: Dict[str, RelationScopeInfo],
    balance_policy: Optional[BalanceSelectionPolicy],
    current_relation_counts: Mapping[str, int],
    current_pattern_counts: Mapping[str, int],
    user_agent: str,
    timeout_sec: int,
    query_limit: int,
    collect_noncore: bool,
) -> Optional[BridgeCandidate]:
    best_candidate: Optional[BridgeCandidate] = None
    best_score: Optional[float] = None
    for direction1 in ("out", "in"):
        first_hop = get_neighbors_cached(
            state=state,
            paths=paths,
            qid=anchor,
            direction=direction1,
            limit=query_limit,
            user_agent=user_agent,
            timeout_sec=timeout_sec,
            component_rank=component_rank,
            anchor_node=anchor,
            query_depth=2,
            query_stage="two_hop_first",
            mid_node=None,
        )
        if first_hop is None:
            continue

        for triple1 in first_hop:
            h1, _, t1 = triple1
            mid = t1 if h1 == anchor else h1
            if mid in main_nodes:
                continue

            for direction2 in ("out", "in"):
                second_hop = get_neighbors_cached(
                    state=state,
                    paths=paths,
                    qid=mid,
                    direction=direction2,
                    limit=query_limit,
                    user_agent=user_agent,
                    timeout_sec=timeout_sec,
                    component_rank=component_rank,
                    anchor_node=anchor,
                    query_depth=2,
                    query_stage="two_hop_second",
                    mid_node=mid,
                )
                if second_hop is None:
                    continue

                for triple2 in second_hop:
                    h2, _, t2 = triple2
                    other2 = t2 if h2 == mid else h2
                    if other2 not in main_nodes:
                        continue

                    scope_info_1 = classify_relation_scope(triple1[1], relation_scope)
                    scope_info_2 = classify_relation_scope(triple2[1], relation_scope)
                    label = classify_bridge_label([scope_info_1, scope_info_2])
                    candidate = BridgeCandidate(
                        component_rank=component_rank,
                        anchor_node=anchor,
                        bridge_triples=[triple1, triple2],
                        bridge_nodes_new=[mid] if mid not in main_nodes else [],
                        target_main_node=other2,
                        label=label,
                        accepted_into_core=(label == "repair_core"),
                        reason=f"two_hop_bridge_via_mid_node::{scope_info_1.scope_source}+{scope_info_2.scope_source}",
                        depth_hops=2,
                        query_direction=f"{direction1}->{direction2}",
                    )
                    record_candidate(
                        state=state,
                        paths=paths,
                        component_state=component_state,
                        candidate=candidate,
                        collect_noncore=collect_noncore,
                    )
                    if not candidate.accepted_into_core:
                        continue

                    scored = score_balance_aware_core_candidate(
                        candidate=candidate,
                        policy=balance_policy,
                        current_relation_counts=current_relation_counts,
                        current_pattern_counts=current_pattern_counts,
                    )
                    if scored is None:
                        state["counters"]["candidate_outcomes"]["rejected_balance_policy"] += 1
                        emit_event(
                            paths,
                            "candidate_balance_rejected",
                            **candidate_to_event_payload(candidate),
                            final_outcome="rejected_balance_policy",
                        )
                        continue

                    score, reasons = scored
                    candidate.selection_score = score
                    candidate.selection_reasons = reasons
                    emit_event(
                        paths,
                        "candidate_scored_for_core",
                        **candidate_to_event_payload(candidate),
                    )
                    if best_score is None or score > best_score:
                        best_candidate = candidate
                        best_score = score

    if best_candidate is not None:
        emit_event(paths, "core_bridge_selected", **candidate_to_event_payload(best_candidate))
    return best_candidate


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Repair weakly disconnected KG components using Wikidata bridges with "
            "append-safe events, atomic checkpoints, and resumable state."
        )
    )
    p.add_argument("--input_triples", type=Path, required=True, help="Input triples JSON/JSONL.")
    scope_group = p.add_mutually_exclusive_group(required=True)
    scope_group.add_argument("--relation_scope_manifest", type=Path, help="Run-phase allocation manifest JSON.")
    scope_group.add_argument("--allowed_relations", type=Path, help="Backward-compatible flat relation universe.")

    p.add_argument("--output_dir", type=Path, required=True, help="Run directory for manifest/state/events/report/graph output.")
    p.add_argument("--resume", action="store_true", help="Resume from existing output_dir state.")
    p.add_argument("--dry_run", action="store_true", help="Query/classify/log as usual but do not apply repair_core triples.")
    p.add_argument(
        "--collect_noncore",
        action="store_true",
        help=(
            "Compatibility flag. Non-core candidates are always written to events.jsonl; "
            "this also stores a bounded non-core sample in state.json."
        ),
    )

    p.add_argument("--max_components", type=int, default=20, help="Maximum number of non-LCC components to process.")
    p.add_argument("--anchor_nodes_per_component", type=int, default=5, help="Top-degree anchors per component.")
    p.add_argument("--query_limit", type=int, default=200, help="WDQS row limit per one-hop query.")
    p.add_argument("--timeout_sec", type=int, default=60, help="WDQS request timeout in seconds.")
    p.add_argument("--wikidata_sleep_sec", type=float, default=0.2, help="Delay between anchor stages.")
    p.add_argument("--user_agent", type=str, default=DEFAULT_USER_AGENT, help="HTTP User-Agent for WDQS.")
    p.add_argument(
        "--disable_balance_aware_core_selection",
        action="store_true",
        help="Accept the first repair_core candidate instead of ranking core bridges against current balance targets.",
    )
    p.add_argument(
        "--protected_pattern",
        action="append",
        default=None,
        help="Pattern name to favor when multiple core bridge candidates are eligible; repeatable. Defaults to symmetric.",
    )
    p.add_argument("--head_field", type=str, default="h")
    p.add_argument("--rel_field", type=str, default="r")
    p.add_argument("--tail_field", type=str, default="t")
    return p.parse_args(argv)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    paths = make_run_paths(args.output_dir)

    triples = load_triples(
        path=args.input_triples,
        head_field=args.head_field,
        rel_field=args.rel_field,
        tail_field=args.tail_field,
    )

    if args.relation_scope_manifest is not None:
        relation_scope = load_relation_scope_manifest(path=args.relation_scope_manifest)
        relation_scope_source = f"relation_scope_manifest:{args.relation_scope_manifest.resolve()}"
        balance_policy = None
        if not args.disable_balance_aware_core_selection:
            balance_policy = load_balance_selection_policy(
                path=args.relation_scope_manifest,
                protected_patterns=args.protected_pattern or ["symmetric"],
            )
    else:
        relation_scope = load_allowed_relations(path=args.allowed_relations, rel_field=args.rel_field)
        relation_scope_source = f"allowed_relations:{args.allowed_relations.resolve()}"
        balance_policy = None

    original_edge_counts = aggregate_triples(triples)
    original_graph = build_digraph(original_edge_counts)
    original_components = stable_components(original_graph)
    if not original_components:
        raise ValueError("Input graph is empty after loading.")

    original_stats = {
        "input_triples": len(triples),
        "unique_triples": len(original_edge_counts),
        "nodes": original_graph.number_of_nodes(),
        "weak_components": len(original_components),
        "top_component_sizes": component_sizes(original_graph)[:10],
        "largest_component_size": len(original_components[0]),
    }

    manifest, state = load_or_init_run(
        args=args,
        paths=paths,
        relation_scope_source=relation_scope_source,
        original_stats=original_stats,
    )
    _ = manifest  # Manifest is intentionally loaded for validation and provenance.

    counters = state["counters"]
    applied_core_set: Set[Triple] = {deserialize_triple(x) for x in state["added_core_triples"]}

    edge_counts = aggregate_triples(triples)
    for triple in applied_core_set:
        if triple not in edge_counts:
            edge_counts[triple] = 1

    initialize_or_recover_graph_output(
        paths=paths,
        original_triples=triples,
        added_core_triples=applied_core_set,
        resume=args.resume,
    )
    write_report_snapshot(paths=paths, state=state, edge_counts=edge_counts)

    g = build_digraph(edge_counts)
    comps_now = stable_components(g)
    main_nodes = set(comps_now[0]) if comps_now else set()

    candidates_to_process = list(enumerate(original_components[1 : 1 + args.max_components], start=2))

    interrupted = False
    run_error: Optional[str] = None

    try:
        for component_rank, comp_nodes in candidates_to_process:
            comp_key = str(component_rank)
            existing_comp = state["components"].get(comp_key)
            if existing_comp is not None and existing_comp.get("status") == "finished":
                counters["candidate_outcomes"]["skipped_due_to_resume"] += 1
                emit_event(
                    paths,
                    "skipped_due_to_resume",
                    scope="component",
                    component_rank=component_rank,
                    reason="component_already_finished",
                )
                continue

            # Anchor selection is persisted per component so resume does not reorder work.
            anchors = existing_comp["anchors"] if existing_comp and existing_comp.get("anchors") else pick_component_anchors(
                g, comp_nodes, top_k=args.anchor_nodes_per_component
            )
            component_state = ensure_component_state(state, component_rank=component_rank, anchors=anchors)

            if not component_state.get("examined_counted"):
                counters["components_examined"] += 1
                component_state["examined_counted"] = True

            component_state["status"] = "in_progress"
            state["current_component_rank"] = component_rank
            state["current_anchor_node"] = None
            state["current_stage"] = None

            if balance_policy is not None:
                current_relation_counts, current_pattern_counts = compute_balance_observed_counts(
                    edge_counts=edge_counts,
                    policy=balance_policy,
                )
            else:
                current_relation_counts, current_pattern_counts = {}, {}

            emit_event(
                paths,
                "component_started",
                component_rank=component_rank,
                component_size=len(comp_nodes),
                anchor_count=len(component_state["anchors"]),
            )
            log(f"Component {component_rank}: start (size={len(comp_nodes)}, anchors={len(component_state['anchors'])})")
            checkpoint_state(paths, state, reason="component_started", component_rank=component_rank)

            selected_bridge: Optional[BridgeCandidate] = None
            for anchor_idx, anchor in enumerate(component_state["anchors"], start=1):
                state["current_anchor_node"] = anchor
                anchor_state = ensure_anchor_state(component_state, anchor)

                emit_event(
                    paths,
                    "anchor_selected",
                    component_rank=component_rank,
                    anchor_node=anchor,
                    anchor_index=anchor_idx,
                    anchor_total=len(component_state["anchors"]),
                )
                log(f"Component {component_rank}: anchor {anchor_idx}/{len(component_state['anchors'])} -> {anchor}")

                if anchor_state["completed"]:
                    counters["candidate_outcomes"]["skipped_due_to_resume"] += 1
                    emit_event(
                        paths,
                        "skipped_due_to_resume",
                        scope="anchor",
                        component_rank=component_rank,
                        anchor_node=anchor,
                        reason="anchor_already_completed",
                    )
                    continue

                counters["bridge_candidates_examined"] += 1

                if not anchor_state["one_hop_done"]:
                    state["current_stage"] = "one_hop"
                    one_hop = find_one_hop_bridge(
                        state=state,
                        paths=paths,
                        component_state=component_state,
                        component_rank=component_rank,
                        anchor=anchor,
                        main_nodes=main_nodes,
                        relation_scope=relation_scope,
                        balance_policy=balance_policy,
                        current_relation_counts=current_relation_counts,
                        current_pattern_counts=current_pattern_counts,
                        user_agent=args.user_agent,
                        timeout_sec=args.timeout_sec,
                        query_limit=args.query_limit,
                        collect_noncore=args.collect_noncore,
                    )
                    anchor_state["one_hop_done"] = True
                    checkpoint_state(paths, state, reason="anchor_one_hop_done", component_rank=component_rank, anchor_node=anchor)
                    if one_hop is not None:
                        if is_better_core_candidate(one_hop, selected_bridge):
                            selected_bridge = one_hop
                        anchor_state["selected_core"] = True
                        anchor_state["completed"] = True
                        if anchor not in component_state["processed_anchors"]:
                            component_state["processed_anchors"].append(anchor)
                        checkpoint_state(paths, state, reason="anchor_completed", component_rank=component_rank, anchor_node=anchor)
                        continue
                else:
                    counters["candidate_outcomes"]["skipped_due_to_resume"] += 1
                    emit_event(
                        paths,
                        "skipped_due_to_resume",
                        scope="anchor_stage",
                        component_rank=component_rank,
                        anchor_node=anchor,
                        stage="one_hop",
                    )

                time.sleep(args.wikidata_sleep_sec)

                if not anchor_state["two_hop_done"]:
                    state["current_stage"] = "two_hop"
                    two_hop = find_two_hop_bridge(
                        state=state,
                        paths=paths,
                        component_state=component_state,
                        component_rank=component_rank,
                        anchor=anchor,
                        main_nodes=main_nodes,
                        relation_scope=relation_scope,
                        balance_policy=balance_policy,
                        current_relation_counts=current_relation_counts,
                        current_pattern_counts=current_pattern_counts,
                        user_agent=args.user_agent,
                        timeout_sec=args.timeout_sec,
                        query_limit=args.query_limit,
                        collect_noncore=args.collect_noncore,
                    )
                    anchor_state["two_hop_done"] = True
                    checkpoint_state(paths, state, reason="anchor_two_hop_done", component_rank=component_rank, anchor_node=anchor)
                    if two_hop is not None:
                        if is_better_core_candidate(two_hop, selected_bridge):
                            selected_bridge = two_hop
                        anchor_state["selected_core"] = True
                        anchor_state["completed"] = True
                        if anchor not in component_state["processed_anchors"]:
                            component_state["processed_anchors"].append(anchor)
                        checkpoint_state(paths, state, reason="anchor_completed", component_rank=component_rank, anchor_node=anchor)
                        continue
                else:
                    counters["candidate_outcomes"]["skipped_due_to_resume"] += 1
                    emit_event(
                        paths,
                        "skipped_due_to_resume",
                        scope="anchor_stage",
                        component_rank=component_rank,
                        anchor_node=anchor,
                        stage="two_hop",
                    )

                anchor_state["completed"] = True
                if anchor not in component_state["processed_anchors"]:
                    component_state["processed_anchors"].append(anchor)

                checkpoint_state(paths, state, reason="anchor_completed", component_rank=component_rank, anchor_node=anchor)
                time.sleep(args.wikidata_sleep_sec)

            applied_this_component = False
            if selected_bridge is not None:
                component_state["selected_core_candidate"] = candidate_to_event_payload(selected_bridge)
                if args.dry_run:
                    counters["candidate_outcomes"]["dry_run_not_applied"] += 1
                    emit_event(
                        paths,
                        "core_bridge_added",
                        **candidate_to_event_payload(selected_bridge),
                        dry_run=True,
                        final_outcome="dry_run_not_applied",
                        added_triples=[],
                        added_count=0,
                    )
                    log(f"Component {component_rank}: core bridge found but not applied due to --dry_run")
                else:
                    added = add_bridge_to_counts(edge_counts=edge_counts, candidate=selected_bridge)
                    if added:
                        counters["candidate_outcomes"]["applied_core"] += 1
                        counters["core_bridges_added"] += len(added)
                        counters["components_repaired"] += 1
                        if component_rank not in state["repaired_component_ranks"]:
                            state["repaired_component_ranks"].append(component_rank)
                        for triple in added:
                            if triple not in applied_core_set:
                                state["added_core_triples"].append(serialize_triple(triple))
                                applied_core_set.add(triple)
                        emit_event(
                            paths,
                            "core_bridge_added",
                            **candidate_to_event_payload(selected_bridge),
                            dry_run=False,
                            final_outcome="applied_core",
                            added_triples=[serialize_triple(t) for t in added],
                            added_count=len(added),
                        )
                        for triple in sorted(added):
                            append_jsonl(paths.graph_output, triple_to_row(triple, source="repair_core"))
                        log(f"Component {component_rank}: applied {len(added)} core bridge triple(s)")
                        g = build_digraph(edge_counts)
                        comps_now = stable_components(g)
                        main_nodes = set(comps_now[0]) if comps_now else set()
                        applied_this_component = True
                    else:
                        counters["candidate_outcomes"]["duplicate_core_candidate"] += 1
                        emit_event(
                            paths,
                            "core_bridge_added",
                            **candidate_to_event_payload(selected_bridge),
                            dry_run=False,
                            final_outcome="duplicate_core_candidate",
                            added_triples=[],
                            added_count=0,
                        )
                        log(f"Component {component_rank}: selected core bridge was duplicate (no new triples)")
            else:
                log(f"Component {component_rank}: no core bridge selected")

            outcome = finalize_component_outcome(state, component_state)
            component_state["status"] = "finished"
            component_state["applied_core"] = applied_this_component
            if component_rank not in state["processed_component_ranks"]:
                state["processed_component_ranks"].append(component_rank)
            if not applied_this_component:
                counters["skipped_components"] += 1

            emit_event(
                paths,
                "component_finished",
                component_rank=component_rank,
                outcome=outcome,
                applied_core=applied_this_component,
                processed_anchors=list(component_state["processed_anchors"]),
                found_labels=dict(component_state["found_labels"]),
                counts_snapshot=counter_snapshot(state),
            )
            log(
                f"Component {component_rank}: finished outcome={outcome}, "
                f"applied_core={applied_this_component}"
            )
            state["current_anchor_node"] = None
            state["current_stage"] = None
            checkpoint_state(paths, state, reason="component_finished", component_rank=component_rank)
            write_report_snapshot(paths=paths, state=state, edge_counts=edge_counts)

        state["completed"] = True
        state["successful"] = True
        state["interrupted"] = False
        state["run_finished_at"] = utc_now_iso()
        state["current_component_rank"] = None
        state["current_anchor_node"] = None
        state["current_stage"] = None
        emit_event(paths, "run_finished", completed=True, successful=True, counts_snapshot=counter_snapshot(state))
        checkpoint_state(paths, state, reason="run_finished")
        write_report_snapshot(paths=paths, state=state, edge_counts=edge_counts)

    except KeyboardInterrupt:
        interrupted = True
        run_error = "keyboard_interrupt"
    except Exception as exc:
        interrupted = True
        run_error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()

    if interrupted:
        state["completed"] = False
        state["successful"] = False
        state["interrupted"] = True
        state["last_error"] = run_error
        state["run_finished_at"] = utc_now_iso()
        state["notes"].append("Run interrupted before completion.")
        emit_event(
            paths,
            "run_interrupted",
            reason=run_error,
            current_component_rank=state.get("current_component_rank"),
            current_anchor_node=state.get("current_anchor_node"),
            current_stage=state.get("current_stage"),
            counts_snapshot=counter_snapshot(state),
        )
        checkpoint_state(paths, state, reason="run_interrupted", component_rank=state.get("current_component_rank"))
        write_report_snapshot(paths=paths, state=state, edge_counts=edge_counts)
        log("Run interrupted. Progress checkpointed. Re-run with --resume to continue.")

    # Keep an end-of-run snapshot for safety, while preserving incremental updates.
    write_report_snapshot(paths=paths, state=state, edge_counts=edge_counts)

    if interrupted:
        return 130 if run_error == "keyboard_interrupt" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
