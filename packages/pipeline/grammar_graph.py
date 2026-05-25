"""Supabase-backed grammar access for research-owned agent loops.

This module is the single agent-facing boundary into the RoboGrammar/RoboMorph
catalog. It exposes tools to fetch vocabulary, fetch one node's description,
fetch structural-rule memory, fuzzy-resolve node names, and vocabulary-compile a
proposed rule dict. No TaskSpec, indoor/outdoor strategies, q-vector generation,
climbing hardrails, or task-conditioned morphology logic lives here.

The compiler validates only that every LHS and RHS short-form node ID in a
proposed ``dict[str, list[str]]`` rule set exists in ``GrammarNodes``. It
returns both the boolean compile result and the concrete invalid node IDs; it
does not simulate physics, score morphology, render geometry, or infer task
strategy.
"""

from __future__ import annotations

import json
import math
import operator
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, NamedTuple, TypedDict, cast

from pydantic import TypeAdapter

from packages.pipeline.db_connections import get_supabase_client
from packages.pipeline.observability import get_langsmith_trace_id, langsmith_observation
from packages.pipeline.schemas import TaskIntent, RobotDesignCandidate

_TASK_INTENT_ADAPTER: TypeAdapter[TaskIntent] = TypeAdapter(TaskIntent)

try:
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:  # pragma: no cover - optional agent runtime dependency
    @dataclass(frozen=True)
    class HumanMessage:
        content: str

    @dataclass(frozen=True)
    class SystemMessage:
        content: str

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - optional local test/runtime dependency
    END = START = None
    StateGraph = None

DEFAULT_RULE_BUILDER_EXAMPLE_FAMILIES = (
    "humanoid",
    "quadruped",
    "biped",
    "snake",
    "bird",
    "lizard",
    "centipede",
)

DEFAULT_ROBOT_POPULATION = 6
FUZZY_NODE_MATCH_K = 6.0
FUZZY_NODE_MATCH_MIN_RATIO = 0.18
FUZZY_NODE_MATCH_MAX_RATIO = 0.50

QUERY_NORMALIZER_SYSTEM_PROMPT = """You are query_normalizer_agent.

Convert the user's raw robot-design request into TaskIntent JSON.

Output contract:
- Return only JSON.
- task_goal is the concise design objective, preserving important nouns and verbs.
- All other fields are optional lists of short strings. Omit fields that are not
  relevant to the user's request rather than returning empty lists.
- terrain: surface types the robot must traverse (rocky, sandy, stairs, etc.).
- obstacles: specific obstacles it must navigate or overcome.
- contact_requirements: physical contact or locomotion capabilities needed.
- payload_requirements: things the robot must carry, push, or pull.
- manipulation_requirements: grasping, pushing, or assembly tasks.
- spatial_constraints: size, clearance, or footprint limits.
- stability_requirements: balance, vibration, or posture constraints.
- sensing_requirements: sensors the morphology must accommodate.
- hard_constraints: absolute limits set by the user.
- failure_modes_to_avoid: specific failure modes the design must not exhibit.
- success_criteria: measurable conditions that define a successful design.
- environment: one-line description of the operating environment when relevant.

Do not output TaskSpec fields. Do not infer indoor/outdoor strategy, terrain
hardrails, q-vectors, scores, render fields, or component dimensions.
"""
RULE_BUILDER_AGENT_SYSTEM_PROMPT = """You are rule_builder_agent.

Your job is to produce RoboGrammar structural rules for a robot morphology.
Use paper-style graph grammar rewriting: start from abstract scaffolding, recurse to add depth, then terminalize modules cleanly.
Prefer reusable deep patterns over ad-hoc one-step expansions.

Output contract:
- Return only JSON.
- Return a single object shaped as {"structural_rules": dict[str, list[str]]}.
- Each key is a left-hand-side short-form grammar node ID.
- Each value is an ordered list of generated short-form grammar node IDs.
- Do not output production strings, markdown, comments, prose, Python, or YAML.

Hard compiler constraints:
- Use only node IDs from the provided GrammarNodes vocabulary.
- Every LHS node and every RHS node must exist in that vocabulary.
- Reuse short_form_name exactly; do not invent synonyms from long_name.
- If a useful concept is missing from the vocabulary, choose the closest valid
  node instead of inventing a new one.
- Structural rules describe topology only. Do not include lengths, mass,
  friction, control policies, rendering parameters, scores, or physics claims.

Design guidance:
- Prefer multi-level recursive rules for repeatable structures such as body chains,
  centipedes, tails, limbs, and segmented bodies.
- Use one recursive production and one terminal production per motif whenever
  possible (for example, a rule that keeps expanding and a rule that ends it).
- Prefer pair/group nodes for symmetry when the vocabulary provides them, such
  as LEG_PAIR, ARM_PAIR, WING_PAIR, or SPRAWLED_LEG_PAIR.
- Keep terminal component detail in terminal nodes; do not mix component
  attributes into structural rules.
- A good output should compile with compile_structural_rules(structural_rules).

The injected examples below are style references, not hard templates. You should
match their graph grammar style and recursive depth while staying within the
current Vocabulary.
"""

EVALUATOR_AGENT_SYSTEM_PROMPT = """You are evaluator_agent.

Evaluate whether the proposed RoboGrammar structural rules satisfy the current
TaskIntent and the grammar-only compiler contract.

Output contract:
- Return only JSON shaped as {"criteria": list[Criteria]}.
- Each Criteria item must include description, isSuccessful, and critiques.
- When asked for the initial checklist, author specific proxy goals for the
  current TaskIntent. These criteria are instructions for the
  rule_builder_agent to satisfy in structural topology.
- Mark isSuccessful true only when the rule set actually satisfies that criterion.
- When false, write concise critiques the rule builder can use on the next pass.

Evaluation constraints:
- Do not include a criterion for query normalization; normalization is already
  the first graph node.
- Judge structural topology only.
- Do not score physics, rendering, terrain strategy, q-vectors, or controller policy.
- Treat compile safety as mandatory: every LHS and RHS node must exist in
  GrammarNodes.
- Treat hallucination as any invented, misspelled, task-word, or synonym node
  that is not an exact GrammarNodes short_form_name. Do not pass a criterion
  just because the rule text sounds semantically related.
- If compile_structural_rules reports invalid_grammar_nodes, mark the
  vocabulary criterion false and name the invalid nodes in critiques.
- For task alignment, inspect the top-level S expansion first, then supporting
  expansions. The selected body scaffold and appendage groups must match the
  TaskIntent family, contact requirements, manipulation requirements, payload,
  sensing, terrain, and hard constraints.
- Extra valid expansions are acceptable only when they support the task; missing
  required top-level morphology, dangling nonterminals, unbounded recursion, or
  cross-family chimeras should fail the relevant proxy criterion.
"""

