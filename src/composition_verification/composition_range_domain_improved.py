#!/usr/bin/env python3
"""
Verify composition candidates on Wikidata (WDQS) efficiently.

Key improvements vs the previous version:
- Retrieve chain sample once per (r1,r2) doc.
 - Discover witnessed targets using VALUES ?rt with GROUP BY COUNT(DISTINCT pair): small, stable responses.
- Do NOT loop over all candidate targets; loop only over witnessed targets.
- Fetch examples only for top witnessed targets (bounded), not for every target.
- Deterministic sampling option for reproducibility (seed derived from r1,r2,offset).
- Doc-level checkpointing only after successful write; transient WDQS failures do NOT advance checkpoint.
- Doc-level error logging (no per-target spam on chain/discovery failure).
"""

import argparse
import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from bson import ObjectId
from pymongo import MongoClient, ASCENDING


LOG = logging.getLogger("composition")
WD_ENTITY_PREFIX = "http://www.wikidata.org/entity/"


# -----------------------------
# Data models
# -----------------------------

@dataclass
class CompositionReport:
    rel1: str
    rel2: str
    rel_target: str
    mode: str
    chain_pairs_examined: int
    chain_pairs_with_shortcut: int
    chain_pairs_missing_shortcut: int
    sample_confidence: float
    examples_missing_shortcut: List[Dict[str, str]]
    examples_with_shortcut: List[Dict[str, str]]
    notes: List[str]


@dataclass
class ChainSample:
    rel1: str
    rel2: str
    mode: str
    chain_triplets: List[Dict[str, str]]         # representative triplets for explainability
    chain_pairs: List[Tuple[str, str]]           # unique (x,z)
    notes: List[str]


class TransientSparqlError(RuntimeError):
    """Retryable/transient WDQS error (timeouts, 429, 5xx)."""


# -----------------------------
# Utilities
# -----------------------------

def write_report_line(report_log, record: Dict[str, Any]) -> None:
    if not report_log:
        return
    report_log.write(json.dumps(record, ensure_ascii=True) + "\n")
    report_log.flush()


def normalize_doc_id(value: Any) -> Optional[Any]:
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str):
        value = value.strip()
        if len(value) == 24:
            try:
                return ObjectId(value)
            except Exception:
                return None
    return value


def get_checkpoint(meta_col, checkpoint_id: str) -> Optional[Any]:
    doc = meta_col.find_one({"_id": checkpoint_id}, {"last_doc_id": 1})
    if not doc:
        return None
    return doc.get("last_doc_id")


def set_checkpoint(
    meta_col,
    checkpoint_id: str,
    last_doc_id: Any,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "last_doc_id": last_doc_id,
        "updated_at": time.time(),
    }
    if extra:
        payload.update(extra)
    meta_col.update_one({"_id": checkpoint_id}, {"$set": payload}, upsert=True)


def get_jsonl_checkpoint(checkpoint_path: str) -> int:
    if not checkpoint_path or not os.path.exists(checkpoint_path):
        return 0
    try:
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        value = int(obj.get("last_line", 0))
        return value if value >= 0 else 0
    except Exception:
        return 0


def set_jsonl_checkpoint(checkpoint_path: str, last_line: int) -> None:
    payload = {
        "last_line": int(last_line),
        "updated_at": time.time(),
    }
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def normalize_targets_input(
    checker: "WikidataCompositionChecker",
    targets: Any,
) -> Tuple[List[str], Dict[str, str], int]:
    if not isinstance(targets, list):
        return [], {}, 0

    normalized: List[str] = []
    pid_to_original: Dict[str, str] = {}
    seen: set = set()
    invalid_count = 0

    for raw in targets:
        candidate: Optional[str] = None
        original: Optional[str] = None

        if isinstance(raw, str):
            candidate = raw
            original = raw
        elif isinstance(raw, dict):
            t = raw.get("t")
            if isinstance(t, str):
                candidate = t
                original = t

        if not candidate:
            invalid_count += 1
            continue

        try:
            pid = checker.normalize_pid(candidate)
        except ValueError:
            invalid_count += 1
            continue

        if pid in seen:
            continue
        seen.add(pid)
        normalized.append(pid)
        pid_to_original[pid] = original or pid

    return normalized, pid_to_original, invalid_count


# -----------------------------
# Core checker
# -----------------------------

