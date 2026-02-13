#!/usr/bin/env python3
"""
Hop Support v2 — Compute support counts WITH loop/non-loop separation.

This version computes TWO counts per (r1, r2):
- support_loop:    |{(x,y,z) : x --r1--> y --r2--> z AND x = z}|
- support_nonloop: |{(x,y,z) : x --r1--> y --r2--> z AND x ≠ z}|

This enables direct computation of:
- confidence_inverse(r1, r2) = support_loop / (support_loop + support_nonloop)
- confidence_symmetric(r) = confidence_inverse(r, r)
- confidence_antisymmetric(r) = 1 - confidence_symmetric(r)

For composition confidence, we need a separate step (target r3 discovery).

SPARQL Strategy:
- Query returns both loop and non-loop in one call using BIND
- Or use two separate queries (more reliable on WDQS)
"""

from __future__ import annotations

import argparse
from asyncio.log import logger
import json
import logging
import os
import random
import re
import sys
import threading
import time
from dataclasses import dataclass
from venv import logger
from typing import Any, Dict, List, Optional, Tuple, Iterable
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

PID_RE = re.compile(r"^P[1-9]\d*$")


def is_pid(x: Any) -> bool:
    return isinstance(x, str) and PID_RE.match(x) is not None


# ----------------------------
# Logging
# ----------------------------
def setup_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("hop_support_v2")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    h = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    h.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(h)
    logger.propagate = False
    return logger


# ----------------------------
# Rate Limiter
# ----------------------------
class TokenBucket:
    def __init__(self, qps: float):
        self.qps = max(0.0001, float(qps))
        self.capacity = 1.0
        self.tokens = 1.0
        self.last = time.time()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last
                self.last = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.qps)
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            time.sleep(0.02)


# ----------------------------
# WDQS Client
# ----------------------------
@dataclass
class WDQSResponse:
    ok: bool
    http: Optional[int]
    retry_after_sec: Optional[int]
    error: Optional[str]
    data: Optional[Dict[str, Any]]
    elapsed_sec: float


