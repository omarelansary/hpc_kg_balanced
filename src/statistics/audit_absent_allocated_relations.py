#!/usr/bin/env python3
"""
Audit absent-but-allocated relations using sampled WDQS evidence.

This script targets relations that are:
1) positively allocated (`eta_integer > 0`),
2) absent from the final graph (`actual_count == 0`), and
3) flagged as `expected_positive_but_absent_in_graph`.

For each target relation, it samples candidate triples from WDQS and classifies
the relation into one of:
- NO_CANDIDATES_GLOBAL
- CANDIDATES_EXIST_BUT_TYPE_FAIL
- TYPED_EXIST_BUT_DO_NOT_TOUCH_GRAPH
- TOUCHING_GRAPH_EXIST_BUT_NOT_REALIZED
- UNKNOWN_OR_QUERY_FAILED

What this audit can conclude
----------------------------
- It can provide sampled evidence that a relation appears globally, survives
  typed filtering (when type metadata is available), and/or touches graph nodes.
- It can highlight relations that were likely realizable in principle but were
  still absent in the extracted graph.

What this audit cannot conclude
-------------------------------
- It is not exhaustive by default. All WDQS checks are bounded by LIMIT.
- A sampled count of zero does not prove global non-existence.
- Type-filter conclusions are unavailable when valid type metadata is missing.
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
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple


SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
DEFAULT_USER_AGENT = "kg-absent-allocation-audit/1.0 (mailto:replace-me@example.com)"

SCRIPT_VERSION = "audit-absent-allocated-relations-1.0"
STATE_SCHEMA_VERSION = 1

EXPECTED_FLAG = "expected_positive_but_absent_in_graph"

BUCKET_NO_CANDIDATES_GLOBAL = "NO_CANDIDATES_GLOBAL"
BUCKET_CANDIDATES_EXIST_BUT_TYPE_FAIL = "CANDIDATES_EXIST_BUT_TYPE_FAIL"
BUCKET_TYPED_EXIST_BUT_DO_NOT_TOUCH_GRAPH = "TYPED_EXIST_BUT_DO_NOT_TOUCH_GRAPH"
BUCKET_TOUCHING_GRAPH_EXIST_BUT_NOT_REALIZED = "TOUCHING_GRAPH_EXIST_BUT_NOT_REALIZED"
BUCKET_UNKNOWN_OR_QUERY_FAILED = "UNKNOWN_OR_QUERY_FAILED"

ALL_BUCKETS = [
    BUCKET_NO_CANDIDATES_GLOBAL,
    BUCKET_CANDIDATES_EXIST_BUT_TYPE_FAIL,
    BUCKET_TYPED_EXIST_BUT_DO_NOT_TOUCH_GRAPH,
    BUCKET_TOUCHING_GRAPH_EXIST_BUT_NOT_REALIZED,
    BUCKET_UNKNOWN_OR_QUERY_FAILED,
]

MANIFEST_FILENAME = "manifest.json"
STATE_FILENAME = "state.json"
EVENTS_FILENAME = "events.jsonl"
REPORT_FILENAME = "report.json"

DEFAULT_SAMPLE_PREVIEW_LIMIT = 30
DEFAULT_MAX_TYPE_VALUES = 12


CandidatePair = Tuple[str, str]


@dataclass(frozen=True)
class RunPaths:
    run_dir: Path
    manifest: Path
    state: Path
    events: Path
    report: Path


@dataclass
class QueryOutcome:
    query_kind: str
    candidates: List[CandidatePair]
    error: Optional[str]
    elapsed_ms: int


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


def emit_event(paths: RunPaths, event_type: str, **payload: Any) -> None:
    row: Dict[str, Any] = {"timestamp": utc_now_iso(), "event_type": event_type}
    row.update(payload)
    append_jsonl(paths.events, row)


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


def to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return int(round(value))
    if isinstance(value, str):
        x = value.strip()
        if not x:
            return None
        try:
            return int(x)
        except ValueError:
            try:
                return int(round(float(x)))
            except ValueError:
                return None
    return None


def normalize_flags(flags: Any) -> List[str]:
    if flags is None:
        return []
    if isinstance(flags, list):
        return [str(x).strip() for x in flags if str(x).strip()]
    if isinstance(flags, str):
        raw = flags.replace("|", ",")
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [str(flags).strip()] if str(flags).strip() else []


def is_qid(value: str) -> bool:
    return isinstance(value, str) and len(value) > 1 and value[0] == "Q" and value[1:].isdigit()


def is_pid(value: str) -> bool:
    return isinstance(value, str) and len(value) > 1 and value[0] == "P" and value[1:].isdigit()


def sanitize_qid_list(values: Any, limit: int = 10_000) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    if not isinstance(values, list):
        return out
    for item in values:
        x = str(item).strip()
        if not is_qid(x) or x in seen:
            continue
        out.append(x)
        seen.add(x)
        if len(out) >= max(1, int(limit)):
            break
    return out


def uri_to_qid(uri: str) -> Optional[str]:
    prefix = "http://www.wikidata.org/entity/"
    if not isinstance(uri, str) or not uri.startswith(prefix):
        return None
    qid = uri[len(prefix) :]
    if is_qid(qid):
        return qid
    return None


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


def normalize_json_records(obj: Any) -> List[dict]:
    if isinstance(obj, list):
        rows: List[dict] = []
        for i, item in enumerate(obj):
            if not isinstance(item, dict):
                raise ValueError(f"Expected list of objects, item {i} is {type(item).__name__}")
            rows.append(item)
        return rows

    if isinstance(obj, dict):
        if "rows" in obj and isinstance(obj["rows"], list):
            rows = obj["rows"]
            if not all(isinstance(x, dict) for x in rows):
                raise ValueError("Expected all rows in 'rows' to be objects.")
            return list(rows)

        for key in (
            "records",
            "items",
            "results",
            "relations",
            "allocations",
            "cards",
            "data",
            "triples",
            "triples_out",
        ):
            value = obj.get(key)
            if isinstance(value, list) and all(isinstance(x, dict) for x in value):
                return list(value)

        if "relation" in obj:
            return [obj]

        if obj and all(isinstance(v, dict) for v in obj.values()):
            return list(obj.values())

    raise ValueError("Could not normalize JSON into a list of records.")


def load_json_or_jsonl_records(path: Path) -> List[dict]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return list(_iter_jsonl(path))

    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return []

    try:
        obj = json.loads(raw_text)
        return normalize_json_records(obj)
    except json.JSONDecodeError:
        return list(_iter_jsonl(path))


def load_graph_nodes(path: Path, head_field: str, tail_field: str) -> Set[str]:
    records = load_json_or_jsonl_records(path)
    nodes: Set[str] = set()
    for idx, obj in enumerate(records, start=1):
        h = obj.get(head_field)
        t = obj.get(tail_field)
        if h is None or t is None:
            raise ValueError(
                f"Triple record #{idx} is missing required fields '{head_field}' or '{tail_field}'. "
                f"Keys: {sorted(obj.keys())}"
            )
        nodes.add(str(h))
        nodes.add(str(t))
    return nodes


def load_relation_audit_rows(path: Path) -> List[dict]:
    records = load_json_or_jsonl_records(path)
    if not records:
        return []
    rows: List[dict] = []
    for idx, row in enumerate(records, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Relation audit row #{idx} must be an object.")
        rows.append(row)
    return rows


def extract_target_relations(rows: Iterable[dict]) -> Tuple[Dict[str, dict], List[str]]:
    target_by_relation: Dict[str, dict] = {}
    warnings: List[str] = []

    for row in rows:
        relation_raw = row.get("relation")
        if relation_raw is None:
            continue
        relation = str(relation_raw).strip()
        if not relation:
            continue

        eta_integer = to_int_or_none(row.get("eta_integer"))
        actual_count = to_int_or_none(row.get("actual_count"))
        flags = normalize_flags(row.get("flags"))

        if eta_integer is None or eta_integer <= 0:
            continue
        if actual_count is None or actual_count != 0:
            continue
        if EXPECTED_FLAG not in flags:
            continue

        normalized = {
            "relation": relation,
            "pattern": str(row.get("pattern") or "UNKNOWN"),
            "eta_integer": int(eta_integer),
            "actual_count": int(actual_count),
            "relation_dom_rng_class": str(row.get("relation_dom_rng_class") or "UNKNOWN"),
            "flags": flags,
        }

        prev = target_by_relation.get(relation)
        if prev is None:
            target_by_relation[relation] = normalized
            continue

        warnings.append(
            f"Duplicate target relation {relation} found in audit rows. Keeping entry with larger eta_integer."
        )
        if int(normalized["eta_integer"]) > int(prev["eta_integer"]):
            target_by_relation[relation] = normalized

    return target_by_relation, warnings


def load_valid_types_map(path: Optional[Path]) -> Tuple[Dict[str, Dict[str, List[str]]], bool]:
    if path is None:
        return {}, False

    data = _load_json(path)
    out: Dict[str, Dict[str, List[str]]] = {}

    def add_entry(relation: str, subj: Any, obj: Any) -> None:
        pid = str(relation).strip()
        if not is_pid(pid):
            return
        subj_list = sanitize_qid_list(subj)
        obj_list = sanitize_qid_list(obj)
        out[pid] = {
            "valid_subject_type_ids": subj_list,
            "valid_object_type_ids": obj_list,
        }

    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            if is_pid(str(key).strip()):
                add_entry(
                    relation=str(key).strip(),
                    subj=value.get("valid_subject_type_ids", []),
                    obj=value.get("valid_object_type_ids", []),
                )

        if not out:
            for key in ("rows", "records", "items", "relations", "data"):
                value = data.get(key)
                if not isinstance(value, list):
                    continue
                for rec in value:
                    if not isinstance(rec, dict):
                        continue
                    rel = rec.get("relation") or rec.get("property_id") or rec.get("property")
                    if rel is None:
                        continue
                    add_entry(
                        relation=str(rel),
                        subj=rec.get("valid_subject_type_ids", []),
                        obj=rec.get("valid_object_type_ids", []),
                    )

    elif isinstance(data, list):
        for rec in data:
            if not isinstance(rec, dict):
                continue
            rel = rec.get("relation") or rec.get("property_id") or rec.get("property")
            if rel is None:
                continue
            add_entry(
                relation=str(rel),
                subj=rec.get("valid_subject_type_ids", []),
                obj=rec.get("valid_object_type_ids", []),
            )
    else:
        raise ValueError("valid_types_json must be a JSON object or list.")

    return out, True


def build_query_global(relation: str, limit: int) -> str:
    return f"""
    SELECT ?h ?t WHERE {{
      ?h wdt:{relation} ?t .
      FILTER(STRSTARTS(STR(?h), "http://www.wikidata.org/entity/Q"))
      FILTER(STRSTARTS(STR(?t), "http://www.wikidata.org/entity/Q"))
    }}
    LIMIT {int(limit)}
    """


def build_query_typed(relation: str, limit: int, subject_types: List[str], object_types: List[str]) -> str:
    typed_clauses: List[str] = []
    if subject_types:
        subj_values = " ".join(f"wd:{x}" for x in subject_types)
        typed_clauses.append(
            f"""
            VALUES ?scls {{ {subj_values} }}
            FILTER EXISTS {{ ?h wdt:P31/wdt:P279* ?scls . }}
            """
        )
    if object_types:
        obj_values = " ".join(f"wd:{x}" for x in object_types)
        typed_clauses.append(
            f"""
            VALUES ?ocls {{ {obj_values} }}
            FILTER EXISTS {{ ?t wdt:P31/wdt:P279* ?ocls . }}
            """
        )
    typed_filter = "\n".join(typed_clauses)
    return f"""
    SELECT ?h ?t WHERE {{
      ?h wdt:{relation} ?t .
      FILTER(STRSTARTS(STR(?h), "http://www.wikidata.org/entity/Q"))
      FILTER(STRSTARTS(STR(?t), "http://www.wikidata.org/entity/Q"))
      {typed_filter}
    }}
    LIMIT {int(limit)}
    """


def run_sparql_json(query: str, user_agent: str, timeout_sec: int) -> dict:
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(
        f"{SPARQL_ENDPOINT}?{params}",
        headers={"Accept": "application/sparql-results+json", "User-Agent": user_agent},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=max(1, int(timeout_sec))) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def extract_candidate_pairs(result: dict) -> List[CandidatePair]:
    try:
        bindings = result["results"]["bindings"]
    except KeyError as exc:
        raise ValueError("Unexpected SPARQL response shape (missing results.bindings).") from exc

    out: List[CandidatePair] = []
    seen: Set[CandidatePair] = set()
    for row in bindings:
        if not isinstance(row, dict):
            continue
        h_uri = row.get("h", {}).get("value")
        t_uri = row.get("t", {}).get("value")
        h = uri_to_qid(h_uri) if isinstance(h_uri, str) else None
        t = uri_to_qid(t_uri) if isinstance(t_uri, str) else None
        if h is None or t is None:
            continue
        pair = (h, t)
        if pair in seen:
            continue
        seen.add(pair)
        out.append(pair)
    return out


def query_relation_sample(
    *,
    state: Dict[str, Any],
    paths: RunPaths,
    relation: str,
    query_kind: str,
    query: str,
    query_limit: int,
    timeout_sec: int,
    user_agent: str,
) -> QueryOutcome:
    counters = state["counters"]
    counters["wdqs_queries_attempted"] = int(counters.get("wdqs_queries_attempted", 0)) + 1
    emit_event(
        paths,
        "wdqs_query_started",
        relation=relation,
        query_kind=query_kind,
        query_limit=int(query_limit),
        timeout_sec=int(timeout_sec),
    )

    t0 = time.perf_counter()
    try:
        result = run_sparql_json(query=query, user_agent=user_agent, timeout_sec=timeout_sec)
        candidates = extract_candidate_pairs(result)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        counters["wdqs_queries_failed"] = int(counters.get("wdqs_queries_failed", 0)) + 1
        emit_event(
            paths,
            "wdqs_query_failed",
            relation=relation,
            query_kind=query_kind,
            elapsed_ms=elapsed_ms,
            error=f"{type(exc).__name__}: {exc}",
        )
        return QueryOutcome(
            query_kind=query_kind,
            candidates=[],
            error=f"{type(exc).__name__}: {exc}",
            elapsed_ms=elapsed_ms,
        )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    counters["wdqs_queries_succeeded"] = int(counters.get("wdqs_queries_succeeded", 0)) + 1
    emit_event(
        paths,
        "wdqs_query_finished",
        relation=relation,
        query_kind=query_kind,
        elapsed_ms=elapsed_ms,
        result_count=len(candidates),
    )
    return QueryOutcome(query_kind=query_kind, candidates=candidates, error=None, elapsed_ms=elapsed_ms)


def count_touching_graph(candidates: Iterable[CandidatePair], graph_nodes: Set[str]) -> int:
    return sum(1 for h, t in candidates if h in graph_nodes or t in graph_nodes)


def sample_preview(candidates: Iterable[CandidatePair], max_items: int = DEFAULT_SAMPLE_PREVIEW_LIMIT) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for h, t in candidates:
        out.append({"h": h, "t": t})
        if len(out) >= max(1, int(max_items)):
            break
    return out


def summarize_note_lines(lines: List[str]) -> str:
    clean = [line.strip() for line in lines if line and line.strip()]
    return " ".join(clean)


def classify_relation(
    *,
    relation_row: dict,
    graph_nodes: Set[str],
    valid_types_map: Dict[str, Dict[str, List[str]]],
    valid_types_supplied: bool,
    args: argparse.Namespace,
    paths: RunPaths,
    state: Dict[str, Any],
) -> Tuple[dict, dict]:
    relation = str(relation_row["relation"])
    pattern = str(relation_row.get("pattern") or "UNKNOWN")
    eta_integer = int(to_int_or_none(relation_row.get("eta_integer")) or 0)
    actual_count = int(to_int_or_none(relation_row.get("actual_count")) or 0)
    relation_dom_rng_class = str(relation_row.get("relation_dom_rng_class") or "UNKNOWN")

    notes: List[str] = [
        f"Sample-based audit using WDQS LIMIT {int(args.query_limit)} per query; results are not exhaustive.",
    ]

    query_failed = False
    global_candidates: List[CandidatePair] = []
    typed_candidates: Optional[List[CandidatePair]] = None
    global_error: Optional[str] = None
    typed_error: Optional[str] = None

    if not is_pid(relation):
        query_failed = True
        bucket = BUCKET_UNKNOWN_OR_QUERY_FAILED
        notes.append(f"Relation ID is not a valid Wikidata property ID: {relation}")
        result_row = {
            "relation": relation,
            "pattern": pattern,
            "eta_integer": eta_integer,
            "actual_count": actual_count,
            "relation_dom_rng_class": relation_dom_rng_class,
            "bucket": bucket,
            "global_candidate_count": 0,
            "typed_candidate_count": None,
            "touching_graph_candidate_count": 0,
            "notes": summarize_note_lines(notes),
            "query_failed": True,
        }
        debug = {
            "relation": relation,
            "type_check_available": False,
            "global_query_error": "invalid_pid",
            "typed_query_error": None,
            "global_sample": [],
            "typed_sample": None,
            "touching_graph_sample": [],
            "touching_source": "none",
        }
        return result_row, debug

    global_query = build_query_global(relation=relation, limit=int(args.query_limit))
    global_outcome = query_relation_sample(
        state=state,
        paths=paths,
        relation=relation,
        query_kind="global",
        query=global_query,
        query_limit=int(args.query_limit),
        timeout_sec=int(args.timeout_sec),
        user_agent=str(args.user_agent),
    )
    if global_outcome.error is not None:
        query_failed = True
        global_error = global_outcome.error
    global_candidates = list(global_outcome.candidates)
    global_count = len(global_candidates)

    type_info = valid_types_map.get(relation)
    subject_types: List[str] = []
    object_types: List[str] = []
    type_check_available = False

    if type_info is not None:
        subject_types = sanitize_qid_list(type_info.get("valid_subject_type_ids", []), limit=DEFAULT_MAX_TYPE_VALUES)
        object_types = sanitize_qid_list(type_info.get("valid_object_type_ids", []), limit=DEFAULT_MAX_TYPE_VALUES)
        if subject_types or object_types:
            type_check_available = True
        else:
            notes.append(
                "valid_types_json contains this relation but no usable subject/object type IDs; typed check unavailable."
            )
    else:
        if valid_types_supplied:
            notes.append("No per-relation type metadata found in valid_types_json; typed check unavailable.")
        else:
            notes.append("valid_types_json not provided; typed check unavailable.")

    bucket = BUCKET_UNKNOWN_OR_QUERY_FAILED
    touching_source = "none"
    touching_sample: List[CandidatePair] = []
    touching_count = 0
    typed_count: Optional[int] = None

    if query_failed:
        bucket = BUCKET_UNKNOWN_OR_QUERY_FAILED
        notes.append("Global WDQS query failed; relation could not be classified reliably.")
    elif global_count <= 0:
        bucket = BUCKET_NO_CANDIDATES_GLOBAL
        notes.append(
            "No item-to-item candidates were observed in sampled global query. "
            "Because this is sample-bounded, true global absence is not guaranteed."
        )
    else:
        if global_count >= int(args.query_limit):
            notes.append(
                "Global query returned the limit; more candidates may exist beyond sampled rows."
            )

        if type_check_available:
            typed_query = build_query_typed(
                relation=relation,
                limit=int(args.query_limit),
                subject_types=subject_types,
                object_types=object_types,
            )
            typed_outcome = query_relation_sample(
                state=state,
                paths=paths,
                relation=relation,
                query_kind="typed",
                query=typed_query,
                query_limit=int(args.query_limit),
                timeout_sec=int(args.timeout_sec),
                user_agent=str(args.user_agent),
            )
            if typed_outcome.error is not None:
                query_failed = True
                typed_error = typed_outcome.error
                bucket = BUCKET_UNKNOWN_OR_QUERY_FAILED
                notes.append("Typed WDQS query failed; typed-vs-untyped classification is inconclusive.")
            else:
                typed_candidates = list(typed_outcome.candidates)
                typed_count = len(typed_candidates)

                if typed_count >= int(args.query_limit):
                    notes.append(
                        "Typed query returned the limit; more typed candidates may exist beyond sampled rows."
                    )

                if typed_count <= 0:
                    bucket = BUCKET_CANDIDATES_EXIST_BUT_TYPE_FAIL
                    notes.append(
                        "Global sampled candidates exist, but sampled typed query returned zero candidates."
                    )
                else:
                    touching_source = "typed"
                    touching_sample = [pair for pair in typed_candidates if pair[0] in graph_nodes or pair[1] in graph_nodes]
                    touching_count = len(touching_sample)
                    if touching_count <= 0:
                        bucket = BUCKET_TYPED_EXIST_BUT_DO_NOT_TOUCH_GRAPH
                        notes.append(
                            "Typed sampled candidates exist, but none touched the final-graph node set."
                        )
                    else:
                        bucket = BUCKET_TOUCHING_GRAPH_EXIST_BUT_NOT_REALIZED
                        notes.append(
                            "Sampled candidates that satisfy available checks touch graph nodes, so the relation appears realizable in principle."
                        )
        else:
            touching_source = "fallback_global"
            touching_sample = [pair for pair in global_candidates if pair[0] in graph_nodes or pair[1] in graph_nodes]
            touching_count = len(touching_sample)
            if touching_count > 0:
                bucket = BUCKET_TOUCHING_GRAPH_EXIST_BUT_NOT_REALIZED
                notes.append(
                    "Using fallback (untyped) sampling, candidates touching graph nodes were observed."
                )
            else:
                bucket = BUCKET_UNKNOWN_OR_QUERY_FAILED
                notes.append(
                    "Typed checks are unavailable and sampled fallback candidates did not touch graph nodes; cannot disambiguate failure mode."
                )

    if touching_count <= 0 and touching_source == "typed":
        touching_count = 0
    elif touching_count <= 0 and touching_source == "fallback_global":
        touching_count = 0

    result_row = {
        "relation": relation,
        "pattern": pattern,
        "eta_integer": eta_integer,
        "actual_count": actual_count,
        "relation_dom_rng_class": relation_dom_rng_class,
        "bucket": bucket,
        "global_candidate_count": global_count,
        "typed_candidate_count": typed_count,
        "touching_graph_candidate_count": touching_count,
        "notes": summarize_note_lines(notes),
        "query_failed": bool(query_failed),
    }

    debug = {
        "relation": relation,
        "type_check_available": bool(type_check_available),
        "subject_type_ids_used": subject_types[:DEFAULT_MAX_TYPE_VALUES] if type_check_available else [],
        "object_type_ids_used": object_types[:DEFAULT_MAX_TYPE_VALUES] if type_check_available else [],
        "global_query_error": global_error,
        "typed_query_error": typed_error,
        "global_sample": sample_preview(global_candidates),
        "typed_sample": sample_preview(typed_candidates or []) if typed_candidates is not None else None,
        "touching_graph_sample": sample_preview(touching_sample),
        "touching_source": touching_source,
    }
    return result_row, debug


def make_run_paths(output_dir: Path) -> RunPaths:
    run_dir = output_dir.resolve()
    return RunPaths(
        run_dir=run_dir,
        manifest=run_dir / MANIFEST_FILENAME,
        state=run_dir / STATE_FILENAME,
        events=run_dir / EVENTS_FILENAME,
        report=run_dir / REPORT_FILENAME,
    )


def build_manifest(args: argparse.Namespace, paths: RunPaths) -> Dict[str, Any]:
    return {
        "script_version": SCRIPT_VERSION,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "output_dir": str(paths.run_dir),
        "hostname": socket.gethostname(),
        "python_version": sys.version,
        "inputs": {
            "graph_triples": str(args.graph_triples.resolve()),
            "relation_audit_json": str(args.relation_audit_json.resolve()),
            "valid_types_json": path_or_none(args.valid_types_json),
        },
        "cli_args": namespace_to_jsonable_dict(args),
    }


def initial_state(target_relations: List[str], warnings: List[str]) -> Dict[str, Any]:
    bucket_counts = {bucket: 0 for bucket in ALL_BUCKETS}
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "script_version": SCRIPT_VERSION,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "completed": False,
        "successful": False,
        "run_finished_at": None,
        "resumptions": 0,
        "target_total": len(target_relations),
        "target_relations": list(target_relations),
        "processed_relations": [],
        "relation_results": {},
        "relation_debug": {},
        "counters": {
            "relations_processed": 0,
            "wdqs_queries_attempted": 0,
            "wdqs_queries_succeeded": 0,
            "wdqs_queries_failed": 0,
            "bucket_counts": bucket_counts,
        },
        "warnings": list(warnings),
        "notes": [
            "All candidate checks are sample-based (LIMIT-bounded WDQS queries). "
            "Zero sampled candidates do not prove absolute absence."
        ],
        "last_error": None,
    }


def ensure_state_defaults(state: Dict[str, Any]) -> None:
    state.setdefault("processed_relations", [])
    state.setdefault("relation_results", {})
    state.setdefault("relation_debug", {})
    state.setdefault("warnings", [])
    state.setdefault("notes", [])
    state.setdefault("last_error", None)
    state.setdefault("target_relations", [])
    state.setdefault("target_total", len(state.get("target_relations", [])))
    state.setdefault("completed", False)
    state.setdefault("successful", False)
    state.setdefault("run_finished_at", None)
    state.setdefault("resumptions", 0)

    counters = state.setdefault("counters", {})
    counters.setdefault("relations_processed", 0)
    counters.setdefault("wdqs_queries_attempted", 0)
    counters.setdefault("wdqs_queries_succeeded", 0)
    counters.setdefault("wdqs_queries_failed", 0)
    counters.setdefault("bucket_counts", {})
    for bucket in ALL_BUCKETS:
        counters["bucket_counts"].setdefault(bucket, 0)

    dedup_processed: List[str] = []
    seen: Set[str] = set()
    for relation in state.get("processed_relations", []):
        rel = str(relation)
        if rel in seen:
            continue
        dedup_processed.append(rel)
        seen.add(rel)
    state["processed_relations"] = dedup_processed

    # Rebuild consistent counters from saved results.
    bucket_counts = Counter()
    for rel, row in state.get("relation_results", {}).items():
        _ = rel
        if isinstance(row, dict):
            bucket = str(row.get("bucket") or BUCKET_UNKNOWN_OR_QUERY_FAILED)
            bucket_counts[bucket] += 1
    for bucket in ALL_BUCKETS:
        counters["bucket_counts"][bucket] = int(bucket_counts.get(bucket, 0))
    counters["relations_processed"] = len(state["relation_results"])


def counter_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    counters = state.get("counters", {})
    return {
        "relations_processed": int(counters.get("relations_processed", 0)),
        "target_total": int(state.get("target_total", 0)),
        "wdqs_queries_attempted": int(counters.get("wdqs_queries_attempted", 0)),
        "wdqs_queries_succeeded": int(counters.get("wdqs_queries_succeeded", 0)),
        "wdqs_queries_failed": int(counters.get("wdqs_queries_failed", 0)),
        "bucket_counts": dict(counters.get("bucket_counts", {})),
    }


def checkpoint_state(paths: RunPaths, state: Dict[str, Any], reason: str, relation: Optional[str] = None) -> None:
    state["updated_at"] = utc_now_iso()
    atomic_write_json(paths.state, state)
    emit_event(
        paths,
        "checkpoint_written",
        reason=reason,
        relation=relation,
        counts_snapshot=counter_snapshot(state),
    )


def assert_new_run_dir(paths: RunPaths) -> None:
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
    if state.get("completed"):
        raise ValueError("Run is already completed; refusing --resume.")

    cli_args = manifest.get("cli_args")
    if not isinstance(cli_args, dict):
        raise ValueError("manifest.json is missing cli_args; cannot validate resume compatibility.")

    now_args = namespace_to_jsonable_dict(args)
    must_match = [
        "graph_triples",
        "relation_audit_json",
        "valid_types_json",
        "head_field",
        "rel_field",
        "tail_field",
        "query_limit",
        "timeout_sec",
        "user_agent",
    ]
    for key in must_match:
        if cli_args.get(key) != now_args.get(key):
            raise ValueError(
                f"Resume incompatible for argument '{key}': previous={cli_args.get(key)!r}, now={now_args.get(key)!r}"
            )


def load_or_init_run(
    *,
    args: argparse.Namespace,
    paths: RunPaths,
    target_relations: List[str],
    warnings: List[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if args.resume:
        if not paths.run_dir.exists():
            raise ValueError(f"Cannot resume: output_dir does not exist: {paths.run_dir}")
        if not paths.manifest.exists() or not paths.state.exists():
            raise ValueError("Cannot resume: manifest.json or state.json is missing.")
        manifest = _load_json(paths.manifest)
        state = _load_json(paths.state)
        validate_resume_compatibility(args=args, manifest=manifest, state=state)
        ensure_state_defaults(state)

        prior_targets = [str(x) for x in state.get("target_relations", [])]
        if prior_targets != target_relations:
            raise ValueError(
                "Cannot resume: target relation set/order changed since initial run. "
                "Use a fresh output_dir for a new run."
            )

        state["resumptions"] = int(state.get("resumptions", 0)) + 1
        if warnings:
            state["warnings"].extend(warnings)
        emit_event(paths, "run_started", resume=True, resumptions=state["resumptions"])
        checkpoint_state(paths, state, reason="resume_loaded")
        log(f"Resumed run in {paths.run_dir}")
        return manifest, state

    assert_new_run_dir(paths)
    manifest = build_manifest(args=args, paths=paths)
    state = initial_state(target_relations=target_relations, warnings=warnings)
    atomic_write_json(paths.manifest, manifest)
    atomic_write_json(paths.state, state)
    emit_event(paths, "run_started", resume=False, resumptions=0)
    checkpoint_state(paths, state, reason="run_initialized")
    log(f"Started new run in {paths.run_dir}")
    return manifest, state


def build_report(manifest: Dict[str, Any], state: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    rows: List[dict] = []
    for relation in sorted(state.get("relation_results", {}).keys()):
        row = state["relation_results"][relation]
        if isinstance(row, dict):
            rows.append(row)

    bucket_counts = Counter(str(row.get("bucket") or BUCKET_UNKNOWN_OR_QUERY_FAILED) for row in rows)
    pattern_counts = Counter(str(row.get("pattern") or "UNKNOWN") for row in rows)
    dom_rng_counts = Counter(str(row.get("relation_dom_rng_class") or "UNKNOWN") for row in rows)

    return {
        "script_version": SCRIPT_VERSION,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "completed": bool(state.get("completed", False)),
        "successful": bool(state.get("successful", False)),
        "run_finished_at": state.get("run_finished_at"),
        "resumptions": int(state.get("resumptions", 0)),
        "inputs": manifest.get("inputs", {}),
        "sampling": {
            "sample_based": True,
            "query_limit": int(args.query_limit),
            "timeout_sec": int(args.timeout_sec),
            "note": (
                "All WDQS candidate counts are LIMIT-bounded samples. "
                "Sampled presence is evidence; sampled absence is not a formal proof."
            ),
        },
        "total_absent_allocated_relations": int(state.get("target_total", 0)),
        "processed_absent_allocated_relations": len(rows),
        "counts_by_failure_bucket": {bucket: int(bucket_counts.get(bucket, 0)) for bucket in ALL_BUCKETS},
        "counts_by_pattern": dict(pattern_counts),
        "counts_by_relation_dom_rng_class": dict(dom_rng_counts),
        "rows": rows,
        "warnings": list(state.get("warnings", [])),
        "notes": list(state.get("notes", [])),
    }


def write_report(paths: RunPaths, manifest: Dict[str, Any], state: Dict[str, Any], args: argparse.Namespace) -> None:
    report = build_report(manifest=manifest, state=state, args=args)
    atomic_write_json(paths.report, report)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Audit relations that were positively allocated but absent in the final graph, "
            "using sampled WDQS candidate evidence and resumable run artifacts."
        )
    )
    p.add_argument("--graph_triples", type=Path, required=True, help="Final graph triples JSON/JSONL.")
    p.add_argument(
        "--relation_audit_json",
        type=Path,
        required=True,
        help="Relation audit/comparison JSON containing relation, actual_count, eta_integer, flags.",
    )
    p.add_argument("--output_dir", type=Path, required=True, help="Run directory for manifest/state/events/report.")
    p.add_argument("--resume", action="store_true", help="Resume from an existing output_dir.")
    p.add_argument("--user_agent", type=str, default=DEFAULT_USER_AGENT, help="HTTP User-Agent for WDQS.")
    p.add_argument("--timeout_sec", type=int, default=60, help="WDQS request timeout in seconds.")
    p.add_argument("--query_limit", type=int, default=200, help="Per-relation WDQS sample limit.")
    p.add_argument("--head_field", type=str, default="h")
    p.add_argument("--rel_field", type=str, default="r")
    p.add_argument("--tail_field", type=str, default="t")
    p.add_argument(
        "--valid_types_json",
        type=Path,
        default=None,
        help="Optional relation->valid subject/object type map JSON.",
    )
    args = p.parse_args(argv)

    if int(args.query_limit) <= 0:
        raise ValueError("--query_limit must be > 0.")
    if int(args.timeout_sec) <= 0:
        raise ValueError("--timeout_sec must be > 0.")
    if not str(args.user_agent).strip():
        raise ValueError("--user_agent must be non-empty.")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    paths = make_run_paths(args.output_dir)

    graph_nodes = load_graph_nodes(
        path=args.graph_triples,
        head_field=str(args.head_field),
        tail_field=str(args.tail_field),
    )
    relation_rows = load_relation_audit_rows(path=args.relation_audit_json)
    target_by_relation, target_warnings = extract_target_relations(relation_rows)
    target_relations = sorted(target_by_relation.keys())

    valid_types_map, valid_types_supplied = load_valid_types_map(args.valid_types_json)
    manifest, state = load_or_init_run(
        args=args,
        paths=paths,
        target_relations=target_relations,
        warnings=target_warnings,
    )
    _ = manifest
    ensure_state_defaults(state)

    processed_set: Set[str] = {str(x) for x in state.get("processed_relations", [])}
    counters = state["counters"]

    interrupted = False
    run_error: Optional[str] = None

    try:
        total = len(target_relations)
        for idx, relation in enumerate(target_relations, start=1):
            if relation in processed_set:
                continue

            base_row = target_by_relation[relation]
            emit_event(
                paths,
                "relation_started",
                relation=relation,
                relation_index=idx,
                relation_total=total,
                pattern=base_row.get("pattern"),
                eta_integer=base_row.get("eta_integer"),
                actual_count=base_row.get("actual_count"),
            )
            log(f"[{idx}/{total}] auditing relation {relation}")

            result_row, debug_row = classify_relation(
                relation_row=base_row,
                graph_nodes=graph_nodes,
                valid_types_map=valid_types_map,
                valid_types_supplied=valid_types_supplied,
                args=args,
                paths=paths,
                state=state,
            )

            state["relation_results"][relation] = result_row
            state["relation_debug"][relation] = debug_row
            state["processed_relations"].append(relation)
            processed_set.add(relation)

            counters["relations_processed"] = int(counters.get("relations_processed", 0)) + 1
            bucket = str(result_row.get("bucket") or BUCKET_UNKNOWN_OR_QUERY_FAILED)
            counters["bucket_counts"][bucket] = int(counters["bucket_counts"].get(bucket, 0)) + 1

            emit_event(
                paths,
                "relation_classified",
                relation=relation,
                bucket=bucket,
                global_candidate_count=result_row.get("global_candidate_count"),
                typed_candidate_count=result_row.get("typed_candidate_count"),
                touching_graph_candidate_count=result_row.get("touching_graph_candidate_count"),
                query_failed=bool(result_row.get("query_failed", False)),
            )
            checkpoint_state(paths, state, reason="relation_classified", relation=relation)
            write_report(paths=paths, manifest=manifest, state=state, args=args)

        state["completed"] = True
        state["successful"] = True
        state["run_finished_at"] = utc_now_iso()
        emit_event(
            paths,
            "run_finished",
            completed=True,
            successful=True,
            counts_snapshot=counter_snapshot(state),
        )
        checkpoint_state(paths, state, reason="run_finished")
        write_report(paths=paths, manifest=manifest, state=state, args=args)
        log("Audit run finished successfully.")

    except KeyboardInterrupt:
        interrupted = True
        run_error = "keyboard_interrupt"
    except Exception as exc:  # noqa: BLE001
        interrupted = True
        run_error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()

    if interrupted:
        state["completed"] = False
        state["successful"] = False
        state["run_finished_at"] = utc_now_iso()
        state["last_error"] = run_error
        state["notes"].append("Run interrupted before completion.")
        emit_event(
            paths,
            "run_finished",
            completed=False,
            successful=False,
            error=run_error,
            counts_snapshot=counter_snapshot(state),
        )
        checkpoint_state(paths, state, reason="run_interrupted")
        write_report(paths=paths, manifest=manifest, state=state, args=args)
        log("Audit run interrupted. Re-run with --resume to continue.")
        return 130 if run_error == "keyboard_interrupt" else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