class WikidataCompositionChecker:
    def __init__(
        self,
        endpoint: str = "https://query.wikidata.org/sparql",
        user_agent: str = "CompositionChecker/2.0 (contact: you@example.com)",
        timeout_s: int = 60,
        max_retries: int = 3,
        backoff_s: float = 2.0,
        min_delay_s: float = 0.2,
        max_delay_s: float = 0.5,
    ) -> None:
        self.endpoint = endpoint
        self.headers = {
            "Accept": "application/sparql-results+json",
            "User-Agent": user_agent,
        }
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.min_delay_s = min_delay_s
        self.max_delay_s = max_delay_s
        self.sparql_post_count = 0

    def _sleep_between_queries(self) -> None:
        delay_min = max(0.0, self.min_delay_s)
        delay_max = max(delay_min, self.max_delay_s)
        if delay_max <= 0:
            return
        time.sleep(random.uniform(delay_min, delay_max))

    @staticmethod
    def normalize_pid(pid: str) -> str:
        pid = pid.strip()
        if pid.startswith("wdt:"):
            pid = pid[4:]
        if pid.startswith("P") and pid[1:].isdigit():
            return pid

        # Accept full IRI: http://www.wikidata.org/prop/direct/P31
        if "/P" in pid:
            p = pid[pid.rfind("P") :]
            if p.startswith("P") and p[1:].isdigit():
                return p

        raise ValueError(f"Unrecognized property id format: {pid}")

    @staticmethod
    def _pid_to_wdt(pid: str) -> str:
        pid = WikidataCompositionChecker.normalize_pid(pid)
        return f"wdt:{pid}"

    def _run_sparql(self, query: str, *, context: Optional[str] = None) -> Dict[str, Any]:
        last_err: Optional[Exception] = None
        query_hash = hashlib.sha1(query.encode("utf-8")).hexdigest()[:10]

        for attempt in range(1, self.max_retries + 1):
            try:
                self._sleep_between_queries()
                self.sparql_post_count += 1

                r = requests.post(
                    self.endpoint,
                    data={"query": query},
                    headers=self.headers,
                    timeout=self.timeout_s,
                )

                if r.status_code == 429:
                    retry_after = r.headers.get("Retry-After")
                    sleep_s = float(retry_after) if retry_after else (self.backoff_s * attempt)
                    LOG.warning("WDQS 429 (rate limit) hash=%s context=%s sleep=%.2fs", query_hash, context or "", sleep_s)
                    time.sleep(sleep_s)
                    last_err = TransientSparqlError(f"429 rate limit (hash={query_hash})")
                    continue

                if r.status_code >= 500:
                    LOG.warning("WDQS %s (server error) hash=%s context=%s", r.status_code, query_hash, context or "")
                    last_err = TransientSparqlError(f"{r.status_code} server error (hash={query_hash})")
                    time.sleep(self.backoff_s * attempt)
                    continue

                if r.status_code >= 400:
                    detail = r.text.strip() if r.text else "no response body"
                    LOG.debug("SPARQL query (hash=%s):\n%s", query_hash, query)
                    raise RuntimeError(f"SPARQL error {r.status_code}: {detail}")

                r.raise_for_status()
                return r.json()

            except requests.exceptions.Timeout as e:
                last_err = e
                LOG.warning("WDQS timeout hash=%s context=%s attempt=%d/%d", query_hash, context or "", attempt, self.max_retries)
                time.sleep(self.backoff_s * attempt)
                continue
            except TransientSparqlError as e:
                last_err = e
                time.sleep(self.backoff_s * attempt)
                continue
            except Exception as e:
                last_err = e
                time.sleep(self.backoff_s * attempt)

        # If last error looks transient, raise as transient so caller can avoid checkpoint advance.
        if isinstance(last_err, (requests.exceptions.Timeout, TransientSparqlError)):
            raise TransientSparqlError(f"SPARQL failed after retries: {last_err}") from last_err
        raise RuntimeError(f"SPARQL failed after retries: {last_err}") from last_err

    def get_chain_sample(
        self,
        rel1: str,
        rel2: str,
        *,
        mode: str = "wdt",
        limit: int = 1000,
        offset: int = 0,
        sample_n: Optional[int] = None,
        require_distinct_nodes: bool = False,
        exclude_self_loops: bool = False,
        deterministic_sample: bool = False,
    ) -> ChainSample:
        if mode != "wdt":
            raise NotImplementedError("Only 'wdt' mode is implemented in this compact checker.")

        p1 = self._pid_to_wdt(rel1)
        p2 = self._pid_to_wdt(rel2)

        distinct_filters = []
        if require_distinct_nodes:
            distinct_filters.append("FILTER(?x != ?y && ?y != ?z && ?x != ?z)")
        if exclude_self_loops and not require_distinct_nodes:
            distinct_filters.append("FILTER(?x != ?z)")
        filter_block = "\n  ".join(distinct_filters)

        chain_query = f"""
SELECT ?x ?y ?z WHERE {{
  ?x {p1} ?y .
  ?y {p2} ?z .
  {filter_block}
  FILTER(STRSTARTS(STR(?x), "{WD_ENTITY_PREFIX}"))
  FILTER(STRSTARTS(STR(?y), "{WD_ENTITY_PREFIX}"))
  FILTER(STRSTARTS(STR(?z), "{WD_ENTITY_PREFIX}"))
}}
LIMIT {limit}
OFFSET {offset}
""".strip()

        chain_json = self._run_sparql(
            chain_query,
            context=f"chain rel1={rel1} rel2={rel2} limit={limit} offset={offset}",
        )
        chain_rows = chain_json.get("results", {}).get("bindings", [])
        raw_triplets = [
            {"x": b["x"]["value"], "y": b["y"]["value"], "z": b["z"]["value"]}
            for b in chain_rows
            if "x" in b and "y" in b and "z" in b
        ]

        # Keep one representative triplet per (x,z).
        xz_to_triplet: Dict[Tuple[str, str], Dict[str, str]] = {}
        for t in raw_triplets:
            key = (t["x"], t["z"])
            if key not in xz_to_triplet:
                xz_to_triplet[key] = t

        notes: List[str] = []
        if not xz_to_triplet:
            notes.append("No chain instances returned for this page (LIMIT/OFFSET).")
            return ChainSample(rel1=rel1, rel2=rel2, mode=mode, chain_triplets=[], chain_pairs=[], notes=notes)

        chain_pairs = list(xz_to_triplet.keys())

        if sample_n is not None and sample_n < len(chain_pairs):
            if deterministic_sample:
                seed_material = f"{rel1}|{rel2}|{offset}|{limit}"
                seed = int(hashlib.sha1(seed_material.encode("utf-8")).hexdigest()[:8], 16)
                rng = random.Random(seed)
                chain_pairs = rng.sample(chain_pairs, sample_n)
                notes.append(f"Deterministically sampled {sample_n} chain pairs (seed={seed}).")
            else:
                chain_pairs = random.sample(chain_pairs, sample_n)
                notes.append(f"Sampled down to {sample_n} chain pairs from the page.")

        chain_triplets = [xz_to_triplet[p] for p in chain_pairs]
        return ChainSample(rel1=rel1, rel2=rel2, mode=mode, chain_triplets=chain_triplets, chain_pairs=chain_pairs, notes=notes)

    def discover_target_counts_for_pairs(
        self,
        chain_sample: ChainSample,
        targets: List[str],
        *,
        mode: Optional[str] = None,
        pairs_batch_size: int = 300,
        targets_batch_size: int = 60,
    ) -> Tuple[Dict[str, int], List[str], List[str]]:
        """
        Returns:
          - counts: pid -> count of (x,z) pairs in sample where ?x wdt:pid ?z holds
          - notes: batching notes
          - invalid_targets: list of invalid target ids encountered
        """
        if mode is None:
            mode = chain_sample.mode
        if mode != "wdt":
            raise NotImplementedError("Only 'wdt' mode is implemented in this compact checker.")
        if mode != chain_sample.mode:
            raise ValueError("Mode mismatch between chain sample and requested mode.")

        chain_pairs = chain_sample.chain_pairs
        notes: List[str] = []

        # Normalize & dedupe targets
        normalized_targets: List[str] = []
        seen: set = set()
        invalid: List[str] = []
        for t in targets:
            try:
                pid = self.normalize_pid(t)
            except ValueError:
                invalid.append(t)
                continue
            if pid in seen:
                continue
            seen.add(pid)
            normalized_targets.append(pid)

        if invalid:
            notes.append(f"Ignored {len(invalid)} invalid targets during discovery.")
        if not chain_pairs or not normalized_targets:
            return {}, notes, invalid

        def _chunked(seq, n):
            for i in range(0, len(seq), n):
                yield seq[i : i + n]

        if len(chain_pairs) > pairs_batch_size:
            notes.append(f"Target discovery batched pairs in chunks of {pairs_batch_size}.")
        if len(normalized_targets) > targets_batch_size:
            notes.append(f"Target discovery batched targets in chunks of {targets_batch_size}.")

        counts: Dict[str, int] = {}
        wdt_targets = [f"wdt:{pid}" for pid in normalized_targets]

        for target_batch in _chunked(wdt_targets, targets_batch_size):
            targets_clause = " ".join(target_batch)
            for pair_batch in _chunked(chain_pairs, pairs_batch_size):
                values_lines = "\n".join(f"( <{x}> <{z}> )" for (x, z) in pair_batch)

                discovery_query = f"""
SELECT ?rt (COUNT(DISTINCT ?pair) AS ?c) WHERE {{
  VALUES ?rt {{ {targets_clause} }}
  VALUES (?x ?z) {{
    {values_lines}
  }}
  BIND(CONCAT(STR(?x), "|", STR(?z)) AS ?pair)
  ?x ?rt ?z .
}}
GROUP BY ?rt
""".strip()

                sample_pairs = "; ".join(f"{x},{z}" for (x, z) in pair_batch[:2])
                sample_targets = " ".join(target_batch[:3])

                discovery_json = self._run_sparql(
                    discovery_query,
                    context=(
                        f"discover-count rel1={chain_sample.rel1} rel2={chain_sample.rel2} "
                        f"pairs_batch={len(pair_batch)} targets_batch={len(target_batch)} "
                        f"sample_pairs={sample_pairs} sample_targets={sample_targets}"
                    ),
                )

                rows = discovery_json.get("results", {}).get("bindings", [])
                for b in rows:
                    if "rt" not in b or "c" not in b:
                        continue
                    rt_val = b["rt"]["value"]
                    pid = self.normalize_pid(rt_val)
                    c = int(b["c"]["value"])
                    counts[pid] = counts.get(pid, 0) + c

        return counts, notes, invalid

    def fetch_example_pairs_for_target(
        self,
        chain_sample: ChainSample,
        target_pid: str,
        *,
        pairs_batch_size: int = 300,
        examples_k: int = 5,
    ) -> List[Tuple[str, str]]:
        """
        Fetch up to examples_k (x,z) pairs among the chain_sample for which ?x wdt:target_pid ?z holds.
        """
        if examples_k <= 0:
            return []

        chain_pairs = chain_sample.chain_pairs
        if not chain_pairs:
            return []

        pt = self._pid_to_wdt(target_pid)

        def _chunked(seq, n):
            for i in range(0, len(seq), n):
                yield seq[i : i + n]

        examples: List[Tuple[str, str]] = []
        for pair_batch in _chunked(chain_pairs, pairs_batch_size):
            if len(examples) >= examples_k:
                break
            values_lines = "\n".join(f"( <{x}> <{z}> )" for (x, z) in pair_batch)
            q = f"""
SELECT ?x ?z WHERE {{
  VALUES (?x ?z) {{
    {values_lines}
  }}
  ?x {pt} ?z .
}}
LIMIT {examples_k}
""".strip()

            js = self._run_sparql(
                q,
                context=f"examples rel1={chain_sample.rel1} rel2={chain_sample.rel2} target={target_pid} batch={len(pair_batch)}",
            )
            rows = js.get("results", {}).get("bindings", [])
            for b in rows:
                if "x" in b and "z" in b:
                    examples.append((b["x"]["value"], b["z"]["value"]))
                    if len(examples) >= examples_k:
                        break

        return examples


