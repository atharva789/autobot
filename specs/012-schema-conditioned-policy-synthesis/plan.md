# Plan 012 — Execution architecture

**Source spec:** [spec.md](spec.md)
**Status:** proposed, not implemented

---

## 1. Everything runs in the cloud. Two planes, because of one constraint.

Scheduled Claude Code routines run as isolated cloud sessions: a fresh GitHub checkout and a model,
with no repository secrets, no Docker daemon, and no MuJoCo. That is not a reason to run the
experiment locally — it is a reason to put the compute where the secrets already live.

**GitHub Actions is the compute plane.** It has a secret manager, Docker, unlimited free minutes on
public repositories, and it can commit results back. The routine never holds a credential and never
runs physics; it decides *what to run* and reads *what came back*.

| | Control plane — Claude routine | Compute plane — GitHub Actions |
| --- | --- | --- |
| Trigger | Daily cron | Push to `experiments/queue/**`, or `workflow_dispatch` |
| Holds secrets | No | Yes (`OPENAI_API_KEY`, repo secret) |
| Model calls | Claude, session model | OpenAI, cheap tier by default |
| Physics | None | MuJoCo, headless CPU |
| Docker | No | Yes — Compose stack (§4) |
| Writes | Experiment manifest, spec increments, README block | Run logs, scaffolds, traces, gate results |
| Cost | Session only | Free minutes + metered OpenAI spend |

Both planes are cloud. Neither needs the developer's machine.

## 2. The loop between them

```text
  day N, 06:00 PT
  ┌─────────────────────────────────────────────────────────┐
  │ Claude routine (control plane)                          │
  │  1. read .runs/loop_research/ from day N-1              │
  │  2. read gate results, cost, what failed                │
  │  3. decide ONE change; write it as a spec increment     │
  │  4. emit experiments/queue/<date>.yaml                  │
  │  5. regenerate README ROUTINE block from logs only      │
  │  6. push branch routine/experiments, open PR            │
  └────────────────────────┬────────────────────────────────┘
                           │ push triggers workflow
                           v
  ┌─────────────────────────────────────────────────────────┐
  │ GitHub Actions (compute plane)                          │
  │  7. docker compose up; load OPENAI_API_KEY from secrets │
  │  8. run the agent loop under the manifest's parameters  │
  │  9. run G1–G4 gates + negative control                  │
  │ 10. commit .runs/loop_research/<run-id>/ back to branch │
  └────────────────────────┬────────────────────────────────┘
                           │
                           v
              day N+1 routine reads step 10's output
```

The seam is `.runs/loop_research/` — committed, machine-readable run logs, already the repo's
convention (`.runs/agent_evals/` is tracked, 134 files).

**The routine may never report a number it did not read from a committed run log.** That single rule
is what stops a daily-writing agent from manufacturing progress. It is enforceable on review because
every number in the README block must be greppable in a committed JSON file.

## 3. Secrets

| Secret | Where | Used by | Notes |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | GitHub repo secret | Actions only | Never reaches the Claude routine |
| `GITHUB_TOKEN` | Auto-injected | Actions | Commits run logs back |

The routine's checkout credential is scoped to push its own branch. It never reads
`OPENAI_API_KEY` — the control plane makes no OpenAI calls, so it has no reason to hold the key,
and a compromised routine session cannot spend money.

Setting the secret is a human action (see §8) because it is a credential.

## 4. Compose stack, inside the Actions runner

Five services, each standing in for a managed cloud service. This is the smallest set that runs the
experiment in the spec — not a portfolio prop.

```text
                       orchestrator
                  (agent loop, cost ceiling,
                   gate runner)
                              |
        +---------------------+---------------------+
        |                     |                     |
        v                     v                     v
     queue                sim-worker            runlog
   (Redis)              (MuJoCo rollouts,      (Postgres)
   job fan-out           N replicas)           runs, revisions,
        |                     |                gates, cost
        +----------> artifacts (MinIO) <-------+
                  scaffolds, traces, replay seeds
```