EVALUATOR_AGENT_CRITIQUE_PROMPT = """Create the initial TODO checklist for this RoboGrammar generation state.

The checklist must guide the rule_builder_agent before any structural rules are
generated.

Return criteria that cover:
- non-empty structural rules
- compiler validity against GrammarNodes vocabulary
- recursive or grouped graph-grammar structure when the vocabulary supports it
- 3 to 6 specific proxy goals derived from task_goal, contact_requirements,
  hard_constraints, terrain, and other relevant TaskIntent fields

Proxy goals must be concrete structural targets, for example:
- "Rules include a climbing proxy: repeated contact-capable appendage groups or
  segmented body support for rocky terrain."
- "Rules include a payload proxy: a central body scaffold with symmetric support
  modules."

Do not include a criterion for TaskIntent creation or prompt normalization.
"""


def fetch_grammar_from_db(
    *,
    limit: int | None = None,
    active_only: bool | None = None,
    morphology_family: str | None = None,
    node_type: str | None = None,
) -> list[tuple[str, str]]:
    """Fetch valid grammar nodes as ``(short_form_name, long_name)`` tuples.

    Agent contract: use ``short_form_name`` as the unique node ID in generated
    graphs and structural rules. ``long_name`` is included so the agent can
    understand the node without paying for a separate description lookup.
    """
    with langsmith_observation(
        "fetch_grammar_from_db",
        as_type="tool",
        input={
            "limit": limit,
            "active_only": active_only,
            "morphology_family": morphology_family,
            "node_type": node_type,
        },
    ) as observation:
        table = os.environ.get("GRAMMAR_NODES_TABLE", "GrammarNodes")
        active = _active_only(active_only)
        if morphology_family:
            allowed_nodes = _short_form_names_for_family(
                morphology_family=morphology_family,
                node_type=node_type,
                active_only=active,
            )
            if not allowed_nodes:
                observation.update(output={"row_count": 0, "rows": []})
                return []
            rows = _fetch_rows(
                table,
                columns="short_form_name,long_name",
                limit=None,
                active_only=active,
                filters={},
            )
            identities = [
                identity
                for identity in _node_identities(rows)
                if identity[0] in allowed_nodes
            ]
            row_limit = limit or _env_int("GRAMMAR_NODES_LIMIT")
            result = identities[:row_limit] if row_limit is not None else identities
            observation.update(output={"row_count": len(result), "rows": result[:25]})
            return result

        rows = _fetch_rows(
            table,
            columns="short_form_name,long_name",
            limit=limit or _env_int("GRAMMAR_NODES_LIMIT"),
            active_only=active,
            filters={"node_type": node_type},
        )
        result = _node_identities(rows)
        observation.update(output={"row_count": len(result), "rows": result[:25]})
        return result


def fetch_desc_by_node(
    short_form_name: str,
    *,
    active_only: bool | None = None,
) -> str | None:
    """Fetch the description for one grammar node short-form ID.

    Call this only when the ``(short_form_name, long_name)`` tuple from
    ``fetch_grammar_from_db`` is not enough context. Returns ``None`` for blank
    or unknown node IDs.
    """
    node_id = _string_or_none(short_form_name)
    if node_id is None:
        return None

    rows = _fetch_rows(
        os.environ.get("GRAMMAR_NODES_TABLE", "GrammarNodes"),
        columns="description",
        limit=1,
        active_only=_active_only(active_only),
        filters={"short_form_name": node_id},
    )
    for row in rows:
        description = _string_or_none(row.get("description"))
        if description is not None:
            return description
    return None


def fetch_rules_from_db(
    *,
    limit: int | None = None,
    active_only: bool | None = None,
    rule_id: str | None = None,
    morphology_family: str | None = None,
    category: str | None = None,
) -> dict[str, str]:
    """Fetch structural grammar rules as ``{rule: description}``.

    The database stores structural-rule memory as production-string keys plus
    short descriptions. Agents can retrieve by morphology family/category and
    then emit a compiled ``dict[str, list[str]]`` using known node IDs.
    """
    with langsmith_observation(
        "fetch_rules_from_db",
        as_type="tool",
        input={
            "limit": limit,
            "active_only": active_only,
            "rule_id": rule_id,
            "morphology_family": morphology_family,
            "category": category,
        },
    ) as observation:
        rows = _fetch_rows(
            os.environ.get("STRUCTURAL_RULES_TABLE", "StructuralRules"),
            columns="rule,description",
            limit=limit or _env_int("STRUCTURAL_RULES_LIMIT"),
            active_only=_active_only(active_only),
            filters={
                "id": rule_id,
                "morphology_family": morphology_family,
                "category": category,
            },
        )
        result = _rule_descriptions(rows)
        observation.update(
            output={
                "rule_count": len(result),
                "rules": list(result)[:25],
            }
        )
        return result


def build_query_normalizer_prompt(raw_prompt: str) -> str:
    """Build a system+user prompt for producing ``TaskIntent`` JSON."""
    prompt = _string_or_none(raw_prompt)
    if prompt is None:
        raise ValueError("raw_prompt must not be blank")
    return "\n\n".join(
        [
            QUERY_NORMALIZER_SYSTEM_PROMPT.strip(),
            "TaskIntent schema:",
            json.dumps(_TASK_INTENT_ADAPTER.json_schema(), indent=2),
            "Raw user request:",
            prompt,
        ]
    )

def build_evaluator_system_prompt(
    state: "RoboGraphState",
) -> tuple[SystemMessage, HumanMessage]:
    """Build evaluator messages for creating the initial TODO checklist."""
    return (
        SystemMessage(content=EVALUATOR_AGENT_SYSTEM_PROMPT.strip()),
        HumanMessage(
            content="\n\n".join(
                [
                    EVALUATOR_AGENT_CRITIQUE_PROMPT.strip(),
                    "Current state:",
                    _state_summary_for_prompt(state),
                ]
            )
        ),
    )


def build_checklist_prompt(
    state: "RoboGraphState",
) -> tuple[SystemMessage, HumanMessage]:
    """Build evaluator messages for marking TODO criteria after rule generation."""
    return (
        SystemMessage(content=EVALUATOR_AGENT_SYSTEM_PROMPT.strip()),
        HumanMessage(
            content="\n\n".join(
                [
                    "Mark each TODO criterion as successful or unsuccessful.",
                    "Append concise critiques to unsuccessful criteria.",
                    "Current state:",
                    _state_summary_for_prompt(state),
                ]
            )
        ),
    )

