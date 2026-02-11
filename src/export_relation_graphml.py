#!/usr/bin/env python3
import argparse, csv, math
import networkx as nx

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edges_csv", required=True)
    ap.add_argument("--out", default="relation_graph.graphml")
    ap.add_argument("--use_weight", choices=["support","log1p"], default="log1p")
    args = ap.parse_args()

    G = nx.DiGraph()
    with open(args.edges_csv, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            r1 = row["r1"]; r2 = row["r2"]
            support = int(float(row["support"]))
            w = support if args.use_weight == "support" else math.log1p(max(0, support))
            G.add_edge(r1, r2, support=support, weight=w)

    nx.write_graphml(G, args.out)
    print(f"Wrote {args.out} with |V|={G.number_of_nodes()} |E|={G.number_of_edges()}")

if __name__ == "__main__":
    main()
