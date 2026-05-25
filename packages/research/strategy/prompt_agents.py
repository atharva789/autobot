"""Agent adapters that inject PromptRegistry prompts into the grammar loop.

grammar_loop.build_structural_rules() accepts injectable agent parameters.
These adapters wrap the configured research chat model with the registry's
prompt templates instead of the default grammar prompt constants, making prompts
and local model backends swappable across experiments.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import TypeAdapter

from packages.pipeline.schemas import TaskIntent
from packages.research.prompts.registry import PromptRegistry

_TASK_INTENT_ADAPTER: TypeAdapter[TaskIntent] = TypeAdapter(TaskIntent)

logger = logging.getLogger(__name__)

_VOCAB_HEADER = "GrammarNodes vocabulary:"
_EXAMPLES_HEADER = "Compile-valid few-shot structural-rule examples"


class RegistryNormalizerAgent:
    """Normalizer agent that uses registry prompts."""

    def __init__(
        self,
        registry: PromptRegistry,
        model_id: str,
        template_name: str = "v1_normalizer",
    ) -> None:
        self._registry = registry
        self._template_name = template_name
        self._llm = _make_structured_llm(model_id, TaskIntent)

    def invoke(self, prompt_text: str | Any) -> Any:
        text = _content_str(prompt_text)
        user_prompt = _extract_after(text, "Raw user request:")
        schema_json = json.dumps(
            _TASK_INTENT_ADAPTER.json_schema(), indent=2
        )

        rendered = self._registry.render(
            self._template_name,
            user_prompt=user_prompt,
            schema_json=schema_json,
        )

        if self._llm is None:
            return None
        return self._llm.invoke(rendered)


class RegistryRuleBuilderAgent:
    """Rule builder agent that replaces the system prompt with the registry version.

    The grammar_graph sends [SystemMessage(system_prompt), HumanMessage(user_prompt)].
    The system_prompt contains dynamic sections (vocabulary, examples) from the DB.
    We extract those sections and render our template with them.
    """

    def __init__(
        self,
        registry: PromptRegistry,
        model_id: str,
        template_name: str = "v1_rule_builder",
    ) -> None:
        self._registry = registry
        self._template_name = template_name
        self._model_id = model_id
        self._llm = _make_structured_llm(model_id, _structural_rules_schema())

    def invoke(self, messages: list[Any] | str | Any) -> Any:
        system_content, user_content = _split_messages(messages)

        query_context = _extract_section(
            system_content, "Robot query context:", _VOCAB_HEADER
        )
        grammar_vocabulary = _extract_section(
            system_content, _VOCAB_HEADER, _EXAMPLES_HEADER
        )
        rule_examples = _extract_after(system_content, _EXAMPLES_HEADER)

        rendered = self._registry.render(
            self._template_name,
            query_context=query_context,
            grammar_vocabulary=grammar_vocabulary,
            rule_examples=rule_examples,
        )

        if self._llm is None:
            return None

        from langchain_core.messages import HumanMessage, SystemMessage
        return self._llm.invoke([
            SystemMessage(content=rendered),
            HumanMessage(content=user_content),
        ])


class RegistryEvaluatorAgent:
    """Evaluator agent that uses registry prompts."""

    def __init__(
        self,
        registry: PromptRegistry,
        model_id: str,
        template_name: str = "v1_evaluator",
    ) -> None:
        self._registry = registry
        self._template_name = template_name
        self._llm = _make_structured_llm(model_id, _todo_schema())

    def invoke(self, messages: list[Any] | str | Any) -> Any:
        _, user_content = _split_messages(messages)

        state_summary = _extract_after(
            user_content, "Current state:"
        ) or user_content

        rendered = self._registry.render(
            self._template_name,
            state_summary=state_summary,
        )

        if self._llm is None:
            return None

        from langchain_core.messages import HumanMessage, SystemMessage
        return self._llm.invoke([
            SystemMessage(content=rendered),
            HumanMessage(content=user_content),
        ])


def build_registry_agents(
    registry: PromptRegistry,
    model_id: str,
) -> dict[str, Any]:
    """Build all three grammar loop agents from registry prompts.

    Returns a dict ready to unpack into build_structural_rules():
        normalizer_agent, rule_builder_agent, evaluator_agent
    """
    registry.load("v1_normalizer")
    registry.load("v1_rule_builder")
    registry.load("v1_evaluator")

    return {
        "normalizer_agent": RegistryNormalizerAgent(registry, model_id),
        "rule_builder_agent": RegistryRuleBuilderAgent(registry, model_id),
        "evaluator_agent": RegistryEvaluatorAgent(registry, model_id),
    }


def _make_structured_llm(model_id: str, schema: Any) -> Any:
    from packages.research.local_chat_models import make_structured_llm

    return make_structured_llm(model_id, schema)


def _structural_rules_schema() -> Any:
    from packages.research.agent_loops.grammar_loop import StructuralRules
    return StructuralRules


def _todo_schema() -> Any:
    from packages.research.agent_loops.grammar_loop import TODO
    return TODO


def _content_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    return str(value)


def _split_messages(messages: Any) -> tuple[str, str]:
    """Extract system and user content from a message list."""
    if isinstance(messages, str):
        return messages, ""
    if isinstance(messages, list) and len(messages) >= 2:
        return _content_str(messages[0]), _content_str(messages[1])
    if isinstance(messages, list) and len(messages) == 1:
        return _content_str(messages[0]), ""
    return _content_str(messages), ""


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    """Extract text between two markers."""
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        return text[start:].strip()
    return text[start:end].strip()


def _extract_after(text: str, marker: str) -> str:
    """Extract text after a marker."""
    idx = text.find(marker)
    if idx < 0:
        return text.strip()
    return text[idx + len(marker):].strip()
