#!/usr/bin/env python3
"""
Alias/Label selector for Wikidata properties (PIDs) optimized for LLM tasks.

Goal
----
Given a Wikidata property id (e.g., "P1001"), return:
- label
- description
- up to K aliases (carefully chosen)

Why selection matters
---------------------
For tasks like inverse-candidacy classification, dumping all aliases creates noise.
This module selects a small, informative subset using:
1) semantic centrality (embedding centroid similarity) when embeddings exist
2) task-specific lexical heuristics ("modes") to favor directionally-informative aliases

Data backends
-------------
Supports both:
1) MongoDB collections
2) JSON export files (Mongo exported arrays)

Expected alias schema in both modes:
{ "relation_id": "P1001", "alias_label": "...", "alias_text_embedding": [float,...] }
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Generator, Iterable, List, Literal, Optional, Sequence, Tuple

import numpy as np

try:
    from pymongo.collection import Collection
    from pymongo.database import Database
except Exception:  # pragma: no cover
    Collection = Any  # type: ignore
    Database = Any  # type: ignore


Mode = Literal["inverse", "generic", "entity_type", "debug"]


_STOPWORDS = {
    "of", "the", "a", "an", "and", "or", "to", "in", "on", "for", "from", "by", "with",
    "is", "are", "was", "were", "be", "being", "been", "as", "at", "into", "over",
}


def _normalize_text(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _tokenize(s: str) -> List[str]:
    return [t for t in re.split(r"[^A-Za-z0-9]+", s.lower()) if t]


def _cosine(u: np.ndarray, v: np.ndarray) -> float:
    # robust cosine for possibly near-zero vectors
    if u.shape != v.shape:
        return -1.0
    un = np.linalg.norm(u)
    vn = np.linalg.norm(v)
    if un == 0.0 or vn == 0.0:
        return -1.0
    return float(np.dot(u, v) / (un * vn))


@dataclass(frozen=True)
class AliasCandidate:
    text: str
    emb: Optional[np.ndarray]  # None if missing
    # computed scores
    centrality: float = 0.0
    label_similarity: float = 0.0
    heuristic: float = 0.0
    combined: float = 0.0


class PropertyAliasSelector:
    """
    Selects K aliases for a property id under a given mode.

    Typical usage:
        selector = PropertyAliasSelector(db, properties_col="properties", aliases_col="property_aliases")
        info = selector.get(pid="P1001", k=3, mode="inverse")
        # info = {"pid":..., "label":..., "description":..., "aliases":[...], "debug":{...}}
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        properties_col: str = "properties",
        aliases_col: str = "property_aliases",
        label_field: str = "label",
        description_field: str = "description",
        pid_field: str = "property_id",
        alias_pid_field: str = "relation_id",
        alias_text_field: str = "alias_label",
        alias_emb_field: str = "alias_text_embedding",
        label_emb_field: str = "label_text_embedding",
        properties_json_path: str = "",
        aliases_json_path: str = "",
        label_embeddings_json_path: str = "",
        preload_aliases_json: bool = False,
        label_similarity_weight: float = 0.35,
    ) -> None:
        self.db = db
        self.backend: Literal["mongo", "json"]
        if db is not None:
            self.backend = "mongo"
            self.properties: Optional[Collection] = db.get_collection(properties_col)
            self.aliases: Optional[Collection] = db.get_collection(aliases_col)
        else:
            if not aliases_json_path:
                raise ValueError("aliases_json_path is required in json mode")
            self.backend = "json"
            self.properties = None
            self.aliases = None
        self.label_field = label_field
        self.description_field = description_field
        self.pid_field = pid_field
        self.alias_pid_field = alias_pid_field
        self.alias_text_field = alias_text_field
        self.alias_emb_field = alias_emb_field
        self.label_emb_field = label_emb_field

        self.properties_json_path = properties_json_path
        self.aliases_json_path = aliases_json_path
        self.label_embeddings_json_path = label_embeddings_json_path
        self.preload_aliases_json = preload_aliases_json
        self.label_similarity_weight = label_similarity_weight
        self._properties_index: Dict[str, Dict[str, Any]] = {}
        self._label_embeddings_index: Dict[str, np.ndarray] = {}
        self._aliases_index: Dict[str, List[Dict[str, Any]]] = {}

        if self.backend == "json":
            if self.properties_json_path:
                self._properties_index = self._load_properties_index(self.properties_json_path)
            if self.label_embeddings_json_path:
                self._label_embeddings_index = self._load_label_embeddings_index(self.label_embeddings_json_path)
            if self.preload_aliases_json:
                self._aliases_index = self._load_aliases_index(self.aliases_json_path)

    # --------- public API ---------

    def get(self, pid: str, k: int = 3, mode: Mode = "inverse", include_debug: bool = False) -> Dict[str, Any]:
        """
        Return property label/description + selected aliases.

        Notes:
        - Always includes label (if present)
        - Does NOT automatically include label among aliases; it returns it separately.
        """
        pid = _normalize_text(pid)
        if k <= 0:
            raise ValueError("k must be >= 1")

        prop = self._get_property_doc(pid)
        label = _normalize_text(prop.get(self.label_field) or "") if prop else ""
        desc = _normalize_text(prop.get(self.description_field) or "") if prop else ""

        # fetch alias docs
        alias_docs = list(self._iter_alias_docs(pid))
        selected, dbg = self._select_aliases(
            label=label,
            desc=desc,
            alias_docs=alias_docs,
            k=k,
            mode=mode,
        )

        out: Dict[str, Any] = {
            "pid": pid,
            "label": label,
            "description": desc,
            "aliases": selected,
        }
        if include_debug:
            out["debug"] = dbg
        return out

    # --------- mongo fetch ---------

    @lru_cache(maxsize=100_000)
    def _get_property_doc(self, pid: str) -> Optional[Dict[str, Any]]:
        if self.backend == "mongo":
            if self.properties is None:
                return None
            return self.properties.find_one(
                {self.pid_field: pid},
                {self.label_field: 1, self.description_field: 1, self.pid_field: 1, self.label_emb_field: 1},
            )
        doc = dict(self._properties_index.get(pid) or {})
        if pid in self._label_embeddings_index and self.label_emb_field not in doc:
            doc[self.label_emb_field] = self._label_embeddings_index[pid]
        return doc or None

    def _iter_alias_docs(self, pid: str) -> Iterable[Dict[str, Any]]:
        if self.backend == "mongo":
            if self.aliases is None:
                return
            projection = {
                self.alias_text_field: 1,
                self.alias_emb_field: 1,
                self.alias_pid_field: 1,
            }
            yield from self.aliases.find({self.alias_pid_field: pid}, projection)
            return

        if self.preload_aliases_json:
            yield from self._aliases_index.get(pid, [])
            return

        for d in self._iter_json_array_objects(self.aliases_json_path):
            if d.get(self.alias_pid_field) == pid:
                yield d

    # --------- scoring / selection ---------

    def _select_aliases(
        self,
        label: str,
        desc: str,
        alias_docs: Sequence[Dict[str, Any]],
        k: int,
        mode: Mode,
    ) -> Tuple[List[str], Dict[str, Any]]:
        # Build candidates, dedupe by normalized text
        seen = set()
        candidates: List[AliasCandidate] = []
        for d in alias_docs:
            text_raw = d.get(self.alias_text_field)
            if not isinstance(text_raw, str) or not text_raw.strip():
                continue
            text = _normalize_text(text_raw)
            tkey = text.lower()
            if tkey in seen:
                continue
            seen.add(tkey)

            emb = None
            emb_raw = d.get(self.alias_emb_field)
            if isinstance(emb_raw, list) and emb_raw and all(isinstance(x, (int, float)) for x in emb_raw):
                try:
                    emb = np.asarray(emb_raw, dtype=np.float32)
                except Exception:
                    emb = None

            candidates.append(AliasCandidate(text=text, emb=emb))

        if not candidates:
            return [], {"note": "no aliases found"}

        # Compute centroid centrality if we have >=2 embeddings
        emb_list = [c.emb for c in candidates if c.emb is not None]
        use_emb = len(emb_list) >= 2
        centroid = None
        if use_emb:
            centroid = np.mean(np.stack(emb_list, axis=0), axis=0)

        label_emb = self._get_label_embedding(alias_docs=alias_docs)
        use_label_sim = label_emb is not None

        scored: List[AliasCandidate] = []
        for c in candidates:
            centrality = 0.0
            if use_emb and c.emb is not None and centroid is not None:
                centrality = _cosine(c.emb, centroid)

            label_similarity = 0.0
            if use_label_sim and c.emb is not None and label_emb is not None:
                label_similarity = _cosine(c.emb, label_emb)

            heuristic = self._heuristic_score(label=label, desc=desc, alias=c.text, mode=mode)

            # Combine: embeddings dominate when present, heuristics guide within ties
            # Scale heuristics to be comparable with cosine (~[-1,1]):
            # heuristic is roughly [0, 1.5] -> scale to ~[0, 0.6]
            combined = centrality
            if use_emb:
                combined = centrality + 0.4 * heuristic
            else:
                combined = heuristic
            if use_label_sim:
                combined += self.label_similarity_weight * label_similarity

            scored.append(
                AliasCandidate(
                    text=c.text,
                    emb=c.emb,
                    centrality=centrality,
                    label_similarity=label_similarity,
                    heuristic=heuristic,
                    combined=combined,
                )
            )

        # Sort by combined desc, then by length (prefer informative but not huge)
        scored.sort(key=lambda x: (x.combined, -min(len(x.text), 80)), reverse=True)

        # Post-filter: remove very low-quality aliases in inverse mode
        filtered: List[AliasCandidate] = []
        for c in scored:
            if mode == "inverse":
                if self._is_too_vague(c.text):
                    continue
            filtered.append(c)

        # Ensure diversity: avoid near-duplicates by token overlap
        selected: List[str] = []
        selected_tokens: List[set] = []
        for c in filtered:
            toks = set(_tokenize(c.text)) - _STOPWORDS
            if not toks:
                # keep only if we still need something and it's not empty
                if len(selected) < k:
                    selected.append(c.text)
                continue

            too_similar = False
            for st in selected_tokens:
                # Jaccard similarity threshold
                inter = len(toks & st)
                union = len(toks | st)
                jacc = (inter / union) if union else 0.0
                if jacc >= 0.8:
                    too_similar = True
                    break
            if too_similar:
                continue

            selected.append(c.text)
            selected_tokens.append(toks)
            if len(selected) >= k:
                break

        dbg = {
            "mode": mode,
            "use_embeddings": use_emb,
            "use_label_similarity": use_label_sim,
            "label_similarity_weight": self.label_similarity_weight,
            "alias_count": len(candidates),
            "scored_top10": [
                {
                    "alias": c.text,
                    "combined": round(c.combined, 4),
                    "centrality": round(c.centrality, 4),
                    "label_similarity": round(c.label_similarity, 4),
                    "heuristic": round(c.heuristic, 4),
                }
                for c in filtered[:10]
            ],
        }
        return selected, dbg

    def _heuristic_score(self, label: str, desc: str, alias: str, mode: Mode) -> float:
        """
        Mode-specific heuristic score in ~[0, 1.5]. Higher is better.
        """
        alias_l = alias.lower()
        toks = _tokenize(alias)
        # Base: prefer medium-length informative aliases
        length = len(alias)
        length_score = 0.0
        if 6 <= length <= 60:
            length_score = 0.4
        elif 3 <= length <= 90:
            length_score = 0.2

        # Penalize aliases that are just stopword-y fragments (e.g., "of country")
        content_toks = [t for t in toks if t not in _STOPWORDS]
        if len(content_toks) <= 1:
            length_score -= 0.4

        # Reward overlap with label/description content words
        ref = " ".join([label or "", desc or ""]).strip()
        ref_toks = set(_tokenize(ref)) - _STOPWORDS
        overlap = len((set(content_toks) - _STOPWORDS) & ref_toks)
        overlap_score = min(0.6, 0.15 * overlap)

        # Mode boosts
        mode_score = 0.0
        if mode == "inverse":
            # Prefer role/direction cues: "of", "by", "from", "to", possessives, agent nouns, passive-ish phrasing
            direction_cues = {"by", "of", "from", "to", "for", "between", "among", "within", "during", "against"}
            cue_hits = sum(1 for t in toks if t in direction_cues)
            mode_score += min(0.6, 0.2 * cue_hits)

            # Passive-ish / agentive cues
            if re.search(r"\bby\b", alias_l):
                mode_score += 0.2
            if re.search(r"\b(ed|en)\b", alias_l):  # crude
                mode_score += 0.05
            if re.search(r"\b(creator|author|founder|employer|employee|owner|member|part)\b", alias_l):
                mode_score += 0.2

            # Penalize vague "linked/related/associated"
            if re.search(r"\b(related|linked|associated|connection|reference)\b", alias_l):
                mode_score -= 0.4

        elif mode == "generic":
            # Keep it simple: prefer informative + overlap
            mode_score += 0.0

        elif mode == "entity_type":
            # Prefer "type of", "class of" cues
            if re.search(r"\b(type|class|kind)\b", alias_l):
                mode_score += 0.3

        elif mode == "debug":
            # no special handling
            mode_score += 0.0

        return max(0.0, length_score + overlap_score + mode_score)

    def _is_too_vague(self, alias: str) -> bool:
        """
        Hard filter for inverse mode: remove aliases that are likely unhelpful.
        """
        a = alias.strip().lower()
        if len(a) <= 2:
            return True
        # Very common vague templates
        if a in {"related", "linked", "association", "associated", "connection"}:
            return True
        # Too little content (e.g., "of country")
        toks = [t for t in _tokenize(a) if t not in _STOPWORDS]
        if len(toks) <= 1:
            return True
        return False

    # --------- json backend helpers ---------

    def _load_properties_index(self, path: str) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for d in self._iter_json_array_objects(path):
            pid = d.get(self.pid_field)
            if isinstance(pid, str) and pid:
                out[pid] = d
        return out

    def _load_aliases_index(self, path: str) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for d in self._iter_json_array_objects(path):
            pid = d.get(self.alias_pid_field)
            if isinstance(pid, str) and pid:
                out.setdefault(pid, []).append(d)
        return out

    def _load_label_embeddings_index(self, path: str) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        for d in self._iter_json_array_objects(path):
            pid = d.get(self.pid_field)
            emb_raw = d.get(self.label_emb_field)
            if not isinstance(pid, str) or not pid:
                continue
            if isinstance(emb_raw, list) and emb_raw and all(isinstance(x, (int, float)) for x in emb_raw):
                try:
                    out[pid] = np.asarray(emb_raw, dtype=np.float32)
                except Exception:
                    pass
        return out

    def _get_label_embedding(self, alias_docs: Sequence[Dict[str, Any]]) -> Optional[np.ndarray]:
        if alias_docs:
            first = alias_docs[0]
            pid = first.get(self.alias_pid_field)
            if isinstance(pid, str):
                emb = self._label_embeddings_index.get(pid)
                if emb is not None:
                    return emb

        # Mongo fallback: some properties docs may include label embedding directly.
        # In JSON mode _get_property_doc already merges from separate label-embedding file.
        if alias_docs:
            pid = alias_docs[0].get(self.alias_pid_field)
            if isinstance(pid, str):
                prop = self._get_property_doc(pid)
                if prop:
                    emb_raw = prop.get(self.label_emb_field)
                    if isinstance(emb_raw, np.ndarray):
                        return emb_raw
                    if isinstance(emb_raw, list) and emb_raw and all(isinstance(x, (int, float)) for x in emb_raw):
                        try:
                            return np.asarray(emb_raw, dtype=np.float32)
                        except Exception:
                            return None
        return None

    def _iter_json_array_objects(self, path: str) -> Generator[Dict[str, Any], None, None]:
        """
        Stream objects from a JSON array file without loading the full file into memory.
        """
        decoder = json.JSONDecoder()
        with open(path, "r", encoding="utf-8") as f:
            buf = ""
            in_array = False
            done = False
            while not done:
                chunk = f.read(1024 * 1024)
                if chunk:
                    buf += chunk
                else:
                    done = True
                i = 0
                n = len(buf)
                while i < n:
                    while i < n and buf[i].isspace():
                        i += 1
                    if i >= n:
                        break
                    if not in_array:
                        if buf[i] != "[":
                            raise ValueError(f"Expected '[' at start of JSON array in {path}")
                        in_array = True
                        i += 1
                        continue
                    if buf[i] == ",":
                        i += 1
                        continue
                    if buf[i] == "]":
                        return
                    try:
                        obj, j = decoder.raw_decode(buf, i)
                    except json.JSONDecodeError:
                        break
                    i = j
                    if isinstance(obj, dict):
                        yield obj
                buf = buf[i:]
            if in_array and buf.strip() not in {"", "]"}:
                raise ValueError(f"Malformed JSON array in {path}")


