# Specification Quality Checklist: Agentic Robot Design Evals

**Purpose**: Validate that the revised product is understandable, testable, and honest before planning
**Created**: 2026-07-19
**Feature**: [spec.md](../spec.md)

## Product clarity

- [x] The first paragraph says exactly what the product does.
- [x] The spec says the AI agent creates or edits the robot and IL Ideation grades it.
- [x] The first buyer and recurring job are explicit.
- [x] Four concrete robotics use cases explain when the product is used.
- [x] The old robot-body workbench is explicitly rejected as the main product.

## Agentic-AI threat model

- [x] Codex, Claude Code, skills, plugins, MCPs, CAD agents, Isaac Sim, and ROS are treated as substitutes.
- [x] The complete model-plus-harness-plus-tool profile is the evaluation subject.
- [x] The spec explains why simulator validation and generic agent evals do not automatically justify this product.
- [x] The product has explicit kill conditions if an engineer and agent can reproduce its value.

## Requirement quality

- [x] No `[NEEDS CLARIFICATION]`, TODO, TBD, or pending markers remain.
- [x] Every functional requirement is testable.
- [x] Every success criterion is measurable.
- [x] User stories have concrete acceptance tests.
- [x] Executed results, estimates, agent claims, failures, and unrun states remain distinct.
- [x] Hard failures cannot be hidden by an aggregate score.
- [x] Protected graders, reference solutions, isolation, and leakage controls are specified.
- [x] Non-goals prevent premature cloud, simulator, IR, workflow, and enterprise layers.

## Robotics validity

- [x] Compilation, simulator load, static diagnostics, and task behavior remain separate.
- [x] The spec does not claim graph diversity or zero-control stability proves task suitability.
- [x] Controller, perturbation, cross-simulator, HIL, and physical evidence are acknowledged as later evidence levels.
- [x] The current repository's false or incomplete evidence paths are named directly.
- [x] The first slice requires known passing solutions and seeded robotics failures.

## Research and business readiness

- [x] Current agentic CAD, simulation, ROS, evaluation, and morphology prior art is documented.
- [x] The four-round red-team reaches an opinionated verdict.
- [x] Technical, substitution, scientific, customer, and moat gates are explicit.
- [x] The market is described as unvalidated rather than venture-scale by assumption.
- [x] The first 12-hour slice requires zero mandatory cloud spend.

## Validation notes

- Specification quality validation completed after the agentic-AI red team.
- Normative scope is limited to `spec.md`; `research.md` and `red-team/agentic-ai-audit.md` provide rationale and evidence.
- Planning, data model, contracts, and the deterministic implementation slice are complete. The live
  comparison, complete agent-plus-engineer substitute, and child-node implementation remain unrun.
