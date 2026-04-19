# Agentic Simulator Roadmap

Date: 2026-04-18
Repo: `/Users/thorbthorb/Downloads/IL_ideation`

Companion technical note:
- [research/2026-04-19-phase-14-20-implementation-practices.md](/Users/thorbthorb/Downloads/IL_ideation/research/2026-04-19-phase-14-20-implementation-practices.md)

## Objective
Turn the current app from a Gemini-driven concept generator with placeholder simulation and symbolic rendering into an agentic robotics compiler/simulator that is:
- standards-compliant enough for further iteration
- simulator-ready for MuJoCo and Isaac workflows
- grounded in real components and procurement data
- capable of producing buildable and printable outputs
- backed by a deterministic compiler/validator around the LLM

## Core Decisions
1. Canonical truth is a custom `RobotDesignIR`, not URDF, MJCF, USD, CAD, or BOM alone.
2. Structural/control interoperability standard is `URDF/Xacro + ros2_control`.
3. MuJoCo target is compiled `MJCF`, not ad hoc XML emitted directly by the LLM.
4. Isaac runtime target is `USD`, produced through URDF/MJCF importer workflow first.
5. Manufacturing target is parametric CAD via `CadQuery`, with `STEP` as the editable exchange format.
6. Printing target is `3MF` first, `STL` fallback.
7. Procurement target is a richer component/product structure with live vendor enrichment where possible.
8. The LLM proposes designs; deterministic code owns compilation, validation, export, and ranking.

## Current Repo Reality
### Design generation
- [design_generator.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/design_generator.py) uses Gemini to generate structured robot candidates.
- [schemas.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/schemas.py) defines the current custom task/design/BOM schemas.
- The design schema is custom. It is not an open robotics standard.

### Simulation artifacts
- [mjx_screener.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/mjx_screener.py) emits a lightweight placeholder MJCF-style asset for screening.
- [urdf_factory.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/urdf_factory.py) is mislabeled and emits `<mujoco>` XML rather than URDF.
- Current simulator artifacts are schematic, not production robot descriptions.

### Components and BOM
- [bom_generator.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/bom_generator.py) generates a coarse BOM from curated catalogs.
- BOM lines are partially grounded in real vendor identifiers, but the model is incomplete.
- Missing layers include transmissions, controller architecture, wiring, assembly hierarchy, and manufacturing distinctions.

### UI rendering
- [RobotGlyph.tsx](/Users/thorbthorb/Downloads/IL_ideation/apps/web/components/RobotGlyph.tsx) renders a stylized symbolic SVG glyph.
- [MorphologyViewer.tsx](/Users/thorbthorb/Downloads/IL_ideation/apps/web/components/MorphologyViewer.tsx) is an older simple viewer and is not the authoritative design-studio renderer.
- The main design studio is still symbolic rather than artifact-driven.

### Export
- There is no complete production export stack for MuJoCo, Isaac Sim, or 3D-print workflows.
- Current design routes mainly return render payloads and placeholder simulator text.

## Critical Gaps Discovered After The First UI Pass
These are blocking issues. No additional UI polish should proceed until these are addressed by backend-backed contracts.

1. UI currently outruns backend semantics.
   - Several visible controls can render without having a real backend action behind them.
   - This creates the appearance of capability without deterministic execution.

2. HITL exists visually, but not yet as a true design-mutation loop.
   - `Approve`, `Deny`, and `Guide` must not be cosmetic.
   - Every decision must create a durable approval event, mutate or branch a design revision, and trigger recompilation / re-ranking.

3. Task-conditioned design generation is still underconstrained.
   - A prompt like “rock climbing” currently does not force the model to reason explicitly about vertical locomotion, adhesion or gripping strategy, center-of-mass control, or climbing-specific end-effectors.
   - A generic quadruped without a climbing mechanism is not an acceptable “climbing robot”.

4. Rendering is still not engineering-grade.
   - Replacing lines with capsules and spheres is not enough.
   - The inspection view must render compiled geometry/meshes and expose engineering overlays, not just concept art in 3D.

5. Tasks are static labels, not agentic processes.
   - The Tasks panel must become a live process graph backed by real jobs:
     - proposal
     - mutation
     - compile
     - simulate
     - export
     - notify
   - It must also support user-triggered edits after render.

6. Photon is not fully operational until recipient onboarding exists.
   - The app needs an explicit setup flow for who to text, consent state, and runtime capability checks.
   - If Photon is not configured, the UI must surface setup, not silently no-op.

## Canonical Architecture
Use a layered model:
1. `TaskIntent`
2. `EmbodimentSpec`
3. `RobotDesignIR`
4. Standards compilers
5. Procurement/manufacturing compilers
6. UI scene compiler
7. Simulation screening and promotion
8. Export bundles

### Layer responsibilities
- `TaskIntent`: user goal, environment, payload, constraints
- `EmbodimentSpec`: topology family, limb inventory, sensor intent, module choices
- `RobotDesignIR`: canonical robot graph with links, joints, inertial placeholders, actuator slots, transmission slots, sensor slots, visual/collision proxies, custom part references, and assembly ownership
- Standards compilers: generate URDF/Xacro, ros2_control, MJCF, UI scene graph
- Manufacturing compiler: generate CAD assemblies and print exports
- Procurement compiler: resolve vendor parts, alternates, pricing, and unresolved lines
- Simulation services: MuJoCo screening for breadth, Isaac promotion for depth

## Multi-Step Roadmap

### Phase 0: Clean representation boundaries
Goal: remove misleading names and placeholder assumptions before adding more layers.

Actions:
1. Rename or replace [urdf_factory.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/urdf_factory.py) so nothing labeled URDF emits `<mujoco>`.
2. Mark [mjx_screener.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/mjx_screener.py) as a placeholder compiler/screener, not canonical geometry.
3. Restrict [design_generator.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/design_generator.py) to proposal generation, not direct export generation.
4. Treat [RobotGlyph.tsx](/Users/thorbthorb/Downloads/IL_ideation/apps/web/components/RobotGlyph.tsx) as concept-only rendering.

Acceptance:
- No file called URDF emits MJCF.
- Concept rendering is clearly separated from compiled artifact rendering.

### Phase 1: Introduce canonical IR
Goal: establish one source of truth for all downstream compilers.

