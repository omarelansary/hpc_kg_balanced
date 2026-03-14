#!/usr/bin/env python3
"""Construct a connected triple graph from allocation outputs.

This script realizes relation-level quotas (eta_integer) into entity-level
triples while enforcing connectivity during construction.

Input:
- Allocation CSV exported from the dashboard (must include: pattern, relation, eta_integer)
  OR allocation JSON exported from the dashboard (must include "allocations" list).
- Triple source from either:
  - MongoDB collection, or
  - local triples JSONL via ``--triples_jsonl`` (no Mongo required).

Connectivity invariant:
- Every added triple (h, r, t) after seeding must satisfy: h in V OR t in V,
  where V is the current set of sampled entities.

Notes:
- Quotas are relation-level. If the same relation appears in multiple patterns,
  quotas are summed before realization.
- Strict mode (default) requires filling exact quotas; otherwise the script fails.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
except ModuleNotFoundError:  # optional in local-file mode
    MongoClient = None
    Collection = object

try:
    from src.kg_building.config_sampler import MongoConfig
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    from src.kg_building.config_sampler import MongoConfig


logger = logging.getLogger("allocation_connected_graph")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@dataclass
class RealizationConfig:
    """Configuration controlling quota realization and connectivity search.

    Attributes
    ----------
    attempts:
        Number of randomized restarts. More attempts increase the chance of
        finding an exact connected realization under hard quotas.
    rcl_size:
        Restricted Candidate List size for randomized greedy selection. Larger
        values increase exploration; smaller values make selection greedier.
    anchor_fraction:
        Fraction of a relation's quota to prioritize as anchored/attaching
        triples early in per-relation sampling.
    overlap_probe_triples:
        Number of probe samples used to estimate relation-to-component overlap.
    mongo_batch_limit:
        Safety cap for batch retrieval in Mongo-backed sampling.
    allow_sampling_fallback:
        If True, Mongo mode uses `$sample` pipelines for random-ish selection.
    strict_quotas:
        If True, fail when exact per-relation quotas cannot be satisfied.
        If False, return best connected partial result found.
    """
    attempts: int = 10
    rcl_size: int = 10
    anchor_fraction: float = 0.2
    overlap_probe_triples: int = 200
    mongo_batch_limit: int = 5000
    allow_sampling_fallback: bool = True
    strict_quotas: bool = True


def resolve_input_path(path: str) -> str:
    """Return a usable filesystem path without changing path semantics.

    Parameters
    ----------
    path:
        Input path, absolute or relative.

    Returns
    -------
    str
        The same path if absolute or existing; otherwise unchanged relative
        path (caller decides final interpretation).
    """
    if not path:
        return path
    if os.path.isabs(path) or os.path.exists(path):
        return path
    return path


def load_allocations_csv(path: str) -> List[Dict]:
    """Load allocation rows from a dashboard CSV export.

    Expected columns include at least:
    - `relation`
    - `eta_integer`
    - optional `pattern`

    Parameters
    ----------
    path:
        CSV path.

    Returns
    -------
    List[Dict]
        Normalized rows of shape
        `{"pattern": str, "relation": str, "eta_integer": int}`.
        Invalid numeric values for `eta_integer` are coerced to 0.
    """
    out: List[Dict] = []
    path = resolve_input_path(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            rel = (row.get("relation") or "").strip()
            pat = (row.get("pattern") or "").strip()
            try:
                eta_i = int(float(row.get("eta_integer", "0")))
            except (TypeError, ValueError):
                eta_i = 0
            if rel:
                out.append({"pattern": pat, "relation": rel, "eta_integer": eta_i})
    return out


def load_allocations_json(path: str) -> List[Dict]:
    """Load allocation rows from dashboard JSON export.

    Expected JSON structure includes top-level key:
    - `allocations`: list of row dicts with `relation`, `eta_integer`,
      and optional `pattern`.

    Parameters
    ----------
    path:
        JSON path.

    Returns
    -------
    List[Dict]
        Normalized rows of shape
        `{"pattern": str, "relation": str, "eta_integer": int}`.
    """
    path = resolve_input_path(path)
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    allocs = doc.get("allocations", [])
    out: List[Dict] = []
    if isinstance(allocs, list):
        for row in allocs:
            if not isinstance(row, dict):
                continue
            rel = str(row.get("relation", "")).strip()
            pat = str(row.get("pattern", "")).strip()
            try:
                eta_i = int(row.get("eta_integer", 0))
            except (TypeError, ValueError):
                eta_i = 0
            if rel:
                out.append({"pattern": pat, "relation": rel, "eta_integer": eta_i})
    return out


def build_relation_quotas(rows: Iterable[Dict]) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]]]:
    """Aggregate row-level allocations into relation quotas.

    If a relation appears multiple times (including across patterns), quotas are
    summed. Non-positive entries are ignored.

    Parameters
    ----------
    rows:
        Iterable of normalized allocation-like rows.

    Returns
    -------
    Tuple[Dict[str, int], Dict[str, Dict[str, int]]]
        - relation_quotas: `{relation -> total_quota}`
        - pattern_relation_quotas: `{pattern -> {relation -> quota_within_pattern}}`
    """
    quotas: Dict[str, int] = defaultdict(int)
    by_pattern: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        rel = str(row.get("relation", "")).strip()
        pat = str(row.get("pattern", "")).strip() or "UNKNOWN"
        try:
            eta_i = int(row.get("eta_integer", 0))
        except (TypeError, ValueError):
            eta_i = 0
        if not rel or eta_i <= 0:
            continue
        quotas[rel] += eta_i
        by_pattern[pat][rel] += eta_i
    return dict(quotas), {p: dict(v) for p, v in by_pattern.items()}


def endpoints(triple: Dict, mcfg: MongoConfig) -> Tuple[str, str]:
    """Extract `(head, tail)` IDs from a triple record using configured field names."""
    return str(triple.get(mcfg.field_head)), str(triple.get(mcfg.field_tail))


class TripleSource:
    """MongoDB-backed triple retrieval adapter.

    The interface mirrors the local-file source so realization logic is shared
    across data backends.
    """

    def __init__(self, coll: Collection, mcfg: MongoConfig, rcfg: RealizationConfig):
        """Initialize Mongo-backed source.

        Parameters
        ----------
        coll:
            Mongo collection storing triples.
        mcfg:
            Field-name and DB config.
        rcfg:
            Realization/search configuration.
        """
        self.coll = coll
        self.mcfg = mcfg
        self.rcfg = rcfg

    def count_triples(self, pid: str) -> int:
        """Return number of triples for relation `pid`."""
        return self.coll.count_documents({self.mcfg.field_rel: pid})

    def sample_triples_any(self, pid: str, n: int) -> List[Dict]:
        """Sample up to `n` triples for relation `pid` without connectivity constraint."""
        if n <= 0:
            return []
        if self.rcfg.allow_sampling_fallback:
            pipeline = [
                {"$match": {self.mcfg.field_rel: pid}},
                {"$sample": {"size": min(n, self.rcfg.mongo_batch_limit)}},
                {"$project": {self.mcfg.field_head: 1, self.mcfg.field_rel: 1, self.mcfg.field_tail: 1}},
            ]
            return list(self.coll.aggregate(pipeline))
        cur = self.coll.find(
            {self.mcfg.field_rel: pid},
            {self.mcfg.field_head: 1, self.mcfg.field_rel: 1, self.mcfg.field_tail: 1},
        ).limit(min(n, self.rcfg.mongo_batch_limit))
        return list(cur)

    def sample_triples_attach_to_v(self, pid: str, v: Set[str], n: int) -> List[Dict]:
        """Sample up to `n` triples for `pid` that touch entity set `v`.

        A triple is eligible if `head in v` OR `tail in v`.
        """
        if n <= 0 or not v:
            return []
        v_list = list(v)
        q = {
            self.mcfg.field_rel: pid,
            "$or": [
                {self.mcfg.field_head: {"$in": v_list}},
                {self.mcfg.field_tail: {"$in": v_list}},
            ],
        }
        if self.rcfg.allow_sampling_fallback:
            pipeline = [
                {"$match": q},
                {"$sample": {"size": min(n, self.rcfg.mongo_batch_limit)}},
                {"$project": {self.mcfg.field_head: 1, self.mcfg.field_rel: 1, self.mcfg.field_tail: 1}},
            ]
            return list(self.coll.aggregate(pipeline))
        cur = self.coll.find(
            q,
            {self.mcfg.field_head: 1, self.mcfg.field_rel: 1, self.mcfg.field_tail: 1},
        ).limit(min(n, self.rcfg.mongo_batch_limit))
        return list(cur)


class LocalTripleSource:
    """Triple source backed by an in-memory JSONL index."""

    def __init__(
        self,
        triples_by_rel: Dict[str, List[Dict]],
        mcfg: MongoConfig,
    ):
        """Initialize local indexed source.

        Parameters
        ----------
        triples_by_rel:
            Mapping `{relation -> list[triple_dict]}`.
        mcfg:
            Field-name configuration used by realization logic.
        """
        self.triples_by_rel = triples_by_rel
        self.mcfg = mcfg

    def count_triples(self, pid: str) -> int:
        """Return number of locally indexed triples for relation `pid`."""
        return len(self.triples_by_rel.get(pid, []))

    def sample_triples_any(self, pid: str, n: int) -> List[Dict]:
        """Uniformly sample up to `n` triples for relation `pid` from local pool."""
        if n <= 0:
            return []
        pool = self.triples_by_rel.get(pid, [])
        if not pool:
            return []
        k = min(n, len(pool))
        return random.sample(pool, k)

    def sample_triples_attach_to_v(self, pid: str, v: Set[str], n: int) -> List[Dict]:
        """Uniformly sample attached triples for relation `pid` from local pool.

        A triple is eligible if `head in v` OR `tail in v`.
        """
        if n <= 0 or not v:
            return []
        pool = self.triples_by_rel.get(pid, [])
        if not pool:
            return []
        attached = []
        for tr in pool:
            h = str(tr.get(self.mcfg.field_head))
            t = str(tr.get(self.mcfg.field_tail))
            if (h in v) or (t in v):
                attached.append(tr)
        if not attached:
            return []
        k = min(n, len(attached))
        return random.sample(attached, k)


def load_triples_jsonl_index(
    path: str,
    mcfg: MongoConfig,
) -> Dict[str, List[Dict]]:
    """Load triples JSONL and index by relation.

    Input format:
    - One JSON object per line.
    - Must contain configured `head`, `relation`, and `tail` fields.

    Malformed lines are skipped with warning counters.

    Parameters
    ----------
    path:
        JSONL path.
    mcfg:
        Field-name configuration.

    Returns
    -------
    Dict[str, List[Dict]]
        Indexed triple map `{relation -> triples}`.
    """
    out: Dict[str, List[Dict]] = defaultdict(list)
    path = resolve_input_path(path)
    bad = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                tr = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if not isinstance(tr, dict):
                bad += 1
                continue
            h = tr.get(mcfg.field_head)
            r = tr.get(mcfg.field_rel)
            t = tr.get(mcfg.field_tail)
            if h is None or r is None or t is None:
                bad += 1
                continue
            rec = {
                mcfg.field_head: str(h),
                mcfg.field_rel: str(r),
                mcfg.field_tail: str(t),
            }
            out[rec[mcfg.field_rel]].append(rec)
    if bad > 0:
        logger.warning("Skipped %d malformed triples while reading %s", bad, path)
    logger.info("Loaded %d relations from triples JSONL: %s", len(out), path)
    return dict(out)


def compute_overlap_score(ts: TripleSource, pid: str, v: Set[str], probe_n: int, mcfg: MongoConfig) -> float:
    """Estimate how easily a relation can attach to current component.

    The score is the empirical fraction of sampled relation triples whose head
    or tail is already in entity set `v`.
    """
    if not v:
        return 0.0
    probes = ts.sample_triples_any(pid, probe_n)
    if not probes:
        return 0.0
    hit = 0
    for tr in probes:
        h, t = endpoints(tr, mcfg)
        if (h in v) or (t in v):
            hit += 1
    return hit / max(1, len(probes))


def estimate_attach_capacity(
    ts,
    pid: str,
    v: Set[str],
    probe_n: int,
    *,
    relation_type_constraints: Optional[Dict[str, List[str]]] = None,
    use_controlled_relaxation: bool = False,
    probe_rounds: int = 1,
) -> Tuple[int, str]:
    """Estimate immediate attachable capacity for relation `pid` under current V.

    Returns
    -------
    Tuple[int, str]
        `(capacity, stage_name)` where `capacity` is candidate count in a
        probe batch and `stage_name` is the stage that achieved that estimate.
    """
    if probe_n <= 0 or not v:
        return 0, "none"
    subj_types = (relation_type_constraints or {}).get("subject", []) if relation_type_constraints else []
    obj_types = (relation_type_constraints or {}).get("object", []) if relation_type_constraints else []
    typed_supported = hasattr(ts, "sample_triples_attach_to_v_typed")
    if use_controlled_relaxation and typed_supported and (subj_types or obj_types):
        stages = [
            ("strict_both", True, True),
            ("subject_only", True, False),
            ("object_only", False, True),
            ("untyped", False, False),
        ]
    else:
        stages = [("untyped", False, False)]

    best_cap = 0
    best_stage = "none"
    for stage_name, use_subj, use_obj in stages:
        for _ in range(max(1, int(probe_rounds))):
            if stage_name == "untyped":
                cands = ts.sample_triples_attach_to_v(pid, v, probe_n)
            else:
                cands = ts.sample_triples_attach_to_v_typed(
                    pid=pid,
                    v=v,
                    n=probe_n,
                    subject_types=subj_types if use_subj else [],
                    object_types=obj_types if use_obj else [],
                )
            cap = len(cands)
            if cap > best_cap:
                best_cap = cap
                best_stage = stage_name
            if cap > 0:
                return cap, stage_name
    return best_cap, best_stage


def rcl_pick(items: List[Tuple[str, float]], rcl_size: int) -> Optional[str]:
    """Pick one item via GRASP-style restricted candidate list.

    Items are sorted by score descending; one item is chosen uniformly from the
    top-`rcl_size` prefix.
    """
    if not items:
        return None
    items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
    rcl = items_sorted[: max(1, min(rcl_size, len(items_sorted)))]
    return random.choice(rcl)[0]


def chunk_backoff_schedule(target_n: int) -> List[int]:
    """Return a descending chunk schedule that backs off toward 1.

    Example: 10 -> [10, 5, 3, 2, 1]
    """
    if target_n <= 0:
        return []
    schedule: List[int] = []
    current = int(target_n)
    while current > 1:
        schedule.append(current)
        next_current = max(1, (current + 1) // 2)
        if next_current == current:
            break
        current = next_current
    if not schedule or schedule[-1] != 1:
        schedule.append(1)
    return schedule


def sample_n_triples_for_relation_connected(
    ts: TripleSource,
    pid: str,
    n: int,
    v: Set[str],
    mcfg: MongoConfig,
    anchor_n: int,
    used_keys: Optional[Set[Tuple[str, str, str]]] = None,
    relation_type_constraints: Optional[Dict[str, List[str]]] = None,
    use_controlled_relaxation: bool = False,
    stage_cb: Optional[Callable[[str, Dict], None]] = None,
) -> Optional[List[Dict]]:
    """Sample exactly `n` triples for one relation while preserving connectivity.

    Connectivity invariant during growth:
    - For every added triple `(h, pid, t)` after seeding, `h in V OR t in V`.

    Parameters
    ----------
    ts:
        Triple source backend (Mongo or local).
    pid:
        Relation to sample.
    n:
        Exact target count for this relation.
    v:
        Mutable entity set for the global connected component.
    mcfg:
        Field-name configuration.
    anchor_n:
        Number of early attached triples to prioritize.
    used_keys:
        Optional dedup set of `(h, pid, t)` already used for this relation.

    Returns
    -------
    Optional[List[Dict]]
        Exactly `n` sampled triples on success; `None` if impossible under the
        current component/constraints.
    """
    if n <= 0:
        return []
    chosen: List[Dict] = []
    v_working = set(v)
    local_used = set(used_keys or set())
    new_keys: Set[Tuple[str, str, str]] = set()

    def add_tr(tr: Dict) -> bool:
        h, t = endpoints(tr, mcfg)
        key = (h, pid, t)
        if key in local_used:
            return False
        chosen.append({mcfg.field_head: h, mcfg.field_rel: pid, mcfg.field_tail: t})
        local_used.add(key)
        new_keys.add(key)
        v_working.add(h)
        v_working.add(t)
        return True

    if not v_working:
        seeds = ts.sample_triples_any(pid, 1)
        if not seeds:
            return None
        add_tr(seeds[0])

    subj_types = (relation_type_constraints or {}).get("subject", []) if relation_type_constraints else []
    obj_types = (relation_type_constraints or {}).get("object", []) if relation_type_constraints else []

    typed_supported = hasattr(ts, "sample_triples_attach_to_v_typed")
    if use_controlled_relaxation and typed_supported and (subj_types or obj_types):
        stages = [
            ("strict_both", True, True),
            ("subject_only", True, False),
            ("object_only", False, True),
            ("untyped", False, False),
        ]
    else:
        stages = [("untyped", False, False)]

    for stage_name, use_subj, use_obj in stages:
        if stage_cb is not None:
            stage_cb(
                "stage_start",
                {
                    "relation": pid,
                    "stage": stage_name,
                    "n_target": n,
                    "n_already": len(chosen),
                },
            )

        needed_anchor = min(anchor_n, n)
        if needed_anchor > 0 and len(chosen) < needed_anchor:
            need_k = max((needed_anchor - len(chosen)) * 3, needed_anchor - len(chosen))
            if stage_name == "untyped":
                anchored = ts.sample_triples_attach_to_v(pid, v_working, need_k)
            else:
                anchored = ts.sample_triples_attach_to_v_typed(
                    pid=pid,
                    v=v_working,
                    n=need_k,
                    subject_types=subj_types if use_subj else [],
                    object_types=obj_types if use_obj else [],
                )
            anchored.sort(
                key=lambda tr: (endpoints(tr, mcfg)[0] not in v_working) or (endpoints(tr, mcfg)[1] not in v_working),
                reverse=True,
            )
            for tr in anchored:
                if len(chosen) >= needed_anchor:
                    break
                h, t = endpoints(tr, mcfg)
                if (h in v_working) or (t in v_working):
                    add_tr(tr)

        while len(chosen) < n:
            remaining = n - len(chosen)
            fetch_n = max(remaining * 3, 50)
            if stage_name == "untyped":
                candidates = ts.sample_triples_attach_to_v(pid, v_working, fetch_n)
            else:
                candidates = ts.sample_triples_attach_to_v_typed(
                    pid=pid,
                    v=v_working,
                    n=fetch_n,
                    subject_types=subj_types if use_subj else [],
                    object_types=obj_types if use_obj else [],
                )
            if not candidates:
                break
            candidates.sort(
                key=lambda tr: (endpoints(tr, mcfg)[0] not in v_working) or (endpoints(tr, mcfg)[1] not in v_working),
                reverse=True,
            )
            progress = 0
            for tr in candidates:
                if len(chosen) >= n:
                    break
                h, t = endpoints(tr, mcfg)
                if (h in v_working) or (t in v_working):
                    if add_tr(tr):
                        progress += 1
            if progress == 0:
                break
        if len(chosen) >= n:
            if used_keys is not None:
                used_keys.update(new_keys)
            v.update(v_working)
            if stage_cb is not None:
                stage_cb(
                    "stage_success",
                    {
                        "relation": pid,
                        "stage": stage_name,
                        "n_final": len(chosen),
                    },
                )
            return chosen

    return None


def is_connected_undirected(triples: List[Dict], mcfg: MongoConfig) -> bool:
    """Check graph connectivity on undirected entity projection.

    Builds an undirected graph on entities where each triple contributes edge
    `(h, t)` and runs DFS/BFS reachability from an arbitrary seed.
    """
    if not triples:
        return False
    adj: Dict[str, Set[str]] = defaultdict(set)
    nodes: Set[str] = set()
    for tr in triples:
        h = str(tr.get(mcfg.field_head))
        t = str(tr.get(mcfg.field_tail))
        nodes.add(h)
        nodes.add(t)
        adj[h].add(t)
        adj[t].add(h)
    start = next(iter(nodes))
    seen = {start}
    stack = [start]
    while stack:
        x = stack.pop()
        for y in adj.get(x, []):
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return len(seen) == len(nodes)


def _dump_checkpoint(path: str, payload: Dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=os.path.dirname(path) or ".") as tf:
        json.dump(payload, tf, ensure_ascii=False)
        tmp = tf.name
    os.replace(tmp, path)


def _load_checkpoint(path: str) -> Optional[Dict]:
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _append_jsonl(path: str, payload: Dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_jsonl_records(path: str, rows: Iterable[Dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=os.path.dirname(path) or ".") as tf:
        for row in rows:
            tf.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp = tf.name
    os.replace(tmp, path)


def build_relation_progress_rows(
    quotas: Dict[str, int],
    feasible: Dict[str, int],
    achieved_counts: Dict[str, int],
    remaining: Dict[str, int],
    fail_counts: Dict[str, int],
    deferral_counts: Dict[str, int],
    skipped_relations: Dict[str, str],
) -> List[Dict]:
    rows: List[Dict] = []
    for relation, expected in quotas.items():
        expected_i = int(expected)
        feasible_i = relation in feasible
        achieved_i = int(achieved_counts.get(relation, 0))
        remaining_i = max(0, int(remaining.get(relation, expected_i if feasible_i else expected_i)))
        skip_reason = str(skipped_relations.get(relation, "") or "")
        if not feasible_i:
            status = "unavailable"
        elif skip_reason:
            status = "skipped"
        elif achieved_i <= 0:
            status = "not_started"
        elif achieved_i >= expected_i:
            status = "completed"
        else:
            status = "in_progress"
        rows.append(
            {
                "relation": relation,
                "expected_triples": expected_i,
                "achieved_triples": achieved_i,
                "remaining_triples": remaining_i,
                "appeared_in_graph": bool(achieved_i > 0),
                "status": status,
                "is_feasible": bool(feasible_i),
                "progress_ratio": (float(achieved_i) / float(expected_i)) if expected_i > 0 else 0.0,
                "fail_count": int(fail_counts.get(relation, 0)),
                "deferral_count": int(deferral_counts.get(relation, 0)),
                "skip_reason": skip_reason,
            }
        )
    return rows


def realize_connected_graph(
    quotas: Dict[str, int],
    ts,
    mcfg: MongoConfig,
    rcfg: RealizationConfig,
    progress_cb: Optional[Callable[[str, Dict], None]] = None,
    initial_entities: Optional[Iterable[str]] = None,
    relation_type_constraints: Optional[Dict[str, Dict[str, List[str]]]] = None,
    use_controlled_relaxation: bool = False,
    checkpoint_path: Optional[str] = None,
    resume_from_checkpoint: bool = False,
    checkpoint_every_relations: int = 1,
    micro_fill_chunk_size: int = 20,
    stall_max_rounds: int = 25,
    max_fail_per_relation: int = 3,
    seed_min_attachable_fraction: float = 0.05,
    seed_expand_rounds: int = 3,
    seed_expand_relations: int = 20,
    seed_expand_triples_per_relation: int = 3,
    bridge_seed_relations: int = 15,
    bridge_seed_triples_per_relation: int = 3,
    bridge_seed_new_entities_target: int = 25,
    capacity_probe_rounds: int = 3,
    zero_triple_force_bootstrap_rounds: int = 5,
    attempt_log_path: Optional[str] = None,
    best_partial_path: Optional[str] = None,
    best_partial_triples_path: Optional[str] = None,
    relation_report_path: Optional[str] = None,
    relation_report_history_path: Optional[str] = None,
) -> Tuple[List[Dict], Dict[str, int]]:
    """Realize relation quotas into a connected triple set.

    Strategy
    --------
    1. Filter feasible relations by availability.
    2. Multi-start randomized greedy search:
       - seed connected component from high-demand relations,
       - prioritize next relation by overlap score to current component,
       - sample full relation quota with attachment invariant.
    3. Validate final undirected connectivity.

    Parameters
    ----------
    quotas:
        Relation-level target counts `{relation -> quota}`.
    ts:
        Triple source backend.
    mcfg:
        Field-name configuration.
    rcfg:
        Search/strictness configuration.

    Returns
    -------
    Tuple[List[Dict], Dict[str, int]]
        - realized triples
        - achieved counts per relation

    Raises
    ------
    RuntimeError
        In strict mode when exact quotas cannot be satisfied.
    """
    if not quotas:
        return [], {}

    def emit(event: str, payload: Dict) -> None:
        if progress_cb is not None:
            try:
                progress_cb(event, payload)
            except Exception:
                # Progress reporting must never break realization.
                pass

    if not attempt_log_path and checkpoint_path:
        attempt_log_path = f"{checkpoint_path}.attempts.jsonl"
    if not best_partial_path and checkpoint_path:
        best_partial_path = f"{checkpoint_path}.best_partial.json"
    if not best_partial_triples_path and checkpoint_path:
        best_partial_triples_path = f"{checkpoint_path}.best_partial.triples.jsonl"
    if not relation_report_path and checkpoint_path:
        relation_report_path = f"{checkpoint_path}.relation_report.current.json"
    if not relation_report_history_path and checkpoint_path:
        relation_report_history_path = f"{checkpoint_path}.relation_report.history.jsonl"

    def persist_attempt_record(record: Dict) -> None:
        if not attempt_log_path:
            return
        _append_jsonl(attempt_log_path, record)
        emit(
            "attempt_record_saved",
            {
                "path": attempt_log_path,
                "attempt": int(record.get("attempt", -1)),
                "event": str(record.get("event", "")),
            },
        )

    best_partial: Tuple[List[Dict], Dict[str, int]] = ([], {})
    best_partial_attempt = 0
    best_partial_doc = _load_checkpoint(best_partial_path) if best_partial_path else None
    if isinstance(best_partial_doc, dict) and best_partial_doc.get("quotas") == quotas:
        raw_triples = best_partial_doc.get("triples", [])
        raw_achieved = best_partial_doc.get("achieved", {})
        if isinstance(raw_triples, list) and isinstance(raw_achieved, dict):
            best_partial = (
                list(raw_triples),
                {str(k): int(v) for k, v in raw_achieved.items()},
            )
            best_partial_attempt = int(best_partial_doc.get("attempt", 0) or 0)
            emit(
                "best_partial_loaded",
                {
                    "path": best_partial_path,
                    "attempt": best_partial_attempt,
                    "triples_total": len(best_partial[0]),
                },
            )

    def persist_best_partial(
        attempt_idx: int,
        triples: List[Dict],
        achieved: Dict[str, int],
        connected: bool,
        reason: str,
    ) -> None:
        payload = {
            "status": "best_partial",
            "attempt": int(attempt_idx),
            "reason": reason,
            "connected": bool(connected),
            "quotas": quotas,
            "triples": triples,
            "achieved": achieved,
        }
        if best_partial_path:
            _dump_checkpoint(best_partial_path, payload)
        if best_partial_triples_path:
            _write_jsonl_records(best_partial_triples_path, triples)
        emit(
            "best_partial_saved",
            {
                "path": best_partial_path or best_partial_triples_path,
                "attempt": int(attempt_idx),
                "triples_total": len(triples),
                "reason": reason,
            },
        )

    def persist_relation_report(
        *,
        attempt_idx: int,
        reason: str,
        feasible: Dict[str, int],
        achieved_counts: Dict[str, int],
        remaining: Dict[str, int],
        fail_counts: Dict[str, int],
        deferral_counts: Dict[str, int],
        skipped_relations: Dict[str, str],
        status: str,
        triples_total: int,
        resume_loaded: bool,
        resume_reason: str,
        seed_info: Dict[str, object],
        final: bool = False,
    ) -> None:
        if not relation_report_path and not relation_report_history_path:
            return
        rows = build_relation_progress_rows(
            quotas=quotas,
            feasible=feasible,
            achieved_counts=achieved_counts,
            remaining=remaining,
            fail_counts=fail_counts,
            deferral_counts=deferral_counts,
            skipped_relations=skipped_relations,
        )
        status_counts: Dict[str, int] = defaultdict(int)
        for row in rows:
            status_counts[str(row["status"])] += 1
        payload = {
            "event": "relation_report",
            "attempt": int(attempt_idx),
            "reason": reason,
            "status": status,
            "final": bool(final),
            "resume_loaded": bool(resume_loaded),
            "resume_reason": resume_reason,
            "triples_total": int(triples_total),
            "relations_total": len(rows),
            "appeared_relations": int(sum(1 for row in rows if row["appeared_in_graph"])),
            "not_appeared_relations": int(sum(1 for row in rows if not row["appeared_in_graph"])),
            "status_counts": dict(status_counts),
            "seed_source": str(seed_info.get("source", "")),
            "seed_relation": str(seed_info.get("relation", "")),
            "seed_entity_count_start": int(seed_info.get("entity_count_start", 0) or 0),
            "relations": rows,
        }
        if relation_report_path:
            _dump_checkpoint(relation_report_path, payload)
        if relation_report_history_path:
            _append_jsonl(relation_report_history_path, payload)
        emit(
            "relation_report_saved",
            {
                "path": relation_report_path or relation_report_history_path,
                "attempt": int(attempt_idx),
                "reason": reason,
                "relations_total": len(rows),
            },
        )

    positive_items = [(pid, q) for pid, q in quotas.items() if q > 0]
    emit_count_total = len(positive_items)
    emit("feasibility_start", {"relations_total": emit_count_total})
    feasible: Dict[str, int] = {}
    for i, (pid, q) in enumerate(positive_items, start=1):
        try:
            ok = ts.count_triples(pid) > 0
        except Exception:
            ok = False
        if ok:
            feasible[pid] = q
        emit(
            "feasibility_progress",
            {
                "relations_checked": i,
                "relations_total": emit_count_total,
                "relations_feasible": len(feasible),
                "current_relation": pid,
            },
        )
    emit(
        "feasibility_done",
        {
            "relations_total": emit_count_total,
            "relations_feasible": len(feasible),
        },
    )
    if rcfg.strict_quotas and len(feasible) != len(quotas):
        missing = sorted(set(quotas) - set(feasible))
        if checkpoint_path:
            _dump_checkpoint(
                checkpoint_path,
                {
                    "status": "failed_precheck",
                    "quotas": quotas,
                    "relations_total": emit_count_total,
                    "relations_feasible": len(feasible),
                    "missing_relations": missing,
                },
            )
            emit("checkpoint_saved", {"path": checkpoint_path, "attempt": 0, "triples_so_far": 0})
        raise RuntimeError(
            f"Strict mode: {len(missing)} relations have no triples in source. Examples: {missing[:10]}"
        )

    if not feasible:
        raise RuntimeError("No feasible relations found with available triples.")

    resume_state = None
    if resume_from_checkpoint and checkpoint_path:
        cp = _load_checkpoint(checkpoint_path)
        if isinstance(cp, dict):
            if cp.get("status") == "success":
                emit("checkpoint_loaded", {"mode": "success", "path": checkpoint_path})
                return cp.get("triples", []), cp.get("achieved", {})
            if cp.get("status") == "in_progress" and cp.get("quotas") == quotas:
                resume_state = cp
                emit("checkpoint_loaded", {"mode": "in_progress", "path": checkpoint_path})
            elif cp.get("status") == "in_progress":
                emit("checkpoint_ignored", {"reason": "quota_mismatch", "path": checkpoint_path})

    if checkpoint_path and resume_state is None:
        _dump_checkpoint(
            checkpoint_path,
            {
                "status": "precheck_done",
                "quotas": quotas,
                "relations_total": emit_count_total,
                "relations_feasible": len(feasible),
            },
        )
        emit("checkpoint_saved", {"path": checkpoint_path, "attempt": 0, "triples_so_far": 0})

    for attempt in range(1, rcfg.attempts + 1):
        logger.info("Attempt %d/%d", attempt, rcfg.attempts)
        emit(
            "attempt_start",
            {
                "attempt": attempt,
                "attempts_total": rcfg.attempts,
                "relations_total": len(feasible),
            },
        )
        resumed_this_attempt = False
        resume_reason = ""
        remaining = dict(feasible)
        triples_out: List[Dict] = []
        V = set(str(x) for x in (initial_entities or []) if x)
        achieved_counts = defaultdict(int)
        used_by_relation: Dict[str, Set[Tuple[str, str, str]]] = defaultdict(set)
        checkpoint_counter = 0
        stall_rounds = 0
        fail_counts: Dict[str, int] = defaultdict(int)
        deferral_counts: Dict[str, int] = defaultdict(int)
        deferred_relations: Set[str] = set()
        seed_info: Dict[str, object] = {
            "source": "initial_entities" if V else "pending_seed",
            "relation": "",
            "entity_count_start": len(V),
        }
        seed_validation_info: Dict[str, int] = {}
        attempt_metrics: Dict[str, int] = {
            "seed_expansion_rounds": 0,
            "bridge_seed_events": 0,
            "bridge_seed_new_entities": 0,
            "force_bootstrap_events": 0,
            "capacity_checks": 0,
            "capacity_none": 0,
            "relation_failed_events": 0,
            "relation_deferred_events": 0,
            "chunk_backoff_events": 0,
            "chunk_backoff_successes": 0,
            "stall_rounds_total": 0,
            "stall_rounds_max": 0,
        }
        skipped_relations: Dict[str, str] = {}
        skipped_reason_counts: Dict[str, int] = defaultdict(int)
        if resume_state is not None and int(resume_state.get("attempt", -1)) == attempt:
            resumed_this_attempt = True
            resume_reason = str(resume_state.get("reason", "") or "")
            remaining = {str(k): int(v) for k, v in resume_state.get("remaining", {}).items()}
            triples_out = list(resume_state.get("triples_out", []))
            V = set(str(x) for x in resume_state.get("V", []))
            achieved_counts = defaultdict(int, {str(k): int(v) for k, v in resume_state.get("achieved_counts", {}).items()})
            raw_used = resume_state.get("used_by_relation", {})
            if isinstance(raw_used, dict):
                for rel, items in raw_used.items():
                    if isinstance(items, list):
                        used_by_relation[str(rel)] = set(
                            tuple(x) for x in items if isinstance(x, (list, tuple)) and len(x) == 3
                        )
            fail_counts = defaultdict(int, {str(k): int(v) for k, v in resume_state.get("fail_counts", {}).items()})
            deferral_counts = defaultdict(int, {str(k): int(v) for k, v in resume_state.get("deferral_counts", {}).items()})
            deferred_relations = set(str(x) for x in resume_state.get("deferred_relations", []))
            stall_rounds = int(resume_state.get("stall_rounds", 0) or 0)
            raw_seed_info = resume_state.get("seed_info", {})
            if isinstance(raw_seed_info, dict):
                seed_info = {
                    "source": str(raw_seed_info.get("source", seed_info["source"]) or seed_info["source"]),
                    "relation": str(raw_seed_info.get("relation", "") or ""),
                    "entity_count_start": int(raw_seed_info.get("entity_count_start", len(V)) or len(V)),
                }
            raw_seed_validation = resume_state.get("seed_validation_info", {})
            if isinstance(raw_seed_validation, dict):
                seed_validation_info = {
                    str(k): int(v) for k, v in raw_seed_validation.items() if isinstance(v, (int, float))
                }
            raw_attempt_metrics = resume_state.get("attempt_metrics", {})
            if isinstance(raw_attempt_metrics, dict):
                for key in attempt_metrics:
                    attempt_metrics[key] = int(raw_attempt_metrics.get(key, attempt_metrics[key]) or attempt_metrics[key])
            raw_skipped = resume_state.get("skipped_relations", {})
            if isinstance(raw_skipped, dict):
                skipped_relations = {str(k): str(v) for k, v in raw_skipped.items()}
            raw_skip_counts = resume_state.get("skipped_reason_counts", {})
            if isinstance(raw_skip_counts, dict):
                skipped_reason_counts = defaultdict(int, {str(k): int(v) for k, v in raw_skip_counts.items()})
            emit(
                "checkpoint_resumed",
                {
                    "attempt": attempt,
                    "relations_done": sum(1 for qv in remaining.values() if qv <= 0),
                    "relations_total": len(feasible),
                    "triples_so_far": len(triples_out),
                },
            )
            resume_state = None

        def save_checkpoint(reason: str) -> None:
            nonlocal checkpoint_counter
            if not checkpoint_path:
                if relation_report_path or relation_report_history_path:
                    persist_relation_report(
                        attempt_idx=attempt,
                        reason=reason,
                        feasible=feasible,
                        achieved_counts=dict(achieved_counts),
                        remaining=remaining,
                        fail_counts=dict(fail_counts),
                        deferral_counts=dict(deferral_counts),
                        skipped_relations=skipped_relations,
                        status="in_progress",
                        triples_total=len(triples_out),
                        resume_loaded=resumed_this_attempt,
                        resume_reason=resume_reason,
                        seed_info=seed_info,
                        final=False,
                    )
                checkpoint_counter = 0
                return
            payload = {
                "status": "in_progress",
                "attempt": attempt,
                "reason": reason,
                "quotas": quotas,
                "remaining": remaining,
                "triples_out": triples_out,
                "V": sorted(V),
                "achieved_counts": dict(achieved_counts),
                "used_by_relation": {k: [list(t) for t in vset] for k, vset in used_by_relation.items()},
                "fail_counts": dict(fail_counts),
                "deferral_counts": dict(deferral_counts),
                "deferred_relations": sorted(deferred_relations),
                "stall_rounds": int(stall_rounds),
                "seed_info": dict(seed_info),
                "seed_validation_info": dict(seed_validation_info),
                "attempt_metrics": dict(attempt_metrics),
                "skipped_relations": dict(skipped_relations),
                "skipped_reason_counts": dict(skipped_reason_counts),
                "best_partial_attempt": int(best_partial_attempt),
                "best_partial_triples_total": len(best_partial[0]),
            }
            _dump_checkpoint(checkpoint_path, payload)
            persist_relation_report(
                attempt_idx=attempt,
                reason=reason,
                feasible=feasible,
                achieved_counts=dict(achieved_counts),
                remaining=remaining,
                fail_counts=dict(fail_counts),
                deferral_counts=dict(deferral_counts),
                skipped_relations=skipped_relations,
                status="in_progress",
                triples_total=len(triples_out),
                resume_loaded=resumed_this_attempt,
                resume_reason=resume_reason,
                seed_info=seed_info,
                final=False,
            )
            emit("checkpoint_saved", {"path": checkpoint_path, "attempt": attempt, "triples_so_far": len(triples_out)})
            checkpoint_counter = 0

        if checkpoint_path:
            save_checkpoint("checkpoint_resumed" if resumed_this_attempt else "attempt_start")
        persist_attempt_record(
            {
                "event": "attempt_start",
                "attempt": attempt,
                "attempts_total": rcfg.attempts,
                "resume_loaded": resumed_this_attempt,
                "resume_reason": resume_reason,
                "relations_total": len(feasible),
                "seed_source": str(seed_info.get("source", "")),
                "seed_relation": str(seed_info.get("relation", "")),
                "seed_entity_count_start": int(seed_info.get("entity_count_start", len(V)) or len(V)),
                "triples_so_far": len(triples_out),
            }
        )
        if V:
            emit(
                "seed_entities_ready",
                {
                    "attempt": attempt,
                    "seed_entity_count": len(V),
                },
            )

        if not V:
            # Fallback seed from highest-demand relations when no initial entity anchors are provided.
            seed_candidates = sorted(remaining.items(), key=lambda kv: kv[1], reverse=True)
            seed_pid = None
            for pid, q in seed_candidates[: max(5, min(50, len(seed_candidates)))]:
                if q <= 0:
                    continue
                seed = ts.sample_triples_any(pid, 1)
                if seed:
                    seed_pid = pid
                    h0, t0 = endpoints(seed[0], mcfg)
                    V.update([h0, t0])
                    key = (h0, pid, t0)
                    used_by_relation[pid].add(key)
                    triples_out.append({mcfg.field_head: h0, mcfg.field_rel: pid, mcfg.field_tail: t0})
                    achieved_counts[pid] += 1
                    remaining[pid] -= 1
                    seed_info["source"] = "seed_triple"
                    seed_info["relation"] = pid
                    seed_info["entity_count_start"] = len(V)
                    done_rel = sum(1 for qv in remaining.values() if qv <= 0)
                    emit(
                        "seed_done",
                        {
                            "attempt": attempt,
                            "relation": pid,
                            "relations_done": done_rel,
                            "relations_total": len(feasible),
                            "triples_so_far": len(triples_out),
                        },
                    )
                    break
            if seed_pid is None:
                logger.info("No seed triple available; retrying.")
                emit(
                    "attempt_failed",
                    {
                        "attempt": attempt,
                        "reason": "no_seed",
                        "triples_so_far": len(triples_out),
                    },
                )
                persist_relation_report(
                    attempt_idx=attempt,
                    reason="no_seed",
                    feasible=feasible,
                    achieved_counts=dict(achieved_counts),
                    remaining=remaining,
                    fail_counts=dict(fail_counts),
                    deferral_counts=dict(deferral_counts),
                    skipped_relations=skipped_relations,
                    status="failed",
                    triples_total=len(triples_out),
                    resume_loaded=resumed_this_attempt,
                    resume_reason=resume_reason,
                    seed_info=seed_info,
                    final=True,
                )
                persist_attempt_record(
                    {
                        "event": "attempt_end",
                        "attempt": attempt,
                        "status": "failed",
                        "reason": "no_seed",
                        "connected": False,
                        "triples_total": len(triples_out),
                        "achieved_total": int(sum(achieved_counts.values())),
                        "remaining_total": int(sum(max(0, int(v)) for v in remaining.values())),
                        "resume_loaded": resumed_this_attempt,
                        "resume_reason": resume_reason,
                        "seed_source": str(seed_info.get("source", "")),
                        "seed_relation": str(seed_info.get("relation", "")),
                        "seed_entity_count_start": int(seed_info.get("entity_count_start", len(V)) or len(V)),
                        "seed_entity_count_end": len(V),
                    }
                )
                continue

        def attachable_summary(
            pending_items: List[Tuple[str, int]],
            probe_n: int,
        ) -> Tuple[int, Dict[str, int]]:
            caps: Dict[str, int] = {}
            attachable = 0
            if not pending_items:
                return 0, caps
            for rel_pid, _rel_q in pending_items:
                cap, _stage = estimate_attach_capacity(
                    ts,
                    rel_pid,
                    V,
                    probe_n,
                    relation_type_constraints=(relation_type_constraints or {}).get(rel_pid, {}),
                    use_controlled_relaxation=use_controlled_relaxation,
                    probe_rounds=capacity_probe_rounds,
                )
                cap_i = int(cap)
                attempt_metrics["capacity_checks"] += 1
                if cap_i <= 0:
                    attempt_metrics["capacity_none"] += 1
                caps[rel_pid] = cap_i
                if cap_i > 0:
                    attachable += 1
            return attachable, caps

        def build_attempt_summary(status: str, reason: str, connected: bool) -> Dict:
            achieved_snapshot = {pid: int(achieved_counts.get(pid, 0)) for pid in quotas}
            remaining_snapshot = {pid: int(remaining.get(pid, 0)) for pid in quotas}
            relations_full = 0
            relations_partial = 0
            relations_zero = 0
            top_unmet = []
            for pid, quota in quotas.items():
                achieved_i = int(achieved_snapshot.get(pid, 0))
                remaining_i = max(0, int(remaining_snapshot.get(pid, 0)))
                if achieved_i >= int(quota):
                    relations_full += 1
                elif achieved_i > 0:
                    relations_partial += 1
                else:
                    relations_zero += 1
                if remaining_i > 0 or skipped_relations.get(pid) or int(fail_counts.get(pid, 0)) > 0:
                    top_unmet.append(
                        {
                            "relation": pid,
                            "quota": int(quota),
                            "achieved": achieved_i,
                            "remaining": remaining_i,
                            "fail_count": int(fail_counts.get(pid, 0)),
                            "deferral_count": int(deferral_counts.get(pid, 0)),
                            "skip_reason": skipped_relations.get(pid, ""),
                        }
                    )
            top_unmet = sorted(top_unmet, key=lambda row: (row["remaining"], row["quota"]), reverse=True)[:20]
            return {
                "event": "attempt_end",
                "attempt": attempt,
                "status": status,
                "reason": reason,
                "connected": bool(connected),
                "triples_total": len(triples_out),
                "achieved_total": int(sum(achieved_snapshot.values())),
                "remaining_total": int(sum(max(0, int(v)) for v in remaining_snapshot.values())),
                "relations_total": len(quotas),
                "relations_fully_met": relations_full,
                "relations_partial": relations_partial,
                "relations_zero": relations_zero,
                "resume_loaded": resumed_this_attempt,
                "resume_reason": resume_reason,
                "seed_source": str(seed_info.get("source", "")),
                "seed_relation": str(seed_info.get("relation", "")),
                "seed_entity_count_start": int(seed_info.get("entity_count_start", len(V)) or len(V)),
                "seed_entity_count_end": len(V),
                "seed_validation": dict(seed_validation_info),
                "attempt_metrics": dict(attempt_metrics),
                "skipped_reason_counts": dict(skipped_reason_counts),
                "skipped_relations": dict(skipped_relations),
                "top_unmet_relations": top_unmet,
            }

        # Phase-1 style seed validation: if current anchors cannot attach enough relations,
        # expand V using untyped probes from high-demand pending relations.
        pending0 = [(pid, q) for pid, q in remaining.items() if q > 0]
        if pending0:
            target_attachable = max(
                1,
                int(seed_min_attachable_fraction * len(pending0)),
            )
            probe_n_seed = max(10, min(80, rcfg.overlap_probe_triples))
            attachable0, _caps0 = attachable_summary(pending0, probe_n_seed)
            emit(
                "seed_validation",
                {
                    "attempt": attempt,
                    "attachable_relations": int(attachable0),
                    "pending_relations": len(pending0),
                    "target_min_attachable": int(target_attachable),
                    "seed_entities": len(V),
                },
            )
            seed_validation_info = {
                "attachable_relations": int(attachable0),
                "pending_relations": int(len(pending0)),
                "target_min_attachable": int(target_attachable),
                "seed_entities": int(len(V)),
            }
            if attachable0 < target_attachable:
                ranked_for_seed = sorted(pending0, key=lambda x: x[1], reverse=True)
                for sround in range(1, max(1, int(seed_expand_rounds)) + 1):
                    before_v = len(V)
                    for pid, _q in ranked_for_seed[: max(1, int(seed_expand_relations))]:
                        seed_any = ts.sample_triples_any(pid, max(1, int(seed_expand_triples_per_relation)))
                        for tr in seed_any:
                            h, t = endpoints(tr, mcfg)
                            V.add(h)
                            V.add(t)
                    after_v = len(V)
                    pending_now = [(pid, q) for pid, q in remaining.items() if q > 0]
                    attachable_now, _caps_now = attachable_summary(pending_now, probe_n_seed)
                    emit(
                        "seed_expansion_round",
                        {
                            "attempt": attempt,
                            "round": sround,
                            "v_before": before_v,
                            "v_after": after_v,
                            "attachable_relations": int(attachable_now),
                            "pending_relations": len(pending_now),
                            "target_min_attachable": int(target_attachable),
                        },
                    )
                    attempt_metrics["seed_expansion_rounds"] = int(sround)
                    seed_validation_info["attachable_relations"] = int(attachable_now)
                    seed_validation_info["pending_relations"] = int(len(pending_now))
                    seed_validation_info["seed_entities"] = int(after_v)
                    if checkpoint_path:
                        save_checkpoint("seed_expansion")
                    if attachable_now >= target_attachable:
                        break

        ok = True
        while True:
            pending = [(pid, q) for pid, q in remaining.items() if q > 0]
            if not pending:
                break
            active_pending = [(pid, q) for pid, q in pending if pid not in deferred_relations]
            if not active_pending and deferred_relations:
                emit(
                    "deferred_relations_released",
                    {
                        "attempt": attempt,
                        "released_relations": len(deferred_relations),
                        "reason": "active_set_exhausted",
                    },
                )
                deferred_relations.clear()
                active_pending = pending

            scored = []
            zero_cap_relations = []
            for pid, q in active_pending:
                ov = compute_overlap_score(ts, pid, V, rcfg.overlap_probe_triples, mcfg)
                cap, cap_stage = estimate_attach_capacity(
                    ts,
                    pid,
                    V,
                    max(10, min(100, rcfg.overlap_probe_triples)),
                    relation_type_constraints=(relation_type_constraints or {}).get(pid, {}),
                    use_controlled_relaxation=use_controlled_relaxation,
                    probe_rounds=capacity_probe_rounds,
                )
                attempt_metrics["capacity_checks"] += 1
                emit(
                    "relation_capacity",
                    {
                        "attempt": attempt,
                        "relation": pid,
                        "capacity": int(cap),
                        "capacity_stage": cap_stage,
                        "remaining_quota": int(q),
                    },
                )
                if cap <= 0:
                    attempt_metrics["capacity_none"] += 1
                    zero_cap_relations.append((pid, q))
                    continue
                # Primary: immediate yield, then yield-to-demand ratio, then overlap/connectability.
                cap_eff = min(int(cap), int(q))
                cap_ratio = float(cap_eff) / float(max(1, int(q)))
                score = (1000.0 * float(cap_eff)) + (100.0 * cap_ratio) + (10.0 * float(ov))
                scored.append((pid, score))

            if not scored:
                stall_rounds += 1
                attempt_metrics["stall_rounds_total"] += 1
                attempt_metrics["stall_rounds_max"] = max(int(attempt_metrics["stall_rounds_max"]), int(stall_rounds))
                emit(
                    "stall_round",
                    {
                        "attempt": attempt,
                        "stall_rounds": stall_rounds,
                        "pending_relations": len(pending),
                        "active_pending_relations": len(active_pending),
                        "triples_so_far": len(triples_out),
                    },
                )
                # Controlled bridge reseed: expand V via relation-any probe without adding triple.
                bridge_seeded = False
                bridge_candidates = sorted(zero_cap_relations, key=lambda x: x[1], reverse=True)
                before_total = len(V)
                new_entities = 0
                seeded_relations = 0
                for pid, _q in bridge_candidates[: max(1, int(bridge_seed_relations))]:
                    seed_any = ts.sample_triples_any(pid, max(1, int(bridge_seed_triples_per_relation)))
                    if not seed_any:
                        continue
                    seeded_relations += 1
                    for tr in seed_any:
                        h, t = endpoints(tr, mcfg)
                        before = len(V)
                        V.update([h, t])
                        delta = len(V) - before
                        if delta > 0:
                            new_entities += int(delta)
                    if new_entities >= max(1, int(bridge_seed_new_entities_target)):
                        break
                if new_entities > 0:
                    bridge_seeded = True
                    attempt_metrics["bridge_seed_events"] += 1
                    attempt_metrics["bridge_seed_new_entities"] += int(new_entities)
                    emit(
                        "bridge_seed",
                        {
                            "attempt": attempt,
                            "v_before": before_total,
                            "v_after": len(V),
                            "new_entities": int(new_entities),
                            "seeded_relations": int(seeded_relations),
                        },
                    )
                    if deferred_relations:
                        emit(
                            "deferred_relations_released",
                            {
                                "attempt": attempt,
                                "released_relations": len(deferred_relations),
                                "reason": "bridge_seed",
                            },
                        )
                        deferred_relations.clear()
                if bridge_seeded:
                    checkpoint_counter += 1
                    if checkpoint_counter >= max(1, checkpoint_every_relations):
                        save_checkpoint("bridge_seed")
                    continue

                # Hard bootstrap: if we keep cycling with zero attach capacity and still
                # have no realized triples, force-add one sampled triple from a high-demand
                # relation to kickstart relation-level realization.
                if len(triples_out) == 0 and stall_rounds >= max(1, int(zero_triple_force_bootstrap_rounds)):
                    boot_pid = None
                    boot_tr = None
                    for cand_pid, _cand_q in sorted(pending, key=lambda x: x[1], reverse=True):
                        any_tr = ts.sample_triples_any(cand_pid, 1)
                        if any_tr:
                            boot_pid = cand_pid
                            boot_tr = any_tr[0]
                            break
                    if boot_pid is not None and boot_tr is not None:
                        h0, t0 = endpoints(boot_tr, mcfg)
                        key0 = (h0, boot_pid, t0)
                        if key0 not in used_by_relation[boot_pid]:
                            used_by_relation[boot_pid].add(key0)
                            triples_out.append({mcfg.field_head: h0, mcfg.field_rel: boot_pid, mcfg.field_tail: t0})
                            achieved_counts[boot_pid] += 1
                            remaining[boot_pid] = max(0, int(remaining.get(boot_pid, 0)) - 1)
                            V.update([h0, t0])
                            attempt_metrics["force_bootstrap_events"] += 1
                            emit(
                                "force_bootstrap",
                                {
                                    "attempt": attempt,
                                    "relation": boot_pid,
                                    "stall_rounds": stall_rounds,
                                    "triples_so_far": len(triples_out),
                                    "remaining_quota_after": int(remaining.get(boot_pid, 0)),
                                },
                            )
                            if checkpoint_path:
                                save_checkpoint("force_bootstrap")
                            if deferred_relations:
                                emit(
                                    "deferred_relations_released",
                                    {
                                        "attempt": attempt,
                                        "released_relations": len(deferred_relations),
                                        "reason": "force_bootstrap",
                                    },
                                )
                                deferred_relations.clear()
                            stall_rounds = 0
                            continue
                    else:
                        emit(
                            "force_bootstrap_failed",
                            {
                                "attempt": attempt,
                                "stall_rounds": stall_rounds,
                                "pending_relations": len(pending),
                            },
                        )

                if rcfg.strict_quotas:
                    ok = False
                    break
                # Non-strict: after repeated stalls, skip one hardest pending relation to unblock loop.
                if stall_rounds >= max(1, stall_max_rounds):
                    skip_pid = max(active_pending, key=lambda x: x[1])[0]
                    remaining[skip_pid] = 0
                    deferred_relations.discard(skip_pid)
                    skipped_relations[skip_pid] = "stall_unblock"
                    skipped_reason_counts["stall_unblock"] += 1
                    emit(
                        "relation_skipped",
                        {
                            "attempt": attempt,
                            "relation": skip_pid,
                            "relations_done": sum(1 for qv in remaining.values() if qv <= 0),
                            "relations_total": len(feasible),
                            "triples_so_far": len(triples_out),
                            "reason": "stall_unblock",
                        },
                    )
                    checkpoint_counter += 1
                    if checkpoint_counter >= max(1, checkpoint_every_relations):
                        save_checkpoint("stall_skip")
                    elif checkpoint_path:
                        save_checkpoint("stall_skip")
                    stall_rounds = 0
                continue

            stall_rounds = 0
            pid = rcl_pick(scored, rcfg.rcl_size) or max(scored, key=lambda x: x[1])[0]
            requested_need = min(int(remaining[pid]), max(1, int(micro_fill_chunk_size)))
            sampled = None
            chunk_schedule = chunk_backoff_schedule(requested_need)
            for idx, need in enumerate(chunk_schedule):
                anchor_n = max(1, int(rcfg.anchor_fraction * need))
                sampled = sample_n_triples_for_relation_connected(
                    ts=ts,
                    pid=pid,
                    n=need,
                    v=V,
                    mcfg=mcfg,
                    anchor_n=anchor_n,
                    used_keys=used_by_relation[pid],
                    relation_type_constraints=(relation_type_constraints or {}).get(pid, {}),
                    use_controlled_relaxation=use_controlled_relaxation,
                    stage_cb=lambda ev, pl: emit(
                        f"relation_{ev}",
                        {
                            "attempt": attempt,
                            **pl,
                        },
                    ),
                )
                if sampled is not None:
                    if need != requested_need:
                        attempt_metrics["chunk_backoff_successes"] += 1
                        emit(
                            "relation_chunk_backoff_success",
                            {
                                "attempt": attempt,
                                "relation": pid,
                                "requested_chunk_size": int(requested_need),
                                "realized_chunk_size": int(need),
                            },
                        )
                    break
                if idx + 1 < len(chunk_schedule):
                    attempt_metrics["chunk_backoff_events"] += 1
                    emit(
                        "relation_chunk_backoff",
                        {
                            "attempt": attempt,
                            "relation": pid,
                            "failed_chunk_size": int(need),
                            "next_chunk_size": int(chunk_schedule[idx + 1]),
                        },
                    )
            if sampled is None:
                fail_counts[pid] += 1
                attempt_metrics["relation_failed_events"] += 1
                emit(
                    "relation_failed",
                    {
                        "attempt": attempt,
                        "relation": pid,
                        "relations_done": sum(1 for qv in remaining.values() if qv <= 0),
                        "relations_total": len(feasible),
                        "triples_so_far": len(triples_out),
                        "fail_count": int(fail_counts[pid]),
                    },
                )
                if rcfg.strict_quotas:
                    ok = False
                    if checkpoint_path:
                        save_checkpoint("relation_failed")
                    break
                # Non-strict: only skip after repeated failures for this relation.
                if fail_counts[pid] >= max(1, max_fail_per_relation):
                    can_defer = deferral_counts[pid] < 1 and any(other_pid != pid for other_pid, _q in pending)
                    if can_defer:
                        deferral_counts[pid] += 1
                        fail_counts[pid] = 0
                        deferred_relations.add(pid)
                        attempt_metrics["relation_deferred_events"] += 1
                        emit(
                            "relation_deferred",
                            {
                                "attempt": attempt,
                                "relation": pid,
                                "relations_done": sum(1 for qv in remaining.values() if qv <= 0),
                                "relations_total": len(feasible),
                                "triples_so_far": len(triples_out),
                                "deferral_count": int(deferral_counts[pid]),
                                "reason": "max_fail_reached",
                            },
                        )
                        checkpoint_counter += 1
                        if checkpoint_counter >= max(1, checkpoint_every_relations):
                            save_checkpoint("relation_deferred")
                        elif checkpoint_path:
                            save_checkpoint("relation_deferred")
                    else:
                        remaining[pid] = 0
                        deferred_relations.discard(pid)
                        skip_reason = "max_fail_after_deferral" if deferral_counts[pid] > 0 else "max_fail_reached"
                        skipped_relations[pid] = skip_reason
                        skipped_reason_counts[skip_reason] += 1
                        emit(
                            "relation_skipped",
                            {
                                "attempt": attempt,
                                "relation": pid,
                                "relations_done": sum(1 for qv in remaining.values() if qv <= 0),
                                "relations_total": len(feasible),
                                "triples_so_far": len(triples_out),
                                "reason": skip_reason,
                            },
                        )
                        checkpoint_counter += 1
                        if checkpoint_counter >= max(1, checkpoint_every_relations):
                            save_checkpoint("relation_skip")
                        elif checkpoint_path:
                            save_checkpoint("relation_skip")
                elif checkpoint_path:
                    save_checkpoint("relation_failed")
                continue
            triples_out.extend(sampled)
            achieved_counts[pid] += len(sampled)
            fail_counts[pid] = 0
            if deferred_relations:
                emit(
                    "deferred_relations_released",
                    {
                        "attempt": attempt,
                        "released_relations": len(deferred_relations),
                        "reason": "graph_growth",
                    },
                )
                deferred_relations.clear()
            remaining[pid] = max(0, int(remaining[pid]) - len(sampled))
            if remaining[pid] <= 0:
                emit(
                    "relation_done",
                    {
                        "attempt": attempt,
                        "relation": pid,
                        "relations_done": sum(1 for qv in remaining.values() if qv <= 0),
                        "relations_total": len(feasible),
                        "triples_so_far": len(triples_out),
                    },
                )
            else:
                emit(
                    "relation_progress",
                    {
                        "attempt": attempt,
                        "relation": pid,
                        "remaining_quota": int(remaining[pid]),
                        "triples_so_far": len(triples_out),
                    },
                )
            checkpoint_counter += 1
            if checkpoint_path and checkpoint_counter >= max(1, checkpoint_every_relations):
                save_checkpoint("relation_progress")

        achieved = {pid: int(achieved_counts.get(pid, 0)) for pid in quotas}

        connected = is_connected_undirected(triples_out, mcfg)
        if ok and connected:
            logger.info("Connected realization succeeded on attempt %d. triples=%d", attempt, len(triples_out))
            persist_best_partial(
                attempt_idx=attempt,
                triples=triples_out,
                achieved=achieved,
                connected=True,
                reason="success",
            )
            best_partial_attempt = attempt
            if checkpoint_path:
                _dump_checkpoint(
                    checkpoint_path,
                    {
                        "status": "success",
                        "attempt": attempt,
                        "quotas": quotas,
                        "triples": triples_out,
                        "achieved": achieved,
                    },
                )
                emit("checkpoint_saved", {"path": checkpoint_path, "attempt": attempt, "triples_so_far": len(triples_out)})
            emit(
                "success",
                {
                    "attempt": attempt,
                    "attempts_total": rcfg.attempts,
                    "triples_total": len(triples_out),
                },
            )
            persist_relation_report(
                attempt_idx=attempt,
                reason="connected_success",
                feasible=feasible,
                achieved_counts=achieved,
                remaining=remaining,
                fail_counts=dict(fail_counts),
                deferral_counts=dict(deferral_counts),
                skipped_relations=skipped_relations,
                status="success",
                triples_total=len(triples_out),
                resume_loaded=resumed_this_attempt,
                resume_reason=resume_reason,
                seed_info=seed_info,
                final=True,
            )
            persist_attempt_record(build_attempt_summary(status="success", reason="connected_success", connected=True))
            return triples_out, achieved

        if len(triples_out) > len(best_partial[0]):
            best_partial = (list(triples_out), dict(achieved))
            best_partial_attempt = attempt
            persist_best_partial(
                attempt_idx=attempt,
                triples=best_partial[0],
                achieved=best_partial[1],
                connected=connected,
                reason="attempt_improved",
            )
        failure_reason = "connectivity_or_quota" if rcfg.strict_quotas else "strict_off_partial_attempt"
        emit(
            "attempt_failed",
            {
                "attempt": attempt,
                "reason": failure_reason,
                "triples_so_far": len(triples_out),
                "connected": connected,
            },
        )
        persist_relation_report(
            attempt_idx=attempt,
            reason=failure_reason,
            feasible=feasible,
            achieved_counts=achieved,
            remaining=remaining,
            fail_counts=dict(fail_counts),
            deferral_counts=dict(deferral_counts),
            skipped_relations=skipped_relations,
            status="failed",
            triples_total=len(triples_out),
            resume_loaded=resumed_this_attempt,
            resume_reason=resume_reason,
            seed_info=seed_info,
            final=True,
        )
        persist_attempt_record(build_attempt_summary(status="failed", reason=failure_reason, connected=connected))

    if rcfg.strict_quotas:
        if checkpoint_path and best_partial[0]:
            _dump_checkpoint(
                checkpoint_path,
                {
                    "status": "partial",
                    "attempt": int(best_partial_attempt),
                    "quotas": quotas,
                    "triples": best_partial[0],
                    "achieved": best_partial[1],
                },
            )
            emit("checkpoint_saved", {"path": checkpoint_path, "attempt": rcfg.attempts, "triples_so_far": len(best_partial[0])})
        emit("failed_all_attempts", {"attempts_total": rcfg.attempts})
        raise RuntimeError(
            "Failed to realize exact connected quotas after all attempts. "
            "Try lowering quotas, increasing attempts, or relaxing strict mode."
        )
    if checkpoint_path:
        _dump_checkpoint(
            checkpoint_path,
            {
                "status": "partial",
                "attempt": int(best_partial_attempt),
                "quotas": quotas,
                "triples": best_partial[0],
                "achieved": best_partial[1],
            },
        )
        emit("checkpoint_saved", {"path": checkpoint_path, "attempt": rcfg.attempts, "triples_so_far": len(best_partial[0])})
    emit(
        "partial_result",
        {
            "triples_total": len(best_partial[0]),
            "attempts_total": rcfg.attempts,
        },
    )
    return best_partial


def main() -> None:
    """CLI entrypoint.

    Supports two data-source modes:
    - MongoDB mode (default): uses `--mongo_*` options.
    - Local JSONL mode: set `--triples_jsonl` to bypass Mongo entirely.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--allocation_csv", default="", help="Allocation CSV export from dashboard.")
    ap.add_argument("--allocation_json", default="", help="Allocation JSON export from dashboard.")
    ap.add_argument("--output_triples", default="connected_allocation_sample.triples.jsonl")
    ap.add_argument("--output_metadata", default="connected_allocation_sample.metadata.json")
    ap.add_argument(
        "--triples_jsonl",
        default="",
        help="Local triples source JSONL (one object per line). If set, MongoDB is not used.",
    )

    ap.add_argument("--mongo_uri", default="mongodb://localhost:27017")
    ap.add_argument("--mongo_db", default="wikidata_ontology")
    ap.add_argument("--mongo_collection", default="triplets")
    ap.add_argument("--field_head", default="h")
    ap.add_argument("--field_rel", default="r")
    ap.add_argument("--field_tail", default="t")

    ap.add_argument("--attempts", type=int, default=10)
    ap.add_argument("--rcl_size", type=int, default=10)
    ap.add_argument("--anchor_fraction", type=float, default=0.2)
    ap.add_argument("--overlap_probe_triples", type=int, default=200)
    ap.add_argument("--mongo_batch_limit", type=int, default=5000)
    ap.add_argument("--allow_sampling_fallback", action="store_true")
    ap.add_argument("--non_strict", action="store_true", help="Allow partial result if exact quotas cannot be met.")
    ap.add_argument("--seed", type=int, default=42)

    args = ap.parse_args()
    random.seed(args.seed)

    if not args.allocation_csv and not args.allocation_json:
        raise ValueError("Provide one of --allocation_csv or --allocation_json.")

    rows: List[Dict] = []
    if args.allocation_csv:
        rows.extend(load_allocations_csv(args.allocation_csv))
    if args.allocation_json:
        rows.extend(load_allocations_json(args.allocation_json))
    if not rows:
        raise RuntimeError("No allocation rows loaded.")

    quotas, by_pattern = build_relation_quotas(rows)
    if not quotas:
        raise RuntimeError("No positive eta_integer quotas found in allocation input.")
    logger.info("Loaded quotas for %d relations (total triples target=%d).", len(quotas), sum(quotas.values()))

    mcfg = MongoConfig(
        uri=args.mongo_uri,
        db_name=args.mongo_db,
        triples_collection=args.mongo_collection,
        field_head=args.field_head,
        field_rel=args.field_rel,
        field_tail=args.field_tail,
    )
    rcfg = RealizationConfig(
        attempts=max(1, args.attempts),
        rcl_size=max(1, args.rcl_size),
        anchor_fraction=max(0.0, min(1.0, args.anchor_fraction)),
        overlap_probe_triples=max(1, args.overlap_probe_triples),
        mongo_batch_limit=max(1, args.mongo_batch_limit),
        allow_sampling_fallback=bool(args.allow_sampling_fallback),
        strict_quotas=not bool(args.non_strict),
    )

    using_local = bool(args.triples_jsonl)
    if using_local:
        triples_by_rel = load_triples_jsonl_index(args.triples_jsonl, mcfg)
        ts = LocalTripleSource(triples_by_rel=triples_by_rel, mcfg=mcfg)
    else:
        if MongoClient is None:
            raise RuntimeError(
                "pymongo is not installed and --triples_jsonl was not provided. "
                "Install pymongo or use --triples_jsonl."
            )
        client = MongoClient(mcfg.uri)
        coll = client[mcfg.db_name][mcfg.triples_collection]
        ts = TripleSource(coll, mcfg, rcfg)

    triples, achieved = realize_connected_graph(quotas, ts, mcfg, rcfg)
    if not triples:
        raise RuntimeError("No triples were realized.")

    achieved_total = sum(achieved.values())
    target_total = sum(quotas.values())

    with open(args.output_triples, "w", encoding="utf-8") as f:
        for tr in triples:
            f.write(json.dumps(tr, ensure_ascii=False) + "\n")

    metadata = {
        "target_total_triples": target_total,
        "achieved_total_triples": achieved_total,
        "relation_quotas": quotas,
        "achieved_per_relation": achieved,
        "pattern_relation_quotas": by_pattern,
        "connected_undirected": is_connected_undirected(triples, mcfg),
        "config": {
            "attempts": rcfg.attempts,
            "rcl_size": rcfg.rcl_size,
            "anchor_fraction": rcfg.anchor_fraction,
            "overlap_probe_triples": rcfg.overlap_probe_triples,
            "mongo_batch_limit": rcfg.mongo_batch_limit,
            "allow_sampling_fallback": rcfg.allow_sampling_fallback,
            "strict_quotas": rcfg.strict_quotas,
            "seed": args.seed,
        },
        "source": {
            "mode": "jsonl" if using_local else "mongo",
            "triples_jsonl": args.triples_jsonl if using_local else None,
            "mongo_uri": None if using_local else mcfg.uri,
            "mongo_db_name": None if using_local else mcfg.db_name,
            "mongo_triples_collection": None if using_local else mcfg.triples_collection,
            "field_head": mcfg.field_head,
            "field_rel": mcfg.field_rel,
            "field_tail": mcfg.field_tail,
        },
    }
    with open(args.output_metadata, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    logger.info("Wrote triples: %s", args.output_triples)
    logger.info("Wrote metadata: %s", args.output_metadata)
    logger.info("Achieved %d / %d triples", achieved_total, target_total)


if __name__ == "__main__":
    main()
