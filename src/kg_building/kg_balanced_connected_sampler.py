# kg_balanced_connected_sampler.py
import ast
import csv
import json
import logging
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from pymongo import MongoClient
from pymongo.collection import Collection

from config_sampler import MongoConfig, InputFiles, SamplingConfig, DomainRangeConfig


logger = logging.getLogger("kg_sampler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


Pattern = str  # "INVERSE" | "SYMMETRIC" | "ANTISYMMETRIC" | "COMPOSITION"
BASE_DIR = os.path.dirname(__file__)


@dataclass(frozen=True)
class InversePair:
    src_pid: str
    inv_pid: str
    src_label: Optional[str] = None
    inv_label: Optional[str] = None


def resolve_input_path(path: str) -> str:
    if not path:
        return path
    if os.path.isabs(path) or os.path.exists(path):
        return path
    candidate = os.path.join(BASE_DIR, path)
    if os.path.exists(candidate):
        return candidate
    return path


def read_single_pid_csv(path: str) -> List[Tuple[str, Optional[str]]]:
    """Reads CSV like: pid,label"""
    out = []
    path = resolve_input_path(path)
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            pid = row.get("pid")
            if not pid:
                continue
            out.append((pid.strip(), (row.get("label") or "").strip() or None))
    return out


def read_inverse_pairs_csv(path: str) -> List[InversePair]:
    """
    Reads CSV like:
    src_pid,src_label,its_inv_pid,its_inv_label
    """
    out = []
    path = resolve_input_path(path)
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            a = (row.get("src_pid") or "").strip()
            b = (row.get("its_inv_pid") or "").strip()
            if not a or not b:
                continue
            out.append(
                InversePair(
                    src_pid=a,
                    inv_pid=b,
                    src_label=(row.get("src_label") or "").strip() or None,
                    inv_label=(row.get("its_inv_label") or "").strip() or None,
                )
            )
    return out


def parse_chains_field(chains_str: str) -> List[Tuple[str, str]]:
    """
    chains is stored like:
      [["P1001","P1001"], ["P1001","P112"], ...]
    sometimes it comes with escaped quotes.
    We'll parse robustly.
    """
    if not chains_str:
        return []
    s = chains_str.strip()

    # Normalize common escaped formats
    # e.g. "[[""P1001"", ""P1001""]]"
    s = s.replace('""', '"')

    try:
        val = ast.literal_eval(s)
        # Expect list of [r1,r2]
        out = []
        for pair in val:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                out.append((str(pair[0]).strip(), str(pair[1]).strip()))
        return out
    except Exception:
        logger.warning("Failed to parse chains field: %r", chains_str[:200])
        return []


def read_composition_targets_csv(path: str) -> Dict[str, Dict]:
    """
    Reads:
    target_pid,target_label,chains,chain_count
    Returns dict: target_pid -> {label, chains:[(r1,r2)], chain_count:int}
    """
    out: Dict[str, Dict] = {}
    path = resolve_input_path(path)
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            pid = (row.get("target_pid") or "").strip()
            if not pid:
                continue
            label = (row.get("target_label") or "").strip() or None
            chains = parse_chains_field(row.get("chains") or "")
            try:
                cc = int((row.get("chain_count") or "0").strip())
            except Exception:
                cc = 0
            out[pid] = {"label": label, "chains": chains, "chain_count": cc}
    return out


class CompatIndex:
    """
    Fast lookup for (r1,r2) -> compatibility.
    Missing means disjoint (per your rule).
    """

    def __init__(self, coll: Collection, cfg: DomainRangeConfig):
        self.coll = coll
        self.cfg = cfg
        self._cache: Dict[Tuple[str, str], str] = {}

    def get(self, r1: str, r2: str) -> Optional[str]:
        key = (r1, r2)
        if key in self._cache:
            return self._cache[key]

        doc = self.coll.find_one({"r1": r1, "r2": r2}, {"compatibility": 1})
        if not doc:
            self._cache[key] = None
            return None

        comp = doc.get("compatibility")
        if comp not in self.cfg.allowed:
            # Treat unknown as None
            self._cache[key] = None
            return None

        self._cache[key] = comp
        return comp

    def chain_is_possible(self, r1: str, r2: str) -> bool:
        comp = self.get(r1, r2)
        if comp is None:
            return not self.cfg.treat_missing_as_disjoint
        return True


class TripleSource:
    def __init__(self, coll: Collection, mcfg: MongoConfig, scfg: SamplingConfig):
        self.coll = coll
        self.mcfg = mcfg
        self.scfg = scfg

    def count_triples(self, pid: str) -> int:
        return self.coll.count_documents({self.mcfg.field_rel: pid})

    def sample_triples_any(self, pid: str, n: int) -> List[Dict]:
        """
        Return up to n triples for relation pid, random-ish.
        Uses aggregation $sample if allowed; otherwise just takes first n (not ideal).
        """
        if n <= 0:
            return []

        if self.scfg.allow_sampling_fallback:
            pipeline = [
                {"$match": {self.mcfg.field_rel: pid}},
                {"$sample": {"size": min(n, self.scfg.mongo_batch_limit)}},
                {"$project": {self.mcfg.field_head: 1, self.mcfg.field_tail: 1, self.mcfg.field_rel: 1}},
            ]
            return list(self.coll.aggregate(pipeline))

        cur = self.coll.find(
            {self.mcfg.field_rel: pid},
            {self.mcfg.field_head: 1, self.mcfg.field_tail: 1, self.mcfg.field_rel: 1},
        ).limit(min(n, self.scfg.mongo_batch_limit))
        return list(cur)

    def sample_triples_attach_to_v(self, pid: str, v: Set[str], n: int) -> List[Dict]:
        """
        Return up to n triples for relation pid where h in v OR t in v.
        WARNING: $in on large v can be heavy; for large runs you should consider indexing h,t and/or
        materializing entity->triples adjacency collections.
        """
        if n <= 0:
            return []
        if not v:
            return []

        v_list = list(v)
        q = {
            self.mcfg.field_rel: pid,
            "$or": [
                {self.mcfg.field_head: {"$in": v_list}},
                {self.mcfg.field_tail: {"$in": v_list}},
            ],
        }
        if self.scfg.allow_sampling_fallback:
            pipeline = [
                {"$match": q},
                {"$sample": {"size": min(n, self.scfg.mongo_batch_limit)}},
                {"$project": {self.mcfg.field_head: 1, self.mcfg.field_tail: 1, self.mcfg.field_rel: 1}},
            ]
            return list(self.coll.aggregate(pipeline))

        cur = self.coll.find(
            q,
            {self.mcfg.field_head: 1, self.mcfg.field_tail: 1, self.mcfg.field_rel: 1},
        ).limit(min(n, self.scfg.mongo_batch_limit))
        return list(cur)


def filter_feasible_inverse_pairs(inv_pairs: List[InversePair], ts: TripleSource, m_needed: int) -> List[InversePair]:
    feasible = []
    for p in inv_pairs:
        if ts.count_triples(p.src_pid) >= m_needed and ts.count_triples(p.inv_pid) >= m_needed:
            feasible.append(p)
    return feasible


def endpoints(triple: Dict, mcfg: MongoConfig) -> Tuple[str, str]:
    return str(triple.get(mcfg.field_head)), str(triple.get(mcfg.field_tail))


def compute_overlap_score(ts: TripleSource, pid: str, v: Set[str], probe_n: int, mcfg: MongoConfig) -> float:
    """
    Estimate how well a relation can attach to current component V:
    overlap score = fraction of probed triples where h or t is in V.
    """
    if not v:
        return 0.0
    probes = ts.sample_triples_any(pid, probe_n)
    if not probes:
        return 0.0
    hit = 0
    for tr in probes:
        h, t = endpoints(tr, mcfg)
        if (h in v) or (t in v):
            hit += 1
    return hit / max(1, len(probes))


def rcl_pick(items: List[Tuple[str, float]], rcl_size: int) -> Optional[str]:
    """
    items: [(pid, score)] sorted high->low or not.
    build RCL of best rcl_size and pick random from it.
    """
    if not items:
        return None
    items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
    rcl = items_sorted[: max(1, min(rcl_size, len(items_sorted)))]
    return random.choice(rcl)[0]


def choose_inverse_pairs(all_pairs: List[InversePair], k_pairs: int) -> List[InversePair]:
    if k_pairs >= len(all_pairs):
        return list(all_pairs)
    return random.sample(all_pairs, k_pairs)


def build_balanced_relation_sets(
    antisym_pids: List[str],
    sym_pids: List[str],
    comp_targets: List[str],
    inv_pairs: List[InversePair],
    ts: TripleSource,
    scfg: SamplingConfig,
    mcfg: MongoConfig,
    k_pairs: int,
    seed_v: Set[str],
) -> Dict[Pattern, List[str]]:
    """
    Returns dict pattern->list of selected relation PIDs.
    Balanced by RELATIONS per pattern:
      K_rel = 2*k_pairs
    Inverse contributes exactly 2*k_pairs relations (src+inv for each selected pair).
    """
    k_rel = 2 * k_pairs
    selected: Dict[Pattern, List[str]] = {"INVERSE": [], "SYMMETRIC": [], "COMPOSITION": [], "ANTISYMMETRIC": []}

    # Inverse: take both directions as relations
    chosen_pairs = choose_inverse_pairs(inv_pairs, k_pairs)
    inv_relations = []
    for p in chosen_pairs:
        inv_relations.extend([p.src_pid, p.inv_pid])
    selected["INVERSE"] = inv_relations

    # For others, prefer relations that overlap the current seed_v (connectability)
    def pick_relations(candidates: List[str], pattern: Pattern) -> List[str]:
        # Filter candidates that have at least M triples available
        feasible = []
        for pid in candidates:
            if ts.count_triples(pid) >= scfg.triples_per_relation_m:
                feasible.append(pid)

        if len(feasible) < k_rel:
            raise RuntimeError(f"Not enough feasible relations for pattern={pattern}. Need {k_rel}, have {len(feasible)}")

        # Score by overlap to seed_v
        scored = [(pid, compute_overlap_score(ts, pid, seed_v, scfg.overlap_probe_triples, mcfg)) for pid in feasible]
        # We will pick k_rel via repeated RCL picking without replacement
        chosen = []
        remaining = scored
        while len(chosen) < k_rel:
            pid = rcl_pick(remaining, scfg.rcl_size)
            if pid is None:
                break
            chosen.append(pid)
            remaining = [(p, s) for (p, s) in remaining if p != pid]
        if len(chosen) < k_rel:
            # fall back: fill randomly among remaining feasible
            remain_pids = [p for (p, _) in remaining]
            need = k_rel - len(chosen)
            chosen.extend(random.sample(remain_pids, need))
        return chosen

    selected["SYMMETRIC"] = pick_relations(sym_pids, "SYMMETRIC")
    selected["COMPOSITION"] = pick_relations(comp_targets, "COMPOSITION")
    selected["ANTISYMMETRIC"] = pick_relations(antisym_pids, "ANTISYMMETRIC")
    return selected


def sample_m_triples_for_relation_connected(
    ts: TripleSource,
    pid: str,
    m: int,
    v: Set[str],
    mcfg: MongoConfig,
    anchor_n: int,
) -> Optional[List[Dict]]:
    """
    Samples exactly m triples for relation pid such that every added triple attaches to current node set v
    (h in v OR t in v at the moment of insertion), so global connectivity is preserved.
    Returns list of triples or None if impossible.
    """
    chosen: List[Dict] = []
    used_keys: Set[Tuple[str, str, str]] = set()

    def add_tr(tr: Dict) -> bool:
        h, t = endpoints(tr, mcfg)
        key = (h, pid, t)
        if key in used_keys:
            return False
        chosen.append({mcfg.field_head: h, mcfg.field_rel: pid, mcfg.field_tail: t})
        used_keys.add(key)
        v.add(h)
        v.add(t)
        return True

    # If v is empty, we can't enforce connectedness; caller should seed.
    if not v:
        # Seed with any triple then proceed
        init = ts.sample_triples_any(pid, 1)
        if not init:
            return None
        add_tr(init[0])

    # Phase 1: anchored triples
    needed_anchor = min(anchor_n, m)
    if needed_anchor > 0:
        anchored = ts.sample_triples_attach_to_v(pid, v, max(needed_anchor * 3, needed_anchor))
        # Prefer those that expand (introduce a new node)
        anchored.sort(
            key=lambda tr: (endpoints(tr, mcfg)[0] not in v) or (endpoints(tr, mcfg)[1] not in v),
            reverse=True,
        )
        for tr in anchored:
            if len(chosen) >= needed_anchor:
                break
            h, t = endpoints(tr, mcfg)
            if (h in v) or (t in v):
                add_tr(tr)

        if len(chosen) < needed_anchor:
            # Not enough anchored triples
            return None

    # Phase 2: fill remaining, still attached to v
    while len(chosen) < m:
        remaining = m - len(chosen)
        candidates = ts.sample_triples_attach_to_v(pid, v, max(remaining * 3, 50))
        if not candidates:
            return None

        # Greedy: prefer expanding triples first
        candidates.sort(
            key=lambda tr: ((endpoints(tr, mcfg)[0] not in v) or (endpoints(tr, mcfg)[1] not in v)),
            reverse=True,
        )
        progress = 0
        for tr in candidates:
            if len(chosen) >= m:
                break
            h, t = endpoints(tr, mcfg)
            if (h in v) or (t in v):
                if add_tr(tr):
                    progress += 1
        if progress == 0:
            return None

    return chosen


def is_connected_undirected(triples: List[Dict], mcfg: MongoConfig) -> bool:
    """
    Simple connectivity check on the undirected projection.
    """
    if not triples:
        return False
    adj: Dict[str, Set[str]] = defaultdict(set)
    nodes: Set[str] = set()
    for tr in triples:
        h = str(tr.get(mcfg.field_head))
        t = str(tr.get(mcfg.field_tail))
        nodes.add(h); nodes.add(t)
        adj[h].add(t); adj[t].add(h)

    start = next(iter(nodes))
    seen = set([start])
    stack = [start]
    while stack:
        x = stack.pop()
        for y in adj.get(x, []):
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return len(seen) == len(nodes)


def filter_composition_targets_by_chain_compat(
    comp_targets: Dict[str, Dict],
    compat: CompatIndex,
) -> List[str]:
    """
    Keep a target if it has at least one chain (r1,r2) that is not disjoint,
    i.e., present in compat collection (or treat_missing_as_disjoint=False).
    """
    kept = []
    for target_pid, meta in comp_targets.items():
        chains = meta.get("chains", [])
        ok = any(compat.chain_is_possible(r1, r2) for (r1, r2) in chains)
        if ok:
            kept.append(target_pid)
    return kept


def main():
    mcfg = MongoConfig()
    files = InputFiles()
    scfg = SamplingConfig()
    dcfg = DomainRangeConfig()

    client = MongoClient(mcfg.uri)
    db = client[mcfg.db_name]
    triples_coll = db[mcfg.triples_collection]
    compat_coll = db[dcfg.compat_collection]

    ts = TripleSource(triples_coll, mcfg, scfg)
    compat = CompatIndex(compat_coll, dcfg)

    # Load relation lists
    antisym = [pid for (pid, _) in read_single_pid_csv(files.antisymmetric_csv)]
    sym = [pid for (pid, _) in read_single_pid_csv(files.symmetric_csv)]

    inv_pairs_raw = read_inverse_pairs_csv(files.inverse_csv)
    inv_pairs = filter_feasible_inverse_pairs(inv_pairs_raw, ts, scfg.triples_per_relation_m)

    if not inv_pairs:
        # Strong diagnostic so you don't waste time
        logger.error("No feasible inverse pairs where BOTH relations have >= M=%d triples.", scfg.triples_per_relation_m)
        logger.error("Raw inverse pairs loaded: %d", len(inv_pairs_raw))
        for p in inv_pairs_raw[:20]:
            logger.error("pair %s (%d triples) <-> %s (%d triples)",
                        p.src_pid, ts.count_triples(p.src_pid),
                        p.inv_pid, ts.count_triples(p.inv_pid))
        raise RuntimeError("No feasible inverse pairs. Lower M or fix inverse CSV / triples coverage.")


    comp_targets_map = read_composition_targets_csv(files.composition_targets_csv)

    # Apply chain compatibility filter to composition targets
    comp_targets = filter_composition_targets_by_chain_compat(comp_targets_map, compat)

    if not inv_pairs:
        raise RuntimeError("No inverse pairs loaded. Cannot balance by inverse bottleneck.")

    # Determine inverse pairs K
    if scfg.inverse_pairs_k is None:
        k_pairs = len(inv_pairs)
    else:
        k_pairs = max(1, min(scfg.inverse_pairs_k, len(inv_pairs)))

    # Derived relations per pattern
    k_rel = 2 * k_pairs
    logger.info("Using inverse_pairs_k=%d => K_relations_per_pattern=%d", k_pairs, k_rel)
    logger.info("Triples per relation M=%d", scfg.triples_per_relation_m)

    # GRASP-like attempts
    best_solution = None

    for attempt in range(1, scfg.attempts + 1):
        logger.info("Attempt %d/%d", attempt, scfg.attempts)

        # Seed component V using inverse relations first
        V: Set[str] = set()
        all_triples: List[Dict] = []

        try:
            # Choose inverse pairs for this attempt
            chosen_pairs = choose_inverse_pairs(inv_pairs, k_pairs)
            inv_relations = []
            for p in chosen_pairs:
                inv_relations.extend([p.src_pid, p.inv_pid])

            # Seed: take 1 triple from first inverse relation (any), to start V
            # Prefer seeding from inverse relations, but fall back to any selected relation later if needed
            seed_candidates = [pid for pid in inv_relations if ts.count_triples(pid) > 0]
            if not seed_candidates:
                logger.warning("No inverse relation has any triples for seeding; retry attempt.")
                continue

            seed_pid = random.choice(seed_candidates)
            seed_tr = ts.sample_triples_any(seed_pid, 1)
            if not seed_tr:
                logger.warning("Seed relation %s had no triples at sampling time; retry attempt.", seed_pid)
                continue

            h0, t0 = endpoints(seed_tr[0], mcfg)
            V.update([h0, t0])


            # Build relation sets (balanced)
            selected = build_balanced_relation_sets(
                antisym_pids=antisym,
                sym_pids=sym,
                comp_targets=comp_targets,
                inv_pairs=chosen_pairs,   # note: here pass the chosen list for deterministic per attempt
                ts=ts,
                scfg=scfg,
                mcfg=mcfg,
                k_pairs=k_pairs,
                seed_v=V,
            )

            # Now sample exactly M triples per relation, interleaving patterns (round-robin) after inverse-first
            # Build an ordered list: inverse relations first, then round-robin others
            inverse_list = selected["INVERSE"]

            other_patterns = ["SYMMETRIC", "COMPOSITION", "ANTISYMMETRIC"]
            other_lists = {p: list(selected[p]) for p in other_patterns}

            # Inverse-first: fully fill inverse relations
            anchor_n = max(1, int(scfg.anchor_fraction * scfg.triples_per_relation_m))
            per_relation_triples: Dict[str, List[Dict]] = {}

            failed = False
            for pid in inverse_list:
                triples = sample_m_triples_for_relation_connected(
                    ts, pid, scfg.triples_per_relation_m, V, mcfg, anchor_n=anchor_n
                )
                if triples is None:
                    failed = True
                    break
                per_relation_triples[pid] = triples
                all_triples.extend(triples)
            if failed:
                logger.info("Failed filling inverse relations; retry attempt.")
                continue

            # Round-robin fill other patterns
            # We will iterate until all their relations are filled
            remaining = sum(len(other_lists[p]) for p in other_patterns)
            rr_order = other_patterns[:]

            while remaining > 0:
                progressed = False
                for pat in rr_order:
                    if not other_lists[pat]:
                        continue
                    pid = other_lists[pat].pop()
                    triples = sample_m_triples_for_relation_connected(
                        ts, pid, scfg.triples_per_relation_m, V, mcfg, anchor_n=anchor_n
                    )
                    if triples is None:
                        # Local repair: try swapping relation with another candidate from same pattern
                        # Choose a replacement that (a) has enough triples and (b) overlaps current V
                        candidates = antisym if pat == "ANTISYMMETRIC" else sym if pat == "SYMMETRIC" else comp_targets
                        # Filter feasible and not already selected
                        already = set(selected["INVERSE"] + selected["SYMMETRIC"] + selected["COMPOSITION"] + selected["ANTISYMMETRIC"])
                        feasible = [c for c in candidates if (c not in already) and ts.count_triples(c) >= scfg.triples_per_relation_m]
                        if not feasible:
                            failed = True
                            break

                        scored = [(c, compute_overlap_score(ts, c, V, scfg.overlap_probe_triples, mcfg)) for c in feasible]
                        repl = rcl_pick(scored, scfg.rcl_size)
                        if repl is None:
                            failed = True
                            break

                        selected[pat].append(repl)  # track it
                        triples2 = sample_m_triples_for_relation_connected(
                            ts, repl, scfg.triples_per_relation_m, V, mcfg, anchor_n=anchor_n
                        )
                        if triples2 is None:
                            failed = True
                            break

                        per_relation_triples[repl] = triples2
                        all_triples.extend(triples2)
                        progressed = True
                        remaining -= 1
                    else:
                        per_relation_triples[pid] = triples
                        all_triples.extend(triples)
                        progressed = True
                        remaining -= 1

                if failed:
                    break
                if not progressed:
                    failed = True
                    break

            if failed:
                logger.info("Failed in round-robin fill; retry attempt.")
                continue

            # Final connectivity check (should pass if invariant was respected)
            if not is_connected_undirected(all_triples, mcfg):
                logger.info("Graph not connected at end (unexpected). Retry attempt.")
                continue

            # Success
            best_solution = {
                "k_pairs": k_pairs,
                "k_relations_per_pattern": k_rel,
                "m_triples_per_relation": scfg.triples_per_relation_m,
                "selected_relations": selected,
                "triples": all_triples,
            }
            logger.info("SUCCESS on attempt %d. Triples=%d", attempt, len(all_triples))
            break

        except Exception as e:
            logger.exception("Attempt failed due to exception: %s", e)
            continue

    if best_solution is None:
        raise RuntimeError("Failed to find a connected balanced sample. Try lowering M or increasing attempts.")

    # Write outputs
    with open("balanced_connected_sample.triples.jsonl", "w", encoding="utf-8") as f:
        for tr in best_solution["triples"]:
            f.write(json.dumps(tr, ensure_ascii=False) + "\n")

    with open("balanced_connected_sample.metadata.json", "w", encoding="utf-8") as f:
        meta = {k: v for (k, v) in best_solution.items() if k != "triples"}
        json.dump(meta, f, indent=2, ensure_ascii=False)

    logger.info("Wrote balanced_connected_sample.triples.jsonl and balanced_connected_sample.metadata.json")


if __name__ == "__main__":
    main()
