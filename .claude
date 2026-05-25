# IL Platform Context for Claude

## Mission
Build a platform that turns natural-language robot skill requests plus sourced video into reviewed, simulator-validated imitation-learning datasets for humanoid robots.

## Read This First
1. `plans/00-master-platform-plan.md`
2. The active phase document:
   - `plans/phase-01-foundation/implementation-discovery-and-validation.md`
   - `plans/phase-02-robot-and-task-ingest/implementation-discovery-and-validation.md`
   - `plans/phase-03-video-intelligence/implementation-discovery-and-validation.md`
   - `plans/phase-04-retargeting-and-simulation/implementation-discovery-and-validation.md`
   - `plans/phase-05-dataset-export-and-productization/implementation-discovery-and-validation.md`

If no active phase has been designated, start with Phase 01.

## Working Rules
- Treat the master plan as the source of truth for locked defaults.
- Preserve the following decisions unless the master plan is explicitly updated:
  web-first product, URDF-first ingest, humanoids, open-web discovery, full source mirroring, human review gate, cloud jobs, Isaac Lab / Isaac Sim, LeRobot-compatible export, no in-platform training in v1.
- Do not skip discovery work and write implementation code from an unresolved phase document.
- Prefer existing robotics and dataset conventions over inventing proprietary ones.
- Keep provenance, auditability, and review gates explicit in all specs and implementations.
- Separate these artifact types clearly:
  master plan, phase discovery doc, phase spec, implementation.

## Document Workflow
1. Read the master plan.
2. Read the current phase discovery document.
3. Refine unresolved decisions only within that phase’s scope.
4. Convert the phase discovery document into a separate phase spec when the exit criteria are satisfied.
5. Implement only from the phase spec, not directly from the discovery doc unless explicitly instructed.

## Output Expectations for Future Agents
- When refining a phase, keep the document focused on open decisions, discovery tasks, validation criteria, interfaces, and risks.
- When promoting a phase to a spec, reference the source phase discovery doc and restate the locked inputs.
- When implementing, preserve cross-phase contracts and keep artifact lineage intact.

## Research vs Product Engineering

This codebase has two distinct layers. Never conflate them.

**Product engineering** (`apps/`, `packages/pipeline/`) is the stable backend that the web
product and API depend on. Changes here must preserve existing contracts, go through migration,
and be safe for live users. `packages/pipeline/schemas.py` defines the canonical types
(`TaskIntent`, `RobotDesignCandidate`) shared across this boundary.

**Research** (`packages/research/`) is a self-contained experimentation layer. It never imports
from `apps/` and does not touch the Supabase production database. Researchers can iterate on
generation strategies, agent prompts, and benchmark methods here without affecting the product.
The entry points are the `GenerationStrategy` protocol and the CLI
(`python -m packages.research.cli`).

See `AGENTS.md` for the full architectural boundary rules before modifying either layer.

## Non-Negotiable Constraints
- Do not allow dataset export without human approval.
- Do not erase lineage between source video, extracted motion, retargeted trajectory, replay, and dataset export.
- Do not silently replace extracted motion with simulator-corrected trajectories.
- Treat mirrored third-party media as compliance-sensitive data with retention and deletion requirements.