Add:
- `packages/pipeline/ir/task_intent.py`
- `packages/pipeline/ir/embodiment.py`
- `packages/pipeline/ir/design_ir.py`
- `packages/pipeline/ir/components.py`
- `packages/pipeline/ir/export_manifest.py`
- `packages/pipeline/ir/design_revision.py`
- `packages/pipeline/ir/checkpoints.py`
- `packages/pipeline/ir/design_jobs.py`

Minimum models:
- `TaskIntent`
- `EmbodimentSpec`
- `RobotDesignIR`
- `AssemblyIR`
- `ExportManifest`
- `DesignRevision`
- `DesignDelta`
- `Checkpoint`
- `ApprovalEvent`
- `DesignJob`
- `TaskRun`

Refactor:
- Split or thin down [schemas.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/schemas.py).
- Make [design_generator.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/design_generator.py) output `EmbodimentSpec` or a lightweight draft, then deterministically compile to `RobotDesignIR`.

Acceptance:
- Every candidate serializes to `RobotDesignIR`.
- UI, BOM, URDF, and MJCF all derive from the same IR.
- Every post-generation edit becomes a new `DesignRevision` with a typed `DesignDelta`.

### Phase 2: Standards compilers
Goal: compile IR into real robotics artifacts.

Add:
- `packages/pipeline/compilers/urdf_compiler.py`
- `packages/pipeline/compilers/xacro_compiler.py`
- `packages/pipeline/compilers/ros2_control_compiler.py`
- `packages/pipeline/compilers/mjcf_compiler.py`
- `packages/pipeline/compilers/ui_scene_compiler.py`

Rules:
1. URDF/Xacro is the primary structure export.
2. `ros2_control` is emitted from actuator/sensor slots.
3. MJCF is separately compiled from IR for MuJoCo.
4. All compilers emit naming maps and validation reports.

Per-candidate outputs:
- `artifacts/<id>/robot.xacro`
- `artifacts/<id>/robot.urdf`
- `artifacts/<id>/ros2_control.xacro`
- `artifacts/<id>/robot.mjcf`
- `artifacts/<id>/ui_scene.json`
- `artifacts/<id>/render.glb`
- `artifacts/<id>/manifest.json`

Acceptance:
- URDF parses.
- MJCF parses.
- Link/joint names are stable across all exports.
- Isaac importer naming constraints are satisfied.
- A browser render asset is produced from the same compiled design, not from a separate fake viewer schema.

### Phase 3: Real component semantics
Goal: define components as a real multi-layer mechatronic model rather than a coarse BOM abstraction.

Replace the current coarse approach in [bom_generator.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/bom_generator.py) with layered component resolution.

Add:
- `packages/pipeline/components/slot_resolver.py`
- `packages/pipeline/components/catalog_models.py`
- `packages/pipeline/components/procurement_enricher.py`

Component categories:
1. Structural
2. Actuation
3. Transmission
4. Joint support
5. Electronics
6. Sensors
7. Wiring/power
8. Printed custom parts
9. Machined custom parts

Each joint resolves to:
- actuator
- transmission
- support hardware
- control interface

Each link resolves to:
- structural parts
- mass/inertia source
- custom vs vendor status

Acceptance:
- No joint exists without a component stack.
- No custom part is silently represented as a vendor part.

### Phase 4: Procurement stack
Goal: move from curated placeholders to supplier-grounded outputs.

Integrations:
- McMaster-Carr for mechanical hardware
- DigiKey for electronics
- Mouser as alternate electronics source
- PartCAD-style abstraction for internal product structure

Add:
- `packages/pipeline/procurement/providers/digikey.py`
- `packages/pipeline/procurement/providers/mouser.py`
- `packages/pipeline/procurement/providers/mcmaster.py`
- `packages/pipeline/procurement/quote_engine.py`

Outputs:
- `bom.json`
- `procurement.json`
- alternates
- unresolved lines
- datasheet/CAD links

Acceptance:
- Critical electronics resolve to real SKUs.
- Mechanical hardware resolves where possible.
- Custom items are explicitly tagged `manufacture_required`.

### Phase 5: CAD and printing
Goal: generate buildable custom parts and export manufacturing assets.

Use:
- `CadQuery` first
- `Onshape` later if collaborative CAD is needed

Add:
- `packages/pipeline/cad/cadquery_parts.py`
- `packages/pipeline/cad/assembly_builder.py`
- `packages/pipeline/cad/print_export.py`

Outputs:
- `assembly.step`
- `visual.glb` or `visual.gltf`
- `parts/*.step`
- `parts/*.stl`
- `parts/*.3mf`

Rules:
- Vendor parts remain references, not printable geometry.
- Only custom parts receive printable exports.

Acceptance:
- STEP opens in CAD.
- 3MF/STL open in the slicer.
- Custom parts are manifold.
- CAD assembly export is rich enough to drive an engineering render path via glTF/GLB.

### Phase 6: UI becomes artifact-driven
Goal: replace symbolic detail rendering with a compiled scene graph.

Refactor:
- [page.tsx](/Users/thorbthorb/Downloads/IL_ideation/apps/web/app/page.tsx)
- [RobotGlyph.tsx](/Users/thorbthorb/Downloads/IL_ideation/apps/web/components/RobotGlyph.tsx)
- [MorphologyViewer.tsx](/Users/thorbthorb/Downloads/IL_ideation/apps/web/components/MorphologyViewer.tsx)

New render modes:
1. Concept
2. Visual geometry
3. Collision geometry
4. Joints/axes/limits
5. Components
6. Sensors
7. Actuators
8. Procurement overlay

Data source:
- `ui_scene.json` generated from `RobotDesignIR`
- later `glTF` for higher-fidelity visuals
- `render.glb` generated from CAD/assembly export for the engineering view

Mandatory UI contracts:
- No visible control may be decorative in production.
- Every visible action button must map to a real route, websocket command, or job dispatch.
- The `Spec` tab must render compiled artifact data.
- The `Export` tab must render actual export readiness, artifacts, or blocking errors.
- Checkpoints must be generated from real `DesignDelta` objects, not template text.
- The Tasks pane must render real `DesignJob` / `TaskRun` rows and support user-triggered edits after render.
- `record clip` must run or replay task-specific motion, not merely orbit the camera around a static model.

