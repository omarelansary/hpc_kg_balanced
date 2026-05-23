"""Pure relation-pattern grouping helpers extracted from the dashboard."""

from __future__ import annotations

import pandas as pd

from .pattern_evidence import prepare_inverse_table, wilson_interval


def unique_preserve(values) -> list[str]:
    """Return unique string values while preserving first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str) and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def filter_pair_universe(
    df_pairs: pd.DataFrame,
    *,
    base_min_total: int,
    base_max_total: int,
    relation_query: str = "",
) -> pd.DataFrame:
    """Filter pair-count rows by total support and optional focus relation."""
    if base_max_total < base_min_total:
        raise ValueError("base_max_total must be >= base_min_total")
    df_f = df_pairs[(df_pairs["total"] >= int(base_min_total)) & (df_pairs["total"] <= int(base_max_total))].copy()
    if relation_query:
        df_f = df_f[(df_f["r1"] == relation_query) | (df_f["r2"] == relation_query)]
    return df_f


def select_symmetric_candidates(
    df_pairs: pd.DataFrame,
    *,
    min_support: int,
    min_confidence: float,
) -> pd.DataFrame:
    """Select empirical symmetric candidates using self-pair loop confidence."""
    out = df_pairs[df_pairs["r1"] == df_pairs["r2"]].copy()
    out = out[(out["total"] >= int(min_support)) & (out["conf_loop"] >= float(min_confidence))]
    return out.sort_values(["conf_loop", "total", "r1"], ascending=[False, False, True])


def select_anti_symmetric_candidates(
    df_pairs: pd.DataFrame,
    *,
    min_support: int,
    min_confidence: float,
) -> pd.DataFrame:
    """Select empirical anti-symmetric candidates using self-pair non-loop confidence."""
    out = df_pairs[df_pairs["r1"] == df_pairs["r2"]].copy()
    out = out[(out["total"] >= int(min_support)) & (out["conf_nonloop"] >= float(min_confidence))]
    return out.sort_values(["conf_nonloop", "total", "r1"], ascending=[False, False, True])


def select_inverse_candidates(
    df_pairs: pd.DataFrame,
    *,
    min_support: int,
    min_confidence: float,
    sort_by: str = "bidirectional_conf_min",
) -> pd.DataFrame:
    """Select empirical inverse candidates using bidirectional loop confidence."""
    inv = prepare_inverse_table(df_pairs)
    inv["two_way_support_min"] = inv[["total", "reverse_total"]].min(axis=1)
    inv = inv[(inv["two_way_support_min"] >= int(min_support)) & (inv["bidirectional_conf_min"] >= float(min_confidence))]
    if sort_by not in inv.columns:
        raise ValueError(f"unknown inverse sort column: {sort_by}")
    return inv.sort_values([sort_by, "total"], ascending=[False, False])


def classify_composition_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Classify accepted composition triples by self-transitivity and swap existence."""
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


def filter_composition_candidates(
    comp_df: pd.DataFrame,
    *,
    min_support: int,
    min_examined: int,
    min_confidence: float,
    min_shortcuts: int,
    use_wilson: bool,
    wilson_z: float,
    focus_pid: str = "",
    sort_by: str = "conf_composition_sample",
) -> pd.DataFrame:
    """Filter compact composition verification rows using dashboard formulas."""
    comp_f = comp_df[
        (comp_df["base_support"] >= int(min_support))
        & (comp_df["chain_pairs_examined"] >= int(min_examined))
        & (comp_df["chain_pairs_with_shortcut"] >= int(min_shortcuts))
        & (comp_df["conf_composition_sample"] >= float(min_confidence))
    ].copy()

    if not comp_f.empty:
        bounds = comp_f.apply(
            lambda r: wilson_interval(
                int(r["chain_pairs_with_shortcut"]),
                int(r["chain_pairs_examined"]),
                float(wilson_z),
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
        comp_f = comp_f[comp_f["wilson_lower_bound"] >= float(min_confidence)]

    if focus_pid:
        comp_f = comp_f[(comp_f["r1"] == focus_pid) | (comp_f["r2"] == focus_pid) | (comp_f["r3"] == focus_pid)]

    comp_f = classify_composition_patterns(comp_f)
    if sort_by not in comp_f.columns:
        raise ValueError(f"unknown composition sort column: {sort_by}")
    return comp_f.sort_values([sort_by, "chain_pairs_with_shortcut"], ascending=[False, False])


def build_pattern_groups(
    sym_df: pd.DataFrame,
    anti_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    comp_df: pd.DataFrame,
) -> tuple[dict[str, list[str]], list[str]]:
    """Build unique relation-level pattern groups for allocation."""
    sym_rel = unique_preserve(sym_df["r1"].tolist()) if not sym_df.empty else []
    anti_rel = unique_preserve(anti_df["r1"].tolist()) if not anti_df.empty else []
    overlap = sorted(set(sym_rel).intersection(anti_rel))
    anti_rel = [r for r in anti_rel if r not in set(sym_rel)]

    inv_rel: list[str] = []
    if not inv_df.empty:
        inv_rel = unique_preserve(inv_df["r1"].tolist() + inv_df["r2"].tolist())

    comp_rel: list[str] = []
    if not comp_df.empty:
        comp_rel = unique_preserve(comp_df["r1"].tolist() + comp_df["r2"].tolist() + comp_df["r3"].tolist())

    return {
        "symmetric": sym_rel,
        "anti_symmetric": anti_rel,
        "inverse": inv_rel,
        "composition": comp_rel,
    }, overlap


def pattern_group_counts(pattern_groups: dict[str, list[str]]) -> dict[str, int]:
    """Return relation counts for each pattern group."""
    return {name: len(relations) for name, relations in pattern_groups.items()}
