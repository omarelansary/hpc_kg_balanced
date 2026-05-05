#!/usr/bin/env python3
import argparse
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from pymongo import MongoClient
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm
from typing import Literal


LOG = logging.getLogger("classify_relations_pipeline")


SYSTEM_PROMPT = (
    "You are an Expert Ontologist and Logician.\n"
    "Your output MUST follow the provided JSON schema exactly.\n"
    "\n"
    "ASSUMPTION:\n"
    "All input relations are wikibase-item (entity→entity) properties.\n"
    "Do NOT evaluate datatype or logic applicability.\n"
    "\n"
    "2) Logic triage for pattern mining (symmetry / anti-symmetry / inverse triage):\n"
    "Your job is NOT to prove patterns.\n"
    "Your job is to reduce Wikidata search space by deciding whether a relation is worth testing.\n"
    "\n"
    "For each pattern, output one triage label:\n"
    "- NO_WAY (testing would be wasted)\n"
    "- TEST (worth testing)\n"
    "- LOW_PRIORITY (possible but unlikely)\n"
    "Also provide a short reason based on semantics and domain/range,if domain/range is unknown or weak, rely on semantics.\n"
    "\n"
    "Definitions:\n"
    "- Symmetry: (h,r,t) implies (t,r,h)\n"
    "- Anti-symmetry (KG sense): (h,r,t) implies (t,r,h) does NOT hold\n"
    "(i.e., reverse edges between distinct entities are not expected)\n"
    "- Inverse: (h,r,t) implies (t,rinv,h)\n"
    "\n"
    "A) Symmetry triage:\n"
    "- NO_WAY if the relation is inherently directional by meaning (e.g., parent_of, part_of, causes).\n"
    "- TEST if the relation is plausibly mutual or undirected (e.g., spouse_of, adjacent_to).\n"
    "- LOW_PRIORITY if unclear or evidence is weak.\n"
    "\n"
    "B) Anti-symmetry triage:\n"
    "- TEST if the relation is directional by meaning and reverse edges between distinct entities are not expected (e.g., hierarchy, containment, ancestry, attribute assignment, origin/location relations).\n"
    "- NO_WAY if the relation is plausibly symmetric or mutual by meaning.\n"
    "- IMPORTANT: If the inverse direction is ill-typed or not normally modeled in Wikidata,\n"
    "  mark LOW_PRIORITY (not NO_WAY), because Wikidata typing may be incomplete.\n"
    "\n"
    "C) Inverse triage:\n"
    "- TEST if an inverse relation is semantically expected and commonly modeled as a separate relation (e.g., child vs parent).\n"
    "- NO_WAY only if the relation is clearly symmetric (self-inverse).\n"
    "- If the reverse direction is conceptually meaningful but not typically modeled as a Wikidata relation, choose LOW_PRIORITY.\n"
    "- If unsure, choose LOW_PRIORITY and optionally suggest 1–3 likely inverse labels.\n"
    "- Do NOT infer one pattern from another (e.g., symmetry does not imply non-transitivity).\n"
    "\n"
    "General conservatism:\n"
    "- Use NO_WAY sparingly.\n"
    "- Only use NO_WAY when you are confident testing would be structurally or semantically wasted.\n"
    "- When unsure between TEST and LOW_PRIORITY, choose TEST.\n"
    "- Do NOT mark a relation as both symmetric and anti-symmetric.\n"
    "\n"
    "3) Composition TARGET triage:\n"
    "Your job is ONLY to decide whether this relation could plausibly be a TARGET\n"
    "of a 2-hop composition rule that connects a to c.\n"
    "r1 and r2 may be DIFFERENT relations, but may also be the SAME relation (self-composition, e.g., includes ∘ includes).\n"
    "\n"
    "Definition context:\n"
    "A relation r is a composite target if there exist r1 and r2 such that\n"
    "r1(a,b) and r2(b,c) imply r(a,c).\n"
    "\n"
    "IMPORTANT:\n"
    "- You are NOT proving composition.\n"
    "- You are ONLY deciding whether r is worth testing as a TARGET.\n"
    "\n"
    "Output:\n"
    "- composition_target = YES or NO_WAY\n"
    "- composition_reason (short)\n"
    "\n"
    "Rules:\n"
    "- Composition here refers to a DEFINITONAL relational shortcut, not an explanatory or provenance chain.\n"
    "- Do NOT consider chains that merely explain how an attribute value or classification was assigned (attribute propagation). Such relations are NOT composition targets.\n"
    "- Choose NO_WAY when r is clearly a terminal attribute/value/classification\n"
    "  relation (e.g., \"type of\", \"classification\", \"characteristic of\", \"has value\").\n"
    "- Otherwise, choose YES when there exists a plausible semantic interpretation where r could compress a meaningful 2-hop path into a direct a→c relation.\n"
    "- When unsure, choose YES (high recall).\n"
    "- Choose NO_WAY only when testing would be structurally or semantically wasted.\n\n"
    "Examples:\n"
    "- grandparent_of is a composition target (YES) because parent_of(a,b) and parent_of(b,c) imply grandparent_of(a,c).\n"
    "- member_of is a composition target (YES) because member_of(a,b) and part_of(b,c) imply member_of(a,c).\n"
    "- capital_of is a composition target (YES), because capital_of(a,b) and located_in(b,c) imply capital_of(a,c).\n"
    "- spouse_of is NOT a composition target (NO_WAY) because spouse_of(a,b) and spouse_of(b,c) do NOT imply spouse_of(a,c).\n"
    "- birth_place is NOT a composition target (NO_WAY) because birth_place(a,b) and located_in(b,c) do NOT imply birth_place(a,c).\n"
)

