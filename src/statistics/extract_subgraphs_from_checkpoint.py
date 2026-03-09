#!/usr/bin/env python3
"""Extract component-filtered triples from a Phase4 checkpoint.

This utility reads a checkpoint JSON produced by:
- src/kg_building/build_connected_graph_from_allocation.py
- src/kg_building/run_phase4_sparql_from_allocation.py

It builds an undirected entity graph on (h, t), finds connected components,
keeps components that satisfy size thresholds, and writes filtered triples.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from src.statistics.plot_connected_triples_graph import (
        _aggregate_triples as _viz_aggregate_triples,
        _build_figure as _viz_build_figure,
        _filter_by_edges as _viz_filter_by_edges,
        _filter_by_nodes as _viz_filter_by_nodes,
    )
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    from src.statistics.plot_connected_triples_graph import (
        _aggregate_triples as _viz_aggregate_triples,
        _build_figure as _viz_build_figure,
        _filter_by_edges as _viz_filter_by_edges,
        _filter_by_nodes as _viz_filter_by_nodes,
    )


Triple = Tuple[str, str, str]


def _safe_int(v: object, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _dump_json_atomic(path: str, payload: Dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(str(tmp), str(out))


def _load_json_if_exists(path: str) -> Optional[Dict]:
    p = Path(path)
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_qid(x: str) -> bool:
    return isinstance(x, str) and len(x) > 1 and x[0] == "Q" and x[1:].isdigit()


def _is_pid(x: str) -> bool:
    return isinstance(x, str) and len(x) > 1 and x[0] == "P" and x[1:].isdigit()


def _run_sparql_json(
    endpoint_url: str,
    user_agent: str,
    query: str,
    *,
    timeout_sec: int,
    retries: int,
    retry_sleep_sec: float = 1.2,
) -> Dict:
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    url = f"{endpoint_url}?{params}"
    headers = {"Accept": "application/sparql-results+json", "User-Agent": user_agent}
    last_err: Optional[Exception] = None
    for k in range(max(1, int(retries))):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=max(5, int(timeout_sec))) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if k + 1 < max(1, int(retries)):
                time.sleep(max(0.1, float(retry_sleep_sec)))
    raise RuntimeError(f"SPARQL request failed after {retries} retries: {last_err}")


def _fetch_wdqs_triples_touching_nodes(
    nodes: List[str],
    *,
    endpoint_url: str,
    user_agent: str,
    timeout_sec: int,
    retries: int,
    limit_per_query: int,
) -> List[Triple]:
    qids = [q for q in nodes if _is_qid(q)]
    if not qids:
        return []
    values = " ".join(f"wd:{q}" for q in qids)
    q = f"""
    SELECT ?h ?p ?t WHERE {{
      VALUES ?v {{ {values} }}
      {{
        ?v ?p ?t .
        BIND(?v AS ?h)
      }}
      UNION
      {{
        ?h ?p ?v .
        BIND(?v AS ?t)
      }}
      FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct/"))
      FILTER(STRSTARTS(STR(?h), "http://www.wikidata.org/entity/Q"))
      FILTER(STRSTARTS(STR(?t), "http://www.wikidata.org/entity/Q"))
    }}
    ORDER BY ?h ?p ?t
    LIMIT {max(1, int(limit_per_query))}
    """
    try:
        res = _run_sparql_json(
            endpoint_url=endpoint_url,
            user_agent=user_agent,
            query=q,
            timeout_sec=timeout_sec,
            retries=retries,
        )
    except Exception:
        return []

    out: List[Triple] = []
    for b in res.get("results", {}).get("bindings", []):
        h_uri = b.get("h", {}).get("value", "")
        p_uri = b.get("p", {}).get("value", "")
        t_uri = b.get("t", {}).get("value", "")
        h = h_uri.rsplit("/", 1)[-1]
        p = p_uri.rsplit("/", 1)[-1]
        t = t_uri.rsplit("/", 1)[-1]
        if _is_qid(h) and _is_pid(p) and _is_qid(t):
            out.append((h, p, t))
    return out


def _chunks(items: List[str], k: int) -> List[List[str]]:
    size = max(1, int(k))
    return [items[i : i + size] for i in range(0, len(items), size)]


def _below_threshold_component_ids(
    comp_stats: List[Dict],
    *,
    min_component_nodes: int,
    min_component_triples: int,
) -> Set[int]:
    return {
        int(x["component_id"])
        for x in comp_stats
        if _safe_int(x.get("nodes"), 0) < int(min_component_nodes)
        or _safe_int(x.get("triples"), 0) < int(min_component_triples)
    }


def _targeted_expand_small_components_from_wdqs(
    triples: List[Triple],
    *,
    min_component_nodes: int,
    min_component_triples: int,
    endpoint_url: str,
    user_agent: str,
    timeout_sec: int,
    retries: int,
    rounds: int,
    nodes_per_query: int,
    limit_per_query: int,
    max_new_triples_total: int,
    checkpoint_path: str = "",
    resume_from_checkpoint: bool = False,
    checkpoint_every_rounds: int = 1,
) -> Tuple[List[Triple], Dict[str, int]]:
    if not user_agent.strip():
        raise RuntimeError("Targeted expansion requires a non-empty --expand_user_agent.")

    current = list(triples)
    added_total = 0
    rounds_run = 0
    start_round = 1

    if resume_from_checkpoint and checkpoint_path:
        cp = _load_json_if_exists(checkpoint_path)
        if isinstance(cp, dict) and cp.get("status") in {"in_progress", "completed"}:
            raw = cp.get("current_triples", [])
            if isinstance(raw, list):
                restored: List[Triple] = []
                for x in raw:
                    if isinstance(x, (list, tuple)) and len(x) == 3:
                        restored.append((str(x[0]), str(x[1]), str(x[2])))
                if restored:
                    current = restored
                    added_total = int(cp.get("new_triples_added", 0))
                    start_round = max(1, int(cp.get("next_round", 1)))

    used = set((h, r, t) for h, r, t in current)

    def save_expand_checkpoint(status: str, next_round: int, extra: Optional[Dict] = None) -> None:
        if not checkpoint_path:
            return
        payload = {
            "status": status,
            "next_round": int(max(1, next_round)),
            "new_triples_added": int(added_total),
            "current_triples": [[h, r, t] for h, r, t in current],
            "triples_count": int(len(current)),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        _dump_json_atomic(checkpoint_path, payload)

    if checkpoint_path and start_round == 1:
        save_expand_checkpoint("in_progress", 1)

    for _round in range(start_round, max(1, int(rounds)) + 1):
        comps, node_to_comp = _connected_components(current)
        comp_stats = _component_stats(current, comps, node_to_comp)
        small_cids = _below_threshold_component_ids(
            comp_stats,
            min_component_nodes=max(1, int(min_component_nodes)),
            min_component_triples=max(1, int(min_component_triples)),
        )
        if not small_cids:
            save_expand_checkpoint(
                "completed",
                _round,
                {"stop_reason": "no_small_components", "rounds_run": int(rounds_run)},
            )
            break

        seed_nodes = sorted([n for n, cid in node_to_comp.items() if cid in small_cids and _is_qid(n)])
        if not seed_nodes:
            save_expand_checkpoint(
                "completed",
                _round,
                {"stop_reason": "no_seed_nodes", "rounds_run": int(rounds_run)},
            )
            break

        before = len(current)
        for batch in _chunks(seed_nodes, max(1, int(nodes_per_query))):
            fetched = _fetch_wdqs_triples_touching_nodes(
                batch,
                endpoint_url=endpoint_url,
                user_agent=user_agent,
                timeout_sec=timeout_sec,
                retries=retries,
                limit_per_query=max(1, int(limit_per_query)),
            )
            for tr in fetched:
                if tr in used:
                    continue
                used.add(tr)
                current.append(tr)
                added_total += 1
                if added_total >= max(1, int(max_new_triples_total)):
                    break
            if added_total >= max(1, int(max_new_triples_total)):
                break
        rounds_run += 1
        if checkpoint_path and (rounds_run % max(1, int(checkpoint_every_rounds)) == 0):
            save_expand_checkpoint(
                "in_progress",
                _round + 1,
                {
                    "round_completed": int(_round),
                    "small_components_last_round": int(len(small_cids)),
                },
            )
        if len(current) == before:
            save_expand_checkpoint(
                "completed",
                _round + 1,
                {"stop_reason": "no_growth", "rounds_run": int(rounds_run)},
            )
            break
        if added_total >= max(1, int(max_new_triples_total)):
            save_expand_checkpoint(
                "completed",
                _round + 1,
                {"stop_reason": "max_new_triples_reached", "rounds_run": int(rounds_run)},
            )
            break

    info = {
        "rounds_run": int(rounds_run),
        "new_triples_added": int(added_total),
        "triples_after_expansion": int(len(current)),
        "expansion_checkpoint_path": str(Path(checkpoint_path).resolve()) if checkpoint_path else None,
        "expansion_resumed": bool(resume_from_checkpoint and start_round > 1),
    }
    if checkpoint_path:
        save_expand_checkpoint(
            "completed",
            max(1, int(rounds)) + 1,
            {"stop_reason": "finished_loop", "rounds_run": int(rounds_run)},
        )
    return current, info


def _pick_checkpoint_triple_list(doc: Dict, attempt_mode: str = "auto") -> Tuple[str, List[Dict]]:
    """Choose which checkpoint list to use for triples extraction.

    attempt_mode:
    - auto: prefer running triples (`triples_out`) when status=in_progress,
      otherwise use final triples (`triples`) when available.
    - running: force `triples_out` (for live in-progress state).
    - final: force `triples` (for success/partial final state).
    """
    mode = str(attempt_mode or "auto").strip().lower()
    if mode not in {"auto", "running", "final"}:
        raise RuntimeError(f"Unsupported attempt_mode={attempt_mode}. Use auto|running|final.")

    status = str(doc.get("status", "")).strip().lower()
    triples = doc.get("triples")
    triples_out = doc.get("triples_out")

    if mode == "running":
        if status != "in_progress":
            raise RuntimeError(
                f"attempt_mode=running requested but checkpoint status is {status!r} (expected 'in_progress')."
            )
        if isinstance(triples_out, list):
            return "triples_out", triples_out
        raise RuntimeError("attempt_mode=running requested but `triples_out` is missing.")

    if mode == "final":
        if isinstance(triples, list):
            return "triples", triples
        raise RuntimeError("attempt_mode=final requested but `triples` is missing.")

    if status == "in_progress" and isinstance(triples_out, list):
        return "triples_out", triples_out
    if isinstance(triples, list):
        return "triples", triples
    if isinstance(triples_out, list):
        return "triples_out", triples_out
    raise RuntimeError("Checkpoint has no usable triples list. Expected `triples` or `triples_out`.")


def _checkpoint_candidate_paths(checkpoint_json: str, attempt_checkpoints_glob: str) -> List[str]:
    base = Path(checkpoint_json)
    candidate_paths: List[str] = []
    if attempt_checkpoints_glob:
        candidate_paths.extend(sorted(glob.glob(attempt_checkpoints_glob)))
    if base.exists():
        candidate_paths.append(str(base))

    deduped: List[str] = []
    seen: Set[str] = set()
    for p in candidate_paths:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)
    return deduped


def _load_checkpoint_doc(
    checkpoint_json: str,
    *,
    attempt_number: Optional[int],
    attempt_checkpoints_glob: str,
    attempt_mode: str,
) -> Tuple[str, Dict]:
    """Load checkpoint doc, optionally selecting a specific attempt number.

    If `attempt_number` is provided:
    - If `attempt_checkpoints_glob` is provided, scan matching files.
    - Also include `checkpoint_json` in the candidate set.
    - Select the newest matching file by mtime.
    """
    base = Path(checkpoint_json)
    if attempt_number is None:
        with open(base, "r", encoding="utf-8") as f:
            return str(base), json.load(f)

    dedup = _checkpoint_candidate_paths(checkpoint_json, attempt_checkpoints_glob)
    if not dedup:
        raise RuntimeError(
            "attempt_number was provided but no checkpoint candidates were found. "
            "Provide --attempt_checkpoints_glob with saved attempt snapshots."
        )

    matches: List[Tuple[float, str, Dict]] = []
    for p in dedup:
        try:
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
            if int(doc.get("attempt", -1)) != int(attempt_number):
                continue
            # Validate mode compatibility up-front.
            _pick_checkpoint_triple_list(doc, attempt_mode=attempt_mode)
            matches.append((Path(p).stat().st_mtime, p, doc))
        except Exception:
            continue

    if not matches:
        raise RuntimeError(
            f"No checkpoint found for attempt={attempt_number} with attempt_mode={attempt_mode}. "
            "If you want old attempts, save per-attempt snapshots and pass --attempt_checkpoints_glob."
        )

    matches.sort(key=lambda x: x[0], reverse=True)
    _mtime, selected_path, selected_doc = matches[0]
    return selected_path, selected_doc


def _parse_triples(rows: List[Dict], field_head: str, field_rel: str, field_tail: str) -> List[Triple]:
    triples: List[Triple] = []
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        h = rec.get(field_head)
        r = rec.get(field_rel)
        t = rec.get(field_tail)
        if h is None or r is None or t is None:
            continue
        triples.append((str(h), str(r), str(t)))
    return triples


def _dedupe_triples(triples: List[Triple]) -> List[Triple]:
    out: List[Triple] = []
    seen: Set[Triple] = set()
    for tr in triples:
        if tr in seen:
            continue
        seen.add(tr)
        out.append(tr)
    return out


def _load_all_attempts_triples(
    checkpoint_json: str,
    *,
    attempt_checkpoints_glob: str,
    attempt_mode: str,
    field_head: str,
    field_rel: str,
    field_tail: str,
) -> Tuple[List[Triple], Dict]:
    candidate_paths = _checkpoint_candidate_paths(checkpoint_json, attempt_checkpoints_glob)
    if not candidate_paths:
        raise RuntimeError(
            "aggregate_all_attempts requested but no checkpoint candidates were found. "
            "Provide --attempt_checkpoints_glob with saved attempt snapshots."
        )

    by_attempt: Dict[int, Tuple[float, str, Dict, str]] = {}
    anonymous_docs: List[Tuple[float, str, Dict, str]] = []
    considered = 0
    skipped = 0

    for p in candidate_paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
            source_key, _rows = _pick_checkpoint_triple_list(doc, attempt_mode=attempt_mode)
            considered += 1
            attempt_raw = doc.get("attempt")
            try:
                attempt_id = int(attempt_raw) if attempt_raw is not None else None
            except (TypeError, ValueError):
                attempt_id = None
            item = (Path(p).stat().st_mtime, p, doc, source_key)
            if attempt_id is None:
                anonymous_docs.append(item)
                continue
            prev = by_attempt.get(attempt_id)
            if prev is None or item[0] >= prev[0]:
                by_attempt[attempt_id] = item
        except Exception:
            skipped += 1
            continue

    selected_docs: List[Tuple[float, str, Dict, str]] = []
    selected_docs.extend(by_attempt[k] for k in sorted(by_attempt))
    for item in sorted(anonymous_docs, key=lambda x: (x[1], x[0])):
        selected_docs.append(item)

    if not selected_docs:
        raise RuntimeError(
            f"aggregate_all_attempts found no compatible checkpoints for attempt_mode={attempt_mode}. "
            "If you want historical attempts, save per-attempt snapshots and pass --attempt_checkpoints_glob."
        )

    all_triples: List[Triple] = []
    source_summaries: List[Dict] = []
    for _mtime, p, doc, source_key in selected_docs:
        rows = doc.get(source_key, [])
        triples = _parse_triples(rows, field_head, field_rel, field_tail)
        if not triples:
            continue
        all_triples.extend(triples)
        source_summaries.append(
            {
                "checkpoint_path": str(Path(p).resolve()),
                "attempt": doc.get("attempt"),
                "status": doc.get("status"),
                "triples_source": source_key,
                "triples_count": len(triples),
            }
        )

    deduped = _dedupe_triples(all_triples)
    if not deduped:
        raise RuntimeError("aggregate_all_attempts found checkpoint docs but no valid triples to aggregate.")

    attempts = []
    for x in source_summaries:
        try:
            if x.get("attempt") is not None:
                attempts.append(int(x["attempt"]))
        except (TypeError, ValueError):
            continue

    info = {
        "enabled": True,
        "source_docs_discovered": len(candidate_paths),
        "source_docs_compatible": considered,
        "source_docs_skipped": skipped,
        "source_docs_used": len(source_summaries),
        "selected_attempts": sorted(set(attempts)),
        "input_triples_before_dedupe": len(all_triples),
        "input_triples_after_dedupe": len(deduped),
        "sources": source_summaries,
    }
    return deduped, info


def _connected_components(triples: List[Triple]) -> Tuple[List[Set[str]], Dict[str, int]]:
    adj: Dict[str, Set[str]] = defaultdict(set)
    nodes: Set[str] = set()
    for h, _r, t in triples:
        nodes.add(h)
        nodes.add(t)
        adj[h].add(t)
        adj[t].add(h)

    components: List[Set[str]] = []
    node_to_comp: Dict[str, int] = {}
    seen: Set[str] = set()
    # Deterministic traversal order for reproducible component IDs.
    for n in sorted(nodes):
        if n in seen:
            continue
        cid = len(components)
        comp_nodes: Set[str] = set()
        stack = [n]
        seen.add(n)
        while stack:
            cur = stack.pop()
            comp_nodes.add(cur)
            node_to_comp[cur] = cid
            for nxt in sorted(adj.get(cur, ())):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        components.append(comp_nodes)
    return components, node_to_comp


def _component_stats(triples: List[Triple], components: List[Set[str]], node_to_comp: Dict[str, int]) -> List[Dict]:
    triples_by_comp: Dict[int, List[Triple]] = defaultdict(list)
    rel_counts_by_comp: Dict[int, Counter] = defaultdict(Counter)
    cross_edges = 0
    for h, r, t in triples:
        cid_h = node_to_comp.get(h)
        cid_t = node_to_comp.get(t)
        if cid_h is None or cid_t is None:
            continue
        if cid_h != cid_t:
            cross_edges += 1
            continue
        triples_by_comp[cid_h].append((h, r, t))
        rel_counts_by_comp[cid_h][r] += 1

    out: List[Dict] = []
    for cid, comp_nodes in enumerate(components):
        rel_counter = rel_counts_by_comp.get(cid, Counter())
        out.append(
            {
                "component_id": cid,
                "nodes": len(comp_nodes),
                "triples": len(triples_by_comp.get(cid, [])),
                "relations": len(rel_counter),
                "top_relations": rel_counter.most_common(10),
            }
        )
    if cross_edges > 0:
        print(f"[warn] Found {cross_edges} cross-component triples; these were skipped in component stats.")
    return out


def _select_components(
    comp_stats: List[Dict],
    *,
    min_component_nodes: int,
    min_component_triples: int,
    keep_largest_only: bool,
    exclude_largest_component: bool,
    max_components: int,
) -> Set[int]:
    if not comp_stats:
        return set()

    ranked = sorted(
        comp_stats,
        key=lambda x: (
            _safe_int(x.get("nodes"), 0),
            _safe_int(x.get("triples"), 0),
            -_safe_int(x.get("component_id"), 0),
        ),
        reverse=True,
    )
    largest_cid = int(ranked[0]["component_id"])
    if keep_largest_only:
        return {largest_cid}

    keep = {
        int(x["component_id"])
        for x in ranked
        if _safe_int(x.get("nodes"), 0) >= min_component_nodes
        and _safe_int(x.get("triples"), 0) >= min_component_triples
    }
    if exclude_largest_component:
        keep.discard(largest_cid)
    if max_components > 0 and keep:
        top = [int(x["component_id"]) for x in ranked if int(x["component_id"]) in keep][:max_components]
        keep = set(top)
    return keep


def _filter_triples_by_components(triples: List[Triple], node_to_comp: Dict[str, int], keep_cids: Set[int]) -> List[Triple]:
    kept: List[Triple] = []
    for h, r, t in triples:
        cid_h = node_to_comp.get(h)
        cid_t = node_to_comp.get(t)
        if cid_h is None or cid_t is None:
            continue
        if cid_h == cid_t and cid_h in keep_cids:
            kept.append((h, r, t))
    return kept


def _write_jsonl(path: str, triples: List[Triple], field_head: str, field_rel: str, field_tail: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for h, r, t in triples:
            f.write(json.dumps({field_head: h, field_rel: r, field_tail: t}, ensure_ascii=False) + "\n")


def _write_relation_counts_csv(path: str, triples: List[Triple]) -> Dict[str, int]:
    rel_counter: Counter[str] = Counter()
    for _h, r, _t in triples:
        rel_counter[str(r)] += 1
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("relation,count\n")
        for rel, cnt in rel_counter.most_common():
            f.write(f"{rel},{int(cnt)}\n")
    return {"relations_distinct": len(rel_counter), "triples_counted": int(sum(rel_counter.values()))}


def _write_graph_html(
    out_html: str,
    triples: List[Triple],
    *,
    max_nodes: int,
    max_edges: int,
    sample_edges: bool,
    top_relations_colored: int,
    layout_seed: int,
    layout_k: float,
    layout_iterations: int,
) -> Dict[str, int]:
    edge_counts = _viz_aggregate_triples(triples)
    edge_counts = _viz_filter_by_nodes(edge_counts, max_nodes=max_nodes)
    edge_counts = _viz_filter_by_edges(
        edge_counts,
        max_edges=max_edges,
        sample_edges=sample_edges,
        random_seed=layout_seed,
    )
    if not edge_counts:
        raise RuntimeError("No edges remain for visualization after max_nodes/max_edges filtering.")

    fig = _viz_build_figure(
        edge_counts=edge_counts,
        top_relations_colored=max(0, int(top_relations_colored)),
        layout_seed=int(layout_seed),
        layout_k=float(layout_k),
        layout_iterations=max(1, int(layout_iterations)),
    )
    out_path = Path(out_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out_path), include_plotlyjs="cdn")

    nodes = set()
    rel_counter: Counter = Counter()
    triples_total = 0
    for (h, r, t), c in edge_counts.items():
        nodes.add(h)
        nodes.add(t)
        rel_counter[r] += int(c)
        triples_total += int(c)
    return {
        "viz_unique_edges": len(edge_counts),
        "viz_nodes": len(nodes),
        "viz_relations": len(rel_counter),
        "viz_triples_total": int(triples_total),
    }


def extract_subgraphs_from_checkpoint(
    *,
    checkpoint_json: str,
    output_triples_jsonl: str,
    output_stats_json: str = "",
    output_relations_csv: str = "",
    out_html: str = "",
    field_head: str = "h",
    field_rel: str = "r",
    field_tail: str = "t",
    min_component_nodes: int = 1,
    min_component_triples: int = 1,
    keep_largest_only: bool = False,
    exclude_largest_component: bool = False,
    max_components: int = 0,
    viz_max_nodes: int = 0,
    viz_max_edges: int = 0,
    viz_sample_edges: bool = False,
    viz_top_relations_colored: int = 20,
    viz_layout_seed: int = 42,
    viz_layout_k: float = 0.0,
    viz_layout_iterations: int = 120,
    attempt_mode: str = "auto",
    attempt_number: Optional[int] = None,
    attempt_checkpoints_glob: str = "",
    aggregate_all_attempts: bool = False,
    expand_small_components: bool = False,
    expand_endpoint_url: str = "https://query.wikidata.org/sparql",
    expand_user_agent: str = "",
    expand_timeout_sec: int = 30,
    expand_retries: int = 2,
    expand_rounds: int = 2,
    expand_nodes_per_query: int = 20,
    expand_limit_per_query: int = 120,
    expand_max_new_triples_total: int = 3000,
    expand_checkpoint_path: str = "",
    expand_resume_checkpoint: bool = False,
    expand_checkpoint_every_rounds: int = 1,
) -> Dict:
    """Extract component-filtered triples from checkpoint and optionally visualize.

    Reproducibility note:
    - For identical output across runs, use the same immutable checkpoint file
      (snapshot), the same arguments, and keep `viz_sample_edges=False`.
    """
    if keep_largest_only and exclude_largest_component:
        raise RuntimeError("Cannot use both keep_largest_only and exclude_largest_component.")
    if aggregate_all_attempts and attempt_number is not None:
        raise RuntimeError("Cannot use --aggregate_all_attempts together with --attempt_number.")

    selected_checkpoint_path: Optional[str] = None
    selected_checkpoint_paths: List[str] = []
    checkpoint_status: Optional[object] = None
    selected_attempt: Optional[object] = None
    aggregate_info = {
        "enabled": False,
        "source_docs_discovered": 1,
        "source_docs_compatible": 1,
        "source_docs_skipped": 0,
        "source_docs_used": 1,
        "selected_attempts": [],
        "input_triples_before_dedupe": None,
        "input_triples_after_dedupe": None,
        "sources": [],
    }

    if aggregate_all_attempts:
        triples, aggregate_info = _load_all_attempts_triples(
            checkpoint_json,
            attempt_checkpoints_glob=attempt_checkpoints_glob,
            attempt_mode=attempt_mode,
            field_head=field_head,
            field_rel=field_rel,
            field_tail=field_tail,
        )
        selected_checkpoint_paths = [str(x["checkpoint_path"]) for x in aggregate_info.get("sources", [])]
        source_key = "all_attempts_deduped"
    else:
        selected_checkpoint_path, checkpoint = _load_checkpoint_doc(
            checkpoint_json,
            attempt_number=attempt_number,
            attempt_checkpoints_glob=attempt_checkpoints_glob,
            attempt_mode=attempt_mode,
        )
        source_key, rows = _pick_checkpoint_triple_list(checkpoint, attempt_mode=attempt_mode)
        triples = _parse_triples(rows, field_head, field_rel, field_tail)
        selected_checkpoint_paths = [str(Path(selected_checkpoint_path).resolve())]
        checkpoint_status = checkpoint.get("status")
        selected_attempt = checkpoint.get("attempt")
        try:
            if selected_attempt is not None:
                aggregate_info["selected_attempts"] = [int(selected_attempt)]
        except (TypeError, ValueError):
            pass
        aggregate_info["sources"] = [
            {
                "checkpoint_path": str(Path(selected_checkpoint_path).resolve()),
                "attempt": selected_attempt,
                "status": checkpoint_status,
                "triples_source": source_key,
                "triples_count": len(triples),
            }
        ]
        aggregate_info["input_triples_before_dedupe"] = len(triples)
        aggregate_info["input_triples_after_dedupe"] = len(triples)

    if not triples:
        raise RuntimeError("No valid triples found in checkpoint data.")

    expansion_info: Optional[Dict[str, int]] = None
    if expand_small_components:
        triples, expansion_info = _targeted_expand_small_components_from_wdqs(
            triples,
            min_component_nodes=max(1, int(min_component_nodes)),
            min_component_triples=max(1, int(min_component_triples)),
            endpoint_url=str(expand_endpoint_url),
            user_agent=str(expand_user_agent),
            timeout_sec=max(5, int(expand_timeout_sec)),
            retries=max(1, int(expand_retries)),
            rounds=max(1, int(expand_rounds)),
            nodes_per_query=max(1, int(expand_nodes_per_query)),
            limit_per_query=max(1, int(expand_limit_per_query)),
            max_new_triples_total=max(1, int(expand_max_new_triples_total)),
            checkpoint_path=str(expand_checkpoint_path),
            resume_from_checkpoint=bool(expand_resume_checkpoint),
            checkpoint_every_rounds=max(1, int(expand_checkpoint_every_rounds)),
        )

    comps, node_to_comp = _connected_components(triples)
    comp_stats = _component_stats(triples, comps, node_to_comp)
    keep_cids = _select_components(
        comp_stats,
        min_component_nodes=max(1, int(min_component_nodes)),
        min_component_triples=max(1, int(min_component_triples)),
        keep_largest_only=bool(keep_largest_only),
        exclude_largest_component=bool(exclude_largest_component),
        max_components=max(0, int(max_components)),
    )
    filtered = _filter_triples_by_components(triples, node_to_comp, keep_cids)
    _write_jsonl(output_triples_jsonl, filtered, field_head, field_rel, field_tail)
    rel_csv_info: Optional[Dict[str, int]] = None
    if output_relations_csv:
        rel_csv_info = _write_relation_counts_csv(output_relations_csv, filtered)

    input_nodes = len(node_to_comp)
    output_nodes = len({x for tr in filtered for x in (tr[0], tr[2])})
    viz_info: Dict[str, int] = {}
    if out_html:
        viz_info = _write_graph_html(
            out_html,
            filtered,
            max_nodes=int(viz_max_nodes),
            max_edges=int(viz_max_edges),
            sample_edges=bool(viz_sample_edges),
            top_relations_colored=int(viz_top_relations_colored),
            layout_seed=int(viz_layout_seed),
            layout_k=float(viz_layout_k),
            layout_iterations=int(viz_layout_iterations),
        )
    kept_stats = [x for x in comp_stats if int(x["component_id"]) in keep_cids]
    summary = {
        "checkpoint_path": str(Path(checkpoint_json).resolve()),
        "selected_checkpoint_path": str(Path(selected_checkpoint_path).resolve()) if selected_checkpoint_path else None,
        "selected_checkpoint_paths": selected_checkpoint_paths,
        "checkpoint_status": checkpoint_status,
        "selected_attempt": selected_attempt,
        "attempt_mode": str(attempt_mode),
        "attempt_aggregation": aggregate_info,
        "triples_source": source_key,
        "input_triples": len(triples),
        "input_nodes": input_nodes,
        "components_total": len(comp_stats),
        "filter": {
            "min_component_nodes": int(max(1, min_component_nodes)),
            "min_component_triples": int(max(1, min_component_triples)),
            "keep_largest_only": bool(keep_largest_only),
            "exclude_largest_component": bool(exclude_largest_component),
            "max_components": int(max(0, max_components)),
        },
        "kept_component_ids": sorted(list(keep_cids)),
        "kept_components": len(keep_cids),
        "output_triples": len(filtered),
        "output_nodes": output_nodes,
        "output_relations_csv": str(Path(output_relations_csv).resolve()) if output_relations_csv else None,
        "relations_csv_summary": rel_csv_info,
        "output_html": str(Path(out_html).resolve()) if out_html else None,
        "viz_summary": viz_info if out_html else None,
        "targeted_expansion": {
            "enabled": bool(expand_small_components),
            "endpoint_url": str(expand_endpoint_url) if expand_small_components else None,
            "rounds_requested": int(expand_rounds) if expand_small_components else None,
            "nodes_per_query": int(expand_nodes_per_query) if expand_small_components else None,
            "limit_per_query": int(expand_limit_per_query) if expand_small_components else None,
            "max_new_triples_total": int(expand_max_new_triples_total) if expand_small_components else None,
            "checkpoint_path": str(Path(expand_checkpoint_path).resolve()) if (expand_small_components and expand_checkpoint_path) else None,
            "resume_checkpoint": bool(expand_resume_checkpoint) if expand_small_components else None,
            "checkpoint_every_rounds": int(expand_checkpoint_every_rounds) if expand_small_components else None,
            "result": expansion_info,
        },
        "components": comp_stats,
        "kept_components_stats": kept_stats,
    }

    if output_stats_json:
        stats_path = Path(output_stats_json)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint_json", required=True)
    ap.add_argument("--output_triples_jsonl", required=True)
    ap.add_argument("--output_stats_json", default="")
    ap.add_argument("--output_relations_csv", default="", help="Optional relation,count CSV for output triples.")
    ap.add_argument("--out_html", default="", help="Optional interactive graph HTML for filtered triples.")
    ap.add_argument("--field_head", default="h")
    ap.add_argument("--field_rel", default="r")
    ap.add_argument("--field_tail", default="t")
    ap.add_argument("--min_component_nodes", type=int, default=1)
    ap.add_argument("--min_component_triples", type=int, default=1)
    ap.add_argument("--keep_largest_only", action="store_true")
    ap.add_argument("--exclude_largest_component", action="store_true", help="Drop the single largest component.")
    ap.add_argument("--max_components", type=int, default=0, help="0 means unlimited.")
    ap.add_argument("--viz_max_nodes", type=int, default=0, help="0 keeps all nodes.")
    ap.add_argument("--viz_max_edges", type=int, default=0, help="0 keeps all unique (h,r,t) edges.")
    ap.add_argument("--viz_sample_edges", action="store_true", help="If viz_max_edges active, sample randomly.")
    ap.add_argument("--viz_top_relations_colored", type=int, default=20)
    ap.add_argument("--viz_layout_seed", type=int, default=42)
    ap.add_argument("--viz_layout_k", type=float, default=0.0, help="0 uses networkx default.")
    ap.add_argument("--viz_layout_iterations", type=int, default=120)
    ap.add_argument(
        "--attempt_mode",
        choices=["auto", "running", "final"],
        default="auto",
        help="auto: running if in_progress else final; running: force triples_out; final: force triples.",
    )
    ap.add_argument("--attempt_number", type=int, default=None, help="Optional attempt id to select.")
    ap.add_argument(
        "--attempt_checkpoints_glob",
        default="",
        help="Optional glob for per-attempt checkpoint snapshots when selecting --attempt_number or --aggregate_all_attempts.",
    )
    ap.add_argument(
        "--aggregate_all_attempts",
        action="store_true",
        help="Aggregate triples from all compatible attempt checkpoints, keeping the latest snapshot per attempt and deduping identical (h,r,t) triples.",
    )
    ap.add_argument(
        "--expand_small_components",
        action="store_true",
        help="For components below threshold, do targeted WDQS expansion using their nodes before filtering.",
    )
    ap.add_argument("--expand_endpoint_url", default="https://query.wikidata.org/sparql")
    ap.add_argument("--expand_user_agent", default="", help="Required when --expand_small_components is set.")
    ap.add_argument("--expand_timeout_sec", type=int, default=30)
    ap.add_argument("--expand_retries", type=int, default=2)
    ap.add_argument("--expand_rounds", type=int, default=2)
    ap.add_argument("--expand_nodes_per_query", type=int, default=20)
    ap.add_argument("--expand_limit_per_query", type=int, default=120)
    ap.add_argument("--expand_max_new_triples_total", type=int, default=3000)
    ap.add_argument("--expand_checkpoint_path", default="", help="Optional expansion-progress checkpoint JSON path.")
    ap.add_argument("--expand_resume_checkpoint", action="store_true", help="Resume expansion from checkpoint path.")
    ap.add_argument("--expand_checkpoint_every_rounds", type=int, default=1)
    args = ap.parse_args()

    summary = extract_subgraphs_from_checkpoint(
        checkpoint_json=args.checkpoint_json,
        output_triples_jsonl=args.output_triples_jsonl,
        output_stats_json=args.output_stats_json,
        output_relations_csv=args.output_relations_csv,
        out_html=args.out_html,
        field_head=args.field_head,
        field_rel=args.field_rel,
        field_tail=args.field_tail,
        min_component_nodes=args.min_component_nodes,
        min_component_triples=args.min_component_triples,
        keep_largest_only=args.keep_largest_only,
        exclude_largest_component=args.exclude_largest_component,
        max_components=args.max_components,
        viz_max_nodes=args.viz_max_nodes,
        viz_max_edges=args.viz_max_edges,
        viz_sample_edges=args.viz_sample_edges,
        viz_top_relations_colored=args.viz_top_relations_colored,
        viz_layout_seed=args.viz_layout_seed,
        viz_layout_k=args.viz_layout_k,
        viz_layout_iterations=args.viz_layout_iterations,
        attempt_mode=args.attempt_mode,
        attempt_number=args.attempt_number,
        attempt_checkpoints_glob=args.attempt_checkpoints_glob,
        aggregate_all_attempts=args.aggregate_all_attempts,
        expand_small_components=args.expand_small_components,
        expand_endpoint_url=args.expand_endpoint_url,
        expand_user_agent=args.expand_user_agent,
        expand_timeout_sec=args.expand_timeout_sec,
        expand_retries=args.expand_retries,
        expand_rounds=args.expand_rounds,
        expand_nodes_per_query=args.expand_nodes_per_query,
        expand_limit_per_query=args.expand_limit_per_query,
        expand_max_new_triples_total=args.expand_max_new_triples_total,
        expand_checkpoint_path=args.expand_checkpoint_path,
        expand_resume_checkpoint=args.expand_resume_checkpoint,
        expand_checkpoint_every_rounds=args.expand_checkpoint_every_rounds,
    )

    print(
        "[done] "
        f"input_triples={summary['input_triples']} "
        f"components_total={summary['components_total']} "
        f"kept_components={summary['kept_components']} "
        f"output_triples={summary['output_triples']} "
        f"output_nodes={summary['output_nodes']}"
    )


if __name__ == "__main__":
    main()
