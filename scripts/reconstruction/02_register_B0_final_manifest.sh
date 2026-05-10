#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_common.sh"

parse_force_only_args "$@"

cd "${REPO_ROOT}"

REBUILD_DIR="${RECON_REBUILD_DIR}"
SELECTED_GRAPH="${RECON_B0_GRAPH}"
ALLOCATION="${RECON_ALLOCATION}"
REAUDIT_REPORT="${REBUILD_DIR}/B0_reaudit.report.json"
ORIGINAL_MANIFEST="artifacts/final_graph/selected_final_graph/final_graph_manifest.json"
DECISION_DOC="docs/reconstruction/19_final_graph_selection_decision.md"
FINAL_DECISION_MD="artifacts/final_graph/selected_final_graph/final_graph_decision.md"

MANIFEST_OUT="${REBUILD_DIR}/final_graph_manifest.rebuilt.json"
METRICS_OUT="${REBUILD_DIR}/final_graph_metrics.rebuilt.json"
HASHES_OUT="${REBUILD_DIR}/final_graph_hashes.rebuilt.tsv"

EXPECTED_GRAPH_SHA="${RECON_EXPECTED_B0_SHA}"
EXPECTED_ALLOCATION_SHA="${RECON_EXPECTED_ALLOCATION_SHA}"

require_files \
  "${SELECTED_GRAPH}" \
  "${ALLOCATION}" \
  "${REAUDIT_REPORT}" \
  "${ORIGINAL_MANIFEST}" \
  "${DECISION_DOC}" \
  "${FINAL_DECISION_MD}"

refuse_overwrite_unless_force "${FORCE}" "${MANIFEST_OUT}" "${METRICS_OUT}" "${HASHES_OUT}"

safe_mkdir "${REBUILD_DIR}"

"${PYTHON_BIN}" - \
  "${SELECTED_GRAPH}" \
  "${ALLOCATION}" \
  "${REAUDIT_REPORT}" \
  "${ORIGINAL_MANIFEST}" \
  "${DECISION_DOC}" \
  "${FINAL_DECISION_MD}" \
  "${MANIFEST_OUT}" \
  "${METRICS_OUT}" \
  "${HASHES_OUT}" \
  "${EXPECTED_GRAPH_SHA}" \
  "${EXPECTED_ALLOCATION_SHA}" <<'PY'
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    selected_graph,
    allocation,
    reaudit_report,
    original_manifest,
    decision_doc,
    final_decision_md,
    manifest_out,
    metrics_out,
    hashes_out,
    expected_graph_sha,
    expected_allocation_sha,
) = [Path(x) for x in sys.argv[1:10]] + sys.argv[10:12]

selected_graph = Path(selected_graph)
allocation = Path(allocation)
reaudit_report = Path(reaudit_report)
original_manifest = Path(original_manifest)
decision_doc = Path(decision_doc)
final_decision_md = Path(final_decision_md)
manifest_out = Path(manifest_out)
metrics_out = Path(metrics_out)
hashes_out = Path(hashes_out)

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)

graph_sha = sha256(selected_graph)
allocation_sha = sha256(allocation)
if graph_sha != expected_graph_sha:
    raise SystemExit(f"selected graph SHA mismatch: {graph_sha}")
if allocation_sha != expected_allocation_sha:
    raise SystemExit(f"allocation SHA mismatch: {allocation_sha}")

report = load_json(reaudit_report)
original = load_json(original_manifest)
graph_metrics = report["graph_metrics"]
allocation_metrics = report["allocation_metrics"]

if report.get("graph_sha256") != graph_sha:
    raise SystemExit("reaudit report graph SHA does not match selected graph")
if report.get("allocation_sha256") != allocation_sha:
    raise SystemExit("reaudit report allocation SHA does not match allocation")

manifest = {
    "rebuilt_on": datetime.now(timezone.utc).isoformat(),
    "rebuild_script": "scripts/reconstruction/02_register_B0_final_manifest.sh",
    "selected_candidate_id": "B0",
    "selected_graph_path": str(selected_graph),
    "selected_graph_sha256": graph_sha,
    "selected_graph_type": "csv_h_r_t",
    "allocation_path": str(allocation),
    "allocation_sha256": allocation_sha,
    "reaudit_report_path": str(reaudit_report),
    "reaudit_report_sha256": sha256(reaudit_report),
    "original_manifest_path": str(original_manifest),
    "original_manifest_sha256": sha256(original_manifest),
    "decision_document_path": str(decision_doc),
    "decision_document_sha256": sha256(decision_doc),
    "final_graph_decision_path": str(final_decision_md),
    "final_graph_decision_sha256": sha256(final_decision_md),
    "decision_date": original.get("decision_date"),
    "rationale": original.get("rationale"),
    "limitations": original.get("limitations"),
    "rejected_or_nonselected_candidates": original.get("rejected_or_nonselected_candidates", []),
    "explicit_notes": [
        "Documentation-only rebuild.",
        "No graph artifact was copied or modified.",
        "No graph was generated.",
        "Metrics were rebuilt from the duplicate-safe B0 reaudit report.",
        "This does not prove upstream end-to-end reproducibility.",
    ],
}

metrics = {
    "rebuilt_on": manifest["rebuilt_on"],
    "metric_source": str(reaudit_report),
    "selected_candidate_id": "B0",
    "selected_graph_path": str(selected_graph),
    "selected_graph_sha256": graph_sha,
    "allocation_path": str(allocation),
    "allocation_sha256": allocation_sha,
    "raw_total_rows": graph_metrics["raw_total_rows"],
    "unique_triples": graph_metrics["unique_triples"],
    "duplicate_triple_count": graph_metrics["duplicate_triple_count"],
    "unique_entities": graph_metrics["unique_entities"],
    "unique_relations": graph_metrics["unique_relations"],
    "weak_component_count": graph_metrics["weak_component_count"],
    "largest_weak_component_ratio": graph_metrics["largest_weak_component_ratio"],
    "allocated_relations_observed": allocation_metrics["allocated_relations_observed"],
    "zero_allocated_relations": allocation_metrics["zero_allocated_relations"],
    "total_deficit": allocation_metrics["total_deficit"],
    "total_surplus": allocation_metrics["total_surplus"],
    "top_underfilled_relations": allocation_metrics["top_underfilled_relations"],
    "top_overfilled_relations": allocation_metrics["top_overfilled_relations"],
    "notes": [
        "Allocation metrics are computed from unique triples.",
        "No graph artifact was modified.",
    ],
}

manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
metrics_out.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

rows = [
    ("selected_graph", selected_graph, graph_sha),
    ("allocation", allocation, allocation_sha),
    ("reaudit_report", reaudit_report, sha256(reaudit_report)),
    ("original_manifest", original_manifest, sha256(original_manifest)),
    ("decision_document", decision_doc, sha256(decision_doc)),
    ("final_graph_decision", final_decision_md, sha256(final_decision_md)),
    ("rebuilt_manifest", manifest_out, sha256(manifest_out)),
    ("rebuilt_metrics", metrics_out, sha256(metrics_out)),
]
with hashes_out.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["role", "path", "sha256"])
    for role, path, digest in rows:
        writer.writerow([role, str(path), digest])

print(f"rebuilt_manifest={manifest_out}")
print(f"rebuilt_metrics={metrics_out}")
print(f"rebuilt_hashes={hashes_out}")
PY
