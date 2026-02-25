#!/usr/bin/env python3
"""Research dashboard for relation-pattern confidence analysis.

This app combines two analysis layers:
1) Phase 1 from hop-support counts:
   - symmetric behavior (r1 == r2) via loop/total
   - anti-symmetric behavior (r1 == r2) via nonloop/total
   - inverse behavior (r1 != r2) with forward and reverse consistency checks
2) Phase 2 from composition verification output:
   - sampled composition confidence for triples (r1, r2, r3)
   - optional Wilson-interval filtering for statistically conservative ranking

Methodological note:
- All confidence values here are empirical proportions over collected/sampled
  chain pairs. They indicate evidence strength in the observed data, not formal
  logical guarantees over the full knowledge graph.
"""

import argparse
import inspect
import json
import math
import os
import random
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

try:
    from src.kg_building.bidirectional_triple_allocation import allocate_for_patterns
except ModuleNotFoundError:
    # Allow running this file directly (e.g., streamlit run path/to/file.py)
    # by adding project root to sys.path at runtime.
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    from src.kg_building.bidirectional_triple_allocation import allocate_for_patterns

try:
    from src.kg_building.build_connected_graph_from_allocation import (
        LocalTripleSource,
        RealizationConfig,
        TripleSource,
        build_relation_quotas,
        is_connected_undirected,
        load_triples_jsonl_index,
        realize_connected_graph,
    )
    from src.kg_building.config_sampler import MongoConfig
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    from src.kg_building.build_connected_graph_from_allocation import (
        LocalTripleSource,
        RealizationConfig,
        TripleSource,
        build_relation_quotas,
        is_connected_undirected,
        load_triples_jsonl_index,
        realize_connected_graph,
    )
    from src.kg_building.config_sampler import MongoConfig


def is_pid(x: str) -> bool:
    """Return True if `x` matches a Wikidata property-id token (e.g., ``P31``).

    Reason:
    Input JSONL may contain non-property tokens or malformed records. Filtering
    early avoids contaminating confidence aggregates with invalid relation IDs.
    """
    return isinstance(x, str) and len(x) >= 2 and x[0] == "P" and x[1:].isdigit()


@st.cache_data(show_spinner=False)
def load_pair_counts(jsonl_path: str, only_success: bool = True) -> pd.DataFrame:
    """Load and aggregate hop support counts from JSONL.

    Args:
        jsonl_path: Path to JSONL produced by hop support collection.
        only_success: If True, keep docs with status == SUCCESS only.

    Returns:
        DataFrame with one row per (r1, r2), aggregated across input docs:
        columns = [r1, r2, loop, nonloop, total, conf_loop, conf_nonloop].

    Formulas used:
        conf_loop(r1, r2) = loop / total
        conf_nonloop(r1, r2) = nonloop / total

    Rationale:
    - `loop` and `nonloop` come directly from hop-support extraction and are
      additive across documents, so summing before ratio is appropriate.
    - restricting to SUCCESS docs (default) avoids mixing complete and partial
      extraction outcomes in baseline pattern confidence estimates.
    """
    rows = []
    doc_status = defaultdict(int)
    bad_rows = 0

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
            doc_status[status] += 1
            if only_success and status != "SUCCESS":
                continue

            r1 = doc.get("r1")
            support_data = doc.get("support_data", {})
            if not is_pid(r1) or not isinstance(support_data, dict):
                continue

            for r2, rec in support_data.items():
                if not is_pid(r2) or not isinstance(rec, dict):
                    continue
                try:
                    loop = int(rec.get("loop", 0) or 0)
                    nonloop = int(rec.get("nonloop", 0) or 0)
                    total = int(rec.get("total", loop + nonloop) or (loop + nonloop))
                except (TypeError, ValueError):
                    bad_rows += 1
                    continue

                rows.append({"r1": r1, "r2": r2, "loop": loop, "nonloop": nonloop, "total": total})

    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["r1", "r2", "loop", "nonloop", "total"])

    agg = (
        df.groupby(["r1", "r2"], as_index=False)
        .agg(loop=("loop", "sum"), nonloop=("nonloop", "sum"), total=("total", "sum"))
    )
    agg["conf_loop"] = agg["loop"] / agg["total"].where(agg["total"] > 0, pd.NA)
    agg["conf_nonloop"] = agg["nonloop"] / agg["total"].where(agg["total"] > 0, pd.NA)
    agg["conf_loop"] = agg["conf_loop"].fillna(0.0)
    agg["conf_nonloop"] = agg["conf_nonloop"].fillna(0.0)

    agg.attrs["doc_status"] = dict(doc_status)
    agg.attrs["bad_rows"] = int(bad_rows)
    return agg


