---
description: Testing strategy by layer, with focused commands and what each class of tests protects.
---

# Testing

## Research tests

Use these when changing agent loops, strategies, prompts, benchmarks, or generated body structures:

```bash
pytest tests/test_research_core.py -v
pytest tests/test_agent_loop_registry.py -v
pytest tests/test_robot_program_v2.py -v
```

These protect:

- strategy contracts,
- loop registration,
- deterministic grammar compilation,
- research metrics,
- prompt-driven generation surfaces.

## Product API tests

Use these when changing workspace, routes, persistence, or candidate conversion:

```bash
pytest tests/test_designs_route.py -v
pytest tests/test_workspace_routes.py -v
pytest tests/test_workspace_sdk.py -v
pytest tests/test_workspace_store.py -v
```

These protect:

- route behavior,
- workspace orchestration,
- local SQLite persistence,
- thread artifacts,
- generated candidate payloads.

## Frontend contract tests

Use:

```bash
pytest tests/test_frontend_workspace_contract.py -v
```

Also run the frontend build when changing TypeScript or UI code:

```bash
cd apps/web
npm run build
```

## Full suite

Before merging broad changes:

```bash
pytest tests/ -v
```

## Documentation checks

Docs validation should check:

- every `SUMMARY.md` link resolves,
- root `.gitbook.yaml` points to `docs/`,
- no page exists outside navigation unless intentionally hidden,
- GitBook-specific blocks are syntactically balanced enough for preview.

The current GitBook CLI does not expose legacy `gitbook build`, so local validation is link and navigation focused unless GitBook preview is running.