Rule:
- `RobotGlyph` remains only for generation-state concept rendering.
- Detail mode must render from compiled artifact data.

Acceptance:
- The inspection studio matches the exported topology.
- Joint and link counts match MJCF/URDF.
- The engineering view uses compiled meshes or GLB assets with meaningful overlays.
- There are no static task/checkpoint/export placeholders in the production workspace.

### Phase 7: Agentic simulation loop
Goal: make the app a true design -> compile -> validate -> simulate -> rank system.

Agents/services:
1. `DesignAgent`
2. `Compiler`
3. `Validator`
4. `MuJoCoScreeningService`
5. `IsaacPromotionService`
6. `ProcurementAgent`
7. `HITLAgent`
8. `TaskOrchestrator`
9. `DesignMutationService`
10. `PlaybackService`

Simulation flow:
1. Gemini proposes 3 candidates.
2. Deterministic compiler builds IR and exports.
3. MuJoCo screening runs:
   - compile/load
   - static stability
   - reachability
   - short-horizon task sanity
4. Top 1-2 candidates are promoted to Isaac.
5. Scores are summarized for HITL.

Mutation flow:
1. A checkpoint is derived from a typed `DesignDelta`.
2. User selects `approve`, `deny`, or `guide`.
3. Backend stores an `ApprovalEvent`.
4. `DesignMutationService` creates a child `DesignRevision` or records an accepted delta.
5. Compiler re-runs on the current revision.
6. Telemetry, BOM, render assets, and rankings are recomputed.
7. The workspace swaps to the new revision with a diff trail.

Task execution flow:
1. User fires a task such as:
   - compare candidate B
   - increase reach by 20 cm
   - replace J2 actuator
   - export URDF
   - run climb sim
   - send review poll
2. `TaskOrchestrator` creates a `TaskRun`.
3. The task either mutates the current design, triggers simulation/export, or dispatches a human review action.
4. The Tasks pane updates live with status, logs, and resulting artifacts.

Playback requirement:
- `record clip` must run one of:
  - a reference-motion replay
  - a short rollout in MuJoCo/Isaac
  - a generated behavior clip for the requested task
- The clip must correspond to the user’s requested action, not generic idle motion.

Do not start with full RL on all 3 candidates.
Start with compile/load and short-horizon screening.

Acceptance:
- All 3 candidates compile.
- Top candidate passes MuJoCo and Isaac import/load.
- Ranking is backed by deterministic artifacts and reproducible metrics.
- HITL decisions visibly alter the current design revision.
- Task runs are live backend jobs, not static UI rows.

### Phase 8: Export routes and bundles
Goal: expose real export artifacts through the backend.

Add:
- `demo/routes/exports.py`
- extend [designs.py](/Users/thorbthorb/Downloads/IL_ideation/demo/routes/designs.py)

API candidates:
- `POST /designs/{id}/compile`
- `GET /designs/{id}/artifacts`
- `POST /designs/{id}/export/mujoco`
- `POST /designs/{id}/export/isaac`
- `POST /designs/{id}/export/print`
- `GET /designs/{id}/procurement`
- `GET /designs/{id}/spec`
- `GET /designs/{id}/exports`
- `GET /designs/{id}/checkpoints`
- `POST /designs/{id}/checkpoints/{checkpoint_id}/decision`
- `GET /designs/{id}/tasks`
- `POST /designs/{id}/tasks`
- `POST /designs/{id}/record-clip`

Bundle definitions:
- MuJoCo bundle:
  - `robot.mjcf`
  - meshes
  - manifest
- Isaac bundle:
  - `robot.urdf`
  - meshes
  - importer config
  - optional generated USD path
- Print bundle:
  - `assembly.step`
  - `parts/*.3mf`
  - `parts/*.stl`
  - print manifest

Acceptance:
- MuJoCo bundle loads.
- Isaac bundle imports.
- Print bundle opens in slicer/CAD.
- `Spec` and `Export` UI panels are backed by these routes and show real data/errors.

### Phase 9: Operational intelligence and HITL telemetry
Goal: make approval prompts, budget context, and robot attributes first-class outputs that can drive better human review.

Add:
- price estimation for each candidate and each major BOM delta
- key robot attributes in the approval surface:
  - weight / mass
  - payload
  - reach
  - joint torque / speed envelope
  - stiffness / backlash / bandwidth
  - stability / complexity / part availability
  - export readiness
- alert tailoring rules so HITL prompts are generated from the current design deltas rather than generic text
- checkpoint synthesis rules so approval cards are built from actual diffs:
  - actuator substitution
  - payload budget shifts
  - reach envelope changes
  - export regressions
  - procurement cost deltas
  - simulation failures or warnings

Acceptance:
- approval dialogs can show a concise engineering delta summary
- alerts can be filtered or prioritized by price, weight, risk, or task mismatch
- the data contract for approvals is stable and versioned
- no checkpoint card is allowed to render without a real backend delta source

### Phase 10: Photon iMessage workflow
Goal: add a concrete iMessage-based HITL path with polls for approval and clarification.

Research-backed product assumptions:
- Photon Spectrum exposes an iMessage API and supports `sendPoll` for iMessage polls.
- The current Photon site explicitly shows iMessage poll support and a messaging SDK built on Spectrum.
- iMessage remote/local SDK behavior is different; poll support is limited to the Photon/remote path in the adapter docs, so the implementation must be explicit about which runtime is used.

Add:
- a Photon integration module for sending text messages
- poll generation for approval / clarification loops
- message templates for:
  - approve / deny / guide
  - budget confirmation
  - actuator substitution
  - procurement clarification
- webhook or polling-based message ingestion for replies
- a dedicated HITL conversation state machine

Implementation requirements:
- use Photon only for human-facing approval questions, not as the source of truth for robot state
- store each poll as a durable approval event in the backend
- support one-click approval and one-click clarification loops
- support remote-mode Photon / Spectrum as the production path for polls
- do not rely on Photon local mode for poll support

Recipient onboarding requirements:
- add a recipient onboarding flow before any poll can be sent
- support entry of an iMessage destination in the format the provider expects:
  - phone number in normalized E.164 where appropriate
  - or Apple ID / platform-specific identifier when that is the active route
- store recipient config in a backend `NotificationTarget` model with:
  - `user_id`
  - `channel`
  - `recipient_id`
  - `consent_at`
  - `verified_at`
  - `last_delivery_status`
  - `capabilities`
