---
description: How prompts become ingest jobs, search queries, selected references, and optional motion-analysis dispatches.
---

# Ingest Pipeline

The ingest route lives in `apps/api/routes/ingest.py`.

It accepts a natural-language task prompt and tries to produce useful reference context for downstream robot design.

## `POST /ingest`

Main behavior:

1. create a job id,
2. log the raw prompt,
3. call `DemoService.analyze_prompt(req.prompt)`,
4. require at least one generated search query,
5. select a reference source,
6. optionally dispatch motion analysis,
7. persist the ingest job in `workspace_store`.

## Prompt analysis

The prompt analysis step extracts:

- task goal,
- constraints,
- search queries,
- possible motion-reference needs.

The design route later uses `plan.task_goal` or `selected_query` as the robot generation prompt.

## Reference selection

The route supports three practical states:

| State | Meaning |
| --- | --- |
| YouTube selected | A reference video was found and selected |
| DROID fallback | YouTube lookup failed or was unavailable, so a fallback reference is used |
| reference skipped | `SKIP_YOUTUBE_SEARCH=1`, so the route skips external search |

## Motion analysis dispatch

If a YouTube video is selected, the route can try a GVHMR dispatch for human motion analysis. This is best-effort and should be treated as enrichment, not a hard dependency for body generation.

## Persistence

The persisted ingest job records:

- prompt,
- plan,
- selected query,
- source,
- selected video/reference,
- status,
- error details when applicable.

`POST /designs/generate` consumes the stored ingest job by id.

## Where ingest ends

Ingest does not generate robot bodies. It prepares task context. Robot body generation starts when the design route calls an agent loop.

