"""Grammar strategy: wraps the registered research-side grammar agent loop."""

from __future__ import annotations

from typing import Any

from packages.research.agent_loops.grammar_loop import build_structural_rules
from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.research.prompts.registry import PromptRegistry
from packages.research.strategy.llm_materializer import LLMIRMaterializer
from packages.research.strategy.prompt_agents import build_registry_agents
from packages.research.strategy.protocol import (
    IRMaterializer,
    StrategyConfig,
)


class GrammarStrategy:
    """Runs the RoboGrammar LangGraph loop then materializes IR via LLM."""

    def __init__(
        self,
        materializer: IRMaterializer | None = None,
    ) -> None:
        self._materializer = materializer or LLMIRMaterializer()
        self.last_state: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "grammar"

    @property
    def version(self) -> str:
        return "1.0.0"

    def generate(
        self,
        prompt: str,
        config: StrategyConfig,
    ) -> list[RobotDesignIR]:
        registry = config.prompt_registry or PromptRegistry()
        agents = build_registry_agents(registry, config.model_id)

        state = build_structural_rules(
            prompt=prompt,
            initial_state=None,
            normalizer_agent=agents["normalizer_agent"],
            rule_builder_agent=agents["rule_builder_agent"],
            evaluator_agent=agents["evaluator_agent"],
            population=config.max_candidates,
            max_attempts=int(config.extra.get("max_attempts", 2)),
            require_human_confirmation=False,
        )
        self.last_state = dict(state)

        raw_output: dict[str, Any] = {
            "structural_rules": _extract_rules(state),
            "spec": state.get("spec"),
            "compile_safe": bool(state.get("compile_result")),
            "checklist": state.get("checklist"),
        }

        designs = self._materializer.materialize(raw_output, prompt, config)

        population = config.max_candidates
        if len(designs) < population:
            for i in range(len(designs), population):
                variant_config = StrategyConfig(
                    seed=config.seed + i,
                    model_id=config.model_id,
                    max_candidates=1,
                    prompt_registry=config.prompt_registry,
                    extra=config.extra,
                )
                variant_designs = self._materializer.materialize(
                    raw_output, prompt, variant_config
                )
                designs.extend(variant_designs)

        return designs[:population]


def _extract_rules(state: Any) -> dict[str, list[str]]:
    structural_rules = state.get("structural_rules")
    if isinstance(structural_rules, dict):
        inner = structural_rules.get("structural_rules", structural_rules)
        if isinstance(inner, dict):
            return inner
    return {}
