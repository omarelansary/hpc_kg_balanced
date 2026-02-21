#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


def is_pid(x: str) -> bool:
    return isinstance(x, str) and len(x) >= 2 and x[0] == "P" and x[1:].isdigit()


@st.cache_data(show_spinner=False)
def load_pairs(jsonl_path: str, only_success: bool = True) -> pd.DataFrame:
    rows = []
    doc_status = defaultdict(int)
    doc_mode = defaultdict(int)
    bad_support_rows = 0
    missing_support_data_docs = 0

    unique_r1_docs = set()
    unique_r1_docs_success = set()
    unique_r1_with_pairs = set()
    r1_status_counts = defaultdict(lambda: defaultdict(int))

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                doc_status["__JSON_DECODE_ERROR__"] += 1
                continue

            status = doc.get("status", "NO_STATUS")
            mode = doc.get("mode", "NO_MODE")
            doc_status[status] += 1
            doc_mode[mode] += 1

            r1 = doc.get("r1")
            if not is_pid(r1):
                continue

            r1_status_counts[r1][status] += 1

            # doc-level coverage (independent of only_success)
            unique_r1_docs.add(r1)
            if status == "SUCCESS":
                unique_r1_docs_success.add(r1)

            # pair extraction can still be limited to SUCCESS docs
            if only_success and status != "SUCCESS":
                continue
    
            support_data = doc.get("support_data", {})
            if not isinstance(support_data, dict):
                missing_support_data_docs += 1
                continue

            added_any = False
            for r2, rec in support_data.items():
                if not is_pid(r2) or not isinstance(rec, dict):
                    continue
                try:
                    loop = int(rec.get("loop", 0) or 0)
                    nonloop = int(rec.get("nonloop", 0) or 0)
                    total = int(rec.get("total", loop + nonloop) or (loop + nonloop))
                except (TypeError, ValueError):
                    bad_support_rows += 1
                    continue

                rows.append(
                    {
                        "r1": r1,
                        "r2": r2,
                        "loop": loop,
                        "nonloop": nonloop,
                        "total": total,
                        "mode": mode,
                        "status": status,
                        "input_status": doc.get("input_status"),
                    }
                )
                added_any = True

            if added_any:
                unique_r1_with_pairs.add(r1)


    df = pd.DataFrame(rows)
    # Attach doc-level stats (for display)
    df.attrs["doc_status"] = dict(doc_status)
    df.attrs["doc_mode"] = dict(doc_mode)
    df.attrs["bad_support_rows"] = int(bad_support_rows)
    df.attrs["missing_support_data_docs"] = int(missing_support_data_docs)
    df.attrs["unique_r1_docs"] = len(unique_r1_docs)
    df.attrs["unique_r1_docs_success"] = len(unique_r1_docs_success)
    df.attrs["unique_r1_with_pairs"] = len(unique_r1_with_pairs)
    # Resolve one display status per r1 with conservative precedence.
    r1_status = {}
    for r1, counts in r1_status_counts.items():
        if counts.get("ERROR", 0) > 0:
            r1_status[r1] = "ERROR"
        elif counts.get("PARTIAL_SUCCESS", 0) > 0:
            r1_status[r1] = "PARTIAL_SUCCESS"
        elif counts.get("SUCCESS", 0) > 0:
            r1_status[r1] = "SUCCESS"
        else:
            r1_status[r1] = max(counts.items(), key=lambda kv: kv[1])[0]
    df.attrs["r1_status"] = r1_status

    return df