@st.cache_data(show_spinner=False)
def load_property_domain_range_class_map(json_path: str) -> dict[str, str]:
    """Load relation domain/range classes from properties JSON.

    Classification labels:
    - `ANY_SUBJECT`: no subject type constraints, object types constrained
    - `ANY_DOMAIN`: subject types constrained, no object type constraints
    - `ANY_BOTH`: both subject and object unconstrained
    - `FULL_BOTH`: both subject and object constrained
    """
    path = Path(json_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return {}

    out: dict[str, str] = {}
    for rec in data:
        if not isinstance(rec, dict):
            continue
        pid = str(rec.get("property_id", "")).strip()
        if not pid:
            continue
        subj = rec.get("valid_subject_type_ids", [])
        obj = rec.get("valid_object_type_ids", [])
        subj_any = not isinstance(subj, list) or len(subj) == 0
        obj_any = not isinstance(obj, list) or len(obj) == 0
        if subj_any and obj_any:
            cls = "ANY_BOTH"
        elif subj_any and not obj_any:
            cls = "ANY_SUBJECT"
        elif not subj_any and obj_any:
            cls = "ANY_DOMAIN"
        else:
            cls = "FULL_BOTH"
        out[pid] = cls
    return out


@st.cache_data(show_spinner=False)
def load_property_domain_range_types_map(json_path: str) -> dict[str, dict[str, list[str]]]:
    """Load per-property subject/object type constraints.

    Returns mapping:
    - property_id -> {"subject": [...], "object": [...]}
    """
    path = Path(json_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    for rec in data:
        if not isinstance(rec, dict):
            continue
        pid = str(rec.get("property_id", "")).strip()
        if not pid:
            continue
        subj = rec.get("valid_subject_type_ids", [])
        obj = rec.get("valid_object_type_ids", [])
        subj_list = [str(x) for x in subj] if isinstance(subj, list) else []
        obj_list = [str(x) for x in obj] if isinstance(obj, list) else []
        out[pid] = {"subject": subj_list, "object": obj_list}
    return out


def prepare_inverse_table(df_pairs: pd.DataFrame) -> pd.DataFrame:
    """Build inverse-confidence table with forward/reverse and bidirectional scores.

    Input df_pairs must contain aggregated (r1, r2) rows with `conf_loop`.

    Returned columns include:
    - conf_loop: forward inverse confidence, conf(r1, r2)
    - reverse_conf_loop: reverse inverse confidence, conf(r2, r1)
    - bidirectional_conf_min: min(conf(r1, r2), conf(r2, r1))
    - bidirectional_conf_mean: mean(conf(r1, r2), conf(r2, r1))

    Rationale:
    - forward-only scores can overstate inverse quality when the reverse
      direction is weak; `bidirectional_conf_min` is a strict conservative
      criterion aligned with "both directions should be high".
    """
    base = df_pairs[df_pairs["r1"] != df_pairs["r2"]][["r1", "r2", "loop", "nonloop", "total", "conf_loop"]].copy()
    rev = base[["r1", "r2", "conf_loop", "total"]].rename(
        columns={"r1": "r2", "r2": "r1", "conf_loop": "reverse_conf_loop", "total": "reverse_total"}
    )
    out = base.merge(rev, on=["r1", "r2"], how="left")
    out["reverse_conf_loop"] = out["reverse_conf_loop"].fillna(0.0)
    out["reverse_total"] = out["reverse_total"].fillna(0).astype(int)
    out["bidirectional_conf_min"] = out[["conf_loop", "reverse_conf_loop"]].min(axis=1)
    out["bidirectional_conf_mean"] = out[["conf_loop", "reverse_conf_loop"]].mean(axis=1)
    return out


def wilson_interval(successes: int, n: int, z: float) -> tuple[float, float]:
    """Return Wilson score interval `(lower, upper)` for a binomial proportion.

    Args:
        successes: Number of positive outcomes (shortcut hits).
        n: Number of Bernoulli trials (examined chain pairs).
        z: Normal quantile for desired confidence level (e.g., 1.96 for 95%).

    Why Wilson:
    - naive normal intervals are unstable for small `n` or extreme proportions.
    - Wilson gives better finite-sample behavior and bounded [0,1] intervals.
    - In this app we primarily use the lower bound to rank/filter composition
      rules conservatively under sampling uncertainty.
    """
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    z2 = z * z
    denom = 1.0 + (z2 / n)
    center = (p + (z2 / (2.0 * n))) / denom
    margin = (z / denom) * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return lower, upper


@st.cache_data(show_spinner=False)
def load_composition_verified_compact(jsonl_path: str, only_success: bool = True) -> pd.DataFrame:
    """Load flattened composition triples from compact verified composition JSONL.

    Args:
        jsonl_path: Path to `*.composition_verified.compact.jsonl`.
        only_success: If True, keep source rows with input_status == SUCCESS only.

    Returns:
        DataFrame with one row per discovered composition triple (r1, r2, r3):
        columns include base pair support and sampled composition statistics.

    Formulas used in this phase:
        conf_composition_sample(r1, r2, r3) = chain_pairs_with_shortcut / chain_pairs_examined

    Notes:
        `chain_pairs_examined` is sampled verification workload from the verifier.
        It is used as the denominator for phase-2 sample confidence.

    Rationale:
    - compact verified JSONL is preferred for interactive analysis because it
      preserves composition verification statistics without the heavy per-row
      target payload of the full verified file.
    - this loader keeps one row per discovered (r1, r2, r3) rule candidate to
      support direct ranking, filtering, and per-pair best-target summaries.
    """
    rows = []
    input_status_counts = defaultdict(int)
    run_status_counts = defaultdict(int)
    bad_rows = 0

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                bad_rows += 1
                continue

            input_status = doc.get("input_status", "NO_STATUS")
            input_status_counts[input_status] += 1
            if only_success and input_status != "SUCCESS":
                continue

            rv = doc.get("rule_verification", {})
            if not isinstance(rv, dict):
                continue

            run = rv.get("composition_run", {})
            if isinstance(run, dict):
                run_status_counts[run.get("status", "NO_RUN_STATUS")] += 1

            r1 = doc.get("r1")
            r2 = doc.get("r2")
            if not is_pid(r1) or not is_pid(r2):
                continue

            base_support = int(doc.get("support", 0) or 0)
            source_mode = doc.get("source_mode")
            target_count = int(doc.get("target_count", 0) or 0)
            targets_truncated = bool(doc.get("targets_truncated", False))

            comp = rv.get("composition", {})
            if not isinstance(comp, dict) or not comp:
                continue

            for r3, rec in comp.items():
                if not is_pid(r3) or not isinstance(rec, dict):
                    continue
                try:
                    examined = int(rec.get("chain_pairs_examined", 0) or 0)
                    shortcuts = int(rec.get("chain_pairs_with_shortcut", 0) or 0)
                    missing = int(rec.get("chain_pairs_missing_shortcut", max(examined - shortcuts, 0)) or 0)
                except (TypeError, ValueError):
                    bad_rows += 1
                    continue

                conf_sample = (shortcuts / examined) if examined > 0 else 0.0
                conf_reported = float(rec.get("sample_confidence", conf_sample) or conf_sample)
                rows.append(
                    {
                        "r1": r1,
                        "r2": r2,
                        "r3": r3,
                        "base_support": base_support,
                        "chain_pairs_examined": examined,
                        "chain_pairs_with_shortcut": shortcuts,
                        "chain_pairs_missing_shortcut": missing,
                        "conf_composition_sample": conf_sample,
                        "sample_confidence_reported": conf_reported,
                        "source_mode": source_mode,
                        "target_count": target_count,
                        "targets_truncated": targets_truncated,
                    }
                )

    out = pd.DataFrame(rows)
    if out.empty:
        out = pd.DataFrame(
            columns=[
                "r1",
                "r2",
                "r3",
                "base_support",
                "chain_pairs_examined",
                "chain_pairs_with_shortcut",
                "chain_pairs_missing_shortcut",
                "conf_composition_sample",
                "sample_confidence_reported",
                "source_mode",
                "target_count",
                "targets_truncated",
            ]
        )

    out.attrs["input_status_counts"] = dict(input_status_counts)
    out.attrs["run_status_counts"] = dict(run_status_counts)
    out.attrs["bad_rows"] = int(bad_rows)
    return out


def classify_composition_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Classify accepted composition triples by transitivity and commutativity.

    Input assumption:
    - `df` already contains composition triples that passed the user's
      confidence/support thresholds, i.e., "composition holds" under filters.

    Classification rules:
    1) Self-transitive composition:
       - r1 == r2 == r3
       - label: `transitive_self_composition`
    2) Otherwise non-transitive composition:
       - test commutativity by swap existence:
         (r2, r1, r3) also present in accepted set
       - if swap exists: `non_transitive_commutative_composition`
       - else: `non_transitive_non_commutative_composition`

    Notes:
    - Commutativity here is empirical/existential in the accepted result set,
      not a universal logical proof over all graph facts.
    """
    out = df.copy()
    if out.empty:
        out["is_transitive_self"] = pd.Series(dtype=bool)
        out["swap_supports_same_target"] = pd.Series(dtype=bool)
        out["composition_class"] = pd.Series(dtype=str)
        return out

    accepted = set(zip(out["r1"], out["r2"], out["r3"]))

    is_transitive_self = (out["r1"] == out["r2"]) & (out["r2"] == out["r3"])
    swap_supports_same_target = out.apply(lambda r: (r["r2"], r["r1"], r["r3"]) in accepted, axis=1)

    out["is_transitive_self"] = is_transitive_self
    out["swap_supports_same_target"] = swap_supports_same_target

    out["composition_class"] = "non_transitive_non_commutative_composition"
    out.loc[swap_supports_same_target, "composition_class"] = "non_transitive_commutative_composition"
    out.loc[is_transitive_self, "composition_class"] = "transitive_self_composition"
    return out


def _unique_preserve(values) -> list[str]:
    out = []
    seen = set()
    for v in values:
        if isinstance(v, str) and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def build_pattern_groups(
    sym_df: pd.DataFrame,
    anti_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    comp_df: pd.DataFrame,
) -> tuple[dict[str, list[str]], list[str]]:
    """Build unique relation groups for phase-3 allocation.

    Semantics:
    - Phase 1/2 tables are candidate-level:
      - inverse: one row per (r1, r2)
      - composition: one row per (r1, r2, r3)
    - Phase 3 allocation is relation-level:
      - each group is the UNIQUE relation-ID set derived from candidate rows.

    Consequence:
    - "candidate count" from Phase 1/2 will generally differ from
      "group size" shown in Phase 3.
    """
    sym_rel = _unique_preserve(sym_df["r1"].tolist()) if not sym_df.empty else []
    anti_rel = _unique_preserve(anti_df["r1"].tolist()) if not anti_df.empty else []
    overlap = sorted(set(sym_rel).intersection(anti_rel))
    anti_rel = [r for r in anti_rel if r not in set(sym_rel)]

    inv_rel = []
    if not inv_df.empty:
        inv_rel = _unique_preserve(inv_df["r1"].tolist() + inv_df["r2"].tolist())

    comp_rel = []
    if not comp_df.empty:
        comp_rel = _unique_preserve(comp_df["r1"].tolist() + comp_df["r2"].tolist() + comp_df["r3"].tolist())

    return {
        "symmetric": sym_rel,
        "anti_symmetric": anti_rel,
        "inverse": inv_rel,
        "composition": comp_rel,
    }, overlap


def build_square_adjacency_matrix(
    df_pairs: pd.DataFrame,
    *,
    min_support: int,
    extra_relations: Optional[list[str]] = None,
) -> tuple[list[str], np.ndarray]:
    """Build square adjacency from filtered pair counts with support thresholding."""
    edge_sum = df_pairs.groupby(["r1", "r2"], as_index=False)["total"].sum()
    edge_sum = edge_sum[edge_sum["total"] >= int(min_support)].copy()

    nodes = set()
    if not edge_sum.empty:
        nodes.update(edge_sum["r1"].tolist())
        nodes.update(edge_sum["r2"].tolist())
    if extra_relations:
        nodes.update(extra_relations)
    relations_universe = sorted(nodes)

    n = len(relations_universe)
    A = np.zeros((n, n), dtype=float)
    rel_to_idx = {r: i for i, r in enumerate(relations_universe)}
    for row in edge_sum.itertuples(index=False):
        i = rel_to_idx[row.r1]
        j = rel_to_idx[row.r2]
        A[i, j] = float(row.total)
    return relations_universe, A


def run_phase3_allocation(
    pattern_groups: dict[str, list[str]],
    eta_per_group: dict[str, int],
    relations_universe: list[str],
    adjacency: np.ndarray,
    *,
    matrix_mode: str,
    temperature: float,
    epsilon: float,
    integerize: bool,
) -> tuple[np.ndarray, dict]:
    """Run allocation over all non-empty groups and return selected W plus results."""
    def _row_normalize(X: np.ndarray) -> np.ndarray:
        s = X.sum(axis=1, keepdims=True)
        return np.divide(X, s, out=np.zeros_like(X), where=s > 0)

    def _col_normalize(X: np.ndarray) -> np.ndarray:
        s = X.sum(axis=0, keepdims=True)
        return np.divide(X, s, out=np.zeros_like(X), where=s > 0)

    if matrix_mode == "adjacency_support":
        W = adjacency.copy()
    elif matrix_mode == "adjacency_log1p":
        W = np.log1p(adjacency)
    elif matrix_mode == "two_hop_log1p":
        W = np.log1p(adjacency @ adjacency)
    elif matrix_mode == "log1p_row_norm":
        W = _row_normalize(np.log1p(adjacency))
    elif matrix_mode == "log1p_col_norm":
        W = _col_normalize(np.log1p(adjacency))
    elif matrix_mode == "log1p_balanced_norm":
        W0 = np.log1p(adjacency)
        W = 0.5 * (_row_normalize(W0) + _col_normalize(W0))
    else:
        raise ValueError(f"Unknown matrix_mode: {matrix_mode}")

    non_empty_groups = {k: v for k, v in pattern_groups.items() if len(v) > 0}
    non_empty_eta = {k: int(eta_per_group.get(k, 0)) for k in non_empty_groups}
    if not non_empty_groups:
        return W, {}

    results = allocate_for_patterns(
        W=W,
        relations_universe=relations_universe,
        pattern_groups=non_empty_groups,
        eta_per_group=non_empty_eta,
        temperature=float(temperature),
        epsilon=float(epsilon),
        integerize=bool(integerize),
    )
    return W, results


def _fmt_sci(x: float, digits: int = 4) -> str:
    """Format numbers for readability using scientific notation when needed."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not np.isfinite(v):
        return str(v)
    if v == 0.0:
        return "0"
    if abs(v) < 1e-4 or abs(v) >= 1e6:
        return f"{v:.{digits}e}"
    return f"{v:.{digits}f}"


