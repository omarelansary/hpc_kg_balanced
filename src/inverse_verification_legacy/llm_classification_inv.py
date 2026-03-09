#!/usr/bin/env python3
"""
Classify candidate inverse relations for each r1 from JSONL input.

Input:
- JSONL lines like `data/processed/hop_support.wikibase_item_only.jsonl`
- metadata file like `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`

Output:
- JSONL checkpointable stream, one line per input r1 record, preserving the original
  line and adding:
  - inv_llm_output: {r2: {decision, reason, request_error, classified_at}}
  - wikidata_inverse_link: {r2: bool}

Rules:
- Prefilter: if r1 == r2 -> NO_WAY (no API call).
- LLM decisions are constrained to NO_WAY/TEST; ERROR is only for request/runtime issues.
- Stop condition: if LLM says NO_WAY for (r1, r2) but Wikidata metadata says r2 is
  an inverse link of r1, stop execution.
"""

import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Literal, Optional, Set, Tuple

from openai import OpenAI
from pydantic import BaseModel, ValidationError
from tqdm import tqdm

LOG = logging.getLogger("inverse_llm_jsonl")

Decision = Literal["NO_WAY", "TEST", "ERROR"]
LLMDecision = Literal["NO_WAY", "TEST"]

SYSTEM_PROMPT = (
    "You are an expert Wikidata property analyst specializing in formal relation semantics.\n"
    "\n"
    "TASK:\n"
    "For a fixed relation r1, evaluate EACH listed candidate_r2 independently and decide "
    "whether candidate_r2 could plausibly be the inverse of r1.\n"
    "\n"
    "Definition (Inverse Relation):\n"
    "candidate_r2 is an inverse of r1 if both describe the SAME underlying relationship "
    "but with subject and object roles swapped. "
    "This means candidate_r2 must express the role-reversed meaning of r1.\n"
    "\n"
    "Important semantic constraints:\n"
    "- Inverse requires semantic role-reversal equivalence.\n"
    "- It does NOT mean merely related, correlated, frequently co-occurring, broader/narrower, "
    "causally linked, or topically associated.\n"
    "- If swapping subject and object changes the meaning of the relationship, "
    "the relations are NOT inverses.\n"
    "\n"
    "Decision policy:\n"
    "- NO_WAY: use ONLY when there is a clear semantic contradiction or incompatibility "
    "between r1 and candidate_r2 under role reversal.\n"
    "- TEST: use in all other cases, including uncertainty, ambiguity, sparse metadata, "
    "borderline cases, or partial plausibility.\n"
    "- When uncertain, prefer TEST.\n"
    "\n"
    "Evaluation discipline:\n"
    "- Evaluate each candidate_r2 independently; do NOT transfer reasoning across candidates.\n"
    "- Do NOT invent or omit candidates.\n"
    "- Base reasoning only on the provided information.\n"
    "- Use provided labels/descriptions as semantic hints when available.\n"
    "\n"
    "Reason quality rules:\n"
    "- Each reason must explicitly reference both r1 and the exact candidate_r2 being evaluated.\n"
    "- Provide one concise, specific sentence (maximum ~25 words).\n"
    "- Avoid generic copy-paste explanations unless the semantics are truly identical.\n"
    "- If your stated contradiction could equally apply to multiple unrelated candidates, "
    "choose TEST instead of NO_WAY.\n"
    "\n"
    "Return strictly valid JSON matching the provided schema."
)



RESPONSE_SCHEMA = {
    "name": "inverse_candidate_classification",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "candidate_r2": {"type": "string"},
                        "decision": {"type": "string", "enum": ["NO_WAY", "TEST"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["candidate_r2", "decision", "reason"],
                },
            }
        },
        "required": ["results"],
    },
    "strict": True,
}


class CandidateClassification(BaseModel):
    candidate_r2: str
    decision: LLMDecision
    reason: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def shard_for_r1(r1: str, num_shards: int) -> int:
    h = hashlib.sha256(r1.encode("utf-8")).hexdigest()
    return int(h[:16], 16) % num_shards


def iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{idx}: {exc}") from exc
            if not isinstance(doc, dict):
                raise ValueError(f"Expected object at {path}:{idx}")
            yield doc