# -----------------------------
# Core evaluation
# -----------------------------

def evaluate_composition_for_doc(
    checker: WikidataCompositionChecker,
    *,
    r1: str,
    r2: str,
    targets: List[str],
    pid_to_original: Dict[str, str],
    invalid_input_targets_count: int,
    limit: int,
    offset: int,
    sample_n: Optional[int],
    deterministic_sample: bool,
    examples_k: int,
    max_example_targets: int,
    pairs_batch_size: int,
    targets_batch_size: int,
    require_distinct_nodes: bool,
    exclude_self_loops: bool,
) -> Dict[str, Any]:
    # Chain sample
    chain_sample = checker.get_chain_sample(
        r1,
        r2,
        limit=limit,
        offset=offset,
        sample_n=sample_n,
        require_distinct_nodes=require_distinct_nodes,
        exclude_self_loops=exclude_self_loops,
        deterministic_sample=deterministic_sample,
    )

    if not chain_sample.chain_pairs:
        return {
            "empty_chain": True,
            "base_notes": chain_sample.notes,
            "chain_pairs_examined": 0,
            "composition": {},
            "composition_discovery_found": [],
            "saved_targets": 0,
        }

    counts, discovery_notes, invalid_targets_discovery = checker.discover_target_counts_for_pairs(
        chain_sample,
        targets,
        pairs_batch_size=pairs_batch_size,
        targets_batch_size=targets_batch_size,
    )

    total_pairs = len(chain_sample.chain_pairs)
    witnessed = [(pid, c) for pid, c in counts.items() if c > 0]
    witnessed.sort(key=lambda x: x[1], reverse=True)

    pair_to_triplet: Dict[Tuple[str, str], Dict[str, str]] = {}
    for triplet in chain_sample.chain_triplets:
        pair_to_triplet.setdefault((triplet["x"], triplet["z"]), triplet)

    now = datetime.utcnow().isoformat()
    base_notes = list(chain_sample.notes)
    base_notes.extend(discovery_notes)
    if invalid_input_targets_count > 0:
        base_notes.append(f"Invalid targets ignored from input shape: {invalid_input_targets_count}.")
    if invalid_targets_discovery:
        base_notes.append(f"Invalid targets ignored during discovery: {len(invalid_targets_discovery)}.")
    base_notes.append("sample_confidence is computed over retrieved chain pairs (page and optional sample), not the full Wikidata graph.")
    base_notes.append("examples_missing_shortcut are approximate and may include true positives within the sample.")

    example_pids = [pid for (pid, _) in witnessed[:max_example_targets]] if examples_k > 0 else []
    examples_map: Dict[str, List[Tuple[str, str]]] = {}
    for pid in example_pids:
        try:
            ex_pairs = checker.fetch_example_pairs_for_target(
                chain_sample,
                pid,
                pairs_batch_size=pairs_batch_size,
                examples_k=examples_k,
            )
            examples_map[pid] = ex_pairs
        except Exception:
            # examples are best-effort; keep doc success
            examples_map[pid] = []

    if deterministic_sample:
        seed_material = f"{r1}|{r2}|{offset}|missing"
        seed = int(hashlib.sha1(seed_material.encode("utf-8")).hexdigest()[:8], 16)
        miss_rng = random.Random(seed)
    else:
        miss_rng = random

    composition: Dict[str, Any] = {}
    saved_targets = 0

    for pid, with_n in witnessed:
        rel_target_key = pid_to_original.get(pid, pid)
        with_n = min(with_n, total_pairs)
        missing_n = max(0, total_pairs - with_n)
        sample_confidence = with_n / total_pairs if total_pairs else 0.0

        examples_with_shortcut: List[Dict[str, str]] = []
        ex_pairs = examples_map.get(pid, [])
        for (x, z) in ex_pairs:
            t = pair_to_triplet.get((x, z))
            if t:
                examples_with_shortcut.append(t)
            if len(examples_with_shortcut) >= examples_k:
                break

        examples_missing_shortcut: List[Dict[str, str]] = []
        if examples_k > 0:
            witnessed_example_pairs = set(ex_pairs)
            candidates_missing = [p for p in chain_sample.chain_pairs if p not in witnessed_example_pairs]
            if candidates_missing:
                pick_n = min(examples_k, len(candidates_missing))
                picked = miss_rng.sample(candidates_missing, pick_n) if pick_n < len(candidates_missing) else candidates_missing
                for (x, z) in picked:
                    t = pair_to_triplet.get((x, z))
                    if t:
                        examples_missing_shortcut.append(t)

        report = CompositionReport(
            rel1=r1,
            rel2=r2,
            rel_target=rel_target_key,
            mode=chain_sample.mode,
            chain_pairs_examined=total_pairs,
            chain_pairs_with_shortcut=with_n,
            chain_pairs_missing_shortcut=missing_n,
            sample_confidence=sample_confidence,
            examples_missing_shortcut=examples_missing_shortcut,
            examples_with_shortcut=examples_with_shortcut,
            notes=list(base_notes),
        )

        composition[rel_target_key] = {
            "rel1": report.rel1,
            "rel2": report.rel2,
            "rel_target": report.rel_target,
            "mode": report.mode,
            "chain_pairs_examined": report.chain_pairs_examined,
            "chain_pairs_with_shortcut": report.chain_pairs_with_shortcut,
            "chain_pairs_missing_shortcut": report.chain_pairs_missing_shortcut,
            "sample_confidence": report.sample_confidence,
            "examples_missing_shortcut": report.examples_missing_shortcut,
            "examples_with_shortcut": report.examples_with_shortcut,
            "notes": report.notes,
            "checked_at": now,
        }
        saved_targets += 1

    discovery_found = [
        {"pid": pid, "count_pairs": count}
        for pid, count in counts.items()
        if count > 0
    ]

    return {
        "empty_chain": False,
        "base_notes": base_notes,
        "chain_pairs_examined": total_pairs,
        "composition": composition,
        "composition_discovery_found": discovery_found,
        "saved_targets": saved_targets,
    }