def _safe_entropy(p: np.ndarray) -> float:
    q = np.asarray(p, dtype=float)
    q = q[q > 0]
    if q.size == 0:
        return 0.0
    return float(-(q * np.log(q)).sum())


def _triples_to_jsonl_text(triples: list[dict]) -> str:
    return "\n".join(json.dumps(tr, ensure_ascii=False) for tr in triples) + ("\n" if triples else "")


class WikidataSparqlTripleSource:
    """Minimal SPARQL-backed triple source for Phase 4 realization."""

    def __init__(
        self,
        mcfg: MongoConfig,
        *,
        endpoint_url: str = "https://query.wikidata.org/sparql",
        user_agent: str = "hpc-kg-balanced-phase4/1.0 (contact: user@example.com)",
        any_fetch: int = 200,
        attach_fetch: int = 200,
        max_v_for_values: int = 30,
        timeout_sec: int = 30,
        retries: int = 3,
        retry_sleep_sec: float = 1.5,
    ):
        self.mcfg = mcfg
        self.endpoint_url = endpoint_url
        self.user_agent = user_agent
        self.any_fetch = max(1, int(any_fetch))
        self.attach_fetch = max(1, int(attach_fetch))
        self.max_v_for_values = max(1, int(max_v_for_values))
        self.timeout_sec = max(5, int(timeout_sec))
        self.retries = max(1, int(retries))
        self.retry_sleep_sec = float(max(0.1, retry_sleep_sec))
        self.max_type_values = 12
        self._count_cache: dict[str, int] = {}
        self._any_cache: dict[tuple[str, int], list[dict]] = {}
        self._class_entity_cache: dict[tuple[str, int], list[str]] = {}

    @staticmethod
    def _qid_only(x: str) -> bool:
        return isinstance(x, str) and len(x) > 1 and x[0] == "Q" and x[1:].isdigit()

    @staticmethod
    def _pid_only(x: str) -> bool:
        return isinstance(x, str) and len(x) > 1 and x[0] == "P" and x[1:].isdigit()

    def _run_sparql(self, query: str) -> dict:
        params = urllib.parse.urlencode({"query": query, "format": "json"})
        url = f"{self.endpoint_url}?{params}"
        headers = {
            "Accept": "application/sparql-results+json",
            "User-Agent": self.user_agent,
        }
        last_err: Optional[Exception] = None
        for k in range(self.retries):
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    raw = resp.read().decode("utf-8")
                return json.loads(raw)
            except Exception as e:
                last_err = e
                if k + 1 < self.retries:
                    time.sleep(self.retry_sleep_sec)
        raise RuntimeError(f"SPARQL request failed after {self.retries} retries: {last_err}")

    def _extract_triples(self, result: dict, pid: str) -> list[dict]:
        out: list[dict] = []
        bindings = result.get("results", {}).get("bindings", [])
        for b in bindings:
            h_uri = b.get("h", {}).get("value", "")
            t_uri = b.get("t", {}).get("value", "")
            h = h_uri.rsplit("/", 1)[-1]
            t = t_uri.rsplit("/", 1)[-1]
            if self._qid_only(h) and self._qid_only(t):
                out.append(
                    {
                        self.mcfg.field_head: h,
                        self.mcfg.field_rel: pid,
                        self.mcfg.field_tail: t,
                    }
                )
        return out

    def count_triples(self, pid: str) -> int:
        if pid in self._count_cache:
            return self._count_cache[pid]
        if not self._pid_only(pid):
            self._count_cache[pid] = 0
            return 0
        # Cheap feasibility proxy: presence check via small sample.
        sample = self.sample_triples_any(pid, 1)
        n = 1 if sample else 0
        self._count_cache[pid] = n
        return n

    def sample_triples_any(self, pid: str, n: int) -> list[dict]:
        if n <= 0 or not self._pid_only(pid):
            return []
        n_eff = min(int(n), self.any_fetch)
        ck = (pid, n_eff)
        if ck in self._any_cache:
            cached = self._any_cache[ck]
            if len(cached) <= n_eff:
                return list(cached)
            return random.sample(cached, k=n_eff)

        query = f"""
        SELECT ?h ?t WHERE {{
          ?h wdt:{pid} ?t .
        }}
        LIMIT {n_eff}
        """
        try:
            res = self._run_sparql(query)
            triples = self._extract_triples(res, pid)
        except Exception:
            triples = []
        self._any_cache[ck] = triples
        return triples

    def sample_triples_attach_to_v(self, pid: str, v: set[str], n: int) -> list[dict]:
        if n <= 0 or not v or not self._pid_only(pid):
            return []
        v_list = [x for x in sorted(v)[: self.max_v_for_values] if self._qid_only(x)]
        if not v_list:
            return []
        values = " ".join(f"wd:{q}" for q in v_list)
        n_eff = min(int(n), self.attach_fetch)
        query = f"""
        SELECT ?h ?t WHERE {{
          ?h wdt:{pid} ?t .
          FILTER(?h IN ({values}) || ?t IN ({values}))
        }}
        LIMIT {n_eff}
        """
        try:
            res = self._run_sparql(query)
            triples = self._extract_triples(res, pid)
        except Exception:
            triples = []
        return triples

    def sample_triples_attach_to_v_typed(
        self,
        pid: str,
        v: set[str],
        n: int,
        subject_types: list[str],
        object_types: list[str],
    ) -> list[dict]:
        """Attach-to-V sampling with optional type filters on subject/object."""
        if n <= 0 or not v or not self._pid_only(pid):
            return []
        v_list = [x for x in sorted(v)[: self.max_v_for_values] if self._qid_only(x)]
        if not v_list:
            return []
        subj = [x for x in subject_types[: self.max_type_values] if self._qid_only(x)]
        obj = [x for x in object_types[: self.max_type_values] if self._qid_only(x)]

        values_v = " ".join(f"wd:{q}" for q in v_list)
        n_eff = min(int(n), self.attach_fetch)

        typed_blocks = []
        if subj:
            values_subj = " ".join(f"wd:{q}" for q in subj)
            typed_blocks.append(
                f"""
                VALUES ?scls {{ {values_subj} }}
                FILTER EXISTS {{ ?h wdt:P31/wdt:P279* ?scls . }}
                """
            )
        if obj:
            values_obj = " ".join(f"wd:{q}" for q in obj)
            typed_blocks.append(
                f"""
                VALUES ?ocls {{ {values_obj} }}
                FILTER EXISTS {{ ?t wdt:P31/wdt:P279* ?ocls . }}
                """
            )
        typed_filter = "\n".join(typed_blocks)
        query = f"""
        SELECT ?h ?t WHERE {{
          ?h wdt:{pid} ?t .
          FILTER(?h IN ({values_v}) || ?t IN ({values_v}))
          {typed_filter}
        }}
        LIMIT {n_eff}
        """
        try:
            res = self._run_sparql(query)
            triples = self._extract_triples(res, pid)
        except Exception:
            triples = []
        return triples

    def fetch_entities_of_class(self, class_qid: str, limit: int = 100) -> list[str]:
        """Fetch entities that are instance/subclass of a class."""
        if limit <= 0 or not self._qid_only(class_qid):
            return []
        k = (class_qid, int(limit))
        if k in self._class_entity_cache:
            return list(self._class_entity_cache[k])
        query = f"""
        SELECT ?e WHERE {{
          ?e wdt:P31/wdt:P279* wd:{class_qid} .
        }}
        LIMIT {int(limit)}
        """
        try:
            res = self._run_sparql(query)
            entities: list[str] = []
            for b in res.get("results", {}).get("bindings", []):
                e_uri = b.get("e", {}).get("value", "")
                q = e_uri.rsplit("/", 1)[-1]
                if self._qid_only(q):
                    entities.append(q)
        except Exception:
            entities = []
        self._class_entity_cache[k] = entities
        return entities