def load_profiles(path: str) -> Dict[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError("Profiles JSON must be an array")

    out: Dict[str, Dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        pid = item.get("property_id")
        if not isinstance(pid, str) or not pid:
            continue
        metadata = item.get("metadata") or {}
        inverse_links_raw = metadata.get("inverse_links") or []
        inverse_ids: Set[str] = set()
        if isinstance(inverse_links_raw, list):
            for link in inverse_links_raw:
                if isinstance(link, dict):
                    inv = link.get("property_id")
                    if isinstance(inv, str) and inv:
                        inverse_ids.add(inv)
        out[pid] = {
            "description": metadata.get("description"),
            "datatype": metadata.get("datatype"),
            "inverse_links": inverse_ids,
        }
    return out


def load_labels(path: str) -> Dict[str, str]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError("Labels JSON must be an array")

    out: Dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        pid = item.get("property_id")
        label = item.get("label")
        if isinstance(pid, str) and pid and isinstance(label, str):
            out[pid] = label
    return out


def _inverse_links_to_set(raw: Any) -> Set[str]:
    out: Set[str] = set()
    if not isinstance(raw, list):
        return out
    for x in raw:
        if isinstance(x, dict):
            pid = x.get("property_id")
            if isinstance(pid, str) and pid:
                out.add(pid)
        elif isinstance(x, str) and x:
            out.add(x)
    return out


def load_inverse_alias_context(path: str) -> Dict[str, Dict[str, Any]]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError("Inverse aliases JSON must be an array")

    out: Dict[str, Dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        pid = item.get("pid") or item.get("property_id")
        if not isinstance(pid, str) or not pid:
            continue
        aliases = item.get("inverse_mode_aliases_labels_topk") or item.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        aliases = [x for x in aliases if isinstance(x, str) and x]
        out[pid] = {
            "label": item.get("label"),
            "description": item.get("description"),
            "aliases": aliases,
            "datatype": item.get("datatype"),
            "inverse_links": _inverse_links_to_set(item.get("inverse_links")),
        }
    return out


def _sample_alias_list(raw: Any, max_aliases: int, max_chars: int, salt: str, seed: int) -> List[str]:
    if not isinstance(raw, list):
        return []
    out_all: List[str] = []
    for x in raw:
        if not isinstance(x, str):
            continue
        t = x.strip()
        if not t:
            continue
        if max_chars > 0:
            t = t[:max_chars]
        out_all.append(t)

    if max_aliases <= 0 or len(out_all) <= max_aliases:
        return out_all

    # Deterministic pseudo-random sampling based on seed + relation salt.
    ranked = sorted(
        out_all,
        key=lambda a: hashlib.sha256(f"{seed}|{salt}|{a}".encode("utf-8")).hexdigest(),
    )
    return ranked[:max_aliases]


def extract_r2_from_ranked_list(raw: Any) -> List[str]:
    out: List[str] = []
    if not isinstance(raw, list):
        return out
    for row in raw:
        if isinstance(row, dict):
            r2 = row.get("r2")
            if isinstance(r2, str) and r2:
                out.append(r2)
    return out


def build_candidate_list(doc: Dict[str, Any], source: str) -> List[str]:
    valid_r2 = [x for x in (doc.get("valid_r2") or []) if isinstance(x, str) and x]
    top_support = extract_r2_from_ranked_list(doc.get("top_support"))
    topk_support = extract_r2_from_ranked_list(doc.get("topk_support"))
    support_keys = [
        k for k in (doc.get("support_by_r2") or {}).keys() if isinstance(k, str) and k
    ]

    if source == "valid_r2":
        chosen = valid_r2
    elif source == "top_support":
        chosen = top_support + [x for x in topk_support if x not in set(top_support)]
    elif source == "union":
        seen_union: Set[str] = set()
        chosen = []
        for part in (valid_r2, top_support, topk_support, support_keys):
            for x in part:
                if x not in seen_union:
                    chosen.append(x)
                    seen_union.add(x)
    else:  # auto
        if valid_r2:
            chosen = valid_r2
        elif top_support or topk_support:
            chosen = top_support + [x for x in topk_support if x not in set(top_support)]
        else:
            chosen = support_keys

    seen: Set[str] = set()
    out: List[str] = []
    for r2 in chosen:
        if r2 not in seen:
            out.append(r2)
            seen.add(r2)
    return out


def support_for_r2(doc: Dict[str, Any], r2: str) -> Optional[int]:
    support = (doc.get("support_by_r2") or {}).get(r2)
    return support if isinstance(support, int) else None


def build_llm_payload(
    r1: str,
    r1_label: Optional[str],
    r1_desc: Optional[str],
    r1_aliases: List[str],
    r1_inverse_links: Set[str],
    doc: Dict[str, Any],
    candidates: List[str],
    profiles: Dict[str, Dict[str, Any]],
    labels: Dict[str, str],
    inverse_alias_ctx: Dict[str, Dict[str, Any]],
    max_aliases_per_relation: int,
    max_alias_chars: int,
    alias_sample_seed: int,
) -> Dict[str, Any]:
    payload_candidates: List[Dict[str, Any]] = []
    for r2 in candidates:
        p2 = profiles.get(r2) or {}
        c2 = inverse_alias_ctx.get(r2) or {}
        payload_candidates.append(
            {
                "candidate_r2": r2,
                "r2_label": c2.get("label") or labels.get(r2),
                "r2_description": c2.get("description") or p2.get("description"),
                "r2_aliases": _sample_alias_list(
                    c2.get("aliases") or [],
                    max_aliases_per_relation,
                    max_alias_chars,
                    salt=f"r2:{r2}",
                    seed=alias_sample_seed,
                ),
                "support": support_for_r2(doc, r2),
                "wikidata_inverse_link_match": r2 in r1_inverse_links,
            }
        )
    return {
        "r1": r1,
        "r1_label": r1_label,
        "r1_description": r1_desc,
        "r1_aliases": _sample_alias_list(
            r1_aliases,
            max_aliases_per_relation,
            max_alias_chars,
            salt=f"r1:{r1}",
            seed=alias_sample_seed,
        ),
        "candidates": payload_candidates,
        "rules": {
            "no_way_threshold": "Use NO_WAY only if fully certain impossible; else TEST.",
            "no_hallucination": "Classify only listed candidate_r2 values.",
        },
    }


def parse_llm_response(raw_text: str) -> List[CandidateClassification]:
    payload = json.loads(raw_text)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("LLM output missing 'results' list")
    results: List[CandidateClassification] = []
    for item in payload["results"]:
        results.append(CandidateClassification.model_validate(item))
    return results


def verify_llm_results(expected_candidates: List[str], results: List[CandidateClassification]) -> None:
    expected = set(expected_candidates)
    got = {x.candidate_r2 for x in results}
    if len(got) != len(results):
        raise ValueError("LLM output contains duplicate candidate_r2 entries")
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        raise ValueError(f"LLM result mismatch. missing={missing} extra={extra}")


def call_llm(client: OpenAI, model: str, payload: Dict[str, Any]) -> List[CandidateClassification]:
    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Classify inverse candidacy for r1 against all listed candidate_r2 values.\n"
                            "Return only JSON with key 'results'.\n"
                            f"{json.dumps(payload, ensure_ascii=True)}"
                        ),
                    },
                ],
                response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
                temperature=0,
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty LLM response")
            parsed = parse_llm_response(content)
            verify_llm_results([x["candidate_r2"] for x in payload["candidates"]], parsed)
            return parsed
        except Exception as exc:  # pylint: disable=broad-except
            last_exc = exc
            if attempt < 3:
                sleep_sec = min(2 ** (attempt - 1), 30)
                LOG.warning("LLM call attempt %d failed, retrying in %ds: %s", attempt, sleep_sec, exc)
                time.sleep(sleep_sec)
    if last_exc is None:
        raise RuntimeError("LLM call failed for unknown reason")
    raise last_exc


