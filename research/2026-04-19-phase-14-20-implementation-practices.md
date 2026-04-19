# Phase 14-20 Implementation Practices

This note is the technical companion to:

- [2026-04-18-agentic-simulator-roadmap.md](/Users/thorbthorb/Downloads/IL_ideation/plans/2026-04-18-agentic-simulator-roadmap.md)

It exists to prevent the next implementation phases from drifting into UI-only changes or prompt-only experimentation without measurable backend gains.

## Scope

This document covers the implementation practices for:

1. task-conditioned embodiment generation and ranking
2. hardrails for climbing, crawling, slippery-terrain, and related non-traditional actions
3. GLB-backed engineering rendering
4. Photon recipient setup and consent flow
5. anti-collapse generation diversity
6. dedicated design validation loop
7. YouTube/GVHMR -> DROID fallback and replay provenance

## Non-negotiable engineering rules

1. Write failing tests before changing production behavior.
2. Every phase must include both offline regression coverage and at least one real-boundary integration test.
3. The model layer is not trusted by default. Deterministic validators and rankers must sit around it.
4. UI controls must not be shown as active unless there is a real backend route and state transition behind them.
5. Saved artifacts, eval reports, and failure traces are required outputs, not optional debugging extras.

## Phase 14: Task-Conditioned Embodiment Generation and Ranking

### Problem

A generic morphology generator will produce visually plausible but task-wrong designs. The "rock climbing" failure is the canonical example: the current system can prefer a quadruped without a viable climbing mechanism because task semantics are too weak and ranking is too shallow.

### Required architecture

Split generation into four roles:

1. `TaskIntent -> TaskCapabilityGraph`
2. `TaskCapabilityGraph -> design drafts`
3. `design drafts -> critic / mutation loop`
4. `validated drafts -> deterministic ranking`

The final preferred candidate must never be selected directly from raw model output.

### Model practice

Use model specialization, not one universal prompt.

- `Gemini 2.5 Pro`
  - stable structured-output baseline
  - use for schema-constrained draft generation
- `Gemini Robotics-ER 1.6 Preview`
  - use for embodied task reasoning and affordance planning
  - do not use as a direct URDF/CAD emitter
- `Claude Opus 4.7`
  - use as critic/mutation agent for long-horizon design critique
- `GPT-5.1`-class models
  - use as evaluator/critic where available

### Best practice

Use at least two independent judgments in the loop:

1. generator/planner model
2. critic/evaluator model

This materially improves task-fit because the evaluator can reject designs that are structurally coherent but task-incoherent.

### TDD harness

Create:

- `research/design_eval_corpus/`
- `research/runs/design_eval/`

Minimum corpus contents:

- `rock_climb_payload.json`
- `crawl_low_pipe.json`
- `slippery_slope_transport.json`
- `ladder_climb_inspection.json`
- `stairs_bin_carry.json`
- at least 15 more prompts with expected affordances

Each corpus case must contain:

- task prompt
- normalized task tags
- required affordances
- rejected affordances
- expected preferred topology families
- known anti-patterns

### Required tests

1. unit tests
   - task parsing
   - capability graph extraction
   - feature normalization
2. integration tests
   - generator -> critic -> ranker
   - preferred candidate changes when affordance evidence changes
3. opt-in live model tests
   - provider-backed
   - persisted report artifacts

### Metrics to track

- task-fit score
- affordance coverage
- critic rejection rate
- compile success
- procurement completeness
- HITL override rate

### Save artifacts

Persist:

- raw model outputs
- normalized candidate objects
- critic reports
- ranking deltas
- final score breakdown

## Phase 15: Hardrails for Non-Traditional Actions

### Problem

Without explicit task-family hardrails, the system can choose designs that are mechanically incoherent for the requested action.

### Required architecture

Add:

- `TaskHardrailRegistry`
- `AffordanceRuleSet`
- `TerrainRiskProfile`
- `CandidateRejectionReason`

The hardrail layer sits between candidate generation and final ranking.

### Best practice

Hardrails must be explainable and task-family specific.

Examples:

- climbing
  - require grasping/adhesion/anchoring strategy
  - require COM and support-surface reasoning
- crawling
  - cap height
  - require low-profile movement assumptions
- slippery terrain
  - require traction/contact strategy
  - require stability or controlled-descent reasoning

### TDD harness

Create negative regression fixtures first.

Examples:

- `climb_reject_generic_quadruped.json`
- `crawl_reject_upright_humanoid.json`
- `slip_reject_tall_narrow_biped.json`

