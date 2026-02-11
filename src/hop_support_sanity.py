#!/usr/bin/env python3
"""
hop_support_sanity.py

Sanity + exploratory statistics for hop_support.jsonl produced by hop_support.py.

What it reports (research-grade, practical):
1) Record counts by support_status, mode, input_status
2) Coverage and success rates
3) Support distribution diagnostics:
   - per r1: outdegree_nonzero (#r2 with support>0)
   - per r1: total_support, top1_support, top1_share, top10_share, entropy
4) Hub detection candidates (high outdegree or high top1_share)
5) Mode-specific completeness:
   - values_chunked: how many r2 have nonzero vs total candidates
   - discover_topk: how many returned r2 vs topk
6) Potential anomalies:
   - status == SUCCESS but empty support list/map
   - missing fields
7) Optional: write derived edge list CSV (r1,r2,support,weight,mode,input_status)

Usage:
  python hop_support_sanity.py --input data/processed/hop_support.jsonl
  python hop_support_sanity.py --input hop_support.jsonl --write_edges edges.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple


def iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception as e:
                yield {"__parse_error__": True, "__line__": i, "__error__": str(e), "__raw__": line[:2000]}


def safe_log(x: float) -> float:
    return math.log(x) if x > 0 else float("-inf")


def entropy_from_counts(counts: List[int]) -> float:
    """Shannon entropy (natural log). Returns 0 if sum is 0 or singleton."""
    s = sum(counts)
    if s <= 0:
        return 0.0
    ent = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / s
        ent -= p * math.log(p)
    return ent


def summarize_numeric(xs: List[float]) -> Dict[str, float]:
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    if not xs:
        return {}
    xs_sorted = sorted(xs)

    def pct(p: float) -> float:
        if not xs_sorted:
            return float("nan")
        k = (len(xs_sorted) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return xs_sorted[int(k)]
        return xs_sorted[f] * (c - k) + xs_sorted[c] * (k - f)

    return {
        "n": float(len(xs_sorted)),
        "min": float(xs_sorted[0]),
        "p25": float(pct(0.25)),
        "median": float(pct(0.50)),
        "p75": float(pct(0.75)),
        "p90": float(pct(0.90)),
        "p95": float(pct(0.95)),
        "max": float(xs_sorted[-1]),
        "mean": float(statistics.mean(xs_sorted)),
        "stdev": float(statistics.pstdev(xs_sorted)) if len(xs_sorted) > 1 else 0.0,
    }


def extract_supports(rec: Dict[str, Any]) -> Tuple[List[Tuple[str, int]], str]:
    """
    Returns (list_of_(r2,support), source_tag)
    source_tag in {"support_by_r2","topk_support","top_support","none"}
    """
    if isinstance(rec.get("support_by_r2"), dict) and rec["support_by_r2"]:
        pairs = []
        for k, v in rec["support_by_r2"].items():
            try:
                pairs.append((str(k), int(v)))
            except Exception:
                continue
        return pairs, "support_by_r2"

    # topk_support: list of dicts
    if isinstance(rec.get("topk_support"), list) and rec["topk_support"]:
        pairs = []
        for d in rec["topk_support"]:
            if not isinstance(d, dict):
                continue
            r2 = d.get("r2")
            supp = d.get("support")
            try:
                pairs.append((str(r2), int(supp)))
            except Exception:
                continue
        return pairs, "topk_support"

    # top_support: list of dicts (values_chunked convenience)
    if isinstance(rec.get("top_support"), list) and rec["top_support"]:
        pairs = []
        for d in rec["top_support"]:
            if not isinstance(d, dict):
                continue
            r2 = d.get("r2")
            supp = d.get("support")
            try:
                pairs.append((str(r2), int(supp)))
            except Exception:
                continue
        return pairs, "top_support"

    return [], "none"


def weight_log1p(support: int) -> float:
    return math.log1p(max(0, support))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to hop_support.jsonl")
    ap.add_argument("--write_edges", default="", help="Optional: write edge list CSV to this path")
    ap.add_argument("--hub_outdeg_threshold", type=int, default=150, help="Flag r1 with outdegree_nonzero >= this")
    ap.add_argument("--hub_top1share_threshold", type=float, default=0.80, help="Flag r1 with top1_share >= this")
    ap.add_argument("--min_support_for_edge", type=int, default=1, help="Edges with support < this excluded from edge CSV")
    args = ap.parse_args()

    path = args.input
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    # Global counters
    parse_errors = 0
    total_records = 0
    r1_seen = set()

    by_support_status = Counter()
    by_mode = Counter()
    by_input_status = Counter()
    by_mode_support_status = Counter()
    anomalies = Counter()

    # Numeric collections for summaries
    outdeg_nonzero_list = []
    outdeg_total_list = []
    total_support_list = []
    top1_support_list = []
    top1_share_list = []
    top10_share_list = []
    entropy_list = []
    elapsed_list = []

    # For deeper inspection / hubs
    hub_candidates = []  # (r1, outdeg_nonzero, total_support, top1_share, mode, input_status)
    empty_success_r1 = []
    failed_r1 = []

    # Edge output
    edge_rows: List[Tuple[str, str, int, float, str, str, str]] = []
    # schema: r1,r2,support,weight,mode,input_status,status

    for rec in iter_jsonl(path):
        total_records += 1

        if rec.get("__parse_error__"):
            parse_errors += 1
            continue

        r1 = rec.get("r1")
        if not isinstance(r1, str) or not r1.startswith("P"):
            anomalies["missing_or_bad_r1"] += 1
            continue
        r1_seen.add(r1)

        status = str(rec.get("status", "MISSING"))
        mode = str(rec.get("mode", "MISSING"))
        input_status = str(rec.get("input_status", "MISSING"))

        by_support_status[status] += 1
        by_mode[mode] += 1
        by_input_status[input_status] += 1
        by_mode_support_status[(mode, status)] += 1

        # elapsed
        try:
            elapsed = float(rec.get("elapsed_sec", float("nan")))
            if not math.isnan(elapsed):
                elapsed_list.append(elapsed)
        except Exception:
            pass

        pairs, source_tag = extract_supports(rec)

        if status == "SUCCESS" and not pairs:
            anomalies["success_but_no_support_pairs"] += 1
            empty_success_r1.append((r1, mode, input_status, source_tag))
            continue

        if status != "SUCCESS":
            failed_r1.append((r1, mode, input_status, rec.get("error")))
            continue

        # Supports
        supports = [max(0, int(s)) for _, s in pairs]
        supports_sorted = sorted(supports, reverse=True)

        total_support = sum(supports_sorted)
        outdeg_total = len(supports_sorted)
        outdeg_nonzero = sum(1 for s in supports_sorted if s > 0)

        top1 = supports_sorted[0] if supports_sorted else 0
        top10 = sum(supports_sorted[:10]) if supports_sorted else 0

        top1_share = (top1 / total_support) if total_support > 0 else 0.0
        top10_share = (top10 / total_support) if total_support > 0 else 0.0
        ent = entropy_from_counts(supports_sorted)

        outdeg_nonzero_list.append(float(outdeg_nonzero))
        outdeg_total_list.append(float(outdeg_total))
        total_support_list.append(float(total_support))
        top1_support_list.append(float(top1))
        top1_share_list.append(float(top1_share))
        top10_share_list.append(float(top10_share))
        entropy_list.append(float(ent))

        # hub flags
        if outdeg_nonzero >= args.hub_outdeg_threshold or top1_share >= args.hub_top1share_threshold:
            hub_candidates.append((r1, outdeg_nonzero, total_support, top1_share, mode, input_status))

        # edges
        if args.write_edges:
            for r2, supp in pairs:
                if not isinstance(r2, str) or not r2.startswith("P"):
                    continue
                if supp < args.min_support_for_edge:
                    continue
                edge_rows.append((r1, r2, supp, weight_log1p(supp), mode, input_status, status))

    # ---- Print report ----
    print("\n==================== hop_support SANITY REPORT ====================")
    print(f"Input file                 : {path}")
    print(f"Total JSONL lines read      : {total_records}")
    print(f"Parse errors               : {parse_errors}")
    print(f"Distinct r1 seen            : {len(r1_seen)}")
    print("-------------------------------------------------------------------")
    print("Counts by support status:")
    for k, v in by_support_status.most_common():
        print(f"  {k:18s} {v}")
    print("-------------------------------------------------------------------")
    print("Counts by mode:")
    for k, v in by_mode.most_common():
        print(f"  {k:18s} {v}")
    print("-------------------------------------------------------------------")
    print("Counts by input_status (from hop_discovery):")
    for k, v in by_input_status.most_common():
        print(f"  {k:18s} {v}")
    print("-------------------------------------------------------------------")
    print("Mode × support_status:")
    for (m, s), v in sorted(by_mode_support_status.items(), key=lambda x: (-x[1], x[0])):
        print(f"  mode={m:22s} status={s:12s} count={v}")
    print("-------------------------------------------------------------------")
    if anomalies:
        print("Anomalies:")
        for k, v in anomalies.most_common():
            print(f"  {k:30s} {v}")
        print("-------------------------------------------------------------------")

    print("Per-r1 distributions (only support_status=SUCCESS with non-empty supports):")
    for name, xs in [
        ("outdeg_total (#r2 returned)", outdeg_total_list),
        ("outdeg_nonzero (#r2 with support>0)", outdeg_nonzero_list),
        ("total_support", total_support_list),
        ("top1_support", top1_support_list),
        ("top1_share", top1_share_list),
        ("top10_share", top10_share_list),
        ("entropy", entropy_list),
        ("elapsed_sec", elapsed_list),
    ]:
        summ = summarize_numeric(xs)
        if not summ:
            print(f"  {name:35s}: (no data)")
            continue
        print(
            f"  {name:35s}: "
            f"n={int(summ['n'])} min={summ['min']:.4g} p25={summ['p25']:.4g} "
            f"med={summ['median']:.4g} p75={summ['p75']:.4g} p90={summ['p90']:.4g} "
            f"p95={summ['p95']:.4g} max={summ['max']:.4g} mean={summ['mean']:.4g} sd={summ['stdev']:.4g}"
        )

    # Top hub candidates
    print("-------------------------------------------------------------------")
    hub_candidates_sorted = sorted(
        hub_candidates,
        key=lambda x: (-(x[1]), -(x[3]), -(x[2])),  # outdeg_nonzero desc, top1_share desc, total_support desc
    )
    print(f"Hub candidates (outdeg_nonzero >= {args.hub_outdeg_threshold} OR top1_share >= {args.hub_top1share_threshold}): {len(hub_candidates_sorted)}")
    for row in hub_candidates_sorted[:25]:
        r1, outdeg_nz, tot_s, t1s, mode, input_status = row
        print(f"  r1={r1:8s} outdeg_nz={outdeg_nz:4d} total_support={tot_s:10d} top1_share={t1s:0.3f} mode={mode} input_status={input_status}")

    # List a few empty-success records (for debugging)
    if empty_success_r1:
        print("-------------------------------------------------------------------")
        print("Examples: status=SUCCESS but no support pairs (first 10):")
        for r1, mode, inp, src in empty_success_r1[:10]:
            print(f"  r1={r1} mode={mode} input_status={inp} extracted_from={src}")

    # List a few failed records
    if failed_r1:
        print("-------------------------------------------------------------------")
        print("Examples: status!=SUCCESS (first 10):")
        for r1, mode, inp, err in failed_r1[:10]:
            print(f"  r1={r1} mode={mode} input_status={inp} err={err}")

    # Write edges if requested
    if args.write_edges:
        os.makedirs(os.path.dirname(args.write_edges) or ".", exist_ok=True)
        with open(args.write_edges, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["r1", "r2", "support", "weight_log1p", "mode", "input_status", "status"])
            for row in edge_rows:
                w.writerow(row)
        print("-------------------------------------------------------------------")
        print(f"Wrote edge list CSV: {args.write_edges}")
        print(f"Edges written (support >= {args.min_support_for_edge}): {len(edge_rows)}")

    print("===================================================================\n")


if __name__ == "__main__":
    main()
