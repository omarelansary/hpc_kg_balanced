#!/usr/bin/env python3
"""
Hop Support (v1) — Add support counts to hop discovery results.

INPUT:
- A JSON/JSONL file containing hop_discovery documents like:
  { r1, status, valid_r2, valid_r2_count, ... }

BEHAVIOR:
1) For documents with status == "SUCCESS" and non-empty valid_r2:
   - Compute support counts using chunked VALUES:
     VALUES ?r2 { wdt:P.. wdt:P.. }
     ?h wdt:r1 ?t .
     ?t ?r2 ?c .
   - Merge chunk results into support_by_r2.

2) For all other documents (ERROR/NOT_FOUND or empty valid_r2):
   - Use discover+count topK (because there is nothing to chunk):
     SELECT ?r2 (COUNT(*) AS ?support) WHERE { ... } GROUP BY ?r2 ORDER BY DESC(?support) LIMIT K
   - Store as topk_support.

OUTPUT:
- hop_support.jsonl (append-only)
- checkpoint.json (resume)

HPC:
- Uses ThreadPoolExecutor, but also enforces global request rate and max inflight requests.
- You can set workers high (e.g., 48), but keep --qps low (e.g., 0.2–1.0) to avoid WDQS 429/504.

NOTES:
- WDQS is rate-limited and can time out; we do retries + backoff + sampling fallback.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Iterable
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

PID_RE = re.compile(r"^P[1-9]\d*$")


# helper
def is_pid(x: Any) -> bool:
    return isinstance(x, str) and PID_RE.match(x) is not None


# ----------------------------
# Logging
# ----------------------------
def setup_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("hop_support")
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
# Rate Limiter (global)
# ----------------------------
class TokenBucket:
    """
    Simple token bucket limiter: allows ~qps requests/sec across all threads.
    """
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
            sleep_s *= (0.8 + 0.4 * random.random())  # jitter
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
                            retry_after = None

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
                            self.logger.debug(f"WDQS JSON parse error attempt={attempt}: {e}")
                            self._sleep_backoff(attempt, None)
                            continue

                    if r.status_code == 429:
                        last_err = "HTTP 429 rate-limited"
                        self.logger.warning(f"WDQS 429 attempt={attempt} retry_after={retry_after}")
                        self._sleep_backoff(attempt, retry_after)
                        continue

                    # common WDQS timeouts show as 504 upstream timeouts
                    text_snip = (r.text or "")[:300].replace("\n", " ")
                    last_err = f"HTTP {r.status_code}: {text_snip}"
                    lvl = logging.WARNING if 500 <= r.status_code < 600 else logging.ERROR
                    self.logger.log(lvl, f"WDQS HTTP {r.status_code} attempt={attempt}: {text_snip}")
                    self._sleep_backoff(attempt, retry_after)
                    continue

                except requests.Timeout:
                    last_err = "timeout"
                    last_http = None
                    self.logger.warning(f"WDQS timeout attempt={attempt}")
                    self._sleep_backoff(attempt, None)
                    continue
                except requests.RequestException as e:
                    last_err = f"request_exception: {e}"
                    last_http = None
                    self.logger.warning(f"WDQS request exception attempt={attempt}: {e}")
                    self._sleep_backoff(attempt, None)
                    continue

        elapsed = time.time() - start_time
        return WDQSResponse(
            ok=False, http=last_http, retry_after_sec=last_retry_after,
            error=last_err or "unknown", data=None, elapsed_sec=elapsed
        )


# ----------------------------
# SPARQL builders
# ----------------------------
def _chunk(iterable: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(iterable), n):
        yield iterable[i:i + n]


def build_values_count_query(r1: str, r2_pids: List[str]) -> str:
    """
    Count support for a fixed set of r2 predicates using VALUES (stable).
    """
    values = " ".join(f"wdt:{pid}" for pid in r2_pids)
    return f"""
SELECT ?r2 (COUNT(DISTINCT ?t) AS ?support) WHERE {{
  VALUES ?r2 {{ {values} }}
  ?h wdt:{r1} ?t .
  ?t ?r2 ?c .
}}
GROUP BY ?r2
""".strip()


def build_discover_count_topk_query(r1: str, topk: int) -> str:
    """
    Discover and count top-K r2 predicates by support.
    We *avoid* wikibase:propertyType join (too expensive).
    FILTER on wdt: namespace is cheaper, then type-filter offline if needed.
    """
    return f"""