# -----------------------------
# Main driver
# -----------------------------

def run_candidates(
    mongo_uri: str,
    db_name: str,
    candidates_col: str,
    *,
    meta_col: str,
    checkpoint_id: str,
    pairs_compatibility: str,
    endpoint: str,
    user_agent: str,
    timeout_s: int,
    max_retries: int,
    backoff_s: float,
    min_delay_s: float,
    max_delay_s: float,
    limit: int,
    offset: int,
    sample_n: Optional[int],
    deterministic_sample: bool,
    examples_k: int,
    max_example_targets: int,
    pairs_batch_size: int,
    targets_batch_size: int,
    require_distinct_nodes: bool,
    exclude_self_loops: bool,
    log_every_docs: int,
    report_path: str,
) -> None:
    client = MongoClient(mongo_uri)
    db = client.get_database(db_name)
    cand_col = db.get_collection(candidates_col)
    meta_collection = db.get_collection(meta_col)

    report_log = open(report_path, "a", encoding="utf-8") if report_path else None

    try:
        base_query: Dict[str, Any] = {"pairs_compatibility": pairs_compatibility}

        last_doc_id_raw = get_checkpoint(meta_collection, checkpoint_id)
        last_doc_id = normalize_doc_id(last_doc_id_raw)
        if last_doc_id_raw is not None and last_doc_id is None:
            LOG.warning("Ignoring invalid checkpoint last_doc_id=%s", last_doc_id_raw)

        total_docs = cand_col.count_documents(base_query)
        LOG.info("Candidates with compatibility=%s: %d", pairs_compatibility, total_docs)

        checker = WikidataCompositionChecker(
            endpoint=endpoint,
            user_agent=user_agent,
            timeout_s=timeout_s,
            max_retries=max_retries,
            backoff_s=backoff_s,
            min_delay_s=min_delay_s,
            max_delay_s=max_delay_s,
        )

        processed_docs = 0
        saved_targets = 0
        skipped_docs_empty_chain = 0
        error_docs = 0

        def process_doc(doc: Dict[str, Any]) -> bool:
            """
            Returns True if doc processed successfully and checkpoint can advance.
            Returns False if transient failure occurred and doc should be retried later.
            """
            nonlocal processed_docs, saved_targets, skipped_docs_empty_chain, error_docs

            doc_id = doc.get("_id")
            r1 = doc.get("r1")
            r2 = doc.get("r2")
            raw_targets = doc.get("targets") or []

            if not r1 or not r2:
                LOG.warning("Skipping doc %s: missing r1/r2", doc_id)
                write_report_line(report_log, {"status": "skip", "doc_id": str(doc_id), "reason": "missing_r1_r2"})
                return True

            if not isinstance(raw_targets, list) or not raw_targets:
                LOG.info("Skipping doc %s: no targets", doc_id)
                write_report_line(report_log, {"status": "skip", "doc_id": str(doc_id), "rel1": r1, "rel2": r2, "reason": "no_targets"})
                return True

            targets, pid_to_original, invalid_input_targets_count = normalize_targets_input(checker, raw_targets)
            if not targets:
                LOG.info("Skipping doc %s: no valid targets after normalization", doc_id)
                write_report_line(
                    report_log,
                    {
                        "status": "skip",
                        "doc_id": str(doc_id),
                        "rel1": r1,
                        "rel2": r2,
                        "reason": "no_valid_targets",
                        "invalid_input_targets_count": invalid_input_targets_count,
                    },
                )
                return True

            sparql_posts_before = checker.sparql_post_count

            LOG.info("Composition verification: %s + %s (targets=%d)", r1, r2, len(targets))
            try:
                eval_result = evaluate_composition_for_doc(
                    checker,
                    r1=r1,
                    r2=r2,
                    targets=targets,
                    pid_to_original=pid_to_original,
                    invalid_input_targets_count=invalid_input_targets_count,
                    limit=limit,
                    offset=offset,
                    sample_n=sample_n,
                    deterministic_sample=deterministic_sample,
                    examples_k=examples_k,
                    max_example_targets=max_example_targets,
                    pairs_batch_size=pairs_batch_size,
                    targets_batch_size=targets_batch_size,
                    require_distinct_nodes=require_distinct_nodes,
                    exclude_self_loops=exclude_self_loops,
                )
            except TransientSparqlError as exc:
                error_docs += 1
                now = datetime.utcnow().isoformat()
                LOG.warning("Transient composition failure doc=%s r1=%s r2=%s err=%s", doc_id, r1, r2, exc)
                write_report_line(
                    report_log,
                    {
                        "status": "error",
                        "doc_id": str(doc_id),
                        "rel1": r1,
                        "rel2": r2,
                        "phase": "composition",
                        "error": str(exc),
                        "checked_at": now,
                    },
                )
                return False
            except Exception as exc:
                error_docs += 1
                now = datetime.utcnow().isoformat()
                LOG.exception("Permanent composition failure doc=%s r1=%s r2=%s", doc_id, r1, r2)
                write_report_line(
                    report_log,
                    {
                        "status": "error",
                        "doc_id": str(doc_id),
                        "rel1": r1,
                        "rel2": r2,
                        "phase": "composition",
                        "error": str(exc),
                        "checked_at": now,
                    },
                )
                return True

            if eval_result["empty_chain"]:
                skipped_docs_empty_chain += 1
                processed_docs += 1
                write_report_line(report_log, {"status": "skip", "doc_id": str(doc_id), "rel1": r1, "rel2": r2, "reason": "empty_chain_sample"})
                cand_col.update_one(
                    {"_id": doc_id},
                    {"$set": {
                        "rule_verification.composition_updated_at": datetime.utcnow().isoformat(),
                        "rule_verification.composition_notes": eval_result["base_notes"],
                    }},
                )
                return True

            update_fields: Dict[str, Any] = {}
            now = datetime.utcnow().isoformat()
            update_fields["rule_verification.composition_discovery_found"] = eval_result["composition_discovery_found"]
            for rel_target_key, result in eval_result["composition"].items():
                update_fields[f"rule_verification.composition.{rel_target_key}"] = result
                saved_targets += 1
                write_report_line(
                    report_log,
                    {
                        "status": "saved",
                        "doc_id": str(doc_id),
                        "rel1": r1,
                        "rel2": r2,
                        "rel_target": rel_target_key,
                        "chain_pairs_examined": result["chain_pairs_examined"],
                        "chain_pairs_with_shortcut": result["chain_pairs_with_shortcut"],
                        "sample_confidence": result["sample_confidence"],
                        "checked_at": now,
                    },
                )

            # Write once per doc
            update_fields["rule_verification.composition_updated_at"] = now
            update_fields["rule_verification.composition_chain_pairs_examined"] = eval_result["chain_pairs_examined"]
            update_fields["rule_verification.composition_notes"] = eval_result["base_notes"]
            sparql_posts_used = checker.sparql_post_count - sparql_posts_before
            update_fields["rule_verification.composition_sparql_posts_used"] = sparql_posts_used
            update_fields["rule_verification.composition_sparql_posts_total"] = checker.sparql_post_count

            cand_col.update_one({"_id": doc_id}, {"$set": update_fields})

            processed_docs += 1
            return True

        # Resume
        if last_doc_id is not None:
            LOG.info("Resuming after doc %s", last_doc_id)
            base_query["_id"] = {"$gt": last_doc_id}

        cursor = cand_col.find(
            base_query,
            {"r1": 1, "r2": 1, "targets": 1, "pairs_compatibility": 1},
        ).sort("_id", ASCENDING)

        for doc in cursor:
            ok = process_doc(doc)
            if ok:
                set_checkpoint(meta_collection, checkpoint_id, doc["_id"])
            else:
                # transient failure: stop run so rerun can retry same doc without skipping
                LOG.warning("Stopping due to transient failure; rerun will retry doc_id=%s", doc.get("_id"))
                break

            if log_every_docs and processed_docs % log_every_docs == 0:
                LOG.info(
                    "Progress: docs=%d/%d saved_targets=%d skipped_empty_chain=%d error_docs=%d sparql_posts=%d",
                    processed_docs,
                    total_docs,
                    saved_targets,
                    skipped_docs_empty_chain,
                    error_docs,
                    checker.sparql_post_count,
                )

        LOG.info(
            "Done. docs=%d saved_targets=%d skipped_empty_chain=%d error_docs=%d sparql_posts=%d",
            processed_docs,
            saved_targets,
            skipped_docs_empty_chain,
            error_docs,
            checker.sparql_post_count,
        )
        if report_path:
            LOG.info("Report appended to %s", report_path)

    finally:
        if report_log:
            report_log.close()


