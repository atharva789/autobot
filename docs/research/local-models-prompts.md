---
description: Local chat model adapters, prompt registry behavior, and versioned prompt templates.
---

# Local Models And Prompts

## Local chat models

`packages/research/local_chat_models.py` provides ChatOpenAI-compatible model factories for local or configured providers.

Use:

- `make_chat_model()`,
- `make_structured_llm()`.

Avoid direct `ChatOpenAI` imports in research loops and strategies unless a task explicitly requires that fallback.

## Provider selection

Common provider values:

| Provider | Use case |
| --- | --- |
| `codex` | Isolated persistent local Codex MCP-server thread |
| `claude-code` | Persistent Claude Code with Sonnet-class model |
| `openai` | Explicit OpenAI fallback |

Set:

```bash
export RESEARCH_LLM_PROVIDER=codex
```

or another supported provider before running model-backed experiments.

## Prompt registry

`packages/research/prompts/registry.py` loads and renders YAML templates.

It supports:

- named templates,
- versions,
- variable rendering,
- SHA-256 hashes,
- prompt metadata for reproducibility.

## Prompt templates

Current templates include V1 and V2 contracts.

V1 examples:

- `v1_normalizer.yaml`,
- `v1_rule_builder.yaml`,
- `v1_evaluator.yaml`,
- `v1_materializer.yaml`.

V2 examples:

- `v2_program_builder.yaml`,
- `v2_program_evaluator.yaml`,
- `v2_program_repair.yaml`,
- `v2_component_materializer.yaml`.

## Prompt discipline

When changing prompts:

- keep the output schema explicit,
- keep examples minimal but representative,
- update tests or fixtures that depend on exact prompt shape,
- preserve prompt hashes in experiment metadata,
- avoid product-route imports of prompt registry internals.

## Deterministic fallback

Many generation paths include deterministic fallback behavior. This is not a bug. It keeps local tests, docs, and non-networked development usable.

When publishing research claims, clearly distinguish:

- model-backed generation,
- fallback generation,
- benchmarked simulation evidence,
- smoke-test-only evidence.

