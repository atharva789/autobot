# Contract — the agent loop

**Source spec:** [spec.md](spec.md) · **Status:** proposed, not implemented

Extends the repo's existing `AgentLoopRunner` protocol
(`packages/research/agent_loops/protocol.py`) rather than inventing a parallel one.

---

## Signature

```python
class ScaffoldLoopRunner(Protocol):
    def __call__(
        self,
        schema_path: Path,
        task_text: str,
        *,
        config: ScaffoldLoopConfig,
    ) -> ScaffoldLoopResult: ...
```

```python
@dataclass(frozen=True)
class ScaffoldLoopConfig:
    max_revisions: int = 8
    episodes_per_batch: int = 64
    step_budget: int = 2_000_000
    usd_ceiling: float = 5.0
    cheap_model: str = ...          # high-frequency steps
    frontier_model: str = ...       # restructure steps only
    seed: int = 42
    prompt_version: str = "v1"

@dataclass(frozen=True)
class ScaffoldLoopResult:
    scaffolds: tuple[TrainingScaffold, ...]   # every revision, in order
    batches: tuple[RolloutBatch, ...]
    status: Literal["completed", "aborted_cost", "aborted_error"]
    cost: CostRecord
```

Frozen dataclasses and tuples: a revision history that can be mutated after the fact is not
evidence.

## Hard constraints

**C1 — No task-specific branching.** Loop code may not branch on task text content. A
`if "lift" in task_text:` is a spec violation, not a shortcut. The task is data flowing into a
prompt, never a switch selecting hand-written behavior.

*Enforcement:* the negative control exists precisely because this cannot be checked by reading code
alone. G2/G3 catch it behaviorally.

**C2 — The schema is read, not assumed.** The loop must parse the schema and pass the resulting
entity table into its prompts. It may not carry a hardcoded list of joint or body names.

*Enforcement:* G1 on a schema using unusual naming conventions.

**C3 — Structured feedback only.** The loop consumes `RolloutBatch` — termination histogram, contact
events, joint saturation. Reducing a batch to `success_rate` before the model sees it violates R3
and removes the only signal that makes revision better than random search.

**C4 — Every revision cites its cause.** A new scaffold carries `motivating_batch_id`. Rejected at
write time otherwise (R2).

**C5 — Cost ceiling is enforced in code.** On breach the loop returns `aborted_cost` with partial
results. It does not raise, and it does not silently continue — a run that overspends must still
produce a readable record of what it bought.

**C6 — Evidence-dense requests.** One revision step is one model call. The call carries the entire
`RolloutBatch` and returns diagnosis, proposed edit, and self-check in one structured response.
Per-episode calls are forbidden. Latency-insensitive calls go through the async batch endpoint.

The boundary: transport batching only. Independent gate arms (G2 permutations, G3 bodies) must
never share a prompt context — a model shown four schemas side by side can differentiate its four
outputs deliberately, which games the divergence gates. Separate requests, same batch job.

*Enforcement:* the orchestrator logs calls-per-revision and request membership per batch job; a
gate arm sharing a request with another arm invalidates that gate's result for the run.

## Expected shape of a revision step

```text
batch(N) ──> diagnose ──> propose edit ──> validate ──> compile ──> scaffold(N+1)
             (cheap)      (cheap|frontier) (static)     (MuJoCo)
                │              │
                │              └── frontier tier ONLY when diagnose returns
                │                  `restructure_required`
                └── input: termination histogram, contacts, saturation
                    NOT: success_rate alone
```

Tier escalation is a decision the loop makes and logs, not a fixed policy. `usd_per_gate_point` in
the run log is what tells us afterwards whether escalating was worth it.

## Registration

Loops register under the existing registry so the product API and tests reach them unchanged:

```python
register_agent_loop("scaffold_v1", run_scaffold_loop)
register_agent_loop("static_scaffold", run_static_scaffold_loop)   # negative control
```

The control registers alongside the real loop deliberately. It runs in the same harness, on the same
cadence, through the same gates (R7) — a control that runs in a special path proves nothing about
the path the real loop takes.

## What the loop must NOT do

- Emit Python, a policy checkpoint, or training hyperparameters. It emits a scaffold; the harness
  trains.
- Read `holdout-*` schemas. Enforced by directory separation and checked in CI.
- Write its own gate results. The harness runs gates; a loop that scores itself is not evaluated.
- Retry a cost-capped step. The cap is the signal.
