#!/bin/bash
# Sweep revised Stage13 pruning experiments and auto-summarize results.
#
# Usage:
#   chmod +x run_stage13_branch_sweep.sh
#   ./run_stage13_branch_sweep.sh
#
# Optional overrides:
#   SWEEP_NAME=my_sweep \
#   BASE_RUN_DIR='src/Pruning graph/.../stage12_path_repair_prod' \
#   WRAPPER='scripts/slurm/stage13_balance_prune_revised_density_aware.slurm' \
#   ./run_stage13_branch_sweep.sh
#
# What it does:
# 1. submits a small set of branch-diagnostic runs via sbatch
# 2. records job ids + prune dirs in a manifest
# 3. submits one dependent summary job that runs after all experiments finish
# 4. writes:
#    - manifest.tsv
#    - summary.csv
#    - summary.md
#
# You can then inspect which branch is alive:
# - tuning branch: P31/P279 begin to move under softer structural penalties
# - backbone branch: even softened runs barely touch P31/P279
# - two-stage branch: pruning improves only peripheral relations and stalls

set -euo pipefail

SWEEP_NAME="${SWEEP_NAME:-stage13_branch_sweep_$(date +%Y%m%d_%H%M%S)}"
BASE_RUN_DIR="${BASE_RUN_DIR:-src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod}"
WRAPPER="${WRAPPER:-scripts/slurm/stage13_balance_prune_revised_density_aware.slurm}"
SWEEP_DIR="${SWEEP_DIR:-${BASE_RUN_DIR}/${SWEEP_NAME}}"
MANIFEST="${SWEEP_DIR}/manifest.tsv"
SUMMARY_JOB_SCRIPT="${SWEEP_DIR}/_summarize_after_runs.sh"

mkdir -p "${SWEEP_DIR}"

if [[ ! -f "${WRAPPER}" ]]; then
  echo "Missing wrapper: ${WRAPPER}" >&2
  exit 1
fi

if ! command -v sbatch >/dev/null 2>&1; then
  echo "sbatch not found in PATH." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "No python interpreter found." >&2
  exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

# ------------------------------------------------------------------------------
# Experiment definitions
# ------------------------------------------------------------------------------
# Format:
# name|ENV1=... ENV2=... ENV3=...
#
# Notes:
# - baseline_safe: current safe branch, should barely move
# - structural_softening: tests whether P31/P279 are blocked mainly by structure penalties
# - stronger_balance: tests whether more balance pressure unlocks useful removals
# - p31_floor_relax: tests whether P31 floor is the blocker
# - density_loosen: tests whether absolute density targets are too tight
# - aggressive_but_guarded: stress test while keeping reject_round + connectivity
#
# Keep DEBUG enabled so you can inspect P31/P279 behavior without rerunning.

