# config_sampler.py
from dataclasses import dataclass
from typing import Optional


@dataclass
class MongoConfig:
    uri: str = "mongodb://localhost:27017"
    db_name: str = "wikidata_ontology"

    # Triples collection (YOU may need to change these defaults to match your schema)
    triples_collection: str = "triplets"

    # Field names in triples docs
    field_head: str = "h"      # subject/entity id (e.g., Qxxx)
    field_tail: str = "t"      # object/entity id (e.g., Qyyy)
    field_rel: str = "r"       # property id (e.g., P1001)

    # If your triples store subject/object under other names, set them here.


@dataclass
class InputFiles:
    antisymmetric_csv: str = "antisymmetric_relations.csv"
    symmetric_csv: str = "symmetric_relations.csv"
    inverse_csv: str = "inverse_directional.csv"
    composition_targets_csv: str = "relations_report.composition_targets.csv"


@dataclass
class SamplingConfig:
    # Balanced constraints
    triples_per_relation_m: int = 50

    # How many inverse pairs to sample (bottleneck). If None -> use ALL available pairs.
    inverse_pairs_k: Optional[int] = None

    # We will sample the same number of RELATIONS per pattern.
    # Since inverse is in pairs (2 relations), we set:
    #   K_relations_per_pattern = 2 * inverse_pairs_k
    # (So inverse contributes exactly that many relations: src+inv for each pair.)
    #
    # If inverse_pairs_k is None, we set it to all pairs and derive K_relations_per_pattern.

    # Connectivity and search robustness
    attempts: int = 50              # GRASP-like restarts
    rcl_size: int = 15              # restricted candidate list size for randomized greedy

    # Overlap estimation (used to prefer connectable relations)
    overlap_probe_triples: int = 200

    # Anchoring: min fraction of M we try to attach early (helps connectivity)
    anchor_fraction: float = 0.2

    # Mongo query controls
    mongo_batch_limit: int = 5000   # safety cap when pulling candidates
    allow_sampling_fallback: bool = True  # allow $sample pipeline if needed


@dataclass
class DomainRangeConfig:
    # Collection where (r1,r2) compatibility is stored
    compat_collection: str = "relation_domain_range_with_all_oher_relations"

    # If (r1,r2) is missing => DISJOINT/IMPOSSIBLE chain
    treat_missing_as_disjoint: bool = True

    # Acceptable compatibility values
    allowed: tuple = ("INTERSECT", "ANY_DOMAIN", "ANY_RANGE", "ANY_BOTH")
