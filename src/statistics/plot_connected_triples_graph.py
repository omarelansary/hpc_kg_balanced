#!/usr/bin/env python3
"""Build an interactive HTML graph from connected triples JSONL.

Input format (one JSON object per line), default fields:
- head: "h"
- relation: "r"
- tail: "t"

Output:
- Interactive Plotly HTML graph with:
  - relation-colored edges (top-K relations, rest grouped as OTHER),
  - node hover details (in/out/total degree),
  - edge hover details via midpoint markers.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import networkx as nx
import plotly.graph_objects as go


def _safe_int(v: object, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _load_triples(
    path: str,
    *,
    field_head: str,
    field_rel: str,
    field_tail: str,
) -> List[Tuple[str, str, str]]:
    triples: List[Tuple[str, str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            h = rec.get(field_head)
            r = rec.get(field_rel)
            t = rec.get(field_tail)
            if h is None or r is None or t is None:
                continue
            triples.append((str(h), str(r), str(t)))
    return triples


def _aggregate_triples(
    triples: Iterable[Tuple[str, str, str]],
) -> Dict[Tuple[str, str, str], int]:
    counts: Dict[Tuple[str, str, str], int] = defaultdict(int)
    for h, r, t in triples:
        counts[(h, r, t)] += 1
    return dict(counts)


def _node_scores(edge_counts: Dict[Tuple[str, str, str], int]) -> Dict[str, int]:
    score: Dict[str, int] = defaultdict(int)
    for (h, _r, t), c in edge_counts.items():
        score[h] += int(c)
        score[t] += int(c)
    return dict(score)


def _filter_by_nodes(
    edge_counts: Dict[Tuple[str, str, str], int],
    *,
    max_nodes: int,
) -> Dict[Tuple[str, str, str], int]:
    if max_nodes <= 0:
        return edge_counts
    scores = _node_scores(edge_counts)
    if len(scores) <= max_nodes:
        return edge_counts
    keep = {n for n, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_nodes]}
    out: Dict[Tuple[str, str, str], int] = {}
    for (h, r, t), c in edge_counts.items():
        if h in keep and t in keep:
            out[(h, r, t)] = c
    return out


def _filter_by_edges(
    edge_counts: Dict[Tuple[str, str, str], int],
    *,
    max_edges: int,
    sample_edges: bool,
    random_seed: int,
) -> Dict[Tuple[str, str, str], int]:
    if max_edges <= 0 or len(edge_counts) <= max_edges:
        return edge_counts
    items = list(edge_counts.items())
    if sample_edges:
        rng = random.Random(random_seed)
        picked = rng.sample(items, max_edges)
        return dict(picked)
    # deterministic: keep highest multiplicity edges first
    items.sort(key=lambda kv: kv[1], reverse=True)
    return dict(items[:max_edges])


def _build_layout_graph(edge_counts: Dict[Tuple[str, str, str], int]) -> nx.Graph:
    g = nx.Graph()
    pair_weight: Dict[Tuple[str, str], int] = defaultdict(int)
    for (h, _r, t), c in edge_counts.items():
        if h == t:
            pair_weight[(h, t)] += int(c)
            continue
        a, b = (h, t) if h < t else (t, h)
        pair_weight[(a, b)] += int(c)
    for (a, b), w in pair_weight.items():
        g.add_edge(a, b, weight=float(w))
    return g


def _relation_palette() -> List[str]:
    return [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
        "#3366CC",
        "#DC3912",
        "#FF9900",
        "#109618",
        "#990099",
        "#0099C6",
        "#DD4477",
        "#66AA00",
        "#B82E2E",
        "#316395",
    ]


def _build_figure(
    edge_counts: Dict[Tuple[str, str, str], int],
    *,
    top_relations_colored: int,
    layout_seed: int,
    layout_k: float,
    layout_iterations: int,
) -> go.Figure:
    if not edge_counts:
        raise RuntimeError("No edges remain after filtering.")

    # Directed degree stats for hover text.
    in_deg: Counter[str] = Counter()
    out_deg: Counter[str] = Counter()
    total_deg: Counter[str] = Counter()
    rel_counts: Counter[str] = Counter()
    for (h, r, t), c in edge_counts.items():
        out_deg[h] += c
        in_deg[t] += c
        total_deg[h] += c
        total_deg[t] += c
        rel_counts[r] += c

    g_layout = _build_layout_graph(edge_counts)
    if g_layout.number_of_nodes() == 0:
        raise RuntimeError("Graph has no nodes after filtering.")

    pos = nx.spring_layout(
        g_layout,
        seed=int(layout_seed),
        k=float(layout_k) if layout_k > 0 else None,
        iterations=max(1, int(layout_iterations)),
        weight="weight",
    )

    top_rel = [r for r, _ in rel_counts.most_common(max(0, top_relations_colored))]
    top_rel_set = set(top_rel)
    rel_color: Dict[str, str] = {}
    palette = _relation_palette()
    for i, r in enumerate(top_rel):
        rel_color[r] = palette[i % len(palette)]
    other_rel_name = "OTHER"

    grouped_edges: Dict[str, List[Tuple[str, str, str, int]]] = defaultdict(list)
    for (h, r, t), c in edge_counts.items():
        key = r if r in top_rel_set else other_rel_name
        grouped_edges[key].append((h, r, t, c))

    traces: List[go.Scatter] = []

    # Edge line traces by relation group.
    for rel_key, edges in sorted(grouped_edges.items(), key=lambda kv: len(kv[1]), reverse=True):
        color = rel_color.get(rel_key, "#bbbbbb")
        xs: List[float] = []
        ys: List[float] = []
        mid_x: List[float] = []
        mid_y: List[float] = []
        mid_text: List[str] = []
        for h, r, t, c in edges:
            x0, y0 = pos[h]
            x1, y1 = pos[t]
            xs.extend([x0, x1, None])
            ys.extend([y0, y1, None])
            mid_x.append((x0 + x1) / 2.0)
            mid_y.append((y0 + y1) / 2.0)
            mid_text.append(f"{h} -[{r}]-> {t}<br>count={c}")

        traces.append(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line=dict(width=1.0 if rel_key != other_rel_name else 0.7, color=color),
                hoverinfo="skip",
                name=f"edge:{rel_key}",
                legendgroup=f"edge:{rel_key}",
            )
        )
        # Midpoint markers are almost invisible but enable edge-level hover details.
        traces.append(
            go.Scatter(
                x=mid_x,
                y=mid_y,
                mode="markers",
                marker=dict(size=5, color=color, opacity=0.05),
                text=mid_text,
                hoverinfo="text",
                name=f"edge-hover:{rel_key}",
                showlegend=False,
                legendgroup=f"edge:{rel_key}",
            )
        )

    # Node trace.
    node_x: List[float] = []
    node_y: List[float] = []
    node_text: List[str] = []
    node_size: List[float] = []
    node_color: List[float] = []

    for n in g_layout.nodes():
        x, y = pos[n]
        d_total = int(total_deg.get(n, 0))
        d_in = int(in_deg.get(n, 0))
        d_out = int(out_deg.get(n, 0))
        node_x.append(x)
        node_y.append(y)
        node_text.append(f"{n}<br>degree_total={d_total}<br>in={d_in}<br>out={d_out}")
        node_size.append(max(7.0, min(35.0, 7.0 + 2.2 * math.log1p(d_total))))
        node_color.append(float(d_total))

    traces.append(
        go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers",
            name="nodes",
            marker=dict(
                size=node_size,
                color=node_color,
                colorscale="YlOrRd",
                showscale=True,
                colorbar=dict(title="Node degree"),
                line=dict(width=0.5, color="#222222"),
            ),
            text=node_text,
            hoverinfo="text",
        )
    )

    total_triplets = int(sum(edge_counts.values()))
    title = (
        f"Connected Triples Graph | nodes={g_layout.number_of_nodes()} | "
        f"unique_edges={len(edge_counts)} | triples={total_triplets}"
    )
    fig = go.Figure(
        data=traces,
        layout=go.Layout(
            title=title,
            showlegend=True,
            hovermode="closest",
            margin=dict(b=20, l=20, r=20, t=55),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor="white",
        ),
    )
    return fig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triples_jsonl", required=True)
    ap.add_argument("--out_html", default="data/connectedgraph/connected_triples_graph.html")
    ap.add_argument("--field_head", default="h")
    ap.add_argument("--field_rel", default="r")
    ap.add_argument("--field_tail", default="t")
    ap.add_argument("--max_nodes", type=int, default=1200, help="0 keeps all nodes.")
    ap.add_argument("--max_edges", type=int, default=3000, help="0 keeps all unique (h,r,t) edges.")
    ap.add_argument(
        "--sample_edges",
        action="store_true",
        help="When max_edges is active, sample edges randomly instead of keeping highest multiplicity first.",
    )
    ap.add_argument("--top_relations_colored", type=int, default=20, help="Top-K relations with distinct colors.")
    ap.add_argument("--layout_seed", type=int, default=42)
    ap.add_argument("--layout_k", type=float, default=0.0, help="Spring layout k. 0 uses networkx default.")
    ap.add_argument("--layout_iterations", type=int, default=150)
    args = ap.parse_args()

    triples = _load_triples(
        args.triples_jsonl,
        field_head=str(args.field_head),
        field_rel=str(args.field_rel),
        field_tail=str(args.field_tail),
    )
    if not triples:
        raise RuntimeError("No triples loaded from input JSONL.")

    edge_counts = _aggregate_triples(triples)
    edge_counts = _filter_by_nodes(edge_counts, max_nodes=_safe_int(args.max_nodes, 0))
    edge_counts = _filter_by_edges(
        edge_counts,
        max_edges=_safe_int(args.max_edges, 0),
        sample_edges=bool(args.sample_edges),
        random_seed=_safe_int(args.layout_seed, 42),
    )

    fig = _build_figure(
        edge_counts=edge_counts,
        top_relations_colored=max(0, _safe_int(args.top_relations_colored, 20)),
        layout_seed=_safe_int(args.layout_seed, 42),
        layout_k=float(args.layout_k),
        layout_iterations=max(1, _safe_int(args.layout_iterations, 150)),
    )

    out_path = Path(args.out_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out_path), include_plotlyjs="cdn")

    nodes = set()
    rel_counter: Counter[str] = Counter()
    for (h, r, t), c in edge_counts.items():
        nodes.add(h)
        nodes.add(t)
        rel_counter[r] += c

    print(
        json.dumps(
            {
                "triples_input_rows": len(triples),
                "triples_unique_edges_used": len(edge_counts),
                "nodes_used": len(nodes),
                "relations_used": len(rel_counter),
                "top_relations": rel_counter.most_common(10),
                "out_html": str(out_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
