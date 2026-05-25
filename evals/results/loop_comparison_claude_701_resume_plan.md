# RoboGrammar Claude 701 loop comparison resume plan

The stopped run in `loop_comparison_claude_701_partial.md` is a partial
grammar-only baseline. It is visible in LangSmith, but it is not a valid
side-by-side comparison because `compiler_centric` and `compiler_feedback` were
not reached.

## Current stopped state

- Completed local boundary: `grammar` only, `102/701` examples.
- Not reached: `compiler_centric`, `compiler_feedback`.
- Partial LangSmith project:
  `robogrammar-compile-result-state.2026-05-25-grammar-claude-code-a74f00ff`
- Partial metrics:
  `evals/results/loop_comparison_claude_701_partial_first_page_metrics.json`

## Recommended completion strategy

Run fresh comparable chunks where all three loop variants execute on the same
dataset slice. Do not treat the existing `grammar`-only first 102 examples as
the matched baseline for a side-by-side result unless matching
`compiler_centric` and `compiler_feedback` are also run on exactly that slice.

Use conservative chunk sizes so each chunk writes a partial summary and can be
stopped cleanly. The runner writes its output summary before each loop, after
each completed loop, and on SIGTERM/SIGINT.

## Commands

First comparable slice:

```bash
/Users/thorbthorb/.venvs/jupyterfix/bin/python -m evals.run_langsmith_loop_experiments \
  --provider claude-code \
  --loop grammar \
  --loop compiler_centric \
  --loop compiler_feedback \
  --offset 0 \
  --limit 25 \
  --max-attempts 2 \
  --max-concurrency 3 \
  --output evals/results/loop_comparison_claude_701_chunk_000_024.json
```

Next slices:

```bash
/Users/thorbthorb/.venvs/jupyterfix/bin/python -m evals.run_langsmith_loop_experiments \
  --provider claude-code \
  --loop grammar \
  --loop compiler_centric \
  --loop compiler_feedback \
  --offset 25 \
  --limit 25 \
  --max-attempts 2 \
  --max-concurrency 3 \
  --output evals/results/loop_comparison_claude_701_chunk_025_049.json
```

Continue by increasing `--offset` in increments of `25` until all `701`
examples are covered.

## After each chunk

1. Read the chunk JSON and collect each loop's `experiment_name`.
2. Summarize each LangSmith project with bounded pagination first:

   ```bash
   /Users/thorbthorb/.venvs/jupyterfix/bin/python evals/summarize_loop_experiment_metrics.py \
     --project <experiment_name> \
     --max-pages 1 \
     --output evals/results/<experiment_name>-metrics-first-page.json
   ```

3. If the bounded summary is healthy and the project is small enough, rerun
   without `--max-pages` for full metrics.
4. Record the chunk metrics and LangSmith links in `.codex`.

## Aggregate chunks

Once chunk JSON files and per-project metrics files exist, aggregate them into a
single local summary:

```bash
/Users/thorbthorb/.venvs/jupyterfix/bin/python evals/aggregate_loop_comparison_chunks.py \
  --chunk-glob 'evals/results/loop_comparison_claude_701_chunk_*.json' \
  --metrics-dir evals/results \
  --expected-examples 701 \
  --require-complete \
  --output evals/results/loop_comparison_claude_701_aggregate.json
```

The aggregator accepts legacy chunk JSON that has `experiment_name` but no loop
`status`, and treats those loops as completed. It also normalizes both the
current metric keys (`root_runs`, `compile_statuses`, `mean_task_alignment`,
`mean_compiler_validity`) and the earlier first-page keys
(`root_runs_first_page`, `compile_statuses_first_page`,
`mean_task_alignment_first_page`, `mean_compiler_validity_first_page`).
Use the aggregate JSON's `coverage.complete` field as the local completion
gate; it is true only when comparable completed chunks cover at least the
expected example count and no chunk has a missing or interrupted loop. With
`--require-complete`, the command exits non-zero until that gate is satisfied.

## Completion criteria

The original objective is complete only when all three loops have comparable
LangSmith experiment projects for the same 701 examples, and the metrics are
recorded for `grammar`, `compiler_centric`, and `compiler_feedback`.
