# kg_balanced_connected_sampler_sparql.py
import ast
import csv
import json
import logging
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from wikidata_sparql_client import WikidataSPARQL


logger = logging.getLogger("kg_sampler_sparql")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@dataclass(frozen=True)
class InversePair:
    src_pid: str
    inv_pid: str
    src_label: Optional[str] = None
    inv_label: Optional[str] = None


@dataclass
class InputFiles:
    antisymmetric_csv: str = "antisymmetric_relations.csv"
    symmetric_csv: str = "symmetric_relations.csv"
    inverse_csv: str = "inverse_directional.csv"
    composition_targets_csv: str = "relations_report.composition_targets.csv"


@dataclass
class SamplingConfig:
    triples_per_relation_m: int = 50

    candidate_pool_per_pattern: int = 5

    # If None => use all inverse pairs in file; else pick that many
    inverse_pairs_k: Optional[int] = None

    # Iterations / robustness
    attempts: int = 5
    rcl_size: int = 10

    # SPARQL fetch sizes
    seed_fetch: int = 20
    attach_fetch: int = 200
    any_fetch: int = 200

    # To keep VALUES small
    max_v_for_values: int = 20

    # Anchoring
    anchor_fraction: float = 0.2


BASE_DIR = os.path.dirname(__file__)
_OVERLAP_CACHE: Dict[Tuple[str, Tuple[str, ...], int], float] = {}


def resolve_input_path(path: str) -> str:
    if not path:
        return path
    if os.path.isabs(path) or os.path.exists(path):
        return path
    candidate = os.path.join(BASE_DIR, path)
    if os.path.exists(candidate):
        return candidate
    return path


def read_single_pid_csv(path: str) -> List[str]:
    out = []
    path = resolve_input_path(path)
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            pid = (row.get("pid") or "").strip()
            if pid:
                out.append(pid)
    return out


def read_inverse_pairs_csv(path: str) -> List[InversePair]:
    out = []
    path = resolve_input_path(path)
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            a = (row.get("src_pid") or "").strip()
            b = (row.get("its_inv_pid") or row.get("dst_pid") or "").strip()
            if a and b:
                out.append(
                    InversePair(
                        src_pid=a,
                        inv_pid=b,
                        src_label=(row.get("src_label") or "").strip() or None,
                        inv_label=(row.get("its_inv_label") or row.get("dst_label") or "").strip() or None,
                    )
                )
    return out


def parse_chains_field(chains_str: str) -> List[Tuple[str, str]]:
    if not chains_str:
        return []
    s = chains_str.strip().replace('""', '"')
    try:
        val = ast.literal_eval(s)
        out = []
        for pair in val:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                out.append((str(pair[0]).strip(), str(pair[1]).strip()))
        return out
    except Exception:
        return []


def read_composition_targets_csv(path: str) -> List[str]:
    # For sampling we only need target_pid list
    out = []
    path = resolve_input_path(path)
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            pid = (row.get("target_pid") or "").strip()
            if pid:
                out.append(pid)
    return out


def rcl_pick(scored: List[Tuple[str, float]], rcl_size: int) -> Optional[str]:
    if not scored:
        return None
    scored = sorted(scored, key=lambda x: x[1], reverse=True)
    rcl = scored[: max(1, min(rcl_size, len(scored)))]
    return random.choice(rcl)[0]


def overlap_score(pid: str, v: Set[str], wd: WikidataSPARQL, max_v: int, probe: int) -> float:
    if not v:
        return 0.0
    v_list = sorted(v)[:max_v]
    key = (pid, tuple(v_list), probe)
    if key in _OVERLAP_CACHE:
        return _OVERLAP_CACHE[key]
    triples = wd.fetch_triples_for_relation_attach_to_v(pid, v_list, limit=probe)
    score = min(1.0, len(triples) / max(1, probe))
    _OVERLAP_CACHE[key] = score
    return score


