"""
This module implements the allocation rule described in the "Bidirectional Triple allocation"
Markdown spec:

Forward probability:
    P_f(r | W,c) = softmax_r( sum_{r' in c} W_{r r'} )

Backward probability:
    P_b(r | W,c) = softmax_r( sum_{r' in c} W_{r' r} )

Final allocation (expected/real-valued):
    eta_r = 0.5 * eta * ( P_f(r|W,c) + P_b(r|W,c) )

Where:
- W is a relation-to-relation weight matrix, intended to be non-negative.
- c is a group (subset) of relations.
- eta is the total triple budget for the group.

Important modeling note:
- This module performs RELATION-LEVEL allocation.
- If upstream analysis outputs candidate rows (e.g., inverse pairs (r1,r2) or
  composition triples (r1,r2,r3)), those rows must be mapped to a relation set
  before calling this module.
- Therefore, "number of candidates" and "number of allocated relations" are
  different quantities and are not expected to match.

Practicalities handled here:
- Numerically stable softmax.
- Optional temperature to control sharpness.
- Optional epsilon smoothing.
- Conversion from real-valued eta_r to *integer* allocations that sum exactly to eta
  using a largest-remainder method (Hamilton apportionment), with deterministic tie-breaking.

Dependencies:
- numpy only.

Author: (Omar El Ansary, Kossi Amouzovi)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np


# -----------------------------
# Data structures
# -----------------------------

@dataclass(frozen=True)
class AllocationResult:
    """Container for all intermediate scores and outputs for a group.

    Attributes
    ----------
    relations:
        Ordered list of relations in the group. All arrays align with this order.
    forward_scores:
        Row-sum scores s_f(r) = sum_{r' in c} W[r, r'].
    backward_scores:
        Column-sum scores s_b(r) = sum_{r' in c} W[r', r].
    p_forward:
        Forward softmax probabilities P_f(r | W,c).
    p_backward:
        Backward softmax probabilities P_b(r | W,c).
    p_avg:
        Averaged probabilities 0.5*(P_f + P_b).
    eta_total:
        Total budget eta for the group.
    eta_expected:
        Real-valued expected allocations eta_r (sum equals eta_total).
    eta_integer:
        Integer allocations (sum equals eta_total).
    """
    relations: List[str]
    forward_scores: np.ndarray
    backward_scores: np.ndarray
    p_forward: np.ndarray
    p_backward: np.ndarray
    p_avg: np.ndarray
    eta_total: int
    eta_expected: np.ndarray
    eta_integer: np.ndarray


# -----------------------------
# Core math utilities
# -----------------------------

def stable_softmax(x: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """Compute a numerically stable softmax.

    Parameters
    ----------
    x:
        1D array of scores.
    temperature:
        Softmax temperature τ. Larger τ => flatter distribution; smaller τ => sharper.
        Must be > 0.

    Returns
    -------
    np.ndarray:
        Softmax probabilities summing to 1.
    """
    if x.ndim != 1:
        raise ValueError("stable_softmax expects a 1D array.")
    if temperature <= 0:
        raise ValueError("temperature must be > 0.")

    z = x / temperature
    z = z - np.max(z)  # stabilize
    exp_z = np.exp(z)
    denom = np.sum(exp_z)

    # Avoid division by zero (should only happen for pathological inputs)
    if denom == 0 or not np.isfinite(denom):
        # fallback to uniform distribution
        return np.full_like(exp_z, 1.0 / exp_z.size, dtype=float)

    return exp_z / denom


def largest_remainder_apportionment(
    expected: np.ndarray,
    total: int,
    *,
    tie_breaker: Optional[Sequence[int]] = None,
) -> np.ndarray:
    """Convert expected real-valued allocations to integers summing to `total`.

    Uses Hamilton's method (largest remainder):
    - Take floor of each expected value.
    - Distribute remaining units to largest fractional remainders.
    - Deterministic tie-breaking can be enforced via `tie_breaker`.

    Parameters
    ----------
    expected:
        1D array of non-negative expected allocations (usually sums to `total`).
    total:
        Target integer sum.
    tie_breaker:
        Optional sequence of indices used to break ties deterministically.
        If provided, ties in fractional parts are resolved by lower rank in this list.

    Returns
    -------
    np.ndarray:
        Integer allocations with sum exactly equal to `total`.
    """
    if expected.ndim != 1:
        raise ValueError("expected must be a 1D array.")
    if total < 0:
        raise ValueError("total must be >= 0.")
    if np.any(expected < 0):
        raise ValueError("expected must be non-negative.")

    base = np.floor(expected).astype(int)
    base_sum = int(base.sum())
    remainder = total - base_sum

    if remainder < 0:
        # base currently overshoots target total. Remove units deterministically from
        # smallest fractional parts first; if needed keep cycling until exact total.
        frac = expected - np.floor(expected)
        order = np.argsort(frac)  # ascending
        to_remove = -remainder
        while to_remove > 0:
            removed_in_pass = 0
            for idx in order:
                if to_remove == 0:
                    break
                if base[idx] > 0:
                    base[idx] -= 1
                    to_remove -= 1
                    removed_in_pass += 1
            if removed_in_pass == 0:
                raise ValueError("Cannot apportion to requested total with given expected values.")
        assert int(base.sum()) == int(total), "Integer apportionment did not match target sum."
        return base

    if remainder == 0:
        return base

    frac = expected - np.floor(expected)

    # Build a deterministic ordering:
    # Primary: frac descending
    # Secondary: tie breaker (if provided) else index ascending
    if tie_breaker is not None:
        rank = np.empty_like(np.arange(len(expected)))
        rank[:] = len(expected)  # default worst rank
        for rnk, i in enumerate(tie_breaker):
            if 0 <= i < len(expected):
                rank[i] = rnk
        # lexsort uses last key as primary; we want frac desc, rank asc
        order = np.lexsort((rank, -frac))
    else:
        order = np.lexsort((np.arange(len(expected)), -frac))

    alloc = base.copy()
    for idx in order[:remainder]:
        alloc[idx] += 1

    # Safety
    assert int(alloc.sum()) == int(total), "Integer apportionment did not match target sum."
    return alloc


# -----------------------------
# Weight matrix handling
# -----------------------------

def build_weight_matrix_from_edges(
    relations: Sequence[str],
    edges: Iterable[Tuple[str, str, float]],
    *,
    default: float = 0.0,
    clip_min: float = 0.0,
) -> np.ndarray:
    """Build a dense weight matrix W from weighted directed edges (r, r', w).

    Parameters
    ----------
    relations:
        Universe of relations (IDs) defining the matrix order.
    edges:
        Iterable of (src_relation, dst_relation, weight).
    default:
        Default weight for missing edges.
    clip_min:
        Minimum value to clip weights to (recommended 0.0 for this method).

    Returns
    -------
    np.ndarray:
        Dense matrix W of shape (n, n) where W[i, j] is weight from relations[i] -> relations[j].
    """
    rel_to_idx = {r: i for i, r in enumerate(relations)}
    n = len(relations)
    W = np.full((n, n), float(default), dtype=float)

    for src, dst, w in edges:
        if src not in rel_to_idx or dst not in rel_to_idx:
            continue
        i, j = rel_to_idx[src], rel_to_idx[dst]
        W[i, j] = float(w)

    if clip_min is not None:
        W = np.maximum(W, float(clip_min))

    return W


def validate_weight_matrix(W: np.ndarray) -> None:
    """Validate W is usable for allocation."""
    if not isinstance(W, np.ndarray):
        raise TypeError("W must be a numpy.ndarray.")
    if W.ndim != 2 or W.shape[0] != W.shape[1]:
        raise ValueError(f"W must be square; got shape={W.shape}.")
    if not np.all(np.isfinite(W)):
        raise ValueError("W contains non-finite values (inf or NaN).")


# -----------------------------
# Bidirectional allocation
# -----------------------------

def bidirectional_allocation(
    W: np.ndarray,
    relations_universe: Sequence[str],
    group: Sequence[str],
    eta: int,
    *,
    temperature: float = 1.0,
    epsilon: float = 0.0,
    integerize: bool = True,
    tie_breaker_relations: Optional[Sequence[str]] = None,
) -> AllocationResult:
    """Compute bidirectional triple allocation for a single group.

    Parameters
    ----------
    W:
        Dense weight matrix over `relations_universe`.
        Interpretation: W[r, r'] is confidence / connectivity weight.
        Recommended: non-negative, e.g., log(1 + support) or log(support) after smoothing.
    relations_universe:
        Ordering of relations used by W.
    group:
        Relations in the group c (subset of universe).
        This is relation-level membership, not candidate-row membership.
        Duplicate relation IDs are de-duplicated while preserving first-seen order.
    eta:
        Total triple budget for this group (integer).
    temperature:
        Softmax temperature τ > 0.
    epsilon:
        Optional additive smoothing applied to the W submatrix *within the group*.
        This can reduce all-zero row/column cases.
    integerize:
        If True, returns integer allocations summing exactly to eta.
        If False, integer allocations will be a rounded view of expected values.
    tie_breaker_relations:
        Optional tie-breaker list of relation IDs. If provided, ties in integerization
        are broken by this order (earlier wins). Useful for reproducibility.

    Returns
    -------
    AllocationResult:
        Contains forward/backward scores, probabilities, and allocations.

    Notes
    -----
    Forward score:
        s_f(r) = sum_{r' in c} W[r, r']

    Backward score:
        s_b(r) = sum_{r' in c} W[r', r]

    Probabilities:
        P_f = softmax(s_f)
        P_b = softmax(s_b)

    Expected allocation:
        eta_expected = 0.5 * eta * (P_f + P_b)

    Integer allocation:
        eta_integer is computed by largest-remainder apportionment to sum exactly to eta.
    """
    validate_weight_matrix(W)
    if W.shape[0] != len(relations_universe):
        raise ValueError(
            f"W shape {W.shape} is incompatible with relations_universe size {len(relations_universe)}."
        )
    if eta < 0:
        raise ValueError("eta must be >= 0.")
    if len(group) == 0:
        raise ValueError("group must be non-empty.")
    if temperature <= 0:
        raise ValueError("temperature must be > 0.")
    if epsilon < 0:
        raise ValueError("epsilon must be >= 0.")

    rel_to_idx = {r: i for i, r in enumerate(relations_universe)}

    # Keep only group relations that exist in the universe, preserve order and de-duplicate.
    group_relations: List[str] = []
    seen = set()
    for r in group:
        if r in rel_to_idx and r not in seen:
            group_relations.append(r)
            seen.add(r)
    if len(group_relations) == 0:
        raise ValueError("None of the group relations are present in relations_universe.")

    idx = np.array([rel_to_idx[r] for r in group_relations], dtype=int)

    # Extract submatrix for the group
    Wc = W[np.ix_(idx, idx)].astype(float, copy=True)
    if epsilon > 0:
        Wc += epsilon
    Wc = np.maximum(Wc, 0.0)  # enforce non-negativity (surgical safety)

    # Scores
    forward_scores = Wc.sum(axis=1)  # row sums
    backward_scores = Wc.sum(axis=0)  # column sums

    # Softmax probabilities
    p_forward = stable_softmax(forward_scores, temperature=temperature)
    p_backward = stable_softmax(backward_scores, temperature=temperature)

    p_avg = 0.5 * (p_forward + p_backward)

    # Expected allocations (real-valued) - sums to eta (up to floating error)
    eta_expected = float(eta) * p_avg

    # Integer allocations
    if integerize:
        tie_breaker = None
        if tie_breaker_relations is not None:
            tie_breaker = [group_relations.index(r) for r in tie_breaker_relations if r in group_relations]
        eta_integer = largest_remainder_apportionment(eta_expected, eta, tie_breaker=tie_breaker)
    else:
        eta_integer = np.rint(eta_expected).astype(int)
        # ensure exact sum by minimal fix if needed
        diff = int(eta) - int(eta_integer.sum())
        if diff != 0:
            # push adjustment to the max expected entries
            order = np.argsort(-eta_expected)
            for k in range(abs(diff)):
                j = order[k % len(order)]
                eta_integer[j] += 1 if diff > 0 else -1

    return AllocationResult(
        relations=group_relations,
        forward_scores=forward_scores,
        backward_scores=backward_scores,
        p_forward=p_forward,
        p_backward=p_backward,
        p_avg=p_avg,
        eta_total=int(eta),
        eta_expected=eta_expected,
        eta_integer=eta_integer,
    )


def allocate_for_patterns(
    W: np.ndarray,
    relations_universe: Sequence[str],
    pattern_groups: Mapping[str, Sequence[str]],
    eta_per_group: Mapping[str, int],
    *,
    temperature: float = 1.0,
    epsilon: float = 0.0,
    integerize: bool = True,
) -> Dict[str, AllocationResult]:
    """Run bidirectional allocation for multiple relation-pattern groups.

    Parameters
    ----------
    W:
        Weight matrix over the universe.
    relations_universe:
        Universe ordering for W.
    pattern_groups:
        Dict mapping pattern_name -> group relations.
        Example pattern names: "composition", "inverse", "symmetric", "etc".
    eta_per_group:
        Dict mapping pattern_name -> eta for that group.
    temperature, epsilon, integerize:
        Passed to bidirectional_allocation.

    Returns
    -------
    Dict[str, AllocationResult]:
        Allocation results per pattern/group.
    """
    out: Dict[str, AllocationResult] = {}
    for pat, group in pattern_groups.items():
        eta = int(eta_per_group.get(pat, 0))
        out[pat] = bidirectional_allocation(
            W=W,
            relations_universe=relations_universe,
            group=group,
            eta=eta,
            temperature=temperature,
            epsilon=epsilon,
            integerize=integerize,
        )
    return out


# -----------------------------
# Example usage (remove in production)
# -----------------------------

if __name__ == "__main__":
    # Example relations universe
    R = ["P1", "P2", "P3", "P4"]

    # Example weights: you said W is log(support) confidence, loop/non-loop/total/etc.
    # Here we just mock: higher means stronger relation-to-relation connectivity.
    edges = [
        ("P1", "P2", np.log(1 + 10)),
        ("P1", "P3", np.log(1 + 2)),
        ("P2", "P3", np.log(1 + 7)),
        ("P3", "P1", np.log(1 + 1)),
        ("P4", "P1", np.log(1 + 9)),
    ]
    W = build_weight_matrix_from_edges(R, edges, default=0.0, clip_min=0.0)

    # One group (pattern)
    group_c = ["P1", "P2", "P3"]
    eta = 1000

    res = bidirectional_allocation(
        W=W,
        relations_universe=R,
        group=group_c,
        eta=eta,
        temperature=1.0,
        epsilon=0.0,
        integerize=True,
    )

    print("Relations:", res.relations)
    print("Forward scores:", res.forward_scores)
    print("Backward scores:", res.backward_scores)
    print("P_forward:", res.p_forward)
    print("P_backward:", res.p_backward)
    print("P_avg:", res.p_avg)
    print("eta_expected:", res.eta_expected)
    print("eta_integer:", res.eta_integer, "sum=", res.eta_integer.sum())