### Required tests

1. unit tests
   - task family classification
   - hardrail trigger logic
2. integration tests
   - rejected candidates cannot win ranking
   - hardrail explanations surface in API payloads
3. live eval tests
   - compare model output quality with and without hardrails

### Success condition

The system must explicitly say why a candidate failed, not merely give it a lower unexplained score.

## Phase 16: GLB-Backed Engineering Rendering

### Problem

Capsules and spheres are acceptable as concept placeholders. They are not acceptable as the inspection-grade representation for a robotics engineering workflow.

### Required architecture

The canonical inspection asset is:

- `render.glb`

And the canonical overlay metadata is:

- `ui_scene.json`

The viewer should render:

- mesh-backed engineering mode from GLB
- concept mode only as an explicit fallback

### Best practice

Keep rendering and selection bound to named nodes and metadata, not screen-space hacks.

Every selectable entity should resolve to:

- `design_id`
- `revision_id`
- `link_id`
- `joint_id`
- `component_id`

### Backend artifact contract

Every compiled candidate must register:

- `render.glb`
- `ui_scene.json`
- node map
- component ownership map
- optional overlay anchors

### Frontend practice

Use:

- `GLTFLoader`
- stable node names
- explicit engineering overlays

Required modes:

1. concept
2. engineering
3. joints
4. components
5. collision
6. sensors

### TDD harness

1. artifact tests
   - compile emits GLB manifest entry
2. loader tests
   - real GLB fixture loaded through the actual loader path
3. overlay tests
   - click target resolves to backend entity
4. screenshot tests
   - concept vs engineering mode are visually distinct

### Success condition

If GLB generation fails, the UI must declare degraded mode. It must not silently present primitives as if they were engineering assets.

## Phase 17: Photon Recipient Setup and Consent Flow

### Problem

Photon-backed HITL only works if there is a real recipient model, verified contactability, consent state, and explicit UI gating.

### Required architecture

Define:

- `NotificationTarget`
- `NotificationConsent`
- `NotificationVerification`

Do not treat a phone number as the only durable identity. Store provider-resolved identifiers separately.

### Best practice

The `send review poll` action must be disabled until all of the following are true:

1. Photon runtime configured
2. recipient exists
3. consent recorded
4. recipient verified
5. poll capability available

### TDD harness

1. unit tests
   - E.164 normalization
   - consent requirement
   - gating logic
2. HTTP-boundary tests
   - real payloads against a local test server
   - headers
   - path correctness
3. opt-in live tests
   - real verification message
   - real approval poll
   - persisted delivery metadata
4. browser tests
   - setup CTA visible when unconfigured
   - poll action disabled until verified

### Success condition

No Photon action can silently no-op. Every failure must surface as setup-required, delivery-failed, or capability-missing.

### Implementation note

The shipped pattern in this repo is:

1. backend persists a default Photon recipient in `workspace_store`
2. `GET /hitl/setup` returns provider readiness, current recipient, and `can_send`
3. `POST /hitl/setup` creates or updates the default recipient in `pending`
4. `POST /hitl/setup/confirm` promotes consent to `confirmed`
5. `POST /designs/{id}/tasks` with `send_review_poll` refuses to run unless the stored setup is confirmed or an explicit override exists
6. UI reads `api.hitl.getSetup()` on load and exposes the setup form inline in the task rail

This is the correct pattern because it keeps Photon as a transport, not the source of truth for design state, while preventing fake “send review poll” affordances in the UI.

## Phase 18: Anti-Collapse Generation Diversity

### Problem

Even a capable generator can start reusing the same robot family across different prompts. This is a quality failure because it hides prompt-insensitivity behind superficially plausible output.

### Required architecture

Add:

- `DesignNoveltySignature`
- `PromptConditioningFingerprint`
- `CandidateSimilarityMatrix`
- `CollapseDetectionReport`

### Best practice

Score both:

1. task-fit
2. prompt-sensitive diversity

The system should penalize duplicate families within one prompt batch and across recent workspace history unless there is explicit evidence that the repeated design is genuinely the best fit.

Because this repo now emits richer compiled render artifacts, the novelty signal must be geometry-aware. A design can be a duplicate even when topology text changes slightly if the compiled engineering profile is still the same family:

- same `task_geometry_profile`
- same dominant primitive composition
- same accessory pattern
- same material richness envelope

