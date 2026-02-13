#!/usr/bin/env python3
"""
hop_support_sanity_v2.py

Enhanced sanity + exploratory statistics for hop_support.jsonl.

NEW in v2:
- Rule candidate detection (symmetric, inverse, composition)
- Confidence estimation where possible
- Cross-reference analysis (bidirectional pairs)
- Hub analysis improvements
- Export formats for downstream analysis

What it reports:
1) Record counts by support_status, mode, input_status
2) Coverage and success rates
3) Support distribution diagnostics
4) Rule candidate detection:
   - Symmetric candidates: r1 where r1 appears in its own support
   - Inverse candidates: (r1, r2) pairs where both directions have support
   - Composition candidates: all (r1, r2) with nonzero support
5) Hub detection
6) Anomaly detection
7) Export: edges CSV, candidates JSON

Usage:
  python hop_support_sanity_v2.py --input hop_support.jsonl
  python hop_support_sanity_v2.py --input hop_support.jsonl --write_edges edges.csv --write_candidates candidates.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# ----------------------------
# Data Classes for Analysis
# ----------------------------
@dataclass
class SymmetricCandidate:
    """r1 where (r1, r1) has support - potential symmetric relation."""
    r1: str
    self_support: int  # support for r1 -> r1 chain
    total_support: int  # total support across all r2
    self_share: float  # self_support / total_support
    outdegree_nonzero: int
    mode: str
    input_status: str


@dataclass
class InverseCandidate:
    """(r1, r2) pair where both directions have support."""
    r1: str
    r2: str
    support_r1_r2: int  # support for r1 -> r2 chain
    support_r2_r1: int  # support for r2 -> r1 chain
    symmetry_ratio: float  # min/max of the two supports
    mode_r1: str
    mode_r2: str


@dataclass
class CompositionCandidate:
    """(r1, r2) pair with support - needs target r3 discovery."""
    r1: str
    r2: str
    support: int
    weight_log1p: float
    mode: str
    input_status: str


@dataclass
class R1Summary:
    """Per-r1 statistics."""
    r1: str
    mode: str
    input_status: str
    status: str
    outdegree_total: int  # number of r2 returned
    outdegree_nonzero: int  # number of r2 with support > 0
    total_support: int
    top1_r2: Optional[str]
    top1_support: int
    top1_share: float
    top10_support: int
    top10_share: float
    entropy: float
    self_support: int  # support for r1 -> r1 (if exists)
    self_share: float
    elapsed_sec: float
    support_map: Dict[str, int] = field(default_factory=dict)


# ----------------------------
# Utilities
# ----------------------------
def iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception as e:
                yield {"__parse_error__": True, "__line__": i, "__error__": str(e)}


def entropy_from_counts(counts: List[int]) -> float:
    """Shannon entropy (natural log)."""
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


def summarize_numeric(xs: List[float], name: str = "") -> Dict[str, Any]:
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    if not xs:
        return {"name": name, "n": 0}
    xs_sorted = sorted(xs)

    def pct(p: float) -> float:
        k = (len(xs_sorted) - 1) * p
        f = int(math.floor(k))
        c = int(math.ceil(k))
        if f == c:
            return xs_sorted[f]
        return xs_sorted[f] * (c - k) + xs_sorted[c] * (k - f)

    return {
        "name": name,
        "n": len(xs_sorted),
        "min": xs_sorted[0],
        "p25": pct(0.25),
        "median": pct(0.50),
        "p75": pct(0.75),
        "p90": pct(0.90),
        "p95": pct(0.95),
        "max": xs_sorted[-1],
        "mean": statistics.mean(xs_sorted),
        "stdev": statistics.pstdev(xs_sorted) if len(xs_sorted) > 1 else 0.0,
    }


def extract_support_map(rec: Dict[str, Any]) -> Tuple[Dict[str, int], str]:
    """
    Extract {r2: support} map from record.
    Returns (map, source_tag).
    """
    # support_by_r2: full map from values_chunked mode
    if isinstance(rec.get("support_by_r2"), dict) and rec["support_by_r2"]:
        return {str(k): int(v) for k, v in rec["support_by_r2"].items()}, "support_by_r2"

    # topk_support: list from discover_topk mode
    if isinstance(rec.get("topk_support"), list) and rec["topk_support"]:
        result = {}
        for d in rec["topk_support"]:
            if isinstance(d, dict):
                r2 = d.get("r2")
                supp = d.get("support", 0)
                if r2:
                    result[str(r2)] = int(supp)
        return result, "topk_support"

    # top_support: convenience list
    if isinstance(rec.get("top_support"), list) and rec["top_support"]:
        result = {}
        for d in rec["top_support"]:
            if isinstance(d, dict):
                r2 = d.get("r2")
                supp = d.get("support", 0)
                if r2:
                    result[str(r2)] = int(supp)
        return result, "top_support"

    return {}, "none"


def is_pid(x: Any) -> bool:
    return isinstance(x, str) and x.startswith("P") and x[1:].isdigit()


# ----------------------------
# Main Analysis
# ----------------------------
def analyze_hop_support(
    input_path: str,
    hub_outdeg_threshold: int = 150,
    hub_top1share_threshold: float = 0.80,
    min_support_for_edge: int = 1,
) -> Dict[str, Any]:
    """
    Main analysis function. Returns a comprehensive report dict.
    """
    # Counters
    parse_errors = 0
    total_records = 0
    
    by_status = Counter()
    by_mode = Counter()
    by_input_status = Counter()
    by_mode_status = Counter()
    anomalies = Counter()

    # Per-r1 data
    r1_summaries: Dict[str, R1Summary] = {}
    
    # For cross-reference (inverse detection)
    # support_matrix[r1][r2] = support count
    support_matrix: Dict[str, Dict[str, int]] = defaultdict(dict)

    # Lists for numeric summaries
    outdeg_nonzero_list = []
    outdeg_total_list = []
    total_support_list = []
    top1_support_list = []
    top1_share_list = []
    top10_share_list = []
    entropy_list = []
    self_share_list = []
    elapsed_list = []

    # Process records
    for rec in iter_jsonl(input_path):
        total_records += 1

        if rec.get("__parse_error__"):
            parse_errors += 1
            continue

        r1 = rec.get("r1")
        if not is_pid(r1):
            anomalies["missing_or_bad_r1"] += 1
            continue

        status = str(rec.get("status", "MISSING"))
        mode = str(rec.get("mode", "MISSING"))
        input_status = str(rec.get("input_status", "MISSING"))

        by_status[status] += 1
        by_mode[mode] += 1
        by_input_status[input_status] += 1
        by_mode_status[(mode, status)] += 1

        # Elapsed
        try:
            elapsed = float(rec.get("elapsed_sec", float("nan")))
            if not math.isnan(elapsed):
                elapsed_list.append(elapsed)
        except Exception:
            elapsed = 0.0

        # Extract support map
        support_map, source_tag = extract_support_map(rec)

        if status == "SUCCESS" and not support_map:
            anomalies["success_but_no_support"] += 1
            continue

        if status != "SUCCESS":
            # Still record for completeness
            r1_summaries[r1] = R1Summary(
                r1=r1, mode=mode, input_status=input_status, status=status,
                outdegree_total=0, outdegree_nonzero=0, total_support=0,
                top1_r2=None, top1_support=0, top1_share=0.0,
                top10_support=0, top10_share=0.0, entropy=0.0,
                self_support=0, self_share=0.0, elapsed_sec=elapsed,
                support_map={}
            )
            continue

        # Compute statistics
        supports = [(r2, max(0, s)) for r2, s in support_map.items() if is_pid(r2)]
        supports_sorted = sorted(supports, key=lambda x: -x[1])
        
        support_values = [s for _, s in supports_sorted]
        total_support = sum(support_values)
        outdeg_total = len(support_values)
        outdeg_nonzero = sum(1 for s in support_values if s > 0)

        top1_r2 = supports_sorted[0][0] if supports_sorted else None
        top1_support = supports_sorted[0][1] if supports_sorted else 0
        top10_support = sum(s for _, s in supports_sorted[:10])

        top1_share = (top1_support / total_support) if total_support > 0 else 0.0
        top10_share = (top10_support / total_support) if total_support > 0 else 0.0
        ent = entropy_from_counts(support_values)

        # Self-support (for symmetric detection)
        self_support = support_map.get(r1, 0)
        self_share = (self_support / total_support) if total_support > 0 else 0.0

        # Store in matrix for cross-reference
        for r2, supp in supports:
            if supp > 0:
                support_matrix[r1][r2] = supp

        # Create summary
        r1_summaries[r1] = R1Summary(
            r1=r1, mode=mode, input_status=input_status, status=status,
            outdegree_total=outdeg_total, outdegree_nonzero=outdeg_nonzero,
            total_support=total_support,
            top1_r2=top1_r2, top1_support=top1_support, top1_share=top1_share,
            top10_support=top10_support, top10_share=top10_share,
            entropy=ent, self_support=self_support, self_share=self_share,
            elapsed_sec=elapsed, support_map=dict(support_map)
        )

        # Append to lists
        outdeg_nonzero_list.append(float(outdeg_nonzero))
        outdeg_total_list.append(float(outdeg_total))
        total_support_list.append(float(total_support))
        top1_support_list.append(float(top1_support))
        top1_share_list.append(top1_share)
        top10_share_list.append(top10_share)
        entropy_list.append(ent)
        if self_support > 0:
            self_share_list.append(self_share)

    # ----------------------------
    # Detect Rule Candidates
    # ----------------------------
    
    # 1. Symmetric candidates: r1 where self_support > 0
    symmetric_candidates: List[SymmetricCandidate] = []
    for r1, summ in r1_summaries.items():
        if summ.status == "SUCCESS" and summ.self_support > 0:
            symmetric_candidates.append(SymmetricCandidate(
                r1=r1,
                self_support=summ.self_support,
                total_support=summ.total_support,
                self_share=summ.self_share,
                outdegree_nonzero=summ.outdegree_nonzero,
                mode=summ.mode,
                input_status=summ.input_status,
            ))
    symmetric_candidates.sort(key=lambda x: (-x.self_support, -x.self_share))

    # 2. Inverse candidates: (r1, r2) where both support_matrix[r1][r2] > 0 AND support_matrix[r2][r1] > 0
    inverse_candidates: List[InverseCandidate] = []
    seen_pairs: Set[Tuple[str, str]] = set()
    
    for r1, r2_map in support_matrix.items():
        for r2, supp_r1_r2 in r2_map.items():
            if r1 == r2:
                continue  # Skip self (that's symmetric)
            if (r2, r1) in seen_pairs:
                continue  # Already processed
            
            supp_r2_r1 = support_matrix.get(r2, {}).get(r1, 0)
            if supp_r2_r1 > 0:
                # Bidirectional support exists
                min_supp = min(supp_r1_r2, supp_r2_r1)
                max_supp = max(supp_r1_r2, supp_r2_r1)
                symmetry_ratio = min_supp / max_supp if max_supp > 0 else 0.0
                
                inverse_candidates.append(InverseCandidate(
                    r1=r1,
                    r2=r2,
                    support_r1_r2=supp_r1_r2,
                    support_r2_r1=supp_r2_r1,
                    symmetry_ratio=symmetry_ratio,
                    mode_r1=r1_summaries[r1].mode if r1 in r1_summaries else "UNKNOWN",
                    mode_r2=r1_summaries[r2].mode if r2 in r1_summaries else "UNKNOWN",
                ))
                seen_pairs.add((r1, r2))
    
    inverse_candidates.sort(key=lambda x: (-(x.support_r1_r2 + x.support_r2_r1), -x.symmetry_ratio))

    # 3. Composition candidates: all (r1, r2) edges with support > 0
    composition_candidates: List[CompositionCandidate] = []
    for r1, r2_map in support_matrix.items():
        summ = r1_summaries.get(r1)
        for r2, supp in r2_map.items():
            if r1 == r2:
                continue  # Exclude self-loops for composition
            if supp >= min_support_for_edge:
                composition_candidates.append(CompositionCandidate(
                    r1=r1,
                    r2=r2,
                    support=supp,
                    weight_log1p=math.log1p(supp),
                    mode=summ.mode if summ else "UNKNOWN",
                    input_status=summ.input_status if summ else "UNKNOWN",
                ))
    composition_candidates.sort(key=lambda x: -x.support)

    # 4. Hub candidates
    hub_candidates: List[R1Summary] = []
    for summ in r1_summaries.values():
        if summ.status == "SUCCESS":
            if summ.outdegree_nonzero >= hub_outdeg_threshold or summ.top1_share >= hub_top1share_threshold:
                hub_candidates.append(summ)
    hub_candidates.sort(key=lambda x: (-x.outdegree_nonzero, -x.top1_share))

    # ----------------------------
    # Build Report
    # ----------------------------
    return {
        "input_path": input_path,
        "total_records": total_records,
        "parse_errors": parse_errors,
        "distinct_r1": len(r1_summaries),
        
        "counts": {
            "by_status": dict(by_status),
            "by_mode": dict(by_mode),
            "by_input_status": dict(by_input_status),
            "by_mode_status": {f"{m}|{s}": c for (m, s), c in by_mode_status.items()},
            "anomalies": dict(anomalies),
        },
        
        "distributions": {
            "outdegree_total": summarize_numeric(outdeg_total_list, "outdegree_total"),
            "outdegree_nonzero": summarize_numeric(outdeg_nonzero_list, "outdegree_nonzero"),
            "total_support": summarize_numeric(total_support_list, "total_support"),
            "top1_support": summarize_numeric(top1_support_list, "top1_support"),
            "top1_share": summarize_numeric(top1_share_list, "top1_share"),
            "top10_share": summarize_numeric(top10_share_list, "top10_share"),
            "entropy": summarize_numeric(entropy_list, "entropy"),
            "self_share": summarize_numeric(self_share_list, "self_share (where >0)"),
            "elapsed_sec": summarize_numeric(elapsed_list, "elapsed_sec"),
        },
        
        "rule_candidates": {
            "symmetric": {
                "count": len(symmetric_candidates),
                "top_25": [asdict(c) for c in symmetric_candidates[:25]],
            },
            "inverse": {
                "count": len(inverse_candidates),
                "top_25": [asdict(c) for c in inverse_candidates[:25]],
            },
            "composition": {
                "count": len(composition_candidates),
                "top_25": [asdict(c) for c in composition_candidates[:25]],
            },
        },
        
        "hubs": {
            "count": len(hub_candidates),
            "threshold_outdeg": hub_outdeg_threshold,
            "threshold_top1share": hub_top1share_threshold,
            "top_25": [{
                "r1": h.r1,
                "outdegree_nonzero": h.outdegree_nonzero,
                "total_support": h.total_support,
                "top1_share": h.top1_share,
                "mode": h.mode,
            } for h in hub_candidates[:25]],
        },
        
        # Full data for export
        "_data": {
            "r1_summaries": r1_summaries,
            "symmetric_candidates": symmetric_candidates,
            "inverse_candidates": inverse_candidates,
            "composition_candidates": composition_candidates,
            "hub_candidates": hub_candidates,
            "support_matrix": dict(support_matrix),
        }
    }


def print_report(report: Dict[str, Any]) -> None:
    """Pretty-print the analysis report."""
    print("\n" + "=" * 70)
    print("HOP SUPPORT ANALYSIS REPORT (v2)")
    print("=" * 70)
    
    print(f"\nInput file:      {report['input_path']}")
    print(f"Total records:   {report['total_records']}")
    print(f"Parse errors:    {report['parse_errors']}")
    print(f"Distinct r1:     {report['distinct_r1']}")
    
    print("\n" + "-" * 70)
    print("COUNTS BY STATUS:")
    for k, v in sorted(report["counts"]["by_status"].items(), key=lambda x: -x[1]):
        print(f"  {k:20s} {v:8d}")
    
    print("\nCOUNTS BY MODE:")
    for k, v in sorted(report["counts"]["by_mode"].items(), key=lambda x: -x[1]):
        print(f"  {k:25s} {v:8d}")
    
    if report["counts"]["anomalies"]:
        print("\nANOMALIES:")
        for k, v in report["counts"]["anomalies"].items():
            print(f"  {k:30s} {v:8d}")
    
    print("\n" + "-" * 70)
    print("DISTRIBUTIONS (SUCCESS records only):")
    for name, stats in report["distributions"].items():
        if stats["n"] == 0:
            print(f"  {name:25s}: (no data)")
            continue
        print(f"  {name:25s}: n={stats['n']:5d} "
              f"min={stats['min']:10.2f} p50={stats['median']:10.2f} "
              f"p95={stats['p95']:10.2f} max={stats['max']:12.2f} "
              f"mean={stats['mean']:10.2f}")
    
    print("\n" + "-" * 70)
    print("RULE CANDIDATES:")
    
    # Symmetric
    sym = report["rule_candidates"]["symmetric"]
    print(f"\n  SYMMETRIC CANDIDATES: {sym['count']} relations with self-support > 0")
    print("  (r1 where chain r1 -> r1 has support)")
    if sym["top_25"]:
        print("  Top 10:")
        for c in sym["top_25"][:10]:
            print(f"    {c['r1']:10s} self_support={c['self_support']:8d} "
                  f"self_share={c['self_share']:.3f} total={c['total_support']:10d}")
    
    # Inverse
    inv = report["rule_candidates"]["inverse"]
    print(f"\n  INVERSE CANDIDATES: {inv['count']} bidirectional pairs")
    print("  ((r1,r2) where both r1->r2 and r2->r1 chains have support)")
    if inv["top_25"]:
        print("  Top 10:")
        for c in inv["top_25"][:10]:
            print(f"    ({c['r1']:8s}, {c['r2']:8s}) "
                  f"support_r1_r2={c['support_r1_r2']:8d} "
                  f"support_r2_r1={c['support_r2_r1']:8d} "
                  f"ratio={c['symmetry_ratio']:.3f}")
    
    # Composition
    comp = report["rule_candidates"]["composition"]
    print(f"\n  COMPOSITION CANDIDATES: {comp['count']} (r1,r2) pairs with support > 0")
    print("  (Excludes self-loops; needs target r3 discovery for confidence)")
    if comp["top_25"]:
        print("  Top 10 by support:")
        for c in comp["top_25"][:10]:
            print(f"    ({c['r1']:8s}, {c['r2']:8s}) support={c['support']:10d}")
    
    # Hubs
    print("\n" + "-" * 70)
    hubs = report["hubs"]
    print(f"HUB RELATIONS: {hubs['count']} "
          f"(outdeg >= {hubs['threshold_outdeg']} OR top1_share >= {hubs['threshold_top1share']})")
    if hubs["top_25"]:
        print("  Top 10:")
        for h in hubs["top_25"][:10]:
            print(f"    {h['r1']:10s} outdeg_nz={h['outdegree_nonzero']:4d} "
                  f"total_support={h['total_support']:10d} top1_share={h['top1_share']:.3f}")
    
    print("\n" + "=" * 70)


def write_edges_csv(
    report: Dict[str, Any],
    output_path: str,
    min_support: int = 1,
) -> int:
    """Write edge list CSV for graph analysis."""
    data = report["_data"]
    support_matrix = data["support_matrix"]
    r1_summaries = data["r1_summaries"]
    
    rows = []
    for r1, r2_map in support_matrix.items():
        summ = r1_summaries.get(r1)
        for r2, supp in r2_map.items():
            if supp >= min_support:
                rows.append({
                    "r1": r1,
                    "r2": r2,
                    "support": supp,
                    "weight_log1p": math.log1p(supp),
                    "is_self_loop": r1 == r2,
                    "mode": summ.mode if summ else "",
                    "input_status": summ.input_status if summ else "",
                })
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    
    return len(rows)


def write_candidates_json(report: Dict[str, Any], output_path: str) -> None:
    """Write rule candidates to JSON for downstream processing."""
    data = report["_data"]
    
    output = {
        "symmetric_candidates": [asdict(c) for c in data["symmetric_candidates"]],
        "inverse_candidates": [asdict(c) for c in data["inverse_candidates"]],
        "composition_candidates": [asdict(c) for c in data["composition_candidates"][:10000]],  # Cap for size
        "summary": {
            "symmetric_count": len(data["symmetric_candidates"]),
            "inverse_count": len(data["inverse_candidates"]),
            "composition_count": len(data["composition_candidates"]),
        }
    }
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Hop Support Analysis v2")
    ap.add_argument("--input", required=True, help="Path to hop_support.jsonl")
    ap.add_argument("--write_edges", default="", help="Write edge list CSV")
    ap.add_argument("--write_candidates", default="", help="Write candidates JSON")
    ap.add_argument("--write_report", default="", help="Write full report JSON")
    ap.add_argument("--hub_outdeg_threshold", type=int, default=150)
    ap.add_argument("--hub_top1share_threshold", type=float, default=0.80)
    ap.add_argument("--min_support_for_edge", type=int, default=1)
    ap.add_argument("--quiet", action="store_true", help="Don't print report to stdout")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        raise FileNotFoundError(args.input)

    report = analyze_hop_support(
        input_path=args.input,
        hub_outdeg_threshold=args.hub_outdeg_threshold,
        hub_top1share_threshold=args.hub_top1share_threshold,
        min_support_for_edge=args.min_support_for_edge,
    )

    if not args.quiet:
        print_report(report)

    if args.write_edges:
        n = write_edges_csv(report, args.write_edges, args.min_support_for_edge)
        print(f"\nWrote {n} edges to {args.write_edges}")

    if args.write_candidates:
        write_candidates_json(report, args.write_candidates)
        print(f"Wrote candidates to {args.write_candidates}")

    if args.write_report:
        # Remove internal data for JSON export
        export_report = {k: v for k, v in report.items() if not k.startswith("_")}
        os.makedirs(os.path.dirname(args.write_report) or ".", exist_ok=True)
        with open(args.write_report, "w", encoding="utf-8") as f:
            json.dump(export_report, f, indent=2, ensure_ascii=False)
        print(f"Wrote report to {args.write_report}")


if __name__ == "__main__":
    main()