| Service | Stands in for | Justified by |
| --- | --- | --- |
| `runlog` (Postgres) | Managed relational DB | R2, R6 — revision lineage and replay need real relations |
| `artifacts` (MinIO) | Object storage | Rollout traces are too large for a DB row |
| `queue` (Redis) | Managed queue | Rollout batches fan out; the loop must not block on one |
| `sim-worker` | CPU/GPU worker pool | The only component that scales with rollout count |
| `orchestrator` | Application container | Holds the loop, the ceiling, and the gate runner |

At the end of a run the stack is torn down and `runlog` is exported to JSON into
`.runs/loop_research/<run-id>/`. The database is ephemeral; **the committed JSON is the record**,
because the control plane can only read what is in git.

**Explicitly not included:** Kubernetes, service mesh, tracing backend, feature store, model
registry. Each gets added when a run log shows a measured limit, not before.

## 5. Cost model

Most loop steps are not hard, and paying frontier prices for all of them is the obvious waste.

| Step | Frequency | Tier | Why |
| --- | --- | --- | --- |
| Read rollout metrics, adjust a weight | High | Cheap frontier | Numeric nudge on a fixed structure |
| Diagnose a termination cause | Medium | Cheap frontier | Classification against a known set |
| Restructure the scaffold | Low | Frontier | Genuinely open-ended |
| G1 gate | Every run | None — static parse | No model call at all |

Enforced in the orchestrator, not by convention:

- Hard per-experiment dollar ceiling; on breach the run aborts and the log records the abort.
- Per-step token cap; an over-cap step is truncated and marked, never silently retried.
- Prompt-prefix caching on the schema — fixed for the whole experiment and the largest stable block.
- **Cost per gate-point-moved** is logged. That is the number that says whether a change was worth it.

Actions minutes are free on public repos, so the only real spend is OpenAI tokens, and the ceiling
bounds it per run.

## 6. Observability

- **Run log** — committed JSON, the source of truth, because the control plane reads only git.
- **Traces** — LangSmith/Langfuse hooks already exist in the repo; one trace per scaffold revision,
  tagged with schema id, gate outcomes, and cost.
- **Rubrics** — gate outcomes are rubric-scored against fixed, versioned criteria. A rubric change is
  a spec change and takes a new version, so historical runs stay comparable.

## 7. Build order

The negative control is built before the real loop on purpose: it is what proves the gates work.

1. `TrainingScaffold` schema and compiler-to-MuJoCo. Gate: a hand-written scaffold trains.
2. Four structurally different schemas. Gate: all compile, baselines run.
3. G1 static resolver. Gate: catches a hand-made unresolvable scaffold.
4. `static_scaffold_loop` negative control. Gate: fails G1–G3; its margin sets τ.
5. G2/G3 structural diff. Gate: separates control from per-schema hand-written scaffolds.
6. Actions workflow + Compose stack, running steps 1–5 in CI. Gate: green run, logs committed.
7. The real loop, cheap tier. Gate: passes G1–G3 on dev schemas.
8. Held-out evaluation, **once**, after everything above is frozen.

Repeatedly evaluating on held-out schemas and tuning against them turns them into dev schemas and
destroys G4. Step 8 happens one time.

## 8. Human actions required before first compute run

1. Add the OpenAI key as a repo secret:

   ```bash
   gh secret set OPENAI_API_KEY --repo atharva789/autobot
   ```

2. Review and merge the workflow that grants Actions write access to the routine branch.

Until step 1 is done, the compute plane cannot run and the routine will correctly report that it has
no new evidence.

## 9. Risks

| Risk | Response |
| --- | --- |
| Gates pass but are trivially passable | Negative control calibrates; if it passes anything, gates are rewritten |
| Routine fabricates progress | May not report unread numbers; README block is delimited and log-derived |
| Cheap tier too weak to restructure | Tiering is measured — log gate movement per tier, escalate on evidence |
| Held-out leaks into development | Held-out schemas live in a separate directory, untouched during steps 1–7 |
| Actions runner too slow for MuJoCo | Step budget is fixed and small by design; if it still fails, cut rollout count, not the gates |
| Compose stack becomes the project | Adding a service requires a measured limit in a committed run log |
| Routine and human collide in git | Routine is confined to `routine/experiments` and opens PRs; never pushes to a human branch |
