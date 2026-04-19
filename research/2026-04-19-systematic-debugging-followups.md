# 2026-04-19 Systematic Debugging Follow-ups

This note records the concrete root causes found after the original phase plan was completed.

## 1. Gemini structured output failure: "too many states for serving"

### Root cause

The provider call in `packages/pipeline/design_generator.py` was still sending the full internal `DesignCandidatesResponse` schema to Gemini structured output.

That schema had accumulated too many provider-hostile features:

- nested post-processing objects
- long property names
- many bounded numeric fields
- array length constraints
- fields that the model did not need to emit because the backend already derives them

This matches Google's current structured output limitation guidance:

- large or deeply nested schemas may be rejected
- bounds and schema complexity contribute to rejection

### Fix shipped

The provider-facing schema is now compact and short-keyed.

The backend now:

1. asks Gemini for a compact candidate schema only
2. reconstructs the richer internal `RobotDesignCandidate` objects deterministically
3. applies task conditioning, hardrails, diversity, telemetry, validation, and rendering after generation

### Engineering practice

Never expose the full internal schema to the model if:

- the backend can derive part of it deterministically
- those fields are only needed for downstream ranking, validation, or UI

Use:

- small provider schema
- deterministic expansion layer
- fallback path for arbitrary provider exceptions

## 2. Humanoid geometry is still too primitive

### Root cause

The current engineering renderer is still procedural and primitive-based.

`packages/pipeline/engineering_render.py` builds geometry from a small internal mesh library:

- `cylinder`
- `sphere`
- `box`
- `cone`

That means the "engineering" GLB is still just a richer primitive assembly, not authored or CAD-derived geometry.

### Consequence

The UI is technically rendering a `.glb`, but not one that is useful enough for robotics engineering or "game-grade" wow-factor expectations.

### Required follow-up

This needs a dedicated follow-up phase:

1. generate a real articulated scene graph from robot IR
2. generate authored link shells / covers / brackets / end-effectors
3. export mesh-backed GLB with:
   - PBR materials
   - normal/roughness maps where applicable
   - named articulated submeshes
4. keep `ui_scene.json` as the metadata overlay contract

Likely stack:

- CadQuery / custom mesh synthesis for custom parts
- Blender or trimesh/pyvista pipeline for polishing and decimation
- glTF 2.0 / GLB as runtime target

## 3. Tasks pane is not actually live

### Root cause

The app seeds task rows once on generation and reloads them by explicit refresh after actions.

Current behavior:

- tasks are created in `build_workspace_tasks(...)`
- route actions mutate tasks
- frontend reloads by calling `refreshDesignRuntime(...)`

There is no server-push channel.

### Consequence

- all seeded tasks appear at once
- the pane is not streamed
- it does not reflect long-running processes incrementally

### Required follow-up

Use:

- `POST` for commands and mutations
- `SSE` for task/event streaming

Why SSE over WebSockets here:

- the dominant flow is server -> client status/events
- simpler FastAPI integration
- easier replay/reconnect semantics
- lower operational complexity than a full bidirectional socket layer

WebSockets are only justified if the task input itself becomes a high-frequency collaborative stream.

## 4. Prompt box in task pane is static

### Root cause

The "Fire a task..." input is `readOnly` and currently just mirrors `selectedQuery ?? prompt`.

It is not wired to:

- mutation routes
- revision requests
- model editing directives

### Required follow-up

Add:

- `POST /designs/{id}/revise`
- `POST /designs/{id}/tasks` for arbitrary task instructions
- revision pipeline:
  - user text edit
  - mutation brief
  - compact model generation or deterministic transform
  - new revision
  - task/event stream update

## 5. "Edit prompt" is only a navigation reset

### Root cause

The current "Edit prompt" button only calls `setStage("prompt")`.

It does not:

- preserve revision context as an editable branch
- open a prefilled revision editor
- request a new revision from the backend

### Required follow-up

Turn it into:

- "Revise brief"
- opens prompt editor prefilled with current active prompt
- creates a design revision branch instead of hard-resetting the workspace

## 6. Hover/highlight/component-inspection behavior is missing

### Root cause

There is no hover selection contract from the viewer into the right inspector.

The current code does not maintain:

- hovered component id
- hovered node id
- selected component metadata resolution

### Required follow-up

Add:

- viewer raycast hit -> node id
- node id -> component id mapping from `ui_scene.json`
- hover state in page-level store
- green highlight material override for hovered structure
- right-pane component tab bound to hovered/selected component

## 7. Photon is not actually integrated with Spectrum

### Root cause

The current code uses `HttpPhotonTransport` and posts to invented endpoints:

- `/messages`
- `/polls`

This is not the same as using the actual Spectrum SDK model documented by Photon.

Photon's documented integration is built around:

- `Spectrum(...)`
- provider configs such as `imessage.config()`
- `app.messages`
- `space.send(...)`
- provider/user/space identities

### Consequence

A phone number alone is not sufficient to prove the app is actually wired to your Photon runtime.

### Required follow-up

Replace the fake transport abstraction with a real Spectrum worker/service:

1. initialize `Spectrum(...)`
2. resolve or create the relevant user/space identity
3. send via real provider-backed `space.send(...)` / platform-specific poll support
4. persist provider-native ids in the workspace store

The current HTTP transport can remain only as a local test shim.

## 8. DROID fallback should remain the structured recovery path

### Current state

This is already mostly correct now:

- YouTube timeout/auth/connection-like failures degrade to DROID
- replay provenance is explicit

### Required follow-up

Improve source orchestration further by:

- preferring DROID on repeated YouTube instability
- storing source health metrics
- exposing why DROID was chosen in the task/event stream

## Shipped follow-up implementations

The following items from this debugging pass are now implemented in the repo:

1. Real Spectrum-backed Photon path
   - `packages/pipeline/photon.py`
   - `apps/web/scripts/photon_send.mjs`
   - uses real `spectrum-ts` provider configuration when `PHOTON_PROJECT_ID` and `PHOTON_SECRET_KEY` are set
   - local HTTP shim remains only as fallback/test scaffolding

2. SSE task/event stream
   - `GET /designs/{id}/events`
   - persisted design events in `demo/workspace_store.py`
   - client-side `EventSource` consumption in `apps/web/app/page.tsx`

3. Revision/edit loop
   - `POST /designs/{id}/revise`
   - deterministic task-aware mutation in `packages/pipeline/design_revision.py`
   - task-pane input is no longer read-only

4. Hover/select component inspection workflow
   - `ui_scene` now includes component ids, structure ids, material labels, bounds, and focus summaries
   - `MorphologyViewer.tsx` now exposes component hover
   - the inspector has a real Components tab bound to hovered geometry

## Remaining major gap

One important gap remains and should be treated as a dedicated follow-up phase, not as solved work:

1. High-fidelity mesh/CAD geometry pipeline
   - The engineering GLB is now metadata-rich and inspectable.
   - It is still generated from a procedural primitive library, not authored/CAD-derived part geometry.
   - This means the app is now architecturally correct for inspection, but not yet at the "game-grade" or CAD-grade fidelity bar.

The correct next geometry phase is:

1. link/component IR -> authored shell/cover/bracket geometry
2. mesh decimation + PBR material pipeline
3. GLB export with articulated named submeshes
4. optional STEP/STL/3MF linkage for custom parts