def is_row_resume_complete(row: Dict[str, Any], candidate_source: str) -> bool:
    r1 = row.get("r1")
    if not isinstance(r1, str) or not r1:
        return False

    expected_candidates = build_candidate_list(row, source=candidate_source)
    expected_set = set(expected_candidates)

    inv_out_raw = row.get("inv_llm_output") or {}
    if not isinstance(inv_out_raw, dict):
        return False
    actual_set = set(inv_out_raw.keys())
    if actual_set != expected_set:
        return False

    status = row.get("inv_llm_status") or {}
    if isinstance(status, dict) and status.get("stop_reason"):
        return False
    cfg = row.get("inv_llm_config") or {}
    if isinstance(cfg, dict):
        old_source = cfg.get("candidate_source")
        if isinstance(old_source, str) and old_source and old_source != candidate_source:
            return False

    if not expected_candidates:
        return True

    all_error = True
    for r2 in expected_candidates:
        v = inv_out_raw.get(r2)
        if not isinstance(v, dict):
            return False
        decision = v.get("decision")
        if decision != "ERROR":
            all_error = False
    if all_error:
        return False

    return True


def load_processed_r1(output_path: str, candidate_source: str) -> Set[str]:
    if not os.path.exists(output_path):
        return set()
    done: Set[str] = set()
    for row in iter_jsonl(output_path):
        r1 = row.get("r1")
        if isinstance(r1, str) and r1 and is_row_resume_complete(row, candidate_source=candidate_source):
            done.add(r1)
    return done