def sample_exact_m_connected(
    pid: str,
    m: int,
    v: Set[str],
    wd: WikidataSPARQL,
    max_v: int,
    anchor_n: int,
    attach_fetch: int,
    any_fetch: int,
) -> Optional[List[Tuple[str, str, str]]]:
    """
    Returns list of (h, pid, t) of length exactly m.
    Connectivity invariant: when adding, h in V OR t in V.
    """
    chosen: List[Tuple[str, str, str]] = []
    used = set()

    def add(h: str, t: str) -> bool:
        key = (h, pid, t)
        if key in used:
            return False
        used.add(key)
        chosen.append((h, pid, t))
        v.add(h); v.add(t)
        return True

    # Seed V if empty
    if not v:
        seeds = wd.fetch_triples_for_relation_any(pid, limit=10)
        if not seeds:
            return None
        h, t = random.choice(seeds)
        add(h, t)

    # Anchored part
    need_anchor = min(anchor_n, m)
    if need_anchor > 0:
        candidates = wd.fetch_triples_for_relation_attach_to_v(pid, sorted(v)[:max_v], limit=attach_fetch)
        if not candidates:
            return None
        # prefer expanding
        random.shuffle(candidates)
        candidates.sort(key=lambda ht: (ht[0] not in v) or (ht[1] not in v), reverse=True)
        for (h, t) in candidates:
            if len(chosen) >= need_anchor:
                break
            if (h in v) or (t in v):
                add(h, t)
        if len(chosen) < need_anchor:
            return None
        
    # # EARLY OVERLAP PROBE: if pid has no edges touching current V, do not spam queries
    # probe = wd.fetch_triples_for_relation_attach_to_v(pid, sorted(v)[:max_v], limit=1)
    # if not probe:
    #     return None

    # # Fill remaining, still attached to V
    # while len(chosen) < m:
    #     remaining = m - len(chosen)
    #     # candidates = wd.fetch_triples_for_relation_attach_to_v(pid, sorted(v)[:max_v], limit=max(attach_fetch, remaining * 5))
    #     # if not candidates:
    #     #     return None


    #     candidates = wd.fetch_triples_for_relation_attach_to_v(pid, sorted(v)[:max_v], limit=max(attach_fetch, remaining * 5))
    #     if not candidates:
    #         # RESEED ONCE: expand V using this relation so it can become part of the backbone
    #         seeds = wd.fetch_triples_for_relation_any(pid, limit=min(any_fetch, 50))
    #         if not seeds:
    #             return None
    #         # add ONE seed edge (this may introduce new nodes but keeps this relation usable)
    #         h, t = random.choice(seeds)
    #         if not add(h, t):
    #             return None
    #         # now try again to attach (next loop iteration)
    #         continue


    # Fill remaining, still attached to V
    while len(chosen) < m:
        remaining = m - len(chosen)
        candidates = wd.fetch_triples_for_relation_attach_to_v(
            pid, sorted(v)[:max_v], limit=max(attach_fetch, remaining * 5)
        )
        if not candidates:
            return None  # MUST fail; otherwise you may disconnect the global graph

        random.shuffle(candidates)
        candidates.sort(key=lambda ht: (ht[0] not in v) or (ht[1] not in v), reverse=True)

        progress = 0
        for (h, t) in candidates:
            if len(chosen) >= m:
                break
            if (h in v) or (t in v):
                if add(h, t):
                    progress += 1

        if progress == 0:
            return None

        # random.shuffle(candidates)
        # candidates.sort(key=lambda ht: (ht[0] not in v) or (ht[1] not in v), reverse=True)

        # progress = 0
        # for (h, t) in candidates:
        #     if len(chosen) >= m:
        #         break
        #     if (h in v) or (t in v):
        #         if add(h, t):
        #             progress += 1
        # if progress == 0:
        #     # # Try a broader fetch without V constraint to expand V indirectly
        #     # any_cands = wd.fetch_triples_for_relation_any(pid, limit=any_fetch)
        #     # # but we still must attach => only accept if it attaches; otherwise ignore
        #     # random.shuffle(any_cands)
        #     # for (h, t) in any_cands:
        #     #     if (h in v) or (t in v):
        #     #         if add(h, t):
        #     #             progress += 1
        #     #             if len(chosen) >= m:
        #     #                 break
        #     # if progress == 0:
        #     return None

    return chosen


