# Implementation Goal: Spec 011 POC

## Objective

Complete the dependency-ordered `tasks.md` for the Agentic Robot Design Evals POC, run the deterministic
and available live profiles, compare the evaluator against a minimal vibe-coded substitute, and record
an evidence-backed continue, refine, open-source, or kill decision.

## Source

- Requirements: `spec.md`
- Architecture and validation: `plan.md`, `data-model.md`, `contracts/`, `quickstart.md`
- Execution checklist: `tasks.md`

## Verification gates

1. Every task reference passes and seeded failure fails the intended assertion.
2. Isolation proves an agent child cannot read the repository or protected files.
3. Deterministic grades replay identically three times.
4. Live agent trials are real or explicitly unrun with exact blockers.
5. The strongest-substitute comparison records implementation effort and outcome differences.
6. Spec drift, complexity, spend, and product kill conditions are audited.

## Complete when

All required tasks are checked, focused tests pass, `poc-results.md` contains raw bundle paths and a
decision, and `concept-tree.md` identifies the next approved branch or parent node.