EXPERIMENTS=(
"baseline_safe|PATTERN_SURPLUS_WEIGHT=12 RELATION_OVERCAP_WEIGHT=3 DENSITY_TRIPLES_PER_ENTITY_PENALTY=5 DENSITY_ENTITIES_PER_TRIPLE_PENALTY=5 PROJECTED_LOW_DEGREE_CREATION_PENALTY=8 TWO_PATH_LOSS_PENALTY=0.25 MAX_TOTAL_REMOVALS=2000 MAX_FRACTION_PER_RELATION_PER_ROUND=0.20 MAX_REMOVALS_PER_RELATION_PER_ROUND=8 TARGET_MIN_TRIPLES_PER_ENTITY=1.02 TARGET_MAX_ENTITIES_PER_TRIPLE=0.98 TARGET_MIN_AVERAGE_PARTICIPATION=2.04 MIN_POST_ROUND_TRIPLES_PER_ENTITY=1.02 MAX_POST_ROUND_ENTITIES_PER_TRIPLE=0.98 MIN_POST_ROUND_AVERAGE_PARTICIPATION=2.04 HARD_RELATION_MIN_COUNTS='P31=5000,P279=650'"
"structural_softening|PATTERN_SURPLUS_WEIGHT=15 RELATION_OVERCAP_WEIGHT=4 DENSITY_TRIPLES_PER_ENTITY_PENALTY=3 DENSITY_ENTITIES_PER_TRIPLE_PENALTY=3 PROJECTED_LOW_DEGREE_CREATION_PENALTY=2 TWO_PATH_LOSS_PENALTY=0.05 ARTICULATION_ENDPOINT_PENALTY=10 MAX_TOTAL_REMOVALS=2000 MAX_FRACTION_PER_RELATION_PER_ROUND=0.20 MAX_REMOVALS_PER_RELATION_PER_ROUND=8 TARGET_MIN_TRIPLES_PER_ENTITY=1.02 TARGET_MAX_ENTITIES_PER_TRIPLE=0.98 TARGET_MIN_AVERAGE_PARTICIPATION=2.04 MIN_POST_ROUND_TRIPLES_PER_ENTITY=1.02 MAX_POST_ROUND_ENTITIES_PER_TRIPLE=0.98 MIN_POST_ROUND_AVERAGE_PARTICIPATION=2.04 HARD_RELATION_MIN_COUNTS='P31=5000,P279=650'"
"stronger_balance|PATTERN_SURPLUS_WEIGHT=18 RELATION_OVERCAP_WEIGHT=5 DENSITY_TRIPLES_PER_ENTITY_PENALTY=3 DENSITY_ENTITIES_PER_TRIPLE_PENALTY=3 PROJECTED_LOW_DEGREE_CREATION_PENALTY=5 TWO_PATH_LOSS_PENALTY=0.10 MAX_TOTAL_REMOVALS=2500 MAX_FRACTION_PER_RELATION_PER_ROUND=0.25 MAX_REMOVALS_PER_RELATION_PER_ROUND=10 TARGET_MIN_TRIPLES_PER_ENTITY=1.02 TARGET_MAX_ENTITIES_PER_TRIPLE=0.98 TARGET_MIN_AVERAGE_PARTICIPATION=2.04 MIN_POST_ROUND_TRIPLES_PER_ENTITY=1.02 MAX_POST_ROUND_ENTITIES_PER_TRIPLE=0.98 MIN_POST_ROUND_AVERAGE_PARTICIPATION=2.04 HARD_RELATION_MIN_COUNTS='P31=5000,P279=650'"
"p31_floor_relax|PATTERN_SURPLUS_WEIGHT=15 RELATION_OVERCAP_WEIGHT=4 DENSITY_TRIPLES_PER_ENTITY_PENALTY=3 DENSITY_ENTITIES_PER_TRIPLE_PENALTY=3 PROJECTED_LOW_DEGREE_CREATION_PENALTY=5 TWO_PATH_LOSS_PENALTY=0.10 MAX_TOTAL_REMOVALS=2000 MAX_FRACTION_PER_RELATION_PER_ROUND=0.20 MAX_REMOVALS_PER_RELATION_PER_ROUND=8 TARGET_MIN_TRIPLES_PER_ENTITY=1.02 TARGET_MAX_ENTITIES_PER_TRIPLE=0.98 TARGET_MIN_AVERAGE_PARTICIPATION=2.04 MIN_POST_ROUND_TRIPLES_PER_ENTITY=1.02 MAX_POST_ROUND_ENTITIES_PER_TRIPLE=0.98 MIN_POST_ROUND_AVERAGE_PARTICIPATION=2.04 HARD_RELATION_MIN_COUNTS='P31=4500,P279=650'"
"density_loosen|PATTERN_SURPLUS_WEIGHT=15 RELATION_OVERCAP_WEIGHT=4 DENSITY_TRIPLES_PER_ENTITY_PENALTY=2 DENSITY_ENTITIES_PER_TRIPLE_PENALTY=2 PROJECTED_LOW_DEGREE_CREATION_PENALTY=5 TWO_PATH_LOSS_PENALTY=0.05 MAX_TOTAL_REMOVALS=2500 MAX_FRACTION_PER_RELATION_PER_ROUND=0.20 MAX_REMOVALS_PER_RELATION_PER_ROUND=8 TARGET_MIN_TRIPLES_PER_ENTITY=1.00 TARGET_MAX_ENTITIES_PER_TRIPLE=1.00 TARGET_MIN_AVERAGE_PARTICIPATION=2.00 MIN_POST_ROUND_TRIPLES_PER_ENTITY=1.00 MAX_POST_ROUND_ENTITIES_PER_TRIPLE=1.00 MIN_POST_ROUND_AVERAGE_PARTICIPATION=2.00 HARD_RELATION_MIN_COUNTS='P31=5000,P279=650'"
"aggressive_but_guarded|PATTERN_SURPLUS_WEIGHT=20 RELATION_OVERCAP_WEIGHT=6 DENSITY_TRIPLES_PER_ENTITY_PENALTY=2 DENSITY_ENTITIES_PER_TRIPLE_PENALTY=2 PROJECTED_LOW_DEGREE_CREATION_PENALTY=3 TWO_PATH_LOSS_PENALTY=0.05 ARTICULATION_ENDPOINT_PENALTY=8 MAX_TOTAL_REMOVALS=3500 MAX_FRACTION_PER_RELATION_PER_ROUND=0.30 MAX_REMOVALS_PER_RELATION_PER_ROUND=15 TARGET_MIN_TRIPLES_PER_ENTITY=1.00 TARGET_MAX_ENTITIES_PER_TRIPLE=1.00 TARGET_MIN_AVERAGE_PARTICIPATION=2.00 MIN_POST_ROUND_TRIPLES_PER_ENTITY=1.00 MAX_POST_ROUND_ENTITIES_PER_TRIPLE=1.00 MIN_POST_ROUND_AVERAGE_PARTICIPATION=2.00 HARD_RELATION_MIN_COUNTS='P31=4500,P279=600'"
)

