---
description: The commands that give useful evidence before changing code or publishing documentation.
---

# Run And Verify

## Fast code checks

Run the focused research tests when changing generation, prompt, benchmark, or registry behavior:

```bash
pytest tests/test_research_core.py -v
pytest tests/test_robot_program_v2.py -v
pytest tests/test_agent_loop_registry.py -v
```

Run product-facing tests when changing the API, workspace, frontend contracts, or persistence:

```bash
pytest tests/test_designs_route.py -v
pytest tests/test_workspace_routes.py -v
pytest tests/test_workspace_sdk.py -v
pytest tests/test_workspace_store.py -v
pytest tests/test_frontend_workspace_contract.py -v
```

Run the full suite before merging broader changes:

```bash
pytest tests/ -v
```

## Frontend checks

For frontend changes:

```bash
cd apps/web
npm run build
```

When UI rendering is changed, verify the running app in a real browser. The robot viewer depends on Three.js and needs visual inspection for camera framing, blank canvas regressions, and overlay overlap.

## API smoke checks

Start the API:

```bash
uvicorn apps.api.app:app --host 127.0.0.1 --port 8000
```

Then verify:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/designs/agent-loops
```

The loop list should include at least `grammar_v2` in a healthy local checkout. It may also include `creative_qd_v2`.

## Documentation validation

The installed `gitbook` CLI supports `dev`, `publish` for integrations, `openapi`, and authentication commands. It does not expose the old static-site `build` command. For this repo, local documentation validation should check the GitBook source instead:

```bash
python3 - <<'PY'
from pathlib import Path
import re

root = Path("docs")
summary = root / "SUMMARY.md"
assert summary.exists(), "docs/SUMMARY.md is missing"

missing = []
for match in re.finditer(r"\]\(([^)]+)\)", summary.read_text()):
    target = match.group(1)
    if target.startswith(("http://", "https://", "#")):
        continue
    if not (root / target).exists():
        missing.append(target)

if missing:
    raise SystemExit("Missing SUMMARY targets: " + ", ".join(missing))

print("GitBook navigation OK")
PY
```

Also run:

```bash
gitbook whoami
```

That confirms the local CLI is authenticated before attempting a GitBook sync or publish workflow.

## Architecture handoff gate

Architecture-sensitive changes must stage the architecture handoff document in the same commit. The default document is `.codex`, unless `git config codex.archDocPath <path>` overrides it.

Architecture-sensitive changes include:

- public APIs,
- route surfaces,
- persistence schemas and migrations,
- shared protocols and type contracts,
- registries and strategy abstractions,
- dependency or build configuration,
- shared core or pipeline modules.

Docs-only edits usually do not need `.codex`, but this repo already uses the architecture handoff rule for major API and abstraction changes.

