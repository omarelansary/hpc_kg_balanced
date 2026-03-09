#!/usr/bin/env python3
"""Convert hop_support-like outputs into hop_discovery-like records.

Output schema per r1:
{
  "r1": "P31",
  "valid_r2": ["P279", ...],
  "valid_r2_count": 123,
  "status": "SUCCESS|NOT_FOUND|ERROR",
  "error": null | "..."
}

Supports input records that contain one of:
- support_data (v2/v3): {r2: {"total": n, ...}} or numeric payloads
- support_by_r2 (v1): {r2: n}
- top_support/topk_support: [{"r2": "...", "support": n}, ...]
- valid_r2 (fallback; treated as unknown support and kept only if min_total_support <= 0)
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

PID_RE = re.compile(r"^P[1-9]\d*$")


def is_pid(x: Any) -> bool:
    return isinstance(x, str) and PID_RE.match(x) is not None


def parse_numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def load_json_or_jsonl(path: str) -> list[dict[str, Any]]:
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

    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            out.append(obj)
    return out


def support_map_from_record(rec: dict[str, Any], min_total_support: float) -> tuple[dict[str, float], int]:
    """Return (r2->support_total, unknown_support_r2_count)."""
    support_map: dict[str, float] = {}
    unknown_support = 0

    sd = rec.get("support_data")
    if isinstance(sd, dict):
        for pid, payload in sd.items():
            if not is_pid(pid):
                continue
            if isinstance(payload, dict):
                total = parse_numeric(payload.get("total", payload.get("support", 0.0)))
            else:
                total = parse_numeric(payload, 0.0)
            support_map[pid] = max(support_map.get(pid, 0.0), total)
        return support_map, unknown_support

    by_r2 = rec.get("support_by_r2")
    if isinstance(by_r2, dict):
        for pid, val in by_r2.items():
            if not is_pid(pid):
                continue
            total = parse_numeric(val, 0.0)
            support_map[pid] = max(support_map.get(pid, 0.0), total)
        return support_map, unknown_support

    for key in ("top_support", "topk_support"):
        arr = rec.get(key)
        if not isinstance(arr, list):
            continue
        for row in arr:
            if not isinstance(row, dict):
                continue
            pid = row.get("r2")
            if not is_pid(pid):
                continue
            total = parse_numeric(row.get("support", 0.0), 0.0)
            support_map[pid] = max(support_map.get(pid, 0.0), total)
        if support_map:
            return support_map, unknown_support

    # Fallback for already hop_discovery-like rows where support is unknown.
    vals = rec.get("valid_r2")
    if isinstance(vals, list):
        for pid in vals:
            if not is_pid(pid):
                continue
            # Unknown support: strict filtering means they pass only if threshold <= 0.
            support_map[pid] = 0.0 if min_total_support > 0 else min_total_support
            unknown_support += 1

    return support_map, unknown_support


def to_hop_discovery_like(rec: dict[str, Any], min_total_support: float) -> tuple[dict[str, Any] | None, Counter]:
    c = Counter()
    r1 = rec.get("r1")
    if not is_pid(r1):
        c["skipped_missing_or_bad_r1"] += 1
        return None, c

    support_map, unknown_support_count = support_map_from_record(rec, min_total_support)
    c["unknown_support_candidates"] += int(unknown_support_count)

    valid_r2 = sorted(pid for pid, total in support_map.items() if total >= min_total_support)
    c["valid_r2_after_filter_total"] += len(valid_r2)
    c["valid_r2_before_filter_total"] += len(support_map)
    c["valid_r2_removed_by_threshold_total"] += max(0, len(support_map) - len(valid_r2))

    src_status = rec.get("status")
    src_error = rec.get("error")

    if len(valid_r2) > 0:
        out_status = "SUCCESS"
        out_error = None
    else:
        if isinstance(src_status, str) and src_status in {"ERROR", "NOT_FOUND"}:
            out_status = src_status
            out_error = src_error if isinstance(src_error, str) else None
        else:
            out_status = "NOT_FOUND"
            out_error = None

    out = {
        "r1": r1,
        "status": out_status,
        "valid_r2": valid_r2,
        "valid_r2_count": len(valid_r2),
        "error": out_error,
    }
    c[f"out_status_{out_status}"] += 1
    return out, c


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert hop_support-like JSON/JSONL to hop_discovery-like JSONL.")
    ap.add_argument("--input", required=True, help="Input JSON/JSONL path (hop_support-like).")
    ap.add_argument("--output", required=True, help="Output JSONL path (hop_discovery-like).")
    ap.add_argument(
        "--min_total_support",
        type=float,
        default=1.0,
        help="Keep r2 only when total support >= this value. Default: 1.",
    )
    ap.add_argument(
        "--dedupe_latest_by_r1",
        action="store_true",
        help="If set, keep only latest row per r1 from input order.",
    )
    args = ap.parse_args()

    records = load_json_or_jsonl(args.input)
    counters = Counter()
    counters["input_records"] = len(records)

    out_rows: list[dict[str, Any]] = []
    for rec in records:
        out, c = to_hop_discovery_like(rec, float(args.min_total_support))
        counters.update(c)
        if out is not None:
            out_rows.append(out)

    if args.dedupe_latest_by_r1:
        latest_by_r1: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        seen: set[str] = set()
        for row in out_rows:
            r1 = row["r1"]
            if r1 not in seen:
                seen.add(r1)
                order.append(r1)
            latest_by_r1[r1] = row
        out_rows = [latest_by_r1[r1] for r1 in order]
        counters["deduped_rows"] = len(out_rows)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as w:
        for row in out_rows:
            w.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("convert_complete")
    print(f"input_records: {counters['input_records']}")
    print(f"output_rows: {len(out_rows)}")
    print(f"min_total_support: {args.min_total_support}")
    print(f"valid_r2_before_filter_total: {counters['valid_r2_before_filter_total']}")
    print(f"valid_r2_after_filter_total: {counters['valid_r2_after_filter_total']}")
    print(f"valid_r2_removed_by_threshold_total: {counters['valid_r2_removed_by_threshold_total']}")
    print(f"unknown_support_candidates: {counters['unknown_support_candidates']}")
    print(f"out_status_SUCCESS: {counters['out_status_SUCCESS']}")
    print(f"out_status_NOT_FOUND: {counters['out_status_NOT_FOUND']}")
    print(f"out_status_ERROR: {counters['out_status_ERROR']}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()

    # python src/enrichments_and_filters/convert_hop_support_to_hop_discovery_like.py --input data/archived/hop_support_v2_w_failed_statuses.wikibase_item_only_before_target_enrichment.jsonl --output data/processed/hop_support_v2_before_target_enrichment_hopdiscovery_like.jsonl --min_total_support 0 --dedupe_latest_by_r1 