Conversely, cosmetic geometry differences must not fool the ranker into thinking two candidates are genuinely different if their affordance and topology signatures are unchanged.

### TDD harness

Create a diversity regression corpus with prompt pairs that should not converge to the same preferred design family.

Minimum examples:

- rock climbing with payload
- crawl under low pipe
- slippery downhill transport
- vessel inspection manipulator
- ladder-climbing inspector

### Required tests

1. unit tests
   - signature generation
   - similarity scoring
2. integration tests
   - duplicate candidate penalization
   - prompt-history-aware collapse detection
3. live eval tests
   - compare diversity before/after anti-collapse controls

### Success condition

The system must be able to explain:

- when two designs are near-duplicates
- why a repeated family was still selected, if it was selected

### Implementation note

The shipped anti-collapse pattern in this repo is geometry-aware and route-backed:

1. compile render payloads first for all three candidates
2. build a novelty signature from:
   - topology key
   - actuation band
   - `task_geometry_profile`
   - primitive composition
   - accessory node pattern
   - material count
3. compare candidates within the same batch
4. compare the batch against recent stored design contexts from `workspace_store`
5. apply diversity penalties only when:
   - the designs are materially similar
   - and the alternative is not meaningfully worse on task-fit
6. persist a machine-readable `collapse_report` so the reranking is explainable

This matters because topology-only diversity is too weak once the render system becomes richer. The generator can hide collapse behind minor parameter drift while still producing the same engineering family. The compiled artifact needs to participate in the diversity check.

## Phase 19: Dedicated Design Validation Loop

### Problem

Generation quality must be continuously validated against structure, exports, task constraints, simulation, and procurement. Without this, model changes remain anecdotal.

### Required architecture

Add:

- `DesignValidationReport`
- `ValidationLoopRun`
- `ValidationFailureCategory`
- `CounterexampleCorpus`

### Validation layers

1. structural completeness
2. hardrail compliance
3. export/compiler success
4. replay/simulation viability
5. procurement/manufacturing completeness
6. render richness and integrity
   - compiled mesh count
   - material count
   - task/geometry profile consistency
   - render artifact availability for the selected revision

### Best practice

Treat validation as a first-class research artifact.

Persist:

- machine-readable report
- human-readable summary
- failure categories
- links to candidate artifacts

Render validation is now part of this phase, not a side concern. If the app claims inspection-grade or engineering-grade rendering, the validation report must say exactly why that claim is justified.

### TDD harness

1. failing tests for known bad outputs first
2. typed report contract tests
3. report persistence tests
4. regression comparisons across generator revisions

### Success condition

No preferred candidate should reach the UI without a validation report explaining why it passed.

### Implementation note

The shipped Phase 19 pattern in this repo is revision-aware and artifact-backed:

1. every generated design revision immediately produces a typed `DesignValidationReport`
2. the report is persisted in two places:
   - `workspace_store` as a `validation_report` artifact
   - on disk under `research/runs/validation_loop/`
3. the report currently validates:
   - structural completeness
   - task / hardrail status
   - compiler outputs (`mjcf`, `render_glb`)
   - render richness (`mesh_node_count`, `material_count`, geometry profile)
   - simulation viability proxies from telemetry
   - procurement grounding and missing-item handling
4. procurement is intentionally graded to match the repo’s current maturity:
   - low confidence + missing critical items is a failure
   - high confidence with explicit custom placeholders is a warning, not a hard fail
5. checkpoint decisions regenerate the validation report on the new revision

This is the correct near-term pattern because it gives the workspace a durable, explainable quality gate without pretending the current compiler/procurement stack is already perfect.

## Phase 20: Motion-Source Orchestration and Replay Provenance

### Problem

YouTube/GVHMR and DROID are different source types. When YouTube fails due to timeout, auth, or quota, the system must degrade cleanly and still provide truthful replay semantics.

### Required architecture

Add:

- `MotionSourceSelector`
- `MotionSourceDecision`
- `ReplayArtifact`
- `ReplayProvenance`

### Best practice

Prefer:

1. YouTube + GVHMR when a strong human reference is available
2. DROID when YouTube fails or yields weak matches

Do not hide provenance. Every replay must say whether it came from:

- `youtube_gvhmr`
- `droid_episode`
- `droid_window`
- `simulated_policy`

Replay should also remain coupled to the compiled render revision. The viewer, overlays, and camera framing should resolve against named nodes from the current engineering artifact, not an unrelated placeholder model.

### TDD harness