- add a setup test action:
  - send a plain text verification ping
  - then enable poll-based HITL only after confirmation
- if Photon credentials or recipient config are missing, the UI must show setup required rather than silently failing

Acceptance:
- backend can send an iMessage poll asking a robot-selection question
- backend can receive the response and resume the approval flow
- every poll is tied to a concrete design delta
- the UI has a visible path to configure who receives HITL messages
- `send review poll` is not shown as active unless Photon runtime and recipient setup are complete

### Phase 11: Visual language refinement
Goal: tighten the UI into a more squared, IDE-like system while keeping the dark industrial look.

Style requirements:
- reduce corner curvature across the whole frontend
- make the activity pane feel more like a coding IDE with softer grid lines and more tiled structure
- preserve the current black-heavy palette
- retain the current generative/studio feel, but make panels more squared and deliberate

Source-of-truth design input:
- use the provided `AutoBot Cowork v2.html` design artifact as the style reference
- extract only the relevant visual language, not the entire product concept

Acceptance:
- the activity pane reads like a structured IDE timeline rather than a generic feed
- component radii are visibly reduced across the app
- the dark palette stays coherent with the current workspace design

### Phase 12: Robot design quality and prompting research
Goal: improve the actual generated robot concepts so they are physically plausible, task-aligned, and not obviously overfit humanoids or absurd multi-legged solutions.

Add research and evaluation around:
- better prompt families for sophisticated but cleaner robot concepts
- model limitations versus prompt limitations versus agent-harness limitations
- more capable foundation models for design generation
- physics-aware design constraints
- architecture options for multi-agent design generation and critique
- domain priors for task families such as climbing, heavy-payload transport, slope descent, manipulation, and inspection

Hard requirement: task-conditioned affordance reasoning
- Introduce a `TaskCapabilityGraph` derived from the user prompt.
- The generator must infer and score required capabilities such as:
  - vertical locomotion
  - adhesion / claw / microspine / suction compatibility
  - dual-arm grasping
  - payload placement
  - center-of-mass management
  - terrain contact strategy
  - fall recovery
- Candidate morphologies must be rejected if they do not satisfy task-critical capabilities.
- Example:
  - a “rock climbing” query must not default to a generic quadruped unless the design explicitly includes a climbing mechanism and the system can justify it against the task.

Required prompt work:
- produce 2 to 3 stronger task-conditioned prompts that generate cleaner, more feasible concepts
- make the model explicitly reason about:
  - stability
  - kinematic plausibility
  - payload placement
  - contact geometry
  - actuation burden
  - manufacturability

Model/harness evaluation requirements:
- Benchmark the current Gemini 2.5 Pro generation path against stronger or complementary models where available:
  - Gemini 2.5 Pro as the current structured-output baseline
  - Claude Opus 4.7 / Opus 4.6-class reasoning agents for longer-horizon design critique and mutation planning
  - OpenAI GPT-5.1-class reasoning models for structured engineering analysis where available in deployment
  - Gemini Robotics-ER 1.5 for embodied task decomposition and physical-scene reasoning, not direct CAD emission
- Use an evaluator harness that measures:
  - task-fit
  - morphology plausibility
  - simulation viability
  - exportability
  - procurement grounding
  - HITL preference
- The harness must separate:
  - prompt failure
  - model failure
  - compiler failure
  - renderer failure

Climbing-specific design requirements from literature:
- For climbing robots, the plan must explicitly model the attachment mechanism and structural posture, since climbing systems depend on specialized adhesion or gripping strategies rather than generic leg count alone.
- Vertical/rough-wall climbing candidates should reason about claw, microspine, suction, magnetic, or dry-adhesion end-effectors depending on the target surface.

Evaluation requirements:
- compare candidate quality across designs using task-fit and feasibility, not visual novelty alone
- identify when failures come from the model, the prompt, or the harness

Acceptance:
- the system can explain why a poor design is poor
- the system can compare prompt variants for design quality
- the system can reject absurd but visually striking geometries
- a query like “rock climbing while carrying a pack” yields candidates with explicit climbing affordances and justifications
- the render path can show a useful engineering model, not just capsules and spheres

### Phase 13: DROID fallback integration
Goal: add a fallback trajectory source that is not treated like generic web video.

Core decision:
- DROID is a trajectory-retrieval backend, not a YouTube-style video backend.
- The app should retrieve episodes or trajectory windows with aligned language, state, action, and camera data.

Required research questions for the next agent:
- official RLDS format
- raw DROID episode format
- Hugging Face / LeRobot DROID mirror format
- what metadata should be indexed for retrieval
- whether text, motion, or visual embeddings are actually needed

Implementation target:
- fallback retrieval should return a compact demonstration object with:
  - episode id
  - task language
  - action/state pointers
  - optional camera/video pointers
  - confidence / match score
  - retrieval rationale

Acceptance:
- fallback selection can hand downstream code a trajectory reference without pretending it is the same source type as YouTube/GVHMR
- the retrieval layer remains structured and queryable

### Phase 14: Task-conditioned embodiment generation and ranking
Goal: replace generic morphology guessing with a reproducible, measured generation-and-ranking pipeline that is explicitly conditioned on task mechanics and embodiment affordances.

Core architecture:
- split generation into distinct backend steps:
  1. `TaskIntent -> TaskCapabilityGraph`
  2. `TaskCapabilityGraph -> candidate design drafts`
  3. `candidate design drafts -> critic / mutation loop`
  4. `candidate design drafts -> deterministic ranking`
- use different model roles rather than one undifferentiated prompt:
  - primary structured generator
  - affordance planner
  - critic / failure analyzer
  - evaluator

Model strategy:
- keep `Gemini 2.5 Pro` as the stable structured-output baseline because the official model docs position it as the advanced complex-task model with structured outputs and long context.
- evaluate `Gemini Robotics-ER 1.6 Preview` as an embodied-reasoning planner, not as a direct CAD or URDF emitter.
- evaluate `Claude Opus 4.7` as a high-end critique / mutation / long-horizon agent model; Anthropic’s current model overview lists it as the most capable generally available reasoning and agentic coding model.
- evaluate `GPT-5.1`-class models as a structured evaluator/critic path where available; the OpenAI GPT-5 docs explicitly recommend the newer GPT-5.1 family over GPT-5.

