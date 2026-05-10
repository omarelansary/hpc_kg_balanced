import argparse
import pandas as pd
from collections import defaultdict
from itertools import product
import os

def load_kg():
    df = pd.read_csv(KG_FILE)
    df.columns = ["h", "r", "t"]
    return df


def build_relation_maps(df):
    rel_triples = defaultdict(set)

    for h, r, t in df.values:
        rel_triples[r].add((h, t))

    return rel_triples


def compute_symmetry(rel_triples):
    results = {}

    for r, pairs in rel_triples.items():
        reversed_pairs = {(t, h) for (h, t) in pairs}

        match = len(pairs & reversed_pairs)
        score = match / max(len(pairs), 1)

        is_sym = score >= SYMMETRY_THRESHOLD

        anti_pairs = [(h, t) for (h, t) in pairs if (t, h) not in pairs and h != t]
        anti_score = len(anti_pairs) / max(len(pairs), 1)

        is_anti = anti_score >= SYMMETRY_THRESHOLD

        results[r] = {
            "symmetric": is_sym,
            "anti_symmetric": is_anti,
            "sym_score": score,
            "anti_score": anti_score,
        }

    return results


def compute_inverse(rel_triples):
    inverse_pairs = defaultdict(list)

    relations = list(rel_triples.keys())

    for r1, r2 in product(relations, relations):
        if r1 == r2:
            continue

        pairs1 = rel_triples[r1]
        pairs2 = rel_triples[r2]

        reversed_pairs2 = {(t, h) for (h, t) in pairs2}

        overlap = len(pairs1 & reversed_pairs2)
        score = overlap / max(len(pairs1), 1)

        if score >= INVERSE_THRESHOLD:
            inverse_pairs[r1].append((r2, score))

    return inverse_pairs


def compute_composition(df, rel_triples):
    composition = defaultdict(list)

    triples_by_head = defaultdict(list)
    for h, r, t in df.values:
        triples_by_head[h].append((r, t))

    for r1 in rel_triples:
        for r2 in rel_triples:
            composed = set()

            for h, r, x in df[df["r"] == r1].values:
                for r_next, t in triples_by_head.get(x, []):
                    if r_next == r2:
                        composed.add((h, t))

            for r3 in rel_triples:
                overlap = len(composed & rel_triples[r3])
                score = overlap / max(len(composed), 1)

                if score >= COMPOSITION_THRESHOLD:
                    composition[r3].append((r1, r2, score))

    return composition


def build_summary(df, rel_triples, sym_res, inv_res, comp_res):
    rows = []

    for r in rel_triples:
        rows.append({
            "relation": r,
            "num_triples": len(rel_triples[r]),
            "symmetric": sym_res[r]["symmetric"],
            "anti_symmetric": sym_res[r]["anti_symmetric"],
            "inverse": int(r in inv_res),
            "composition": int(r in comp_res),
        })

    return pd.DataFrame(rows)


def save_outputs(summary, inv_res, comp_res):
    summary.to_csv(f"{OUTPUT_DIR}/summary.csv", index=False)

    summary[summary["symmetric"] == 1].to_csv(f"{OUTPUT_DIR}/symmetric.csv", index=False)
    summary[summary["anti_symmetric"] == 1].to_csv(f"{OUTPUT_DIR}/anti_symmetric.csv", index=False)
    summary[summary["inverse"] == 1].to_csv(f"{OUTPUT_DIR}/inverse.csv", index=False)
    summary[summary["composition"] == 1].to_csv(f"{OUTPUT_DIR}/composition.csv", index=False)

    inv_rows = []
    for r, pairs in inv_res.items():
        for r2, score in pairs:
            inv_rows.append({"r1": r, "r2": r2, "score": score})

    pd.DataFrame(inv_rows).to_csv(f"{OUTPUT_DIR}/inverse_pairs.csv", index=False)

    comp_rows = []
    for r3, pairs in comp_res.items():
        for r1, r2, score in pairs:
            comp_rows.append({"r3": r3, "r1": r1, "r2": r2, "score": score})

    pd.DataFrame(comp_rows).to_csv(f"{OUTPUT_DIR}/composition_triples.csv", index=False)


def build_pattern_relation_sets(summary, inv_res, comp_res):
    pattern_relations = {
        "symmetric": set(summary[summary["symmetric"] == 1]["relation"]),
        "anti_symmetric": set(summary[summary["anti_symmetric"] == 1]["relation"]),
        "inverse": set(inv_res.keys()),
        "composition": set(comp_res.keys()),
    }
    return pattern_relations


def split_kg_by_patterns(df, pattern_relations):
    pattern_kgs = {}

    for pattern, relations in pattern_relations.items():
        pattern_kgs[pattern] = df[df["r"].isin(relations)]

    return pattern_kgs


def save_pattern_kgs(pattern_kgs):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for pattern, kg_df in pattern_kgs.items():
        kg_df[["h", "r", "t"]].to_csv(
            f"{OUTPUT_DIR}/kg_{pattern}.txt",
            sep="\t",
            index=False,
            header=False
        )


def save_multi_pattern_kgs(df, pattern_relations):
    """
    Create KGs for combinations (e.g., sym+inv, inv+comp)
    """

    combinations = [
        ("sym_inv", ["symmetric", "inverse"]),
        ("sym_comp", ["symmetric", "composition"]),
        ("asym_inv", ["anti_symmetric", "inverse"]),
        ("asym_comp", ["anti_symmetric", "composition"]),
    ]

    for name, pats in combinations:
        rels = set().union(*[pattern_relations[p] for p in pats])
        subset = df[df["r"].isin(rels)]

        subset[["h", "r", "t"]].to_csv(
            f"{OUTPUT_DIR}/kg_{name}.txt",
            sep="\t",
            index=False,
            header=False
        )

def main():
    df = load_kg()

    rel_triples = build_relation_maps(df)

    sym_res = compute_symmetry(rel_triples)
    inv_res = compute_inverse(rel_triples)
    comp_res = compute_composition(df, rel_triples)

    summary = build_summary(df, rel_triples, sym_res, inv_res, comp_res)

    save_outputs(summary, inv_res, comp_res)

    # NEW PART
    pattern_relations = build_pattern_relation_sets(summary, inv_res, comp_res)

    pattern_kgs = split_kg_by_patterns(df, pattern_relations)

    save_pattern_kgs(pattern_kgs)

    save_multi_pattern_kgs(df, pattern_relations)

    print("Pattern-based KGs saved.")


def parse_args():
    parser = argparse.ArgumentParser(description="Compute simple KG pattern statistics for a CSV with columns h,r,t.")
    parser.add_argument("--kg_file", required=True, help="Input KG CSV path")
    parser.add_argument("--output_dir", required=True, help="Directory for summary outputs")
    parser.add_argument("--symmetry_threshold", type=float, default=0.9)
    parser.add_argument("--inverse_threshold", type=float, default=0.9)
    parser.add_argument("--composition_threshold", type=float, default=0.5)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    KG_FILE = args.kg_file
    OUTPUT_DIR = args.output_dir
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    SYMMETRY_THRESHOLD = args.symmetry_threshold
    INVERSE_THRESHOLD = args.inverse_threshold
    COMPOSITION_THRESHOLD = args.composition_threshold
    main()