def init_result_entry(decision: Decision, reason: str, request_error: Optional[str]) -> Dict[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "request_error": request_error,
        "classified_at": utc_now_iso(),
    }


def classify_record(
    doc: Dict[str, Any],
    client: OpenAI,
    model: str,
    batch_size: int,
    show_payload: bool,
    candidate_source: str,
    profiles: Dict[str, Dict[str, Any]],
    labels: Dict[str, str],
    inverse_alias_ctx: Dict[str, Dict[str, Any]],
    enforce_wikibase_item: bool,
    max_aliases_per_relation: int,
    max_alias_chars: int,
    alias_sample_seed: int,
) -> Tuple[Dict[str, Any], Optional[str], Dict[str, Any]]:
    r1 = doc.get("r1")
    if not isinstance(r1, str) or not r1:
        raise ValueError("Record missing r1")

    p1 = profiles.get(r1) or {}
    c1 = inverse_alias_ctx.get(r1) or {}
    r1_label = c1.get("label") if "label" in c1 else labels.get(r1)
    r1_desc = c1.get("description") if "description" in c1 else p1.get("description")
    r1_aliases = c1.get("aliases") if "aliases" in c1 else []
    if "inverse_links" in c1:
        r1_inverse_links = c1.get("inverse_links") or set()
    else:
        r1_inverse_links = p1.get("inverse_links") or set()
    r1_datatype = c1.get("datatype") if "datatype" in c1 else p1.get("datatype")

    candidates = build_candidate_list(doc, source=candidate_source)
    record_stats: Dict[str, Any] = {
        "total_candidates": len(candidates),
        "prefilter_self_no_way": 0,
        "prefilter_non_wikibase_no_way": 0,
        "llm_batches": 0,
        "llm_batch_errors": 0,
        "stop_triggered": False,
        "decisions": {"NO_WAY": 0, "TEST": 0, "ERROR": 0},
    }
    if not candidates:
        out_doc = dict(doc)
        out_doc["inv_llm_output"] = {}
        out_doc["wikidata_inverse_link"] = {}
        return out_doc, None, record_stats

    inv_out: Dict[str, Dict[str, Any]] = {}
    inverse_match: Dict[str, bool] = {}
    pending_for_llm: List[str] = []

    for r2 in candidates:
        inverse_match[r2] = r2 in r1_inverse_links
        if r1 == r2:
            inv_out[r2] = init_result_entry(
                decision="NO_WAY",
                reason="prefilter: r1 equals r2, so this is not treated as an inverse pair.",
                request_error=None,
            )
            record_stats["prefilter_self_no_way"] += 1
            continue

        if enforce_wikibase_item:
            p2 = profiles.get(r2) or {}
            c2 = inverse_alias_ctx.get(r2) or {}
            r2_datatype = c2.get("datatype") if "datatype" in c2 else p2.get("datatype")
            if r1_datatype != "wikibase-item" or r2_datatype != "wikibase-item":
                inv_out[r2] = init_result_entry(
                    decision="NO_WAY",
                    reason="prefilter: non-wikibase-item datatype under enforce_wikibase_item.",
                    request_error=None,
                )
                record_stats["prefilter_non_wikibase_no_way"] += 1
                continue

        pending_for_llm.append(r2)

    stop_reason: Optional[str] = None
    for i in range(0, len(pending_for_llm), batch_size):
        record_stats["llm_batches"] += 1
        chunk = pending_for_llm[i : i + batch_size]
        payload = build_llm_payload(
            r1=r1,
            r1_label=r1_label,
            r1_desc=r1_desc,
            r1_aliases=r1_aliases,
            r1_inverse_links=r1_inverse_links,
            doc=doc,
            candidates=chunk,
            profiles=profiles,
            labels=labels,
            inverse_alias_ctx=inverse_alias_ctx,
            max_aliases_per_relation=max_aliases_per_relation,
            max_alias_chars=max_alias_chars,
            alias_sample_seed=alias_sample_seed,
        )
        if show_payload:
            LOG.info("LLM payload for r1=%s chunk=%d: %s", r1, i // batch_size, json.dumps(payload, ensure_ascii=True))

        try:
            results = call_llm(client=client, model=model, payload=payload)
            by_r2 = {x.candidate_r2: x for x in results}
            for r2 in chunk:
                item = by_r2[r2]
                inv_out[r2] = init_result_entry(
                    decision=item.decision,
                    reason=item.reason.strip(),
                    request_error=None,
                )
                if item.decision == "NO_WAY" and inverse_match.get(r2, False):
                    stop_reason = (
                        "Stop condition triggered: LLM returned NO_WAY while metadata.inverse_links "
                        f"contains r2 as inverse. r1={r1}, r2={r2}"
                    )
                    record_stats["stop_triggered"] = True
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            err = f"LLM_RESPONSE_ERROR: {exc}"
            record_stats["llm_batch_errors"] += 1
            for r2 in chunk:
                inv_out[r2] = init_result_entry(
                    decision="ERROR",
                    reason="Request failed before valid classification output.",
                    request_error=err,
                )
        except Exception as exc:  # pylint: disable=broad-except
            err = f"LLM_REQUEST_ERROR: {exc}"
            record_stats["llm_batch_errors"] += 1
            for r2 in chunk:
                inv_out[r2] = init_result_entry(
                    decision="ERROR",
                    reason="Request failed before valid classification output.",
                    request_error=err,
                )

        if stop_reason:
            break

    out_doc = dict(doc)
    out_doc["inv_llm_output"] = inv_out
    out_doc["wikidata_inverse_link"] = inverse_match
    error_count = 0
    no_way_count = 0
    test_count = 0
    for v in inv_out.values():
        if not isinstance(v, dict):
            continue
        decision = v.get("decision")
        if decision == "ERROR":
            error_count += 1
        elif decision == "NO_WAY":
            no_way_count += 1
        elif decision == "TEST":
            test_count += 1
    total_candidates = len(candidates)
    all_error = total_candidates > 0 and error_count == total_candidates
    complete = set(inv_out.keys()) == set(candidates)
    classified_candidates = len(inv_out)
    record_stats["decisions"]["NO_WAY"] = no_way_count
    record_stats["decisions"]["TEST"] = test_count
    record_stats["decisions"]["ERROR"] = error_count
    out_doc["inv_llm_status"] = {
        "complete": complete,
        "total_candidates": total_candidates,
        "classified_candidates": classified_candidates,
        "error_count": error_count,
        "all_error": all_error,
        "stop_reason": stop_reason,
        "updated_at": utc_now_iso(),
    }
    out_doc["inv_llm_config"] = {
        "candidate_source": candidate_source,
        "model": model,
        "enforce_wikibase_item": enforce_wikibase_item,
        "updated_at": utc_now_iso(),
    }
    return out_doc, stop_reason, record_stats


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM inverse classification over JSONL hop-support records.")
    parser.add_argument("--input_path", default="data/processed/hop_support.wikibase_item_only.jsonl")
    parser.add_argument(
        "--relation_profiles_path",
        default="data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json",
    )
    parser.add_argument(
        "--labels_path",
        default="",
        help="Optional JSON array file with property_id/label fields.",
    )
    parser.add_argument(
        "--inverse_aliases_path",
        default="data/processed/wikidata_ontology.inverse_mode_aliases_topk.json",
        help="JSON array with pid,label,description,inverse_mode_aliases_labels_topk,datatype,inverse_links.",
    )
    parser.add_argument("--output_path", required=True)
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--batch_size", type=int, default=25, help="Number of r2 candidates per LLM request.")
    parser.add_argument("--max_aliases_per_relation", type=int, default=4, help="Max aliases sent per relation in LLM payload.")
    parser.add_argument("--max_alias_chars", type=int, default=80, help="Max characters per alias sent in LLM payload.")
    parser.add_argument("--alias_sample_seed", type=int, default=42, help="Seed for deterministic pseudo-random alias sampling.")
    parser.add_argument("--candidate_source", choices=["auto", "valid_r2", "top_support", "union"], default="union")
    parser.add_argument("--enforce_wikibase_item", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument("--checkpoint_every", type=int, default=1)
    parser.add_argument("--num_shards", type=int, default=1, help="Deterministic shard count for safe parallel runs.")
    parser.add_argument("--shard_index", type=int, default=0, help="0-based shard index to process.")
    parser.add_argument("--report_path", default="", help="Optional path to write final run report as JSON.")
    parser.add_argument("--show_payload", action="store_true")
    parser.add_argument("--log_level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s [%(levelname)s] %(message)s")
    if args.batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if args.checkpoint_every <= 0:
        raise ValueError("checkpoint_every must be > 0")
    if args.max_aliases_per_relation < 0:
        raise ValueError("max_aliases_per_relation must be >= 0")
    if args.max_alias_chars < 0:
        raise ValueError("max_alias_chars must be >= 0")
    if args.num_shards <= 0:
        raise ValueError("num_shards must be > 0")
    if args.shard_index < 0 or args.shard_index >= args.num_shards:
        raise ValueError("shard_index must be in [0, num_shards)")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    client = OpenAI(api_key=api_key, base_url=base_url)

    profiles = load_profiles(args.relation_profiles_path)
    labels = load_labels(args.labels_path)
    inverse_alias_ctx: Dict[str, Dict[str, Any]] = {}
    if args.inverse_aliases_path:
        if os.path.exists(args.inverse_aliases_path):
            inverse_alias_ctx = load_inverse_alias_context(args.inverse_aliases_path)
        else:
            LOG.warning("inverse_aliases_path not found: %s; continuing without alias context.", args.inverse_aliases_path)
    LOG.info("Loaded relation profiles: %d", len(profiles))
    if args.labels_path:
        LOG.info("Loaded property labels: %d", len(labels))
    if args.inverse_aliases_path:
        LOG.info("Loaded inverse alias context rows: %d", len(inverse_alias_ctx))
    LOG.info(
        "Run config input=%s output=%s candidate_source=%s model=%s resume=%s reprocess=%s labels_path=%s inverse_aliases_path=%s num_shards=%d shard_index=%d",
        args.input_path,
        args.output_path,
        args.candidate_source,
        args.model,
        args.resume,
        args.reprocess,
        args.labels_path,
        args.inverse_aliases_path,
        args.num_shards,
        args.shard_index,
    )

    processed: Set[str] = set()
    if args.resume and not args.reprocess:
        processed = load_processed_r1(args.output_path, candidate_source=args.candidate_source)
        LOG.info("Resume enabled. Already processed r1 count: %d", len(processed))

    write_mode = "w" if args.reprocess else "a"
    written = 0
    stop_reason: Optional[str] = None
    start_ts = time.time()
    run_stats: Dict[str, Any] = {
        "input_records_seen": 0,
        "invalid_r1_skipped": 0,
        "resume_skipped": 0,
        "written_records": 0,
        "stop_triggered_records": 0,
        "candidate_total": 0,
        "decision_counts": {"NO_WAY": 0, "TEST": 0, "ERROR": 0},
        "prefilter_self_no_way": 0,
        "prefilter_non_wikibase_no_way": 0,
        "llm_batches": 0,
        "llm_batch_errors": 0,
        "shard_skipped": 0,
    }

    with open(args.output_path, write_mode, encoding="utf-8") as out_f:
        progress = tqdm(desc="Classifying r1 records", unit="r1")
        for doc in iter_jsonl(args.input_path):
            run_stats["input_records_seen"] += 1
            r1 = doc.get("r1")
            if not isinstance(r1, str) or not r1:
                LOG.warning("Skipping record with invalid r1")
                run_stats["invalid_r1_skipped"] += 1
                progress.update(1)
                continue
            if shard_for_r1(r1, args.num_shards) != args.shard_index:
                run_stats["shard_skipped"] += 1
                progress.update(1)
                continue
            if not args.reprocess and r1 in processed:
                run_stats["resume_skipped"] += 1
                progress.update(1)
                continue

            classified, local_stop_reason, rec_stats = classify_record(
                doc=doc,
                client=client,
                model=args.model,
                batch_size=args.batch_size,
                show_payload=args.show_payload,
                candidate_source=args.candidate_source,
                profiles=profiles,
                labels=labels,
                inverse_alias_ctx=inverse_alias_ctx,
                enforce_wikibase_item=args.enforce_wikibase_item,
                max_aliases_per_relation=args.max_aliases_per_relation,
                max_alias_chars=args.max_alias_chars,
                alias_sample_seed=args.alias_sample_seed,
            )
            run_stats["candidate_total"] += rec_stats["total_candidates"]
            run_stats["prefilter_self_no_way"] += rec_stats["prefilter_self_no_way"]
            run_stats["prefilter_non_wikibase_no_way"] += rec_stats["prefilter_non_wikibase_no_way"]
            run_stats["llm_batches"] += rec_stats["llm_batches"]
            run_stats["llm_batch_errors"] += rec_stats["llm_batch_errors"]
            run_stats["decision_counts"]["NO_WAY"] += rec_stats["decisions"]["NO_WAY"]
            run_stats["decision_counts"]["TEST"] += rec_stats["decisions"]["TEST"]
            run_stats["decision_counts"]["ERROR"] += rec_stats["decisions"]["ERROR"]

            out_f.write(json.dumps(classified, ensure_ascii=True) + "\n")
            written += 1
            run_stats["written_records"] = written
            if written % args.checkpoint_every == 0:
                out_f.flush()
                os.fsync(out_f.fileno())
                LOG.info("Checkpoint flushed at written_records=%d", written)

            if local_stop_reason:
                stop_reason = local_stop_reason
                run_stats["stop_triggered_records"] += 1
                LOG.error(stop_reason)
                progress.update(1)
                break

            progress.update(1)

        progress.close()
        out_f.flush()
        os.fsync(out_f.fileno())

    elapsed_sec = time.time() - start_ts
    report = {
        "started_at": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
        "finished_at": utc_now_iso(),
        "elapsed_sec": round(elapsed_sec, 3),
        "input_path": args.input_path,
        "output_path": args.output_path,
        "relation_profiles_path": args.relation_profiles_path,
        "labels_path": args.labels_path,
        "inverse_aliases_path": args.inverse_aliases_path,
        "model": args.model,
        "candidate_source": args.candidate_source,
        "resume": args.resume,
        "reprocess": args.reprocess,
        "enforce_wikibase_item": args.enforce_wikibase_item,
        "checkpoint_every": args.checkpoint_every,
        "num_shards": args.num_shards,
        "shard_index": args.shard_index,
        "max_aliases_per_relation": args.max_aliases_per_relation,
        "max_alias_chars": args.max_alias_chars,
        "alias_sample_seed": args.alias_sample_seed,
        "stats": run_stats,
        "stop_reason": stop_reason,
    }

    LOG.info("Run summary: %s", json.dumps(report["stats"], ensure_ascii=True))
    LOG.info("Wrote %d new records to %s", written, args.output_path)
    LOG.info("Finished at %s", utc_now_iso())
    if args.report_path:
        with open(args.report_path, "w", encoding="utf-8") as rf:
            rf.write(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
        LOG.info("Wrote final report to %s", args.report_path)
    if stop_reason:
        raise RuntimeError(stop_reason)


if __name__ == "__main__":
    main()