SELECT ?r2 (COUNT(DISTINCT ?t) AS ?support) WHERE {{
  ?h wdt:{r1} ?t .
  ?t ?r2 ?c .
  FILTER(STRSTARTS(STR(?r2), STR(wdt:)))
}}
GROUP BY ?r2
ORDER BY DESC(?support)
LIMIT {int(topk)}
""".strip()


def build_discover_count_topk_query_sampled_t(r1: str, topk: int, t_limit: int) -> str:
    """
    Sampling fallback: cap first-hop solutions by limiting ?t list.
    Support is then sample-based but stable (good for ranking).
    """
    return f"""
SELECT ?r2 (COUNT(DISTINCT ?t) AS ?support) WHERE {{
  {{
    SELECT ?t WHERE {{
      ?h wdt:{r1} ?t .
    }}
    LIMIT {int(t_limit)}
  }}
  ?t ?r2 ?c .
  FILTER(STRSTARTS(STR(?r2), STR(wdt:)))
}}
GROUP BY ?r2
ORDER BY DESC(?support)
LIMIT {int(topk)}
""".strip()


# ----------------------------
# Parsing helpers
# ----------------------------
WDT_PREFIX = "http://www.wikidata.org/prop/direct/"


def parse_count_bindings(data: Dict[str, Any]) -> List[Tuple[str, int]]:
    """
    Parse results of SELECT ?r2 (COUNT(DISTINCT ?t) AS ?support).
    Returns list of (pid, support).
    """
    out: List[Tuple[str, int]] = []
    bindings = (data.get("results", {}) or {}).get("bindings", []) or []
    for b in bindings:
        r2_uri = (b.get("r2", {}) or {}).get("value", "")
        support_raw = (b.get("support", {}) or {}).get("value", "0")
        if r2_uri.startswith(WDT_PREFIX):
            pid = r2_uri[len(WDT_PREFIX):]
            try:
                supp = int(float(support_raw))
            except Exception:
                supp = 0
            if is_pid(pid):
                out.append((pid, supp))
    return out


# ----------------------------
# Checkpoint / IO
# ----------------------------
_io_lock = threading.Lock()


def load_processed_r1(output_jsonl: str) -> set[str]:
    processed: set[str] = set()
    if not os.path.exists(output_jsonl):
        return processed
    with open(output_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                r1 = obj.get("r1")
                if isinstance(r1, str) and r1:
                    processed.add(r1)
            except Exception:
                continue
    return processed


def append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    line = json.dumps(obj, ensure_ascii=False)
    with _io_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def save_checkpoint(path: str, payload: Dict[str, Any]) -> None:
    with _io_lock:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def read_input_docs(input_path: str) -> List[Dict[str, Any]]:
    """
    Accepts:
    - JSON array file: [ {...}, {...} ]
    - JSONL file: one JSON object per line
    """
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []
    if text[0] == "[":
        return json.loads(text)
    # JSONL
    docs: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        docs.append(json.loads(line))
    return docs


# ----------------------------
# Worker logic
# ----------------------------
def compute_support_for_doc(
    doc: Dict[str, Any],
    wdqs: WDQSClient,
    chunk_size: int,
    topk: int,
    sampled_t_limit: int,
    logger: logging.Logger,
) -> Dict[str, Any]:
    """
    Returns an output record for this r1:
    - If doc is SUCCESS with valid_r2 -> chunked VALUES counting
    - Else -> discover+count topK (with sampling fallback on repeated timeouts)
    """
    r1 = doc.get("r1")
    if not is_pid(r1):
        raise ValueError("Invalid or missing r1")

    status = doc.get("status")
    valid_r2: List[str] = doc.get("valid_r2") or []
    valid_r2 = [x for x in valid_r2 if is_pid(x)]
    valid_r2 = sorted(set(valid_r2))

    started = time.time()

    if status == "SUCCESS" and len(valid_r2) > 0:
        # Chunked VALUES approach
        support_by_r2: Dict[str, int] = {}
        total_chunks = 0
        total_rows = 0
        total_queries = 0
        successful_chunks = 0
        failed_chunks = 0

        for chunk in _chunk(valid_r2, chunk_size):
            total_chunks += 1
            q = build_values_count_query(r1, chunk)
            resp = wdqs.post_query(q)
            total_queries += 1

            if not resp.ok:
                # Fail fast? We choose to continue; partial results still useful.
                logger.warning(f"[VALUES][{r1}] chunk_failed size={len(chunk)} err={resp.error}")
                failed_chunks += 1
                continue

            successful_chunks += 1
            pairs = parse_count_bindings(resp.data or {})
            total_rows += len(pairs)
            for pid, supp in pairs:
                support_by_r2[pid] = support_by_r2.get(pid, 0) + supp

        elapsed = time.time() - started
        # Ensure all candidate r2 appear with at least 0 (optional, but handy downstream)
        for pid in valid_r2:
            support_by_r2.setdefault(pid, 0)

        # Convert to top list for convenience
        top_list = sorted(
            [{"r2": pid, "support": supp} for pid, supp in support_by_r2.items()],
            key=lambda x: x["support"],
            reverse=True,
        )
        if failed_chunks == 0:
            out_status = "SUCCESS"
            out_error = None
        elif successful_chunks == 0:
            out_status = "ERROR"
            out_error = "all VALUES chunks failed"
        else:
            out_status = "PARTIAL_SUCCESS"
            out_error = f"{failed_chunks} of {total_chunks} chunks failed"

        return {
            "r1": r1,
            "mode": "values_chunked",
            "input_status": status,
            "valid_r2_count": len(valid_r2),
            "chunk_size": chunk_size,
            "chunks": total_chunks,
            "successful_chunks": successful_chunks,
            "failed_chunks": failed_chunks,
            "queries": total_queries,
            "rows_returned": total_rows,
            "support_by_r2": support_by_r2,     # full map
            "top_support": top_list[:topk],     # convenience
            "status": out_status,
            "error": out_error,
            "elapsed_sec": elapsed,
            "updated_at": time.time(),
        }

    # Fallback: discover+count topK
    # First try full discover+count; if it fails repeatedly, use sampled_t variant.
    q1 = build_discover_count_topk_query(r1, topk)
    resp = wdqs.post_query(q1)
    if not resp.ok:
        logger.warning(f"[TOPK][{r1}] full_failed err={resp.error}; trying sampled_t={sampled_t_limit}")
        q2 = build_discover_count_topk_query_sampled_t(r1, topk, sampled_t_limit)
        resp2 = wdqs.post_query(q2)
        if not resp2.ok:
            elapsed = time.time() - started
            return {
                "r1": r1,
                "mode": "discover_topk",
                "input_status": status,
                "status": "ERROR",
                "error": f"full_failed={resp.error}; sampled_failed={resp2.error}",
                "http_code": resp2.http,
                "elapsed_sec": elapsed,
                "updated_at": time.time(),
            }
        pairs = parse_count_bindings(resp2.data or {})
        elapsed = time.time() - started
        return {
            "r1": r1,
            "mode": "discover_topk_sampled_t",
            "input_status": status,
            "t_limit": sampled_t_limit,
            "topk": topk,
            "topk_support": [{"r2": pid, "support": supp} for pid, supp in pairs],
            "status": "SUCCESS",
            "error": None,
            "elapsed_sec": elapsed,
            "updated_at": time.time(),
        }

    pairs = parse_count_bindings(resp.data or {})
    elapsed = time.time() - started
    return {
        "r1": r1,
        "mode": "discover_topk",
        "input_status": status,
        "topk": topk,
        "topk_support": [{"r2": pid, "support": supp} for pid, supp in pairs],
        "status": "SUCCESS",
        "error": None,
        "elapsed_sec": elapsed,
        "updated_at": time.time(),
    }


# ----------------------------
# Main runner
# ----------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Compute hop support counts from hop_discovery JSON/JSONL")
    ap.add_argument("--input", required=True, help="Path to hop_discovery JSON or JSONL")
    ap.add_argument("--output_jsonl", default="hop_support.jsonl", help="Append-only output JSONL")
    ap.add_argument("--checkpoint", default="checkpoint.json", help="Checkpoint JSON file")

    # WDQS
    ap.add_argument("--wdqs_endpoint", default="https://query.wikidata.org/sparql")
    ap.add_argument("--user_agent", default=os.getenv("WDQS_USER_AGENT", ""),
                    help="Must include mailto:... to avoid 403 blocks")
    ap.add_argument("--timeout_sec", type=int, default=90)
    ap.add_argument("--max_retries", type=int, default=5)
    ap.add_argument("--backoff_base_sec", type=float, default=2.0)
    ap.add_argument("--backoff_cap_sec", type=float, default=120.0)

    # Strategy
    ap.add_argument("--chunk_size", type=int, default=40, help="VALUES chunk size for SUCCESS docs")
    ap.add_argument("--topk", type=int, default=50, help="Top-K r2 to keep for discover+count mode")
    ap.add_argument("--sampled_t_limit", type=int, default=20000, help="Fallback t-cap for sampled discover+count")

    # HPC / threading controls
    ap.add_argument("--workers", type=int, default=16, help="Thread pool size (CPU cores != WDQS capacity)")
    ap.add_argument("--qps", type=float, default=0.5, help="Global requests/sec across all threads")
    ap.add_argument("--max_inflight", type=int, default=4, help="Max concurrent HTTP requests at once")

    # Resume behavior
    ap.add_argument("--resume", action="store_true", help="Resume by skipping r1 already in output_jsonl")

    # Logging
    ap.add_argument("--log_level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    ap.add_argument("--checkpoint_every", type=int, default=25, help="Write checkpoint every N completed items")

    args = ap.parse_args()
    if args.chunk_size < 1:
        sys.exit("chunk_size must be >= 1")
    if args.checkpoint_every < 1:
        sys.exit("checkpoint_every must be >= 1")
    if args.topk < 1:
        sys.exit("topk must be >= 1")
    if args.max_inflight < 1:
        sys.exit("max_inflight must be >= 1")
    if args.qps <= 0:
        sys.exit("qps must be > 0")
    if args.workers < 1:
        sys.exit("workers must be >= 1")

    logger = setup_logging(args.log_level)

    if not args.user_agent or "mailto:" not in args.user_agent:
        logger.error("You must pass --user_agent with mailto:... (WDQS requirement)")
        sys.exit(2)

    docs = read_input_docs(args.input)
    logger.info(f"Loaded {len(docs)} input docs from {args.input}")

    processed = set()
    if args.resume:
        processed = load_processed_r1(args.output_jsonl)
        logger.info(f"Resume enabled: loaded {len(processed)} already-processed r1 from {args.output_jsonl}")

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

    # Build task list
    tasks: List[Dict[str, Any]] = []
    for d in docs:
        r1 = d.get("r1")
        if not is_pid(r1):
            continue
        if args.resume and r1 in processed:
            continue
        tasks.append(d)

    logger.info(f"Queued {len(tasks)} tasks")

    done = 0
    ok = 0
    err = 0
    started_all = time.time()

    # Process in parallel
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(
                compute_support_for_doc,
                d,
                wdqs,
                args.chunk_size,
                args.topk,
                args.sampled_t_limit,
                logger,
            ): d.get("r1")
            for d in tasks
        }

        for fut in as_completed(futures):
            r1 = futures[fut]
            done += 1
            try:
                result = fut.result()
                if result.get("status") == "SUCCESS":
                    ok += 1
                    logger.info(f"[DONE] {r1} mode={result.get('mode')} elapsed={result.get('elapsed_sec', 0):.1f}s")
                else:
                    err += 1
                    logger.warning(f"[FAIL] {r1} err={result.get('error')}")
            except Exception as e:
                err += 1
                result = {
                    "r1": r1,
                    "status": "ERROR",
                    "error": f"unhandled_exception: {e}",
                    "updated_at": time.time(),
                }
                logger.exception(f"[EXCEPTION] {r1}: {e}")

            append_jsonl(args.output_jsonl, result)

            # checkpoint
            if done % args.checkpoint_every == 0:
                elapsed = time.time() - started_all
                save_checkpoint(args.checkpoint, {
                    "input": args.input,
                    "output_jsonl": args.output_jsonl,
                    "done": done,
                    "ok": ok,
                    "err": err,
                    "total_tasks": len(tasks),
                    "elapsed_sec": elapsed,
                    "rate_per_sec": (done / elapsed) if elapsed > 0 else 0.0,
                    "updated_at": time.time(),
                })
                logger.info(f"Checkpoint: done={done}/{len(tasks)} ok={ok} err={err}")

    elapsed_all = time.time() - started_all
    save_checkpoint(args.checkpoint, {
        "input": args.input,
        "output_jsonl": args.output_jsonl,
        "done": done,
        "ok": ok,
        "err": err,
        "total_tasks": len(tasks),
        "elapsed_sec": elapsed_all,
        "rate_per_sec": (done / elapsed_all) if elapsed_all > 0 else 0.0,
        "finished": True,
        "updated_at": time.time(),
    })
    logger.info(f"Finished: done={done} ok={ok} err={err} elapsed={elapsed_all:.1f}s")


if __name__ == "__main__":
    main()

# python hop_support.py \
#   --input hop_discovery.jsonl \
#   --output_jsonl hop_support.jsonl \
#   --checkpoint hop_support_checkpoint.json \
#   --resume \
#   --user_agent "hop_support/1.0 (mailto: omaransari@gmail.com)" \
#   --workers 48 \
#   --qps 0.5 \
#   --max_inflight 4 \
#   --chunk_size 40 \
#   --topk 50 \
#   --sampled_t_limit 20000 \
#   --log_level INFO
