import argparse
import pandas as pd


def extract_2paths(kg_path: str, out_path: str):
    kg = pd.read_csv(kg_path)

    # ensure correct column names
    kg.columns = ["h", "r", "t"]

    paths = []

    # group by head for fast lookup
    head_to_triples = kg.groupby("h")
    loops = 0
    for _, row in kg.iterrows():
        h, r1, mid = row["h"], row["r"], row["t"]

        # self-loop skip (optional)
        if h == mid:
            loops += 1
            continue

        # find second hop
        if mid in head_to_triples.groups:
            next_triples = head_to_triples.get_group(mid)

            for _, row2 in next_triples.iterrows():
                r2, t = row2["r"], row2["t"]

                paths.append((h, r1, r2, t))

    # save
    df = pd.DataFrame(paths, columns=["h", "r1", "r2", "t"])
    df.to_csv(out_path, index=False)
    print(f"loops: {loops}")
    n_ent = pd.concat([kg.h, kg.t])
    print(n_ent.head())
    print(f"Entities with duplicates {len(n_ent)}")
    n_ent.drop_duplicates(inplace=True)
    print(f"n_ent: {len(n_ent)}")
    print(f"Triples: {kg.shape[0]}")
    print(f"Saved {len(df)} 2-paths → {out_path}")
    return df


def parse_args():
    parser = argparse.ArgumentParser(description="Extract all 2-hop paths from a KG CSV with columns h,r,t.")
    parser.add_argument("--kg_file", required=True, help="Input KG CSV path")
    parser.add_argument("--out_path", required=True, help="Output CSV path for extracted 2-paths")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    df = extract_2paths(args.kg_file, args.out_path)
    df_tuples = set(df.itertuples(index=False, name=None))
    count_sym = 0
    count_inv = 0
    count_commutative = 0
    count_uncommutative = 0
    for _, row in df.iterrows():
        if row["h"] == row["t"]:
            if row["r1"] == row["r2"]:
                count_sym += 1
            else:
                count_inv += 1
        elif (row["h"], row["r2"], row["r1"], row["t"]) in df_tuples:
            count_commutative += 1
        else:
            count_uncommutative += 1
    print(f"Symmetries: {count_sym}")
    print(f"Inverses: {count_inv}")
    print(f"Commutatives: {count_commutative}")
    print(f"Uncommutatives: {count_uncommutative}")