Hard requirement:
- the model layer must be benchmarked, not chosen by intuition.
- every generator change must land with offline and live eval evidence.

TDD process:
1. Build a `design_eval_corpus/` with at least 20 task prompts:
   - vertical climbing with payload
   - crawling under constrained clearance
   - walking on slippery incline
   - stair ascent with bin
   - ladder climbing
   - pipe inspection
   - vessel-entry manipulation
   - heavy object downhill transport
2. Write failing task-fit tests first:
   - each prompt must produce 3 candidates
   - each candidate must include explicit task-fit evidence
   - ranking must not prefer a candidate that fails task-critical affordances
3. Add golden regression tests for known failures:
   - “rock climbing while carrying a rope pack” must not produce a generic non-climbing quadruped as the preferred design unless it explicitly contains a climbing mechanism and support analysis
   - “crawl under a low pipe” must strongly penalize tall torso geometries
   - “slippery slope transport” must force traction/contact strategy reasoning
4. Add live-provider eval tests behind opt-in env flags:
   - run the same prompt corpus against:
     - Gemini 2.5 Pro
     - Claude Opus 4.7 if available
     - GPT-5.1 if available
     - Gemini Robotics-ER 1.6 as planner if available
   - persist results under `research/runs/design_eval/`
5. Compare:
   - task-fit score
   - affordance coverage
   - plausibility score
   - compilation success
   - procurement completeness
   - HITL preference score

Verification:
- unit tests for `TaskCapabilityGraph` extraction
- integration tests for generator -> critic -> ranker pipeline
- opt-in live model tests against real provider APIs
- saved evaluation reports with per-model deltas and failure categories

Acceptance:
- model choice is justified by stored eval reports, not anecdote
- every preferred candidate includes explicit capability reasoning
- the system can explain why rejected candidates failed task-fit
- the preferred design changes when affordance coverage changes

### Phase 15: Hardrails for non-traditional actions and terrain
Goal: encode domain-specific task constraints so the system rejects obviously wrong morphologies before they reach the UI.

Scope:
- climbing
- crawling
- slippery terrain locomotion
- constrained-clearance motion
- payload transport on unstable ground

Add:
- `TaskHardrailRegistry`
- `AffordanceRuleSet`
- `TerrainRiskProfile`
- `CandidateRejectionReason`

Hardrail examples:
- climbing:
  - require explicit attachment/grasping/adhesion strategy
  - require COM management and vertical support reasoning
  - require end-effector or foot design suitable for the target surface class
- crawling:
  - cap torso height
  - prefer low profile and prone/compact geometries
  - reject high-COM standing morphologies for strict clearance tasks
- slippery terrain:
  - require traction/contact strategy, stance-width reasoning, or controlled descent strategy
  - reject speculative narrow-footed tall platforms without compensation

TDD process:
1. Write a negative test suite first.
   - inputs that must be rejected:
     - rock climbing -> generic quadruped with no climbing mechanism
     - slippery slope -> tall thin biped with no traction strategy
     - crawlspace task -> full-height humanoid with upright torso
2. Write structured hardrail tests:
   - each task family produces required capability flags
   - each candidate is validated against those flags
3. Add scoring tests:
   - hardrail violations reduce score below acceptance threshold
   - severe violations produce explicit rejection, not just minor penalties
4. Add scenario-level integration tests:
   - generator produces 3 candidates
   - validator rejects/penalizes bad ones
   - ranker cannot choose a rejected candidate
5. Add literature-backed fixtures:
   - climbing surfaces and adhesion modes
   - slope/slip contact constraints
   - crawl clearance envelopes

Verification:
- offline regression suite for all non-traditional task families
- per-candidate explanation traces showing which hardrails fired
- live model evals confirm the hardrail layer actually improves preferred-candidate quality

Acceptance:
- impossible or weakly justified candidates are rejected before ranking
- each non-traditional task has explicit capability requirements in code
- system exposes rejection reasons to HITL and logs

### Phase 16: GLB-backed engineering rendering
Goal: replace the current primitive capsule/sphere aesthetic with compiled, inspection-grade engineering rendering driven by exported assets.

Target rendering stack:
- canonical mesh/runtime asset: `glTF 2.0` / `.glb`
- browser loader: `GLTFLoader`
- engineering overlays from `ui_scene.json`
- concept mode remains available, but inspection mode must be mesh-backed

Why this format:
- Khronos positions glTF as the runtime 3D asset delivery format and notes that `.glb` can package scenes, nodes, meshes, materials, textures, skins, and animations.
- Three.js `GLTFLoader` is the obvious browser path for this repo’s frontend stack.

Required backend outputs:
- `render.glb`
- `ui_scene.json`
- material map and mesh metadata
- named overlay anchors for:
  - joints
  - actuators
  - sensors
  - collision proxies
  - component ownership

Required frontend capabilities:
- render compiled GLB in inspection mode
- overlay component metadata on selected links/joints
- view modes:
  - concept
  - engineering mesh
  - joints
  - components
  - collision
- camera presets for:
  - orthographic engineering view
  - exploded/component view
  - task playback camera

TDD process:
1. Write artifact contract tests first:
   - every compiled design produces `render.glb`
   - GLB path is registered in export/spec responses
2. Write loader tests:
   - use a real GLB fixture and load it with the same browser/runtime path used by the app
   - verify scene contains named nodes and expected mesh count
3. Write overlay tests:
   - joint metadata must resolve to visible overlay anchors
   - component click targets must map back to backend component/spec IDs
4. Write regression tests for degraded mode:
   - if GLB is missing, app must explicitly show degraded concept mode rather than silently pretending it is engineering render mode
5. Add visual verification:
   - browser screenshot tests comparing concept vs engineering mode
   - at least one saved screenshot per candidate in CI artifacts or local verification artifacts

Verification:
- unit tests for asset manifest generation
- integration tests for GLB export registration
- real loader tests using GLTFLoader-compatible assets
- browser screenshot verification on the rendered scene

Acceptance:
- engineering mode is backed by GLB, not primitives
- component selection operates on real mesh/node metadata
- degraded mode is explicit and detectable

### Phase 17: Photon recipient setup and consent flow
Goal: make Photon usable in production by adding real recipient onboarding, consent, verification, and UI gating before polls/messages are available.