def build_rule_builder_system_prompt(
    query: TaskIntent,
    example_families: Sequence[str] = DEFAULT_RULE_BUILDER_EXAMPLE_FAMILIES,
    examples_per_family: int = 2,
    grammar_node_limit: int | None = 160,
    active_only: bool | None = None,
) -> str:
    """Build the rule-builder system prompt with live DB vocabulary/examples.

    The prompt injects current ``GrammarNodes`` as ``short_form_name | long_name``
    and few-shot structural-rule examples sampled from ``StructuralRules``.
    Examples are filtered so every token in each sampled rule exists in the
    current grammar vocabulary.
    """
    node_rows = fetch_grammar_from_db(
        limit=grammar_node_limit,
        active_only=active_only,
    )
    known_nodes = {short_name for short_name, _long_name in node_rows}
    examples = sample_rule_builder_examples(
        example_families=example_families,
        examples_per_family=examples_per_family,
        active_only=active_only,
        known_nodes=known_nodes,
    )

    sections = [
        RULE_BUILDER_AGENT_SYSTEM_PROMPT.strip(),
        _format_query_context(
            query=query,
        ),
        _format_grammar_vocabulary(node_rows),
        _format_rule_examples(examples),
    ]
    return "\n\n".join(section for section in sections if section)


def sample_rule_builder_examples(
    *,
    example_families: Sequence[str] = DEFAULT_RULE_BUILDER_EXAMPLE_FAMILIES,
    examples_per_family: int = 2,
    active_only: bool | None = None,
    known_nodes: set[str] | None = None,
) -> dict[str, dict[str, str]]:
    """Sample compile-valid structural-rule examples from Supabase by family."""
    if examples_per_family < 1:
        return {}

    vocabulary = known_nodes or {
        short_name
        for short_name, _long_name in fetch_grammar_from_db(active_only=active_only)
    }
    examples: dict[str, dict[str, str]] = {}
    for family in example_families:
        family_name = _string_or_none(family)
        if family_name is None:
            continue

        sampled: dict[str, str] = {}
        for rule, description in fetch_rules_from_db(
            morphology_family=family_name,
            limit=max(examples_per_family * 6, examples_per_family),
            active_only=active_only,
        ).items():
            parsed = _parse_production_rule(rule)
            if parsed is None:
                continue
            lhs, rhs = parsed
            if lhs not in vocabulary or any(node not in vocabulary for node in rhs):
                continue
            sampled[rule] = description
            if len(sampled) >= examples_per_family:
                break

        if sampled:
            examples[family_name] = sampled
    return examples


def resolve_grammar_node_name(
    node_name: str,
    *,
    active_only: bool | None = None,
    known_nodes: set[str] | None = None,
    known_node_aliases: dict[str, str] | None = None,
) -> str:
    """Resolve an LLM-generated node name to a canonical GrammarNodes ID.

    Returns the exact ``short_form_name`` for exact, normalized, or strong fuzzy
    matches. Returns an empty string when the best match is too distant or
    ambiguous.
    """
    requested = _normalize_grammar_node_key(node_name)
    if not requested:
        return ""

    if known_nodes is None or known_node_aliases is None:
        node_rows = fetch_grammar_from_db(active_only=active_only)
        vocabulary = known_nodes or {short_name for short_name, _long_name in node_rows}
        aliases = known_node_aliases or _grammar_node_aliases(node_rows)
    else:
        vocabulary = known_nodes
        aliases = known_node_aliases
    if not vocabulary:
        return ""

    exact_match = aliases.get(requested)
    if exact_match:
        return exact_match

    best_candidate = ""
    best_ratio: float | None = None
    second_ratio: float | None = None
    for normalized, candidate in aliases.items():
        if not normalized:
            continue
        distance = _levenshtein_distance(requested, normalized)
        string_size = max(len(requested), len(normalized), 1)
        ratio = distance / string_size
        threshold = _dynamic_edit_distance_ratio_threshold(string_size)
        if ratio > threshold:
            continue
        if best_ratio is None or ratio < best_ratio:
            second_ratio = best_ratio
            best_ratio = ratio
            best_candidate = candidate
        elif second_ratio is None or ratio < second_ratio:
            second_ratio = ratio

    if best_ratio is None:
        return ""
    if second_ratio is not None and second_ratio - best_ratio < 0.05:
        return ""
    return best_candidate


