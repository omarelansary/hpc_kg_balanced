
#!/usr/bin/env python3
"""
kg_builder.py

A single-file, modular, resumable pipeline for relation-balanced knowledge graph
construction from a frozen candidate universe.

Design goals:
- deterministic behavior
- no silent overwrites
- append-only stage outputs
- resumable collection/checkpoint semantics
- clear CLI subcommands
- auditability
- crash-safe segment finalization
- streaming JSONL stage I/O where practical
- optional local multithreading for CPU-light independent work

Notes
-----
This implementation is intentionally production-oriented but generic. It includes:
- run directory management
- config loading (YAML if available, JSON fallback)
- data schemas
- stage manifests and summaries
- candidate annotation and audit
- deterministic graph construction
- bounded repair
- weak-component filtering
- final audit

What is intentionally left as project-specific integration:
- exact WDQS query text and chunking logic
- exact ontology resource loading format
- exact hop-support matrix resource loading format
- candidate retrieval backends

Those project-specific adapters are isolated behind small interfaces so that the
rest of the pipeline remains testable and rerunnable.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
from dataclasses import dataclass, asdict, field
import datetime as dt
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import random
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

try:
    import requests  # type: ignore
except Exception:
    requests = None


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG = logging.getLogger("kg_builder")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding=encoding) as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True))


class JsonlSegmentWriter:
    """
    Crash-safe JSONL segment writer.

    Writes to a temporary path and atomically promotes to final path on success.
    The caller should write one segment per worker/task/chunk to avoid concurrent
    append corruption.
    """

    def __init__(self, final_path: Path):
        self.final_path = final_path
        ensure_dir(final_path.parent)
        self.tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
        self._fh = open(self.tmp_path, "w", encoding="utf-8")

    def write(self, obj: Dict[str, Any]) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")

    def close_and_promote(self) -> None:
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._fh.close()
        os.replace(self.tmp_path, self.final_path)

    def abort(self) -> None:
        try:
            self._fh.close()
        finally:
            if self.tmp_path.exists():
                self.tmp_path.unlink(missing_ok=True)


def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL in {path} line {line_no}: {e}") from e


def list_jsonl_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.jsonl") if p.is_file())


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Config and run context
# ---------------------------------------------------------------------------

@dataclass
class Config:
    run_root: str = "runs"
    seed: int = 7
    max_workers: int = 4
    use_threads_for_local_stages: bool = True

    allocated_relations_path: str = "inputs/allocated_relations.jsonl"
    ontology_compatibility_path: Optional[str] = None
    support_matrix_path: Optional[str] = None
    candidate_input_path: Optional[str] = None  # pre-collected raw candidates
    candidate_source_mode: str = "auto"  # auto | local | wdqs
    wdqs_endpoint: str = "https://query.wikidata.org/sparql"
    wdqs_user_agent: str = "kg_builder/1.0 (Codex relation-balanced pipeline)"
    wdqs_timeout_sec: int = 60
    wdqs_page_size: int = 250
    wdqs_order_results: bool = False
    wdqs_overfetch_factor: float = 3.0
    wdqs_max_raw_candidates_per_relation: int = 15000
    wdqs_pause_between_pages_sec: float = 0.25
    wdqs_max_retries: int = 5
    wdqs_backoff_base_sec: float = 2.0
    wdqs_backoff_cap_sec: float = 30.0
    wdqs_require_entity_targets: bool = True
    generic_manual_risk_relations: List[str] = field(default_factory=lambda: ["P31", "P279", "P131", "P17"])

    genericity_support_threshold: float = 1e-12
    genericity_coverage_threshold: float = 0.80
    genericity_top_mass_quantile: float = 0.90

    candidate_alpha: int = 5
    candidate_beta: int = 20
    candidate_floor: int = 40
    candidate_hard_cap_per_relation: int = 2000
    small_relation_full_retrieval_threshold: int = 300

    global_triple_budget: int = 3000
    bridge_seed_count: int = 10
    hard_relation_seed_count: int = 20
    per_relation_seed_cap: int = 2

    weight_relation_need: float = 3.0
    weight_first_realization_bonus: float = 8.0
    weight_attachability: float = 2.0
    weight_bridge: float = 2.0
    weight_component_merge: float = 3.0
    weight_hub_penalty: float = 1.5
    weight_genericity_penalty: float = 1.25
    weight_noise_penalty: float = 1.25

    weak_component_min_triples: int = 3
    weak_component_min_entities: int = 3

    allow_auxiliary_last_resort_repair: bool = False
    auxiliary_repair_relations_path: Optional[str] = None

    @staticmethod
    def load(path: Path) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if path.suffix.lower() in {".yaml", ".yml"}:
            if yaml is None:
                raise RuntimeError("PyYAML is not installed. Use JSON config or install pyyaml.")
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        return Config(**(data or {}))


@dataclass
class RunContext:
    config: Config
    run_dir: Path
    manifest_path: Path

    @staticmethod
    def create(config: Config, run_name: Optional[str] = None) -> "RunContext":
        root = Path(config.run_root)
        ensure_dir(root)
        if run_name is None:
            ts = dt.datetime.now().strftime("run_%Y_%m_%d_%H%M%S")
            run_name = ts
        run_dir = root / run_name
        if run_dir.exists():
            raise FileExistsError(f"Run directory already exists: {run_dir}")
        ensure_dir(run_dir)
        ensure_dir(run_dir / "logs")
        ctx = RunContext(config=config, run_dir=run_dir, manifest_path=run_dir / "manifest.json")
        ctx.write_manifest({
            "created_at": utc_now_iso(),
            "run_dir": str(run_dir),
            "seed": config.seed,
            "python_version": sys.version,
            "config": dataclasses.asdict(config),
            "stages": {},
        })
        if yaml is not None:
            atomic_write_text(run_dir / "config_snapshot.yaml", yaml.safe_dump(dataclasses.asdict(config), sort_keys=True))
        else:
            atomic_write_json(run_dir / "config_snapshot.json", dataclasses.asdict(config))
        return ctx

    @staticmethod
    def open_existing(config: Config, run_dir: Path) -> "RunContext":
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory does not exist: {run_dir}")
        return RunContext(config=config, run_dir=run_dir, manifest_path=run_dir / "manifest.json")

    def read_manifest(self) -> Dict[str, Any]:
        return read_json(self.manifest_path)

    def write_manifest(self, manifest: Dict[str, Any]) -> None:
        atomic_write_json(self.manifest_path, manifest)

    def update_stage(self, stage_name: str, payload: Dict[str, Any]) -> None:
        manifest = self.read_manifest()
        manifest.setdefault("stages", {})
        manifest["stages"][stage_name] = payload
        manifest["updated_at"] = utc_now_iso()
        self.write_manifest(manifest)

    def stage_dir(self, name: str) -> Path:
        path = self.run_dir / name
        ensure_dir(path)
        return path

    def stage_payload(self, stage_name: str) -> Optional[Dict[str, Any]]:
        if not self.manifest_path.exists():
            return None
        manifest = self.read_manifest()
        return manifest.get("stages", {}).get(stage_name)

    def stage_completed(self, stage_name: str) -> bool:
        return self.stage_payload(stage_name) is not None


def ensure_stage_can_write_once(ctx: RunContext, stage_name: str, expected_outputs: Sequence[Path]) -> None:
    if ctx.stage_completed(stage_name):
        raise RuntimeError(
            f"Stage {stage_name} is already completed for run {ctx.run_dir}. "
            "Create a new run or continue with a later stage instead of overwriting it."
        )

    existing_outputs = [str(path) for path in expected_outputs if path.exists()]
    if existing_outputs:
        raise RuntimeError(
            f"Stage {stage_name} has existing outputs but is not marked complete. "
            f"Refusing to overwrite: {existing_outputs}"
        )


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RelationAllocation:
    relation: str
    eta_integer: int
    eta_total: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_record(rec: Dict[str, Any]) -> "RelationAllocation":
        relation = rec["relation"]
        eta_integer = int(rec["eta_integer"])
        md = dict(rec)
        md.pop("relation", None)
        md.pop("eta_integer", None)
        return RelationAllocation(
            relation=relation,
            eta_integer=eta_integer,
            eta_total=rec.get("eta_total"),
            metadata=md,
        )


@dataclass
class GenericityRecord:
    relation: str
    coverage_score: float
    support_mass_score: float
    candidate_volume_score: float
    manual_structural_risk: float
    genericity_score: float
    genericity_bucket: str


@dataclass
class CandidateRecord:
    triple_id: str
    h: str
    r: str
    t: str
    genericity_score: float
    genericity_bucket: str
    collection_mode: str
    hub_penalty: float
    shortcut_risk: float
    ontology_ok: bool
    self_loop_flag: bool
    quality_score: float
    source_stage: str
    chunk_id: Optional[str] = None
    query_id: Optional[str] = None
    retrieved_at: Optional[str] = None
    run_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> Dict[str, Any]:
        rec = asdict(self)
        extra = rec.pop("extra", {}) or {}
        for key, value in extra.items():
            if key not in rec:
                rec[key] = value
        return rec


@dataclass
class TripleSelectionRecord:
    triple_id: str
    h: str
    r: str
    t: str
    layer: str  # core | auxiliary_repair
    score: float
    selection_reason: str
    relation_need_score: float
    first_realization_bonus: float
    attachability_score: float
    bridge_score: float
    component_merge_score: float
    hub_penalty: float
    genericity_penalty: float
    noise_penalty: float
    structurally_weak: bool = False

    def to_record(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Resource loading
# ---------------------------------------------------------------------------

def iter_allocation_records(path: Path) -> Iterator[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        yield from read_jsonl(path)
        return

    if suffix != ".json":
        raise ValueError(
            f"Unsupported allocated relations format for {path}. "
            "Use JSONL, or JSON with a top-level allocations list."
        )

    obj = read_json(path)
    if isinstance(obj, dict) and isinstance(obj.get("allocations"), list):
        for idx, rec in enumerate(obj["allocations"]):
            if not isinstance(rec, dict):
                raise ValueError(
                    f"Invalid allocations[{idx}] in {path}: expected object, got {type(rec).__name__}"
                )
            yield rec
        return

    if isinstance(obj, list):
        for idx, rec in enumerate(obj):
            if not isinstance(rec, dict):
                raise ValueError(
                    f"Invalid allocation record {idx} in {path}: expected object, got {type(rec).__name__}"
                )
            yield rec
        return

    raise ValueError(
        f"Unsupported JSON structure for allocated relations in {path}. "
        "Expected a list of records or a dict with an allocations list."
    )


def unique_preserving_order(values: Iterable[Any]) -> List[Any]:
    out: List[Any] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def load_allocated_relations(path: Path) -> List[RelationAllocation]:
    merged_records: Dict[str, Dict[str, Any]] = {}
    metadata_values: Dict[str, Dict[str, List[Any]]] = defaultdict(lambda: defaultdict(list))
    duplicate_relation_count = 0

    for rec in iter_allocation_records(path):
        eta_integer = int(rec.get("eta_integer", 0))
        if eta_integer <= 0:
            continue
        relation = rec["relation"]
        eta_total_present = rec.get("eta_total") is not None
        if relation in merged_records:
            duplicate_relation_count += 1
        else:
            merged_records[relation] = {
                "relation": relation,
                "eta_integer": 0,
                "eta_total": 0.0 if eta_total_present else None,
            }

        merged = merged_records[relation]
        merged["eta_integer"] += eta_integer
        if eta_total_present:
            if merged.get("eta_total") is None:
                merged["eta_total"] = 0.0
            merged["eta_total"] += safe_float(rec.get("eta_total"), 0.0)

        for key, value in rec.items():
            if key in {"relation", "eta_integer", "eta_total"}:
                continue
            metadata_values[relation][key].append(value)

    for relation, merged in merged_records.items():
        for key, values in metadata_values[relation].items():
            uniq_values = unique_preserving_order(values)
            merged[key] = uniq_values[0] if len(uniq_values) == 1 else uniq_values

    items = [RelationAllocation.from_record(rec) for rec in merged_records.values()]
    rels = [x.relation for x in items]
    if len(rels) != len(set(rels)):
        dupes = [r for r, c in Counter(rels).items() if c > 1]
        raise ValueError(f"Duplicate allocated relations found: {dupes[:10]}")
    if duplicate_relation_count > 0:
        LOG.info(
            "Merged %d duplicate allocation rows across %d unique relations from %s",
            duplicate_relation_count,
            len(items),
            path,
        )
    return items


def load_support_matrix(path: Optional[Path], relations: Sequence[str]) -> Dict[str, Dict[str, float]]:
    """
    Expected format:
    JSON object: { "P31": {"P279": 12.3, ...}, ... }
    or JSONL with fields {row, col, value}
    """
    if path is None or not path.exists():
        LOG.warning("No support matrix supplied; genericity scores will be weaker.")
        return {r: {} for r in relations}
    if path.suffix.lower() == ".json":
        obj = read_json(path)
        return {str(k): {str(k2): safe_float(v2) for k2, v2 in (v or {}).items()} for k, v in obj.items()}
    matrix: Dict[str, Dict[str, float]] = defaultdict(dict)
    for rec in read_jsonl(path):
        row = rec["row"]
        col = rec["col"]
        val = safe_float(rec.get("value", 0.0))
        matrix[row][col] = val
    return matrix


def load_ontology_compatibility(path: Optional[Path]) -> Set[Tuple[str, str, str]]:
    """
    Optional simple compatibility resource.
    Supported JSONL format:
    {"relation":"Pxx","subject_type":"Q...", "object_type":"Q..."}
    """
    out: Set[Tuple[str, str, str]] = set()
    if path is None:
        return out
    p = Path(path)
    if not p.exists():
        LOG.warning("Ontology compatibility path does not exist: %s", p)
        return out
    for rec in read_jsonl(p):
        out.add((rec["relation"], rec["subject_type"], rec["object_type"]))
    return out


# ---------------------------------------------------------------------------
# Genericity scoring
# ---------------------------------------------------------------------------

def quantile_threshold(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    idx = min(len(values_sorted) - 1, max(0, int(math.floor(q * (len(values_sorted) - 1)))))
    return values_sorted[idx]


def score_genericity(
    allocations: List[RelationAllocation],
    support_matrix: Dict[str, Dict[str, float]],
    config: Config,
) -> List[GenericityRecord]:
    rels = [a.relation for a in allocations]
    manual_flag_set = set(config.generic_manual_risk_relations)

    coverage: Dict[str, float] = {}
    support_mass: Dict[str, float] = {}
    for r in rels:
        row = support_matrix.get(r, {})
        non_zero_neighbors = set()
        total_mass = 0.0
        for c in rels:
            val_rc = safe_float(row.get(c, 0.0))
            val_cr = safe_float(support_matrix.get(c, {}).get(r, 0.0))
            if val_rc > config.genericity_support_threshold or val_cr > config.genericity_support_threshold:
                non_zero_neighbors.add(c)
            total_mass += val_rc + val_cr
        coverage[r] = len(non_zero_neighbors) / max(1, len(rels))
        support_mass[r] = total_mass

    masses = list(support_mass.values())
    mass_thr = quantile_threshold(masses, config.genericity_top_mass_quantile)
    max_mass = max(masses) if masses else 1.0

    # volume proxy from eta as a stable first approximation
    max_eta = max((a.eta_integer for a in allocations), default=1)
    out: List[GenericityRecord] = []
    for a in allocations:
        r = a.relation
        cov = coverage.get(r, 0.0)
        mass_raw = support_mass.get(r, 0.0)
        mass_score = 0.0 if max_mass <= 0 else mass_raw / max_mass
        vol_score = a.eta_integer / max_eta if max_eta > 0 else 0.0
        manual = 1.0 if r in manual_flag_set else 0.0

        # Weighted combined score. Kept simple and transparent.
        score = 0.35 * cov + 0.25 * mass_score + 0.20 * vol_score + 0.20 * manual

        if manual >= 1.0 or cov >= config.genericity_coverage_threshold or mass_raw >= mass_thr:
            bucket = "high" if score >= 0.60 or manual >= 1.0 else "medium"
        elif score >= 0.33:
            bucket = "medium"
        else:
            bucket = "low"

        out.append(
            GenericityRecord(
                relation=r,
                coverage_score=cov,
                support_mass_score=mass_score,
                candidate_volume_score=vol_score,
                manual_structural_risk=manual,
                genericity_score=score,
                genericity_bucket=bucket,
            )
        )
    return sorted(out, key=lambda x: ({"high": 0, "medium": 1, "low": 2}[x.genericity_bucket], -x.genericity_score, x.relation))


# ---------------------------------------------------------------------------
# Candidate collection adapters
# ---------------------------------------------------------------------------

class CandidateSource:
    """
    Abstraction layer for candidate retrieval.

    Implementations can be:
    - frozen local JSONL source
    - WDQS-backed collector
    - hybrid source

    Version in this file:
    - LocalFrozenCandidateSource: reads a pre-existing JSONL/dir of JSONL and
      filters by relation. This keeps the core pipeline immediately runnable.
    """

    name = "candidate_source"

    def iter_relation_candidates(self, relation: str, *, raw_limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        raise NotImplementedError

    def recommended_max_workers(self, requested_max_workers: int) -> int:
        return requested_max_workers


class LocalFrozenCandidateSource(CandidateSource):
    name = "local_frozen_jsonl"

    def __init__(self, path: Path):
        self.files = list_jsonl_files(path)
        if not self.files:
            raise FileNotFoundError(f"No JSONL candidate files found under {path}")

    def iter_relation_candidates(self, relation: str, *, raw_limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        for fp in self.files:
            for rec in read_jsonl(fp):
                if rec.get("r") == relation or rec.get("relation") == relation:
                    yield rec


WIKIDATA_ENTITY_PREFIX = "http://www.wikidata.org/entity/"


def wikidata_entity_id_from_uri(uri: str) -> Optional[str]:
    if not isinstance(uri, str) or not uri.startswith(WIKIDATA_ENTITY_PREFIX):
        return None
    entity_id = uri[len(WIKIDATA_ENTITY_PREFIX):]
    if entity_id.startswith("Q") and entity_id[1:].isdigit():
        return entity_id
    return None


def parse_wdqs_binding_term(term: Dict[str, Any]) -> Optional[str]:
    term_type = term.get("type")
    value = term.get("value")
    if not value:
        return None
    if term_type == "uri":
        return wikidata_entity_id_from_uri(value) or value
    if term_type in {"literal", "typed-literal", "bnode"}:
        return str(value)
    return None


def build_wdqs_candidate_query(
    relation: str,
    limit: int,
    offset: int,
    require_entity_targets: bool,
    order_results: bool,
) -> str:
    target_filter = (
        f'FILTER(STRSTARTS(STR(?t), "{WIKIDATA_ENTITY_PREFIX}Q"))'
        if require_entity_targets
        else ""
    )
    order_clause = "ORDER BY ?h ?t" if order_results else ""
    return f"""