#TODO: refine prompt and instructions for compostion and transitivity  and also the SCHEMA accordingly

RESPONSE_SCHEMA = {
    "name": "relation_classification_response",
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
                        "relation_id": {
                            "type": "string"
                        },

                        "logic": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "symmetry": {"$ref": "#/$defs/triage_signal"},
                                "anti_symmetry": {"$ref": "#/$defs/triage_signal"},
                                "inverse": {"$ref": "#/$defs/triage_signal"}
                            },
                            "required": ["symmetry", "anti_symmetry", "inverse"]
                        },

                        "composition": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "composition_target": {
                                    "type": "string",
                                    "enum": ["YES", "NO_WAY"]
                                },
                                "composition_reason": {
                                    "type": "string"
                                }
                            },
                            "required": ["composition_target", "composition_reason"]
                        }
                    },
                    "required": ["relation_id", "logic", "composition"]
                }
            }
        },
        "required": ["results"],
        "$defs": {
            "triage_signal": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "decision": {
                        "type": "string",
                        "enum": ["NO_WAY", "TEST", "LOW_PRIORITY"]
                    },
                    "reason": {
                        "type": "string"
                    }
                },
                "required": ["decision", "reason"]
            }
        }
    },
    "strict": True
}

TriageDecision = Literal["NO_WAY", "TEST", "LOW_PRIORITY"]
CompositionTarget = Literal["YES", "NO_WAY"]

class TriageSignal(BaseModel):
    decision: TriageDecision
    reason: str

class LogicBlock(BaseModel):
    symmetry: TriageSignal
    anti_symmetry: TriageSignal
    inverse: TriageSignal


class CompositionBlock(BaseModel):
    composition_target: CompositionTarget
    composition_reason: str


class RelationClassification(BaseModel):
    relation_id: str
    logic: LogicBlock
    composition: CompositionBlock


