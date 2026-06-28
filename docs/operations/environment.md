---
description: Environment variables and runtime knobs that affect the product, research loops, model providers, and exports.
---

# Environment

## Product API

| Variable | Purpose |
| --- | --- |
| `WORKSPACE_DB_PATH` | Override local SQLite workspace database path |
| `SKIP_YOUTUBE_SEARCH` | Skip YouTube search in ingest when set to `1` |
| `EVOLUTION_ARTIFACTS_DIR` | Override local evolution artifact directory |
| `NEXT_PUBLIC_API_URL` | Frontend base URL for the API |

Default workspace database:

```text
/tmp/il_ideation/workspace.sqlite3
```

## Research LLM provider

| Variable | Purpose |
| --- | --- |
| `RESEARCH_LLM_PROVIDER` | Select local or remote model provider |
| `RESEARCH_USE_LANGGRAPH_AUTO_INVOKE` | Enable automatic LangGraph invocation for supported legacy paths |

Common provider values:

```bash
export RESEARCH_LLM_PROVIDER=codex
export RESEARCH_LLM_PROVIDER=claude-code
export RESEARCH_LLM_PROVIDER=openai
```

Use `packages/research/local_chat_models.py` factory helpers instead of direct provider imports.

## External services

The repo contains integrations or hooks for:

- Supabase,
- LangSmith,
- Google/Gemini,
- YouTube/reference search,
- GVHMR dispatch,
- Modal trial dispatch,
- MuJoCo screening,
- GitBook docs publishing.

Not all of these are required for local smoke tests. When documenting evidence, state which external services were actually reachable.

## Local-first development

Many core paths work without external services:

- deterministic grammar fallback,
- local workspace database,
- route unit tests,
- frontend contract tests,
- documentation validation,
- research core tests.

This is intentional. A missing networked service should not make every developer flow unusable.