SELECT DISTINCT ?h ?t WHERE {{
  ?h wdt:{relation} ?t .
  FILTER(STRSTARTS(STR(?h), "{WIKIDATA_ENTITY_PREFIX}Q"))
  {target_filter}
}}
{order_clause}
LIMIT {int(limit)}
OFFSET {int(offset)}
""".strip()


def determine_source_fetch_limit(target: int, bucket: str, config: Config) -> int:
    if bucket == "high":
        write_goal = min(target, config.small_relation_full_retrieval_threshold)
    else:
        write_goal = max(target, config.small_relation_full_retrieval_threshold)
    inflated = int(math.ceil(write_goal * max(1.0, config.wdqs_overfetch_factor)))
    return max(1, min(config.wdqs_max_raw_candidates_per_relation, max(write_goal, inflated)))


class WDQSCandidateSource(CandidateSource):
    name = "wdqs"

    def __init__(self, config: Config):
        if requests is None:
            raise RuntimeError(
                "The 'requests' package is required for WDQS candidate retrieval. "
                "Install project requirements or provide candidate_input_path."
            )
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.wdqs_user_agent,
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
        })

    def recommended_max_workers(self, requested_max_workers: int) -> int:
        # Keep WDQS collection polite and low-pressure.
        return 1

    def _sleep_backoff(self, attempt: int, retry_after_header: Optional[str]) -> None:
        retry_after_sec = None
        if retry_after_header:
            try:
                retry_after_sec = float(retry_after_header)
            except Exception:
                retry_after_sec = None
        if retry_after_sec is not None and retry_after_sec > 0:
            sleep_sec = min(retry_after_sec, self.config.wdqs_backoff_cap_sec)
        else:
            sleep_sec = min(
                self.config.wdqs_backoff_base_sec * (2 ** max(0, attempt - 1)),
                self.config.wdqs_backoff_cap_sec,
            )
        time.sleep(sleep_sec)

    def _post_query(self, sparql: str) -> Dict[str, Any]:
        last_error = "unknown"
        for attempt in range(1, self.config.wdqs_max_retries + 1):
            try:
                response = self.session.post(
                    self.config.wdqs_endpoint,
                    data={"query": sparql},
                    params={"format": "json"},
                    timeout=self.config.wdqs_timeout_sec,
                )
            except requests.Timeout:
                last_error = "timeout"
                self._sleep_backoff(attempt, None)
                continue
            except requests.RequestException as exc:
                last_error = f"request_exception: {exc}"
                self._sleep_backoff(attempt, None)
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except Exception as exc:
                    last_error = f"json_parse_error: {exc}"
                    self._sleep_backoff(attempt, None)
                    continue

            last_error = f"HTTP {response.status_code}: {(response.text or '')[:300].replace(chr(10), ' ')}"
            self._sleep_backoff(attempt, response.headers.get("Retry-After"))

        raise RuntimeError(f"WDQS query failed after retries: {last_error}")

    def iter_relation_candidates(self, relation: str, *, raw_limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        page_size = max(1, min(self.config.wdqs_page_size, raw_limit or self.config.wdqs_page_size))
        offset = 0
        yielded = 0

        while raw_limit is None or yielded < raw_limit:
            remaining = None if raw_limit is None else raw_limit - yielded
            if remaining is not None and remaining <= 0:
                break
            limit = page_size if remaining is None else min(page_size, remaining)
            query = build_wdqs_candidate_query(
                relation,
                limit=limit,
                offset=offset,
                require_entity_targets=self.config.wdqs_require_entity_targets,
                order_results=self.config.wdqs_order_results,
            )
            data = self._post_query(query)
            bindings = ((data.get("results") or {}).get("bindings") or [])
            if not bindings:
                break

            for row in bindings:
                h = parse_wdqs_binding_term(row.get("h", {}))
                t = parse_wdqs_binding_term(row.get("t", {}))
                if not h or not t:
                    continue
                yield {
                    "h": h,
                    "r": relation,
                    "t": t,
                    "source_backend": self.name,
                    "query_offset": offset,
                    "query_limit": limit,
                }
                yielded += 1
                if raw_limit is not None and yielded >= raw_limit:
                    break

            if len(bindings) < limit:
                break
            offset += limit
            if self.config.wdqs_pause_between_pages_sec > 0:
                time.sleep(self.config.wdqs_pause_between_pages_sec)


def build_candidate_source(config: Config) -> CandidateSource:
    mode = (config.candidate_source_mode or "auto").strip().lower()
    if mode not in {"auto", "local", "wdqs"}:
        raise ValueError(f"Unsupported candidate_source_mode: {config.candidate_source_mode}")

    if config.candidate_input_path:
        if mode in {"auto", "local"}:
            return LocalFrozenCandidateSource(Path(config.candidate_input_path))
        LOG.info(
            "candidate_input_path is set but candidate_source_mode=%s; using WDQS backend instead.",
            config.candidate_source_mode,
        )

    if mode == "local":
        raise ValueError("candidate_input_path is required when candidate_source_mode=local.")

    return WDQSCandidateSource(config)


# ---------------------------------------------------------------------------
# Candidate annotation and filtering
# ---------------------------------------------------------------------------

def triple_id(h: str, r: str, t: str) -> str:
    return stable_hash(f"{h}\t{r}\t{t}")


def infer_types_from_record(rec: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    # Project-specific enrichment can override this.
    return rec.get("subject_type"), rec.get("object_type")


def ontology_compatible(rec: Dict[str, Any], compatibility: Set[Tuple[str, str, str]]) -> bool:
    if not compatibility:
        return True
    st, ot = infer_types_from_record(rec)
    if st is None or ot is None:
        return True  # do not hard-fail when type data is missing
    return (rec["r"], st, ot) in compatibility


def estimate_hub_penalty(h: str, t: str, entity_freq: Dict[str, int]) -> float:
    # Simple bounded penalty based on local observed frequency in candidate intake.
    max_freq = max(entity_freq.values()) if entity_freq else 1
    if max_freq <= 1:
        return 0.0
    freq = max(entity_freq.get(h, 0), entity_freq.get(t, 0))
    return min(1.0, freq / max_freq)


def estimate_shortcut_risk(relation_bucket: str) -> float:
    return {"low": 0.1, "medium": 0.4, "high": 0.8}[relation_bucket]


def quality_score(*, ontology_ok: bool, self_loop_flag: bool, hub_penalty: float, shortcut_risk: float, genericity_score: float) -> float:
    base = 1.0
    if not ontology_ok:
        base -= 1.0
    if self_loop_flag:
        base -= 1.0
    base -= 0.30 * hub_penalty
    base -= 0.25 * shortcut_risk
    base -= 0.20 * genericity_score
    return max(0.0, round(base, 6))


def determine_candidate_target(eta_integer: int, config: Config) -> int:
    return min(
        config.candidate_hard_cap_per_relation,
        max(config.candidate_floor, config.candidate_alpha * eta_integer + config.candidate_beta),
    )


def append_bounded_sorted_record(
    records: List[Dict[str, Any]],
    rec: Dict[str, Any],
    keep_limit: int,
    key_fn,
) -> None:
    if keep_limit <= 0:
        return
    records.append(rec)
    # Keep memory bounded without paying a full sort cost on every insertion.
    if len(records) > keep_limit * 2:
        records.sort(key=key_fn)
        del records[keep_limit:]


def annotate_relation_candidates(
    relation: str,
    source: CandidateSource,
    genericity_map: Dict[str, GenericityRecord],
    allocations_map: Dict[str, RelationAllocation],
    compatibility: Set[Tuple[str, str, str]],
    out_segment: Path,
    run_id: str,
    config: Config,
) -> Dict[str, Any]:
    """
    Annotate and freeze a relation-specific candidate segment from the configured source.
    This function is safe to run in parallel across relations because it writes one file per relation.
    """
    eta = allocations_map[relation].eta_integer
    bucket = genericity_map[relation].genericity_bucket
    target = determine_candidate_target(eta, config)
    source_raw_limit = determine_source_fetch_limit(target, bucket, config)
    LOG.info(
        "Collecting candidates for relation=%s source=%s target=%d raw_limit=%d bucket=%s",
        relation,
        source.name,
        target,
        source_raw_limit,
        bucket,
    )

    # Intake accepted records with bounded retention so very large relations do not
    # accumulate fully in RAM before we write the shard.
    kept_records: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    entity_freq: Counter[str] = Counter()
    reject_counts = Counter()
    accepted_count = 0
    keep_limit = (
        min(target, config.small_relation_full_retrieval_threshold)
        if bucket == "high"
        else max(target, config.small_relation_full_retrieval_threshold)
    )

    for raw in source.iter_relation_candidates(relation, raw_limit=source_raw_limit):
        h = raw.get("h")
        r = raw.get("r") or raw.get("relation")
        t = raw.get("t")
        if not h or not r or not t:
            reject_counts["MALFORMED"] += 1
            continue
        tid = triple_id(h, r, t)
        if tid in seen:
            reject_counts["DUPLICATE"] += 1
            continue
        seen.add(tid)

        self_loop = h == t
        if self_loop:
            reject_counts["SELF_LOOP"] += 1
            continue

        rec = {"h": h, "r": r, "t": t, **raw}
        onto_ok = ontology_compatible(rec, compatibility)
        if not onto_ok:
            reject_counts["ONTOLOGY_INCOMPATIBLE"] += 1
            continue

        accepted_count += 1
        append_bounded_sorted_record(kept_records, rec, keep_limit, key_fn=lambda row: (row["h"], row["r"], row["t"]))
        entity_freq[h] += 1
        entity_freq[t] += 1

    # candidate count may decide "small full retrieval" behavior
    full_small = accepted_count <= config.small_relation_full_retrieval_threshold and bucket != "high"
    collection_mode = "graph_anchored" if bucket == "high" else ("small_full" if full_small else "normal")
    kept_records.sort(key=lambda row: (row["h"], row["r"], row["t"]))
    if len(kept_records) > keep_limit:
        del kept_records[keep_limit:]
    if bucket == "high":
        output_records = kept_records[: min(target, config.small_relation_full_retrieval_threshold)]
    elif full_small:
        output_records = kept_records
    else:
        output_records = kept_records[: min(target, accepted_count)]

    writer = JsonlSegmentWriter(out_segment)
    written = 0
    try:
        for idx, rec in enumerate(output_records):
            h, r, t = rec["h"], rec["r"], rec["t"]
            tid = triple_id(h, r, t)
            hub = estimate_hub_penalty(h, t, entity_freq)
            shortcut = estimate_shortcut_risk(bucket)
            gscore = genericity_map[r].genericity_score
            qs = quality_score(
                ontology_ok=True,
                self_loop_flag=False,
                hub_penalty=hub,
                shortcut_risk=shortcut,
                genericity_score=gscore,
            )
            cand = CandidateRecord(
                triple_id=tid,
                h=h,
                r=r,
                t=t,
                genericity_score=gscore,
                genericity_bucket=bucket,
                collection_mode=collection_mode,
                hub_penalty=hub,
                shortcut_risk=shortcut,
                ontology_ok=True,
                self_loop_flag=False,
                quality_score=qs,
                source_stage="candidate_collection",
                chunk_id=f"{relation}_0",
                query_id=None,
                retrieved_at=utc_now_iso(),
                run_id=run_id,
                extra={k: v for k, v in rec.items() if k not in {"h", "r", "t"}},
            )
            writer.write(cand.to_record())
            written += 1
        writer.close_and_promote()
    except Exception:
        writer.abort()
        raise

    LOG.info(
        "Finished relation=%s source=%s accepted=%d written=%d rejects=%s",
        relation,
        source.name,
        accepted_count,
        written,
        dict(reject_counts),
    )

    return {
        "relation": relation,
        "eta_integer": eta,
        "genericity_bucket": bucket,
        "collection_mode": collection_mode,
        "source_backend": source.name,
        "accepted_candidates": accepted_count,
        "source_raw_limit": source_raw_limit,
        "target_candidates": target,
        "written_candidates": written,
        "reject_counts": dict(reject_counts),
        "segment": str(out_segment),
    }


def recover_relation_candidate_segment(
    relation: str,
    segment_path: Path,
    genericity_map: Dict[str, GenericityRecord],
    allocations_map: Dict[str, RelationAllocation],
    config: Config,
) -> Dict[str, Any]:
    written = 0
    observed_modes: Counter[str] = Counter()
    for rec in read_jsonl(segment_path):
        if rec.get("r") != relation:
            raise ValueError(
                f"Existing candidate segment {segment_path} contains relation {rec.get('r')} "
                f"while recovering relation {relation}."
            )
        written += 1
        if rec.get("collection_mode"):
            observed_modes[str(rec["collection_mode"])] += 1

    return {
        "relation": relation,
        "eta_integer": allocations_map[relation].eta_integer,
        "genericity_bucket": genericity_map[relation].genericity_bucket,
        "collection_mode": observed_modes.most_common(1)[0][0] if observed_modes else "recovered_existing_segment",
        "target_candidates": determine_candidate_target(allocations_map[relation].eta_integer, config),
        "written_candidates": written,
        "reject_counts": {},
        "segment": str(segment_path),
        "recovered_existing_segment": True,
    }


# ---------------------------------------------------------------------------
# Candidate auditing
# ---------------------------------------------------------------------------

def audit_candidate_relation(relation: str, segment_path: Path, allocations_map: Dict[str, RelationAllocation]) -> Dict[str, Any]:
    entity_counter: Counter[str] = Counter()
    count = 0
    heads: Set[str] = set()
    tails: Set[str] = set()
    quality_sum = 0.0
    genericity_sum = 0.0
    hub_penalty_sum = 0.0

    for rec in read_jsonl(segment_path):
        count += 1
        h, t = rec["h"], rec["t"]
        heads.add(h)
        tails.add(t)
        entity_counter[h] += 1
        entity_counter[t] += 1
        quality_sum += safe_float(rec.get("quality_score"), 0.0)
        genericity_sum += safe_float(rec.get("genericity_score"), 0.0)
        hub_penalty_sum += safe_float(rec.get("hub_penalty"), 0.0)

    top_entities = entity_counter.most_common(10)
    max_entity_freq = top_entities[0][1] if top_entities else 0
    uniq_entities = len(entity_counter)
    concentration_ratio = 0.0 if count == 0 else max_entity_freq / max(1, 2 * count)

    return {
        "relation": relation,
        "eta_integer": allocations_map[relation].eta_integer,
        "candidate_count": count,
        "unique_heads": len(heads),
        "unique_tails": len(tails),
        "unique_entities": uniq_entities,
        "max_entity_frequency": max_entity_freq,
        "max_entity_concentration_ratio": round(concentration_ratio, 6),
        "avg_quality_score": round(quality_sum / count, 6) if count else 0.0,
        "avg_genericity_score": round(genericity_sum / count, 6) if count else 0.0,
        "avg_hub_penalty": round(hub_penalty_sum / count, 6) if count else 0.0,
        "top_entities": top_entities,
        "possible_undercollection_flag": count < allocations_map[relation].eta_integer,
    }


# ---------------------------------------------------------------------------
# Graph utilities
# ---------------------------------------------------------------------------

class UnionFind:
    def __init__(self) -> None:
        self.parent: Dict[str, str] = {}
        self.rank: Dict[str, int] = {}

    def add(self, x: str) -> None:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x: str) -> str:
        self.add(x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1

    def component_map(self) -> Dict[str, Set[str]]:
        groups: Dict[str, Set[str]] = defaultdict(set)
        for x in self.parent:
            groups[self.find(x)].add(x)
        return groups


def connected_components_from_triples(triples: Iterable[Tuple[str, str, str]]) -> Dict[int, Set[str]]:
    uf = UnionFind()
    for h, _, t in triples:
        uf.union(h, t)
    groups = uf.component_map()
    out: Dict[int, Set[str]] = {}
    for idx, (_, nodes) in enumerate(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))):
        out[idx] = nodes
    return out


# ---------------------------------------------------------------------------
# Core construction
# ---------------------------------------------------------------------------

@dataclass
class GraphState:
    selected_triple_ids: Set[str] = field(default_factory=set)
    selected_triples: List[TripleSelectionRecord] = field(default_factory=list)
    relation_counts_core: Counter[str] = field(default_factory=Counter)
    relation_counts_aux: Counter[str] = field(default_factory=Counter)
    relation_realized: Set[str] = field(default_factory=set)
    entity_degrees: Counter[str] = field(default_factory=Counter)
    entities: Set[str] = field(default_factory=set)
    uf: UnionFind = field(default_factory=UnionFind)

    def add(self, sel: TripleSelectionRecord) -> None:
        if sel.triple_id in self.selected_triple_ids:
            return
        self.selected_triple_ids.add(sel.triple_id)
        self.selected_triples.append(sel)
        if sel.layer == "core":
            self.relation_counts_core[sel.r] += 1
        else:
            self.relation_counts_aux[sel.r] += 1
        self.relation_realized.add(sel.r)
        self.entities.add(sel.h)
        self.entities.add(sel.t)
        self.entity_degrees[sel.h] += 1
        self.entity_degrees[sel.t] += 1
        self.uf.union(sel.h, sel.t)

    def component_id(self, x: str) -> str:
        return self.uf.find(x)

    def components(self) -> Dict[str, Set[str]]:
        return self.uf.component_map()


def candidate_iter_from_dir(path: Path) -> Iterator[Dict[str, Any]]:
    for fp in list_jsonl_files(path):
        yield from read_jsonl(fp)


def attachability_bonus(h: str, t: str, entities: Set[str]) -> float:
    h_in = h in entities
    t_in = t in entities
    if h_in and t_in:
        return 1.0
    if h_in or t_in:
        return 0.6
    return 0.1


def bridge_bonus(h: str, t: str, entity_relation_incidence: Dict[str, int]) -> float:
    return min(1.0, (entity_relation_incidence.get(h, 0) + entity_relation_incidence.get(t, 0)) / 20.0)


def component_merge_bonus(h: str, t: str, state: GraphState) -> float:
    if h not in state.entities or t not in state.entities:
        return 0.0
    return 1.0 if state.component_id(h) != state.component_id(t) else 0.0


def relation_need_score(relation: str, allocations_map: Dict[str, RelationAllocation], state: GraphState) -> float:
    cap = allocations_map[relation].eta_integer
    current = state.relation_counts_core[relation]
    if cap <= 0 or current >= cap:
        return 0.0
    return (cap - current) / cap


def first_realization_bonus(relation: str, state: GraphState) -> float:
    return 1.0 if relation not in state.relation_realized else 0.0


def degree_penalty(h: str, t: str, state: GraphState) -> float:
    deg_h = state.entity_degrees.get(h, 0)
    deg_t = state.entity_degrees.get(t, 0)
    max_deg = max(state.entity_degrees.values()) if state.entity_degrees else 1
    if max_deg <= 0:
        return 0.0
    return min(1.0, max(deg_h, deg_t) / max_deg)


def deterministic_tie_key(rec: Dict[str, Any]) -> Tuple[str, str, str]:
    return (rec["r"], rec["h"], rec["t"])


def candidate_total_score(rec: Dict[str, Any], state: GraphState, allocations_map: Dict[str, RelationAllocation], entity_relation_incidence: Dict[str, int], config: Config) -> Tuple[float, Dict[str, float]]:
    r = rec["r"]
    need = relation_need_score(r, allocations_map, state)
    first = first_realization_bonus(r, state)
    att = attachability_bonus(rec["h"], rec["t"], state.entities)
    bridge = bridge_bonus(rec["h"], rec["t"], entity_relation_incidence)
    merge = component_merge_bonus(rec["h"], rec["t"], state)
    hub_pen = max(degree_penalty(rec["h"], rec["t"], state), safe_float(rec.get("hub_penalty"), 0.0))
    generic_pen = safe_float(rec.get("genericity_score"), 0.0)
    noise_pen = 1.0 - safe_float(rec.get("quality_score"), 0.0)

    score = (
        config.weight_relation_need * need
        + config.weight_first_realization_bonus * first
        + config.weight_attachability * att
        + config.weight_bridge * bridge
        + config.weight_component_merge * merge
        - config.weight_hub_penalty * hub_pen
        - config.weight_genericity_penalty * generic_pen
        - config.weight_noise_penalty * noise_pen
    )
    parts = {
        "relation_need_score": round(need, 6),
        "first_realization_bonus": round(first, 6),
        "attachability_score": round(att, 6),
        "bridge_score": round(bridge, 6),
        "component_merge_score": round(merge, 6),
        "hub_penalty": round(hub_pen, 6),
        "genericity_penalty": round(generic_pen, 6),
        "noise_penalty": round(noise_pen, 6),
    }
    return score, parts


def prepare_entity_relation_incidence(candidate_dir: Path) -> Dict[str, int]:
    incidence: Counter[str] = Counter()
    for fp in list_jsonl_files(candidate_dir):
        relation_entities: Set[str] = set()
        for rec in read_jsonl(fp):
            relation_entities.add(rec["h"])
            relation_entities.add(rec["t"])
        for entity in relation_entities:
            incidence[entity] += 1
    return dict(incidence)


def select_seed_triples(
    candidate_dir: Path,
    allocations: List[RelationAllocation],
    entity_relation_incidence: Dict[str, int],
    config: Config,
) -> List[Dict[str, Any]]:
    hard_seed_candidates: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    bridge_samples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rec in candidate_iter_from_dir(candidate_dir):
        append_bounded_sorted_record(
            hard_seed_candidates[rec["r"]],
            rec,
            config.per_relation_seed_cap,
            deterministic_tie_key,
        )
        append_bounded_sorted_record(
            bridge_samples[rec["r"]],
            rec,
            50,
            deterministic_tie_key,
        )

    # hard-relation / low-eta seeds
    allocations_sorted = sorted(allocations, key=lambda a: (a.eta_integer, a.relation))
    seeds: List[Dict[str, Any]] = []
    seed_ids: Set[str] = set()
    per_relation = Counter()

    for a in allocations_sorted:
        if len(seeds) >= config.hard_relation_seed_count:
            break
        recs = hard_seed_candidates.get(a.relation, [])
        recs.sort(key=deterministic_tie_key)
        for rec in recs:
            if per_relation[a.relation] >= config.per_relation_seed_cap:
                break
            if rec["triple_id"] in seed_ids:
                continue
            seeds.append(rec)
            seed_ids.add(rec["triple_id"])
            per_relation[a.relation] += 1
            if len(seeds) >= config.hard_relation_seed_count:
                break

    # bridge-aware seeds
    scored_pool: List[Tuple[float, Dict[str, Any]]] = []
    for relation, recs in bridge_samples.items():
        recs.sort(key=deterministic_tie_key)
        for rec in recs:
            bridge = bridge_bonus(rec["h"], rec["t"], entity_relation_incidence)
            scored_pool.append((bridge, rec))
    scored_pool.sort(key=lambda x: (-x[0], x[1]["r"], x[1]["h"], x[1]["t"]))
    for _, rec in scored_pool[: config.bridge_seed_count]:
        if rec["triple_id"] not in seed_ids:
            seeds.append(rec)
            seed_ids.add(rec["triple_id"])
    return seeds


def construct_core_graph(
    candidate_dir: Path,
    allocations: List[RelationAllocation],
    config: Config,
) -> GraphState:
    allocations_map = {a.relation: a for a in allocations}
    state = GraphState()
    ent_inc = prepare_entity_relation_incidence(candidate_dir)

    # seed phase
    seeds = select_seed_triples(candidate_dir, allocations, ent_inc, config)
    for rec in seeds:
        r = rec["r"]
        if state.relation_counts_core[r] >= allocations_map[r].eta_integer:
            continue
        score, parts = candidate_total_score(rec, state, allocations_map, ent_inc, config)
        sel = TripleSelectionRecord(
            triple_id=rec["triple_id"],
            h=rec["h"],
            r=r,
            t=rec["t"],
            layer="core",
            score=score,
            selection_reason="seed",
            **parts,
        )
        state.add(sel)
        if len(state.selected_triples) >= config.global_triple_budget:
            return state

    # iterative selection by rescanning the frozen shards. This is slower than
    # materializing all candidates once, but it keeps memory bounded for small-RAM
    # machines.
    while len(state.selected_triples) < config.global_triple_budget:
        best_rec: Optional[Dict[str, Any]] = None
        best_score = -float("inf")
        best_parts: Optional[Dict[str, float]] = None

        if all(state.relation_counts_core[r] >= allocations_map[r].eta_integer for r in allocations_map):
            break

        for rec in candidate_iter_from_dir(candidate_dir):
            tid = rec["triple_id"]
            if tid in state.selected_triple_ids:
                continue
            r = rec["r"]
            if state.relation_counts_core[r] >= allocations_map[r].eta_integer:
                continue
            score, parts = candidate_total_score(rec, state, allocations_map, ent_inc, config)
            tie = deterministic_tie_key(rec)
            if best_parts is None or score > best_score or (score == best_score and tie < deterministic_tie_key(best_rec)):  # type: ignore[arg-type]
                best_rec = rec
                best_score = score
                best_parts = parts

        if best_rec is None or best_parts is None:
            break

        sel = TripleSelectionRecord(
            triple_id=best_rec["triple_id"],
            h=best_rec["h"],
            r=best_rec["r"],
            t=best_rec["t"],
            layer="core",
            score=best_score,
            selection_reason="scored_selection",
            **best_parts,
        )
        state.add(sel)

    return state


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

def realize_missing_with_unused_candidates(
    candidate_dir: Path,
    state: GraphState,
    allocations: List[RelationAllocation],
    config: Config,
) -> List[TripleSelectionRecord]:
    allocations_map = {a.relation: a for a in allocations}
    ent_inc = prepare_entity_relation_incidence(candidate_dir)
    repairs: List[TripleSelectionRecord] = []

    missing = [a.relation for a in allocations if a.relation not in state.relation_realized]

    for relation in sorted(missing):
        if len(state.selected_triples) >= config.global_triple_budget:
            break
        best_rec = None
        best_score = -float("inf")
        best_parts = None
        for rec in candidate_iter_from_dir(candidate_dir):
            if rec["r"] != relation or rec["triple_id"] in state.selected_triple_ids:
                continue
            score, parts = candidate_total_score(rec, state, allocations_map, ent_inc, config)
            tie = deterministic_tie_key(rec)
            if best_parts is None or score > best_score or (score == best_score and tie < deterministic_tie_key(best_rec)):  # type: ignore[arg-type]
                best_score = score
                best_rec = rec
                best_parts = parts
        if best_rec is not None and best_parts is not None:
            sel = TripleSelectionRecord(
                triple_id=best_rec["triple_id"],
                h=best_rec["h"],
                r=best_rec["r"],
                t=best_rec["t"],
                layer="core",
                score=best_score,
                selection_reason="repair_missing_relation",
                **best_parts,
            )
            state.add(sel)
            repairs.append(sel)
    return repairs


def merge_components_with_allocated_candidates(
    candidate_dir: Path,
    state: GraphState,
    allocations: List[RelationAllocation],
    config: Config,
) -> List[TripleSelectionRecord]:
    allocations_map = {a.relation: a for a in allocations}
    ent_inc = prepare_entity_relation_incidence(candidate_dir)
    applied: List[TripleSelectionRecord] = []

    while True:
        if len(state.selected_triples) >= config.global_triple_budget:
            break
        best_sel: Optional[TripleSelectionRecord] = None
        best_tie: Optional[Tuple[str, str, str]] = None
        for rec in candidate_iter_from_dir(candidate_dir):
            if rec["triple_id"] in state.selected_triple_ids:
                continue
            r = rec["r"]
            if state.relation_counts_core[r] >= allocations_map[r].eta_integer:
                continue
            if rec["h"] not in state.entities or rec["t"] not in state.entities:
                continue
            if state.component_id(rec["h"]) == state.component_id(rec["t"]):
                continue
            score, parts = candidate_total_score(rec, state, allocations_map, ent_inc, config)
            tie = deterministic_tie_key(rec)
            if best_sel is None or score > best_sel.score or (score == best_sel.score and tie < best_tie):  # type: ignore[operator]
                best_sel = TripleSelectionRecord(
                    triple_id=rec["triple_id"],
                    h=rec["h"],
                    r=rec["r"],
                    t=rec["t"],
                    layer="core",
                    score=score,
                    selection_reason="repair_component_merge_allocated",
                    **parts,
                )
                best_tie = tie
        if best_sel is None:
            break
        state.add(best_sel)
        applied.append(best_sel)
    return applied


# ---------------------------------------------------------------------------
# Weak-component filtering
# ---------------------------------------------------------------------------

def component_stats_for_state(state: GraphState) -> List[Dict[str, Any]]:
    comp_nodes = state.components()
    triples_by_comp: Dict[str, List[TripleSelectionRecord]] = defaultdict(list)
    for sel in state.selected_triples:
        cid = state.component_id(sel.h)
        triples_by_comp[cid].append(sel)

    rows: List[Dict[str, Any]] = []
    for cid, nodes in comp_nodes.items():
        trs = triples_by_comp.get(cid, [])
        rows.append({
            "component_id": cid,
            "entity_count": len(nodes),
            "triple_count": len(trs),
            "relations": sorted(set(t.r for t in trs)),
            "triple_ids": [t.triple_id for t in trs],
        })
    rows.sort(key=lambda x: (-x["triple_count"], -x["entity_count"], x["component_id"]))
    return rows


def filter_weak_components(
    state: GraphState,
    allocations: List[RelationAllocation],
    config: Config,
) -> Tuple[GraphState, List[Dict[str, Any]]]:
    allocations_map = {a.relation: a for a in allocations}
    comp_rows = component_stats_for_state(state)

    # determine relations with unique realization locations
    relation_occurrences = Counter(t.r for t in state.selected_triples if t.layer == "core")
    kept_ids: Set[str] = set()
    reports: List[Dict[str, Any]] = []

    for row in comp_rows:
        cid = row["component_id"]
        triples = [t for t in state.selected_triples if state.component_id(t.h) == cid]
        relations = {t.r for t in triples}
        is_small = row["triple_count"] < config.weak_component_min_triples or row["entity_count"] < config.weak_component_min_entities

        hard_unique_relation_present = False
        for r in relations:
            if relation_occurrences[r] > 0 and state.relation_counts_core[r] == 1 and allocations_map.get(r, RelationAllocation(r, 0)).eta_integer > 0:
                hard_unique_relation_present = True
                break

        keep = not is_small or hard_unique_relation_present
        for t in triples:
            if keep:
                kept_ids.add(t.triple_id)
                if is_small and hard_unique_relation_present:
                    t.structurally_weak = True

        reports.append({
            "component_id": cid,
            "keep": keep,
            "small_component": is_small,
            "hard_unique_relation_present": hard_unique_relation_present,
            "triple_count": row["triple_count"],
            "entity_count": row["entity_count"],
            "relations": sorted(relations),
        })

    new_state = GraphState()
    for sel in state.selected_triples:
        if sel.triple_id in kept_ids:
            new_state.add(sel)
    return new_state, reports


# ---------------------------------------------------------------------------
# Final audit
# ---------------------------------------------------------------------------

def final_audit(
    state: GraphState,
    allocations: List[RelationAllocation],
    candidate_audit_by_relation: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    allocations_map = {a.relation: a for a in allocations}
    comp_rows = component_stats_for_state(state)
    total_core = sum(1 for x in state.selected_triples if x.layer == "core")
    total_aux = sum(1 for x in state.selected_triples if x.layer != "core")
    total_entities = len(state.entities)
    comp_count = len(comp_rows)
    largest_comp_entities = max((row["entity_count"] for row in comp_rows), default=0)
    lcc_ratio = 0.0 if total_entities == 0 else largest_comp_entities / total_entities

    per_relation = []
    for a in sorted(allocations, key=lambda x: x.relation):
        cand = candidate_audit_by_relation.get(a.relation, {})
        core_count = int(state.relation_counts_core[a.relation])
        aux_count = int(state.relation_counts_aux[a.relation])
        realized = core_count > 0 or aux_count > 0
        if cand.get("candidate_count", 0) == 0:
            reason = "NO_CANDIDATES"
        elif not realized:
            reason = "REPAIR_FAILED"
        else:
            reason = ""
        per_relation.append({
            "relation": a.relation,
            "eta_integer": a.eta_integer,
            "candidate_count": cand.get("candidate_count", 0),
            "core_selected_count": core_count,
            "aux_selected_count": aux_count,
            "realized": realized,
            "reason_if_unrealized": reason,
        })

    return {
        "generated_at": utc_now_iso(),
        "total_core_triples": total_core,
        "total_auxiliary_repair_triples": total_aux,
        "total_selected_triples": total_core + total_aux,
        "total_entities": total_entities,
        "component_count": comp_count,
        "largest_connected_component_entity_ratio": round(lcc_ratio, 6),
        "realized_allocated_relations": sum(1 for row in per_relation if row["realized"]),
        "unrealized_allocated_relations": sum(1 for row in per_relation if not row["realized"]),
        "per_relation": per_relation,
        "per_component": comp_rows,
    }


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------

def stage_score_genericity(ctx: RunContext) -> None:
    stage = "stage01_genericity"
    out_dir = ctx.stage_dir(stage)
    ensure_stage_can_write_once(ctx, stage, [out_dir / "relation_genericity.jsonl", out_dir / "summary.json"])
    allocations = load_allocated_relations(Path(ctx.config.allocated_relations_path))
    support = load_support_matrix(Path(ctx.config.support_matrix_path) if ctx.config.support_matrix_path else None, [a.relation for a in allocations])
    scored = score_genericity(allocations, support, ctx.config)

    writer = JsonlSegmentWriter(out_dir / "relation_genericity.jsonl")
    try:
        for row in scored:
            writer.write(asdict(row))
        writer.close_and_promote()
    except Exception:
        writer.abort()
        raise

    summary = {
        "count": len(scored),
        "bucket_counts": dict(Counter(x.genericity_bucket for x in scored)),
        "high_genericity_relations": [x.relation for x in scored if x.genericity_bucket == "high"],
    }
    atomic_write_json(out_dir / "summary.json", summary)
    ctx.update_stage(stage, {"completed_at": utc_now_iso(), **summary})


def stage_collect_candidates(ctx: RunContext) -> None:
    stage = "stage02_candidates"
    if ctx.stage_completed(stage):
        raise RuntimeError(
            f"Stage {stage} is already completed for run {ctx.run_dir}. "
            "Create a new run or continue with a later stage instead of overwriting it."
        )
    out_dir = ctx.stage_dir(stage)
    shards_dir = out_dir / "shards"
    checkpoints_dir = out_dir / "checkpoints"
    reports_dir = out_dir / "reports"
    for p in (shards_dir, checkpoints_dir, reports_dir):
        ensure_dir(p)

    allocations = load_allocated_relations(Path(ctx.config.allocated_relations_path))
    allocations_map = {a.relation: a for a in allocations}
    genericity_rows = [GenericityRecord(**rec) for rec in read_jsonl(ctx.run_dir / "stage01_genericity" / "relation_genericity.jsonl")]
    genericity_map = {row.relation: row for row in genericity_rows}
    compatibility = load_ontology_compatibility(ctx.config.ontology_compatibility_path)
    source = build_candidate_source(ctx.config)
    LOG.info("Stage %s using candidate source backend: %s", stage, source.name)
    run_id = ctx.run_dir.name

    tasks = []
    for a in allocations:
        segment = shards_dir / f"{a.relation}.jsonl"
        checkpoint = checkpoints_dir / f"{a.relation}.json"
        if checkpoint.exists() and segment.exists():
            continue
        if checkpoint.exists() and not segment.exists():
            raise RuntimeError(
                f"Checkpoint exists without a candidate segment for relation {a.relation}: {checkpoint}"
            )
        if segment.exists() and not checkpoint.exists():
            recovered = recover_relation_candidate_segment(
                a.relation,
                segment,
                genericity_map,
                allocations_map,
                ctx.config,
            )
            atomic_write_json(checkpoint, {
                "completed": True,
                "relation": a.relation,
                "result": recovered,
                "timestamp": utc_now_iso(),
            })
            continue
        tasks.append((a.relation, segment, checkpoint))

    results = []
    max_workers = source.recommended_max_workers(min(ctx.config.max_workers, max(1, len(tasks))))
    if ctx.config.use_threads_for_local_stages and max_workers > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {
                ex.submit(
                    annotate_relation_candidates,
                    relation,
                    source,
                    genericity_map,
                    allocations_map,
                    compatibility,
                    segment,
                    run_id,
                    ctx.config,
                ): (relation, checkpoint)
                for relation, segment, checkpoint in tasks
            }
            for fut in concurrent.futures.as_completed(futs):
                relation, checkpoint = futs[fut]
                result = fut.result()
                atomic_write_json(checkpoint, {"completed": True, "relation": relation, "result": result, "timestamp": utc_now_iso()})
                results.append(result)
    else:
        for relation, segment, checkpoint in tasks:
            result = annotate_relation_candidates(
                relation,
                source,
                genericity_map,
                allocations_map,
                compatibility,
                segment,
                run_id,
                ctx.config,
            )
            atomic_write_json(checkpoint, {"completed": True, "relation": relation, "result": result, "timestamp": utc_now_iso()})
            results.append(result)

    # summarize across all checkpoints
    all_results = []
    for cp in sorted(checkpoints_dir.glob("*.json")):
        all_results.append(read_json(cp)["result"])
    atomic_write_json(reports_dir / "summary.json", {
        "relation_count_completed": len(all_results),
        "total_written_candidates": sum(x["written_candidates"] for x in all_results),
        "bucket_counts": dict(Counter(x["genericity_bucket"] for x in all_results)),
        "collection_modes": dict(Counter(x["collection_mode"] for x in all_results)),
    })
    ctx.update_stage(stage, {"completed_at": utc_now_iso(), "completed_relations": len(all_results)})


def stage_audit_candidates(ctx: RunContext) -> None:
    stage = "stage03_candidate_audit"
    out_dir = ctx.stage_dir(stage)
    ensure_stage_can_write_once(ctx, stage, [out_dir / "candidate_relation_audit.jsonl", out_dir / "summary.json"])
    shards_dir = ctx.run_dir / "stage02_candidates" / "shards"
    allocations = load_allocated_relations(Path(ctx.config.allocated_relations_path))
    allocations_map = {a.relation: a for a in allocations}

    rows = []
    for a in allocations:
        segment = shards_dir / f"{a.relation}.jsonl"
        if not segment.exists():
            rows.append({
                "relation": a.relation,
                "eta_integer": a.eta_integer,
                "candidate_count": 0,
                "missing_segment": True,
            })
            continue
        rows.append(audit_candidate_relation(a.relation, segment, allocations_map))

    writer = JsonlSegmentWriter(out_dir / "candidate_relation_audit.jsonl")
    try:
        for row in rows:
            writer.write(row)
        writer.close_and_promote()
    except Exception:
        writer.abort()
        raise

    summary = {
        "relation_count": len(rows),
        "relations_with_zero_candidates": sum(1 for row in rows if row.get("candidate_count", 0) == 0),
        "possible_undercollection_relations": [row["relation"] for row in rows if row.get("possible_undercollection_flag")],
    }
    atomic_write_json(out_dir / "summary.json", summary)
    ctx.update_stage(stage, {"completed_at": utc_now_iso(), **summary})


def stage_construct_graph(ctx: RunContext) -> None:
    stage = "stage04_core_graph"
    out_dir = ctx.stage_dir(stage)
    ensure_stage_can_write_once(
        ctx,
        stage,
        [
            out_dir / "core_graph_triples.jsonl",
            out_dir / "core_graph_selection_log.jsonl",
            out_dir / "core_graph_relation_counts.json",
            out_dir / "core_graph_component_report.json",
        ],
    )
    candidate_dir = ctx.run_dir / "stage02_candidates" / "shards"
    allocations = load_allocated_relations(Path(ctx.config.allocated_relations_path))
    state = construct_core_graph(candidate_dir, allocations, ctx.config)

    writer = JsonlSegmentWriter(out_dir / "core_graph_triples.jsonl")
    sel_writer = JsonlSegmentWriter(out_dir / "core_graph_selection_log.jsonl")
    try:
        for sel in state.selected_triples:
            writer.write(sel.to_record())
            sel_writer.write(sel.to_record())
        writer.close_and_promote()
        sel_writer.close_and_promote()
    except Exception:
        writer.abort()
        sel_writer.abort()
        raise

    relation_counts = dict(state.relation_counts_core)
    comp_report = component_stats_for_state(state)
    atomic_write_json(out_dir / "core_graph_relation_counts.json", relation_counts)
    atomic_write_json(out_dir / "core_graph_component_report.json", comp_report)
    ctx.update_stage(stage, {
        "completed_at": utc_now_iso(),
        "core_triple_count": len(state.selected_triples),
        "realized_relations": len(state.relation_realized),
    })


def load_state_from_selected_jsonl(path: Path) -> GraphState:
    state = GraphState()
    for rec in read_jsonl(path):
        state.add(TripleSelectionRecord(**rec))
    return state


def stage_repair_graph(ctx: RunContext) -> None:
    stage = "stage05_repair"
    out_dir = ctx.stage_dir(stage)
    ensure_stage_can_write_once(ctx, stage, [out_dir / "repair_triples.jsonl", out_dir / "summary.json"])
    candidate_dir = ctx.run_dir / "stage02_candidates" / "shards"
    core_graph_path = ctx.run_dir / "stage04_core_graph" / "core_graph_triples.jsonl"
    allocations = load_allocated_relations(Path(ctx.config.allocated_relations_path))
    state = load_state_from_selected_jsonl(core_graph_path)

    pass1 = realize_missing_with_unused_candidates(candidate_dir, state, allocations, ctx.config)
    pass2 = merge_components_with_allocated_candidates(candidate_dir, state, allocations, ctx.config)

    writer = JsonlSegmentWriter(out_dir / "repair_triples.jsonl")
    try:
        for sel in [*pass1, *pass2]:
            writer.write(sel.to_record())
        writer.close_and_promote()
    except Exception:
        writer.abort()
        raise

    atomic_write_json(out_dir / "summary.json", {
        "missing_relation_repairs": len(pass1),
        "component_merge_repairs": len(pass2),
        "auxiliary_repair_enabled": ctx.config.allow_auxiliary_last_resort_repair,
    })
    ctx.update_stage(stage, {"completed_at": utc_now_iso(), "repair_count": len(pass1) + len(pass2)})


def stage_filter_components(ctx: RunContext) -> None:
    stage = "stage06_filtering"
    out_dir = ctx.stage_dir(stage)
    ensure_stage_can_write_once(ctx, stage, [out_dir / "filtered_graph_triples.jsonl", out_dir / "component_filter_report.json"])
    allocations = load_allocated_relations(Path(ctx.config.allocated_relations_path))
    core_graph_path = ctx.run_dir / "stage04_core_graph" / "core_graph_triples.jsonl"
    repair_path = ctx.run_dir / "stage05_repair" / "repair_triples.jsonl"

    state = load_state_from_selected_jsonl(core_graph_path)
    if repair_path.exists():
        for rec in read_jsonl(repair_path):
            state.add(TripleSelectionRecord(**rec))

    filtered_state, report = filter_weak_components(state, allocations, ctx.config)

    writer = JsonlSegmentWriter(out_dir / "filtered_graph_triples.jsonl")
    try:
        for sel in filtered_state.selected_triples:
            writer.write(sel.to_record())
        writer.close_and_promote()
    except Exception:
        writer.abort()
        raise

    atomic_write_json(out_dir / "component_filter_report.json", report)
    ctx.update_stage(stage, {
        "completed_at": utc_now_iso(),
        "kept_triples": len(filtered_state.selected_triples),
        "removed_components": sum(1 for row in report if not row["keep"]),
    })


def stage_final_audit(ctx: RunContext) -> None:
    stage = "stage07_final_audit"
    out_dir = ctx.stage_dir(stage)
    ensure_stage_can_write_once(ctx, stage, [out_dir / "final_audit.json"])
    allocations = load_allocated_relations(Path(ctx.config.allocated_relations_path))
    candidate_audit_path = ctx.run_dir / "stage03_candidate_audit" / "candidate_relation_audit.jsonl"
    filtered_graph_path = ctx.run_dir / "stage06_filtering" / "filtered_graph_triples.jsonl"

    state = load_state_from_selected_jsonl(filtered_graph_path)
    candidate_audit_by_relation = {rec["relation"]: rec for rec in read_jsonl(candidate_audit_path)}
    audit = final_audit(state, allocations, candidate_audit_by_relation)

    atomic_write_json(out_dir / "final_audit.json", audit)
    ctx.update_stage(stage, {
        "completed_at": utc_now_iso(),
        "realized_allocated_relations": audit["realized_allocated_relations"],
        "unrealized_allocated_relations": audit["unrealized_allocated_relations"],
        "component_count": audit["component_count"],
    })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Relation-balanced KG construction pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", required=True, help="Path to YAML or JSON config.")
    parser.add_argument("--run-dir", help="Existing run directory for continuing a run.")
    parser.add_argument("--run-name", help="New run directory name when creating a run.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-run", help="Create a new immutable run directory and snapshot config.")
    sub.add_parser("score-genericity", help="Compute genericity scores and buckets.")
    sub.add_parser("collect-candidates", help="Annotate and freeze relation candidate segments.")
    sub.add_parser("audit-candidates", help="Audit frozen candidate universe.")
    sub.add_parser("construct-graph", help="Build the core graph from frozen candidates.")
    sub.add_parser("repair-graph", help="Run bounded repair passes.")
    sub.add_parser("filter-components", help="Remove weak tiny components under the configured rule.")
    sub.add_parser("final-audit", help="Produce final global, relation, and component audit outputs.")
    sub.add_parser("run-all", help="Run all stages in order after creating/opening a run.")

    return parser.parse_args()


def get_context(args: argparse.Namespace, config: Config, create_if_missing: bool = False) -> RunContext:
    if args.run_dir:
        return RunContext.open_existing(config, Path(args.run_dir))
    if create_if_missing:
        return RunContext.create(config, run_name=args.run_name)
    raise ValueError("This command requires --run-dir, or use init-run / run-all with optional --run-name.")


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)
    config = Config.load(Path(args.config))
    random.seed(config.seed)

    if args.command == "init-run":
        ctx = RunContext.create(config, run_name=args.run_name)
        print(ctx.run_dir)
        return 0

    if args.command == "run-all":
        ctx = RunContext.create(config, run_name=args.run_name) if not args.run_dir else RunContext.open_existing(config, Path(args.run_dir))
        pipeline = [
            ("stage01_genericity", stage_score_genericity),
            ("stage02_candidates", stage_collect_candidates),
            ("stage03_candidate_audit", stage_audit_candidates),
            ("stage04_core_graph", stage_construct_graph),
            ("stage05_repair", stage_repair_graph),
            ("stage06_filtering", stage_filter_components),
            ("stage07_final_audit", stage_final_audit),
        ]
        for stage_name, stage_fn in pipeline:
            if ctx.stage_completed(stage_name):
                LOG.info("Skipping completed stage %s for run %s", stage_name, ctx.run_dir)
                continue
            stage_fn(ctx)
        print(ctx.run_dir)
        return 0

    ctx = get_context(args, config, create_if_missing=False)

    command_to_stage = {
        "score-genericity": stage_score_genericity,
        "collect-candidates": stage_collect_candidates,
        "audit-candidates": stage_audit_candidates,
        "construct-graph": stage_construct_graph,
        "repair-graph": stage_repair_graph,
        "filter-components": stage_filter_components,
        "final-audit": stage_final_audit,
    }
    fn = command_to_stage[args.command]
    fn(ctx)
    print(ctx.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