Core recipient model:
- `NotificationTarget`
  - `id`
  - `channel`
  - `provider`
  - `recipient_id`
  - `display_name`
  - `phone_e164` when applicable
  - `consent_at`
  - `verified_at`
  - `capabilities`
  - `last_delivery_status`

Important architectural note:
- Photon/Spectrum is a messaging runtime built around `Space`, `Message`, and `User`.
- the app must not assume “phone number only” is always the canonical identifier.
- UI may start from phone/email entry, but backend must store the provider-resolved recipient identity.

Required UX:
- setup panel or modal in the workspace
- recipient input and validation
- explicit consent capture
- verification message / ping flow
- capability detection:
  - text available
  - poll available
  - reply handling available
- `send review poll` disabled until setup is complete

TDD process:
1. Write validation tests first:
   - malformed phone/recipient rejected
   - consent required before activation
   - missing Photon config surfaces setup-needed state
2. Write setup-flow tests:
   - create recipient
   - send verification ping
   - mark verified on success
3. Write real HTTP-boundary tests:
   - outbound message and poll payloads against a local HTTP test server
   - auth headers
   - path correctness
4. Write opt-in live Photon tests:
   - with real `PROJECT_ID` / credentials / test recipient
   - send a real verification text
   - send a real approval poll
   - persist message IDs and statuses under `research/runs/photon/`
5. Write UI integration tests:
   - when recipient missing, `send review poll` is disabled and setup CTA is shown
   - when verified, action becomes available and visible status is rendered

Verification:
- unit tests for recipient normalization and consent rules
- integration tests for outbound transport payloads
- opt-in real Photon tests
- browser/UI tests for setup gating and verified state

Acceptance:
- app exposes an explicit recipient setup flow
- Photon actions cannot silently no-op
- review polls/messages are only enabled when setup and verification are complete
- delivery state is visible in the UI

### Phase 18: Anti-collapse generation diversity and prompt-sensitive design variation
Goal: prevent the generator from recycling the same robot family across materially different prompts and force prompt-sensitive embodiment diversity.

Problem to solve:
- the system can converge on one visually familiar design family and keep reusing it across unrelated prompts
- this is a model/harness failure, not just a UI issue

Add:
- `DesignNoveltySignature`
- `PromptConditioningFingerprint`
- `CandidateDiversityConstraint`
- `PriorDesignMemory`
- `CollapseDetectionReport`

Required behavior:
- prompts with materially different task mechanics must not return near-identical preferred designs unless the system can justify the convergence with explicit capability reasoning
- the ranker must balance:
  - task-fit
  - feasibility
  - procurement grounding
  - novelty relative to other candidates for the same prompt
  - prompt-sensitivity relative to prior prompts in the same project

Implementation techniques:
- compute topology/affordance/component signatures for every candidate
- compute geometry/render signatures from compiled artifacts:
  - `task_geometry_profile`
  - `mesh_node_count`
  - `material_count`
  - `primitive_keys`
  - accessory/component node mix
- penalize near-duplicate candidates within the same prompt batch
- track preferred-design signatures across prompts in the workspace
- add contrastive generation instructions:
  - candidate A = conservative baseline
  - candidate B = alternate embodiment strategy
  - candidate C = higher-risk but task-grounded variant
- maintain a memory of recent design families to discourage lazy repetition

TDD process:
1. Build failing regression cases where different prompts currently collapse to the same morphology family.
2. Add signature tests:
   - different task families should produce materially different capability signatures
   - candidate sets for one prompt should not collapse to the same topology with cosmetic changes only
3. Add ranking tests:
   - when two candidates are nearly identical, the duplicate is penalized unless it has materially better task-fit
4. Add longitudinal workspace tests:
   - running successive prompts in one session should not keep surfacing the same preferred design family without explicit justification
5. Add opt-in live model evals:
   - compare diversity and task-fit before/after anti-collapse controls
   - persist reports under `research/runs/diversity_eval/`

Verification:
- offline duplicate-detection regression suite
- saved similarity matrices for candidate batches
- live provider eval reports showing reduced collapse without reduced task-fit

Acceptance:
- the system can detect and explain when designs are near-duplicates
- different task prompts do not silently collapse to the same preferred morphology family
- diversity pressure does not override hard task-fit constraints
- diversity analysis distinguishes topology duplication from render/geometry duplication

### Phase 19: Design validation loop and research harness
Goal: create a dedicated validation loop for generated designs so model output is continuously checked against physics, exports, procurement, and task realism.

Problem to solve:
- generation quality cannot be trusted from prompt output alone
- validation logic must be a first-class subsystem with saved research outputs for learning and debugging

Add:
- `DesignValidationReport`
- `ValidationFailureCategory`
- `ValidationLoopRun`
- `CounterexampleCorpus`

Validation layers:
1. structural validation
   - IR completeness
   - joint/link consistency
2. compiler validation
   - URDF/MJCF/GLB/export generation success
   - render artifact richness and integrity:
     - non-trivial mesh count
     - material richness
     - geometry profile consistency with task family
3. task validation
   - affordance coverage
   - hardrail compliance
4. simulation validation
   - screening/load success
   - replay viability
5. procurement/manufacturing validation
   - critical components resolved
   - custom parts identified cleanly

Research requirement:
- every meaningful generation change must produce a stored validation report so model/harness failures can be studied later
- this phase is explicitly for learning purposes, not just pass/fail gating

TDD process:
1. Write failing validation tests for known bad outputs:
   - task-incoherent design
   - export-incoherent design
   - procurement-incomplete design
2. Add validator contract tests:
   - every candidate yields a typed validation report
   - reports include failure categories and actionable reasoning
3. Add research artifact tests:
   - successful runs persist reports under `research/runs/validation_loop/`
4. Add regression suites that compare generator revisions over time
5. Add opt-in live model validation runs for the evaluation corpus

Verification:
- unit tests for every validator stage
- integration tests for full candidate -> validation report flow
- stored validation artifacts with human-readable summaries and machine-readable JSON

Acceptance:
- no preferred candidate reaches the UI without a validation report
- validation results can distinguish model failure from compiler failure from simulation failure
- validation artifacts are persisted for technical learning and postmortem review
- validation reports include render-quality findings so engineering-grade claims are testable

