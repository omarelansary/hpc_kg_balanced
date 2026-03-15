#!/usr/bin/env python3
"""Relation-motif-guided repair for missing allocated relations.

This script repairs missing allocated relations in a sampled knowledge graph by
using directed 2-hop relation motifs anchored in already realized graph
structure.

Method summary
--------------
Let:
- ``r_g`` be an allocated relation that is already realized in the graph.
- ``r_m`` be an allocated relation that is missing from the graph.
- hop-support store directed pair support for patterns of the form
  ``a --r1--> b --r2--> c``.

For each missing relation ``r_m``, the script searches for realized relations
``r_g`` such that either:

1. ``(r_g, r_m)`` has support, corresponding to the motif
   ``s --r_g--> x --r_m--> y``.
2. ``(r_m, r_g)`` has support, corresponding to the motif
   ``z --r_m--> x --r_g--> y``.

Candidate pair-orientation combinations are ranked using:

    score = priority(r_m)
            * log(1 + hop_support)
            * log(1 + anchor_count)
            * component_bonus

Then the script queries WDQS with a *strong anchored query* that requires the
realized relation context to be instantiated by graph entities.

Template A: realized relation first, missing relation second
------------------------------------------------------------
Used when support exists for ``(r_g, r_m)``.

    VALUES ?s { ... G_subj(r_g) ... }
    VALUES ?x { ... G_obj(r_g) ... }
    ?s wdt:r_g ?x .
    ?x wdt:r_m ?y .

Repairs the missing triple ``(x, r_m, y)``.

Template B: missing relation first, realized relation second
------------------------------------------------------------
Used when support exists for ``(r_m, r_g)``.

    VALUES ?x { ... G_subj(r_g) ... }
    VALUES ?y { ... G_obj(r_g) ... }
    ?z wdt:r_m ?x .
    ?x wdt:r_g ?y .

Repairs the missing triple ``(z, r_m, x)``.

Filtering and cleaning
----------------------
The script implements the following checks and controls:
- The realized ``r_g`` context must already exist in the graph.
- The repaired triple must be novel.
- Self-loops can be blocked unless explicitly allowed.
- Optional type consistency check for the repaired triple.
- Prefer anchors in the giant component.
- Limit accepted repairs per anchor entity.
- Limit accepted repairs per missing relation.
- Limit candidate pair-orientation combinations per missing relation.

Input assumptions
-----------------
Graph triples JSONL:
    Each line is an object with at least ``h``, ``r``, ``t``.

Hop-support JSONL:
    Each line is an object with:
    - ``r1``
    - ``support_data``: mapping ``r2 -> {total, loop, nonloop}``

Priority file:
    JSONL, JSON, or CSV. Each record must contain a relation identifier and a
    priority field such as ``eta_integer`` or ``eta_expected``.

Optional type constraint files:
    constraints JSON/JSONL record format:
        {
          "relation": "P31",
          "valid_subject_type_ids": ["Q5", ...],
          "valid_object_type_ids": ["Q43229", ...]
        }
    entity-types JSON/JSONL format either:
        {"entity": "Q42", "types": ["Q5", ...]}
    or a JSON object:
        {"Q42": ["Q5", ...], ...}

Outputs
-------
- repaired graph triples JSONL
- accepted repair log JSONL
- rejected candidate log JSONL
- summary JSON

Notes
-----
This method is a targeted repair strategy. It is not expected to recover every
missing allocated relation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
import heapq
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

try:
    import requests
except Exception:  # pragma: no cover - requests may be missing in some environments
    requests = None


Triple = Tuple[str, str, str]
Pair = Tuple[str, str]
Relation = str
Entity = str
Orientation = str  # "rg_rm" or "rm_rg"


@dataclass(frozen=True)
class CandidatePair:
    """Ranked relation-pair candidate for repairing one missing relation.

    Attributes
    ----------
    missing_relation:
        Missing allocated relation to repair.
    realized_relation:
        Already realized allocated relation that provides graph anchors.
    orientation:
        Either ``rg_rm`` meaning ``(r_g, r_m)`` support exists, or ``rm_rg``
        meaning ``(r_m, r_g)`` support exists.
    hop_support:
        Directed 2-hop support count from the hop-support store.
    anchor_count:
        Number of possible graph anchors for the realized relation in the
        required role.
    giant_component_anchor_fraction:
        Fraction of available anchors that belong to the giant component.
    score:
        Final ranking score for the pair-orientation candidate.
    priority_value:
        Priority of the missing relation, usually ``eta_integer`` or
        ``eta_expected``.
    """

    missing_relation: Relation
    realized_relation: Relation
    orientation: Orientation
    hop_support: int
    anchor_count: int
    giant_component_anchor_fraction: float
    score: float
    priority_value: float


@dataclass
class RepairRecord:
    """Accepted repair log record."""

    missing_relation: Relation
    realized_relation: Relation
    orientation: Orientation
    hop_support: int
    anchor_count: int
    priority_value: float
    relation_pair_score: float
    anchor_entity: Entity
    anchor_component_id: int
    anchor_in_giant_component: bool
    candidate_triple_h: Entity
    candidate_triple_r: Relation
    candidate_triple_t: Entity
    graph_context_h: Optional[Entity]
    graph_context_r: Relation
    graph_context_t: Optional[Entity]
    wdqs_query_template: str
    wdqs_query_hash: str
    type_filter_enabled: bool
    type_filter_passed: Optional[bool]
    accepted_at_unix: float


@dataclass
class RejectRecord:
    """Rejected candidate log record."""

    missing_relation: Relation
    realized_relation: Relation
    orientation: Orientation
    candidate_triple_h: Optional[Entity]
    candidate_triple_r: Relation
    candidate_triple_t: Optional[Entity]
    reason: str
    details: Dict[str, Any]


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "time": time.time(),
        }
        return json.dumps(payload, ensure_ascii=False)


class WDQSClient:
    """Small SPARQL client with retry and backoff.

    Parameters
    ----------
    endpoint:
        SPARQL endpoint URL.
    user_agent:
        User-Agent header string.
    timeout_sec:
        Request timeout in seconds.
    max_retries:
        Maximum retries per request.
    min_delay_sec:
        Delay between calls to reduce endpoint pressure.
    random_seed:
        Seed for jitter.
    dry_run:
        If True, queries are not executed and only returned as text.
    """

    def __init__(
        self,
        endpoint: str,
        user_agent: str,
        timeout_sec: float,
        max_retries: int,
        min_delay_sec: float,
        random_seed: int,
        dry_run: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.min_delay_sec = min_delay_sec
        self.dry_run = dry_run
        self._rng = random.Random(random_seed)
        self._last_call_ts = 0.0
        if not dry_run and requests is None:
            raise RuntimeError("requests is required for live WDQS querying")

    def _sleep_if_needed(self) -> None:
        now = time.time()
        dt = now - self._last_call_ts
        if dt < self.min_delay_sec:
            time.sleep(self.min_delay_sec - dt)
        self._last_call_ts = time.time()

    def run_select(self, query: str) -> Dict[str, Any]:
        """Execute a SELECT query and return parsed JSON.

        In dry-run mode this returns an empty bindings payload while still
        preserving the same output shape.
        """
        if self.dry_run:
            return {"results": {"bindings": []}, "dry_run": True, "query": query}

        headers = {
            "Accept": "application/sparql-results+json",
            "User-Agent": self.user_agent,
        }
        data = {"query": query}
        params = {"format": "json"}

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                self._sleep_if_needed()
                response = requests.post(
                    self.endpoint,
                    headers=headers,
                    data=data,
                    params=params,
                    timeout=self.timeout_sec,
                )
                if response.status_code == 200:
                    return response.json()
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise RuntimeError(f"endpoint status={response.status_code}")
                raise RuntimeError(
                    f"non-retryable endpoint status={response.status_code} body={response.text[:500]}"
                )
            except Exception as exc:  # pragma: no cover - network dependent
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                backoff = (2 ** attempt) + self._rng.uniform(0.0, 0.5)
                time.sleep(backoff)
        assert last_exc is not None
        raise last_exc


def setup_logging(verbose: bool) -> None:
    """Configure process logging."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(handler)


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    """Yield JSON objects from a JSONL file."""
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_no}: {exc}") from exc


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    """Write dictionaries to JSONL."""
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


