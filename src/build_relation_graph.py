#!/usr/bin/env python3
"""
build_relation_graph.py

Build a relation-level hop graph from hop_support.jsonl and print feasibility stats.

Nodes: relation PIDs (r1 and r2)
Directed edges: r1 -> r2 if support >= min_support
Weights: optional log1p(support)

Outputs:
- edges CSV (optional)
- relations list (optional)
- prints connectivity stats (weakly connected components) dependency-free.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict, Counter, deque
from typing import Any, Dict, Iterable, List, Tuple, Set


def iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def extract_pairs(rec: Dict[str, Any]) -> List[Tuple[str, int]]:
    # Prefer full map if present
    if isinstance(rec.get("support_by_r2"), dict) and rec["support_by_r2"]:
        out = []
        for r2, s in rec["support_by_r2"].items():
            try:
                out.append((str(r2), int(s)))
            except Exception:
                continue
        return out

    # Else fallback list
    if isinstance(rec.get("topk_support"), list) and rec["topk_support"]:
        out = []
        for d in rec["topk_support"]:
            if not isinstance(d, dict):
                continue
            r2 = d.get("r2")
            s = d.get("support")
            try:
                out.append((str(r2), int(s)))
            except Exception:
                continue
        return out

    # Else top_support convenience
    if isinstance(rec.get("top_support"), list) and rec["top_support"]:
        out = []
        for d in rec["top_support"]:
            if not isinstance(d, dict):
                continue
            r2 = d.get("r2")
            s = d.get("support")
            try:
                out.append((str(r2), int(s)))
            except Exception:
                continue
        return out

    return []


def log1p_weight(support: int) -> float:
    return math.log1p(max(0, support))


def build_graph(
    hop_support_path: str,
    min_support: int,
    keep_status: Set[str],
) -> Tuple[Set[str], List[Tuple[str, str, int, float]], Dict[str, Set[str]], Dict[str, Set[str]]]:
    """
    Returns:
      nodes,
      edges list: (r1, r2, support, weight),
      out_adj (directed),
      undirected adjacency (for weak connectivity)
    """
    nodes: Set[str] = set()
    edges: List[Tuple[str, str, int, float]] = []
    out_adj: Dict[str, Set[str]] = defaultdict(set)
    undirected: Dict[str, Set[str]] = defaultdict(set)

    skipped_empty = 0
    skipped_status = 0

    for rec in iter_jsonl(hop_support_path):
        status = str(rec.get("status", ""))
        if status not in keep_status:
            skipped_status += 1
            continue

        r1 = rec.get("r1")
        if not isinstance(r1, str) or not r1.startswith("P"):
            continue

        pairs = extract_pairs(rec)
        if not pairs:
            skipped_empty += 1
            continue

        for r2, supp in pairs:
            if not isinstance(r2, str) or not r2.startswith("P"):
                continue
            if supp < min_support:
                continue
            nodes.add(r1)
            nodes.add(r2)

            w = log1p_weight(supp)
            edges.append((r1, r2, supp, w))
            out_adj[r1].add(r2)

            # undirected for weak connectivity analysis
            undirected[r1].add(r2)
            undirected[r2].add(r1)

    return nodes, edges, out_adj, undirected


def weakly_connected_components(nodes: Set[str], undirected: Dict[str, Set[str]]) -> List[Set[str]]:
    seen: Set[str] = set()
    comps: List[Set[str]] = []

    for n in nodes:
        if n in seen:
            continue
        q = deque([n])
        seen.add(n)
        comp = {n}
        while q:
            u = q.popleft()
            for v in undirected.get(u, set()):
                if v not in seen:
                    seen.add(v)
                    comp.add(v)
                    q.append(v)
        comps.append(comp)

    comps.sort(key=len, reverse=True)
    return comps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="hop_support.jsonl")
    ap.add_argument("--min_support", type=int, default=2, help="keep edge if support >= min_support")
    ap.add_argument("--include_partial", action="store_true", help="include PARTIAL_SUCCESS records")
    ap.add_argument("--edges_csv", default="", help="optional output edges CSV")
    ap.add_argument("--relations_txt", default="", help="optional output relations list")
    args = ap.parse_args()

    keep_status = {"SUCCESS"}
    if args.include_partial:
        keep_status.add("PARTIAL_SUCCESS")

    nodes, edges, out_adj, undirected = build_graph(
        hop_support_path=args.input,
        min_support=args.min_support,
        keep_status=keep_status,
    )

    # Degree stats
    out_degs = [len(out_adj.get(n, set())) for n in nodes]
    out_degs_sorted = sorted(out_degs)
    def pct(p: float) -> float:
        if not out_degs_sorted:
            return 0.0
        k = (len(out_degs_sorted) - 1) * p
        f = int(math.floor(k))
        c = int(math.ceil(k))
        if f == c:
            return float(out_degs_sorted[f])
        return out_degs_sorted[f] * (c - (k - f)) + out_degs_sorted[c] * (k - f)

    comps = weakly_connected_components(nodes, undirected)

    print("\n================ Relation Graph Feasibility ================")
    print(f"Input                : {args.input}")
    print(f"Statuses included     : {sorted(keep_status)}")
    print(f"Min support           : {args.min_support}")
    print("------------------------------------------------------------")
    print(f"|V| (relations)       : {len(nodes)}")
    print(f"|E| (hop edges)       : {len(edges)}")
    print("------------------------------------------------------------")
    if comps:
        lcc = comps[0]
        print(f"Weak CC count         : {len(comps)}")
        print(f"LCC size              : {len(lcc)} ({(len(lcc)/len(nodes)*100):.2f}% of nodes)")
        if len(comps) > 1:
            print(f"2nd CC size           : {len(comps[1])}")
    else:
        print("No components (graph empty after filtering).")
    print("------------------------------------------------------------")
    if out_degs_sorted:
        print("Out-degree (directed) summary:")
        print(f"  min={out_degs_sorted[0]} p25={pct(0.25):.1f} med={pct(0.50):.1f} p75={pct(0.75):.1f} p90={pct(0.90):.1f} max={out_degs_sorted[-1]}")
    print("============================================================\n")

    if args.edges_csv:
        os.makedirs(os.path.dirname(args.edges_csv) or ".", exist_ok=True)
        with open(args.edges_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["r1", "r2", "support", "weight_log1p"])
            for r1, r2, supp, wt in edges:
                w.writerow([r1, r2, supp, f"{wt:.6f}"])
        print(f"Wrote edges CSV: {args.edges_csv}")

    if args.relations_txt:
        os.makedirs(os.path.dirname(args.relations_txt) or ".", exist_ok=True)
        with open(args.relations_txt, "w", encoding="utf-8") as f:
            for r in sorted(nodes):
                f.write(r + "\n")
        print(f"Wrote relations list: {args.relations_txt}")


if __name__ == "__main__":
    main()
# python src/build_relation_graph.py \
#   --input data/processed/hop_support.jsonl \
#   --min_support 2 \
#   --include_partial \
#   --edges_csv data/processed/relation_graph_edges.csv \
#   --relations_txt data/processed/relation_graph_relations.txt
