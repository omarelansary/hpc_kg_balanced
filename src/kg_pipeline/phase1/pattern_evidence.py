"""Pure Phase I evidence loaders extracted from the hop-pattern dashboard."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd


def is_pid(x: str) -> bool:
    """Return True when ``x`` is a Wikidata property-id token such as ``P31``."""
    return isinstance(x, str) and len(x) >= 2 and x[0] == "P" and x[1:].isdigit()


def load_pair_counts(jsonl_path: str | Path, only_success: bool = True) -> pd.DataFrame:
    """Load and aggregate hop-support pair counts from JSONL.

    The returned DataFrame has one row per ``(r1, r2)`` with columns
    ``r1``, ``r2``, ``loop``, ``nonloop``, ``total``, ``conf_loop``, and
    ``conf_nonloop``.
    """
    rows: list[dict[str, object]] = []
    doc_status: defaultdict[str, int] = defaultdict(int)
    bad_rows = 0

    with Path(jsonl_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                doc_status["__JSON_DECODE_ERROR__"] += 1
                continue

            status = doc.get("status", "NO_STATUS")
            doc_status[str(status)] += 1
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


def prepare_inverse_table(df_pairs: pd.DataFrame) -> pd.DataFrame:
    """Build inverse-confidence rows with forward and reverse loop scores."""
    base = df_pairs[df_pairs["r1"] != df_pairs["r2"]][
        ["r1", "r2", "loop", "nonloop", "total", "conf_loop"]
    ].copy()
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
    """Return Wilson score interval ``(lower, upper)`` for a binomial proportion."""
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


def load_composition_verified_compact(jsonl_path: str | Path, only_success: bool = True) -> pd.DataFrame:
    """Load flattened composition triples from compact verified composition JSONL."""
    rows: list[dict[str, object]] = []
    input_status_counts: defaultdict[str, int] = defaultdict(int)
    run_status_counts: defaultdict[str, int] = defaultdict(int)
    bad_rows = 0

    with Path(jsonl_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                bad_rows += 1
                continue

            input_status = doc.get("input_status", "NO_STATUS")
            input_status_counts[str(input_status)] += 1
            if only_success and input_status != "SUCCESS":
                continue

            rv = doc.get("rule_verification", {})
            if not isinstance(rv, dict):
                continue

            run = rv.get("composition_run", {})
            if isinstance(run, dict):
                run_status_counts[str(run.get("status", "NO_RUN_STATUS"))] += 1

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
