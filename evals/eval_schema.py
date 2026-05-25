"""Schema for RoboGrammar eval dataset entries.

Each eval entry tests one aspect of the grammar agent loop:
- Can it produce valid structural rules from a natural language prompt?
- Can the compiler detect invalid node references?
- Can the evaluator catch physically infeasible designs?
- Does fuzzy matching recover misspelled nodes or hallucinate new ones?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Tag(str, Enum):
    VALID_BASELINE = "valid_baseline"
    HALLUCINATION_MISSPELL = "hallucination_misspell"
    HALLUCINATION_INVENT = "hallucination_invent"
    HALLUCINATION_ORPHAN = "hallucination_orphan"
    RECURSION_NO_BASE = "recursion_no_base"
    RECURSION_SELF_ONLY = "recursion_self_only"
    RECURSION_OVERUSE = "recursion_overuse"
    ABSTRACTION_MISMATCH = "abstraction_mismatch"
    INFEASIBLE_TOPOLOGY = "infeasible_topology"
    INFEASIBLE_LOAD = "infeasible_load"
    FAMILY_CONFUSION = "family_confusion"
    AMBIGUOUS_MORPHOLOGY = "ambiguous_morphology"
    MISSING_NODES = "missing_nodes"
    PARTIAL_RULES = "partial_rules"
    VALID_COMPLEX = "valid_complex"
    CONSTRAINT_VIOLATION = "constraint_violation"


@dataclass(frozen=True)
class EvalEntry:
    id: str
    prompt: str
    expected_rules: dict[str, list[str]]
    tag: Tag
    expected_compile_safe: bool
    expected_behavior: Literal["produce", "reject", "flag_infeasible"]
    difficulty: Literal["easy", "medium", "hard"]
    notes: str
    subtag: str = ""
    expected_invalid_nodes: tuple[str, ...] = field(default_factory=tuple)
    source_family: str = ""
