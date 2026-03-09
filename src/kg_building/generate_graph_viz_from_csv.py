#!/usr/bin/env python3
"""Generate an interactive graph visualization from an edge-list CSV.

Expected CSV schema:
- mandatory: source and target columns
- optional: weight column (for edge width and hover info)
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import networkx as nx
import plotly.graph_objects as go


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate interactive graph HTML from CSV edge list.")
    p.add_argument("--input", required=True, help="Path to CSV file.")
    p.add_argument("--source-col", required=True, help="Source node column.")
    p.add_argument("--target-col", required=True, help="Target node column.")
    p.add_argument("--weight-col", default="", help="Optional weight column.")
    p.add_argument(
        "--directed",
        action="store_true",
        help="Use directed graph (default: undirected).",
    )
    p.add_argument(
        "--top-edges",
        type=int,
        default=400,
        help="Keep top-N edges by weight. If no weight, keeps first N rows. Default: 400.",
    )
    p.add_argument(
        "--max-nodes",
        type=int,
        default=200,
        help="Limit nodes to top degree nodes after edge filtering. Default: 200.",
    )
    p.add_argument(
        "--output",
        required=True,
        help="Output HTML path.",
    )
    return p.parse_args()


def parse_weight(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 1.0


def load_edges(
    input_csv: Path,
    source_col: str,
    target_col: str,
    weight_col: str,
) -> list[tuple[str, str, float]]:
    last_decode_error: UnicodeDecodeError | None = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        edges: list[tuple[str, str, float]] = []
        try:
            with input_csv.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                missing = [c for c in [source_col, target_col] if c not in reader.fieldnames]
                if missing:
                    raise ValueError(f"Missing required column(s): {missing}. Available: {reader.fieldnames}")
                for row in reader:
                    s = str(row.get(source_col, "")).strip()
                    t = str(row.get(target_col, "")).strip()
                    if not s or not t:
                        continue
                    w = parse_weight(str(row.get(weight_col, "1.0"))) if weight_col else 1.0
                    edges.append((s, t, w))
            return edges
        except UnicodeDecodeError as exc:
            last_decode_error = exc
            continue
    if last_decode_error is not None:
        raise ValueError(f"Failed to decode CSV with tried encodings: {last_decode_error}") from last_decode_error
    return []


def build_figure(G: nx.Graph) -> go.Figure:
    pos = nx.spring_layout(G, seed=42, k=None, iterations=80)

    edge_x: list[float] = []
    edge_y: list[float] = []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=0.6, color="rgba(130,130,130,0.45)"),
        hoverinfo="none",
        mode="lines",
        showlegend=False,
    )

    node_x: list[float] = []
    node_y: list[float] = []
    node_text: list[str] = []
    node_color: list[int] = []
    for n in G.nodes():
        x, y = pos[n]
        deg = int(G.degree(n))
        node_x.append(x)
        node_y.append(y)
        node_text.append(f"{n}<br>degree={deg}")
        node_color.append(deg)

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=[str(n) for n in G.nodes()],
        textposition="top center",
        hoverinfo="text",
        hovertext=node_text,
        marker=dict(
            showscale=True,
            colorscale="YlGnBu",
            color=node_color,
            size=10,
            colorbar=dict(title="Node Degree"),
            line_width=0.8,
        ),
        showlegend=False,
    )

    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title=f"Graph Visualization ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)",
            title_x=0.5,
            hovermode="closest",
            margin=dict(b=20, l=10, r=10, t=60),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            template="plotly_white",
        ),
    )
    return fig


def main() -> None:
    args = parse_args()
    input_csv = Path(args.input)
    output_html = Path(args.output)
    output_html.parent.mkdir(parents=True, exist_ok=True)

    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    edges = load_edges(input_csv, args.source_col, args.target_col, args.weight_col)
    if not edges:
        raise ValueError("No valid edges found in CSV.")

    if args.weight_col:
        edges = sorted(edges, key=lambda e: e[2], reverse=True)
    if args.top_edges > 0:
        edges = edges[: args.top_edges]

    G: nx.Graph | nx.DiGraph
    G = nx.DiGraph() if args.directed else nx.Graph()
    for s, t, w in edges:
        if G.has_edge(s, t):
            G[s][t]["weight"] += float(w)
        else:
            G.add_edge(s, t, weight=float(w))

    if args.max_nodes > 0 and G.number_of_nodes() > args.max_nodes:
        keep_nodes = {n for n, _ in sorted(G.degree, key=lambda x: x[1], reverse=True)[: args.max_nodes]}
        G = G.subgraph(keep_nodes).copy()

    if G.number_of_edges() == 0:
        raise ValueError("No edges remain after filtering.")

    fig = build_figure(G)
    # Embed plotly.js for offline/local viewing (no external CDN dependency).
    fig.write_html(str(output_html), include_plotlyjs=True, full_html=True)

    print(f"Generated: {output_html}")
    print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")


if __name__ == "__main__":
    main()