def normalize_datatype(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def is_wikibase_item(datatype: Optional[str]) -> bool:
    return normalize_datatype(datatype) == "wikibase-item"


def normalize_qid(value: Optional[str]) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    if value.startswith("http"):
        value = value.rsplit("/", 1)[-1]
    if value.startswith("Q") and value[1:].isdigit():
        return value
    return None


def build_prefilter_result(relation_id: str) -> Dict[str, Any]:
    """in pure math, a relation over literals can still be symmetric etc., but 
    for Wikidata KG pattern mining, our decision is valid because we are 
    restricting scope to entity–entity relations."""
    
    reason = "Excluded by preprocessing: datatype is not wikibase-item (literal/identifier). Out of scope for entity→entity pattern mining."
    return {
        "relation_id": relation_id,
        "logic": {
            "symmetry": {"decision": "NO_WAY", "reason": reason},
            "anti_symmetry": {"decision": "NO_WAY", "reason": reason},
            "inverse": {"decision": "NO_WAY", "reason": reason},
        },
        "composition": {
            "composition_target": "NO_WAY",
            "composition_reason": reason,
        },
    }

def build_user_payload(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"relations": batch}


def extract_relation_id(doc: Dict[str, Any]) -> Optional[str]:
    for key in ("id", "property_id", "relation_id"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def extract_batch_item(
    doc: Dict[str, Any],
    property_meta: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    relation_id = extract_relation_id(doc)
    if not relation_id:
        return None
    meta = doc.get("meta") or doc.get("metadata") or {}
    label = meta.get("label") or doc.get("label")
    description = meta.get("description") or doc.get("description")
    datatype = meta.get("datatype") or doc.get("datatype")
    domains = meta.get("domains") or doc.get("domains") or meta.get("valid_subject_type_ids") or doc.get(
        "valid_subject_type_ids"
    )
    ranges = meta.get("ranges") or doc.get("ranges") or meta.get("valid_object_type_ids") or doc.get(
        "valid_object_type_ids"
    )
    examples = doc.get("examples") or meta.get("examples") or []

    fallback = property_meta.get(relation_id) or {}
    if not label:
        label = fallback.get("label")
    if not domains:
        domains = fallback.get("valid_subject_type_ids") or []
    if not ranges:
        ranges = fallback.get("valid_object_type_ids") or []

    return {
        "relation_id": relation_id,
        "label": label,
        "description": description,
        "datatype": datatype,
        "domains": domains or [],
        "ranges": ranges or [],
        "examples": examples,
    }


def get_entity_label(
    qid: str,
    labels_col,
    cache: Dict[str, Optional[str]],
) -> Optional[str]:
    if qid in cache:
        return cache[qid]
    doc = labels_col.find_one({"entity_id": qid}, {"label": 1})
    label = doc.get("label") if doc else None
    cache[qid] = label
    return label


def build_examples_for_relation(
    relation_id: str,
    triplets_col,
    labels_col,
    label_cache: Dict[str, Optional[str]],
    property_label: Optional[str],
    limit: int,
) -> List[str]:
    examples: List[str] = []
    cursor = triplets_col.find(
        {"property_id": relation_id},
        {"subject": 1, "object": 1},
    ).sort("_id", 1).limit(limit)
    for doc in cursor:
        subject_raw = doc.get("subject")
        object_raw = doc.get("object")
        subject_qid = normalize_qid(subject_raw)
        object_qid = normalize_qid(object_raw)
        subject_label = None
        object_label = None
        if subject_qid:
            subject_label = get_entity_label(subject_qid, labels_col, label_cache)
        if object_qid:
            object_label = get_entity_label(object_qid, labels_col, label_cache)
        subject_display = subject_label or subject_qid or str(subject_raw)
        object_display = object_label or object_qid or str(object_raw)
        predicate_display = property_label or relation_id
        examples.append(f"{subject_display} --{predicate_display}--> {object_display}")
    return examples


def build_aliases_for_relation(
    relation_id: str,
    aliases_col,
    limit: int,
) -> List[str]:
    aliases: List[str] = []
    cursor = aliases_col.find(
        {"relation_id": relation_id},
        {"alias_label": 1},
    ).sort("_id", 1).limit(limit)
    for doc in cursor:
        label = doc.get("alias_label")
        if isinstance(label, str) and label.strip():
            aliases.append(label)
    return aliases


def parse_llm_response(raw_text: str) -> List[RelationClassification]:
    payload = json.loads(raw_text)
    items = None
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            items = payload.get("results")
        elif isinstance(payload.get("relations"), list):
            items = payload.get("relations")
        elif isinstance(payload.get("items"), list):
            items = payload.get("items")
        elif isinstance(payload.get("data"), list):
            items = payload.get("data")
        elif "relation_id" in payload:
            items = [payload]
        else:
            for value in payload.values():
                if isinstance(value, list):
                    items = value
                    break
    if not isinstance(items, list):
        keys = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        raise ValueError(f"LLM output is not a list (keys={keys})")
    parsed: List[RelationClassification] = []
    for item in items:
        parsed.append(RelationClassification.model_validate(item))
    return parsed


def verify_classification(item: RelationClassification) -> Optional[str]:
    errors: List[str] = []

    # Mutual exclusion invariant (strong)
    if (
        item.logic.symmetry.decision == "TEST"
        and item.logic.anti_symmetry.decision == "TEST"
    ):
        errors.append("ConflictSymmetryVsAntiSymmetry")

    if not errors:
        return None
    return "|".join(errors)


def apply_any_antisymmetry_guard(
    item: RelationClassification,
    has_any_domain_or_range: bool,
) -> Optional[str]:
    if not has_any_domain_or_range:
        return None
    if item.logic.anti_symmetry.decision != "TEST":
        return None
    item.logic.anti_symmetry.decision = "LOW_PRIORITY"
    return "AntiSymmetryNeedsTypedDomainRange"


@retry(wait=wait_exponential(min=1, max=30), stop=stop_after_attempt(3))
def call_llm(client: OpenAI, model: str, user_payload: Dict[str, Any]) -> List[RelationClassification]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Classify the following relations. Return ONLY valid JSON "
                    "as an object with a single key 'results' containing a list "
                    "of objects matching the required schema.\n"
                    f"{json.dumps(user_payload, ensure_ascii=True)}"
                ),
            },
        ],
        response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty LLM response")
    return parse_llm_response(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify Wikidata relations with an LLM.")
    parser.add_argument("--mongo_uri", required=True)
    parser.add_argument("--db_name", default="wikidata_ontology")
    parser.add_argument("--collection", default="relation_profiles")
    parser.add_argument("--properties_db", default="wikidata_ontology")
    parser.add_argument("--properties_collection", default="properties")
    parser.add_argument("--aliases_db", default="wikidata_ontology")
    parser.add_argument("--aliases_collection", default="property_aliases")
    parser.add_argument("--aliases_limit", type=int, default=10)
    parser.add_argument("--triplets_db", default="triplets_db")
    parser.add_argument("--triplets_collection", default="initial_triplets")
    parser.add_argument("--entity_labels_collection", default="entity_labels")
    parser.add_argument("--examples_per_relation", type=int, default=3)
    parser.add_argument("--show_payload", action="store_true")
    parser.add_argument("--payload_path", default="")
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--batch_size", type=int, default=20)
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument("--log_level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s [%(levelname)s] %(message)s")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    client = OpenAI(api_key=api_key, base_url=base_url)

    mongo = MongoClient(args.mongo_uri)
    db = mongo.get_database(args.db_name)
    collection = db.get_collection(args.collection)
    triplets_db = mongo.get_database(args.triplets_db)
    triplets_col = triplets_db.get_collection(args.triplets_collection)
    labels_col = triplets_db.get_collection(args.entity_labels_collection)
    aliases_db = mongo.get_database(args.aliases_db)
    aliases_col = aliases_db.get_collection(args.aliases_collection)
    property_meta: Dict[str, Dict[str, Any]] = {}
    if args.properties_collection:
        properties_db = db if not args.properties_db else mongo.get_database(args.properties_db)
        properties_col = properties_db.get_collection(args.properties_collection)
        for doc in properties_col.find(
            {},
            {"property_id": 1, "label": 1, "valid_subject_type_ids": 1, "valid_object_type_ids": 1},
        ):
            prop_id = doc.get("property_id")
            if not isinstance(prop_id, str) or not prop_id:
                continue
            property_meta[prop_id] = {
                "label": doc.get("label"),
                "valid_subject_type_ids": doc.get("valid_subject_type_ids") or [],
                "valid_object_type_ids": doc.get("valid_object_type_ids") or [],
            }

    query: Dict[str, Any] = {}
    if not args.reprocess:
        query = {"$or": [{"llm_classification": {"$exists": False}}, {"llm_classification": None}]}

    total = collection.count_documents(query)
    progress = tqdm(total=total, desc="Classifying relations", unit="relation")

    batch: List[Dict[str, Any]] = []
    batch_ids: List[str] = []
    batch_doc_ids: Dict[str, Any] = {}
    batch_any_guard: Dict[str, bool] = {}
    label_cache: Dict[str, Optional[str]] = {}
    payload_log = None
    if args.payload_path:
        payload_log = open(args.payload_path, "a", encoding="utf-8")

    cursor = collection.find(
        query,
        {
            "id": 1,
            "property_id": 1,
            "relation_id": 1,
            "meta": 1,
            "metadata": 1,
            "label": 1,
            "description": 1,
            "datatype": 1,
            "domains": 1,
            "ranges": 1,
            "valid_subject_type_ids": 1,
            "valid_object_type_ids": 1,
            "examples": 1,
        },
    )
    for doc in cursor:
        relation_id = extract_relation_id(doc)
        if not relation_id:
            progress.update(1)
            continue

        meta = doc.get("meta") or doc.get("metadata") or {}
        datatype = meta.get("datatype") or doc.get("datatype")
        if datatype and not is_wikibase_item(datatype):
            classification = build_prefilter_result(relation_id)
            update: Dict[str, Any] = {"$set": {"llm_classification": classification}}
            update["$unset"] = {"verification_error": ""}
            collection.update_one({"_id": doc["_id"]}, update)
            progress.update(1)
            continue

        item = extract_batch_item(doc, property_meta)
        if not item:
            progress.update(1)
            continue
        if args.examples_per_relation > 0:
            property_label = item.get("label")
            examples = build_examples_for_relation(
                relation_id,
                triplets_col,
                labels_col,
                label_cache,
                property_label,
                args.examples_per_relation,
            )
            if examples:
                item["examples"] = examples
        if args.aliases_limit > 0:
            aliases = build_aliases_for_relation(relation_id, aliases_col, args.aliases_limit)
            if aliases:
                item["aliases"] = aliases
        batch.append(item)
        batch_ids.append(relation_id)
        batch_doc_ids[relation_id] = doc["_id"]
        domains = item.get("domains") or []
        ranges = item.get("ranges") or []
        batch_any_guard[relation_id] = ("ANY" in domains) or ("ANY" in ranges)

        if len(batch) >= args.batch_size:
            payload = build_user_payload(batch)
            if args.show_payload:
                LOG.info("LLM payload: %s", json.dumps(payload, ensure_ascii=True))
            if payload_log:
                payload_log.write(json.dumps(payload, ensure_ascii=True) + "\n")
            try:
                parsed = call_llm(client, args.model, payload)
                results_by_id = {item.relation_id: item for item in parsed}
                for rel_id in batch_ids:
                    result = results_by_id.get(rel_id)
                    if not result:
                        LOG.warning("Missing LLM result for %s", rel_id)
                        progress.update(1)
                        continue
                    any_error = apply_any_antisymmetry_guard(result, batch_any_guard.get(rel_id, False))
                    error = verify_classification(result)
                    if any_error:
                        error = "|".join([e for e in [error, any_error] if e])
                    update: Dict[str, Any] = {"$set": {"llm_classification": result.model_dump()}}
                    if error:
                        update["$set"]["verification_error"] = error
                    else:
                        update["$unset"] = {"verification_error": ""}
                    collection.update_one({"_id": batch_doc_ids.get(rel_id)}, update)
                    progress.update(1)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                LOG.exception("Batch failed due to parsing/validation error: %s", exc)
                progress.update(len(batch))
            except Exception as exc:  # pylint: disable=broad-except
                LOG.exception("Batch failed due to unexpected error: %s", exc)
                progress.update(len(batch))
            batch = []
            batch_ids = []
            batch_doc_ids = {}
            batch_any_guard = {}

    if batch:
        payload = build_user_payload(batch)
        if args.show_payload:
            LOG.info("LLM payload: %s", json.dumps(payload, ensure_ascii=True))
        if payload_log:
            payload_log.write(json.dumps(payload, ensure_ascii=True) + "\n")
        try:
            parsed = call_llm(client, args.model, payload)
            results_by_id = {item.relation_id: item for item in parsed}
            for rel_id in batch_ids:
                result = results_by_id.get(rel_id)
                if not result:
                    LOG.warning("Missing LLM result for %s", rel_id)
                    progress.update(1)
                    continue
                any_error = apply_any_antisymmetry_guard(result, batch_any_guard.get(rel_id, False))
                error = verify_classification(result)
                if any_error:
                    error = "|".join([e for e in [error, any_error] if e])
                update = {"$set": {"llm_classification": result.model_dump()}}
                if error:
                    update["$set"]["verification_error"] = error
                else:
                    update["$unset"] = {"verification_error": ""}
                collection.update_one({"_id": batch_doc_ids.get(rel_id)}, update)
                progress.update(1)
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            LOG.exception("Final batch failed due to parsing/validation error: %s", exc)
            progress.update(len(batch))
        except Exception as exc:  # pylint: disable=broad-except
            LOG.exception("Final batch failed due to unexpected error: %s", exc)
            progress.update(len(batch))

    progress.close()
    if payload_log:
        payload_log.close()
    LOG.info("Classification run finished at %s", datetime.utcnow().isoformat())


if __name__ == "__main__":
    main()
