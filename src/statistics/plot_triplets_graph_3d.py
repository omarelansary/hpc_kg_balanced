#!/usr/bin/env python3
"""Build an interactive 2D/3D HTML graph from triplets JSON or JSONL."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import networkx as nx
import plotly.graph_objects as go

Triple = Tuple[str, str, str]
EdgeCounts = Dict[Triple, int]


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
) -> List[Triple]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")

    if p.suffix.lower() == ".jsonl":
        triples: List[Triple] = []
        with p.open("r", encoding="utf-8") as f:
            for line_no, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL in {p} at line {line_no}: {exc}") from exc
                if not isinstance(rec, dict):
                    continue
                h = rec.get(field_head)
                r = rec.get(field_rel)
                t = rec.get(field_tail)
                if h is None or r is None or t is None:
                    continue
                triples.append((str(h), str(r), str(t)))
        return triples

    if p.suffix.lower() != ".json":
        raise ValueError(f"Unsupported input type: {p}")

    with p.open("r", encoding="utf-8") as f:
        obj = json.load(f)

    rows: List[object]
    if isinstance(obj, list):
        rows = obj
    elif isinstance(obj, dict):
        if isinstance(obj.get("triples"), list):
            rows = obj["triples"]
        elif isinstance(obj.get("triples_out"), list):
            rows = obj["triples_out"]
        else:
            raise ValueError(f"No triplet list found in JSON file: {p}")
    else:
        raise ValueError(f"Unsupported JSON structure in {p}")

    triples: List[Triple] = []
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        h = rec.get(field_head)
        r = rec.get(field_rel)
        t = rec.get(field_tail)
        if h is None or r is None or t is None:
            continue
        triples.append((str(h), str(r), str(t)))
    return triples


def _aggregate_triples(triples: Iterable[Triple]) -> EdgeCounts:
    counts: EdgeCounts = defaultdict(int)
    for h, r, t in triples:
        counts[(h, r, t)] += 1
    return dict(counts)


def _edge_counts_node_set(edge_counts: EdgeCounts) -> Set[str]:
    nodes: Set[str] = set()
    for h, _r, t in edge_counts:
        nodes.add(h)
        nodes.add(t)
    return nodes


def _edge_counts_stats(edge_counts: EdgeCounts) -> Tuple[int, int]:
    return len(_edge_counts_node_set(edge_counts)), len(edge_counts)


def _node_scores(edge_counts: EdgeCounts) -> Dict[str, int]:
    score: Dict[str, int] = defaultdict(int)
    for (h, _r, t), c in edge_counts.items():
        score[h] += int(c)
        score[t] += int(c)
    return dict(score)


def _build_layout_graph(edge_counts: EdgeCounts) -> nx.DiGraph:
    g = nx.DiGraph()
    for (h, _r, t), c in edge_counts.items():
        if g.has_edge(h, t):
            g[h][t]["weight"] += float(c)
        else:
            g.add_edge(h, t, weight=float(c))
    return g


def _filter_to_node_set(edge_counts: EdgeCounts, keep_nodes: Set[str]) -> EdgeCounts:
    out: EdgeCounts = {}
    for triple, count in edge_counts.items():
        h, _r, t = triple
        if h in keep_nodes and t in keep_nodes:
            out[triple] = count
    return out


def _filter_by_nodes(edge_counts: EdgeCounts, *, max_nodes: int) -> EdgeCounts:
    if max_nodes <= 0:
        return edge_counts
    scores = _node_scores(edge_counts)
    if len(scores) <= max_nodes:
        return edge_counts
    keep = {n for n, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_nodes]}
    return _filter_to_node_set(edge_counts, keep)


def _filter_by_edges(
    edge_counts: EdgeCounts,
    *,
    max_edges: int,
    sample_edges: bool,
    random_seed: int,
) -> EdgeCounts:
    if max_edges <= 0 or len(edge_counts) <= max_edges:
        return edge_counts
    items = list(edge_counts.items())
    if sample_edges:
        rng = random.Random(random_seed)
        return dict(rng.sample(items, max_edges))
    items.sort(key=lambda kv: kv[1], reverse=True)
    return dict(items[:max_edges])


def _filter_loaded_triples_by_edge_counts(triples: List[Triple], edge_counts: EdgeCounts) -> List[Triple]:
    keep = set(edge_counts.keys())
    return [triple for triple in triples if triple in keep]


def _filter_by_center_node(edge_counts: EdgeCounts, *, center_node: str, hops: int) -> EdgeCounts:
    g = _build_layout_graph(edge_counts)
    if center_node not in g:
        raise RuntimeError(f"center_node={center_node!r} is not present in the graph after loading.")
    cutoff = max(0, int(hops))
    keep_nodes = set(nx.single_source_shortest_path_length(g.to_undirected(), center_node, cutoff=cutoff).keys())
    filtered = _filter_to_node_set(edge_counts, keep_nodes)
    if not filtered:
        raise RuntimeError(
            f"No edges remain in the {cutoff}-hop neighborhood around center_node={center_node!r}. "
            "Try increasing --hops or choosing another center node."
        )
    return filtered


def _filter_largest_component(edge_counts: EdgeCounts) -> EdgeCounts:
    g = _build_layout_graph(edge_counts)
    if g.number_of_nodes() == 0:
        raise RuntimeError("Cannot compute largest component on an empty graph.")
    components = list(nx.weakly_connected_components(g))
    if not components:
        raise RuntimeError("No weakly connected components found in the graph.")
    keep_nodes = max(components, key=len)
    filtered = _filter_to_node_set(edge_counts, set(keep_nodes))
    if not filtered:
        raise RuntimeError("Largest-component filtering removed all edges.")
    return filtered


def _sorted_weak_components(g: nx.DiGraph) -> List[Set[str]]:
    return sorted((set(comp) for comp in nx.weakly_connected_components(g)), key=len, reverse=True)


def _sorted_strong_components(g: nx.DiGraph) -> List[Set[str]]:
    return sorted((set(comp) for comp in nx.strongly_connected_components(g)), key=len, reverse=True)


def _filter_weak_component_rank(edge_counts: EdgeCounts, *, rank: int) -> EdgeCounts:
    g = _build_layout_graph(edge_counts)
    components = _sorted_weak_components(g)
    if not components:
        raise RuntimeError("No weakly connected components found in the graph.")
    idx = int(rank) - 1
    if idx < 0 or idx >= len(components):
        raise RuntimeError(
            f"Invalid --weak_component_rank={rank}. Available weak components: {len(components)}."
        )
    filtered = _filter_to_node_set(edge_counts, components[idx])
    if not filtered:
        raise RuntimeError(f"Weak-component rank {rank} filtering removed all edges.")
    return filtered


def _compute_connectivity_diagnostics(g: nx.DiGraph, *, top_k: int) -> Dict[str, object]:
    weak_components = _sorted_weak_components(g)
    strong_components = _sorted_strong_components(g)
    weak_sizes = [len(comp) for comp in weak_components]
    strong_sizes = [len(comp) for comp in strong_components]
    graph_nodes = int(g.number_of_nodes())
    largest_weak = int(weak_sizes[0]) if weak_sizes else 0
    largest_fraction = float(largest_weak / graph_nodes) if graph_nodes > 0 else 0.0
    return {
        "graph_nodes": graph_nodes,
        "graph_edges_directed": int(g.number_of_edges()),
        "num_weak_components": int(len(weak_components)),
        "num_strong_components": int(len(strong_components)),
        "largest_weak_component_size": largest_weak,
        "largest_weak_component_fraction": largest_fraction,
        "top_weak_component_sizes": weak_sizes[: max(0, int(top_k))],
        "top_strong_component_sizes": strong_sizes[: max(0, int(top_k))],
    }


def _infer_export_format(path: str, export_format: str) -> str:
    mode = str(export_format).strip().lower()
    if mode and mode != "auto":
        if mode not in {"json", "csv", "txt"}:
            raise RuntimeError(f"Unsupported export format: {export_format}. Use json|csv|txt|auto.")
        return mode
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    if suffix in {".txt", ".tsv"}:
        return "txt"
    raise RuntimeError(
        f"Could not infer export format from path: {path}. Use .json, .csv, .txt or pass --export_triplets_format."
    )


def _write_export_triplets(
    path: str,
    triples: List[Triple],
    *,
    export_format: str,
    field_head: str,
    field_rel: str,
    field_tail: str,
) -> Dict[str, object]:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = _infer_export_format(path, export_format)

    if fmt == "json":
        payload = [{field_head: h, field_rel: r, field_tail: t} for h, r, t in triples]
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    elif fmt == "csv":
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[field_head, field_rel, field_tail])
            writer.writeheader()
            for h, r, t in triples:
                writer.writerow({field_head: h, field_rel: r, field_tail: t})
    else:
        with out_path.open("w", encoding="utf-8") as f:
            for h, r, t in triples:
                f.write(f"{h}\t{r}\t{t}\n")

    return {
        "path": str(out_path.resolve()),
        "format": fmt,
        "rows": len(triples),
    }


def _require_nonempty(edge_counts: EdgeCounts, *, stage: str) -> None:
    if edge_counts:
        return
    raise RuntimeError(
        f"No edges remain after {stage}. Adjust --center_node/--hops/--largest_component/--weak_component_rank/--max_nodes/--max_edges."
    )


def _compute_degree_stats(edge_counts: EdgeCounts) -> Tuple[Counter[str], Counter[str], Counter[str], Counter[str]]:
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
    return in_deg, out_deg, total_deg, rel_counts


def _relation_palette() -> List[str]:
    return [
        "#1746A2",
        "#E14D2A",
        "#007965",
        "#F2A900",
        "#6A4C93",
        "#2B2D42",
        "#4C956C",
        "#C1121F",
        "#3A86FF",
        "#FB5607",
        "#00A6A6",
        "#A44A3F",
        "#7B6D8D",
        "#3D5A80",
        "#118AB2",
        "#5F0F40",
        "#6D597A",
        "#386641",
        "#8D99AE",
        "#8338EC",
    ]


def _relation_style(rel_counts: Counter[str], top_relations_colored: int) -> Tuple[Set[str], Dict[str, str], str]:
    top_rel = [r for r, _ in rel_counts.most_common(max(0, top_relations_colored))]
    top_rel_set = set(top_rel)
    palette = _relation_palette()
    rel_color: Dict[str, str] = {}
    for i, rel in enumerate(top_rel):
        rel_color[rel] = palette[i % len(palette)]
    return top_rel_set, rel_color, "OTHER"


def _group_edges_by_relation(
    edge_counts: EdgeCounts,
    *,
    top_rel_set: Set[str],
    other_rel_name: str,
) -> Dict[str, List[Tuple[str, str, str, int]]]:
    grouped: Dict[str, List[Tuple[str, str, str, int]]] = defaultdict(list)
    for (h, r, t), c in edge_counts.items():
        grouped[r if r in top_rel_set else other_rel_name].append((h, r, t, c))
    return grouped


def _spring_layout(
    g_layout: nx.DiGraph,
    *,
    dim: int,
    layout_seed: int,
    layout_k: float,
    layout_iterations: int,
):
    if g_layout.number_of_nodes() == 0:
        raise RuntimeError("Graph has no nodes after filtering.")
    return nx.spring_layout(
        g_layout,
        seed=int(layout_seed),
        k=float(layout_k) if layout_k > 0 else None,
        iterations=max(1, int(layout_iterations)),
        weight="weight",
        dim=int(dim),
    )


def _top_labeled_nodes(total_deg: Counter[str], *, label_top_nodes: int) -> List[str]:
    return [n for n, _ in total_deg.most_common(max(0, int(label_top_nodes)))]


def _build_2d_arrow_annotations(
    grouped_edges: Dict[str, List[Tuple[str, str, str, int]]],
    pos: Dict[str, Sequence[float]],
    *,
    rel_color: Dict[str, str],
    other_rel_name: str,
) -> List[Dict[str, object]]:
    annotations: List[Dict[str, object]] = []
    for rel_key, edges in grouped_edges.items():
        color = rel_color.get(rel_key, "#B8B8B8")
        width = 1.4 if rel_key != other_rel_name else 0.9
        for h, _r, t, _c in edges:
            x0, y0 = pos[h][0], pos[h][1]
            x1, y1 = pos[t][0], pos[t][1]
            start_x = (0.40 * x0) + (0.60 * x1)
            start_y = (0.40 * y0) + (0.60 * y1)
            end_x = (0.18 * x0) + (0.82 * x1)
            end_y = (0.18 * y0) + (0.82 * y1)
            annotations.append(
                {
                    "xref": "x",
                    "yref": "y",
                    "axref": "x",
                    "ayref": "y",
                    "x": end_x,
                    "y": end_y,
                    "ax": start_x,
                    "ay": start_y,
                    "text": "",
                    "showarrow": True,
                    "arrowhead": 3,
                    "arrowsize": 1.0,
                    "arrowwidth": width,
                    "arrowcolor": color,
                    "opacity": 0.85,
                }
            )
    return annotations


def _build_2d_figure(
    edge_counts: EdgeCounts,
    *,
    top_relations_colored: int,
    layout_seed: int,
    layout_k: float,
    layout_iterations: int,
    label_top_nodes: int,
) -> go.Figure:
    in_deg, out_deg, total_deg, rel_counts = _compute_degree_stats(edge_counts)
    top_rel_set, rel_color, other_rel_name = _relation_style(rel_counts, top_relations_colored)
    grouped_edges = _group_edges_by_relation(edge_counts, top_rel_set=top_rel_set, other_rel_name=other_rel_name)

    g_layout = _build_layout_graph(edge_counts)
    pos = _spring_layout(
        g_layout,
        dim=2,
        layout_seed=layout_seed,
        layout_k=layout_k,
        layout_iterations=layout_iterations,
    )

    traces: List[go.Scatter] = []
    for rel_key, edges in sorted(grouped_edges.items(), key=lambda kv: len(kv[1]), reverse=True):
        color = rel_color.get(rel_key, "#B8B8B8")
        xs: List[float] = []
        ys: List[float] = []
        mid_x: List[float] = []
        mid_y: List[float] = []
        mid_text: List[str] = []
        for h, r, t, c in edges:
            x0, y0 = pos[h][0], pos[h][1]
            x1, y1 = pos[t][0], pos[t][1]
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
                line=dict(width=1.2 if rel_key != other_rel_name else 0.8, color=color),
                hoverinfo="skip",
                name=f"edge:{rel_key}",
                legendgroup=f"edge:{rel_key}",
            )
        )
        traces.append(
            go.Scatter(
                x=mid_x,
                y=mid_y,
                mode="markers",
                marker=dict(size=7, color=color, opacity=0.06),
                text=mid_text,
                hoverinfo="text",
                name=f"edge-hover:{rel_key}",
                showlegend=False,
                legendgroup=f"edge:{rel_key}",
            )
        )

    node_x: List[float] = []
    node_y: List[float] = []
    node_text: List[str] = []
    node_size: List[float] = []
    node_color: List[float] = []
    for node in g_layout.nodes():
        x, y = pos[node][0], pos[node][1]
        d_total = int(total_deg.get(node, 0))
        d_in = int(in_deg.get(node, 0))
        d_out = int(out_deg.get(node, 0))
        node_x.append(x)
        node_y.append(y)
        node_text.append(f"{node}<br>degree_total={d_total}<br>in={d_in}<br>out={d_out}")
        node_size.append(max(6.0, min(28.0, 6.0 + 2.0 * math.log1p(d_total))))
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
                line=dict(width=0.5, color="#111827"),
                opacity=0.94,
            ),
            text=node_text,
            hoverinfo="text",
        )
    )

    label_nodes = _top_labeled_nodes(total_deg, label_top_nodes=label_top_nodes)
    if label_nodes:
        traces.append(
            go.Scatter(
                x=[pos[n][0] for n in label_nodes],
                y=[pos[n][1] for n in label_nodes],
                mode="text",
                text=label_nodes,
                textposition="top center",
                textfont=dict(size=10, color="#1F2937"),
                hoverinfo="skip",
                showlegend=False,
                name="labels",
            )
        )

    total_triplets = int(sum(edge_counts.values()))
    title = (
        f"Triplets Graph (2D) | nodes={g_layout.number_of_nodes()} | "
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
            plot_bgcolor="#F7F4EA",
            paper_bgcolor="#F7F4EA",
            legend=dict(bgcolor="rgba(255,255,255,0.88)", bordercolor="#D6D3D1", borderwidth=1),
            annotations=_build_2d_arrow_annotations(
                grouped_edges,
                pos,
                rel_color=rel_color,
                other_rel_name=other_rel_name,
            ),
        ),
    )
    return fig


def _build_3d_figure(
    edge_counts: EdgeCounts,
    *,
    top_relations_colored: int,
    layout_seed: int,
    layout_k: float,
    layout_iterations: int,
    label_top_nodes: int,
) -> go.Figure:
    in_deg, out_deg, total_deg, rel_counts = _compute_degree_stats(edge_counts)
    top_rel_set, rel_color, other_rel_name = _relation_style(rel_counts, top_relations_colored)
    grouped_edges = _group_edges_by_relation(edge_counts, top_rel_set=top_rel_set, other_rel_name=other_rel_name)

    g_layout = _build_layout_graph(edge_counts)
    pos = _spring_layout(
        g_layout,
        dim=3,
        layout_seed=layout_seed,
        layout_k=layout_k,
        layout_iterations=layout_iterations,
    )

    traces: List[go.Scatter3d] = []
    for rel_key, edges in sorted(grouped_edges.items(), key=lambda kv: len(kv[1]), reverse=True):
        color = rel_color.get(rel_key, "#B8B8B8")
        xs: List[float] = []
        ys: List[float] = []
        zs: List[float] = []
        mid_x: List[float] = []
        mid_y: List[float] = []
        mid_z: List[float] = []
        mid_text: List[str] = []
        dir_x: List[float] = []
        dir_y: List[float] = []
        dir_z: List[float] = []
        dir_text: List[str] = []
        for h, r, t, c in edges:
            x0, y0, z0 = pos[h]
            x1, y1, z1 = pos[t]
            xs.extend([x0, x1, None])
            ys.extend([y0, y1, None])
            zs.extend([z0, z1, None])
            mid_x.append((x0 + x1) / 2.0)
            mid_y.append((y0 + y1) / 2.0)
            mid_z.append((z0 + z1) / 2.0)
            dir_x.append((0.24 * x0) + (0.76 * x1))
            dir_y.append((0.24 * y0) + (0.76 * y1))
            dir_z.append((0.24 * z0) + (0.76 * z1))
            text = f"{h} -[{r}]-> {t}<br>count={c}"
            mid_text.append(text)
            dir_text.append(text + "<br>direction: toward tail")

        traces.append(
            go.Scatter3d(
                x=xs,
                y=ys,
                z=zs,
                mode="lines",
                line=dict(width=2 if rel_key != other_rel_name else 1, color=color),
                hoverinfo="skip",
                name=f"edge:{rel_key}",
                legendgroup=f"edge:{rel_key}",
            )
        )
        traces.append(
            go.Scatter3d(
                x=mid_x,
                y=mid_y,
                z=mid_z,
                mode="markers",
                marker=dict(size=2.5, color=color, opacity=0.08),
                text=mid_text,
                hoverinfo="text",
                name=f"edge-hover:{rel_key}",
                showlegend=False,
                legendgroup=f"edge:{rel_key}",
            )
        )
        traces.append(
            go.Scatter3d(
                x=dir_x,
                y=dir_y,
                z=dir_z,
                mode="markers",
                marker=dict(size=3.5, color=color, symbol="diamond", opacity=0.85),
                text=dir_text,
                hoverinfo="text",
                name=f"dir:{rel_key}",
                showlegend=False,
                legendgroup=f"edge:{rel_key}",
            )
        )

    node_x: List[float] = []
    node_y: List[float] = []
    node_z: List[float] = []
    node_text: List[str] = []
    node_size: List[float] = []
    node_color: List[float] = []
    for node in g_layout.nodes():
        x, y, z = pos[node]
        d_total = int(total_deg.get(node, 0))
        d_in = int(in_deg.get(node, 0))
        d_out = int(out_deg.get(node, 0))
        node_x.append(x)
        node_y.append(y)
        node_z.append(z)
        node_text.append(f"{node}<br>degree_total={d_total}<br>in={d_in}<br>out={d_out}")
        node_size.append(max(4.0, min(20.0, 4.0 + 1.9 * math.log1p(d_total))))
        node_color.append(float(d_total))

    traces.append(
        go.Scatter3d(
            x=node_x,
            y=node_y,
            z=node_z,
            mode="markers",
            name="nodes",
            marker=dict(
                size=node_size,
                color=node_color,
                colorscale="YlOrRd",
                showscale=True,
                colorbar=dict(title="Node degree"),
                line=dict(width=0.4, color="#111827"),
                opacity=0.92,
            ),
            hoverinfo="text",
            hovertext=node_text,
        )
    )

    label_nodes = _top_labeled_nodes(total_deg, label_top_nodes=label_top_nodes)
    if label_nodes:
        traces.append(
            go.Scatter3d(
                x=[pos[n][0] for n in label_nodes],
                y=[pos[n][1] for n in label_nodes],
                z=[pos[n][2] for n in label_nodes],
                mode="text",
                text=label_nodes,
                textposition="top center",
                textfont=dict(size=9, color="#1F2937"),
                hoverinfo="skip",
                showlegend=False,
                name="labels",
            )
        )

    total_triplets = int(sum(edge_counts.values()))
    title = (
        f"Triplets Graph (3D) | nodes={g_layout.number_of_nodes()} | "
        f"unique_edges={len(edge_counts)} | triples={total_triplets}"
    )
    fig = go.Figure(
        data=traces,
        layout=go.Layout(
            title=title,
            showlegend=True,
            hovermode="closest",
            margin=dict(b=10, l=10, r=10, t=50),
            paper_bgcolor="#F7F4EA",
            plot_bgcolor="#F7F4EA",
            scene=dict(
                bgcolor="#F7F4EA",
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
                zaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
                camera=dict(eye=dict(x=1.55, y=1.55, z=1.2)),
            ),
            legend=dict(bgcolor="rgba(255,255,255,0.85)", bordercolor="#D6D3D1", borderwidth=1),
        ),
    )
    return fig


def _build_figure(
    edge_counts: EdgeCounts,
    *,
    dim: int,
    top_relations_colored: int,
    layout_seed: int,
    layout_k: float,
    layout_iterations: int,
    label_top_nodes: int,
):
    if dim == 2:
        return _build_2d_figure(
            edge_counts,
            top_relations_colored=top_relations_colored,
            layout_seed=layout_seed,
            layout_k=layout_k,
            layout_iterations=layout_iterations,
            label_top_nodes=label_top_nodes,
        )
    return _build_3d_figure(
        edge_counts,
        top_relations_colored=top_relations_colored,
        layout_seed=layout_seed,
        layout_k=layout_k,
        layout_iterations=layout_iterations,
        label_top_nodes=label_top_nodes,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Build an interactive 2D/3D graph HTML from triplets JSON or JSONL.")
    ap.add_argument("--triples_path", required=True, help="Input triplets path (.json or .jsonl).")
    ap.add_argument("--out_html", required=True, help="Output HTML path.")
    ap.add_argument("--field_head", default="h")
    ap.add_argument("--field_rel", default="r")
    ap.add_argument("--field_tail", default="t")
    ap.add_argument(
        "--export_triplets_path",
        default="",
        help="Optional export path for structurally filtered triplets (.json, .csv, .txt).",
    )
    ap.add_argument(
        "--export_triplets_format",
        choices=["auto", "json", "csv", "txt"],
        default="auto",
        help="Export format for --export_triplets_path. auto infers from file extension.",
    )
    ap.add_argument("--dim", type=int, choices=[2, 3], default=2, help="Plot dimension. 2 is the default.")
    ap.add_argument("--center_node", default="", help="Optional node id to center an ego/neighborhood view on.")
    ap.add_argument("--hops", type=int, default=1, help="Hop count for --center_node neighborhood extraction.")
    ap.add_argument(
        "--largest_component",
        action="store_true",
        help="Keep only the largest weakly connected component before plotting.",
    )
    ap.add_argument(
        "--weak_component_rank",
        type=int,
        default=None,
        help="Optional 1-based weakly connected component rank to isolate before plotting.",
    )
    ap.add_argument(
        "--component_report_top_k",
        type=int,
        default=10,
        help="How many weak/strong component sizes to report in summaries.",
    )
    ap.add_argument("--max_nodes", type=int, default=0, help="0 keeps all nodes.")
    ap.add_argument("--max_edges", type=int, default=0, help="0 keeps all unique (h,r,t) edges.")
    ap.add_argument(
        "--sample_edges",
        action="store_true",
        help="When max_edges is active, sample edges randomly instead of keeping highest multiplicity first.",
    )
    ap.add_argument("--top_relations_colored", type=int, default=20, help="Top-K relations with distinct colors.")
    ap.add_argument("--label_top_nodes", type=int, default=40, help="Show text labels for top-degree nodes.")
    ap.add_argument("--layout_seed", type=int, default=42)
    ap.add_argument("--layout_k", type=float, default=0.0, help="Spring layout k. 0 uses networkx default.")
    ap.add_argument("--layout_iterations", type=int, default=100)
    args = ap.parse_args()

    triples = _load_triples(
        args.triples_path,
        field_head=str(args.field_head),
        field_rel=str(args.field_rel),
        field_tail=str(args.field_tail),
    )
    if not triples:
        raise RuntimeError("No triples loaded from input file.")

    edge_counts_all = _aggregate_triples(triples)
    _require_nonempty(edge_counts_all, stage="loading")

    nodes_before_filter, edges_before_filter = _edge_counts_stats(edge_counts_all)
    edge_counts = dict(edge_counts_all)

    center_node = str(args.center_node).strip()
    if center_node:
        edge_counts = _filter_by_center_node(edge_counts, center_node=center_node, hops=max(0, int(args.hops)))
        _require_nonempty(edge_counts, stage="center-node neighborhood filtering")

    if args.weak_component_rank is not None:
        edge_counts = _filter_weak_component_rank(edge_counts, rank=int(args.weak_component_rank))
        _require_nonempty(edge_counts, stage="weak-component-rank filtering")

    if bool(args.largest_component):
        edge_counts = _filter_largest_component(edge_counts)
        _require_nonempty(edge_counts, stage="largest-component filtering")

    edge_counts_structural = dict(edge_counts)
    export_info: Optional[Dict[str, object]] = None
    if args.export_triplets_path:
        export_triples = _filter_loaded_triples_by_edge_counts(triples, edge_counts_structural)
        if not export_triples:
            raise RuntimeError("No structurally filtered triplets remain for export.")
        export_info = _write_export_triplets(
            str(args.export_triplets_path),
            export_triples,
            export_format=str(args.export_triplets_format),
            field_head=str(args.field_head),
            field_rel=str(args.field_rel),
            field_tail=str(args.field_tail),
        )

    edge_counts = _filter_by_nodes(edge_counts, max_nodes=_safe_int(args.max_nodes, 0))
    _require_nonempty(edge_counts, stage="max_nodes filtering")

    edge_counts = _filter_by_edges(
        edge_counts,
        max_edges=_safe_int(args.max_edges, 0),
        sample_edges=bool(args.sample_edges),
        random_seed=_safe_int(args.layout_seed, 42),
    )
    _require_nonempty(edge_counts, stage="max_edges filtering")

    nodes_after_filter, edges_after_filter = _edge_counts_stats(edge_counts)
    g_layout = _build_layout_graph(edge_counts)
    connectivity = _compute_connectivity_diagnostics(
        g_layout,
        top_k=max(1, _safe_int(args.component_report_top_k, 10)),
    )

    fig = _build_figure(
        edge_counts=edge_counts,
        dim=int(args.dim),
        top_relations_colored=max(0, _safe_int(args.top_relations_colored, 20)),
        layout_seed=_safe_int(args.layout_seed, 42),
        layout_k=float(args.layout_k),
        layout_iterations=max(1, _safe_int(args.layout_iterations, 1000)),
        label_top_nodes=max(0, _safe_int(args.label_top_nodes, 40)),
    )

    out_path = Path(args.out_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out_path), include_plotlyjs=True, full_html=True)

    rel_counter: Counter[str] = Counter()
    for (_h, r, _t), c in edge_counts.items():
        rel_counter[r] += c

    summary = {
        "triples_input_rows": len(triples),
        "triples_unique_edges_used": len(edge_counts),
        "nodes_used": nodes_after_filter,
        "relations_used": len(rel_counter),
        "top_relations": rel_counter.most_common(10),
        "out_html": str(out_path.resolve()),
        "dim": int(args.dim),
        "center_node": center_node or None,
        "hops": int(max(0, args.hops)),
        "largest_component": bool(args.largest_component),
        "nodes_before_filter": int(nodes_before_filter),
        "nodes_after_filter": int(nodes_after_filter),
        "edges_before_filter": int(edges_before_filter),
        "edges_after_filter": int(edges_after_filter),
        "weak_component_rank": int(args.weak_component_rank) if args.weak_component_rank is not None else None,
        "component_report_top_k": int(max(1, _safe_int(args.component_report_top_k, 10))),
        "max_nodes": int(args.max_nodes),
        "max_edges": int(args.max_edges),
        "sample_edges": bool(args.sample_edges),
        "export_triplets_path": export_info["path"] if export_info else None,
        "export_triplets_format": export_info["format"] if export_info else None,
        "export_triplets_rows": int(export_info["rows"]) if export_info else None,
    }
    summary.update(connectivity)

    print(
        "[filter] "
        f"input_triples={len(triples)} "
        f"unique_edges={edges_before_filter} "
        f"nodes_before={nodes_before_filter} "
        f"nodes_after={nodes_after_filter} "
        f"edges_after={edges_after_filter} "
        f"center_node={center_node or '-'} "
        f"hops={int(max(0, args.hops))} "
        f"largest_component={bool(args.largest_component)}"
    )
    print("[connectivity] components are computed from graph structure, not from visual layout positions")
    print(
        "[connectivity] "
        f"weak_components={connectivity['num_weak_components']} "
        f"strong_components={connectivity['num_strong_components']} "
        f"largest_weak={connectivity['largest_weak_component_size']}/{connectivity['graph_nodes']} "
        f"fraction={connectivity['largest_weak_component_fraction']:.4f}"
    )
    print(
        "[components] "
        f"top_weak={connectivity['top_weak_component_sizes']} "
        f"top_strong={connectivity['top_strong_component_sizes']}"
    )
    if export_info:
        print(
            "[export] "
            f"path={export_info['path']} "
            f"format={export_info['format']} "
            f"rows={export_info['rows']}"
        )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
