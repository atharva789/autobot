---
description: How local SQLite workspace state is organized and where generated robot data is stored.
---

# Local Persistence

The current workspace product uses local SQLite through `apps/api/workspace_store.py`.

Default database path:

```text
/tmp/il_ideation/workspace.sqlite3
```

Override it with:

```bash
export WORKSPACE_DB_PATH=/path/to/workspace.sqlite3
```

## What the store owns

`WorkspaceStore` stores product workflow state:

| Table family | Purpose |
| --- | --- |
| ingest jobs | prompt analysis, selected references, source metadata, status |
| designs | generated candidate records |
| design revisions | stored revisions and latest candidate state |
| design checkpoints | HITL approval checkpoints |
| approval events | review and approval actions |
| task runs | execution metadata for API-driven work |
| artifacts | MJCF, UI scene, and export artifacts |
| design events | timeline events for design lifecycle |
| evolutions | evolution jobs and loop state |
| program drafts | generated `program.md` drafts for evolutions |
| iterations | evolution iteration records |
| workspace projects | local project metadata |
| workspace threads | chat thread metadata |
| thread messages | user and assistant messages |
| context summaries | compact summaries attached to threads |
| thread artifacts | generated robot artifacts attached to chats |
| simulation specs | requested simulation checks |
| policy specs | requested policy/training specs |

## JSON normalization

Several fields are stored as JSON strings in SQLite and decoded when read. Boolean-like fields are normalized on the way in and out. This matters for frontend contract stability because route handlers can return normal Python dictionaries rather than raw SQLite strings.

## Product state versus research state

Product state answers:

- What did the user ask for?
- Which candidate did we generate?
- Which thread owns the artifact?
- Which design is selected?
- What did the user approve?
- Which export artifacts exist?

Research state answers:

- Which strategy was run?
- Which seed and model were used?
- Which prompts and prompt hashes were used?
- What metrics did each candidate achieve?
- How does this run compare to another run?

Keep these stores separate. Product persistence is not a research benchmark database.

## Supabase status

The repo still contains Supabase client code, migrations, and older routes that reference Supabase concepts. The current workspace flow is local-first. When documenting or debugging state, confirm which route path you are using before assuming Supabase is active.

