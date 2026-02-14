# stats_enriched_pairs.py
#
# Reads the output JSONL from enrich_pairs_with_targets.py and prints
# full statistics on target_count and support.
#
# Usage:
#   python stats_enriched_pairs.py --input pairs_with_compatible_targets.jsonl
#   python stats_enriched_pairs.py --input output.jsonl --out_file stats_report.json

import argparse
import json
import math
import sys
from collections import Counter
from typing import Any, Dict, List


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def compute_stats(values: List[float]) -> Dict[str, Any]:
    """Compute min, max, mean, median, std, quartiles, and percentiles (step 10)."""
    if not values:
        return {"count": 0}

    s = sorted(values)
    n = len(s)
    total = sum(s)
    mean = total / n
    variance = sum((x - mean) ** 2 for x in s) / n
    std = math.sqrt(variance)

    def percentile(pct: float) -> float:
        """Linear interpolation percentile."""
        if n == 1:
            return s[0]
        k = (pct / 100.0) * (n - 1)
        f = int(k)
        c = f + 1 if f + 1 < n else f
        d = k - f
        return s[f] + d * (s[c] - s[f])

    # Percentiles every 10%
    percentiles = {}
    for p in range(0, 101, 10):
        percentiles[f"p{p}"] = round(percentile(p), 2)

    # Quartiles
    quartiles = {
        "q1": round(percentile(25), 2),
        "q2_median": round(percentile(50), 2),
        "q3": round(percentile(75), 2),
        "iqr": round(percentile(75) - percentile(25), 2),
    }

    return {
        "count": n,
        "min": s[0],
        "max": s[-1],
        "mean": round(mean, 2),
        "median": round(percentile(50), 2),
        "std": round(std, 2),
        "sum": round(total, 2),
        "quartiles": quartiles,
        "percentiles": percentiles,
    }


def main():
    parser = argparse.ArgumentParser(description="Statistics for enriched pairs JSONL output.")
    parser.add_argument("--input", required=True, help="Input JSONL file (output of enrich_pairs_with_targets.py).")
    parser.add_argument("--out_file", default=None, help="Optional: save full report as JSON file.")
    args = parser.parse_args()

    print(f"Loading {args.input}...")
    records = load_jsonl(args.input)
    print(f"Total rows: {len(records)}\n")

    if not records:
        print("No records found.")
        return

    # Extract numeric fields
    target_counts = [r["target_count"] for r in records if "target_count" in r]
    supports = [r["support"] for r in records if "support" in r]

    # Categorical breakdowns
    mode_counts = Counter(r.get("source_mode") for r in records)
    status_counts = Counter(r.get("input_status") for r in records)
    truncated_count = sum(1 for r in records if r.get("targets_truncated"))

    # Unique r1, r2
    unique_r1 = len(set(r.get("r1") for r in records))
    unique_r2 = len(set(r.get("r2") for r in records))
    unique_pairs = len(set((r.get("r1"), r.get("r2")) for r in records))

    # How many pairs matched zero targets
    zero_targets = sum(1 for tc in target_counts if tc == 0)
    max_targets = max(target_counts) if target_counts else 0
    max_target_pairs = sum(1 for tc in target_counts if tc == max_targets)

    # Build report
    report: Dict[str, Any] = {
        "total_rows": len(records),
        "unique_r1": unique_r1,
        "unique_r2": unique_r2,
        "unique_pairs": unique_pairs,
        "source_mode_distribution": dict(mode_counts),
        "input_status_distribution": dict(status_counts),
        "targets_truncated_count": truncated_count,
        "target_count_stats": compute_stats(target_counts),
        "target_count_zero": zero_targets,
        "target_count_at_max": {"max_value": max_targets, "num_pairs": max_target_pairs},
        "support_stats": compute_stats(supports),
    }

    # --- Print to stdout ---
    def print_section(title: str, stats: Dict[str, Any]):
        print(f"{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")
        print(f"  Count:   {stats['count']}")
        print(f"  Min:     {stats['min']}")
        print(f"  Max:     {stats['max']}")
        print(f"  Mean:    {stats['mean']}")
        print(f"  Median:  {stats['median']}")
        print(f"  Std:     {stats['std']}")
        print()
        q = stats["quartiles"]
        print(f"  Quartiles:")
        print(f"    Q1 (25%):   {q['q1']}")
        print(f"    Q2 (50%):   {q['q2_median']}")
        print(f"    Q3 (75%):   {q['q3']}")
        print(f"    IQR:        {q['iqr']}")
        print()
        p = stats["percentiles"]
        print(f"  Percentiles (every 10%):")
        for key in sorted(p.keys(), key=lambda x: int(x[1:])):
            pct = int(key[1:])
            bar = "█" * int(p[key] / (stats["max"] or 1) * 40)
            print(f"    {pct:>3}%:  {p[key]:>10.2f}  {bar}")
        print()

    print(f"\n{'#' * 60}")
    print(f"  ENRICHED PAIRS STATISTICS")
    print(f"{'#' * 60}\n")

    print(f"  Total rows:       {len(records)}")
    print(f"  Unique r1:        {unique_r1}")
    print(f"  Unique r2:        {unique_r2}")
    print(f"  Unique (r1,r2):   {unique_pairs}")
    print(f"  Truncated:        {truncated_count}")
    print()

    print(f"  Source mode distribution:")
    for mode, cnt in mode_counts.most_common():
        print(f"    {mode or 'N/A':25s}  {cnt:>8d}  ({100*cnt/len(records):.1f}%)")
    print()

    print(f"  Input status distribution:")
    for status, cnt in status_counts.most_common():
        print(f"    {status or 'N/A':25s}  {cnt:>8d}  ({100*cnt/len(records):.1f}%)")
    print()

    print(f"  Pairs with target_count = 0:    {zero_targets}  ({100*zero_targets/len(records):.1f}%)")
    print(f"  Pairs at max target_count ({max_targets}): {max_target_pairs}")
    print()

    if target_counts:
        print_section("TARGET COUNT", compute_stats(target_counts))

    if supports:
        print_section("SUPPORT", compute_stats(supports))

    # --- Save JSON report ---
    if args.out_file:
        with open(args.out_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Full report saved to {args.out_file}")


if __name__ == "__main__":
    main()
    #python stats_enriched_pairs.py --input pairs_with_compatible_targets_dom_rng_v1.jsonl --out_file stats.json