def main():
    files = InputFiles()
    cfg = SamplingConfig()

    # IMPORTANT: set a real UA (Wikidata requires it)
    wd = WikidataSPARQL(user_agent="balanced-benchmark-pipeline/1.0 (contact: omaransary@gmail.com)")

    antisym = read_single_pid_csv(files.antisymmetric_csv)
    sym = read_single_pid_csv(files.symmetric_csv)
    inv_pairs = read_inverse_pairs_csv(files.inverse_csv)
    comp_targets = read_composition_targets_csv(files.composition_targets_csv)

    if not inv_pairs:
        raise RuntimeError("No inverse pairs loaded; cannot balance using inverse bottleneck.")

    # Determine K pairs
    if cfg.inverse_pairs_k is None:
        k_pairs = len(inv_pairs)
    else:
        k_pairs = max(1, min(cfg.inverse_pairs_k, len(inv_pairs)))

    k_rel = k_pairs
    m = cfg.triples_per_relation_m
    anchor_n = max(1, int(cfg.anchor_fraction * m))

    logger.info("K_pairs=%d => K_relations_per_pattern=%d; M=%d", k_pairs, k_rel, m)


    for attempt in range(1, cfg.attempts + 1):
        logger.info("Attempt %d/%d", attempt, cfg.attempts)
        V: Set[str] = set()
        triples_out: List[Tuple[str, str, str]] = []

        chosen_pairs = random.sample(inv_pairs, k_pairs) if k_pairs < len(inv_pairs) else list(inv_pairs)
        inv_rel = []
        for p in chosen_pairs:
            inv_rel.extend([p.src_pid, p.inv_pid])

        # Seed V from an inverse relation (any triple)
        seed_pid = random.choice(inv_rel)
        seed = wd.fetch_triples_for_relation_any(seed_pid, limit=cfg.seed_fetch)
        if not seed:
            logger.warning("No seed triples for %s; retry attempt.", seed_pid)
            continue
        h0, t0 = random.choice(seed)
        V.update([h0, t0])


        selected: Dict[str, List[str]] = {"INVERSE": inv_rel, "SYMMETRIC": [], "COMPOSITION": [], "ANTISYMMETRIC": []}

        # Ensure we fill seed_pid first (so V expands early)
        inverse_pids_ordered = [seed_pid] + [p for p in selected["INVERSE"] if p != seed_pid]

        # Fill inverse first
        ok = True
        inverse_remaining = list(inverse_pids_ordered)
        while inverse_remaining:
            scored = [
                (pid, overlap_score(pid, V, wd, cfg.max_v_for_values, probe=30))
                for pid in inverse_remaining
            ]
            candidates = [(pid, score) for (pid, score) in scored if score > 0.0]
            if not candidates:
                ok = False
                break
            pid = rcl_pick(candidates, cfg.rcl_size) or candidates[0][0]
            inverse_remaining.remove(pid)
            logger.info("Filling inverse pid=%s with |V|=%d", pid, len(V))
            samp = sample_exact_m_connected(
                pid, m, V, wd, cfg.max_v_for_values, anchor_n, attach_fetch=2000, any_fetch=cfg.any_fetch
            )
            logger.info("fill pid=%s -> %s", pid, "OK" if samp is not None else "FAIL")
            if samp is None:
                ok = False
                break
            triples_out.extend(samp)
        if not ok:
            logger.info("Failed filling inverse; retry attempt.")
            continue

        # Select other relations biased by overlap with the expanded V
        def select_k_rel(cands: List[str], name: str) -> List[str]:
            if len(cands) < k_rel:
                raise RuntimeError(f"Not enough candidates to fill {name}: need {k_rel}, have {len(cands)}")

            pool_size = min(cfg.candidate_pool_per_pattern, len(cands))
            scored: List[Tuple[str, float]] = []
            tried_sizes = set()
            while True:
                tried_sizes.add(pool_size)
                pool = random.sample(cands, pool_size)
                scored_all = [
                    (pid, overlap_score(pid, V, wd, cfg.max_v_for_values, probe=30))
                    for pid in pool
                ]
                scored = [(pid, score) for (pid, score) in scored_all if score > 0.0]
                if len(scored) >= k_rel or pool_size == len(cands):
                    break
                # expand pool to improve odds of overlap
                pool_size = min(len(cands), max(pool_size * 2, k_rel))
                if pool_size in tried_sizes:
                    break

            if len(scored) < k_rel:
                raise RuntimeError(
                    f"Not enough candidates with overlap > 0 to fill {name}: need {k_rel}, have {len(scored)}"
                )

            chosen = []
            remaining = scored[:]
            while len(chosen) < k_rel:
                pid = rcl_pick(remaining, cfg.rcl_size)
                if pid is None:
                    break
                chosen.append(pid)
                remaining = [(p, s) for (p, s) in remaining if p != pid]
            if len(chosen) < k_rel:
                remain_pids = [p for (p, _) in remaining]
                need = k_rel - len(chosen)
                if len(remain_pids) < need:
                    raise RuntimeError(
                        f"Not enough candidates with overlap > 0 to fill {name}: need {k_rel}, have {len(remain_pids)}"
                    )
                chosen.extend(random.sample(remain_pids, need))
            return chosen

        try:
            selected["SYMMETRIC"] = select_k_rel(sym, "SYMMETRIC")
            selected["COMPOSITION"] = select_k_rel(comp_targets, "COMPOSITION")
            selected["ANTISYMMETRIC"] = select_k_rel(antisym, "ANTISYMMETRIC")
        except Exception as e:
            logger.warning("Relation selection failed: %s", e)
            continue

        # Round-robin fill others
        rr = ["SYMMETRIC", "COMPOSITION", "ANTISYMMETRIC"]
        remaining = {p: list(selected[p]) for p in rr}
        while any(remaining[p] for p in rr):
            progressed = False
            for p in rr:
                if not remaining[p]:
                    continue
                scored = [
                    (pid, overlap_score(pid, V, wd, cfg.max_v_for_values, probe=30))
                    for pid in remaining[p]
                ]
                candidates = [(pid, score) for (pid, score) in scored if score > 0.0]
                if not candidates:
                    continue
                pid = rcl_pick(candidates, cfg.rcl_size) or candidates[0][0]
                remaining[p].remove(pid)
                samp = sample_exact_m_connected(
                    pid, m, V, wd, cfg.max_v_for_values, anchor_n, cfg.attach_fetch, cfg.any_fetch
                )
                if samp is None:
                    ok = False
                    break
                triples_out.extend(samp)
                progressed = True
            if not ok or not progressed:
                ok = False
                break

        if not ok:
            logger.info("Failed filling all patterns; retry attempt.")
            continue

        # Success
        with open("balanced_connected_sample.triples.jsonl", "w", encoding="utf-8") as f:
            for (h, pid, t) in triples_out:
                f.write(json.dumps({"h": h, "r": pid, "t": t}) + "\n")

        with open("balanced_connected_sample.metadata.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "k_pairs": k_pairs,
                    "k_relations_per_pattern": k_rel,
                    "m_triples_per_relation": m,
                    "selected_relations": selected,
                    "note": "Triples pulled live from Wikidata SPARQL; graph connectivity enforced during construction.",
                },
                f,
                indent=2,
            )

        logger.info("SUCCESS. Triples written: %d", len(triples_out))
        return

    raise RuntimeError("Failed after all attempts. Try lowering M, reducing K_pairs, or increasing fetch limits.")


if __name__ == "__main__":
    main()