### Phase 20: Motion-source orchestration and replay semantics
Goal: make YouTube/GVHMR and DROID work as an explicit source hierarchy so timeout/auth failures degrade cleanly and task playback always has a real motion provenance.

Core decision:
- DROID is the preferred structured fallback when the YouTube path fails due to timeout, auth, quota, or no high-confidence human reference result
- the app must not pretend DROID and YouTube/GVHMR are the same source type

Add:
- `MotionSourceSelector`
- `MotionSourceDecision`
- `ReplayArtifact`
- `ReplayProvenance`

Required source selection behavior:
1. try YouTube + GVHMR when:
   - search succeeds
   - auth/quota is healthy
   - a strong human reference is found
2. immediately fall back to DROID when:
   - YouTube request times out
   - YouTube auth/quota errors occur
   - no strong reference survives quality filters
3. surface source provenance in the workspace:
   - `youtube_gvhmr`
   - `droid_episode`
   - `droid_window`
   - `simulated_policy`

Replay requirement:
- `record clip` must run one of:
  - GVHMR-derived replay
  - DROID trajectory replay
  - simulated policy playback
- it must never degrade to a camera orbit or static viewport animation while claiming task playback
- replay output must stay compatible with the richer engineering geometry path:
  - camera framing and overlays target compiled mesh/node names
  - replay provenance binds to the rendered revision

TDD process:
1. Write failing route tests for YouTube timeout/auth/quota errors.
2. Add source-selection tests:
   - timeout -> DROID
   - auth failure -> DROID
   - weak-match -> DROID
   - strong-match -> YouTube/GVHMR
3. Add replay artifact tests:
   - every playback request returns explicit provenance and source references
4. Add integration tests using real local HTTP failure servers for the YouTube boundary and real indexed DROID fixtures for fallback retrieval
5. Add UI contract tests:
   - playback source label is visible
   - fallback state is visible
   - replay controls are disabled only when no source exists

Verification:
- route-level timeout/auth fallback regression tests
- DROID retrieval integration tests on real stored fixtures
- saved replay artifacts under `research/runs/replay_eval/`

Acceptance:
- YouTube auth/timeout failures no longer surface as dead-end ingest failures when DROID can satisfy the request
- `record clip` always exposes a truthful replay provenance
- DROID is treated as a structured trajectory backend, not as a fake video substitute

Implementation status:
- shipped
- the current repo distinguishes:
  - `youtube_gvhmr`
  - `droid_episode`
  - `droid_window`
  - `unavailable`
- replay provenance is resolved from persisted ingest/runtime state rather than prompt text or UI-only assumptions

## Repo-Specific File Plan
### Create
- `packages/pipeline/ir/*`
- `packages/pipeline/compilers/*`
- `packages/pipeline/components/*`
- `packages/pipeline/procurement/*`
- `packages/pipeline/cad/*`
- `packages/pipeline/validation/*`
- `demo/routes/exports.py`

### Refactor heavily
- [design_generator.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/design_generator.py)
- [schemas.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/schemas.py)
- [bom_generator.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/bom_generator.py)
- [mjx_screener.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/mjx_screener.py)
- [page.tsx](/Users/thorbthorb/Downloads/IL_ideation/apps/web/app/page.tsx)

### Deprecate or remove
- [urdf_factory.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/urdf_factory.py) as currently named
- symbolic detail-mode dependence on [RobotGlyph.tsx](/Users/thorbthorb/Downloads/IL_ideation/apps/web/components/RobotGlyph.tsx)

## Acceptance Gates
1. IR gate
   - A candidate compiles to `RobotDesignIR` and serializes cleanly.
2. Standards gate
   - URDF and MJCF parse and load.
3. UI gate
   - The detail view matches the compiled topology.
   - No major control in the workspace is decorative or backend-free.
4. Procurement gate
   - Critical items resolve to real SKUs or explicit manufacturing placeholders.
5. CAD gate
   - Custom parts export to STEP and 3MF/STL.
6. Simulation gate
   - Top candidate survives staged screening.
7. Export gate
   - One-click MuJoCo, Isaac, and print bundles are produced.
8. HITL gate
   - approvals can surface price, mass, torque, payload, and other key deltas.
   - approve / deny / guide create durable design decisions and mutate or branch the current design.
9. Messaging gate
   - Photon can send and receive poll-driven iMessage approvals.
   - recipient onboarding, consent, and verification are complete.
10. Fallback gate
   - DROID retrieval is available as a structured non-video fallback source.
11. Task runtime gate
   - Tasks pane shows real job execution, logs, and resulting artifacts.
12. Playback gate
   - `record clip` produces task-matched playback rather than a generic viewport animation.
13. Model-eval gate
   - embodiment generator changes must ship with saved offline and, when configured, live provider eval reports.
14. Hardrail gate
   - non-traditional task families reject or heavily penalize candidates that miss required affordances.
15. Graphics gate
   - engineering render mode is GLB-backed and verified by loader + browser visual checks.
16. Photon onboarding gate
   - user cannot send a Photon review poll without a verified recipient and visible consent state.
17. Diversity gate
   - materially different prompts do not silently recycle the same preferred morphology family.
18. Validation-loop gate
   - every preferred candidate has a persisted validation report with categorized failures and reasoning.
19. Motion-source gate
   - timeout/auth/quota failures on YouTube trigger DROID fallback when available, and playback provenance is visible.

## Recommended Implementation Order
1. Canonical IR
2. Design revision / checkpoint / task-run models
3. Task-conditioned embodiment generation and ranking harness
4. Hardrail registry for non-traditional task families
5. URDF/Xacro + ros2_control compiler
6. MJCF compiler
7. Validation suite
8. MuJoCo screening and short-horizon playback
9. Procurement enrichment
10. CAD, GLB, and print export
11. Export/spec/checkpoint/task routes
12. Artifact-driven renderer and engineering overlays
13. HITL mutation loop
14. Photon onboarding, recipient setup, and poll integration
15. Anti-collapse diversity controls
16. Dedicated validation loop and research harness
17. Operational telemetry and price estimation
18. UI styling refinement
19. Motion-source orchestration and replay semantics
20. Isaac promotion
21. DROID fallback integration