def main() -> None:
    """Run Streamlit UI for phase-1 and phase-2 pattern analysis.

    Interactive filters control support and confidence thresholds, and outputs
    ranked candidate tables for symmetric, anti-symmetric, inverse, and composition patterns.

    Design notes:
    - Phase 1 and Phase 2 are intentionally separated in the UI because they are
      computed from different datasets and denominators.
    - Wilson filtering is optional and composition-only: it refines sampled
      composition confidence by requiring a conservative lower-confidence bound.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input",
        required=False,
        default="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced/data/archived/hop_support_v2_w_failed_statuses.wikibase_item_only_before_target_enrichment.jsonl",
    )
    ap.add_argument(
        "--composition_input",
        required=False,
        default="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced/data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl",
    )
    ap.add_argument("--include_non_success_docs", action="store_true")
    args = ap.parse_args()
    properties_json_path = str((Path(__file__).resolve().parents[2] / "data/raw/wikidata_ontology.properties.json"))
    rel_dom_rng_class = load_property_domain_range_class_map(properties_json_path)
    rel_dom_rng_types = load_property_domain_range_types_map(properties_json_path)

    st.set_page_config(page_title="Hop Pattern Analysis - Phase 1 + 2", layout="wide")
    st.title("Hop Pattern Analysis - Phase 1 + 2")

    only_success = not args.include_non_success_docs
    df = load_pair_counts(args.input, only_success=only_success)

    status_counts = (
        pd.Series(df.attrs.get("doc_status", {}), name="count")
        .rename_axis("status")
        .reset_index()
        .sort_values("count", ascending=False)
    )
    top_left, top_mid, top_right = st.columns([1, 1, 2])
    with top_left:
        st.subheader("Input doc statuses")
        st.dataframe(status_counts, use_container_width=True, hide_index=True)
    with top_mid:
        st.subheader("Load summary")
        st.metric("Unique (r1,r2)", int(len(df)))
        st.metric("Unique r1", int(df["r1"].nunique()) if not df.empty else 0)
        st.metric("Unique r2", int(df["r2"].nunique()) if not df.empty else 0)
        st.metric("Bad support rows skipped", int(df.attrs.get("bad_rows", 0)))
    with top_right:
        st.markdown(
            "### Patterns used (Phase 1)\n\n"
            "**Symmetric** (`r1 = r2 = r`)\n"
            "- Formula: `conf = loop / total`\n"
            "- Meaning: higher means `r` behaves more symmetric.\n\n"
            "**Anti-symmetric** (`r1 = r2 = r`)\n"
            "- Formula: `conf = nonloop / total = 1 - (loop / total)`\n"
            "- Meaning: higher means `r` behaves more one-way.\n\n"
            "**Inverse** (`r1 != r2`)\n"
            "- Forward: `conf(r1,r2) = loop(r1,r2) / total(r1,r2)`\n"
            "- Reverse: `conf(r2,r1) = loop(r2,r1) / total(r2,r1)`\n"
            "- Bidirectional (strict): `min(conf(r1,r2), conf(r2,r1))`\n"
            "- Meaning: true inverse candidates need both directions high.\n\n"
            "**Composition** (`r1 -> r2` implies `r3`)\n"
            "- Formula used in phase 2 data: `conf_sample = chain_pairs_with_shortcut / chain_pairs_examined`\n"
            "- Meaning: among sampled chain pairs from `(r1,r2)`, how often direct shortcut `r3` exists."
        )

    if df.empty:
        st.warning("No pair counts loaded. Check file path or status filter.")
        return

    st.sidebar.header("Filters")
    min_total = int(st.sidebar.number_input("Min total support", min_value=0, value=8, step=1))
    max_total = int(st.sidebar.number_input("Max total support", min_value=0, value=int(df["total"].max()), step=1))
    min_conf = float(st.sidebar.slider("Min confidence", 0.0, 1.0, 0.5, 0.01))
    min_reverse_conf = float(st.sidebar.slider("Min reverse confidence (inverse only)", 0.0, 1.0, 0.0, 0.01))
    topn = int(st.sidebar.slider("Top-N rows", 5, 200, 30, 5))
    sort_by = st.sidebar.selectbox(
        "Sort inverse by",
        options=["conf_loop", "bidirectional_conf_min", "bidirectional_conf_mean", "total"],
        index=1,
    )
    relation_query = st.sidebar.text_input("Focus relation PID (optional)", "").strip()

    if max_total < min_total:
        st.sidebar.error("Max total support must be >= min total support.")
        return

    df_f = df[(df["total"] >= min_total) & (df["total"] <= max_total)].copy()
    if relation_query:
        df_f = df_f[(df_f["r1"] == relation_query) | (df_f["r2"] == relation_query)]

    st.subheader("Filtered universe")
    st.write(f"Kept **{len(df_f)}** / {len(df)} unique (r1,r2) pairs")
    if df_f.empty:
        st.warning("No rows after filters.")
        return

    # Symmetric + anti-symmetric (r1 == r2)
    sym = df_f[df_f["r1"] == df_f["r2"]].copy()
    sym = sym[sym["conf_loop"] >= min_conf]
    sym = sym.sort_values(["conf_loop", "total", "r1"], ascending=[False, False, True])
    anti = df_f[df_f["r1"] == df_f["r2"]].copy()
    anti = anti[anti["conf_nonloop"] >= min_conf]
    anti = anti.sort_values(["conf_nonloop", "total", "r1"], ascending=[False, False, True])

    # Inverse (r1 != r2)
    inv = prepare_inverse_table(df_f)
    inv = inv[(inv["conf_loop"] >= min_conf) & (inv["reverse_conf_loop"] >= min_reverse_conf)]
    inv = inv.sort_values([sort_by, "total"], ascending=[False, False])

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Symmetric candidates", int(len(sym)))
    with m2:
        st.metric("Anti-symmetric candidates", int(len(anti)))
    with m3:
        st.metric("Inverse candidates", int(len(inv)))
    with m4:
        st.metric("Median support (filtered)", float(df_f["total"].median()))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"### Symmetric candidates (r1 == r2), top {topn}")
        show_sym = sym[["r1", "loop", "nonloop", "total", "conf_loop", "conf_nonloop"]].head(topn)
        st.dataframe(show_sym, use_container_width=True, hide_index=True)

    with c2:
        st.markdown(f"### Anti-symmetric candidates (r1 == r2), top {topn}")
        show_anti = anti[["r1", "loop", "nonloop", "total", "conf_nonloop", "conf_loop"]].head(topn)
        st.dataframe(show_anti, use_container_width=True, hide_index=True)

    st.markdown(f"### Inverse candidates (r1 != r2), top {topn}")
    show_inv = inv[
        [
            "r1",
            "r2",
            "loop",
            "nonloop",
            "total",
            "conf_loop",
            "reverse_conf_loop",
            "bidirectional_conf_min",
            "bidirectional_conf_mean",
            "reverse_total",
        ]
    ].head(topn)
    st.dataframe(show_inv, use_container_width=True, hide_index=True)

    st.caption(
        "Interpretation: high `conf_loop` supports symmetric/inverse behavior; high `conf_nonloop` supports anti-symmetric behavior."
    )

    st.divider()
    st.header("Phase 2 - Composition (from verified compact JSONL)")
    st.caption(f"Data source: `{args.composition_input}`")

    comp_df = load_composition_verified_compact(args.composition_input, only_success=only_success)
    if comp_df.empty:
        st.warning("No composition rows loaded. Check composition file path or success filter.")
        return

    comp_left, comp_mid, comp_right = st.columns([1, 1, 2])
    with comp_left:
        st.subheader("Composition input statuses")
        comp_status = (
            pd.Series(comp_df.attrs.get("input_status_counts", {}), name="count")
            .rename_axis("input_status")
            .reset_index()
            .sort_values("count", ascending=False)
        )
        st.dataframe(comp_status, use_container_width=True, hide_index=True)
    with comp_mid:
        st.subheader("Composition load summary")
        st.metric("Rows (r1,r2,r3)", int(len(comp_df)))
        st.metric("Unique (r1,r2)", int(comp_df[["r1", "r2"]].drop_duplicates().shape[0]))
        st.metric("Unique r3 targets", int(comp_df["r3"].nunique()))
        st.metric("Bad rows skipped", int(comp_df.attrs.get("bad_rows", 0)))
    with comp_right:
        st.markdown(
            "**Composition formulas shown here**\n\n"
            "- `shortcuts = chain_pairs_with_shortcut`\n"
            "- `examined = chain_pairs_examined`\n"
            "- `conf_composition_sample = shortcuts / examined`\n\n"
            "This is sample-based confidence from the verifier output."
        )

    st.subheader("Composition controls")
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        comp_min_support = int(st.number_input("Min (r1,r2) support", min_value=0, value=8, step=1))
    with f2:
        comp_min_examined = int(st.number_input("Min chain pairs examined", min_value=0, value=50, step=1))
    with f3:
        comp_min_conf = float(st.slider("Min composition confidence", 0.0, 1.0, 0.05, 0.01))
    with f4:
        comp_min_shortcuts = int(st.number_input("Min shortcut hits", min_value=0, value=1, step=1))
    with f5:
        use_wilson = bool(st.checkbox("Use Wilson filter", value=True))

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        comp_topn = int(st.slider("Composition Top-N rows", 5, 500, 50, 5))
    with g2:
        comp_sort_by = st.selectbox(
            "Sort composition by",
            options=[
                "conf_composition_sample",
                "wilson_lower_bound",
                "chain_pairs_with_shortcut",
                "chain_pairs_examined",
                "base_support",
            ],
            index=0,
        )
    with g3:
        comp_focus_pid = st.text_input("Focus PID for composition (optional)", "").strip()
    with g4:
        wilson_conf_level = st.selectbox(
            "Wilson confidence level",
            options=[0.80, 0.90, 0.95, 0.99],
            index=2,
            help="Used only when Wilson filter is enabled.",
        )

    z_by_level = {0.80: 1.2815515655446004, 0.90: 1.6448536269514722, 0.95: 1.959963984540054, 0.99: 2.5758293035489004}
    z_value = z_by_level[float(wilson_conf_level)]

    comp_f = comp_df[
        (comp_df["base_support"] >= comp_min_support)
        & (comp_df["chain_pairs_examined"] >= comp_min_examined)
        & (comp_df["chain_pairs_with_shortcut"] >= comp_min_shortcuts)
        & (comp_df["conf_composition_sample"] >= comp_min_conf)
    ].copy()

    if not comp_f.empty:
        bounds = comp_f.apply(
            lambda r: wilson_interval(
                int(r["chain_pairs_with_shortcut"]),
                int(r["chain_pairs_examined"]),
                z_value,
            ),
            axis=1,
            result_type="expand",
        )
        bounds.columns = ["wilson_lower_bound", "wilson_upper_bound"]
        comp_f = pd.concat([comp_f, bounds], axis=1)
    else:
        comp_f["wilson_lower_bound"] = pd.Series(dtype=float)
        comp_f["wilson_upper_bound"] = pd.Series(dtype=float)

    if use_wilson:
        comp_f = comp_f[comp_f["wilson_lower_bound"] >= comp_min_conf]

    if comp_focus_pid:
        comp_f = comp_f[
            (comp_f["r1"] == comp_focus_pid) | (comp_f["r2"] == comp_focus_pid) | (comp_f["r3"] == comp_focus_pid)
        ]

    comp_f = classify_composition_patterns(comp_f)
    comp_f = comp_f.sort_values([comp_sort_by, "chain_pairs_with_shortcut"], ascending=[False, False])
    st.write(f"Kept **{len(comp_f)}** / {len(comp_df)} composition triples")
    if comp_f.empty:
        st.warning("No composition triples after filters.")
    else:
        cm1, cm2, cm3, cm4 = st.columns(4)
        with cm1:
            st.metric("Unique r1", int(comp_f["r1"].nunique()))
        with cm2:
            st.metric("Unique r2", int(comp_f["r2"].nunique()))
        with cm3:
            st.metric("Unique r3", int(comp_f["r3"].nunique()))
        with cm4:
            if use_wilson:
                st.metric("Median Wilson lower", float(comp_f["wilson_lower_bound"].median()))
            else:
                st.metric("Median conf", float(comp_f["conf_composition_sample"].median()))

        class_counts = (
            comp_f["composition_class"].value_counts().rename_axis("composition_class").reset_index(name="count")
        )
        st.markdown("### Composition class counts")
        st.dataframe(class_counts, use_container_width=True, hide_index=True)

        st.markdown(f"### Top composition triples (r1, r2, r3), top {comp_topn}")
        st.dataframe(
            comp_f[
                [
                    "r1",
                    "r2",
                    "r3",
                    "base_support",
                    "chain_pairs_examined",
                    "chain_pairs_with_shortcut",
                    "chain_pairs_missing_shortcut",
                    "conf_composition_sample",
                    "wilson_lower_bound",
                    "wilson_upper_bound",
                    "composition_class",
                    "sample_confidence_reported",
                    "target_count",
                    "targets_truncated",
                ]
            ].head(comp_topn),
            use_container_width=True,
            hide_index=True,
        )

        best_per_pair = (
            comp_f.sort_values(["conf_composition_sample", "chain_pairs_with_shortcut"], ascending=[False, False])
            .groupby(["r1", "r2"], as_index=False)
            .first()
            .sort_values(["conf_composition_sample", "chain_pairs_with_shortcut"], ascending=[False, False])
        )
        st.markdown(f"### Best target r3 per (r1, r2), top {comp_topn}")
        st.dataframe(
            best_per_pair[
                [
                    "r1",
                    "r2",
                    "r3",
                    "base_support",
                    "chain_pairs_examined",
                    "chain_pairs_with_shortcut",
                    "conf_composition_sample",
                    "wilson_lower_bound",
                    "wilson_upper_bound",
                    "composition_class",
                ]
            ].head(comp_topn),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.header("Phase 3 - Bidirectional Triple Allocation")
    st.caption(
        "Groups are derived from the current Phase 1/2 filtered outputs. "
        "Phase 3 allocates over unique relation IDs (relation-level), not over candidate rows. "
        "Matrix is built from filtered hop-support pairs."
    )

    linked_min_support = int(max(min_total, comp_min_support))
    use_custom_matrix_min_support = bool(
        st.checkbox(
            "Use custom matrix min support (Phase 3)",
            value=True,
            help="By default, Phase 3 follows max(Phase1 min total support, Phase2 min (r1,r2) support).",
        )
    )
    if use_custom_matrix_min_support:
        alloc_min_support = int(
            st.number_input(
                "Matrix min support (custom)",
                min_value=0,
                value=linked_min_support,
                step=1,
                help="Pairs with support below this threshold are set to zero in adjacency.",
            )
        )
    else:
        alloc_min_support = linked_min_support
        st.caption(
            f"Matrix min support is auto-linked to Phase 1/2 filters: max({min_total}, {comp_min_support}) = {alloc_min_support}."
        )

    a1, a2, a3 = st.columns(3)
    with a1:
        st.metric("Matrix min support", alloc_min_support)
    with a2:
        matrix_mode = st.selectbox(
            "Weight matrix mode",
            options=[
                "log1p_balanced_norm",
                "log1p_row_norm",
                "log1p_col_norm",
                "adjacency_log1p",
                "adjacency_support",
                "two_hop_log1p",
            ],
            index=0,
            help="Recommended default is log1p_balanced_norm: preserves log-support weighting while reducing hub dominance.",
        )
    with a3:
        temperature = float(st.slider("Softmax temperature", 0.1, 5.0, 1.0, 0.1))
    epsilon = float(st.number_input("Epsilon smoothing", min_value=0.0, value=0.0, step=0.01))

    b1, b2, b3, b4, b5 = st.columns(5)
    with b1:
        eta_sym = int(st.number_input("Eta symmetric", min_value=0, value=1000, step=50))
    with b2:
        eta_anti = int(st.number_input("Eta anti-symmetric", min_value=0, value=1000, step=50))
    with b3:
        eta_inv = int(st.number_input("Eta inverse", min_value=0, value=1000, step=50))
    with b4:
        eta_comp = int(st.number_input("Eta composition", min_value=0, value=1000, step=50))
    with b5:
        integerize = bool(st.checkbox("Integer allocations", value=True))

    pattern_groups, overlap = build_pattern_groups(sym, anti, inv, comp_f)
    if overlap:
        st.warning(
            "Some relations appeared in both symmetric and anti-symmetric candidates; "
            "they were kept in symmetric and removed from anti-symmetric."
        )

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Group size: symmetric", len(pattern_groups["symmetric"]))
    with m2:
        st.metric("Group size: anti-symmetric", len(pattern_groups["anti_symmetric"]))
    with m3:
        st.metric("Group size: inverse", len(pattern_groups["inverse"]))
    with m4:
        st.metric("Group size: composition", len(pattern_groups["composition"]))
    st.caption(
        "Group size counts unique relations in each pattern group. "
        "These are expected to differ from candidate-row counts in Phase 1/2."
    )

    group_preview_rows = []
    for pat, rels in pattern_groups.items():
        group_preview_rows.append({"pattern": pat, "size": len(rels), "relations": ", ".join(rels[:20])})
    st.dataframe(pd.DataFrame(group_preview_rows), use_container_width=True, hide_index=True)

    eta_per_group = {
        "symmetric": eta_sym,
        "anti_symmetric": eta_anti,
        "inverse": eta_inv,
        "composition": eta_comp,
    }
    all_group_relations = _unique_preserve(
        pattern_groups["symmetric"]
        + pattern_groups["anti_symmetric"]
        + pattern_groups["inverse"]
        + pattern_groups["composition"]
    )
    relations_universe, adjacency = build_square_adjacency_matrix(
        df_f,
        min_support=alloc_min_support,
        extra_relations=all_group_relations,
    )

    st.caption(
        f"Adjacency matrix shape: {adjacency.shape}. Universe contains all filtered matrix nodes and all group relations."
    )

    if len(relations_universe) == 0:
        st.warning("No relations available for matrix/allocation under current filters.")
        return

    W, alloc_results = run_phase3_allocation(
        pattern_groups=pattern_groups,
        eta_per_group=eta_per_group,
        relations_universe=relations_universe,
        adjacency=adjacency,
        matrix_mode=matrix_mode,
        temperature=temperature,
        epsilon=epsilon,
        integerize=integerize,
    )

    matrix_preview_n = min(20, len(relations_universe))
    matrix_preview = pd.DataFrame(
        W[:matrix_preview_n, :matrix_preview_n],
        index=relations_universe[:matrix_preview_n],
        columns=relations_universe[:matrix_preview_n],
    )
    st.markdown(f"### Weight matrix preview ({matrix_preview_n}x{matrix_preview_n})")
    st.dataframe(matrix_preview, use_container_width=True)

    if not alloc_results:
        st.warning("No non-empty groups to allocate.")
        return

    rows = []
    diag_rows = []
    for pat, res in alloc_results.items():
        idx = [relations_universe.index(r) for r in res.relations]
        Wc = W[np.ix_(idx, idx)]
        row_sum = Wc.sum(axis=1)
        col_sum = Wc.sum(axis=0)
        nonzero_cells = int(np.count_nonzero(Wc))
        total_cells = int(Wc.size) if Wc.size > 0 else 1
        entropy = _safe_entropy(res.p_avg)
        eff_rel = float(np.exp(entropy)) if entropy > 0 else 1.0
        diag_rows.append(
            {
                "pattern": pat,
                "group_size": len(res.relations),
                "eta_total": int(res.eta_total),
                "nonzero_eta_integer": int(np.count_nonzero(res.eta_integer)),
                "max_eta_integer": int(res.eta_integer.max()) if len(res.eta_integer) else 0,
                "min_eta_integer": int(res.eta_integer.min()) if len(res.eta_integer) else 0,
                "p_avg_max": float(res.p_avg.max()) if len(res.p_avg) else 0.0,
                "p_avg_min": float(res.p_avg.min()) if len(res.p_avg) else 0.0,
                "effective_relations_exp_entropy": eff_rel,
                "Wc_density": float(nonzero_cells / total_cells),
                "Wc_zero_rows": int(np.count_nonzero(row_sum == 0)),
                "Wc_zero_cols": int(np.count_nonzero(col_sum == 0)),
            }
        )
        for i, rel in enumerate(res.relations):
            rows.append(
                {
                    "pattern": pat,
                    "relation": rel,
                    "eta_total": int(res.eta_total),
                    "forward_score": float(res.forward_scores[i]),
                    "backward_score": float(res.backward_scores[i]),
                    "p_forward": float(res.p_forward[i]),
                    "p_backward": float(res.p_backward[i]),
                    "p_avg": float(res.p_avg[i]),
                    "eta_expected": float(res.eta_expected[i]),
                    "eta_integer": int(res.eta_integer[i]),
                }
            )
    alloc_df = pd.DataFrame(rows).sort_values(["pattern", "eta_integer", "eta_expected"], ascending=[True, False, False])
    alloc_df["relation_dom_rng_class"] = alloc_df["relation"].map(lambda r: rel_dom_rng_class.get(str(r), "UNKNOWN"))
    diag_df = pd.DataFrame(diag_rows).sort_values(["pattern"])
    st.markdown("### Allocation diagnostics")
    st.dataframe(diag_df, use_container_width=True, hide_index=True)

    show_nonzero_only = bool(
        st.checkbox(
            "Show only rows with eta_integer > 0",
            value=True,
            help="If most rows are zero, this view is easier to inspect.",
        )
    )
    view_df = alloc_df[alloc_df["eta_integer"] > 0].copy() if show_nonzero_only else alloc_df.copy()
    st.caption(f"Displaying {len(view_df)} rows out of {len(alloc_df)} total allocation rows.")
    st.markdown("### Allocation results")
    alloc_display = view_df.copy()
    for col in ["forward_score", "backward_score", "p_forward", "p_backward", "p_avg", "eta_expected"]:
        alloc_display[col] = alloc_display[col].map(lambda v: _fmt_sci(v, digits=6))
    st.dataframe(alloc_display, use_container_width=True, hide_index=True)

    result_payload = {
        "config": {
            "min_total": min_total,
            "max_total": max_total,
            "min_conf": min_conf,
            "min_reverse_conf": min_reverse_conf,
            "comp_min_support": comp_min_support,
            "matrix_min_support": alloc_min_support,
            "matrix_mode": matrix_mode,
            "temperature": temperature,
            "epsilon": epsilon,
            "integerize": integerize,
        },
        "eta_per_group": eta_per_group,
        "pattern_groups": pattern_groups,
        "relations_universe": relations_universe,
        "allocations": alloc_df.to_dict(orient="records"),
    }
    result_json = json.dumps(result_payload, indent=2)
    st.download_button(
        label="Download allocation JSON",
        data=result_json,
        file_name="bidirectional_allocation_results.json",
        mime="application/json",
    )
    st.download_button(
        label="Download allocation CSV",
        data=alloc_df.to_csv(index=False),
        file_name="bidirectional_allocation_results.csv",
        mime="text/csv",
    )

    st.divider()
    st.header("Phase 4 - Connected Triple Realization")
    st.caption(
        "Realize Phase 3 relation quotas (eta_integer) into a connected entity-level triple graph. "
        "Every added triple must attach to the growing entity component."
    )
    st.info(
        "Phase 4 automatically uses the current Phase 3 allocation table as quota input. "
        "You only need to provide where raw triples come from (JSONL or MongoDB)."
    )

    source_mode = st.radio(
        "Triple source mode",
        options=["JSONL", "MongoDB", "Wikidata SPARQL"],
        index=0,
        horizontal=True,
        help="Choose where Phase 4 fetches raw (h,r,t) triples from.",
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        p4_attempts = int(st.slider("Attempts", 1, 50, 10, 1))
    with c2:
        p4_rcl_size = int(st.slider("RCL size", 1, 50, 10, 1))
    with c3:
        p4_anchor_fraction = float(st.slider("Anchor fraction", 0.0, 1.0, 0.2, 0.05))
    with c4:
        p4_overlap_probe = int(st.number_input("Overlap probe triples", min_value=1, value=200, step=10))

    d1, d2, d3, d4 = st.columns(4)
    with d1:
        p4_strict = bool(st.checkbox("Strict quotas", value=False))
    with d2:
        p4_seed = int(st.number_input("Random seed", min_value=0, value=42, step=1))
    with d3:
        p4_field_h = st.text_input("Head field", value="h")
    with d4:
        p4_field_r = st.text_input("Relation field", value="r")
    p4_field_t = st.text_input("Tail field", value="t")
    ck1, ck2, ck3 = st.columns(3)
    with ck1:
        p4_checkpoint_enabled = bool(st.checkbox("Enable checkpointing", value=True))
    with ck2:
        p4_resume_checkpoint = bool(st.checkbox("Resume from checkpoint", value=True))
    with ck3:
        p4_checkpoint_every = int(st.number_input("Checkpoint every N relations", min_value=1, value=1, step=1))
    p4_checkpoint_path = st.text_input(
        "Checkpoint file path",
        value="data/processed/phase4_connected_realization.checkpoint.json",
        help="Phase 4 writes progress here and can resume later.",
    ).strip()

    triples_jsonl_path = ""
    uploaded_triples_file = None
    mongo_uri = "mongodb://localhost:27017"
    mongo_db = "wikidata_ontology"
    mongo_collection = "triplets"
    sparql_endpoint = "https://query.wikidata.org/sparql"
    sparql_user_agent = "hpc-kg-balanced-phase4/1.0 (contact: omar@gmail.com)"
    sparql_any_fetch = 200
    sparql_attach_fetch = 200
    sparql_max_v = 30
    sparql_timeout = 30
    sparql_retries = 3
    use_backbone_seed = True
    backbone_top_k = 20
    backbone_entities_per_class = 80
    backbone_max_seed_entities = 1000
    use_controlled_relaxation = True
    max_type_values = 12

    if source_mode == "JSONL":
        triples_jsonl_path = st.text_input(
            "Triples JSONL path",
            value="",
            help="One JSON triple per line. Must include configured head/relation/tail fields.",
        ).strip()

        if triples_jsonl_path:
            if os.path.exists(triples_jsonl_path):
                st.success(f"JSONL path found: {triples_jsonl_path}")
            else:
                st.warning(f"JSONL path not found: {triples_jsonl_path}")

        uploaded_triples_file = st.file_uploader(
            "Or upload triples JSONL (optional)",
            type=["jsonl"],
            help="If uploaded, this file is used for Phase 4 and overrides the path above.",
        )
    elif source_mode == "MongoDB":
        m1, m2, m3 = st.columns(3)
        with m1:
            mongo_uri = st.text_input("Mongo URI", value="mongodb://localhost:27017").strip()
        with m2:
            mongo_db = st.text_input("Mongo DB", value="wikidata_ontology").strip()
        with m3:
            mongo_collection = st.text_input("Mongo collection", value="triplets").strip()
    else:
        s1, s2 = st.columns(2)
        with s1:
            sparql_endpoint = st.text_input("SPARQL endpoint", value="https://query.wikidata.org/sparql").strip()
        with s2:
            sparql_user_agent = st.text_input(
                "SPARQL User-Agent",
                value="hpc-kg-balanced-phase4/1.0 (contact: user@example.com)",
                help="Wikidata requires a descriptive User-Agent with contact info.",
            ).strip()
        s3, s4, s5, s6 = st.columns(4)
        with s3:
            sparql_any_fetch = int(st.number_input("Any fetch limit", min_value=10, value=200, step=10))
        with s4:
            sparql_attach_fetch = int(st.number_input("Attach fetch limit", min_value=10, value=200, step=10))
        with s5:
            sparql_max_v = int(st.number_input("Max V in VALUES", min_value=5, value=30, step=5))
        with s6:
            sparql_timeout = int(st.number_input("SPARQL timeout (sec)", min_value=5, value=30, step=5))
        sparql_retries = int(st.number_input("SPARQL retries", min_value=1, value=3, step=1))
        b1, b2, b3 = st.columns(3)
        with b1:
            use_backbone_seed = bool(
                st.checkbox(
                    "Use typed backbone seeding (Phase 1)",
                    value=True,
                    help="Seed entity set V from top domain/range classes before relation filling.",
                )
            )
        with b2:
            backbone_top_k = int(st.number_input("Backbone top-K classes", min_value=1, value=20, step=1))
        with b3:
            backbone_entities_per_class = int(st.number_input("Entities per class", min_value=5, value=80, step=5))
        backbone_max_seed_entities = int(
            st.number_input("Max seed entities", min_value=50, value=1000, step=50)
        )
        r1c, r2c = st.columns(2)
        with r1c:
            use_controlled_relaxation = bool(
                st.checkbox(
                    "Use controlled typed relaxation (Phase 2)",
                    value=True,
                    help="Stages: strict_both -> subject_only -> object_only -> untyped.",
                )
            )
        with r2c:
            max_type_values = int(
                st.number_input(
                    "Max type IDs per side",
                    min_value=1,
                    value=12,
                    step=1,
                    help="Limits VALUES size for subject/object class filters.",
                )
            )

    run_phase4 = st.button("Run Phase 4 Connected Realization", type="primary")
    if run_phase4:
        np.random.seed(p4_seed)
        import random as _random

        _random.seed(p4_seed)

        alloc_rows = alloc_df.to_dict(orient="records")
        quotas, by_pattern_phase4 = build_relation_quotas(alloc_rows)
        if not quotas:
            st.error("No positive eta_integer quotas found in Phase 3 allocation table.")
            return

        mcfg_phase4 = MongoConfig(
            uri=mongo_uri,
            db_name=mongo_db,
            triples_collection=mongo_collection,
            field_head=p4_field_h,
            field_rel=p4_field_r,
            field_tail=p4_field_t,
        )
        rcfg_phase4 = RealizationConfig(
            attempts=p4_attempts,
            rcl_size=p4_rcl_size,
            anchor_fraction=p4_anchor_fraction,
            overlap_probe_triples=p4_overlap_probe,
            strict_quotas=p4_strict,
        )

        try:
            if source_mode == "JSONL":
                effective_jsonl_path = triples_jsonl_path
                if uploaded_triples_file is not None:
                    with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as tmpf:
                        tmpf.write(uploaded_triples_file.getvalue())
                        effective_jsonl_path = tmpf.name
                if not effective_jsonl_path:
                    st.error("Please provide or upload a triples JSONL file for JSONL mode.")
                    return
                if not os.path.exists(effective_jsonl_path):
                    st.error(f"Triples JSONL file not found: {effective_jsonl_path}")
                    return
                triples_by_rel = load_triples_jsonl_index(effective_jsonl_path, mcfg_phase4)
                ts_phase4 = LocalTripleSource(triples_by_rel=triples_by_rel, mcfg=mcfg_phase4)
            elif source_mode == "MongoDB":
                try:
                    from pymongo import MongoClient as _MongoClient
                except ModuleNotFoundError:
                    st.error("pymongo is not installed. Use JSONL mode or install pymongo.")
                    return
                client = _MongoClient(mcfg_phase4.uri)
                coll = client[mcfg_phase4.db_name][mcfg_phase4.triples_collection]
                ts_phase4 = TripleSource(coll, mcfg_phase4, rcfg_phase4)
            else:
                ts_phase4 = WikidataSparqlTripleSource(
                    mcfg_phase4,
                    endpoint_url=sparql_endpoint,
                    user_agent=sparql_user_agent,
                    any_fetch=sparql_any_fetch,
                    attach_fetch=sparql_attach_fetch,
                    max_v_for_values=sparql_max_v,
                    timeout_sec=sparql_timeout,
                    retries=sparql_retries,
                )
                ts_phase4.max_type_values = max_type_values

            total_relations_phase4 = max(1, len([q for q in quotas.values() if q > 0]))
            p4_progress_bar = st.progress(0.0)
            p4_progress_text = st.empty()
            p4_progress_text.info("Phase 4 started...")
            initial_entities_phase4: list[str] = []

            if source_mode == "Wikidata SPARQL" and use_backbone_seed:
                class_scores: dict[str, int] = defaultdict(int)
                for rel, q in quotas.items():
                    if q <= 0:
                        continue
                    types = rel_dom_rng_types.get(rel, {})
                    for c in types.get("subject", []):
                        class_scores[c] += int(q)
                    for c in types.get("object", []):
                        class_scores[c] += int(q)
                ranked_classes = sorted(class_scores.items(), key=lambda kv: kv[1], reverse=True)
                selected_classes = [c for c, _ in ranked_classes[: max(1, backbone_top_k)]]
                if selected_classes:
                    p4_progress_text.info(
                        f"Phase 4 backbone seeding: fetching entities for {len(selected_classes)} classes."
                    )
                seed_entities: list[str] = []
                for i, c in enumerate(selected_classes, start=1):
                    ents = ts_phase4.fetch_entities_of_class(c, limit=backbone_entities_per_class)
                    if ents:
                        seed_entities.extend(ents)
                    frac = i / max(1, len(selected_classes))
                    p4_progress_bar.progress(float(min(0.15, 0.15 * frac)))
                    p4_progress_text.info(
                        f"Backbone class fetch {i}/{len(selected_classes)}: class={c}, "
                        f"seed_entities={len(seed_entities)}"
                    )
                    if len(seed_entities) >= backbone_max_seed_entities:
                        break
                # Preserve order and cap total.
                seen_seed = set()
                initial_entities_phase4 = []
                for e in seed_entities:
                    if e not in seen_seed:
                        seen_seed.add(e)
                        initial_entities_phase4.append(e)
                        if len(initial_entities_phase4) >= backbone_max_seed_entities:
                            break
                p4_progress_text.info(
                    f"Backbone seeding complete: {len(initial_entities_phase4)} seed entities."
                )

            def _phase4_progress(event: str, payload: dict) -> None:
                attempt = int(payload.get("attempt", 1))
                attempts_total = int(payload.get("attempts_total", max(1, p4_attempts)))
                rel_done = int(payload.get("relations_done", 0))
                rel_total = int(payload.get("relations_total", total_relations_phase4))
                rel_frac = (rel_done / max(1, rel_total))
                global_frac = ((attempt - 1) + rel_frac) / max(1, attempts_total)
                global_frac = float(min(1.0, max(0.0, global_frac)))
                if event in {"feasibility_start", "feasibility_progress", "feasibility_done"}:
                    checked = int(payload.get("relations_checked", 0))
                    total = int(payload.get("relations_total", total_relations_phase4))
                    feasible_n = int(payload.get("relations_feasible", 0))
                    frac = checked / max(1, total)
                    # Reserve first 20% of progress bar for feasibility/precheck.
                    p4_progress_bar.progress(float(min(0.2, max(0.0, 0.2 * frac))))
                    if event == "feasibility_start":
                        p4_progress_text.info(f"Precheck started: scanning {total} relations for source availability.")
                    elif event == "feasibility_progress":
                        cur_rel = payload.get("current_relation", "")
                        p4_progress_text.info(
                            f"Precheck {checked}/{total}: feasible={feasible_n}; current relation={cur_rel}"
                        )
                    else:
                        p4_progress_text.info(f"Precheck done: feasible relations {feasible_n}/{total}.")
                    return

                # Attempt phase occupies remaining 80% of the progress bar.
                p4_progress_bar.progress(float(min(1.0, 0.2 + 0.8 * global_frac)))

                if event == "attempt_start":
                    p4_progress_text.info(f"Attempt {attempt}/{attempts_total} started.")
                elif event == "seed_done":
                    rel = payload.get("relation", "")
                    p4_progress_text.info(
                        f"Attempt {attempt}/{attempts_total}: seed relation {rel}; "
                        f"relations done {rel_done}/{rel_total}."
                    )
                elif event == "relation_done":
                    rel = payload.get("relation", "")
                    triples_so_far = int(payload.get("triples_so_far", 0))
                    p4_progress_text.info(
                        f"Attempt {attempt}/{attempts_total}: completed relation {rel}; "
                        f"relations done {rel_done}/{rel_total}; triples {triples_so_far}."
                    )
                elif event == "relation_failed":
                    rel = payload.get("relation", "")
                    p4_progress_text.warning(
                        f"Attempt {attempt}/{attempts_total}: failed while filling relation {rel}; retrying."
                    )
                elif event == "relation_skipped":
                    rel = payload.get("relation", "")
                    p4_progress_text.warning(
                        f"Attempt {attempt}/{attempts_total}: skipped relation {rel} in non-strict mode; continuing."
                    )
                elif event == "attempt_failed":
                    reason = payload.get("reason", "unknown")
                    p4_progress_text.warning(f"Attempt {attempt}/{attempts_total} failed ({reason}).")
                elif event == "relation_stage_start":
                    rel = payload.get("relation", "")
                    stage = payload.get("stage", "")
                    p4_progress_text.info(
                        f"Attempt {attempt}/{attempts_total}: relation {rel} stage={stage}."
                    )
                elif event == "relation_stage_success":
                    rel = payload.get("relation", "")
                    stage = payload.get("stage", "")
                    p4_progress_text.info(
                        f"Attempt {attempt}/{attempts_total}: relation {rel} succeeded at stage={stage}."
                    )
                elif event == "checkpoint_loaded":
                    mode = payload.get("mode", "unknown")
                    p = payload.get("path", "")
                    p4_progress_text.info(f"Checkpoint loaded ({mode}): {p}")
                elif event == "checkpoint_resumed":
                    triples_so_far = int(payload.get("triples_so_far", 0))
                    p4_progress_text.info(f"Resumed from checkpoint: triples so far {triples_so_far}.")
                elif event == "checkpoint_saved":
                    p = payload.get("path", "")
                    triples_so_far = int(payload.get("triples_so_far", 0))
                    p4_progress_text.info(f"Checkpoint saved: {p} (triples={triples_so_far})")
                elif event == "checkpoint_ignored":
                    reason = payload.get("reason", "unknown")
                    p4_progress_text.warning(f"Checkpoint ignored: {reason}.")
                elif event == "success":
                    triples_total = int(payload.get("triples_total", 0))
                    p4_progress_bar.progress(1.0)
                    p4_progress_text.success(
                        f"Phase 4 succeeded on attempt {attempt}/{attempts_total} with {triples_total} triples."
                    )
                elif event == "failed_all_attempts":
                    p4_progress_text.error("Phase 4 failed in all attempts.")
                elif event == "partial_result":
                    triples_total = int(payload.get("triples_total", 0))
                    p4_progress_bar.progress(1.0)
                    p4_progress_text.warning(f"Phase 4 returning partial result: {triples_total} triples.")

            _sig = inspect.signature(realize_connected_graph)
            _kwargs = {
                "quotas": quotas,
                "ts": ts_phase4,
                "mcfg": mcfg_phase4,
                "rcfg": rcfg_phase4,
            }
            if "progress_cb" in _sig.parameters:
                _kwargs["progress_cb"] = _phase4_progress
            else:
                p4_progress_text.warning(
                    "Loaded older realization module without live progress callback support. "
                    "Running without granular progress updates."
                )
            if "initial_entities" in _sig.parameters:
                _kwargs["initial_entities"] = initial_entities_phase4
            elif initial_entities_phase4:
                p4_progress_text.warning(
                    "Loaded older realization module without initial_entities support. "
                    "Phase 4 will fallback to relation-based seeding."
                )
            if "relation_type_constraints" in _sig.parameters:
                _kwargs["relation_type_constraints"] = rel_dom_rng_types
            if "use_controlled_relaxation" in _sig.parameters:
                _kwargs["use_controlled_relaxation"] = bool(
                    source_mode == "Wikidata SPARQL" and use_controlled_relaxation
                )
            if "checkpoint_path" in _sig.parameters and p4_checkpoint_enabled and p4_checkpoint_path:
                _kwargs["checkpoint_path"] = p4_checkpoint_path
            if "resume_from_checkpoint" in _sig.parameters:
                _kwargs["resume_from_checkpoint"] = bool(p4_checkpoint_enabled and p4_resume_checkpoint)
            if "checkpoint_every_relations" in _sig.parameters:
                _kwargs["checkpoint_every_relations"] = int(max(1, p4_checkpoint_every))
            triples_out, achieved = realize_connected_graph(**_kwargs)
            if not triples_out:
                st.error("No triples were realized.")
                return

            target_total = int(sum(quotas.values()))
            achieved_total = int(sum(achieved.values()))
            connected = bool(is_connected_undirected(triples_out, mcfg_phase4))

            r1, r2, r3, r4 = st.columns(4)
            with r1:
                st.metric("Target triples", target_total)
            with r2:
                st.metric("Achieved triples", achieved_total)
            with r3:
                st.metric("Connected", "Yes" if connected else "No")
            with r4:
                st.metric("Relations with quota", len(quotas))

            achieved_df = (
                pd.DataFrame(
                    [{"relation": rel, "target_quota": int(quotas.get(rel, 0)), "achieved": int(achieved.get(rel, 0))}
                     for rel in sorted(quotas)]
                )
                .sort_values(["achieved", "target_quota", "relation"], ascending=[False, False, True])
            )
            st.markdown("### Per-relation realization")
            st.dataframe(achieved_df, use_container_width=True, hide_index=True)

            preview_n = min(200, len(triples_out))
            st.markdown(f"### Triple preview (first {preview_n})")
            st.dataframe(pd.DataFrame(triples_out[:preview_n]), use_container_width=True, hide_index=True)

            viz_edge_cap = min(150, len(triples_out))
            if viz_edge_cap > 0:
                st.markdown(f"### Graph preview (first {viz_edge_cap} edges)")
                dot_lines = ["graph G {"]
                for tr in triples_out[:viz_edge_cap]:
                    h = str(tr.get(p4_field_h, ""))
                    t = str(tr.get(p4_field_t, ""))
                    r = str(tr.get(p4_field_r, ""))
                    if not h or not t:
                        continue
                    dot_lines.append(f'  "{h}" -- "{t}" [label="{r}"];')
                dot_lines.append("}")
                st.graphviz_chart("\n".join(dot_lines))

            metadata_phase4 = {
                "target_total_triples": target_total,
                "achieved_total_triples": achieved_total,
                "relation_quotas": quotas,
                "achieved_per_relation": achieved,
                "pattern_relation_quotas": by_pattern_phase4,
                "connected_undirected": connected,
                "config": {
                    "attempts": p4_attempts,
                    "rcl_size": p4_rcl_size,
                    "anchor_fraction": p4_anchor_fraction,
                    "overlap_probe_triples": p4_overlap_probe,
                    "strict_quotas": p4_strict,
                    "seed": p4_seed,
                    "phase1_backbone_seeding_enabled": bool(source_mode == "Wikidata SPARQL" and use_backbone_seed),
                    "phase1_backbone_top_k": backbone_top_k if source_mode == "Wikidata SPARQL" else None,
                    "phase1_backbone_entities_per_class": backbone_entities_per_class if source_mode == "Wikidata SPARQL" else None,
                    "phase1_backbone_max_seed_entities": backbone_max_seed_entities if source_mode == "Wikidata SPARQL" else None,
                    "phase1_seed_entities_count": len(initial_entities_phase4),
                    "phase2_controlled_relaxation_enabled": bool(
                        source_mode == "Wikidata SPARQL" and use_controlled_relaxation
                    ),
                    "phase2_max_type_values_per_side": max_type_values if source_mode == "Wikidata SPARQL" else None,
                    "checkpoint_enabled": p4_checkpoint_enabled,
                    "checkpoint_path": p4_checkpoint_path if p4_checkpoint_enabled else None,
                    "resume_from_checkpoint": bool(p4_checkpoint_enabled and p4_resume_checkpoint),
                    "checkpoint_every_relations": int(max(1, p4_checkpoint_every)),
                },
                "source": {
                    "mode": "jsonl" if source_mode == "JSONL" else "mongo" if source_mode == "MongoDB" else "wikidata_sparql",
                    "triples_jsonl": triples_jsonl_path if source_mode == "JSONL" else None,
                    "triples_jsonl_uploaded": uploaded_triples_file is not None if source_mode == "JSONL" else False,
                    "mongo_uri": mongo_uri if source_mode == "MongoDB" else None,
                    "mongo_db_name": mongo_db if source_mode == "MongoDB" else None,
                    "mongo_triples_collection": mongo_collection if source_mode == "MongoDB" else None,
                    "sparql_endpoint": sparql_endpoint if source_mode == "Wikidata SPARQL" else None,
                    "sparql_user_agent": sparql_user_agent if source_mode == "Wikidata SPARQL" else None,
                    "sparql_any_fetch": sparql_any_fetch if source_mode == "Wikidata SPARQL" else None,
                    "sparql_attach_fetch": sparql_attach_fetch if source_mode == "Wikidata SPARQL" else None,
                    "sparql_max_v_for_values": sparql_max_v if source_mode == "Wikidata SPARQL" else None,
                    "sparql_timeout_sec": sparql_timeout if source_mode == "Wikidata SPARQL" else None,
                    "sparql_retries": sparql_retries if source_mode == "Wikidata SPARQL" else None,
                    "field_head": p4_field_h,
                    "field_rel": p4_field_r,
                    "field_tail": p4_field_t,
                },
            }
            st.download_button(
                label="Download connected triples JSONL",
                data=_triples_to_jsonl_text(triples_out),
                file_name="connected_allocation_sample.triples.jsonl",
                mime="application/jsonl",
            )
            st.download_button(
                label="Download connected realization metadata JSON",
                data=json.dumps(metadata_phase4, indent=2),
                file_name="connected_allocation_sample.metadata.json",
                mime="application/json",
            )
        except Exception as e:
            st.error(f"Phase 4 failed: {e}")


if __name__ == "__main__":
    main()