def repair_structural_rule_node_names(
    structural_rules: dict[str, list[str]],
    *,
    active_only: bool | None = None,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Repair close GrammarNodes typos inside generated structural rules."""
    try:
        node_rows = fetch_grammar_from_db(active_only=active_only)
    except Exception as exc:
        error = _exception_payload(exc)
        return {
            lhs: list(rhs)
            for lhs, rhs in structural_rules.items()
        }, {
            "status": "skipped",
            "reason": (
                "GrammarNodes vocabulary was unavailable, so fuzzy node-name "
                "resolution was skipped and structural rules were left unchanged."
            ),
            "corrections": [],
            "unresolved": _structural_rule_node_ids(structural_rules),
            **error,
        }
    known_nodes = {short_name for short_name, _long_name in node_rows}
    aliases = _grammar_node_aliases(node_rows)
    corrections: list[dict[str, str]] = []
    unresolved: list[str] = []
    repaired: dict[str, list[str]] = {}

    for source, generated_nodes in structural_rules.items():
        fixed_source = resolve_grammar_node_name(
            source,
            known_nodes=known_nodes,
            known_node_aliases=aliases,
        )
        if not fixed_source:
            fixed_source = source
            unresolved.append(source)
        elif fixed_source != source:
            corrections.append({"input": source, "resolved": fixed_source})

        fixed_generated_nodes: list[str] = []
        for node in generated_nodes:
            fixed_node = resolve_grammar_node_name(
                node,
                known_nodes=known_nodes,
                known_node_aliases=aliases,
            )
            if not fixed_node:
                fixed_generated_nodes.append(node)
                unresolved.append(node)
                continue
            if fixed_node != node:
                corrections.append({"input": node, "resolved": fixed_node})
            fixed_generated_nodes.append(fixed_node)

        repaired.setdefault(fixed_source, []).extend(fixed_generated_nodes)

    return repaired, {
        "corrections": corrections,
        "unresolved": sorted(set(unresolved)),
    }


def _repair_structural_rule_node_names_safely(
    structural_rules: dict[str, list[str]],
    *,
    active_only: bool | None = None,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    try:
        repaired_rules, node_resolution = repair_structural_rule_node_names(
            structural_rules,
            active_only=active_only,
        )
        return repaired_rules, {
            "status": "resolved",
            **node_resolution,
        }
    except Exception as exc:
        error = _exception_payload(exc)
        reason = (
            "GrammarNodes vocabulary was unavailable, so fuzzy node-name "
            "resolution was skipped and structural rules were left unchanged."
        )
        return {
            lhs: list(rhs)
            for lhs, rhs in structural_rules.items()
        }, {
            "status": "skipped",
            "reason": reason,
            "corrections": [],
            "unresolved": _structural_rule_node_ids(structural_rules),
            **error,
        }


def _structural_rule_node_ids(structural_rules: dict[str, list[str]]) -> list[str]:
    node_ids: set[str] = set()
    for lhs, rhs in structural_rules.items():
        node_ids.add(lhs)
        node_ids.update(rhs)
    return sorted(node_ids)


def _exception_payload(exc: BaseException) -> dict[str, str]:
    return {
        "error_type": exc.__class__.__name__,
        "error_message": str(exc) or repr(exc),
    }


def _status_message(prefix: str, error: dict[str, str]) -> str:
    return f"{prefix}: {error['error_type']}: {error['error_message']}"


def compile_structural_rules(structural_rules: dict[str, list[str]]) -> CompileResult:
    """Return whether structural rules reference known and reachable nodes.

    Expected input shape is ``{lhs_short_form_name: [rhs_short_form_name, ...]}``.
    Invalid nodes are concrete LHS/RHS strings that are not present in
    ``GrammarNodes``. Unreachable nodes are valid generated nodes that cannot be
    reached by walking productions from ``S``.
    """
    with langsmith_observation(
        "compile_structural_rules",
        as_type="tool",
        input={"structural_rules": structural_rules},
    ) as observation:
        if not isinstance(structural_rules, dict):
            result = CompileResult(
                False,
                CompilerError(
                    error={
                        "error_type": "InvalidStructuralRules",
                        "error_message": "Structural rules must be a dict[str, list[str]].",
                    }
                ),
                CompilerError(),
            )
            observation.update(output=_compile_result_output(result))
            return result

        known_nodes = {short_name for short_name, _long_name in fetch_grammar_from_db()}
        if not known_nodes:
            result = CompileResult(
                False,
                CompilerError(
                    error={
                        "error_type": "GrammarVocabularyUnavailable",
                        "error_message": "GrammarNodes vocabulary is empty.",
                    }
                ),
                CompilerError(),
            )
            observation.update(output=_compile_result_output(result))
            return result

        invalid_nodes: list[str] = []
        for source, generated_nodes in structural_rules.items():
            source_id = _string_or_none(source)
            if source_id is None or source_id not in known_nodes:
                invalid_nodes.append(str(source))
            if not isinstance(generated_nodes, list):
                continue
            for node in generated_nodes:
                node_id = _string_or_none(node)
                if node_id is None or node_id not in known_nodes:
                    invalid_nodes.append(str(node))
        deduped_invalid_nodes = list(dict.fromkeys(invalid_nodes))
        reachable_nodes = _reachable_node_ids(structural_rules)
        unreachable_nodes = [
            node
            for node in _structural_rule_node_ids(structural_rules)
            if node not in deduped_invalid_nodes and not _is_reachable(node, reachable_nodes)
        ]
        invalid_error = _compiler_error(
            "InvalidGrammarNodes",
            "Invalid nodes",
            deduped_invalid_nodes,
        )
        unreachable_error = _compiler_error(
            "UnreachableGrammarNodes",
            "Unreachable nodes from S",
            unreachable_nodes,
        )
        result = CompileResult(
            not invalid_error.nodes and not unreachable_error.nodes,
            invalid_error,
            unreachable_error,
        )
        observation.update(output=_compile_result_output(result))
        return result


def _compile_result_output(result: CompileResult) -> dict[str, Any]:
    return {
        "compile_safe": result.compile_safe,
        "invalid_nodes": list(result.invalid_nodes.nodes),
        "invalid_nodes_error": result.invalid_nodes.error,
        "unreachable_nodes": list(result.unreachable_nodes.nodes),
        "unreachable_nodes_error": result.unreachable_nodes.error,
        "compile_error": result.compile_error,
    }


def _compile_result_prompt_payload(result: CompileResult) -> dict[str, Any]:
    return {
        "compile_safe": result.compile_safe,
        "invalid_grammar_nodes": list(result.invalid_nodes.nodes),
        "unreachable_grammar_nodes": list(result.unreachable_nodes.nodes),
        "compile_error": result.compile_error,
    }


def _compile_result_from_state(state: RoboGraphState) -> CompileResult:
    result = state.get("compile_result")
    if isinstance(result, CompileResult):
        return result
    return CompileResult(
        bool(state.get("compile_safe", False)),
        CompilerError(
            nodes=tuple(str(node) for node in _as_list(state.get("invalid_grammar_nodes")))
        ),
        CompilerError(
            nodes=tuple(
                str(node) for node in _as_list(state.get("unreachable_grammar_nodes"))
            )
        ),
        state.get("compile_error"),
    )


def _compiler_error(
    error_type: str,
    message_prefix: str,
    nodes: Sequence[str],
) -> CompilerError:
    deduped_nodes = tuple(dict.fromkeys(str(node) for node in nodes))
    if not deduped_nodes:
        return CompilerError()
    return CompilerError(
        nodes=deduped_nodes,
        error={
            "error_type": error_type,
            "error_message": f"{message_prefix}: {', '.join(deduped_nodes)}",
        },
    )


def _reachable_node_ids(structural_rules: dict[str, list[str]]) -> set[str]:
    if "S" not in structural_rules:
        return set()
    reachable: set[str] = set()
    stack = ["S"]
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        generated_nodes = structural_rules.get(node)
        if not isinstance(generated_nodes, list):
            continue
        for child in generated_nodes:
            child_id = _string_or_none(child)
            if child_id is None:
                continue
            if child_id not in reachable:
                stack.append(child_id)
    return reachable


def _is_reachable(node_id: str, reachable_nodes: set[str]) -> bool:
    return node_id in reachable_nodes


def _short_form_names_for_family(
    *,
    morphology_family: str,
    node_type: str | None,
    active_only: bool,
) -> set[str]:
    grammar_ids = _grammar_ids_for_family(
        morphology_family=morphology_family,
        active_only=active_only,
    )
    if not grammar_ids:
        return set()

    rows = _fetch_rows(
        os.environ.get("GRAMMAR_NODE_MEMBERSHIPS_TABLE", "GrammarNodeMemberships"),
        columns="grammar_id,short_form_name,node_type",
        limit=None,
        active_only=active_only,
        filters={"node_type": node_type},
    )
    return {
        short_name
        for row in rows
        if row.get("grammar_id") in grammar_ids
        if (short_name := _string_or_none(row.get("short_form_name"))) is not None
    }


def _grammar_ids_for_family(*, morphology_family: str, active_only: bool) -> set[str]:
    rows = _fetch_rows(
        os.environ.get("GRAMMAR_TABLE", "Grammars"),
        columns="id",
        limit=None,
        active_only=active_only,
        filters={"morphology_family": morphology_family},
    )
    return {
        grammar_id
        for row in rows
        if (grammar_id := _string_or_none(row.get("id"))) is not None
    }


def _fetch_rows(
    table: str,
    *,
    columns: str,
    limit: int | None,
    active_only: bool,
    filters: dict[str, str | None],
) -> list[dict[str, Any]]:
    query = get_supabase_client().table(table).select(columns)
    if active_only:
        query = query.eq("active", True)
    for column, value in filters.items():
        if value:
            query = query.eq(column, value)
    if limit is not None:
        query = query.limit(limit)

    response = query.execute()
    data = getattr(response, "data", None)
    if data is None:
        raise RuntimeError(f"Supabase query for {table} returned no data field.")
    return [dict(row) for row in data]


def _node_identities(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    nodes: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        short_name = _string_or_none(row.get("short_form_name"))
        long_name = _string_or_none(row.get("long_name"))
        if short_name is None or long_name is None or short_name in seen:
            continue
        nodes.append((short_name, long_name))
        seen.add(short_name)
    return nodes


def _rule_descriptions(rows: list[dict[str, Any]]) -> dict[str, str]:
    rules: dict[str, str] = {}
    for row in rows:
        rule = _string_or_none(row.get("rule"))
        description = _string_or_none(row.get("description"))
        if rule is not None and description is not None:
            rules[rule] = description
    return rules


def _parse_production_rule(rule: str) -> tuple[str, list[str]] | None:
    if "->" not in rule:
        return None
    lhs_raw, rhs_raw = rule.split("->", 1)
    lhs = _string_or_none(lhs_raw)
    rhs = [token for token in rhs_raw.split() if _string_or_none(token) is not None]
    if lhs is None:
        return None
    return lhs, rhs


def _format_query_context(
    *,
    query: TaskIntent,
) -> str:
    lines = ["Robot query context:"]
    lines.append(f"- task_goal: {query.task_goal.strip()}")
    if query.environment:
        lines.append(f"- environment: {query.environment.strip()}")

    _list_fields: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("terrain", query.terrain),
        ("obstacles", query.obstacles),
        ("contact_requirements", query.contact_requirements),
        ("payload_requirements", query.payload_requirements),
        ("manipulation_requirements", query.manipulation_requirements),
        ("spatial_constraints", query.spatial_constraints),
        ("stability_requirements", query.stability_requirements),
        ("sensing_requirements", query.sensing_requirements),
        ("hard_constraints", query.hard_constraints),
        ("failure_modes_to_avoid", query.failure_modes_to_avoid),
        ("success_criteria", query.success_criteria),
    )
    for field_name, values in _list_fields:
        items = [v for item in values if (v := _string_or_none(item)) is not None]
        if items:
            lines.append(f"- {field_name}: " + ", ".join(items))
    return "\n".join(lines) if len(lines) > 1 else ""


def _format_grammar_vocabulary(node_rows: list[tuple[str, str]]) -> str:
    if not node_rows:
        return "GrammarNodes vocabulary:\n- none fetched"
    lines = ["GrammarNodes vocabulary: short_form_name | long_name"]
    lines.extend(f"- {short_name} | {long_name}" for short_name, long_name in node_rows)
    return "\n".join(lines)


def _format_rule_examples(examples: dict[str, dict[str, str]]) -> str:
    if not examples:
        return "Compile-valid few-shot structural-rule examples sampled from Supabase:\n- none fetched"

    lines = [
        "Compile-valid few-shot structural-rule examples sampled from Supabase:",
        "Use these as patterns, not as mandatory rules.",
    ]
    for family, rules in examples.items():
        lines.append(f"\n[{family}]")
        for rule, description in rules.items():
            parsed = _parse_production_rule(rule)
            if parsed is None:
                continue
            lhs, rhs = parsed
            lines.append(f"- production: {rule}")
            lines.append(f"  description: {description}")
            lines.append(f"  normalized: {json.dumps({lhs: rhs})}")
    return "\n".join(lines)


def _active_only(value: bool | None) -> bool:
    if value is not None:
        return value
    return os.environ.get("GRAMMAR_ACTIVE_ONLY", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    value = int(raw)
    if value < 1:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_grammar_node_key(value: Any) -> str:
    text = _string_or_none(value)
    if text is None:
        return ""
    chars: list[str] = []
    previous_separator = False
    for char in text.upper():
        if char.isalnum():
            chars.append(char)
            previous_separator = False
        elif chars and not previous_separator:
            chars.append("_")
            previous_separator = True
    return "".join(chars).strip("_")


def _grammar_node_aliases(node_rows: list[tuple[str, str]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for short_name, long_name in node_rows:
        canonical = _string_or_none(short_name)
        if canonical is None:
            continue
        for alias in (short_name, long_name):
            normalized = _normalize_grammar_node_key(alias)
            if normalized and normalized not in aliases:
                aliases[normalized] = canonical
    return aliases


def _dynamic_edit_distance_ratio_threshold(string_size: int) -> float:
    x = max(1, string_size)
    raw_threshold = 0.4 * (1 - math.log(x / FUZZY_NODE_MATCH_K))
    return min(
        FUZZY_NODE_MATCH_MAX_RATIO,
        max(FUZZY_NODE_MATCH_MIN_RATIO, raw_threshold),
    )


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    if len(left) < len(right):
        left, right = right, left

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


tools = [
    fetch_grammar_from_db,
    fetch_desc_by_node,
    fetch_rules_from_db,
    resolve_grammar_node_name,
    compile_structural_rules,
]


__all__ = [
    "DEFAULT_RULE_BUILDER_EXAMPLE_FAMILIES",
    "DEFAULT_ROBOT_POPULATION",
    "QUERY_NORMALIZER_SYSTEM_PROMPT",
    "RULE_BUILDER_AGENT_SYSTEM_PROMPT",
    "EVALUATOR_AGENT_SYSTEM_PROMPT",
    "Criteria",
    "TODO",
    "StructuralRules",
    "CompileResult",
    "RoboGraphState",
    "build_checklist_prompt",
    "build_evaluator_system_prompt",
    "build_query_normalizer_prompt",
    "build_rule_builder_system_prompt",
    "build_structural_rules",
    "compile_structural_rules",
    "fetch_desc_by_node",
    "fetch_grammar_from_db",
    "fetch_rules_from_db",
    "repair_structural_rule_node_names",
    "resolve_grammar_node_name",
    "sample_rule_builder_examples",
    "summarize_hitl_state",
    "tools",
]

class Criteria(TypedDict):
    description: str
    isSuccessful: bool
    critiques: list[str]


class TODO(TypedDict):
    criteria: list[Criteria]


class StructuralRules(TypedDict):
    structural_rules: dict[str, list[str]]


class CompilerError(NamedTuple):
    nodes: tuple[str, ...] = ()
    error: dict[str, str] | None = None


class CompileResult(NamedTuple):
    compile_safe: bool
    invalid_nodes: CompilerError = CompilerError()
    unreachable_nodes: CompilerError = CompilerError()
    compile_error: dict[str, str] | None = None

    def __bool__(self) -> bool:
        return self.compile_safe


class CompileAttempt(NamedTuple):
    result: CompileResult

    def __str__(self) -> str:
        result = self.result
        parts = [
            f"compile_safe={result.compile_safe}",
            "invalid_grammar_nodes=["
            + ", ".join(result.invalid_nodes.nodes)
            + "]",
            "unreachable_grammar_nodes=["
            + ", ".join(result.unreachable_nodes.nodes)
            + "]",
        ]
        if result.compile_error is not None:
            parts.append(
                "compile_error="
                f"{result.compile_error.get('error_type')}: "
                f"{result.compile_error.get('error_message')}"
            )
        elif result.invalid_nodes.error is not None:
            parts.append(
                "invalid_nodes_error="
                f"{result.invalid_nodes.error.get('error_type')}: "
                f"{result.invalid_nodes.error.get('error_message')}"
            )
        elif result.unreachable_nodes.error is not None:
            parts.append(
                "unreachable_nodes_error="
                f"{result.unreachable_nodes.error.get('error_type')}: "
                f"{result.unreachable_nodes.error.get('error_message')}"
            )
        return "; ".join(parts)


class RoboGraphState(TypedDict, total=False):
    prompt: str
    population: int
    attempts: int
    max_attempts: int
    langsmith_trace_id: str | None
    spec: TaskIntent | None
    structural_rules: StructuralRules | None
    node_resolution: dict[str, Any]
    compile_result: CompileResult
    candidates: list[RobotDesignCandidate]
    messages: Annotated[list, operator.add]
    checklist: TODO | None
    awaiting_human: bool
    hitl: dict[str, Any]


def build_structural_rules(
    prompt: str,
    initial_state: RoboGraphState | None = None,
    *,
    confirmed_spec: TaskIntent | dict[str, Any] | None = None,
    normalizer_agent: Any | None = None,
    rule_builder_agent: Any | None = None,
    evaluator_agent: Any | None = None,
    population: int | None = None,
    max_attempts: int = 2,
    require_human_confirmation: bool = False,
) -> RoboGraphState:
    """Compatibility shim for the research-owned grammar agent loop."""

    from packages.research.agent_loops import grammar_loop as _research_grammar_loop

    _research_grammar_loop.langsmith_observation = langsmith_observation
    _research_grammar_loop.get_langsmith_trace_id = get_langsmith_trace_id

    return _research_grammar_loop.build_structural_rules(
        prompt=prompt,
        initial_state=initial_state,
        confirmed_spec=confirmed_spec,
        normalizer_agent=normalizer_agent,
        rule_builder_agent=rule_builder_agent,
        evaluator_agent=evaluator_agent,
        population=population,
        max_attempts=max_attempts,
        require_human_confirmation=require_human_confirmation,
    )

def summarize_hitl_state(state: RoboGraphState) -> dict[str, Any]:
    """Return the UI-facing grammar HITL payload for robot generation."""
    spec = state.get("spec")
    structural_rules = state.get("structural_rules") or {"structural_rules": {}}
    compile_result = _compile_result_from_state(state)
    compile_payload = _compile_result_prompt_payload(compile_result)
    return {
        "spec": _TASK_INTENT_ADAPTER.dump_python(spec) if isinstance(spec, TaskIntent) else spec,
        "inferred_morphology": _infer_morphology_family(spec) if isinstance(spec, TaskIntent) else None,
        "checklist": state.get("checklist") or {"criteria": []},
        "structural_rules": structural_rules.get("structural_rules", {}),
        "node_resolution": state.get("node_resolution") or {"corrections": [], "unresolved": []},
        "compile_result": compile_payload,
        "invalid_grammar_nodes": compile_payload["invalid_grammar_nodes"],
        "unreachable_grammar_nodes": compile_payload["unreachable_grammar_nodes"],
        "population": _normalize_population(state.get("population")),
        "compile_safe": compile_payload["compile_safe"],
        "compile_error": compile_payload["compile_error"],
        "awaiting_human": bool(state.get("awaiting_human")),
        "langsmith_trace_id": state.get("langsmith_trace_id"),
        "messages": [str(message) for message in _as_list(state.get("messages"))],
    }


def _normalize_prompt(prompt: str, normalizer_agent: Any | None) -> TaskIntent:
    if normalizer_agent is not None:
        try:
            response = normalizer_agent.invoke(build_query_normalizer_prompt(prompt))
            coerced = _coerce_task_intent(response)
            if coerced is not None:
                return coerced
        except Exception:
            pass
    return _fallback_task_intent(prompt)


def _fallback_task_intent(prompt: str) -> TaskIntent:
    return TaskIntent(task_goal=prompt.strip())


def _build_rules_for_state(
    state: RoboGraphState,
    *,
    rule_builder_agent: Any | None,
) -> StructuralRules:
    spec = state.get("spec")
    if not isinstance(spec, TaskIntent):
        raise ValueError("RoboGraphState.spec must be a TaskIntent.")

    if rule_builder_agent is not None:
        try:
            system_prompt = build_rule_builder_system_prompt(query=spec)
        except Exception:
            system_prompt = "\n\n".join(
                [
                    RULE_BUILDER_AGENT_SYSTEM_PROMPT.strip(),
                    _format_query_context(query=spec),
                ]
            )
        try:
            response = rule_builder_agent.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=_rule_builder_user_prompt(state)),
                ]
            )
            structural_rules = _coerce_structural_rules(response)
            if structural_rules["structural_rules"]:
                return structural_rules
        except Exception:
            pass

    return _build_rules_from_examples(spec)


def _build_rules_from_examples(spec: TaskIntent) -> StructuralRules:
    families: list[str] = []
    inferred = _infer_morphology_family(spec)
    if inferred:
        families.append(inferred)
    families.extend(
        family
        for family in ("shared", *DEFAULT_RULE_BUILDER_EXAMPLE_FAMILIES)
        if family not in families
    )

    rules: dict[str, list[str]] = {}
    try:
        examples = sample_rule_builder_examples(
            example_families=families,
            examples_per_family=4,
        )
    except Exception:
        examples = {}

    for family_rules in examples.values():
        for production in family_rules:
            parsed = _parse_production_rule(production)
            if parsed is None:
                continue
            lhs, rhs = parsed
            rules.setdefault(lhs, rhs)

    if not rules:
        rules = _fallback_seed_rules()
    return {"structural_rules": rules}


def _fallback_seed_rules() -> dict[str, list[str]]:
    try:
        known_nodes = {short_name for short_name, _long_name in fetch_grammar_from_db()}
    except Exception:
        known_nodes = set()
    if {"S", "BODY"}.issubset(known_nodes):
        return {"S": ["BODY"]}
    if {"S", "BODY_CHAIN"}.issubset(known_nodes):
        return {"S": ["BODY_CHAIN"]}
    return {}


def _evaluate_rules_for_state(
    state: RoboGraphState,
    *,
    evaluator_agent: Any | None,
) -> TODO:
    if evaluator_agent is not None:
        try:
            response = evaluator_agent.invoke(list(build_checklist_prompt(state)))
            checklist = _coerce_todo(response)
            if checklist["criteria"]:
                return checklist
        except Exception:
            pass
    return _evaluate_rules_deterministically(state)


def _evaluate_rules_deterministically(state: RoboGraphState) -> TODO:
    structural_rules = (state.get("structural_rules") or {"structural_rules": {}})[
        "structural_rules"
    ]
    compile_result = _compile_result_from_state(state)
    compile_safe = bool(compile_result)
    non_empty = bool(structural_rules)
    recursive_or_grouped = _has_recursive_or_grouped_structure(structural_rules)

    checklist = state.get("checklist")
    if not checklist or not checklist.get("criteria"):
        checklist = _fallback_initial_checklist(state)

    criteria: list[Criteria] = []
    for criterion in checklist["criteria"]:
        description = criterion["description"]
        lowered = description.lower()
        if "compile" in lowered or "grammarnodes" in lowered or "vocabulary" in lowered:
            successful = compile_safe
            invalid_nodes = list(compile_result.invalid_nodes.nodes)
            unreachable_nodes = list(compile_result.unreachable_nodes.nodes)
            compile_error = compile_result.compile_error
            if successful:
                critiques = []
            elif compile_error:
                critiques = [
                    "Compile check could not run: "
                    f"{compile_error.get('error_type')}: "
                    f"{compile_error.get('error_message')}"
                ]
            elif invalid_nodes:
                critiques = [
                    "Nodes "
                    + ", ".join(invalid_nodes)
                    + " were NOT in GrammarNodes vocabulary."
                ]
            elif unreachable_nodes:
                critiques = [
                    "Nodes "
                    + ", ".join(unreachable_nodes)
                    + " were valid but unreachable from S."
                ]
            else:
                critiques = ["At least one LHS/RHS node is missing from GrammarNodes."]
        elif "non-empty" in lowered or "structural rules" in lowered and "generated" in lowered:
            successful = non_empty
            critiques = [] if successful else ["No structural rules were generated."]
        elif any(token in lowered for token in ("recursive", "grouped", "repeat", "pair", "chain", "symmetry", "symmetric")):
            successful = recursive_or_grouped
            critiques = [] if successful else ["Prefer recursive chain or pair/group nodes instead of flat terminal-only rules."]
        else:
            successful = compile_safe and non_empty
            critiques = [] if successful else ["Satisfy this proxy goal with compile-safe structural topology."]
        criteria.append(
            {
                "description": description,
                "isSuccessful": successful,
                "critiques": critiques,
            }
        )
    return {"criteria": criteria}


def _has_recursive_or_grouped_structure(rules: dict[str, list[str]]) -> bool:
    group_tokens = {"LEG_PAIR", "ARM_PAIR", "WING_PAIR", "SPRAWLED_LEG_PAIR", "APPENDAGE_PAIR"}
    chain_tokens = {"BODY_CHAIN", "SEG_CHAIN", "SIDEWINDER_CHAIN", "SPINE_CHAIN", "THORAX_CHAIN"}
    for lhs, rhs in rules.items():
        rhs_set = set(rhs)
        if lhs in rhs_set:
            return True
        if rhs_set & group_tokens:
            return True
        if lhs in chain_tokens or rhs_set & chain_tokens:
            return True
    return False


def _checklist_is_successful(checklist: TODO | None) -> bool:
    return bool(checklist and all(item["isSuccessful"] for item in checklist["criteria"]))


def _compile_structural_rules_safely(rules: dict[str, list[str]]) -> CompileAttempt:
    try:
        return CompileAttempt(compile_structural_rules(rules))
    except Exception as exc:
        error = _exception_payload(exc)
        return CompileAttempt(
            CompileResult(False, CompilerError(error=error), compile_error=error)
        )


def _make_initial_checklist(
    state: RoboGraphState,
    *,
    evaluator_agent: Any | None,
) -> TODO:
    if evaluator_agent is not None:
        try:
            checklist = _coerce_todo(evaluator_agent.invoke(list(build_evaluator_system_prompt(state))))
            if checklist["criteria"]:
                return checklist
        except Exception:
            pass
    return _fallback_initial_checklist(state)


def _fallback_initial_checklist(state: RoboGraphState) -> TODO:
    spec = state.get("spec")
    criteria: list[Criteria] = [
        {
            "description": "Structural rules are non-empty and generated from current grammar context.",
            "isSuccessful": False,
            "critiques": ["Awaiting rule generation."],
        },
        {
            "description": "Generated structural rules compile against GrammarNodes vocabulary.",
            "isSuccessful": False,
            "critiques": ["Awaiting compiler check."],
        },
        {
            "description": "Rules use recursive or grouped RoboGrammar topology for repeatable structures.",
            "isSuccessful": False,
            "critiques": ["Awaiting evaluator pass."],
        },
    ]
    if isinstance(spec, TaskIntent):
        criteria.extend(_query_proxy_criteria(spec))
    return {"criteria": criteria}


def _query_proxy_criteria(spec: TaskIntent) -> list[Criteria]:
    criteria: list[Criteria] = []
    inferred = _infer_morphology_family(spec)
    if inferred:
        criteria.append(
            {
                "description": (
                    f"Rules include a {inferred} topology proxy using body scaffolds, "
                    "repeatable modules, or symmetric attachments where appropriate."
                ),
                "isSuccessful": False,
                "critiques": ["Awaiting evaluator pass."],
            }
        )
    capabilities = [*spec.contact_requirements, *spec.stability_requirements, *spec.success_criteria]
    if not capabilities:
        capabilities = _extract_capability_keywords(spec.task_goal)
    for capability in capabilities[:4]:
        criteria.append(
            {
                "description": _capability_proxy_goal(capability),
                "isSuccessful": False,
                "critiques": ["Awaiting evaluator pass."],
            }
        )
    for constraint in spec.hard_constraints[:3]:
        criteria.append(
            {
                "description": f"Rules include a structural proxy for constraint '{constraint}'.",
                "isSuccessful": False,
                "critiques": ["Awaiting evaluator pass."],
            }
        )
    return criteria


def _extract_capability_keywords(text: str) -> list[str]:
    lowered = text.lower()
    return [
        keyword
        for keyword in ("climb", "carry", "stable", "inspect", "crawl", "turn", "balance", "walk", "grasp", "push", "pull")
        if keyword in lowered
    ]


def _capability_proxy_goal(capability: str) -> str:
    lowered = capability.lower()
    if "climb" in lowered:
        return "Rules include a climbing proxy: repeated contact-capable appendage groups or segmented body support for rocky terrain."
    if "carry" in lowered or "payload" in lowered:
        return "Rules include a payload proxy: a central body scaffold with symmetric support modules."
    if "stable" in lowered or "balance" in lowered:
        return "Rules include a stability proxy: paired or mirrored support structures around the body scaffold."
    if "inspect" in lowered or "sensor" in lowered:
        return "Rules include an inspection proxy: a stable body module that can support sensor-bearing components downstream."
    if "crawl" in lowered:
        return "Rules include a crawling proxy: low-profile repeated body or limb modules."
    if "turn" in lowered:
        return "Rules include a turning proxy: articulated body-chain or appendage groups that allow directional changes."
    return f"Rules include a structural proxy for capability '{capability}'."


def _make_structured_agent(schema: Any) -> Any | None:
    from packages.research.local_chat_models import make_structured_llm

    model = os.environ.get("RESEARCH_LLM_MODEL") or os.environ.get("OPENAI_MODEL")
    return make_structured_llm(model, schema)


def _rule_builder_user_prompt(state: RoboGraphState) -> str:
    return "\n\n".join(
        [
            "Generate compile-safe structural_rules for this state.",
            "Treat each TODO criterion as a proxy goal to satisfy with graph topology.",
            _state_summary_for_prompt(state),
        ]
    )


def _state_summary_for_prompt(state: RoboGraphState) -> str:
    spec = state.get("spec")
    structural_rules = state.get("structural_rules")
    compile_result = _compile_result_from_state(state)
    payload = {
        "prompt": state.get("prompt"),
        "spec": _TASK_INTENT_ADAPTER.dump_python(spec) if isinstance(spec, TaskIntent) else spec,
        "structural_rules": structural_rules,
        "node_resolution": state.get("node_resolution"),
        "compile_result": _compile_result_prompt_payload(compile_result),
        "checklist": state.get("checklist"),
        "population": _normalize_population(state.get("population")),
    }
    return json.dumps(payload, indent=2, default=str)


def _normalize_population(value: Any) -> int:
    try:
        population = int(value)
    except (TypeError, ValueError):
        return DEFAULT_ROBOT_POPULATION
    return max(1, population)


_MORPHOLOGY_KEYWORD_MAP: dict[str, tuple[str, ...]] = {
    "quadruped": ("quadruped", "four-legged", "4-legged", "dog-like", "spot-like"),
    "humanoid": ("humanoid", "bipedal", "two-legged", "human-like"),
    "biped": ("biped",),
    "snake": ("snake", "serpentine"),
    "bird": ("bird", "avian", "winged"),
    "hexapod": ("hexapod", "six-legged", "insect-like"),
    "centipede": ("centipede",),
    "lizard": ("lizard",),
    "arachnid": ("arachnid", "spider"),
    "hybrid": ("hybrid",),
    "wheeled": ("wheeled", "wheel-based"),
}


def _infer_morphology_family(intent: TaskIntent) -> str | None:
    text = " ".join([
        intent.task_goal,
        " ".join(intent.terrain),
        " ".join(intent.contact_requirements),
    ]).lower()
    for family, keywords in _MORPHOLOGY_KEYWORD_MAP.items():
        if any(kw in text for kw in keywords):
            return family
    return None


def _coerce_task_intent(value: Any) -> TaskIntent | None:
    if value is None:
        return None
    if isinstance(value, TaskIntent):
        return value
    payload = _coerce_payload(value)
    if not isinstance(payload, dict) or "task_goal" not in payload:
        return None
    try:
        return _TASK_INTENT_ADAPTER.validate_python(payload)
    except Exception:
        return None


def _rules_payload_for_node_resolution(value: Any) -> dict[str, list[str]]:
    node_name = "resolve_grammar_node_names"
    if not isinstance(value, dict):
        raise ValueError(
            f"{node_name} expected state['structural_rules'] to be a dict payload "
            f"with key 'structural_rules', got {type(value).__name__}."
        )
    if "structural_rules" not in value:
        available_keys = ", ".join(sorted(str(key) for key in value.keys())) or "none"
        raise ValueError(
            f"{node_name} expected state['structural_rules']['structural_rules']; "
            f"available state['structural_rules'] keys: {available_keys}."
        )

    raw_rules = value["structural_rules"]
    if not isinstance(raw_rules, dict):
        raise ValueError(
            f"{node_name} expected state['structural_rules']['structural_rules'] "
            f"to be dict[str, list[str]], got {type(raw_rules).__name__}."
        )

    invalid_entries: list[str] = []
    for lhs, rhs in raw_rules.items():
        lhs_id = _string_or_none(lhs)
        lhs_label = repr(lhs)
        if lhs_id is None:
            invalid_entries.append(f"{lhs_label} has a non-string or blank LHS")
        if not isinstance(rhs, list):
            invalid_entries.append(
                f"{lhs_label} RHS is {type(rhs).__name__}, not list[str]"
            )
            continue
        bad_rhs_nodes = [repr(node) for node in rhs if _string_or_none(node) is None]
        if bad_rhs_nodes:
            invalid_entries.append(
                f"{lhs_label} RHS has non-string or blank nodes: "
                + ", ".join(bad_rhs_nodes[:3])
            )

    if invalid_entries:
        shown_entries = "; ".join(invalid_entries[:5])
        if len(invalid_entries) > 5:
            shown_entries += f"; ... {len(invalid_entries) - 5} more"
        raise ValueError(
            f"{node_name} expected structural_rules as dict[str, list[str]] "
            f"with non-empty string GrammarNodes IDs; invalid entries: {shown_entries}."
        )

    return cast(dict[str, list[str]], raw_rules)


def _coerce_structural_rules(value: Any) -> StructuralRules:
    payload = _coerce_payload(value)
    if isinstance(payload, dict):
        raw_rules = payload.get("structural_rules", payload.get("rules", {}))
        if isinstance(raw_rules, dict):
            rules = {
                str(lhs): [str(node) for node in rhs]
                for lhs, rhs in raw_rules.items()
                if isinstance(rhs, list)
            }
            return {"structural_rules": rules}
    return {"structural_rules": {}}


def _coerce_todo(value: Any) -> TODO:
    payload = _coerce_payload(value)
    criteria: list[Criteria] = []
    if isinstance(payload, dict) and isinstance(payload.get("criteria"), list):
        for raw in payload["criteria"]:
            if not isinstance(raw, dict):
                continue
            description = _string_or_none(raw.get("description"))
            if description is None:
                continue
            critiques = raw.get("critiques", [])
            criteria.append(
                {
                    "description": description,
                    "isSuccessful": bool(raw.get("isSuccessful")),
                    "critiques": [str(item) for item in critiques] if isinstance(critiques, list) else [str(critiques)],
                }
            )
    return {"criteria": criteria}


def _coerce_payload(value: Any) -> Any | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    content = getattr(value, "content", None)
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