cat > "${MANIFEST}" <<'EOF'
name	job_id	prune_dir	report_path	debug_path
EOF

job_ids=()

submit_one() {
  local name="$1"
  local env_overrides="$2"
  local prune_dir="${SWEEP_DIR}/${name}"
  local debug_path="${prune_dir}/pruned_graph.debug.json"
  local submit_cmd
  local job_id

  mkdir -p "${prune_dir}"

  # Always keep these debug signals on across experiments.
  local common_env="PRUNE_DIR=${prune_dir} DEBUG_DUMP_PATH=${debug_path} DEBUG_TOP_CANDIDATES=50 DEBUG_RELATIONS='P31,P279'"

  # shellcheck disable=SC2086
  submit_cmd="${common_env} ${env_overrides} sbatch --parsable ${WRAPPER}"
  echo "Submitting ${name}..."
  # shellcheck disable=SC2086
  job_id=$(eval ${submit_cmd})
  echo -e "${name}\t${job_id}\t${prune_dir}\t${prune_dir}/pruned_graph.report.json\t${debug_path}" >> "${MANIFEST}"
  job_ids+=("${job_id}")
}

for spec in "${EXPERIMENTS[@]}"; do
  name="${spec%%|*}"
  env_overrides="${spec#*|}"
  submit_one "${name}" "${env_overrides}"
done

dep_string="$(IFS=:; echo "${job_ids[*]}")"

cat > "${SUMMARY_JOB_SCRIPT}" <<'EOF'
#!/bin/bash
set -euo pipefail

MANIFEST="$1"
OUT_CSV="$2"
OUT_MD="$3"

PYTHON_BIN="$(command -v python3 || command -v python)"

"${PYTHON_BIN}" - "$MANIFEST" "$OUT_CSV" "$OUT_MD" <<'PY'
import csv
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
out_csv = Path(sys.argv[2])
out_md = Path(sys.argv[3])

rows = []
with manifest_path.open("r", encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter="\t")
    for row in reader:
        rows.append(row)

def load_json(path_str):
    p = Path(path_str)
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def top_relation_counts(report, n=5):
    if not report:
        return ""
    items = sorted(report.get("relation_removal_counts", {}).items(), key=lambda kv: (-kv[1], kv[0]))
    return "; ".join(f"{k}:{v}" for k, v in items[:n])

def objective(report, key):
    if not report:
        return ""
    return report.get("final_objective_metrics", {}).get(key, "")

def top_debug_relation(debug, relation):
    if not debug:
        return None
    rr = debug.get("debug_relations", {}).get(relation, {})
    rounds = rr.get("round_summaries", [])
    if not rounds:
        return None
    best = max(rounds, key=lambda x: x.get("max_score", float("-inf")))
    return {
        "candidate_count": best.get("candidate_count"),
        "positive_score_count": best.get("positive_score_count"),
        "max_score": best.get("max_score"),
    }

