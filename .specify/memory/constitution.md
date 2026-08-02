<!--
Sync Impact Report
- Version change: template -> 1.0.0
- Adopted principles: Spec Is Source; Executed Evidence; Test First; Complexity Pays Rent;
  Architectural Boundaries; Falsification Before Expansion
- Added sections: Product Discovery and Resource Constraints; Development Workflow
- Removed sections: none; placeholder sections were replaced
- Templates: plan-template.md updated; spec-template.md updated; tasks-template.md updated
- Command templates: no .specify/templates/commands directory exists
- Follow-up items: none
-->
# IL Ideation Constitution

## Core Principles

### I. Specification Is the Source

Every product behavior, public contract, data model, and architectural change MUST trace to an
approved numbered specification. Work MUST proceed in the order `spec -> plan -> tasks -> tests ->
implementation -> verification`. If implementation and specification disagree, the drift MUST be
measured and either the implementation or the approved specification MUST be corrected. Issue text,
screenshots, generated reports, and current code behavior do not supersede an approved specification.

### II. Executed Evidence Defines the Claim

A result MUST state what actually executed, which artifact revision it tested, and what the evidence
does and does not support. Stored flags, generated prose, placeholders, synthetic scores, fixture
outputs, and successful parsing MUST NOT be presented as simulation, training, physical validation,
or task performance. Failures, timeouts, dependency errors, and unrun work MUST remain distinct.
Robotics claims MUST keep structural validity, compilation, simulator loading, static diagnostics,
controlled behavior, HIL, and physical evidence separate.

### III. Test First and Reproduce

Behavior changes MUST follow red-green-refactor: write one minimal test, observe the expected
failure, implement the minimum behavior, and observe the test pass before refactoring. Every accepted
evaluation result MUST identify its inputs, tool and simulator versions, parameters, seeds when
available, artifact digests, raw output, and error state. Deterministic graders MUST reproduce the same
grade from the same saved outcome. Nondeterministic claims MUST report repeated trials rather than one
preferred run.

### IV. Complexity Must Pay Rent

New abstractions, services, persistence layers, orchestration engines, simulators, queues, and cloud
resources MUST solve a demonstrated requirement that a simpler design cannot meet. Every plan MUST
name the strongest simpler alternative and explain why it fails. Prefer direct data structures and
two or three clear layers over indirection. Complexity is justified when it materially improves
correctness, robot-graph generality, reproducibility, evaluation power, or measured operating cost.
Speculative scale and aesthetic architecture are not justification.

### V. Preserve Architectural Boundaries

The product layer under `apps/` owns user workflows, API contracts, and product persistence. The
research layer under `packages/research/` owns strategies, agent loops, prompts, experiments, and
benchmarks. `packages/pipeline/` owns shared deterministic robot representations, compilers, and
simulation checks. Research MUST NOT import product code. Product code MAY import only the narrow
registered agent-loop surface from research. Changes to a shared IR, public API, schema, compiler
contract, registry, or core pipeline MUST update the configured architecture handoff document in the
same change.

### VI. Falsification Before Expansion

Every proposed product branch MUST name its buyer, recurring job, strongest agent-plus-tools
substitute, smallest working POC, measurable advantage, and kill conditions before implementation.
The first implementation MUST test the riskiest assumption, not build the broadest interface. A branch
that is reproduced in one day by a capable engineer and coding agent, catches no consequential error,
or lacks recurring use MUST be killed or retained only as open-source infrastructure. Hosted control
planes, enterprise administration, public leaderboards, and broad UX MUST wait until the local POC
beats the strongest substitute on decision quality, effort, or unique evidence.

## Product Discovery and Resource Constraints

- Local execution MUST be exhausted before paid deployment or compute is requested.
- Total external spend MUST remain at or below $200 unless the user explicitly raises the limit.
- A resource request MUST name the exact experiment, expected artifact, spend and time limits, stop
  condition, and decision the result changes.
- The concept tree MUST record parent-child relationships, evidence, kill reasons, and the next parent
  explored after a branch stops yielding useful hypotheses.
- The product MUST remain callable through ordinary files and command-line interfaces. A dashboard MAY
  review evidence, but MUST NOT become the sole path to reproduce a result.

## Development Workflow

1. Inspect the current repository and strongest external substitute.
2. Specify one falsifiable product or feature branch and obtain approval.
3. Produce the implementation plan, data model, contracts, quickstart, and dependency-ordered tasks.
4. Implement test-first, marking tasks complete only after their verification succeeds.
5. Run the POC against its substitute and record raw evidence, drift, complexity, cost, and kill result.
6. Refine only when the evidence identifies a specific correctable weakness.
7. Add adjacent concept branches as separate designs; do not silently mix their requirements.
8. Update `README.md` and the architecture handoff whenever the implemented product or architecture
   materially changes.

## Governance

This constitution governs all Spec Kit artifacts and implementation work in IL Ideation. Amendments
require an explicit rationale, a semantic version change, a sync-impact report, and propagation to
dependent templates. Compliance MUST be checked during planning, task generation, implementation, and
spec-drift review. A principle violation MUST either be removed or documented in the plan's complexity
tracking table with the rejected simpler alternative and approval evidence.

**Version**: 1.0.0 | **Ratified**: 2026-07-19 | **Last Amended**: 2026-07-19
