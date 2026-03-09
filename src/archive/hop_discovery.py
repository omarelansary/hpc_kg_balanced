#!/usr/bin/env python3
"""
Hop Discovery Script (v2 - with threading)

For each WikibaseItem relation r1 in relation_profile, discovers which r2 relations
form valid hops (a --r1--> b --r2--> c) by querying WDQS.

Features:
- Resumes from checkpoint via _meta collection
- Distinguishes ERROR vs NOT_FOUND vs SUCCESS
- Handles WDQS rate limiting with exponential backoff
- Deduplicates results in Python (not SPARQL DISTINCT)
- Filters to only WikibaseItem properties
- Logs progress and errors
- Multi-threaded: separate threads for querying and saving
- Checkpoints based on scanned count, not just processed

Output collection: hop_discovery
Schema: {
    r1: "P123",
    valid_r2: ["P17", "P31", ...],
    valid_r2_count: 42,
    status: "SUCCESS" | "NOT_FOUND" | "ERROR",
    error: null | "error message",
    query_time_sec: 1.23,
    sample_size: 50000,
    updated_at: timestamp
}
"""

import argparse
import json
import logging
import os
import queue
import random
import sys
import threading
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError
from bson import ObjectId


# ----------------------------
# Logging
# ----------------------------
def setup_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("hop_discovery")
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
        logger: logging.Logger,
    ):
        self.endpoint = endpoint
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.backoff_base_sec = backoff_base_sec
        self.backoff_cap_sec = backoff_cap_sec
        self.logger = logger

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

    def _sleep_backoff(self, attempt: int, retry_after_sec: Optional[int]) -> None:
        if retry_after_sec is not None and retry_after_sec > 0:
            sleep_s = min(float(retry_after_sec), self.backoff_cap_sec)
        else:
            sleep_s = min(self.backoff_base_sec * (2 ** max(0, attempt - 1)), self.backoff_cap_sec)
            sleep_s *= (0.8 + 0.4 * random.random())  # Jitter
        self.logger.debug(f"Sleeping {sleep_s:.1f}s before retry")
        time.sleep(sleep_s)

    def post_query(self, sparql: str) -> WDQSResponse:
        """POST a SPARQL query with retries/backoff."""
        last_err: Optional[str] = None
        last_http: Optional[int] = None
        last_retry_after: Optional[int] = None
        start_time = time.time()

        for attempt in range(1, self.max_retries + 1):
            try:
                r = self.session.post(
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

                # Track last HTTP status for observability
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
                        self.logger.debug(f"WDQS JSON parse error (attempt {attempt}): {e}")
                        self._sleep_backoff(attempt, None)
                        continue

                if r.status_code == 429:
                    last_err = "HTTP 429 rate-limited"
                    self.logger.warning(f"WDQS 429 rate-limited (attempt {attempt}); retry_after={retry_after}")
                    self._sleep_backoff(attempt, retry_after)
                    continue

                if r.status_code == 403:
                    text_snip = (r.text or "")[:300].replace("\n", " ")
                    last_err = f"HTTP 403 forbidden: {text_snip}"
                    self.logger.error(f"WDQS 403 forbidden (attempt {attempt}): {text_snip}")
                    self._sleep_backoff(attempt, retry_after)
                    continue

                # 5xx or other 4xx
                text_snip = (r.text or "")[:300].replace("\n", " ")
                last_err = f"HTTP {r.status_code}: {text_snip}"
                lvl = logging.WARNING if 500 <= r.status_code < 600 else logging.ERROR
                self.logger.log(lvl, f"WDQS HTTP {r.status_code} (attempt {attempt}): {text_snip}")
                self._sleep_backoff(attempt, retry_after)
                continue

            except requests.Timeout:
                last_err = "timeout"
                last_http = None
                self.logger.warning(f"WDQS timeout (attempt {attempt})")
                self._sleep_backoff(attempt, None)
                continue
            except requests.RequestException as e:
                last_err = f"request_exception: {e}"
                last_http = None
                self.logger.warning(f"WDQS request exception (attempt {attempt}): {e}")
                self._sleep_backoff(attempt, None)
                continue

        elapsed = time.time() - start_time
        return WDQSResponse(
            ok=False, http=last_http, retry_after_sec=last_retry_after,
            error=last_err or "unknown", data=None, elapsed_sec=elapsed
        )


# ----------------------------
# SPARQL Query Builder
# ----------------------------
def build_hop_discovery_query(r1: str, limit: int) -> str:
    """
    Query to find all WikibaseItem r2 that form hops with r1.
    Returns non-distinct results (we dedupe in Python).
    """
    return f"""
SELECT ?r2 WHERE {{
  ?h wdt:{r1} ?t .
  ?t ?r2 ?c .
  ?r2entity wikibase:directClaim ?r2 ;
            wikibase:propertyType wikibase:WikibaseItem .
}}
LIMIT {limit}
""".strip()


# ----------------------------
# Result Processing
# ----------------------------
def extract_r2_from_results(
    bindings: List[Dict[str, Any]],
    valid_r2_set: Optional[Set[str]] = None
) -> Set[str]:
    """
    Extract unique r2 PIDs from SPARQL results.
    Optionally filter to only those in valid_r2_set.
    """
    prefix = "http://www.wikidata.org/prop/direct/"
    found = set()

    for b in bindings:
        uri = b.get("r2", {}).get("value", "")
        if uri.startswith(prefix):
            pid = uri[len(prefix):]
            if pid.startswith("P"):
                if valid_r2_set is None or pid in valid_r2_set:
                    found.add(pid)

    return found


def discover_one_r1(
    r1: str,
    wdqs: WDQSClient,
    sample_limit: int,
    valid_r2_set: Optional[Set[str]],
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Run hop discovery query for a single r1 and build normalized output record."""
    query = build_hop_discovery_query(r1, sample_limit)
    resp = wdqs.post_query(query)
    now = time.time()

    if not resp.ok:
        logger.warning(f"[ERROR] {r1}: {resp.error}")
        return {
            "r1": r1,
            "valid_r2": [],
            "valid_r2_count": 0,
            "status": "ERROR",
            "error": resp.error,
            "http_code": resp.http,
            "query_time_sec": resp.elapsed_sec,
            "sample_limit": sample_limit,
            "rows_returned": 0,
            "updated_at": now,
        }

    bindings = resp.data.get("results", {}).get("bindings", [])
    rows_returned = len(bindings)

    if rows_returned == 0:
        logger.info(f"[NOT_FOUND] {r1}: no hops found")
        return {
            "r1": r1,
            "valid_r2": [],
            "valid_r2_count": 0,
            "status": "NOT_FOUND",
            "error": None,
            "http_code": 200,
            "query_time_sec": resp.elapsed_sec,
            "sample_limit": sample_limit,
            "rows_returned": 0,
            "updated_at": now,
        }

    found_r2 = extract_r2_from_results(bindings, valid_r2_set)
    found_r2_sorted = sorted(found_r2)

    if len(found_r2_sorted) == 0:
        logger.info(f"[NOT_FOUND] {r1}: rows={rows_returned} but 0 valid r2 after filtering")
        return {
            "r1": r1,
            "valid_r2": [],
            "valid_r2_count": 0,
            "status": "NOT_FOUND",
            "error": None,
            "reason": "filtered_all_candidates" if valid_r2_set is not None else "no_valid_r2_after_extraction",
            "http_code": 200,
            "query_time_sec": resp.elapsed_sec,
            "sample_limit": sample_limit,
            "rows_returned": rows_returned,
            "updated_at": now,
        }

    logger.info(f"[SUCCESS] {r1}: found {len(found_r2_sorted)} valid r2 from {rows_returned} rows in {resp.elapsed_sec:.1f}s")
    return {
        "r1": r1,
        "valid_r2": found_r2_sorted,
        "valid_r2_count": len(found_r2_sorted),
        "status": "SUCCESS",
        "error": None,
        "http_code": 200,
        "query_time_sec": resp.elapsed_sec,
        "sample_limit": sample_limit,
        "rows_returned": rows_returned,
        "updated_at": now,
    }


def read_input_docs(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass
    docs: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            obj = json.loads(line)
            if isinstance(obj, dict):
                docs.append(obj)
    return docs


def append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_existing_status_jsonl(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            r1 = obj.get("r1")
            st = obj.get("status")
            if isinstance(r1, str) and r1 and isinstance(st, str):
                out[r1] = st
    return out


def load_json_checkpoint(path: str) -> int:
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        idx = obj.get("next_index", 0)
        if isinstance(idx, int) and idx >= 0:
            return idx
    except Exception:
        return 0
    return 0


def save_json_checkpoint(path: str, payload: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ----------------------------
# Checkpoint Management
# ----------------------------
def get_checkpoint(meta_col, checkpoint_id: str, logger: logging.Logger) -> Optional[ObjectId]:
    """Get last processed document ID from checkpoint."""
    try:
        doc = meta_col.find_one({"_id": checkpoint_id}, {"last_input_id": 1})
        if not doc:
            return None
        last = doc.get("last_input_id")
        if not last:
            return None
        return ObjectId(last)
    except Exception as e:
        logger.warning(f"Invalid checkpoint value, starting from beginning: {e}")
        return None


def set_checkpoint(
    meta_col,
    checkpoint_id: str,
    last_input_id: ObjectId,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """Save checkpoint with optional extra metadata."""
    payload: Dict[str, Any] = {
        "last_input_id": str(last_input_id),
        "updated_at": time.time(),
    }
    if extra:
        payload.update(extra)
    meta_col.update_one({"_id": checkpoint_id}, {"$set": payload}, upsert=True)


# ----------------------------
# Thread-safe Stats
# ----------------------------
class Stats:
    """Thread-safe statistics counter."""
    def __init__(self):
        self.lock = threading.Lock()
        self.scanned = 0
        self.processed = 0
        self.success = 0
        self.not_found = 0
        self.errors = 0
        self.skipped = 0
        self.saved = 0
        self.last_seen_id: Optional[ObjectId] = None
        self.start_time = time.time()
    
    def increment_scanned(self, _id: ObjectId):
        with self.lock:
            self.scanned += 1
            self.last_seen_id = _id
    
    def increment_skipped(self):
        with self.lock:
            self.skipped += 1
    
    def increment_processed(self, status: str):
        with self.lock:
            self.processed += 1
            if status == "SUCCESS":
                self.success += 1
            elif status == "NOT_FOUND":
                self.not_found += 1
            else:
                self.errors += 1
    
    def increment_saved(self):
        with self.lock:
            self.saved += 1
    
    def get_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            elapsed = time.time() - self.start_time
            return {
                "scanned": self.scanned,
                "processed": self.processed,
                "success": self.success,
                "not_found": self.not_found,
                "errors": self.errors,
                "skipped": self.skipped,
                "saved": self.saved,
                "last_seen_id": self.last_seen_id,
                "elapsed_sec": elapsed,
                "rate_per_sec": self.processed / elapsed if elapsed > 0 else 0,
            }


# ----------------------------
# Worker Functions
# ----------------------------
def query_worker(
    wdqs: WDQSClient,
    task_queue: queue.Queue,
    result_queue: queue.Queue,
    sample_limit: int,
    valid_r2_set: Optional[Set[str]],
    stats: Stats,
    logger: logging.Logger,
    delay_between_queries: float,
):
    """Worker thread that queries WDQS and puts results in result_queue."""
    while True:
        try:
            item = task_queue.get(timeout=1)
        except queue.Empty:
            continue
        
        if item is None:  # Poison pill
            task_queue.task_done()
            break
        
        r1, _id = item
        
        try:
            result = discover_one_r1(r1, wdqs, sample_limit, valid_r2_set, logger)
            stats.increment_processed(result["status"])
            result_queue.put(result)

        except Exception as e:
            logger.exception(f"Unhandled error processing {r1}: {e}")
            stats.increment_processed("ERROR")
            result_queue.put({
                "r1": r1,
                "valid_r2": [],
                "valid_r2_count": 0,
                "status": "ERROR",
                "error": str(e),
                "http_code": None,
                "query_time_sec": 0,
                "sample_limit": sample_limit,
                "rows_returned": 0,
                "updated_at": time.time(),
            })
        
        task_queue.task_done()
        
        if delay_between_queries > 0:
            time.sleep(delay_between_queries)


def save_worker(
    result_queue: queue.Queue,
    output_col,
    stats: Stats,
    logger: logging.Logger,
):
    """Worker thread that saves results to MongoDB."""
    while True:
        try:
            result = result_queue.get(timeout=1)
        except queue.Empty:
            continue
        
        if result is None:  # Poison pill
            result_queue.task_done()
            break
        
        try:
            output_col.update_one(
                {"r1": result["r1"]},
                {"$set": result},
                upsert=True
            )
            stats.increment_saved()
        except Exception as e:
            logger.error(f"Failed to save result for {result['r1']}: {e}")
        
        result_queue.task_done()


def checkpoint_worker(
    meta_col,
    checkpoint_id: str,
    stats: Stats,
    checkpoint_interval: int,
    logger: logging.Logger,
    stop_event: threading.Event,
):
    """Worker thread that periodically saves checkpoints."""
    last_scanned = 0
    
    while not stop_event.is_set():
        time.sleep(5)  # Check every 5 seconds
        
        snapshot = stats.get_snapshot()
        current_scanned = snapshot["scanned"]
        
        # Checkpoint if we've scanned enough new documents
        if current_scanned - last_scanned >= checkpoint_interval and snapshot["last_seen_id"]:
            set_checkpoint(
                meta_col,
                checkpoint_id,
                snapshot["last_seen_id"],
                extra={
                    "scanned": snapshot["scanned"],
                    "processed": snapshot["processed"],
                    "success": snapshot["success"],
                    "not_found": snapshot["not_found"],
                    "errors": snapshot["errors"],
                    "skipped": snapshot["skipped"],
                    "saved": snapshot["saved"],
                    "rate_per_sec": snapshot["rate_per_sec"],
                },
            )
            logger.info(
                f"Checkpoint: scanned={snapshot['scanned']} processed={snapshot['processed']} "
                f"success={snapshot['success']} not_found={snapshot['not_found']} "
                f"errors={snapshot['errors']} skipped={snapshot['skipped']} "
                f"rate={snapshot['rate_per_sec']:.3f}/sec"
            )
            last_scanned = current_scanned


# ----------------------------
# Index Management
# ----------------------------
def ensure_indexes(output_col, logger: logging.Logger) -> None:
    """Ensure indexes exist, handling duplicates gracefully."""
    try:
        output_col.create_index([("r1", ASCENDING)], unique=True)
    except DuplicateKeyError:
        logger.warning("Duplicate r1 values exist. Cleaning up...")
        # Find and remove duplicates, keeping the most recent
        pipeline = [
            {"$group": {
                "_id": "$r1",
                "count": {"$sum": 1},
                "docs": {"$push": {"_id": "$_id", "updated_at": {"$ifNull": ["$updated_at", 0]}}}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        for dup in output_col.aggregate(pipeline):
            docs = sorted(dup["docs"], key=lambda x: x.get("updated_at", 0), reverse=True)
            ids_to_delete = [d["_id"] for d in docs[1:]]
            output_col.delete_many({"_id": {"$in": ids_to_delete}})
            logger.info(f"Removed {len(ids_to_delete)} duplicate(s) for r1={dup['_id']}")
        # Retry index creation
        output_col.create_index([("r1", ASCENDING)], unique=True)
    except Exception as e:
        if "duplicate key" in str(e).lower():
            logger.warning(f"Duplicate key error: {e}. Cleaning up...")
            # Same cleanup logic
            pipeline = [
                {"$group": {
                    "_id": "$r1",
                    "count": {"$sum": 1},
                    "docs": {"$push": {"_id": "$_id", "updated_at": {"$ifNull": ["$updated_at", 0]}}}
                }},
                {"$match": {"count": {"$gt": 1}}}
            ]
            for dup in output_col.aggregate(pipeline):
                docs = sorted(dup["docs"], key=lambda x: x.get("updated_at", 0), reverse=True)
                ids_to_delete = [d["_id"] for d in docs[1:]]
                output_col.delete_many({"_id": {"$in": ids_to_delete}})
                logger.info(f"Removed {len(ids_to_delete)} duplicate(s) for r1={dup['_id']}")
            output_col.create_index([("r1", ASCENDING)], unique=True)
        else:
            raise
    
    output_col.create_index([("status", ASCENDING)])
    logger.info("Indexes ensured on output collection")


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Hop Discovery: Find valid r2 for each r1")

    # MongoDB
    parser.add_argument("--mongo_uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
    parser.add_argument("--db", default="wikidata_ontology")
    parser.add_argument("--input_col", default="relation_profiles", help="Input collection with r1 relations")
    parser.add_argument("--output_col", default="hop_discovery", help="Output collection for results")
    parser.add_argument("--meta_col", default="_meta", help="Checkpoint collection")
    parser.add_argument("--checkpoint_id", default="hop_discovery_checkpoint", help="Checkpoint document ID")

    # File mode (JSON/JSONL input + JSONL output)
    parser.add_argument("--input_json", default="", help="Path to input JSON/JSONL exported relation profiles")
    parser.add_argument("--output_jsonl", default="hop_discovery.jsonl", help="Output JSONL path for file mode")
    parser.add_argument("--checkpoint_json", default="hop_discovery_checkpoint.json", help="Checkpoint JSON path for file mode")

    # WDQS
    parser.add_argument("--wdqs_endpoint", default="https://query.wikidata.org/sparql")
    parser.add_argument(
        "--user_agent",
        default=os.getenv("WDQS_USER_AGENT", ""),
        help="Descriptive UA, e.g. 'hop_discovery/1.0 (mailto:you@example.com)'",
    )
    parser.add_argument("--timeout_sec", type=int, default=90, help="WDQS query timeout")
    parser.add_argument("--max_retries", type=int, default=5, help="Max retries per query")
    parser.add_argument("--backoff_base_sec", type=float, default=2.0)
    parser.add_argument("--backoff_cap_sec", type=float, default=120.0)

    # Query parameters
    parser.add_argument("--sample_limit", type=int, default=50000, help="LIMIT for SPARQL query")
    parser.add_argument("--filter_to_valid_r2", action="store_true", help="Filter results to only relations in input_col")

    # Processing
    parser.add_argument("--checkpoint_every", type=int, default=50, help="Save checkpoint every N scanned documents")
    parser.add_argument("--delay_between_queries", type=float, default=0.5, help="Delay between queries (seconds)")
    parser.add_argument("--skip_existing", action="store_true", help="Skip r1 already in output collection")
    parser.add_argument("--retry_errors", action="store_true", help="Retry r1 that previously had ERROR status")

    # Threading
    parser.add_argument("--num_query_workers", type=int, default=1, 
                        help="Number of query worker threads (be careful with WDQS rate limits)")
    parser.add_argument("--num_save_workers", type=int, default=2, help="Number of save worker threads")

    # Logging
    parser.add_argument("--log_level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()
    logger = setup_logging(args.log_level)

    # Validate worker counts
    if args.num_query_workers < 1 or args.num_save_workers < 1:
        logger.error("--num_query_workers and --num_save_workers must both be >= 1")
        sys.exit(2)

    # Validate user agent
    if not args.user_agent or "mailto:" not in args.user_agent:
        logger.error(
            "You must provide a descriptive --user_agent containing contact info (mailto:...). "
            "This is required by WDQS to avoid 403 blocks."
        )
        sys.exit(2)

    # File mode: process exported JSON/JSONL without MongoDB
    if args.input_json:
        wdqs = WDQSClient(
            endpoint=args.wdqs_endpoint,
            user_agent=args.user_agent,
            timeout_sec=args.timeout_sec,
            max_retries=args.max_retries,
            backoff_base_sec=args.backoff_base_sec,
            backoff_cap_sec=args.backoff_cap_sec,
            logger=logger,
        )

        docs = read_input_docs(args.input_json)
        logger.info(f"Loaded {len(docs)} docs from {args.input_json}")

        # Keep only wikibase-item relation rows with property_id
        candidates: List[str] = []
        for d in docs:
            pid = d.get("property_id")
            dt = ((d.get("metadata") or {}).get("datatype") or "").strip().lower()
            if isinstance(pid, str) and pid and dt == "wikibase-item":
                candidates.append(pid)
        logger.info(f"File mode candidates (wikibase-item): {len(candidates)}")

        # De-duplicate while preserving order.
        candidates = list(dict.fromkeys(candidates))

        valid_r2_set: Optional[Set[str]] = None
        if args.filter_to_valid_r2:
            valid_r2_set = set(candidates)
            logger.info(f"Valid r2 set contains {len(valid_r2_set)} properties (from input file)")

        existing_status = load_existing_status_jsonl(args.output_jsonl) if args.skip_existing else {}
        if args.skip_existing:
            logger.info(f"Loaded {len(existing_status)} existing r1 from {args.output_jsonl}")

        # In threaded file mode, resume is output-driven via --skip_existing.
        ckpt_idx = load_json_checkpoint(args.checkpoint_json)
        if ckpt_idx > 0:
            logger.info("Checkpoint found; threaded file mode resumes via --skip_existing + existing output")

        scanned = len(candidates)
        processed = success = not_found = errors = skipped = 0
        started = time.time()

        tasks: List[tuple[int, str]] = []
        for idx, r1 in enumerate(candidates):
            if args.skip_existing:
                old = existing_status.get(r1)
                if old in ("SUCCESS", "NOT_FOUND") or (old == "ERROR" and not args.retry_errors):
                    skipped += 1
                    continue
            tasks.append((idx, r1))

        logger.info(f"File mode queued tasks: {len(tasks)} (skipped={skipped})")

        def _run_one(task: tuple[int, str]) -> tuple[int, Dict[str, Any]]:
            idx, r1 = task
            result = discover_one_r1(r1, wdqs, args.sample_limit, valid_r2_set, logger)
            if args.delay_between_queries > 0:
                time.sleep(args.delay_between_queries)
            return idx, result

        with ThreadPoolExecutor(max_workers=args.num_query_workers) as ex:
            futures = {ex.submit(_run_one, t): t[0] for t in tasks}
            max_completed_idx = -1
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    idx2, result = fut.result()
                    idx = idx2
                except Exception as e:
                    r1 = "UNKNOWN"
                    result = {
                        "r1": r1,
                        "valid_r2": [],
                        "valid_r2_count": 0,
                        "status": "ERROR",
                        "error": f"unhandled_exception: {e}",
                        "http_code": None,
                        "query_time_sec": 0,
                        "sample_limit": args.sample_limit,
                        "rows_returned": 0,
                        "updated_at": time.time(),
                    }

                append_jsonl(args.output_jsonl, result)
                max_completed_idx = max(max_completed_idx, idx)

                st = result.get("status")
                processed += 1
                if st == "SUCCESS":
                    success += 1
                elif st == "NOT_FOUND":
                    not_found += 1
                else:
                    errors += 1

                if processed % args.checkpoint_every == 0:
                    elapsed = time.time() - started
                    save_json_checkpoint(args.checkpoint_json, {
                        "next_index_hint": max_completed_idx + 1,
                        "scanned": scanned,
                        "processed": processed,
                        "queued_tasks": len(tasks),
                        "success": success,
                        "not_found": not_found,
                        "errors": errors,
                        "skipped": skipped,
                        "rate_per_sec": (processed / elapsed) if elapsed > 0 else 0.0,
                        "updated_at": time.time(),
                    })

        elapsed = time.time() - started
        save_json_checkpoint(args.checkpoint_json, {
            "done": True,
            "next_index_hint": len(candidates),
            "scanned": scanned,
            "processed": processed,
            "queued_tasks": len(tasks),
            "success": success,
            "not_found": not_found,
            "errors": errors,
            "skipped": skipped,
            "rate_per_sec": (processed / elapsed) if elapsed > 0 else 0.0,
            "total_elapsed_sec": elapsed,
            "updated_at": time.time(),
        })
        logger.info(
            f"Done (file mode)! scanned={scanned} processed={processed} success={success} "
            f"not_found={not_found} errors={errors} skipped={skipped}"
        )
        return

    # Connect to MongoDB
    client = MongoClient(args.mongo_uri)
    db = client[args.db]

    input_col = db[args.input_col]
    output_col = db[args.output_col]
    meta_col = db[args.meta_col]

    # Ensure indexes
    ensure_indexes(output_col, logger)

    # Build valid r2 set if filtering
    valid_r2_set: Optional[Set[str]] = None
    if args.filter_to_valid_r2:
        logger.info("Building valid r2 set from input collection...")
        valid_r2_set = set()
        for doc in input_col.find({"metadata.datatype": "wikibase-item"}, {"property_id": 1}):
            pid = doc.get("property_id")
            if pid:
                valid_r2_set.add(pid)
        logger.info(f"Valid r2 set contains {len(valid_r2_set)} properties")

    # Get existing r1 in output (for skip logic)
    existing_r1: Set[str] = set()
    if args.skip_existing:
        logger.info("Loading existing r1 from output collection...")
        for doc in output_col.find({}, {"r1": 1, "status": 1}):
            r1 = doc.get("r1")
            status = doc.get("status")
            if r1:
                if status in ("SUCCESS", "NOT_FOUND"):
                    existing_r1.add(r1)
                elif status == "ERROR" and not args.retry_errors:
                    existing_r1.add(r1)
        logger.info(f"Will skip {len(existing_r1)} already processed r1")

    # Initialize WDQS client
    wdqs = WDQSClient(
        endpoint=args.wdqs_endpoint,
        user_agent=args.user_agent,
        timeout_sec=args.timeout_sec,
        max_retries=args.max_retries,
        backoff_base_sec=args.backoff_base_sec,
        backoff_cap_sec=args.backoff_cap_sec,
        logger=logger,
    )

    # Get checkpoint
    last_id = get_checkpoint(meta_col, args.checkpoint_id, logger)
    logger.info(f"Starting hop discovery, resume_after_id={last_id}")

    # Build query for input documents
    query: Dict[str, Any] = {"metadata.datatype": "wikibase-item"}
    if last_id is not None:
        logger.info("Checkpoint found; scanning from start to avoid skipping unprocessed docs")

    # Count total for progress
    total_count = input_col.count_documents({"metadata.datatype": "wikibase-item"})
    remaining_count = input_col.count_documents(query)
    logger.info(f"Total WikibaseItem relations: {total_count}, remaining: {remaining_count}")

    # Initialize stats and queues
    stats = Stats()
    task_queue: queue.Queue = queue.Queue(maxsize=100)
    result_queue: queue.Queue = queue.Queue(maxsize=100)
    stop_checkpoint = threading.Event()

    # Start workers
    query_threads = []
    for i in range(args.num_query_workers):
        t = threading.Thread(
            target=query_worker,
            args=(wdqs, task_queue, result_queue, args.sample_limit, 
                  valid_r2_set, stats, logger, args.delay_between_queries),
            name=f"query-worker-{i}",
            daemon=True,
        )
        t.start()
        query_threads.append(t)
    
    save_threads = []
    for i in range(args.num_save_workers):
        t = threading.Thread(
            target=save_worker,
            args=(result_queue, output_col, stats, logger),
            name=f"save-worker-{i}",
            daemon=True,
        )
        t.start()
        save_threads.append(t)
    
    checkpoint_thread = threading.Thread(
        target=checkpoint_worker,
        args=(meta_col, args.checkpoint_id, stats, args.checkpoint_every, logger, stop_checkpoint),
        name="checkpoint-worker",
        daemon=True,
    )
    checkpoint_thread.start()

    # Feed tasks
    try:
        cursor = input_col.find(query, {"_id": 1, "property_id": 1}).sort([("_id", ASCENDING)])
        
        for doc in cursor:
            _id = doc.get("_id")
            r1 = doc.get("property_id")
            
            if not r1 or not isinstance(_id, ObjectId):
                continue
            
            stats.increment_scanned(_id)
            
            # Skip if already processed
            if r1 in existing_r1:
                stats.increment_skipped()
                continue
            
            # Add to queue (blocks if queue is full)
            task_queue.put((r1, _id))
        
        # Signal query workers to stop
        for _ in query_threads:
            task_queue.put(None)
        
        # Wait for query workers
        for t in query_threads:
            t.join()
        
        # Wait for all results to be processed
        task_queue.join()
        
        # Signal save workers to stop
        for _ in save_threads:
            result_queue.put(None)
        
        # Wait for save workers
        for t in save_threads:
            t.join()
        
        result_queue.join()
        
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
    finally:
        # Stop checkpoint worker
        stop_checkpoint.set()
        checkpoint_thread.join(timeout=2)
        
        # Final checkpoint
        snapshot = stats.get_snapshot()
        if snapshot["last_seen_id"]:
            set_checkpoint(
                meta_col,
                args.checkpoint_id,
                snapshot["last_seen_id"],
                extra={
                    "done": True,
                    "scanned": snapshot["scanned"],
                    "processed": snapshot["processed"],
                    "success": snapshot["success"],
                    "not_found": snapshot["not_found"],
                    "errors": snapshot["errors"],
                    "skipped": snapshot["skipped"],
                    "saved": snapshot["saved"],
                    "rate_per_sec": snapshot["rate_per_sec"],
                    "total_elapsed_sec": snapshot["elapsed_sec"],
                },
            )
        
        logger.info(
            f"Done! scanned={snapshot['scanned']} processed={snapshot['processed']} "
            f"success={snapshot['success']} not_found={snapshot['not_found']} "
            f"errors={snapshot['errors']} skipped={snapshot['skipped']} "
            f"saved={snapshot['saved']}"
        )


if __name__ == "__main__":
    main()
    # python hop_discovery.py --user_agent "hop_discovery/1.0 (mailto:oamrans@gmail.com)"

