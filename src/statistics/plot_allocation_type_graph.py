#!/usr/bin/env python3
"""Visualize allocation relations against ontology subject/object classes.

This script builds a graph from:
1) allocation JSON produced by bidirectional allocation, and
2) Wikidata ontology properties JSON containing valid subject/object classes.

Graph model:
- Relation nodes: P-ids present in allocation rows.
- Class nodes: Q-ids from valid subject/object class lists.
- Typed edges: relation -> class with role in {"subject", "object"}.
- Optional relation-compatibility edges:
  r1 -- r2 if object classes(r1) intersects subject classes(r2).

Output:
- Interactive HTML (Plotly) for quick inspection.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

import networkx as nx
import plotly.graph_objects as go


def _load_alloc_relations(path: str, min_eta_integer: int, top_relations: int) -> Dict[str, int]:
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    rows = doc.get("allocations", []) if isinstance(doc, dict) else []
    rel_eta: Dict[str, int] = defaultdict(int)
    for row in rows:
        if not isinstance(row, dict):
            continue
        rel = str(row.get("relation", "")).strip()
        if not rel:
            continue
        try:
            eta_i = int(row.get("eta_integer", 0))
        except (TypeError, ValueError):
            eta_i = 0
        if eta_i < min_eta_integer:
            continue
        rel_eta[rel] += eta_i
    ranked = sorted(rel_eta.items(), key=lambda x: x[1], reverse=True)
    if top_relations > 0:
        ranked = ranked[:top_relations]
    return dict(ranked)


def _load_properties(path: str) -> Dict[str, Dict[str, List[str]]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out: Dict[str, Dict[str, List[str]]] = {}
    if not isinstance(data, list):
        return out
    for rec in data:
        if not isinstance(rec, dict):
            continue
        pid = str(rec.get("property_id", "")).strip()
        if not pid:
            continue
        subj = rec.get("valid_subject_type_ids", [])
        obj = rec.get("valid_object_type_ids", [])
        out[pid] = {
            "subject": [str(x) for x in subj] if isinstance(subj, list) else [],
            "object": [str(x) for x in obj] if isinstance(obj, list) else [],
            "label": str(rec.get("label", "")).strip(),
        }
    return out


def _build_graph(
    rel_eta: Dict[str, int],
    props: Dict[str, Dict[str, List[str]]],
    add_relation_compat_edges: bool,
    max_compat_edges: int,
) -> nx.Graph:
    g = nx.Graph()
    rel_subject: Dict[str, Set[str]] = {}
    rel_object: Dict[str, Set[str]] = {}

    for rel, eta_i in rel_eta.items():
        rec = props.get(rel, {})
        label = rec.get("label", "")
        subj = set(rec.get("subject", []) or [])
        obj = set(rec.get("object", []) or [])
        rel_subject[rel] = subj
        rel_object[rel] = obj
        g.add_node(rel, kind="relation", eta_integer=int(eta_i), label=label)
        for c in subj:
            g.add_node(c, kind="class")
            g.add_edge(rel, c, edge_kind="subject")
        for c in obj:
            g.add_node(c, kind="class")
            g.add_edge(rel, c, edge_kind="object")

    if add_relation_compat_edges:
        rels = list(rel_eta.keys())
        compat: List[Tuple[str, str, int]] = []
        for i, r1 in enumerate(rels):
            o1 = rel_object.get(r1, set())
            if not o1:
                continue
            for r2 in rels[i + 1 :]:
                s2 = rel_subject.get(r2, set())
                if not s2:
                    continue
                inter = o1.intersection(s2)
                if inter:
                    compat.append((r1, r2, len(inter)))
        compat.sort(key=lambda x: x[2], reverse=True)
        if max_compat_edges > 0:
            compat = compat[:max_compat_edges]
        for r1, r2, w in compat:
            if not g.has_edge(r1, r2):
                g.add_edge(r1, r2, edge_kind="compat", weight=w)
    return g


def _edge_traces(g: nx.Graph, pos: Dict[str, Tuple[float, float]]) -> List[go.Scatter]:
    by_kind: Dict[str, List[Tuple[float, float, float, float]]] = defaultdict(list)
    for u, v, data in g.edges(data=True):
        ek = str(data.get("edge_kind", "other"))
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        by_kind[ek].append((x0, y0, x1, y1))

    traces: List[go.Scatter] = []
    style = {
        "subject": ("#1f77b4", 1.0),
        "object": ("#2ca02c", 1.0),
        "compat": ("#ff7f0e", 1.6),
        "other": ("#999999", 1.0),
    }
    for kind, segs in by_kind.items():
        color, width = style.get(kind, style["other"])
        xs: List[float] = []
        ys: List[float] = []
        for x0, y0, x1, y1 in segs:
            xs.extend([x0, x1, None])
            ys.extend([y0, y1, None])
        traces.append(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line=dict(width=width, color=color),
                hoverinfo="skip",
                name=f"edge:{kind}",
            )
        )
    return traces


def _node_traces(g: nx.Graph, pos: Dict[str, Tuple[float, float]]) -> List[go.Scatter]:
    rel_x: List[float] = []
    rel_y: List[float] = []
    rel_text: List[str] = []
    rel_size: List[float] = []

    cls_x: List[float] = []
    cls_y: List[float] = []
    cls_text: List[str] = []

    for n, data in g.nodes(data=True):
        x, y = pos[n]
        kind = str(data.get("kind", "class"))
        if kind == "relation":
            eta_i = int(data.get("eta_integer", 0))
            label = str(data.get("label", "")).strip()
            rel_x.append(x)
            rel_y.append(y)
            rel_text.append(f"{n} | eta={eta_i}" + (f" | {label}" if label else ""))
            rel_size.append(max(9.0, min(30.0, 8.0 + eta_i ** 0.5)))
        else:
            cls_x.append(x)
            cls_y.append(y)
            cls_text.append(str(n))

    rel_trace = go.Scatter(
        x=rel_x,
        y=rel_y,
        mode="markers",
        name="relations",
        marker=dict(size=rel_size, color="#d62728", line=dict(width=0.5, color="#222")),
        text=rel_text,
        hoverinfo="text",
    )
    cls_trace = go.Scatter(
        x=cls_x,
        y=cls_y,
        mode="markers",
        name="classes",
        marker=dict(size=6, color="#7f7f7f", opacity=0.7),
        text=cls_text,
        hoverinfo="text",
    )
    return [rel_trace, cls_trace]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allocation_json", required=True)
    ap.add_argument("--properties_json", required=True)
    ap.add_argument("--out_html", default="data/connectedgraph/allocation_type_graph.html")
    ap.add_argument("--min_eta_integer", type=int, default=1)
    ap.add_argument("--top_relations", type=int, default=200, help="0 keeps all relations.")
    ap.add_argument("--add_relation_compat_edges", action="store_true")
    ap.add_argument("--max_compat_edges", type=int, default=500, help="Used only when compat edges are enabled.")
    ap.add_argument("--layout_seed", type=int, default=42)
    args = ap.parse_args()

    rel_eta = _load_alloc_relations(args.allocation_json, args.min_eta_integer, args.top_relations)
    props = _load_properties(args.properties_json)
    g = _build_graph(
        rel_eta=rel_eta,
        props=props,
        add_relation_compat_edges=bool(args.add_relation_compat_edges),
        max_compat_edges=max(0, args.max_compat_edges),
    )
    if g.number_of_nodes() == 0:
        raise RuntimeError("Graph is empty. Check min_eta_integer/top_relations filters.")

    pos = nx.spring_layout(g, seed=int(args.layout_seed), k=None)
    traces = []
    traces.extend(_edge_traces(g, pos))
    traces.extend(_node_traces(g, pos))

    title = (
        f"Allocation Type Graph | relations={sum(1 for _,d in g.nodes(data=True) if d.get('kind')=='relation')}"
        f" | classes={sum(1 for _,d in g.nodes(data=True) if d.get('kind')=='class')}"
        f" | edges={g.number_of_edges()}"
    )
    fig = go.Figure(
        data=traces,
        layout=go.Layout(
            title=title,
            showlegend=True,
            hovermode="closest",
            margin=dict(b=20, l=20, r=20, t=50),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor="white",
        ),
    )
    out_path = Path(args.out_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out_path), include_plotlyjs="cdn")

    print(
        json.dumps(
            {
                "out_html": str(out_path),
                "nodes": g.number_of_nodes(),
                "edges": g.number_of_edges(),
                "relations": sum(1 for _, d in g.nodes(data=True) if d.get("kind") == "relation"),
                "classes": sum(1 for _, d in g.nodes(data=True) if d.get("kind") == "class"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