## What Not To Do First
1. Do not make USD the canonical source of truth.
2. Do not let the LLM emit URDF/MJCF directly.
3. Do not start with full RL training on all 3 candidates.
4. Do not treat the current curated BOM catalogs as sufficient procurement grounding.
5. Do not keep the mislabeled URDF path alive indefinitely.
6. Do not treat DROID as if it were the same source type as YouTube/GVHMR.
7. Do not make Photon the source of truth for design state; it is only a messaging/HITL channel.
8. Do not ship polished UI controls that are not wired to backend actions.
9. Do not treat a primitive capsule/sphere viewer as an acceptable engineering render path.
10. Do not allow task-critical affordances like climbing adhesion or grasp strategy to remain implicit.
11. Do not accept generator quality based on one or two anecdotal prompts; use a corpus and saved validation reports.
12. Do not let YouTube/GVHMR failure become a dead-end if DROID fallback can satisfy the request.
13. Do not present a replay clip without disclosing whether it came from GVHMR, DROID, or simulated policy output.

## Sources
- MuJoCo XML reference: https://mujoco.readthedocs.io/en/latest/XMLreference.html
- MuJoCo modeling / URDF note: https://mujoco.readthedocs.io/en/stable/modeling.html
- MuJoCo MJX: https://mujoco.readthedocs.io/en/latest/mjx.html
- Isaac Sim URDF import: https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html
- Isaac Sim URDF importer: https://docs.isaacsim.omniverse.nvidia.com/latest/robot_setup/ext_isaacsim_asset_importer_urdf.html
- Isaac Sim MJCF importer: https://docs.isaacsim.omniverse.nvidia.com/5.1.0/importer_exporter/import_mjcf.html
- Isaac Sim Robot Schema: https://docs.isaacsim.omniverse.nvidia.com/latest/omniverse_usd/robot_schema.html
- Isaac Lab asset import workflow: https://isaac-sim.github.io/IsaacLab/develop/source/how-to/import_new_asset.html
- ROS 2 URDF docs: https://docs.ros.org/en/humble/Tutorials/Intermediate/URDF/URDF-Main.html
- ros2_control getting started: https://control.ros.org/rolling/doc/getting_started/getting_started.html
- ros2_control hardware interface types: https://docs.ros.org/en/rolling/p/hardware_interface/doc/hardware_interface_types_userdoc.html
- SDFormat spec: https://sdformat.org/spec
- OpenUSD articulation root: https://openusd.org/release/api/class_usd_physics_articulation_root_a_p_i.html
- OpenUSD mesh schema: https://openusd.org/docs/api/class_usd_geom_mesh.html
- CadQuery import/export: https://cadquery.readthedocs.io/en/latest/importexport.html
- PartCAD intro: https://partcad.readthedocs.io/en/latest/intro.html
- PartCAD procurement/manufacturing: https://partcad.readthedocs.io/en/latest/features.html
- Onshape URDF export announcement: https://www.onshape.com/en/resource-center/what-is-new/urdf-export-control-point-edit-curve-g3-support-connection-analysis
- onshape-to-robot docs: https://onshape-to-robot.readthedocs.io/en/latest/
- 3MF specification: https://3mf.io/spec/
- Prusa/3MF workflow: https://3mf.io/blog/2022/12/how-to-export-3d-print-projects-from-prusaslicer-with-3mf/
- lib3mf docs: https://lib3mf.readthedocs.io/en/
- DigiKey API: https://developer.digikey.com/products/product-information-v4/partsearch
- Mouser API: https://my.mouser.com/api-search/
- McMaster-Carr API: https://www.mcmaster.com/help/api/
- Photon Spectrum: https://photon.codes/spectrum
- Photon Spectrum TS getting started: https://docs.photon.codes/spectrum-ts/getting-started
- Photon pricing/features: https://photon.codes/pricing
- Photon iMessage adapter notes: https://chat-sdk.dev/adapters/imessage
- Photon messages docs: https://docs.photon.codes/spectrum-ts/messages

### Phase 21: High-fidelity mesh/CAD geometry pipeline
Goal: move from inspectable procedural GLB output to genuinely high-fidelity robot geometry suitable for engineering review and stronger visual presentation.

Required because:
- the current engineering renderer now has correct component metadata and hover/inspection behavior
- but the emitted GLB is still built from a procedural primitive library, not authored or CAD-derived geometry

Deliverables:
1. authored shell/cover/bracket/end-effector geometry per link/component family
2. richer material system:
   - PBR base color
   - roughness/metalness
   - optional normal maps
3. named articulated submeshes preserved in GLB export
4. deterministic mapping from `RobotDesignIR` component ids to GLB node ids
5. optional custom-part CAD linkout:
   - STEP
   - STL
   - 3MF

Acceptance:
1. engineering GLB remains parseable by `GLTFLoader`
2. mesh/node naming stays stable across revisions
3. right-pane component inspection still resolves exact submeshes
4. visual fidelity materially exceeds primitive-only capsule/box assemblies
- DROID dataset overview: https://droid-dataset.github.io/droid/the-droid-dataset.html
- LeRobot DROID porting guide: https://huggingface.co/docs/lerobot/main/en/porting_datasets_v3
- CadQuery import/export: https://cadquery.readthedocs.io/en/stable/importexport.html
- glTF runtime asset delivery: https://www.khronos.org/gltf/
- Three.js GLTFLoader: https://threejs.org/docs/pages/GLTFLoader.html
- Gemini 2.5 Pro model page: https://ai.google.dev/models/gemini
- Gemini Robotics-ER 1.5 overview: https://ai.google.dev/gemini-api/docs/robotics-overview
- Gemini Robotics-ER 1.5 model page: https://deepmind.google/models/gemini-robotics/gemini-robotics-er/
- Claude Opus 4.7 announcement: https://www.anthropic.com/news/claude-opus-4-7
- OpenAI GPT-5 model docs: https://platform.openai.com/docs/models/gpt-5
- RoboMoRe co-design paper: https://openreview.net/forum?id=DRthPQNRhA
- Accelerated co-design through morphological pretraining: https://openreview.net/forum?id=WVliGyFwZv
- Climbing robot structural design: https://link.springer.com/article/10.1186/s40638-015-0031-x
- Claw gripper system for climbing robots: https://link.springer.com/article/10.1007/s10846-017-0552-3
- Review of modular legged and climbing robots: https://www.mdpi.com/2313-7673/9/6/319