class WDQSClient:
    def __init__(
        self,
        endpoint: str,
        user_agent: str,
        timeout_sec: int,
        max_retries: int,
        backoff_base_sec: float,
        backoff_cap_sec: float,
        limiter: TokenBucket,
        inflight_sem: threading.Semaphore,
        logger: logging.Logger,
    ):
        self.endpoint = endpoint
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.backoff_base_sec = backoff_base_sec
        self.backoff_cap_sec = backoff_cap_sec
        self.limiter = limiter
        self.inflight_sem = inflight_sem
        self.logger = logger
        self._tls = threading.local()
        self._session_headers = {
            "User-Agent": user_agent,
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _get_session(self) -> requests.Session:
        s = getattr(self._tls, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update(self._session_headers)
            self._tls.session = s
        return s

    def _sleep_backoff(self, attempt: int, retry_after_sec: Optional[int]) -> None:
        if retry_after_sec is not None and retry_after_sec > 0:
            sleep_s = min(float(retry_after_sec), self.backoff_cap_sec)
        else:
            sleep_s = min(self.backoff_base_sec * (2 ** max(0, attempt - 1)), self.backoff_cap_sec)
            sleep_s *= (0.8 + 0.4 * random.random())
        time.sleep(sleep_s)

    def post_query(self, sparql: str) -> WDQSResponse:
        last_err: Optional[str] = None
        last_http: Optional[int] = None
        last_retry_after: Optional[int] = None
        start_time = time.time()

        for attempt in range(1, self.max_retries + 1):
            self.limiter.acquire()
            with self.inflight_sem:
                try:
                    session = self._get_session()
                    r = session.post(
                        self.endpoint,
                        data={"query": sparql},
                        params={"format": "json"},
                        timeout=self.timeout_sec,
                    )

                    retry_after = None
                    if "Retry-After" in r.headers:
                        try:
                            retry_after = int(r.headers["Retry-After"])
                        except Exception:
                            pass

                    last_http = r.status_code
                    last_retry_after = retry_after
                    elapsed = time.time() - start_time

                    if r.status_code == 200:
                        try:
                            return WDQSResponse(
                                ok=True, http=200, retry_after_sec=None,
                                error=None, data=r.json(), elapsed_sec=elapsed
                            )
                        except Exception as e:
                            last_err = f"JSON parse error: {e}"
                            self._sleep_backoff(attempt, None)
                            continue

                    if r.status_code == 429:
                        last_err = "HTTP 429 rate-limited"
                        self.logger.warning(f"WDQS 429 attempt={attempt}")
                        self._sleep_backoff(attempt, retry_after)
                        continue

                    text_snip = (r.text or "")[:300].replace("\n", " ")
                    last_err = f"HTTP {r.status_code}: {text_snip}"
                    self._sleep_backoff(attempt, retry_after)
                    continue

                except requests.Timeout:
                    last_err = "timeout"
                    last_http = None
                    self._sleep_backoff(attempt, None)
                    continue
                except requests.RequestException as e:
                    last_err = f"request_exception: {e}"
                    last_http = None
                    self._sleep_backoff(attempt, None)
                    continue

        elapsed = time.time() - start_time
        return WDQSResponse(
            ok=False, http=last_http, retry_after_sec=last_retry_after,
            error=last_err or "unknown", data=None, elapsed_sec=elapsed
        )


# ----------------------------
# SPARQL Queries
# ----------------------------
def build_loop_nonloop_count_query(r1: str, r2_pids: List[str]) -> str:
    """
    Count BOTH loop and non-loop support in one query.
    Returns: r2, is_loop (true/false), support
    """
    values = " ".join(f"wdt:{pid}" for pid in r2_pids)
    return f"""
SELECT ?r2 ?is_loop (COUNT(DISTINCT ?y) AS ?support) WHERE {{
  VALUES ?r2 {{ {values} }}
  ?x wdt:{r1} ?y .
  ?y ?r2 ?z .
  BIND(?x = ?z AS ?is_loop)
}}
GROUP BY ?r2 ?is_loop
""".strip()


def build_loop_count_query(r1: str, r2_pids: List[str]) -> str:
    """Count only loops (x = z)."""
    values = " ".join(f"wdt:{pid}" for pid in r2_pids)
    return f"""
SELECT ?r2 (COUNT(DISTINCT ?y) AS ?support) WHERE {{
  VALUES ?r2 {{ {values} }}
  ?x wdt:{r1} ?y .
  ?y ?r2 ?x .
}}
GROUP BY ?r2
""".strip()


def build_total_count_query(r1: str, r2_pids: List[str]) -> str:
    """Count total (loop + non-loop)."""
    values = " ".join(f"wdt:{pid}" for pid in r2_pids)
    return f"""
SELECT ?r2 (COUNT(DISTINCT ?y) AS ?support) WHERE {{
  VALUES ?r2 {{ {values} }}
  ?x wdt:{r1} ?y .
  ?y ?r2 ?z .
}}
GROUP BY ?r2
""".strip()


def build_discover_loop_topk_query(r1: str, topk: int) -> str:
    """Discover top-K r2 by loop support."""
    return f"""
SELECT ?r2 (COUNT(DISTINCT ?y) AS ?support) WHERE {{
  ?x wdt:{r1} ?y .
  ?y ?r2 ?x .
  ?r2prop wikibase:directClaim ?r2 ;
          wikibase:propertyType wikibase:WikibaseItem .
}}
GROUP BY ?r2
ORDER BY DESC(?support)
LIMIT {int(topk)}
""".strip()


def build_discover_total_topk_query(r1: str, topk: int) -> str:
    """Discover top-K r2 by total support."""
    return f"""
SELECT ?r2 (COUNT(DISTINCT ?y) AS ?support) WHERE {{
  ?x wdt:{r1} ?y .
  ?y ?r2 ?z .
  ?r2prop wikibase:directClaim ?r2 ;
          wikibase:propertyType wikibase:WikibaseItem .
}}
GROUP BY ?r2
ORDER BY DESC(?support)
LIMIT {int(topk)}
""".strip()


# ----------------------------
# Parsing
# ----------------------------
WDT_PREFIX = "http://www.wikidata.org/prop/direct/"


def parse_loop_nonloop_bindings(data: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    """
    Parse results of loop/non-loop query.
    Returns: {pid: {"loop": count, "nonloop": count}}
    """
    result: Dict[str, Dict[str, int]] = {}
    bindings = (data.get("results", {}) or {}).get("bindings", []) or []
    
    for b in bindings:
        r2_uri = (b.get("r2", {}) or {}).get("value", "")
        is_loop_raw = (b.get("is_loop", {}) or {}).get("value", "false")
        support_raw = (b.get("support", {}) or {}).get("value", "0")
        
        if not r2_uri.startswith(WDT_PREFIX):
            continue
        pid = r2_uri[len(WDT_PREFIX):]
        if not is_pid(pid):
            continue
        
        try:
            supp = int(float(support_raw))
        except Exception:
            supp = 0
        
        is_loop = is_loop_raw.lower() in ("true", "1")
        
        if pid not in result:
            result[pid] = {"loop": 0, "nonloop": 0}
        
        if is_loop:
            result[pid]["loop"] += supp
        else:
            result[pid]["nonloop"] += supp
    
    return result


def parse_simple_count_bindings(data: Dict[str, Any]) -> Dict[str, int]:
    """Parse simple COUNT results."""
    result: Dict[str, int] = {}
    bindings = (data.get("results", {}) or {}).get("bindings", []) or []
    
    for b in bindings:
        r2_uri = (b.get("r2", {}) or {}).get("value", "")
        support_raw = (b.get("support", {}) or {}).get("value", "0")
        
        if not r2_uri.startswith(WDT_PREFIX):
            continue
        pid = r2_uri[len(WDT_PREFIX):]
        if not is_pid(pid):
            continue
        
        try:
            result[pid] = int(float(support_raw))
        except Exception:
            result[pid] = 0
    
    return result


# ----------------------------
# Chunk Helper
# ----------------------------
def chunk_list(lst: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# ----------------------------
# IO
# ----------------------------
_io_lock = threading.Lock()


def load_processed_r1(output_path: str) -> set:
    processed = set()
    if not os.path.exists(output_path):
        return processed
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                r1 = obj.get("r1")
                if r1:
                    processed.add(r1)
            except Exception:
                pass
    return processed


def append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    line = json.dumps(obj, ensure_ascii=False)
    with _io_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_input_docs(input_path: str) -> List[Dict[str, Any]]:
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []
    if text[0] == "[":
        return json.loads(text)
    docs = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            docs.append(json.loads(line))
    return docs


# ----------------------------
# Worker
# ----------------------------
def compute_support_v2(
    doc: Dict[str, Any],
    wdqs: WDQSClient,
    chunk_size: int,
    topk: int,
    logger: logging.Logger,
    use_separate_queries: bool = True,  # More reliable than combined query
) -> Dict[str, Any]:
    """
    Compute loop and non-loop support for all r2.
    """
    r1 = doc.get("r1")
    if not is_pid(r1):
        raise ValueError("Invalid r1")

    status = doc.get("status")
    valid_r2: List[str] = [x for x in (doc.get("valid_r2") or []) if is_pid(x)]
    valid_r2 = sorted(set(valid_r2))

    started = time.time()

    if status == "SUCCESS" and len(valid_r2) > 0:
        # Chunked approach with separate loop and total queries
        support_data: Dict[str, Dict[str, int]] = {}  # pid -> {loop, nonloop, total}
        
        total_chunks = 0
        successful_chunks = 0
        failed_chunks = 0
        failed_r2: List[str] = []

        for chunk in chunk_list(valid_r2, chunk_size):
            total_chunks += 1
            
            if use_separate_queries:
                # Query 1: Loop count (x = z)
                q_loop = build_loop_count_query(r1, chunk)
                resp_loop = wdqs.post_query(q_loop)
                
                # Query 2: Total count
                q_total = build_total_count_query(r1, chunk)
                resp_total = wdqs.post_query(q_total)
                
                if not resp_loop.ok or not resp_total.ok:
                    failed_chunks += 1
                    failed_r2.extend(chunk)  # Track which r2 we couldn't verify
                    err = resp_loop.error or resp_total.error
                    logger.warning(f"[{r1}] chunk failed: {err}")
                    continue
                
                loop_counts = parse_simple_count_bindings(resp_loop.data or {})
                total_counts = parse_simple_count_bindings(resp_total.data or {})
                
                for pid in chunk:
                    loop = loop_counts.get(pid, 0)
                    total = total_counts.get(pid, 0)
                    nonloop = max(0, total - loop)
                    support_data[pid] = {
                        "loop": loop,
                        "nonloop": nonloop,
                        "total": total,
                    }
                successful_chunks += 1
                
            else:
                # Combined query (may be less reliable)
                q = build_loop_nonloop_count_query(r1, chunk)
                resp = wdqs.post_query(q)
                
                if not resp.ok:
                    failed_chunks += 1
                    failed_r2.extend(chunk)  # Track which r2 we couldn't verify
                    logger.warning(f"[{r1}] chunk failed: {resp.error}")
                    continue
                
                parsed = parse_loop_nonloop_bindings(resp.data or {})
                for pid, counts in parsed.items():
                    support_data[pid] = {
                        "loop": counts["loop"],
                        "nonloop": counts["nonloop"],
                        "total": counts["loop"] + counts["nonloop"],
                    }
                successful_chunks += 1

        elapsed = time.time() - started

        # Ensure all r2 have entries
        # for pid in valid_r2:
        #     if pid not in support_data:
        #         support_data[pid] = {"loop": 0, "nonloop": 0, "total": 0}

        # Compute confidences
        # confidence_data: Dict[str, Optional[float]] = {}
        # for pid, counts in support_data.items():
        #     total = counts["total"]
        #     if total > 0:
        #         confidence_data[pid] = counts["loop"] / total
        #     else:
        #         confidence_data[pid] = None

        # Build output
        if failed_chunks == 0:
            out_status = "SUCCESS"
            out_error = None
        elif successful_chunks == 0:
            out_status = "ERROR"
            out_error = "all chunks failed"
        else:
            out_status = "PARTIAL_SUCCESS"
            out_error = f"{failed_chunks}/{total_chunks} chunks failed"

        return {
            "r1": r1,
            "mode": "values_chunked_v2",
            "input_status": status,
            "valid_r2_count": len(valid_r2),
            "chunk_size": chunk_size,
            "chunks": total_chunks,
            "successful_chunks": successful_chunks,
            "failed_chunks": failed_chunks,
            "failed_r2": failed_r2,  # r2 we couldn't verify (unknown, not zero)
            "support_data": support_data,  # {r2: {loop, nonloop, total}} - only verified r2
            "status": out_status,
            "error": out_error,
            "elapsed_sec": elapsed,
            "updated_at": time.time(),
        }

    # Fallback: discover mode (for ERROR/NOT_FOUND input docs)
    # Just get top-K by loop support
    q = build_discover_loop_topk_query(r1, topk)
    resp = wdqs.post_query(q)
    
    if not resp.ok:
        elapsed = time.time() - started
        return {
            "r1": r1,
            "mode": "discover_topk_v2",
            "input_status": status,
            "status": "ERROR",
            "error": resp.error,
            "elapsed_sec": elapsed,
            "updated_at": time.time(),
        }

    loop_counts = parse_simple_count_bindings(resp.data or {})
    
    # Also get total to compute confidence
    q2 = build_discover_total_topk_query(r1, topk)
    resp2 = wdqs.post_query(q2)
    total_counts = parse_simple_count_bindings(resp2.data or {}) if resp2.ok else {}

    elapsed = time.time() - started

    support_data = {}
    confidence_data = {}
    for pid, loop in loop_counts.items():
        total = total_counts.get(pid, loop)
        nonloop = max(0, total - loop)
        support_data[pid] = {"loop": loop, "nonloop": nonloop, "total": total}
        # confidence_data[pid] = loop / total if total > 0 else None

    return {
        "r1": r1,
        "mode": "discover_topk_v2",
        "input_status": status,
        "topk": topk,
        "support_data": support_data,
        # "confidence_inverse": confidence_data,
        "status": "SUCCESS",
        "error": None,
        "elapsed_sec": elapsed,
        "updated_at": time.time(),
    }


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Hop Support v2 - with loop/non-loop separation")
    ap.add_argument("--input", required=True, help="hop_discovery JSON/JSONL")
    ap.add_argument("--output_jsonl", default="hop_support_v2.jsonl")
    ap.add_argument("--checkpoint", default="hop_support_v2_checkpoint.json")

    ap.add_argument("--wdqs_endpoint", default="https://query.wikidata.org/sparql")
    ap.add_argument("--user_agent", default=os.getenv("WDQS_USER_AGENT", ""))
    ap.add_argument("--timeout_sec", type=int, default=90)
    ap.add_argument("--max_retries", type=int, default=5)
    ap.add_argument("--backoff_base_sec", type=float, default=2.0)
    ap.add_argument("--backoff_cap_sec", type=float, default=120.0)

    ap.add_argument("--chunk_size", type=int, default=30, help="Smaller chunks for 2 queries per chunk")
    ap.add_argument("--topk", type=int, default=50)

    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--qps", type=float, default=0.3, help="Lower QPS since we do 2 queries per chunk")
    ap.add_argument("--max_inflight", type=int, default=2)

    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--log_level", default="INFO")
    ap.add_argument("--checkpoint_every", type=int, default=25)

    args = ap.parse_args()
    logger = setup_logging(args.log_level)

    if not args.user_agent or "mailto:" not in args.user_agent:
        logger.error("--user_agent with mailto: required")
        sys.exit(2)

    docs = read_input_docs(args.input)
    logger.info(f"Loaded {len(docs)} docs from {args.input}")

    processed = set()
    if args.resume:
        processed = load_processed_r1(args.output_jsonl)
        logger.info(f"Resume: {len(processed)} already done")

    limiter = TokenBucket(args.qps)
    inflight_sem = threading.Semaphore(args.max_inflight)

    wdqs = WDQSClient(
        endpoint=args.wdqs_endpoint,
        user_agent=args.user_agent,
        timeout_sec=args.timeout_sec,
        max_retries=args.max_retries,
        backoff_base_sec=args.backoff_base_sec,
        backoff_cap_sec=args.backoff_cap_sec,
        limiter=limiter,
        inflight_sem=inflight_sem,
        logger=logger,
    )

    tasks = [d for d in docs if is_pid(d.get("r1")) and d.get("r1") not in processed]
    logger.info(f"Queued {len(tasks)} tasks")

    done = 0
    ok = 0
    err = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(compute_support_v2, d, wdqs, args.chunk_size, args.topk, logger): d.get("r1")
            for d in tasks
        }

        for fut in as_completed(futures):
            r1 = futures[fut]
            done += 1
            try:
                result = fut.result()
                if result.get("status") == "SUCCESS":
                    ok += 1
                    logger.info(f"[OK] {r1} elapsed={result.get('elapsed_sec', 0):.1f}s")
                else:
                    err += 1
                    logger.warning(f"[FAIL] {r1}: {result.get('error')}")
            except Exception as e:
                err += 1
                result = {"r1": r1, "status": "ERROR", "error": str(e), "updated_at": time.time()}
                logger.exception(f"[EXC] {r1}: {e}")

            append_jsonl(args.output_jsonl, result)

            if done % args.checkpoint_every == 0:
                elapsed = time.time() - t0
                logger.info(f"Checkpoint: {done}/{len(tasks)} ok={ok} err={err} rate={done/elapsed:.2f}/s")

    elapsed = time.time() - t0
    logger.info(f"Done: {done} ok={ok} err={err} elapsed={elapsed:.1f}s")


if __name__ == "__main__":
    main()