def run_candidates_jsonl(
    input_jsonl: str,
    output_jsonl: str,
    *,
    output_jsonl_compact: str,
    checkpoint_path: str,
    stats_path: str,
    resume: bool,
    endpoint: str,
    user_agent: str,
    timeout_s: int,
    max_retries: int,
    backoff_s: float,
    min_delay_s: float,
    max_delay_s: float,
    limit: int,
    offset: int,
    sample_n: Optional[int],
    deterministic_sample: bool,
    examples_k: int,
    max_example_targets: int,
    pairs_batch_size: int,
    targets_batch_size: int,
    require_distinct_nodes: bool,
    exclude_self_loops: bool,
    log_every_docs: int,
    report_path: str,
) -> None:
    checker = WikidataCompositionChecker(
        endpoint=endpoint,
        user_agent=user_agent,
        timeout_s=timeout_s,
        max_retries=max_retries,
        backoff_s=backoff_s,
        min_delay_s=min_delay_s,
        max_delay_s=max_delay_s,
    )
    report_log = open(report_path, "a", encoding="utf-8") if report_path else None
    compact_log = open(output_jsonl_compact, "a", encoding="utf-8") if output_jsonl_compact else None

    try:
        start_line = get_jsonl_checkpoint(checkpoint_path) if resume else 0
        if start_line > 0:
            LOG.info("Resuming JSONL mode after line %d", start_line)

        stats: Dict[str, Any] = {
            "input_jsonl": input_jsonl,
            "output_jsonl": output_jsonl,
            "output_jsonl_compact": output_jsonl_compact or "",
            "checkpoint_path": checkpoint_path,
            "started_at": datetime.utcnow().isoformat(),
            "resumed": bool(resume),
            "start_line": int(start_line),
            "lines_seen": 0,
            "nonempty_lines_seen": 0,
            "output_docs_written": 0,
            "output_compact_docs_written": 0,
            "success_docs": 0,
            "skipped_docs": 0,
            "error_docs": 0,
            "skip_reasons": {},
            "error_phases": {},
            "saved_targets": 0,
            "sparql_posts_total": 0,
            "stopped_on_transient": False,
            "stop_line": None,
            "stop_reason": "",
            "final_checkpoint_line": int(start_line),
        }

        def _inc(bucket: Dict[str, int], key: str) -> None:
            bucket[key] = bucket.get(key, 0) + 1

        def _write_output(out_doc: Dict[str, Any]) -> None:
            fout.write(json.dumps(out_doc, ensure_ascii=True) + "\n")
            fout.flush()
            stats["output_docs_written"] += 1
            if compact_log is not None:
                compact_doc = dict(out_doc)
                compact_doc.pop("targets", None)
                compact_log.write(json.dumps(compact_doc, ensure_ascii=True) + "\n")
                compact_log.flush()
                stats["output_compact_docs_written"] += 1

        processed_docs = 0
        saved_targets = 0
        skipped_docs_empty_chain = 0
        error_docs = 0

        with open(input_jsonl, "r", encoding="utf-8") as fin, open(output_jsonl, "a", encoding="utf-8") as fout:
            for line_no, raw_line in enumerate(fin, start=1):
                stats["lines_seen"] += 1
                if line_no <= start_line:
                    continue
                line = raw_line.strip()
                if not line:
                    set_jsonl_checkpoint(checkpoint_path, line_no)
                    stats["final_checkpoint_line"] = line_no
                    continue
                stats["nonempty_lines_seen"] += 1

                try:
                    doc = json.loads(line)
                except Exception as exc:
                    error_docs += 1
                    stats["error_docs"] += 1
                    _inc(stats["error_phases"], "parse_jsonl")
                    write_report_line(
                        report_log,
                        {
                            "status": "error",
                            "line_no": line_no,
                            "phase": "parse_jsonl",
                            "error": str(exc),
                            "checked_at": datetime.utcnow().isoformat(),
                        },
                    )
                    parse_error_doc = {
                        "_line_no": line_no,
                        "_raw_line": line[:1000],
                        "rule_verification": {
                            "composition_run": {
                                "status": "error",
                                "reason": "parse_jsonl",
                                "error": str(exc),
                                "checked_at": datetime.utcnow().isoformat(),
                            }
                        },
                    }
                    _write_output(parse_error_doc)
                    set_jsonl_checkpoint(checkpoint_path, line_no)
                    stats["final_checkpoint_line"] = line_no
                    continue

                r1 = doc.get("r1")
                r2 = doc.get("r2")
                raw_targets = doc.get("targets") or []
                if not r1 or not r2:
                    out_doc = dict(doc)
                    out_doc["rule_verification"] = out_doc.get("rule_verification", {})
                    out_doc["rule_verification"]["composition_run"] = {
                        "status": "skip",
                        "reason": "missing_r1_r2",
                        "checked_at": datetime.utcnow().isoformat(),
                    }
                    _write_output(out_doc)
                    stats["skipped_docs"] += 1
                    _inc(stats["skip_reasons"], "missing_r1_r2")
                    write_report_line(report_log, {"status": "skip", "line_no": line_no, "reason": "missing_r1_r2"})
                    set_jsonl_checkpoint(checkpoint_path, line_no)
                    stats["final_checkpoint_line"] = line_no
                    continue
                if not isinstance(raw_targets, list) or not raw_targets:
                    out_doc = dict(doc)
                    out_doc["rule_verification"] = out_doc.get("rule_verification", {})
                    out_doc["rule_verification"]["composition_run"] = {
                        "status": "skip",
                        "reason": "no_targets",
                        "checked_at": datetime.utcnow().isoformat(),
                    }
                    _write_output(out_doc)
                    stats["skipped_docs"] += 1
                    _inc(stats["skip_reasons"], "no_targets")
                    write_report_line(report_log, {"status": "skip", "line_no": line_no, "rel1": r1, "rel2": r2, "reason": "no_targets"})
                    set_jsonl_checkpoint(checkpoint_path, line_no)
                    stats["final_checkpoint_line"] = line_no
                    continue

                targets, pid_to_original, invalid_input_targets_count = normalize_targets_input(checker, raw_targets)
                if not targets:
                    out_doc = dict(doc)
                    out_doc["rule_verification"] = out_doc.get("rule_verification", {})
                    out_doc["rule_verification"]["composition_run"] = {
                        "status": "skip",
                        "reason": "no_valid_targets",
                        "invalid_input_targets_count": invalid_input_targets_count,
                        "checked_at": datetime.utcnow().isoformat(),
                    }
                    _write_output(out_doc)
                    stats["skipped_docs"] += 1
                    _inc(stats["skip_reasons"], "no_valid_targets")
                    write_report_line(
                        report_log,
                        {
                            "status": "skip",
                            "line_no": line_no,
                            "rel1": r1,
                            "rel2": r2,
                            "reason": "no_valid_targets",
                            "invalid_input_targets_count": invalid_input_targets_count,
                        },
                    )
                    set_jsonl_checkpoint(checkpoint_path, line_no)
                    stats["final_checkpoint_line"] = line_no
                    continue

                sparql_posts_before = checker.sparql_post_count
                try:
                    eval_result = evaluate_composition_for_doc(
                        checker,
                        r1=r1,
                        r2=r2,
                        targets=targets,
                        pid_to_original=pid_to_original,
                        invalid_input_targets_count=invalid_input_targets_count,
                        limit=limit,
                        offset=offset,
                        sample_n=sample_n,
                        deterministic_sample=deterministic_sample,
                        examples_k=examples_k,
                        max_example_targets=max_example_targets,
                        pairs_batch_size=pairs_batch_size,
                        targets_batch_size=targets_batch_size,
                        require_distinct_nodes=require_distinct_nodes,
                        exclude_self_loops=exclude_self_loops,
                    )
                except TransientSparqlError as exc:
                    error_docs += 1
                    stats["error_docs"] += 1
                    stats["stopped_on_transient"] = True
                    stats["stop_line"] = line_no
                    stats["stop_reason"] = str(exc)
                    _inc(stats["error_phases"], "composition_transient")
                    write_report_line(
                        report_log,
                        {
                            "status": "error",
                            "line_no": line_no,
                            "rel1": r1,
                            "rel2": r2,
                            "phase": "composition",
                            "error": str(exc),
                            "checked_at": datetime.utcnow().isoformat(),
                        },
                    )
                    LOG.warning("Stopping JSONL run due to transient failure at line %d", line_no)
                    break
                except Exception as exc:
                    error_docs += 1
                    stats["error_docs"] += 1
                    _inc(stats["error_phases"], "composition")
                    write_report_line(
                        report_log,
                        {
                            "status": "error",
                            "line_no": line_no,
                            "rel1": r1,
                            "rel2": r2,
                            "phase": "composition",
                            "error": str(exc),
                            "checked_at": datetime.utcnow().isoformat(),
                        },
                    )
                    out_doc = dict(doc)
                    out_doc["rule_verification"] = out_doc.get("rule_verification", {})
                    out_doc["rule_verification"]["composition_run"] = {
                        "status": "error",
                        "reason": "composition",
                        "error": str(exc),
                        "checked_at": datetime.utcnow().isoformat(),
                    }
                    _write_output(out_doc)
                    set_jsonl_checkpoint(checkpoint_path, line_no)
                    stats["final_checkpoint_line"] = line_no
                    continue

                now = datetime.utcnow().isoformat()
                sparql_posts_used = checker.sparql_post_count - sparql_posts_before
                out_doc = dict(doc)

                if eval_result["empty_chain"]:
                    skipped_docs_empty_chain += 1
                    stats["skipped_docs"] += 1
                    _inc(stats["skip_reasons"], "empty_chain_sample")
                    out_doc["rule_verification"] = {
                        "composition_updated_at": now,
                        "composition_notes": eval_result["base_notes"],
                        "composition_chain_pairs_examined": 0,
                        "composition_sparql_posts_used": sparql_posts_used,
                        "composition_sparql_posts_total": checker.sparql_post_count,
                        "composition_run": {
                            "status": "skip",
                            "reason": "empty_chain_sample",
                            "checked_at": now,
                        },
                    }
                    write_report_line(
                        report_log,
                        {"status": "skip", "line_no": line_no, "rel1": r1, "rel2": r2, "reason": "empty_chain_sample"},
                    )
                else:
                    out_doc["rule_verification"] = {
                        "composition_discovery_found": eval_result["composition_discovery_found"],
                        "composition": eval_result["composition"],
                        "composition_updated_at": now,
                        "composition_chain_pairs_examined": eval_result["chain_pairs_examined"],
                        "composition_notes": eval_result["base_notes"],
                        "composition_sparql_posts_used": sparql_posts_used,
                        "composition_sparql_posts_total": checker.sparql_post_count,
                        "composition_run": {
                            "status": "success",
                            "reason": "ok",
                            "checked_at": now,
                        },
                    }
                    saved_targets += eval_result["saved_targets"]
                    stats["success_docs"] += 1
                    stats["saved_targets"] += eval_result["saved_targets"]
                    for rel_target_key, result in eval_result["composition"].items():
                        write_report_line(
                            report_log,
                            {
                                "status": "saved",
                                "line_no": line_no,
                                "rel1": r1,
                                "rel2": r2,
                                "rel_target": rel_target_key,
                                "chain_pairs_examined": result["chain_pairs_examined"],
                                "chain_pairs_with_shortcut": result["chain_pairs_with_shortcut"],
                                "sample_confidence": result["sample_confidence"],
                                "checked_at": now,
                            },
                        )

                _write_output(out_doc)
                processed_docs += 1
                set_jsonl_checkpoint(checkpoint_path, line_no)
                stats["final_checkpoint_line"] = line_no

                if log_every_docs and processed_docs % log_every_docs == 0:
                    LOG.info(
                        "JSONL progress: docs=%d saved_targets=%d skipped_empty_chain=%d error_docs=%d sparql_posts=%d",
                        processed_docs,
                        saved_targets,
                        skipped_docs_empty_chain,
                        error_docs,
                        checker.sparql_post_count,
                    )

        LOG.info(
            "JSONL done. docs=%d saved_targets=%d skipped_empty_chain=%d error_docs=%d sparql_posts=%d",
            processed_docs,
            saved_targets,
            skipped_docs_empty_chain,
            error_docs,
            checker.sparql_post_count,
        )
        stats["sparql_posts_total"] = checker.sparql_post_count
        stats["finished_at"] = datetime.utcnow().isoformat()

        if stats_path:
            with open(stats_path, "w", encoding="utf-8") as sf:
                json.dump(stats, sf, ensure_ascii=True, indent=2)
            LOG.info("JSONL stats written to %s", stats_path)

        LOG.info("JSONL output appended to %s", output_jsonl)
        LOG.info("JSONL checkpoint at %s", checkpoint_path)
        if report_path:
            LOG.info("Report appended to %s", report_path)
    finally:
        if report_log:
            report_log.close()
        if compact_log:
            compact_log.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify composition rules for candidate (r1,r2,target) sets via chain sampling + multi-target discovery.",
    )
    parser.add_argument("--mongo_uri", default="")
    parser.add_argument("--db_name", default="wikidata_ontology")
    parser.add_argument("--candidates_col", default="only_intersecting_pairs_with_targets_composition")
    parser.add_argument("--meta_col", default="_meta")
    parser.add_argument("--checkpoint_id", default="improved_composition_candidates_checkpoint")
    parser.add_argument("--pairs_compatibility", default="INTERSECT")
    parser.add_argument("--input_jsonl", default="", help="Optional JSONL input path (enables JSONL mode).")
    parser.add_argument("--output_jsonl", default="", help="JSONL output path (used with --input_jsonl).")
    parser.add_argument("--output_jsonl_compact", default="", help="Optional compact JSONL output path without `targets` field.")
    parser.add_argument("--jsonl_checkpoint", default="", help="Checkpoint JSON path for JSONL mode.")
    parser.add_argument("--stats_path", default="", help="Optional run statistics JSON output path.")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint in JSONL mode.")

    parser.add_argument("--endpoint", default="https://query.wikidata.org/sparql")
    parser.add_argument("--user_agent", default="CompositionChecker/2.0 (contact: omaransary@gmail.com)")
    parser.add_argument("--timeout_s", type=int, default=60)
    parser.add_argument("--max_retries", type=int, default=3)
    parser.add_argument("--backoff_s", type=float, default=2.0)
    parser.add_argument("--min_delay_s", type=float, default=0.2)
    parser.add_argument("--max_delay_s", type=float, default=0.5)

    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--sample_n", type=int, default=300)
    parser.add_argument("--deterministic_sample", action="store_true")

    parser.add_argument("--examples_k", type=int, default=5)
    parser.add_argument("--max_example_targets", type=int, default=20)

    parser.add_argument("--pairs_batch_size", type=int, default=300)
    parser.add_argument("--targets_batch_size", type=int, default=60)

    parser.add_argument("--require_distinct_nodes", action="store_true")
    parser.add_argument("--exclude_self_loops", action="store_true")

    parser.add_argument("--log_every_docs", type=int, default=20)
    parser.add_argument("--report_path", default="")
    parser.add_argument("--log_level", default="INFO")

    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s [%(levelname)s] %(message)s")

    sample_n = None if args.sample_n <= 0 else args.sample_n

    if args.input_jsonl:
        output_jsonl = args.output_jsonl or f"{args.input_jsonl}.composition_verified.jsonl"
        checkpoint_path = args.jsonl_checkpoint or f"{output_jsonl}.checkpoint.json"
        run_candidates_jsonl(
            input_jsonl=args.input_jsonl,
            output_jsonl=output_jsonl,
            output_jsonl_compact=args.output_jsonl_compact,
            checkpoint_path=checkpoint_path,
            stats_path=args.stats_path,
            resume=args.resume,
            endpoint=args.endpoint,
            user_agent=args.user_agent,
            timeout_s=args.timeout_s,
            max_retries=args.max_retries,
            backoff_s=args.backoff_s,
            min_delay_s=args.min_delay_s,
            max_delay_s=args.max_delay_s,
            limit=args.limit,
            offset=args.offset,
            sample_n=sample_n,
            deterministic_sample=args.deterministic_sample,
            examples_k=args.examples_k,
            max_example_targets=args.max_example_targets,
            pairs_batch_size=args.pairs_batch_size,
            targets_batch_size=args.targets_batch_size,
            require_distinct_nodes=args.require_distinct_nodes,
            exclude_self_loops=args.exclude_self_loops,
            log_every_docs=args.log_every_docs,
            report_path=args.report_path,
        )
        return

    if not args.mongo_uri:
        parser.error("--mongo_uri is required when --input_jsonl is not provided.")

    run_candidates(
        mongo_uri=args.mongo_uri,
        db_name=args.db_name,
        candidates_col=args.candidates_col,
        meta_col=args.meta_col,
        checkpoint_id=args.checkpoint_id,
        pairs_compatibility=args.pairs_compatibility,
        endpoint=args.endpoint,
        user_agent=args.user_agent,
        timeout_s=args.timeout_s,
        max_retries=args.max_retries,
        backoff_s=args.backoff_s,
        min_delay_s=args.min_delay_s,
        max_delay_s=args.max_delay_s,
        limit=args.limit,
        offset=args.offset,
        sample_n=sample_n,
        deterministic_sample=args.deterministic_sample,
        examples_k=args.examples_k,
        max_example_targets=args.max_example_targets,
        pairs_batch_size=args.pairs_batch_size,
        targets_batch_size=args.targets_batch_size,
        require_distinct_nodes=args.require_distinct_nodes,
        exclude_self_loops=args.exclude_self_loops,
        log_every_docs=args.log_every_docs,
        report_path=args.report_path,
    )


if __name__ == "__main__":
    main()

    # Example:
    # python composition_range_domain.py \
    #   --mongo_uri "mongodb://localhost:27017/" \
    #   --db_name "wikidata_ontology" \
    #   --candidates_col "only_intersecting_pairs_with_targets_composition" \
    #   --pairs_compatibility "INTERSECT" \
    #   --report_path "composition_candidates_chain_intersect_report_improved.jsonl" \
    #   --deterministic_sample \
    #   --log_level INFO