def _build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Select informative aliases for a Wikidata property.")
    p.add_argument("--pid", required=True)
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--mode", choices=["inverse", "generic", "entity_type", "debug"], default="inverse")
    p.add_argument("--include_debug", action="store_true")
    p.add_argument("--backend", choices=["mongo", "json"], default="json")
    p.add_argument("--mongo_uri", default="")
    p.add_argument("--db_name", default="wikidata_ontology")
    p.add_argument("--properties_col", default="properties")
    p.add_argument("--aliases_col", default="property_aliases")
    p.add_argument("--properties_json_path", default="data/raw/wikidata_ontology.properties.json")
    p.add_argument("--aliases_json_path", default="data/raw/wikidata_ontology.property_aliases.json")
    p.add_argument(
        "--label_embeddings_json_path",
        default="",
        help="Optional JSON array file with property_id and label_text_embedding.",
    )
    p.add_argument("--preload_aliases_json", action="store_true")
    p.add_argument(
        "--label_similarity_weight",
        type=float,
        default=0.35,
        help="Weight for cosine(label_embedding, alias_embedding) in final ranking.",
    )
    return p


def main() -> None:
    args = _build_cli().parse_args()
    if args.backend == "mongo":
        if not args.mongo_uri:
            raise ValueError("--mongo_uri is required when --backend mongo")
        from pymongo import MongoClient  # lazy import for json-only environments

        mongo = MongoClient(args.mongo_uri)
        db = mongo.get_database(args.db_name)
        selector = PropertyAliasSelector(
            db=db,
            properties_col=args.properties_col,
            aliases_col=args.aliases_col,
            label_similarity_weight=args.label_similarity_weight,
        )
    else:
        selector = PropertyAliasSelector(
            db=None,
            properties_json_path=args.properties_json_path,
            aliases_json_path=args.aliases_json_path,
            label_embeddings_json_path=args.label_embeddings_json_path,
            preload_aliases_json=args.preload_aliases_json,
            label_similarity_weight=args.label_similarity_weight,
        )

    out = selector.get(pid=args.pid, k=args.k, mode=args.mode, include_debug=args.include_debug)
    print(json.dumps(out, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
