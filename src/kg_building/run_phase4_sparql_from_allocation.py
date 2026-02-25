#!/usr/bin/env python3
"""Run Phase-4 connected realization from allocation JSON using Wikidata SPARQL.

This is a non-Streamlit runner intended for batch execution (e.g., Slurm).
It reuses the same core realization engine as the dashboard:
- src/kg_building/build_connected_graph_from_allocation.py
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    from src.kg_building.build_connected_graph_from_allocation import (
        RealizationConfig,
        build_relation_quotas,
        is_connected_undirected,
        load_allocations_json,
        realize_connected_graph,
    )
    from src.kg_building.config_sampler import MongoConfig
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    from src.kg_building.build_connected_graph_from_allocation import (
        RealizationConfig,
        build_relation_quotas,
        is_connected_undirected,
        load_allocations_json,
        realize_connected_graph,
    )
    from src.kg_building.config_sampler import MongoConfig


class WikidataSparqlTripleSource:
    """Minimal SPARQL-backed triple source with typed/untyped attach retrieval."""

    def __init__(
        self,
        mcfg: MongoConfig,
        *,
        endpoint_url: str,
        user_agent: str,
        any_fetch: int,
        attach_fetch: int,
        max_v_for_values: int,
        timeout_sec: int,
        retries: int,
        retry_sleep_sec: float = 1.5,
        max_type_values: int = 12,
    ):
        self.mcfg = mcfg
        self.endpoint_url = endpoint_url
        self.user_agent = user_agent
        self.any_fetch = max(1, int(any_fetch))
        self.attach_fetch = max(1, int(attach_fetch))
        self.max_v_for_values = max(1, int(max_v_for_values))
        self.timeout_sec = max(5, int(timeout_sec))
        self.retries = max(1, int(retries))
        self.retry_sleep_sec = max(0.1, float(retry_sleep_sec))
        self.max_type_values = max(1, int(max_type_values))
        self._count_cache: Dict[str, int] = {}
        self._class_entity_cache: Dict[tuple[str, int], List[str]] = {}

    @staticmethod
    def _qid_only(x: str) -> bool:
        return isinstance(x, str) and len(x) > 1 and x[0] == "Q" and x[1:].isdigit()

    @staticmethod
    def _pid_only(x: str) -> bool:
        return isinstance(x, str) and len(x) > 1 and x[0] == "P" and x[1:].isdigit()

    def _select_v_values(self, v: Set[str]) -> List[str]:
        """Select a bounded QID subset from V for SPARQL VALUES/IN filters.

        Using a fixed sorted prefix can repeatedly probe the same narrow region
        of V and lead to persistent zero-capacity estimates. We instead sample
        a fresh subset each call to improve attachability coverage while
        honoring max_v_for_values.
        """
        vals = [x for x in v if self._qid_only(x)]
        if not vals:
            return []
        k = min(len(vals), self.max_v_for_values)
        if len(vals) <= k:
            return vals
        return random.sample(vals, k)

    def _run_sparql(self, query: str) -> dict:
        params = urllib.parse.urlencode({"query": query, "format": "json"})
        url = f"{self.endpoint_url}?{params}"
        headers = {"Accept": "application/sparql-results+json", "User-Agent": self.user_agent}
        last_err: Optional[Exception] = None
        for k in range(self.retries):
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    raw = resp.read().decode("utf-8")
                return json.loads(raw)
            except Exception as e:  # noqa: BLE001
                last_err = e
                if k + 1 < self.retries:
                    time.sleep(self.retry_sleep_sec)
        raise RuntimeError(f"SPARQL request failed after {self.retries} retries: {last_err}")

    def _extract_triples(self, result: dict, pid: str) -> List[Dict]:
        out: List[Dict] = []
        for b in result.get("results", {}).get("bindings", []):
            h_uri = b.get("h", {}).get("value", "")
            t_uri = b.get("t", {}).get("value", "")
            h = h_uri.rsplit("/", 1)[-1]
            t = t_uri.rsplit("/", 1)[-1]
            if self._qid_only(h) and self._qid_only(t):
                out.append(
                    {
                        self.mcfg.field_head: h,
                        self.mcfg.field_rel: pid,
                        self.mcfg.field_tail: t,
                    }
                )
        return out

    def count_triples(self, pid: str) -> int:
        if pid in self._count_cache:
            return self._count_cache[pid]
        sample = self.sample_triples_any(pid, 1)
        n = 1 if sample else 0
        self._count_cache[pid] = n
        return n

    def sample_triples_any(self, pid: str, n: int) -> List[Dict]:
        if n <= 0 or not self._pid_only(pid):
            return []
        n_eff = min(int(n), self.any_fetch)
        query = f"""
        SELECT ?h ?t WHERE {{
          ?h wdt:{pid} ?t .
        }}
        LIMIT {n_eff}
        """
        try:
            res = self._run_sparql(query)
            return self._extract_triples(res, pid)
        except Exception:  # noqa: BLE001
            return []

    def sample_triples_attach_to_v(self, pid: str, v: Set[str], n: int) -> List[Dict]:
        if n <= 0 or not v or not self._pid_only(pid):
            return []
        v_list = self._select_v_values(v)
        if not v_list:
            return []
        values_v = " ".join(f"wd:{q}" for q in v_list)
        n_eff = min(int(n), self.attach_fetch)
        query = f"""
        SELECT ?h ?t WHERE {{
          VALUES ?v {{ {values_v} }}
          {{
            ?v wdt:{pid} ?t .
            BIND(?v AS ?h)
          }}
          UNION
          {{
            ?h wdt:{pid} ?v .
            BIND(?v AS ?t)
          }}
        }}
        LIMIT {n_eff}
        """
        try:
            res = self._run_sparql(query)
            return self._extract_triples(res, pid)
        except Exception:  # noqa: BLE001
            return []

    def sample_triples_attach_to_v_typed(
        self,
        pid: str,
        v: Set[str],
        n: int,
        subject_types: List[str],
        object_types: List[str],
    ) -> List[Dict]:
        if n <= 0 or not v or not self._pid_only(pid):
            return []
        v_list = self._select_v_values(v)
        if not v_list:
            return []
        subj = [x for x in subject_types[: self.max_type_values] if self._qid_only(x)]
        obj = [x for x in object_types[: self.max_type_values] if self._qid_only(x)]
        values_v = " ".join(f"wd:{q}" for q in v_list)
        n_eff = min(int(n), self.attach_fetch)

        typed_blocks: List[str] = []
        if subj:
            values_subj = " ".join(f"wd:{q}" for q in subj)
            typed_blocks.append(
                f"""
                VALUES ?scls {{ {values_subj} }}
                FILTER EXISTS {{ ?h wdt:P31/wdt:P279* ?scls . }}
                """
            )
        if obj:
            values_obj = " ".join(f"wd:{q}" for q in obj)
            typed_blocks.append(
                f"""
                VALUES ?ocls {{ {values_obj} }}
                FILTER EXISTS {{ ?t wdt:P31/wdt:P279* ?ocls . }}
                """
            )
        typed_filter = "\n".join(typed_blocks)

        query = f"""
        SELECT ?h ?t WHERE {{
          VALUES ?v {{ {values_v} }}
          {{
            ?v wdt:{pid} ?t .
            BIND(?v AS ?h)
          }}
          UNION
          {{
            ?h wdt:{pid} ?v .
            BIND(?v AS ?t)
          }}
          {typed_filter}
        }}
        LIMIT {n_eff}
        """
        try:
            res = self._run_sparql(query)
            return self._extract_triples(res, pid)
        except Exception:  # noqa: BLE001
            return []

    def fetch_entities_of_class(self, class_qid: str, limit: int) -> List[str]:
        if limit <= 0 or not self._qid_only(class_qid):
            return []
        key = (class_qid, int(limit))
        if key in self._class_entity_cache:
            return list(self._class_entity_cache[key])
        query = f"""
        SELECT ?e WHERE {{
          ?e wdt:P31/wdt:P279* wd:{class_qid} .
        }}
        LIMIT {int(limit)}
        """
        try:
            res = self._run_sparql(query)
            entities: List[str] = []
            for b in res.get("results", {}).get("bindings", []):
                e_uri = b.get("e", {}).get("value", "")
                q = e_uri.rsplit("/", 1)[-1]
                if self._qid_only(q):
                    entities.append(q)
        except Exception:  # noqa: BLE001
            entities = []
        self._class_entity_cache[key] = entities
        return entities


def load_property_domain_range_types_map(json_path: str) -> Dict[str, Dict[str, List[str]]]:
    path = Path(json_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return {}
    out: Dict[str, Dict[str, List[str]]] = {}
    for rec in data:
        if not isinstance(rec, dict):
            continue
        pid = str(rec.get("property_id", "")).strip()
        if not pid:
            continue
        subj = rec.get("valid_subject_type_ids", [])
        obj = rec.get("valid_object_type_ids", [])
        out[pid] = {
            "subject": [str(x) for x in subj] if isinstance(subj, list) else [],
            "object": [str(x) for x in obj] if isinstance(obj, list) else [],
        }
    return out


def build_backbone_seed_entities(
    quotas: Dict[str, int],
    rel_dom_rng_types: Dict[str, Dict[str, List[str]]],
    ts: WikidataSparqlTripleSource,
    *,
    backbone_top_k: int,
    entities_per_class: int,
    max_seed_entities: int,
) -> List[str]:
    class_scores: Dict[str, int] = defaultdict(int)
    for rel, q in quotas.items():
        if q <= 0:
            continue
        types = rel_dom_rng_types.get(rel, {})
        for c in types.get("subject", []):
            class_scores[c] += int(q)
        for c in types.get("object", []):
            class_scores[c] += int(q)
    ranked = sorted(class_scores.items(), key=lambda kv: kv[1], reverse=True)
    selected = [c for c, _ in ranked[: max(1, int(backbone_top_k))]]

    acc: List[str] = []
    seen = set()
    for c in selected:
        ents = ts.fetch_entities_of_class(c, limit=int(entities_per_class))
        for e in ents:
            if e not in seen:
                seen.add(e)
                acc.append(e)
                if len(acc) >= int(max_seed_entities):
                    return acc
    return acc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allocation_json", required=True)
    ap.add_argument("--properties_json", default="data/raw/wikidata_ontology.properties.json")
    ap.add_argument("--output_triples", default="data/connectedgraph/connected_allocation_sample.triples.jsonl")
    ap.add_argument("--output_metadata", default="data/connectedgraph/connected_allocation_sample.metadata.json")
    ap.add_argument("--checkpoint_path", default="data/connectedgraph/phase4_connected_realization.slurm.checkpoint.json")

    ap.add_argument("--endpoint_url", default="https://query.wikidata.org/sparql")
    ap.add_argument("--user_agent", required=True)
    ap.add_argument("--any_fetch", type=int, default=200)
    ap.add_argument("--attach_fetch", type=int, default=200)
    ap.add_argument("--max_v_for_values", type=int, default=30)
    ap.add_argument("--timeout_sec", type=int, default=30)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--max_type_values", type=int, default=12)

    ap.add_argument("--attempts", type=int, default=10)
    ap.add_argument("--rcl_size", type=int, default=10)
    ap.add_argument("--anchor_fraction", type=float, default=0.2)
    ap.add_argument("--overlap_probe_triples", type=int, default=200)
    ap.add_argument("--non_strict", action="store_true")
    ap.add_argument("--seed", type=int, default=42)

    ap.add_argument("--use_backbone_seed", action="store_true")
    ap.add_argument("--backbone_top_k", type=int, default=20)
    ap.add_argument("--backbone_entities_per_class", type=int, default=80)
    ap.add_argument("--backbone_max_seed_entities", type=int, default=1000)

    ap.add_argument("--use_controlled_relaxation", action="store_true")
    ap.add_argument("--resume_from_checkpoint", action="store_true")
    ap.add_argument("--checkpoint_every_relations", type=int, default=1)
    ap.add_argument("--micro_fill_chunk_size", type=int, default=20)
    ap.add_argument("--stall_max_rounds", type=int, default=25)
    ap.add_argument("--max_fail_per_relation", type=int, default=3)
    ap.add_argument("--seed_min_attachable_fraction", type=float, default=0.05)
    ap.add_argument("--seed_expand_rounds", type=int, default=3)
    ap.add_argument("--seed_expand_relations", type=int, default=20)
    ap.add_argument("--seed_expand_triples_per_relation", type=int, default=3)
    ap.add_argument("--bridge_seed_relations", type=int, default=15)
    ap.add_argument("--bridge_seed_triples_per_relation", type=int, default=3)
    ap.add_argument("--bridge_seed_new_entities_target", type=int, default=25)
    ap.add_argument("--capacity_probe_rounds", type=int, default=3)
    ap.add_argument("--zero_triple_force_bootstrap_rounds", type=int, default=5)

    args = ap.parse_args()
    random.seed(args.seed)

    rows = load_allocations_json(args.allocation_json)
    quotas, by_pattern = build_relation_quotas(rows)
    if not quotas:
        raise RuntimeError("No positive quotas from allocation JSON.")

    mcfg = MongoConfig(field_head="h", field_rel="r", field_tail="t")
    rcfg = RealizationConfig(
        attempts=max(1, args.attempts),
        rcl_size=max(1, args.rcl_size),
        anchor_fraction=max(0.0, min(1.0, args.anchor_fraction)),
        overlap_probe_triples=max(1, args.overlap_probe_triples),
        strict_quotas=not args.non_strict,
    )
    ts = WikidataSparqlTripleSource(
        mcfg,
        endpoint_url=args.endpoint_url,
        user_agent=args.user_agent,
        any_fetch=args.any_fetch,
        attach_fetch=args.attach_fetch,
        max_v_for_values=args.max_v_for_values,
        timeout_sec=args.timeout_sec,
        retries=args.retries,
        max_type_values=args.max_type_values,
    )

    rel_types = load_property_domain_range_types_map(args.properties_json)
    initial_entities: List[str] = []
    if args.use_backbone_seed:
        initial_entities = build_backbone_seed_entities(
            quotas,
            rel_types,
            ts,
            backbone_top_k=args.backbone_top_k,
            entities_per_class=args.backbone_entities_per_class,
            max_seed_entities=args.backbone_max_seed_entities,
        )

    def progress(event: str, payload: Dict) -> None:
        print(f"[phase4] {event} {payload}", flush=True)

    triples, achieved = realize_connected_graph(
        quotas=quotas,
        ts=ts,
        mcfg=mcfg,
        rcfg=rcfg,
        progress_cb=progress,
        initial_entities=initial_entities,
        relation_type_constraints=rel_types,
        use_controlled_relaxation=bool(args.use_controlled_relaxation),
        checkpoint_path=args.checkpoint_path,
        resume_from_checkpoint=bool(args.resume_from_checkpoint),
        checkpoint_every_relations=max(1, args.checkpoint_every_relations),
        micro_fill_chunk_size=max(1, args.micro_fill_chunk_size),
        stall_max_rounds=max(1, args.stall_max_rounds),
        max_fail_per_relation=max(1, args.max_fail_per_relation),
        seed_min_attachable_fraction=max(0.0, min(1.0, args.seed_min_attachable_fraction)),
        seed_expand_rounds=max(1, args.seed_expand_rounds),
        seed_expand_relations=max(1, args.seed_expand_relations),
        seed_expand_triples_per_relation=max(1, args.seed_expand_triples_per_relation),
        bridge_seed_relations=max(1, args.bridge_seed_relations),
        bridge_seed_triples_per_relation=max(1, args.bridge_seed_triples_per_relation),
        bridge_seed_new_entities_target=max(1, args.bridge_seed_new_entities_target),
        capacity_probe_rounds=max(1, args.capacity_probe_rounds),
        zero_triple_force_bootstrap_rounds=max(1, args.zero_triple_force_bootstrap_rounds),
    )

    Path(args.output_triples).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_triples, "w", encoding="utf-8") as f:
        for tr in triples:
            f.write(json.dumps(tr, ensure_ascii=False) + "\n")

    metadata = {
        "target_total_triples": int(sum(quotas.values())),
        "achieved_total_triples": int(sum(achieved.values())),
        "relation_quotas": quotas,
        "achieved_per_relation": achieved,
        "pattern_relation_quotas": by_pattern,
        "connected_undirected": bool(is_connected_undirected(triples, mcfg)),
        "config": vars(args),
        "seed_entity_count": len(initial_entities),
    }
    with open(args.output_metadata, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"[phase4] wrote triples: {args.output_triples}", flush=True)
    print(f"[phase4] wrote metadata: {args.output_metadata}", flush=True)


if __name__ == "__main__":
    main()