summary_rows = []
for row in rows:
    report = load_json(row["report_path"])
    debug = load_json(row["debug_path"])
    p31 = top_debug_relation(debug, "P31")
    p279 = top_debug_relation(debug, "P279")
    summary_rows.append({
        "name": row["name"],
        "job_id": row["job_id"],
        "total_removed": "" if not report else report.get("total_removed", ""),
        "rounds_completed": "" if not report else report.get("rounds_completed", ""),
        "triples_minus_entities": objective(report, "triples_minus_entities"),
        "triples_per_entity": objective(report, "triples_per_entity"),
        "entities_per_triple": objective(report, "entities_per_triple"),
        "average_participation": objective(report, "average_participation"),
        "weak_component_count": objective(report, "weak_component_count"),
        "largest_component_ratio": objective(report, "largest_component_ratio"),
        "guards": "" if not report else report.get("any_guard_triggered", ""),
        "target_floor_guard": "" if not report else report.get("any_target_floor_guard_triggered", ""),
        "relation_floor_guard": "" if not report else report.get("any_relation_floor_guard_triggered", ""),
        "top_removed_relations": top_relation_counts(report, n=5),
        "P31_best_positive_count": "" if p31 is None else p31["positive_score_count"],
        "P31_best_max_score": "" if p31 is None else p31["max_score"],
        "P279_best_positive_count": "" if p279 is None else p279["positive_score_count"],
        "P279_best_max_score": "" if p279 is None else p279["max_score"],
        "report_path": row["report_path"],
        "debug_path": row["debug_path"],
    })

fieldnames = list(summary_rows[0].keys()) if summary_rows else [
    "name","job_id","total_removed","rounds_completed","triples_minus_entities",
    "triples_per_entity","entities_per_triple","average_participation",
    "weak_component_count","largest_component_ratio","guards","target_floor_guard",
    "relation_floor_guard","top_removed_relations","P31_best_positive_count",
    "P31_best_max_score","P279_best_positive_count","P279_best_max_score",
    "report_path","debug_path"
]

out_csv.parent.mkdir(parents=True, exist_ok=True)
with out_csv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(summary_rows)

with out_md.open("w", encoding="utf-8") as f:
    f.write("# Stage13 branch sweep summary\n\n")
    f.write("| name | removed | rounds | T-E | T/E | E/T | avg part | comps | LCC ratio | guards | P31 +score | P31 max | P279 +score | P279 max | top removed |\n")
    f.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|\n")
    for r in summary_rows:
        f.write(
            f"| {r['name']} | {r['total_removed']} | {r['rounds_completed']} | {r['triples_minus_entities']} | "
            f"{r['triples_per_entity']} | {r['entities_per_triple']} | {r['average_participation']} | "
            f"{r['weak_component_count']} | {r['largest_component_ratio']} | {r['guards']} | "
            f"{r['P31_best_positive_count']} | {r['P31_best_max_score']} | "
            f"{r['P279_best_positive_count']} | {r['P279_best_max_score']} | {r['top_removed_relations']} |\n"
        )

    f.write("\n## Quick reading guide\n\n")
    f.write("- If **P31/P279 positive-score counts** stay near zero across all runs, pruning-only is probably not enough.\n")
    f.write("- If a softer-structure run increases **P31 positive-score counts** materially without breaking density/connectivity, the tuning branch is alive.\n")
    f.write("- If runs mostly remove peripheral relations while **P31/P279 remain non-removable**, the backbone or two-stage branch is more likely.\n")
    f.write("- Use the report/debug paths in the CSV for deep inspection.\n")
PY
EOF

chmod +x "${SUMMARY_JOB_SCRIPT}"

SUMMARY_JOB_ID=$(sbatch --parsable --dependency=afterany:${dep_string} --job-name="${SWEEP_NAME}_summary" --output="${SWEEP_DIR}/summary_%j.out" --error="${SWEEP_DIR}/summary_%j.err" --wrap "${SUMMARY_JOB_SCRIPT} '${MANIFEST}' '${SWEEP_DIR}/summary.csv' '${SWEEP_DIR}/summary.md'")

echo
echo "Sweep submitted."
echo "Sweep dir: ${SWEEP_DIR}"
echo "Manifest:  ${MANIFEST}"
echo "Summary job: ${SUMMARY_JOB_ID}"
echo "Experiment job ids: ${job_ids[*]}"
echo
echo "When all jobs finish, inspect:"
echo "  ${SWEEP_DIR}/summary.csv"
echo "  ${SWEEP_DIR}/summary.md"