class JsonlAppender:
    """Append JSON rows to disk immediately (flush on each write)."""

    def __init__(self, path: Path, *, truncate: bool = False) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if truncate else "a"
        self._fh = self.path.open(mode, encoding="utf-8")

    def write(self, row: Dict[str, Any]) -> None:
        self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def write_checkpoint_atomic(path: Path, payload: Dict[str, Any]) -> None:
    """Atomically update checkpoint JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_checkpoint(path: Path) -> Dict[str, Any]:
    """Load checkpoint JSON, returning empty state when absent."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_json_or_jsonl(path: Path) -> Any:
    """Load JSON or JSONL based on extension/content.

    Returns
    -------
    Any
        JSON object for .json, list of objects for .jsonl.
    """
    if path.suffix.lower() == ".jsonl":
        return list(iter_jsonl(path))
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_relation_list(path: Path) -> List[Relation]:
    """Load a relation list from txt/json/jsonl/csv.

    Supported formats
    -----------------
    txt:
        one relation per line
    json:
        list[str] or dict keys or list[dict] with relation field
    jsonl:
        one object per line with relation field
    csv:
        one column named relation or r
    """
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if suffix == ".jsonl":
        rows = list(iter_jsonl(path))
        return [extract_relation_field(row) for row in rows]
    if suffix == ".json":
        obj = load_json_or_jsonl(path)
        if isinstance(obj, list):
            if all(isinstance(x, str) for x in obj):
                return list(obj)
            return [extract_relation_field(x) for x in obj]
        if isinstance(obj, dict):
            if all(isinstance(k, str) for k in obj.keys()):
                return list(obj.keys())
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            out: List[str] = []
            for row in reader:
                rel = row.get("relation") or row.get("r")
                if rel:
                    out.append(rel)
            return out
    raise ValueError(f"unsupported relation list format: {path}")