def describe_series(s: pd.Series) -> pd.DataFrame:
    s = s.dropna().astype(float)
    if s.empty:
        return pd.DataFrame()

    percentiles = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
    q = s.quantile(percentiles, interpolation="linear")
    out = {
        "count": s.count(),
        "mean": s.mean(),
        "std": s.std(ddof=1) if s.count() > 1 else 0.0,
        "min": s.min(),
        "q1": s.quantile(0.25),
        "median": s.quantile(0.50),
        "q3": s.quantile(0.75),
        "max": s.max(),
    }
    # 10% steps
    for p in range(10, 100, 10):
        out[f"p{p}"] = float(q[p / 100.0])
    out["p95"] = float(q[0.95])
    out["p99"] = float(q[0.99])

    return pd.DataFrame([out])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=False, default="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced/data/archived/hop_support_v2_w_failed_statuses.wikibase_item_only_before_target_enrichment.jsonl")
    ap.add_argument("--include_non_success_docs", action="store_true")
    args = ap.parse_args()

    st.set_page_config(page_title="Hop Support Explorer", layout="wide")
    st.title("Hop Support Explorer (JSONL)")

    only_success = not args.include_non_success_docs
    df = load_pairs(args.input, only_success=only_success)

    # Header stats
    colA, colB, colC = st.columns([1, 1, 2])
    with colA:
        st.subheader("Doc status counts")
        status_counts = (
            pd.Series(df.attrs.get("doc_status", {}), name="count")
            .rename_axis("status")
            .reset_index()
            .sort_values("count", ascending=False)
        )
        st.dataframe(status_counts, use_container_width=True, hide_index=True)
    with colB:
        st.subheader("Doc mode counts")
        mode_counts = (
            pd.Series(df.attrs.get("doc_mode", {}), name="count")
            .rename_axis("mode")
            .reset_index()
            .sort_values("count", ascending=False)
        )
        st.dataframe(mode_counts, use_container_width=True, hide_index=True)
    with colC:
        st.subheader("Pairs extracted")
        st.metric("Rows (r1,r2)", len(df))
        st.metric("Unique r1 (docs)", int(df.attrs.get("unique_r1_docs", 0)))
        st.metric("Unique r1 (SUCCESS docs)", int(df.attrs.get("unique_r1_docs_success", 0)))
        st.metric("Unique r1 (with >=1 pair)", int(df.attrs.get("unique_r1_with_pairs", 0)))
        st.metric("Unique r2", df["r2"].nunique() if not df.empty else 0)
        st.metric("Skipped malformed support rows", int(df.attrs.get("bad_support_rows", 0)))
        st.metric("Docs without support_data", int(df.attrs.get("missing_support_data_docs", 0)))

    if df.empty:
        st.warning("No rows loaded (check file path or filters).")
        return

    # Sidebar filters
    st.sidebar.header("Filters")
    min_total, max_total = int(df["total"].min()), int(df["total"].max())
    lo = int(
        st.sidebar.number_input(
            "Min total support",
            min_value=min_total,
            max_value=max_total,
            value=min_total,
            step=1,
        )
    )
    hi = int(
        st.sidebar.number_input(
            "Max total support",
            min_value=min_total,
            max_value=max_total,
            value=max_total,
            step=1,
        )
    )
    if lo > hi:
        st.sidebar.error("Min total support cannot be greater than max total support.")
        return

    # Optional PID filters
    r1_query = st.sidebar.text_input("Filter r1 (exact PID, optional)", "")
    r2_query = st.sidebar.text_input("Filter r2 (exact PID, optional)", "")

    df_f = df[(df["total"] >= lo) & (df["total"] <= hi)]
    if r1_query.strip():
        df_f = df_f[df_f["r1"] == r1_query.strip()]
    if r2_query.strip():
        df_f = df_f[df_f["r2"] == r2_query.strip()]

    st.subheader("Filtered dataset")
    st.write(f"Kept **{len(df_f)}** / {len(df)} pairs")
    if df_f.empty:
        st.warning("No rows after filters.")
        return

    color_status = st.sidebar.checkbox(
        "Color plots by status",
        value=(df_f["status"].nunique() > 1),
    )
    color_arg = "status" if color_status else None

    # Descriptive stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### total stats")
        st.dataframe(describe_series(df_f["total"]), use_container_width=True, hide_index=True)
    with col2:
        st.markdown("### loop stats")
        st.dataframe(describe_series(df_f["loop"]), use_container_width=True, hide_index=True)
    with col3:
        st.markdown("### nonloop stats")
        st.dataframe(describe_series(df_f["nonloop"]), use_container_width=True, hide_index=True)

    # Plots
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        fig = px.histogram(df_f, x="total", color=color_arg, nbins=60, title="Histogram: total support")
        st.plotly_chart(fig, use_container_width=True)
    with pcol2:
        fig = px.box(df_f, y="total", color=color_arg, points="outliers", title="Boxplot: total support")
        st.plotly_chart(fig, use_container_width=True)

    # Top/bottom pairs
    st.markdown("## Extremes")
    ecol1, ecol2 = st.columns(2)

    topn = st.sidebar.number_input("Top-N", min_value=5, max_value=200, value=20, step=5)

    with ecol1:
        st.markdown(f"### Top {topn} (r1,r2) by total")
        top_pairs = df_f.sort_values(["total", "r1", "r2"], ascending=[False, True, True]).head(topn)
        st.dataframe(top_pairs, use_container_width=True)

    with ecol2:
        st.markdown(f"### Bottom {topn} (r1,r2) by total")
        bot_pairs = df_f.sort_values(["total", "r1", "r2"], ascending=[True, True, True]).head(topn)
        st.dataframe(bot_pairs, use_container_width=True)

    # Aggregate by r2
    st.markdown("## r2-level aggregates")
    agg_r2 = (
        df_f.groupby("r2")
        .agg(
            count=("total", "size"),
            mean_total=("total", "mean"),
            max_total=("total", "max"),
            min_total=("total", "min"),
            sum_total=("total", "sum"),
            sum_loop=("loop", "sum"),
            sum_nonloop=("nonloop", "sum"),
        )
        .reset_index()
    )

    acol1, acol2 = st.columns(2)
    with acol1:
        st.markdown(f"### Top {topn} r2 by mean(total)")
        st.dataframe(agg_r2.sort_values(["mean_total", "sum_total"], ascending=False).head(topn), use_container_width=True)
    with acol2:
        st.markdown(f"### Top {topn} r2 by max(total)")
        st.dataframe(agg_r2.sort_values(["max_total", "mean_total"], ascending=False).head(topn), use_container_width=True)

    # Aggregate by r1
    st.markdown("## r1-level aggregates")
    agg_r1 = (
        df_f.groupby("r1")
        .agg(
            count=("total", "size"),
            mean_total=("total", "mean"),
            max_total=("total", "max"),
            sum_total=("total", "sum"),
        )
        .reset_index()
    )
    st.dataframe(agg_r1.sort_values(["sum_total", "max_total"], ascending=False).head(topn), use_container_width=True)

    # Square adjacency matrix view
    st.markdown("## Adjacency Matrix (square)")
    node_source = st.radio(
        "Nodes from",
        options=["Filtered", "Raw"],
        index=0,
        horizontal=True,
        help="Choose whether matrix node list is derived from the filtered dataset or the raw loaded dataset.",
    )
    matrix_nodes_df = df_f if node_source == "Filtered" else df
    node_edge_sum = matrix_nodes_df.groupby(["r1", "r2"], as_index=False)["total"].sum()
    available_nodes = sorted(set(node_edge_sum["r1"]).union(set(node_edge_sum["r2"])))
    available_node_count = len(available_nodes)
    if available_node_count == 0:
        st.warning("No nodes available for adjacency matrix with current filters.")
        return

    default_node_k = min(50, available_node_count)
    node_k = st.slider("Node count", 1, available_node_count, default_node_k, 1)
    error_value = float(
        st.number_input(
            "Error sentinel value",
            value=-1.0,
            step=0.1,
            help="Used on diagonal cells for nodes whose r1 status includes ERROR.",
        )
    )

    edge_sum = df_f.groupby(["r1", "r2"], as_index=False)["total"].sum()
    edge_sum_raw = df.groupby(["r1", "r2"], as_index=False)["total"].sum()
    out_score = node_edge_sum.groupby("r1", as_index=False)["total"].sum().rename(columns={"r1": "node", "total": "out"})
    in_score = node_edge_sum.groupby("r2", as_index=False)["total"].sum().rename(columns={"r2": "node", "total": "in"})
    node_score = out_score.merge(in_score, on="node", how="outer").fillna(0.0)
    node_score["score"] = node_score["out"] + node_score["in"]
    nodes = node_score.sort_values(["score", "node"], ascending=[False, True]).head(node_k)["node"].tolist()

    square_filtered = (
        edge_sum.pivot_table(index="r1", columns="r2", values="total", aggfunc="sum", fill_value=0)
        .reindex(index=nodes, columns=nodes, fill_value=0)
        .astype(float)
    )
    square_raw = (
        edge_sum_raw.pivot_table(index="r1", columns="r2", values="total", aggfunc="sum", fill_value=0)
        .reindex(index=nodes, columns=nodes, fill_value=0)
        .astype(float)
    )
    square_log = np.log1p(square_filtered)
    state = np.full(square_filtered.shape, "NO_EDGE", dtype=object)
    state[square_raw.values > 0] = "FILTERED_OUT"
    state[square_filtered.values > 0] = "EDGE"

    r1_status = df.attrs.get("r1_status", {})
    for i, node in enumerate(nodes):
        if r1_status.get(node) == "ERROR" and square_filtered.iat[i, i] == 0:
            square_log.iat[i, i] = error_value
            state[i, i] = "ERROR"

    customdata = np.dstack([square_filtered.values, square_raw.values, state])
    fig = px.imshow(
        square_log.values,
        x=nodes,
        y=nodes,
        aspect="equal",
        color_continuous_scale="Viridis",
        title="Adjacency matrix value: log(1 + support), 0=no edge, error=sentinel",
    )
    fig.update_traces(
        customdata=customdata,
        hovertemplate=(
            "r1: %{y}<br>"
            "r2: %{x}<br>"
            "state: %{customdata[2]}<br>"
            "filtered_support: %{customdata[0]}<br>"
            "raw_support: %{customdata[1]}<br>"
            "matrix_value: %{z:.4f}<extra></extra>"
        ),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Legend: NO_EDGE -> no raw connection; FILTERED_OUT -> raw edge exists but removed by filters; "
        f"ERROR -> {error_value}; EDGE -> log(1 + filtered_support). "
        "Rows and columns use the same node order, so diagonal cells are r1==r2."
    )

if __name__ == "__main__":
    main()
