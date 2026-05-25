# RoboGrammar Claude 701 loop comparison partial result

- Stopped: 2026-05-25 local workspace session, at the user's request.
- Stop reason: stop the experiment after the last completed run.
- Runner command:
  ```bash
  /Users/thorbthorb/.venvs/jupyterfix/bin/python -m evals.run_langsmith_loop_experiments \
    --provider claude-code \
    --loop grammar \
    --loop compiler_centric \
    --loop compiler_feedback \
    --limit 0 \
    --max-attempts 2 \
    --max-concurrency 3 \
    --output evals/results/loop_comparison_claude_701.json
  ```
- Final local completed boundary: first loop `grammar`, `102/701` examples completed.
- Reached loops: `grammar` only.
- Not reached: `compiler_centric`, `compiler_feedback`.
- Final full comparison output: `evals/results/loop_comparison_claude_701.json` was not emitted because the runner was intentionally stopped before all configured loops completed.
- Local log: `evals/results/loop_comparison_claude_701.log`.
- LangSmith project: `robogrammar-compile-result-state.2026-05-25-grammar-claude-code-a74f00ff`.
- LangSmith comparison URL:
  `https://smith.langchain.com/o/a52ccfe7-bc7a-4851-9a62-677d03ed199b/datasets/76d011c7-6bff-4260-a5bd-dbd8dddc80c1/compare?selectedSessions=b70dabe3-dfba-42e0-8196-6b30ff2e1f1e`
- Lightweight LangSmith visibility check after stop: first page capped at `100` root runs, with `97` successful and `3` pending on that page.
- Bounded LangSmith metrics from the first 100 root runs are recorded in `evals/results/loop_comparison_claude_701_partial_first_page_metrics.json`:
  - Run statuses: `97` success, `3` pending.
  - Errors: `0`.
  - Compile status: `81` compile-safe, `19` compile-unsafe.
  - Mean task alignment: `0.7357`.
  - Mean compiler validity: `0.8351`.
  - `langsmith_trace_id` present in `97` returned runs.
- Metrics caveat: an all-pages LangSmith metric summarization attempt stalled on pagination and was terminated without writing `evals/results/loop_comparison_claude_701_partial_metrics.json`. `evals/summarize_loop_experiment_metrics.py` now supports bounded pagination via `--max-pages`; the bounded metrics above are first-page metrics, not full 102-run totals.
- Interpretation: this is a visible partial grammar-loop baseline, not a completed side-by-side comparison of all three loop variants.