def extract_relation_field(row: Dict[str, Any]) -> Relation:
    """Extract relation identifier from a record."""
    for key in ("relation", "r", "predicate", "property"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    raise KeyError(f"could not find relation field in row keys={list(row.keys())}")


def load_priorities(path: Path, priority_field: str) -> Dict[Relation, float]:
    """Load relation priorities from JSON, JSONL, or CSV.

    Parameters
    ----------
    path:
        File containing relation priority data.
    priority_field:
        Column/key to use as priority.
    """
    suffix = path.suffix.lower()
    out: Dict[Relation, float] = {}

    def update_from_row(row: Dict[str, Any]) -> None:
        rel = extract_relation_field(row)
        if priority_field not in row:
            raise KeyError(f"priority field '{priority_field}' not found for relation={rel}")
        out[rel] = float(row[priority_field])

    if suffix == ".jsonl":
        for row in iter_jsonl(path):
            update_from_row(row)
        return out
    if suffix == ".json":
        obj = load_json_or_jsonl(path)
        if isinstance(obj, dict):
            # Either mapping relation -> value or nested dict.
            for rel, value in obj.items():
                if isinstance(value, (int, float)):
                    out[str(rel)] = float(value)
                elif isinstance(value, dict):
                    if priority_field not in value:
                        raise KeyError(f"priority field '{priority_field}' not found for relation={rel}")
                    out[str(rel)] = float(value[priority_field])
                else:
                    raise ValueError(f"unsupported JSON mapping value for relation={rel}: {type(value)}")
            return out
        if isinstance(obj, list):
            for row in obj:
                update_from_row(row)
            return out
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                update_from_row(row)
        return out
    raise ValueError(f"unsupported priority file format: {path}")


def load_relation_eta_caps_from_allocation(
    path: Optional[Path],
    eta_field: str = "eta_expected",
    rounding: str = "floor",
) -> Tuple[Dict[Relation, int], Dict[Relation, float]]:
    """Load per-relation acceptance caps from allocation results.

    Uses the maximum value of ``eta_field`` for each relation.
    """
    if path is None:
        return {}, {}

    obj = load_json_or_jsonl(path)
    if isinstance(obj, dict) and isinstance(obj.get("allocations"), list):
        rows = obj["allocations"]
    elif isinstance(obj, list):
        rows = obj
    else:
        raise ValueError(f"unsupported allocation file shape: {path}")

    max_eta: Dict[Relation, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            rel = extract_relation_field(row)
        except KeyError:
            continue
        raw = row.get(eta_field)
        if raw is None:
            continue
        value = float(raw)
        if not math.isfinite(value):
            continue
        prev = max_eta.get(rel)
        if prev is None or value > prev:
            max_eta[rel] = value

    caps: Dict[Relation, int] = {}
    for rel, value in max_eta.items():
        if rounding == "ceil":
            cap = int(math.ceil(value))
        elif rounding == "round":
            cap = int(round(value))
        else:
            cap = int(math.floor(value))
        caps[rel] = max(1, cap)
    return caps, max_eta


def load_graph(path: Path) -> List[Triple]:
    """Load graph triples from JSONL."""
    triples: List[Triple] = []
    for row in iter_jsonl(path):
        h = row["h"]
        r = row["r"]
        t = row["t"]
        triples.append((h, r, t))
    return triples


def build_graph_indices_from_jsonl(
    path: Path,
) -> Tuple[
    Set[Triple],
    Dict[Relation, Set[Entity]],
    Dict[Relation, Set[Entity]],
    Dict[Relation, Set[Pair]],
    Dict[Entity, Set[Entity]],
    Dict[Entity, int],
    int,
    int,
]:
    """Build graph indices directly from JSONL without storing a full list."""
    triple_set: Set[Triple] = set()
    rel_to_subj: Dict[Relation, Set[Entity]] = defaultdict(set)
    rel_to_obj: Dict[Relation, Set[Entity]] = defaultdict(set)
    rel_to_pairs: Dict[Relation, Set[Pair]] = defaultdict(set)
    adjacency: Dict[Entity, Set[Entity]] = defaultdict(set)
    input_count = 0

    for row in iter_jsonl(path):
        input_count += 1
        h = row["h"]
        r = row["r"]
        t = row["t"]
        triple = (h, r, t)
        if triple in triple_set:
            continue
        triple_set.add(triple)
        rel_to_subj[r].add(h)
        rel_to_obj[r].add(t)
        rel_to_pairs[r].add((h, t))
        adjacency[h].add(t)
        adjacency[t].add(h)

    node_to_component: Dict[Entity, int] = {}
    component_sizes: Dict[int, int] = {}
    comp_id = 0
    for node in adjacency:
        if node in node_to_component:
            continue
        stack = [node]
        node_to_component[node] = comp_id
        size = 0
        while stack:
            cur = stack.pop()
            size += 1
            for nbr in adjacency[cur]:
                if nbr not in node_to_component:
                    node_to_component[nbr] = comp_id
                    stack.append(nbr)
        component_sizes[comp_id] = size
        comp_id += 1

    giant_component_id = max(component_sizes.items(), key=lambda kv: kv[1])[0] if component_sizes else -1
    return (
        triple_set,
        rel_to_subj,
        rel_to_obj,
        rel_to_pairs,
        adjacency,
        node_to_component,
        giant_component_id,
        input_count,
    )


def build_graph_indices(
    triples: Sequence[Triple],
) -> Tuple[
    Set[Triple],
    Dict[Relation, Set[Entity]],
    Dict[Relation, Set[Entity]],
    Dict[Relation, Set[Pair]],
    Dict[Entity, Set[Entity]],
    Dict[Entity, int],
    int,
]:
    """Build relation-specific graph indices and weak components.

    Weak components are computed on the undirected version of the graph.

    Returns
    -------
    triple_set
        All graph triples.
    rel_to_subj
        ``r -> {subjects}``
    rel_to_obj
        ``r -> {objects}``
    rel_to_pairs
        ``r -> {(subject, object)}``
    adjacency
        Undirected adjacency map.
    node_to_component
        Weak-component id per node.
    giant_component_id
        Component id with the largest number of nodes.
    """
    triple_set = set(triples)
    rel_to_subj: Dict[Relation, Set[Entity]] = defaultdict(set)
    rel_to_obj: Dict[Relation, Set[Entity]] = defaultdict(set)
    rel_to_pairs: Dict[Relation, Set[Pair]] = defaultdict(set)
    adjacency: Dict[Entity, Set[Entity]] = defaultdict(set)

    for h, r, t in triples:
        rel_to_subj[r].add(h)
        rel_to_obj[r].add(t)
        rel_to_pairs[r].add((h, t))
        adjacency[h].add(t)
        adjacency[t].add(h)
        if h not in adjacency:
            adjacency[h] = set()
        if t not in adjacency:
            adjacency[t] = set()

    node_to_component: Dict[Entity, int] = {}
    component_sizes: Dict[int, int] = {}
    comp_id = 0
    for node in adjacency:
        if node in node_to_component:
            continue
        stack = [node]
        node_to_component[node] = comp_id
        size = 0
        while stack:
            cur = stack.pop()
            size += 1
            for nbr in adjacency[cur]:
                if nbr not in node_to_component:
                    node_to_component[nbr] = comp_id
                    stack.append(nbr)
        component_sizes[comp_id] = size
        comp_id += 1

    if component_sizes:
        giant_component_id = max(component_sizes.items(), key=lambda kv: kv[1])[0]
    else:
        giant_component_id = -1

    return (
        triple_set,
        rel_to_subj,
        rel_to_obj,
        rel_to_pairs,
        adjacency,
        node_to_component,
        giant_component_id,
    )


def load_hop_support(path: Path) -> Dict[Relation, Dict[Relation, int]]:
    """Load directed hop-support counts as ``support[r1][r2] = total``."""
    support: Dict[Relation, Dict[Relation, int]] = {}
    for row in iter_jsonl(path):
        r1 = row["r1"]
        data = row.get("support_data", {})
        if not isinstance(data, dict):
            continue
        inner: Dict[Relation, int] = {}
        for r2, stats in data.items():
            if isinstance(stats, dict):
                inner[r2] = int(stats.get("total", 0))
            elif isinstance(stats, (int, float)):
                inner[r2] = int(stats)
        support[r1] = inner
    return support


def load_constraints(path: Optional[Path]) -> Dict[Relation, Dict[str, Set[str]]]:
    """Load type constraints mapping.

    Returns
    -------
    dict
        ``relation -> {valid_subject_type_ids: set, valid_object_type_ids: set}``
    """
    if path is None:
        return {}
    obj = load_json_or_jsonl(path)
    rows = obj if isinstance(obj, list) else [obj]
    constraints: Dict[Relation, Dict[str, Set[str]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        rel = extract_relation_field(row)
        subj = set(row.get("valid_subject_type_ids") or [])
        obj_types = set(row.get("valid_object_type_ids") or [])
        constraints[rel] = {
            "valid_subject_type_ids": subj,
            "valid_object_type_ids": obj_types,
        }
    return constraints


def load_entity_types(path: Optional[Path]) -> Dict[Entity, Set[str]]:
    """Load entity type assignments.

    Supported shapes
    ----------------
    JSONL rows:
        {"entity": "Q42", "types": ["Q5", ...]}
    JSON object:
        {"Q42": ["Q5", ...]}
    JSON list:
        same as JSONL rows
    """
    if path is None:
        return {}
    obj = load_json_or_jsonl(path)
    out: Dict[Entity, Set[str]] = {}
    if isinstance(obj, dict):
        for ent, types in obj.items():
            out[str(ent)] = set(types or [])
        return out
    rows = obj if isinstance(obj, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entity = row.get("entity") or row.get("qid") or row.get("id")
        if entity:
            out[str(entity)] = set(row.get("types") or row.get("type_ids") or [])
    return out


def type_filter_passes(
    relation: Relation,
    h: Entity,
    t: Entity,
    constraints: Dict[Relation, Dict[str, Set[str]]],
    entity_types: Dict[Entity, Set[str]],
) -> Optional[bool]:
    """Check type consistency for a candidate triple.

    Returns
    -------
    Optional[bool]
        ``True`` or ``False`` if enough information exists.
        ``None`` if no applicable type constraints or entity type data exist.
    """
    if relation not in constraints or not entity_types:
        return None
    c = constraints[relation]
    subj_allowed = c.get("valid_subject_type_ids", set())
    obj_allowed = c.get("valid_object_type_ids", set())
    h_types = entity_types.get(h)
    t_types = entity_types.get(t)
    if h_types is None or t_types is None:
        return None
    subj_ok = True if not subj_allowed else bool(h_types & subj_allowed)
    obj_ok = True if not obj_allowed else bool(t_types & obj_allowed)
    return subj_ok and obj_ok


def query_hash(query: str) -> str:
    """Small deterministic query fingerprint."""
    return hashlib.sha1(query.encode("utf-8")).hexdigest()


def chunked(seq: Sequence[str], size: int) -> Iterator[List[str]]:
    """Yield fixed-size chunks from a sequence."""
    for i in range(0, len(seq), size):
        yield list(seq[i : i + size])


def chunked_pairs(seq: Sequence[Pair], size: int) -> Iterator[List[Pair]]:
    """Yield fixed-size chunks from a pair sequence."""
    for i in range(0, len(seq), size):
        yield list(seq[i : i + size])


def sparql_values_pairs(var_a: str, var_b: str, pairs: Sequence[Pair]) -> str:
    """Build VALUES with two variables, e.g. VALUES (?s ?x) { (wd:Q1 wd:Q2) }."""
    if not pairs:
        return f"VALUES (?{var_a} ?{var_b}) {{ }}"
    items = " ".join(f"(wd:{a} wd:{b})" for a, b in pairs)
    return f"VALUES (?{var_a} ?{var_b}) {{ {items} }}"


def build_query_template_a(anchor_pairs: Sequence[Pair], rg: str, rm: str, limit: int) -> str:
    """Build strong anchored WDQS query for orientation ``(r_g, r_m)``.

    This asks for graph-instantiated contexts ``s --r_g--> x`` and missing continuations
    ``x --r_m--> y`` while keeping only entity-object candidates.
    """
    return f"""
SELECT DISTINCT ?s ?x ?y WHERE {{
  {sparql_values_pairs('s', 'x', anchor_pairs)}
  ?s wdt:{rg} ?x .
  ?x wdt:{rm} ?y .
  FILTER(STRSTARTS(STR(?y), "http://www.wikidata.org/entity/Q"))
}}
LIMIT {limit}
""".strip()


def build_query_template_b(anchor_pairs: Sequence[Pair], rg: str, rm: str, limit: int) -> str:
    """Build strong anchored WDQS query for orientation ``(r_m, r_g)``.

    This asks for missing incoming edges ``z --r_m--> x`` and graph-instantiated contexts
    ``x --r_g--> y`` while keeping only entity-subject candidates.
    """
    return f"""
SELECT DISTINCT ?z ?x ?y WHERE {{
  {sparql_values_pairs('x', 'y', anchor_pairs)}
  ?z wdt:{rm} ?x .
  ?x wdt:{rg} ?y .
  FILTER(STRSTARTS(STR(?z), "http://www.wikidata.org/entity/Q"))
}}
LIMIT {limit}
""".strip()


def parse_wd_entity(binding: Dict[str, Any], field: str) -> Optional[str]:
    """Extract bare QID from a SPARQL binding field."""
    if field not in binding:
        return None
    value = binding[field].get("value")
    if not isinstance(value, str):
        return None
    if "/entity/" in value:
        return value.rsplit("/entity/", 1)[-1]
    return value


def is_qid(value: Optional[str]) -> bool:
    """Return True when value looks like a Wikidata QID."""
    if not isinstance(value, str):
        return False
    if not value.startswith("Q"):
        return False
    return value[1:].isdigit()


def giant_component_anchor_fraction(
    anchors: Iterable[Entity],
    node_to_component: Dict[Entity, int],
    giant_component_id: int,
) -> float:
    """Compute the fraction of anchors inside the giant component."""
    anchors = list(anchors)
    if not anchors:
        return 0.0
    good = 0
    for a in anchors:
        if node_to_component.get(a) == giant_component_id:
            good += 1
    return good / max(1, len(anchors))


def relation_pair_candidates(
    missing_relations: Sequence[Relation],
    realized_relations: Set[Relation],
    priorities: Dict[Relation, float],
    support: Dict[Relation, Dict[Relation, int]],
    rel_to_subj: Dict[Relation, Set[Entity]],
    rel_to_obj: Dict[Relation, Set[Entity]],
    node_to_component: Dict[Entity, int],
    giant_component_id: int,
) -> Dict[Relation, List[CandidatePair]]:
    """Generate and score candidate pair-orientation repairs.

    For each missing relation ``r_m``, this searches for realized relations
    ``r_g`` with support in either directed orientation.
    """
    out: Dict[Relation, List[CandidatePair]] = defaultdict(list)

    for rm in missing_relations:
        priority = float(priorities.get(rm, 0.0))
        for rg in realized_relations:
            # Orientation 1: (r_g, r_m)
            support_rg_rm = int(support.get(rg, {}).get(rm, 0))
            if support_rg_rm > 0:
                anchors = rel_to_obj.get(rg, set())
                anchor_count = len(anchors)
                if anchor_count > 0:
                    frac = giant_component_anchor_fraction(anchors, node_to_component, giant_component_id)
                    score = max(priority, 1e-12) * math.log1p(support_rg_rm) * math.log1p(anchor_count) * (1.0 + frac)
                    out[rm].append(
                        CandidatePair(
                            missing_relation=rm,
                            realized_relation=rg,
                            orientation="rg_rm",
                            hop_support=support_rg_rm,
                            anchor_count=anchor_count,
                            giant_component_anchor_fraction=frac,
                            score=score,
                            priority_value=priority,
                        )
                    )

            # Orientation 2: (r_m, r_g)
            support_rm_rg = int(support.get(rm, {}).get(rg, 0))
            if support_rm_rg > 0:
                anchors = rel_to_subj.get(rg, set())
                anchor_count = len(anchors)
                if anchor_count > 0:
                    frac = giant_component_anchor_fraction(anchors, node_to_component, giant_component_id)
                    score = max(priority, 1e-12) * math.log1p(support_rm_rg) * math.log1p(anchor_count) * (1.0 + frac)
                    out[rm].append(
                        CandidatePair(
                            missing_relation=rm,
                            realized_relation=rg,
                            orientation="rm_rg",
                            hop_support=support_rm_rg,
                            anchor_count=anchor_count,
                            giant_component_anchor_fraction=frac,
                            score=score,
                            priority_value=priority,
                        )
                    )

        out[rm].sort(key=lambda x: (-x.score, -x.hop_support, -x.anchor_count, x.realized_relation, x.orientation))
    return out


def relation_pair_candidates_for_missing(
    rm: Relation,
    realized_relations: Set[Relation],
    priorities: Dict[Relation, float],
    support: Dict[Relation, Dict[Relation, int]],
    rel_to_subj: Dict[Relation, Set[Entity]],
    rel_to_obj: Dict[Relation, Set[Entity]],
    node_to_component: Dict[Entity, int],
    giant_component_id: int,
) -> List[CandidatePair]:
    """Generate and score pair-orientation candidates for one missing relation."""
    priority = float(priorities.get(rm, 0.0))
    out: List[CandidatePair] = []
    for rg in realized_relations:
        support_rg_rm = int(support.get(rg, {}).get(rm, 0))
        if support_rg_rm > 0:
            anchors = rel_to_obj.get(rg, set())
            anchor_count = len(anchors)
            if anchor_count > 0:
                frac = giant_component_anchor_fraction(anchors, node_to_component, giant_component_id)
                score = max(priority, 1e-12) * math.log1p(support_rg_rm) * math.log1p(anchor_count) * (1.0 + frac)
                out.append(
                    CandidatePair(
                        missing_relation=rm,
                        realized_relation=rg,
                        orientation="rg_rm",
                        hop_support=support_rg_rm,
                        anchor_count=anchor_count,
                        giant_component_anchor_fraction=frac,
                        score=score,
                        priority_value=priority,
                    )
                )

        support_rm_rg = int(support.get(rm, {}).get(rg, 0))
        if support_rm_rg > 0:
            anchors = rel_to_subj.get(rg, set())
            anchor_count = len(anchors)
            if anchor_count > 0:
                frac = giant_component_anchor_fraction(anchors, node_to_component, giant_component_id)
                score = max(priority, 1e-12) * math.log1p(support_rm_rg) * math.log1p(anchor_count) * (1.0 + frac)
                out.append(
                    CandidatePair(
                        missing_relation=rm,
                        realized_relation=rg,
                        orientation="rm_rg",
                        hop_support=support_rm_rg,
                        anchor_count=anchor_count,
                        giant_component_anchor_fraction=frac,
                        score=score,
                        priority_value=priority,
                    )
                )

    out.sort(key=lambda x: (-x.score, -x.hop_support, -x.anchor_count, x.realized_relation, x.orientation))
    return out


def maybe_shuffle_and_limit(items: List[CandidatePair], top_k: int, seed: int) -> List[CandidatePair]:
    """Keep top-k candidate pair-orientation combinations.

    Ties are already mostly deterministic due to sorting. This helper exists so
    the selection strategy can be modified later if desired.
    """
    shuffled = list(items)
    rng = random.Random(seed)
    rng.shuffle(shuffled)
    shuffled.sort(key=lambda x: (-x.score, -x.hop_support, -x.anchor_count))
    return shuffled[:top_k]


def relation_seed(base_seed: int, relation: str) -> int:
    """Build a deterministic per-relation seed."""
    digest = hashlib.sha1(relation.encode("utf-8")).hexdigest()
    return (base_seed + int(digest[:8], 16)) % (2 ** 31 - 1)


def candidate_new_entity_penalty(counter: Counter[str], entity: str) -> float:
    """Penalty for repeatedly introducing the same new entity.

    Returns a multiplicative factor in ``(0, 1]``.
    """
    count = counter[entity]
    return 1.0 / (1.0 + math.log1p(count))


def iter_template_a_rows(
    client: WDQSClient,
    rg: Relation,
    rm: Relation,
    anchor_pairs: Sequence[Pair],
    values_chunk_size: int,
    query_limit: int,
) -> Iterator[Dict[str, Optional[str]]]:
    """Run Template A over chunked VALUES and collect bindings.

    Yields rows with fields ``s``, ``x``, ``y``.
    """
    for pair_chunk in chunked_pairs(list(anchor_pairs), values_chunk_size):
        query = build_query_template_a(pair_chunk, rg, rm, query_limit)
        payload = client.run_select(query)
        for b in payload.get("results", {}).get("bindings", []):
            yield {
                "s": parse_wd_entity(b, "s"),
                "x": parse_wd_entity(b, "x"),
                "y": parse_wd_entity(b, "y"),
                "_query": query,
            }


def iter_template_b_rows(
    client: WDQSClient,
    rg: Relation,
    rm: Relation,
    anchor_pairs: Sequence[Pair],
    values_chunk_size: int,
    query_limit: int,
) -> Iterator[Dict[str, Optional[str]]]:
    """Run Template B over chunked VALUES and collect bindings.

    Yields rows with fields ``z``, ``x``, ``y``.
    """
    for pair_chunk in chunked_pairs(list(anchor_pairs), values_chunk_size):
        query = build_query_template_b(pair_chunk, rg, rm, query_limit)
        payload = client.run_select(query)
        for b in payload.get("results", {}).get("bindings", []):
            yield {
                "z": parse_wd_entity(b, "z"),
                "x": parse_wd_entity(b, "x"),
                "y": parse_wd_entity(b, "y"),
                "_query": query,
            }


def relation_pair_context_exists_template_a(rel_to_pairs: Dict[Relation, Set[Pair]], rg: Relation, s: str, x: str) -> bool:
    """Check whether graph already contains ``(s, r_g, x)``."""
    return (s, x) in rel_to_pairs.get(rg, set())


def relation_pair_context_exists_template_b(rel_to_pairs: Dict[Relation, Set[Pair]], rg: Relation, x: str, y: str) -> bool:
    """Check whether graph already contains ``(x, r_g, y)``."""
    return (x, y) in rel_to_pairs.get(rg, set())


def run_repair(args: argparse.Namespace) -> Dict[str, Any]:
    """Run the full relation-motif-guided repair pipeline."""
    logger = logging.getLogger("relation_motif_repair")

    graph_path = Path(args.graph_jsonl)
    hop_support_path = Path(args.hop_support_jsonl)
    priorities_path = Path(args.priorities)
    missing_path = Path(args.missing_relations)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    constraints_path = Path(args.constraints_json) if args.constraints_json else None
    entity_types_path = Path(args.entity_types_json) if args.entity_types_json else None
    realized_relations_path = Path(args.realized_relations) if args.realized_relations else None
    allocation_results_path = Path(args.allocation_results_json) if args.allocation_results_json else None

    repaired_graph_path = out_dir / "repaired_graph.jsonl"
    accepted_log_path = out_dir / "accepted_repairs.jsonl"
    rejected_log_path = out_dir / "rejected_repairs.jsonl"
    summary_path = out_dir / "summary.json"
    pair_candidates_path = out_dir / "pair_candidates.jsonl"
    new_triples_path = out_dir / "new_triples_added.jsonl"
    collected_candidates_path = out_dir / "collected_candidates_all.jsonl"
    unused_candidates_path = out_dir / "collected_candidates_unused.jsonl"
    checkpoint_path = Path(args.checkpoint_path) if args.checkpoint_path else (out_dir / "repair_checkpoint.json")

    logger.info("loading graph and building indices")
    (
        triple_set,
        rel_to_subj,
        rel_to_obj,
        rel_to_pairs,
        _,
        node_to_component,
        giant_component_id,
        graph_input_triples_count,
    ) = build_graph_indices_from_jsonl(graph_path)

    logger.info("loading hop support")
    support = load_hop_support(hop_support_path)

    logger.info("loading priorities")
    priorities = load_priorities(priorities_path, args.priority_field)

    logger.info("loading missing relations")
    missing_relations = load_relation_list(missing_path)

    if realized_relations_path:
        logger.info("loading realized relation whitelist")
        realized_relations = set(load_relation_list(realized_relations_path))
    else:
        realized_relations = set(rel_to_pairs.keys())
    initial_realized_relations_count = len(realized_relations)

    logger.info("loading optional type constraints")
    constraints = load_constraints(constraints_path)
    entity_types = load_entity_types(entity_types_path)
    type_filter_enabled = bool(args.enable_type_filter and constraints and entity_types)

    logger.info("loading allocation-based per-relation caps")
    eta_caps, _eta_raw_max = load_relation_eta_caps_from_allocation(
        allocation_results_path,
        eta_field=args.allocation_eta_field,
        rounding=args.allocation_eta_rounding,
    )
    per_relation_cap: Dict[Relation, int] = {}
    for rm in missing_relations:
        if rm in eta_caps:
            per_relation_cap[rm] = eta_caps[rm]
        else:
            per_relation_cap[rm] = max(1, int(args.max_accepts_per_missing_relation))

    resume = bool(args.resume)
    if not resume and checkpoint_path.exists():
        checkpoint_path.unlink()

    checkpoint = load_checkpoint(checkpoint_path) if resume else {}
    processed_missing_relations: Set[str] = set(checkpoint.get("processed_missing_relations", []))
    accepted_per_missing_relation: Counter[str] = Counter(
        {k: int(v) for k, v in (checkpoint.get("accepted_per_missing_relation") or {}).items()}
    )
    accepted_per_anchor: Counter[str] = Counter(
        {k: int(v) for k, v in (checkpoint.get("accepted_per_anchor") or {}).items()}
    )
    introduced_new_entity_counter: Counter[str] = Counter(
        {k: int(v) for k, v in (checkpoint.get("introduced_new_entity_counter") or {}).items()}
    )
    accepted_repairs_count = int(checkpoint.get("accepted_repairs", 0))
    rejected_candidates_count = int(checkpoint.get("rejected_candidates", 0))
    new_triples_added_count = int(checkpoint.get("new_triples_added", 0))
    realized_missing_relations: Set[str] = set(checkpoint.get("repaired_relations", []))
    processed_since_checkpoint = 0
    pass_index = int(checkpoint.get("pass_index", 0))

    if resume and new_triples_path.exists():
        restored = 0
        for row in iter_jsonl(new_triples_path):
            h = row.get("h")
            r = row.get("r")
            t = row.get("t")
            if not isinstance(h, str) or not isinstance(r, str) or not isinstance(t, str):
                continue
            triple = (h, r, t)
            if triple in triple_set:
                continue
            triple_set.add(triple)
            rel_to_subj[r].add(h)
            rel_to_obj[r].add(t)
            rel_to_pairs[r].add((h, t))
            restored += 1
        if restored:
            logger.info("restored new triples from resume file", extra={"restored": restored})

    if resume and accepted_log_path.exists():
        accepted_per_missing_relation.clear()
        accepted_per_anchor.clear()
        introduced_new_entity_counter.clear()
        accepted_repairs_count = 0
        realized_missing_relations.clear()
        for row in iter_jsonl(accepted_log_path):
            rm = row.get("missing_relation")
            anchor = row.get("anchor_entity")
            h = row.get("candidate_triple_h")
            t = row.get("candidate_triple_t")
            orientation = row.get("orientation")
            if isinstance(rm, str):
                accepted_per_missing_relation[rm] += 1
                realized_missing_relations.add(rm)
            if isinstance(anchor, str):
                accepted_per_anchor[anchor] += 1
            if orientation == "rg_rm" and isinstance(t, str):
                introduced_new_entity_counter[t] += 1
            elif orientation == "rm_rg" and isinstance(h, str):
                introduced_new_entity_counter[h] += 1
            accepted_repairs_count += 1

    if resume and rejected_log_path.exists():
        rejected_candidates_count = sum(1 for _ in iter_jsonl(rejected_log_path))

    if resume and new_triples_path.exists():
        new_triples_added_count = sum(1 for _ in iter_jsonl(new_triples_path))
    # Re-enable relations that were previously marked as processed only due to
    # lack of candidates. We only keep relations processed when their cap is met.
    cap_reached_relations = {
        rm
        for rm in missing_relations
        if accepted_per_missing_relation[rm] >= max(1, int(per_relation_cap.get(rm, args.max_accepts_per_missing_relation)))
    }
    if pass_index <= 0:
        processed_missing_relations = set(cap_reached_relations)
    else:
        processed_missing_relations = {
            rm for rm in processed_missing_relations if rm in set(missing_relations)
        } | cap_reached_relations

    # Any already-accepted missing relation is now realized and can act as r_g.
    for rm in missing_relations:
        if accepted_per_missing_relation[rm] > 0:
            realized_relations.add(rm)

    client = WDQSClient(
        endpoint=args.endpoint,
        user_agent=args.user_agent,
        timeout_sec=args.timeout_sec,
        max_retries=args.max_retries,
        min_delay_sec=args.min_delay_sec,
        random_seed=args.random_seed,
        dry_run=args.dry_run,
    )

    accepted_writer = JsonlAppender(accepted_log_path, truncate=not resume)
    rejected_writer = JsonlAppender(rejected_log_path, truncate=not resume)
    pair_writer = JsonlAppender(pair_candidates_path, truncate=not resume)
    new_triples_writer = JsonlAppender(new_triples_path, truncate=not resume)
    collected_writer = JsonlAppender(collected_candidates_path, truncate=not resume)
    unused_writer = JsonlAppender(unused_candidates_path, truncate=not resume)

    def persist_checkpoint(force: bool = False) -> None:
        nonlocal processed_since_checkpoint, pass_index
        if not force and processed_since_checkpoint < max(1, int(args.checkpoint_every)):
            return
        payload = {
            "processed_missing_relations": sorted(processed_missing_relations),
            "accepted_per_missing_relation": dict(accepted_per_missing_relation),
            "accepted_per_anchor": dict(accepted_per_anchor),
            "introduced_new_entity_counter": dict(introduced_new_entity_counter),
            "accepted_repairs": int(accepted_repairs_count),
            "rejected_candidates": int(rejected_candidates_count),
            "new_triples_added": int(new_triples_added_count),
            "repaired_relations": sorted(realized_missing_relations),
            "pass_index": int(pass_index),
            "updated_at_unix": time.time(),
        }
        write_checkpoint_atomic(checkpoint_path, payload)
        processed_since_checkpoint = 0

    try:
        passes_completed = 0
        while True:
            pending_relations = [
                rm for rm in missing_relations
                if accepted_per_missing_relation[rm] < max(1, int(per_relation_cap.get(rm, args.max_accepts_per_missing_relation)))
            ]
            if not pending_relations:
                break
            if args.max_reconsider_passes > 0 and passes_completed >= args.max_reconsider_passes:
                break

            pass_index += 1
            passes_completed += 1
            pass_new_triples = 0

            # From pass 2 onward, revisit all unresolved relations.
            if pass_index > 1:
                processed_missing_relations = {
                    rm
                    for rm in processed_missing_relations
                    if accepted_per_missing_relation[rm] >= max(1, int(per_relation_cap.get(rm, args.max_accepts_per_missing_relation)))
                }

            logger.info(
                "starting repair pass",
                extra={
                    "pass_index": pass_index,
                    "pending_relations": len(pending_relations),
                    "realized_relations": len(realized_relations),
                },
            )

            for rm in pending_relations:
                if rm in processed_missing_relations:
                    continue

                relation_cap = max(1, int(per_relation_cap.get(rm, args.max_accepts_per_missing_relation)))
                if accepted_per_missing_relation[rm] >= relation_cap:
                    processed_missing_relations.add(rm)
                    processed_since_checkpoint += 1
                    persist_checkpoint()
                    continue

                pair_candidates = relation_pair_candidates_for_missing(
                    rm=rm,
                    realized_relations=realized_relations,
                    priorities=priorities,
                    support=support,
                    rel_to_subj=rel_to_subj,
                    rel_to_obj=rel_to_obj,
                    node_to_component=node_to_component,
                    giant_component_id=giant_component_id,
                )
                candidates = maybe_shuffle_and_limit(
                    pair_candidates,
                    args.top_pair_candidates_per_missing_relation,
                    relation_seed(args.random_seed, rm),
                )
                for cp in candidates:
                    pair_writer.write(asdict(cp))

                if not candidates:
                    rejected = RejectRecord(
                        missing_relation=rm,
                        realized_relation="",
                        orientation="",
                        candidate_triple_h=None,
                        candidate_triple_r=rm,
                        candidate_triple_t=None,
                        reason="no_supported_realized_relation_pair",
                        details={"pass_index": pass_index},
                    )
                    rejected_writer.write(asdict(rejected))
                    rejected_candidates_count += 1
                    processed_missing_relations.add(rm)
                    processed_since_checkpoint += 1
                    persist_checkpoint()
                    continue

                accepted_before_relation = accepted_per_missing_relation[rm]
                for cand in candidates:
                    if accepted_per_missing_relation[rm] >= relation_cap:
                        break

                    rg = cand.realized_relation
                    anchor_pairs = sorted(rel_to_pairs.get(rg, set()))
                    if not anchor_pairs:
                        rejected = RejectRecord(
                            missing_relation=rm,
                            realized_relation=rg,
                            orientation=cand.orientation,
                            candidate_triple_h=None,
                            candidate_triple_r=rm,
                            candidate_triple_t=None,
                            reason="no_anchor_pairs_for_realized_relation",
                            details={},
                        )
                        rejected_writer.write(asdict(rejected))
                        rejected_candidates_count += 1
                        continue

                    remaining = relation_cap - accepted_per_missing_relation[rm]
                    if remaining <= 0:
                        break

                    if cand.orientation == "rg_rm":
                        row_iter = iter_template_a_rows(
                            client=client,
                            rg=rg,
                            rm=rm,
                            anchor_pairs=anchor_pairs,
                            values_chunk_size=args.values_chunk_size,
                            query_limit=args.query_limit,
                        )
                        query_template = "template_a"
                    else:
                        row_iter = iter_template_b_rows(
                            client=client,
                            rg=rg,
                            rm=rm,
                            anchor_pairs=anchor_pairs,
                            values_chunk_size=args.values_chunk_size,
                            query_limit=args.query_limit,
                        )
                        query_template = "template_b"

                    scored_heap: List[Tuple[float, int, Dict[str, Any]]] = []
                    row_index = 0
                    for row in row_iter:
                        row_index += 1
                        query_text = row.get("_query") or ""
                        q_hash = query_hash(query_text)

                        if cand.orientation == "rg_rm":
                            s = row.get("s")
                            x = row.get("x")
                            y = row.get("y")
                            candidate_h = x
                            candidate_t = y
                            graph_context_h = s
                            graph_context_t = x
                            anchor_entity = x
                            new_entity = y
                            context_ok = bool(s and x and relation_pair_context_exists_template_a(rel_to_pairs, rg, s, x))
                            self_loop = bool(x and y and x == y)
                            type_pass = type_filter_passes(rm, x, y, constraints, entity_types) if (type_filter_enabled and x and y) else None
                        else:
                            z = row.get("z")
                            x = row.get("x")
                            y = row.get("y")
                            candidate_h = z
                            candidate_t = x
                            graph_context_h = x
                            graph_context_t = y
                            anchor_entity = x
                            new_entity = z
                            context_ok = bool(x and y and relation_pair_context_exists_template_b(rel_to_pairs, rg, x, y))
                            self_loop = bool(z and x and z == x)
                            type_pass = type_filter_passes(rm, z, x, constraints, entity_types) if (type_filter_enabled and z and x) else None

                        collected_payload: Dict[str, Any] = {
                            "missing_relation": rm,
                            "realized_relation": rg,
                            "orientation": cand.orientation,
                            "candidate_triple_h": candidate_h,
                            "candidate_triple_r": rm,
                            "candidate_triple_t": candidate_t,
                            "graph_context_h": graph_context_h,
                            "graph_context_r": rg,
                            "graph_context_t": graph_context_t,
                            "anchor_entity": anchor_entity,
                            "new_entity": new_entity,
                            "wdqs_query_template": query_template,
                            "wdqs_query_hash": q_hash,
                            "wdqs_query": query_text,
                            "hop_support": cand.hop_support,
                            "relation_pair_score": cand.score,
                        }
                        collected_writer.write(collected_payload)

                        def reject_and_store(reason: str, details: Dict[str, Any]) -> None:
                            nonlocal rejected_candidates_count
                            rejected = RejectRecord(
                                missing_relation=rm,
                                realized_relation=rg,
                                orientation=cand.orientation,
                                candidate_triple_h=candidate_h,
                                candidate_triple_r=rm,
                                candidate_triple_t=candidate_t,
                                reason=reason,
                                details=details,
                            )
                            rejected_writer.write(asdict(rejected))
                            rejected_candidates_count += 1
                            unused_writer.write(
                                {
                                    **collected_payload,
                                    "reason": reason,
                                    "details": details,
                                }
                            )

                        if not candidate_h or not candidate_t or not anchor_entity:
                            reject_and_store("missing_binding_field", row)
                            continue
                        if not is_qid(candidate_h) or not is_qid(candidate_t):
                            reject_and_store("non_entity_candidate", {})
                            continue
                        new_triple = (candidate_h, rm, candidate_t)
                        if new_triple in triple_set:
                            reject_and_store("triple_already_exists", {})
                            continue
                        if not context_ok:
                            reject_and_store("graph_context_not_found", {"context": [graph_context_h, rg, graph_context_t]})
                            continue
                        if (not args.allow_self_loops) and self_loop:
                            reject_and_store("self_loop_blocked", {})
                            continue
                        if type_filter_enabled and type_pass is False:
                            reject_and_store("type_filter_failed", {})
                            continue
                        if accepted_per_anchor[anchor_entity] >= args.max_accepts_per_anchor:
                            reject_and_store(
                                "anchor_reuse_limit_reached",
                                {"anchor": anchor_entity, "count": accepted_per_anchor[anchor_entity]},
                            )
                            continue

                        component_bonus = args.giant_component_bonus if node_to_component.get(anchor_entity) == giant_component_id else 1.0
                        type_bonus = args.type_bonus if type_pass is True else 1.0
                        novelty_penalty = candidate_new_entity_penalty(introduced_new_entity_counter, new_entity)
                        final_score = cand.score * component_bonus * type_bonus * novelty_penalty
                        scored_payload = {
                            **collected_payload,
                            "final_score": final_score,
                            "type_filter_passed": type_pass,
                        }

                        if len(scored_heap) < remaining:
                            heapq.heappush(scored_heap, (final_score, row_index, scored_payload))
                        else:
                            worst_score, worst_row_idx, worst_payload = scored_heap[0]
                            if (final_score, row_index) > (worst_score, worst_row_idx):
                                heapq.heapreplace(scored_heap, (final_score, row_index, scored_payload))
                                unused_writer.write(
                                    {
                                        **worst_payload,
                                        "reason": "not_selected_rank_pruned",
                                        "details": {"remaining_capacity": remaining},
                                    }
                                )
                            else:
                                unused_writer.write(
                                    {
                                        **scored_payload,
                                        "reason": "not_selected_rank_pruned",
                                        "details": {"remaining_capacity": remaining},
                                    }
                                )

                    selected = sorted(scored_heap, key=lambda x: (-x[0], x[1]))
                    for _, _, selected_payload in selected:
                        if accepted_per_missing_relation[rm] >= relation_cap:
                            unused_writer.write(
                                {
                                    **selected_payload,
                                    "reason": "relation_cap_reached_post_rank",
                                    "details": {"relation_cap": relation_cap},
                                }
                            )
                            continue
                        candidate_h = selected_payload["candidate_triple_h"]
                        candidate_t = selected_payload["candidate_triple_t"]
                        anchor_entity = selected_payload["anchor_entity"]
                        new_entity = selected_payload["new_entity"]
                        assert isinstance(candidate_h, str)
                        assert isinstance(candidate_t, str)
                        assert isinstance(anchor_entity, str)
                        assert isinstance(new_entity, str)
                        new_triple = (candidate_h, rm, candidate_t)
                        if new_triple in triple_set:
                            unused_writer.write(
                                {
                                    **selected_payload,
                                    "reason": "triple_already_exists_post_rank",
                                    "details": {},
                                }
                            )
                            continue
                        if accepted_per_anchor[anchor_entity] >= args.max_accepts_per_anchor:
                            unused_writer.write(
                                {
                                    **selected_payload,
                                    "reason": "anchor_reuse_limit_reached_post_rank",
                                    "details": {"anchor": anchor_entity, "count": accepted_per_anchor[anchor_entity]},
                                }
                            )
                            continue

                        triple_set.add(new_triple)
                        rel_to_subj[rm].add(candidate_h)
                        rel_to_obj[rm].add(candidate_t)
                        rel_to_pairs[rm].add((candidate_h, candidate_t))

                        accepted_per_missing_relation[rm] += 1
                        accepted_per_anchor[anchor_entity] += 1
                        introduced_new_entity_counter[new_entity] += 1
                        accepted_repairs_count += 1
                        new_triples_added_count += 1
                        pass_new_triples += 1
                        realized_missing_relations.add(rm)
                        realized_relations.add(rm)

                        new_triples_writer.write({"h": candidate_h, "r": rm, "t": candidate_t})

                        accepted = RepairRecord(
                            missing_relation=rm,
                            realized_relation=rg,
                            orientation=cand.orientation,
                            hop_support=cand.hop_support,
                            anchor_count=cand.anchor_count,
                            priority_value=cand.priority_value,
                            relation_pair_score=cand.score,
                            anchor_entity=anchor_entity,
                            anchor_component_id=node_to_component.get(anchor_entity, -1),
                            anchor_in_giant_component=node_to_component.get(anchor_entity) == giant_component_id,
                            candidate_triple_h=candidate_h,
                            candidate_triple_r=rm,
                            candidate_triple_t=candidate_t,
                            graph_context_h=selected_payload.get("graph_context_h"),
                            graph_context_r=rg,
                            graph_context_t=selected_payload.get("graph_context_t"),
                            wdqs_query_template=str(selected_payload.get("wdqs_query_template")),
                            wdqs_query_hash=str(selected_payload.get("wdqs_query_hash")),
                            type_filter_enabled=type_filter_enabled,
                            type_filter_passed=selected_payload.get("type_filter_passed"),
                            accepted_at_unix=time.time(),
                        )
                        accepted_writer.write(asdict(accepted))
                        if args.checkpoint_every_accept:
                            persist_checkpoint(force=True)

                if accepted_per_missing_relation[rm] == accepted_before_relation:
                    rejected = RejectRecord(
                        missing_relation=rm,
                        realized_relation="",
                        orientation="",
                        candidate_triple_h=None,
                        candidate_triple_r=rm,
                        candidate_triple_t=None,
                        reason="no_candidate_survived_filters",
                        details={"candidate_pair_count": len(candidates), "pass_index": pass_index},
                    )
                    rejected_writer.write(asdict(rejected))
                    rejected_candidates_count += 1

                processed_missing_relations.add(rm)
                processed_since_checkpoint += 1
                persist_checkpoint()

            persist_checkpoint(force=True)
            if pass_new_triples <= 0:
                break
    finally:
        accepted_writer.close()
        rejected_writer.close()
        pair_writer.close()
        new_triples_writer.close()
        collected_writer.close()
        unused_writer.close()

    # Compose final repaired graph file from original + append-only added triples.
    with repaired_graph_path.open("w", encoding="utf-8") as out:
        for row in iter_jsonl(graph_path):
            out.write(
                json.dumps({"h": row["h"], "r": row["r"], "t": row["t"]}, ensure_ascii=False)
                + "\n"
            )
        if new_triples_path.exists():
            for row in iter_jsonl(new_triples_path):
                out.write(
                    json.dumps({"h": row["h"], "r": row["r"], "t": row["t"]}, ensure_ascii=False)
                    + "\n"
                )

    summary = {
        "graph_input_triples": graph_input_triples_count,
        "graph_output_triples": graph_input_triples_count + new_triples_added_count,
        "new_triples_added": new_triples_added_count,
        "missing_relations_requested": len(missing_relations),
        "missing_relations_repaired": len(realized_missing_relations),
        "repaired_relations": sorted(realized_missing_relations),
        "accepted_repairs": accepted_repairs_count,
        "rejected_candidates": rejected_candidates_count,
        "type_filter_enabled": type_filter_enabled,
        "dry_run": args.dry_run,
        "priority_field": args.priority_field,
        "top_pair_candidates_per_missing_relation": args.top_pair_candidates_per_missing_relation,
        "max_accepts_per_missing_relation_default": args.max_accepts_per_missing_relation,
        "max_accepts_per_anchor": args.max_accepts_per_anchor,
        "allocation_results_json": str(allocation_results_path) if allocation_results_path else None,
        "allocation_eta_field": args.allocation_eta_field,
        "allocation_eta_rounding": args.allocation_eta_rounding,
        "allocation_relations_with_caps": len(eta_caps),
        "initial_realized_relations": initial_realized_relations_count,
        "final_realized_relations": len(realized_relations),
        "repair_passes_completed": passes_completed,
        "checkpoint_path": str(checkpoint_path),
        "resume": resume,
        "outputs": {
            "repaired_graph_jsonl": str(repaired_graph_path),
            "new_triples_added_jsonl": str(new_triples_path),
            "accepted_repairs_jsonl": str(accepted_log_path),
            "rejected_repairs_jsonl": str(rejected_log_path),
            "pair_candidates_jsonl": str(pair_candidates_path),
            "collected_candidates_all_jsonl": str(collected_candidates_path),
            "collected_candidates_unused_jsonl": str(unused_candidates_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    p = argparse.ArgumentParser(
        description="Repair missing allocated relations using directed 2-hop relation motifs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--graph_jsonl", required=True, help="Input graph triples JSONL.")
    p.add_argument("--hop_support_jsonl", required=True, help="Directed hop-support JSONL.")
    p.add_argument("--priorities", required=True, help="Priority file for missing relations (json/jsonl/csv).")
    p.add_argument("--missing_relations", required=True, help="Missing relation list (txt/json/jsonl/csv).")
    p.add_argument(
        "--realized_relations",
        default="",
        help="Optional realized relation whitelist. If omitted, all graph relations are treated as realized candidates.",
    )
    p.add_argument(
        "--priority_field",
        default="eta_integer",
        help="Priority field to use from the priorities file, for example eta_integer or eta_expected.",
    )
    p.add_argument(
        "--constraints_json",
        default="",
        help="Optional relation constraint file with valid subject/object types.",
    )
    p.add_argument(
        "--entity_types_json",
        default="",
        help="Optional entity type file used by the type filter.",
    )
    p.add_argument(
        "--enable_type_filter",
        action="store_true",
        help="Enable the type filter if both constraints and entity types are available.",
    )
    p.add_argument(
        "--allow_self_loops",
        action="store_true",
        help="Allow repaired self-loops. By default they are blocked.",
    )
    p.add_argument(
        "--top_pair_candidates_per_missing_relation",
        type=int,
        default=3,
        help="How many ranked pair-orientation candidates to test per missing relation.",
    )
    p.add_argument(
        "--max_reconsider_passes",
        type=int,
        default=0,
        help="Maximum full repair passes. 0 means run until convergence (no new triples).",
    )
    p.add_argument(
        "--max_accepts_per_missing_relation",
        type=int,
        default=1,
        help="Default maximum accepted repaired triples per missing relation (used when allocation cap is unavailable).",
    )
    p.add_argument(
        "--max_accepts_per_anchor",
        type=int,
        default=2,
        help="Maximum accepted repairs that may reuse the same graph anchor entity.",
    )
    p.add_argument(
        "--values_chunk_size",
        type=int,
        default=50,
        help="Chunk size for VALUES clauses.",
    )
    p.add_argument(
        "--allocation_results_json",
        default="",
        help="Optional allocation results JSON. When provided, per-relation cap uses max eta (per relation) from this file.",
    )
    p.add_argument(
        "--allocation_eta_field",
        default="eta_expected",
        help="Eta field inside allocation rows used to derive per-relation cap.",
    )
    p.add_argument(
        "--allocation_eta_rounding",
        choices=("floor", "ceil", "round"),
        default="floor",
        help="How to convert eta values to integer acceptance caps.",
    )
    p.add_argument(
        "--query_limit",
        type=int,
        default=200,
        help="LIMIT for each SPARQL query chunk.",
    )
    p.add_argument(
        "--endpoint",
        default="https://query.wikidata.org/sparql",
        help="SPARQL endpoint URL.",
    )
    p.add_argument(
        "--user_agent",
        required=True,
        help="User-Agent header for WDQS requests.",
    )
    p.add_argument(
        "--timeout_sec",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds.",
    )
    p.add_argument(
        "--max_retries",
        type=int,
        default=2,
        help="Maximum retries per WDQS request.",
    )
    p.add_argument(
        "--min_delay_sec",
        type=float,
        default=1.0,
        help="Minimum delay between WDQS requests.",
    )
    p.add_argument(
        "--giant_component_bonus",
        type=float,
        default=1.25,
        help="Multiplicative bonus for anchors in the giant component.",
    )
    p.add_argument(
        "--type_bonus",
        type=float,
        default=1.10,
        help="Multiplicative bonus when the optional type filter passes.",
    )
    p.add_argument("--out_dir", required=True, help="Output directory.")
    p.add_argument(
        "--checkpoint_path",
        default="",
        help="Checkpoint JSON path. Defaults to <out_dir>/repair_checkpoint.json.",
    )
    p.add_argument(
        "--checkpoint_every",
        type=int,
        default=1,
        help="Persist checkpoint after this many processed missing relations.",
    )
    p.add_argument(
        "--checkpoint_every_accept",
        action="store_true",
        help="Persist checkpoint after every accepted triple for maximum crash safety.",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint and append-only outputs in out_dir.",
    )
    p.add_argument("--random_seed", type=int, default=13, help="Random seed.")
    p.add_argument(
        "--dry_run",
        action="store_true",
        help="Build candidates and queries without executing WDQS requests.",
    )
    p.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    summary = run_repair(args)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