1. local HTTP boundary tests for YouTube timeout/auth/quota failure
2. DROID fixture integration tests
3. replay artifact contract tests
4. UI contract tests for visible source labels and disabled-state logic

### Success condition

`record clip` must never pretend a static camera orbit is task playback. It must either:

- replay a real motion source
- replay simulated policy output
- or explicitly surface that no motion source exists

### Implementation note

This phase is now shipped in the repo with three concrete replay states:

1. `youtube_gvhmr`
   - inferred from persisted ingest state when a YouTube source URL exists and a GVHMR job has been dispatched
2. `droid_episode` / `droid_window`
   - sourced from persisted DROID fallback payloads and trajectory-window metadata
3. `unavailable`
   - explicit no-source state instead of fake playback claims

The critical practice change is that replay provenance is resolved from ingest/runtime persistence, not from UI assumptions or prompt text. That keeps `record clip` truthful even when upstream source selection degraded or partially completed.

## Real-Boundary Testing Policy

Mocks are allowed only for narrow unit tests. They are not sufficient to close a phase.

Minimum external-boundary verification by phase:

- Phase 14
  - opt-in live provider evals for at least one real model provider
- Phase 15
  - live eval comparison with hardrails on/off for at least one provider
- Phase 16
  - real GLB fixture load using the same runtime loader used in the app
- Phase 17
  - local HTTP boundary tests always
  - real Photon send/poll tests when credentials and recipient are available
- Phase 18
  - live diversity-eval comparison for at least one provider-backed generator
- Phase 19
  - saved validation reports for at least one live-provider corpus run
- Phase 20
  - local HTTP failure injection for YouTube path plus real DROID-format fixture retrieval

## Artifact Storage Policy

Save reports under:

- `research/runs/design_eval/`
- `research/runs/hardrail_eval/`
- `research/runs/render_verification/`
- `research/runs/photon/`
- `research/runs/diversity_eval/`
- `research/runs/validation_loop/`
- `research/runs/replay_eval/`

Each run should include:

- timestamp
- git SHA if available
- model/provider details where relevant
- input corpus case
- output summary
- failure category
- human-readable conclusion

## What Not to Do

1. Do not treat prompt tuning alone as a substitute for ranking and hardrails.
2. Do not claim engineering rendering when only primitives are displayed.
3. Do not expose Photon UI actions before recipient setup exists.
4. Do not accept passing tests that only validate synthetic mock objects for provider-backed integrations.
5. Do not accept repetitive design families across different prompts without explicit similarity reporting.
6. Do not treat YouTube timeout/auth failure as a terminal error if DROID fallback is available.
7. Do not present replay without visible source provenance.

## Immediate Next Implementation Order

1. Phase 14:
   - write failing design-eval corpus tests
   - implement `TaskCapabilityGraph`
   - add critic/ranker split
2. Phase 15:
   - add hardrail registry and negative regression suite
3. Phase 16:
   - define artifact contract for `render.glb` and `ui_scene.json`
   - write loader and overlay tests
4. Phase 17:
   - add recipient model and setup routes
   - add Photon gating tests and UI setup flow
5. Phase 18:
   - add novelty signatures and duplicate penalization tests
6. Phase 19:
   - add typed validation reports and persistence tests
7. Phase 20:
   - add motion-source selection, DROID fallback routing, and replay provenance tests

## Phase 16 Implementation Note: Compiled Rendering as a Contract

The key improvement in Phase 16 is architectural, not cosmetic.

Previous state:
- the frontend improvised robot visuals from candidate scalars
- the backend had no render artifact contract beyond MJCF text
- "3D" rendering was just local primitive synthesis

Current state:
- the backend emits a deterministic engineering render payload
- that payload includes:
  - `render_glb`
  - `ui_scene`
  - `engineering_ready`
- the frontend engineering/joints/components modes consume that compiled artifact instead of inventing geometry from scratch
- if the artifact is missing, the UI must explicitly degrade and say so

Why this matters:
- rendering is now coupled to backend design state
- revisions can regenerate the artifact and the UI will reflect the new compiled geometry
- the render path is testable at the real loader boundary using `GLTFLoader`
- this is the minimum viable bridge from design semantics to engineering inspection

Recommended practice going forward:
1. Treat every serious viewer mode as artifact-backed.
2. Keep concept mode freeform, but keep engineering modes compiled.
3. Add screenshot verification on top of loader verification for later phases.
4. When mesh fidelity improves, upgrade the compiler output, not the viewer contract.
