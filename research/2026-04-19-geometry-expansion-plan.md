# Phase 16A: Geometry Expansion Plan

## Goal

Raise the engineering viewer from placeholder procedural shapes to a compiled, task-conditioned GLB artifact that is visually richer, more informative, and structurally tied to backend design state.

## Why the current geometry is insufficient

Current state:
- the backend emits a valid GLB, but it is effectively a set of scaled cubes
- engineering mode is artifact-backed, but the artifact is still low-information
- the geometry does not visibly communicate task affordances like climbing, payload carriage, traction, or crawling profile
- the viewer can inspect a robot, but not learn much from the model itself

That misses one of the core wow-factors for the app.

## Research constraints

### glTF material and runtime support

glTF 2.0 uses a metallic-roughness physically based material model. This is the right baseline for consistent engineering visualization across runtimes.

Sources:
- glTF 2.0 specification: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- Khronos PBR overview: https://www.khronos.org/gltf/pbr

### Three.js runtime capability

`GLTFLoader` supports core glTF plus useful extensions including:
- `KHR_lights_punctual`
- `KHR_materials_clearcoat`
- `KHR_materials_emissive_strength`
- `KHR_materials_specular`
- `KHR_materials_transmission`

That means the frontend can already consume richer GLB assets if the backend emits them.

Source:
- https://threejs.org/docs/pages/GLTFLoader.html

### Longer-term manufacturing bridge

CadQuery can export `STEP`, `STL`, `3MF`, and `glTF`. That is the right long-term path for manufacturing-grade geometry, but not the minimum viable step for this phase.

Source:
- https://cadquery.readthedocs.io/en/stable/importexport.html

## Implementation approach

### Step 1: Task-conditioned geometry intent

Add a backend geometry-intent layer derived from:
- `TaskSpec` when available
- candidate rationale and topology otherwise

This intent controls:
- silhouette profile
- accessory modules
- end-effector style
- traction style
- payload carriage modules

Required task families for this phase:
- climbing
- slippery terrain / descent
- crawling / low-profile traversal
- load-carry / backpack
- default general-purpose

### Step 2: Replace cube-only GLB generation with a primitive mesh library

Backend should generate reusable mesh primitives with normals:
- box
- cylinder
- sphere
- cone/frustum

Then compose richer robots from those primitives:
- torso shell
- head / sensor dome
- limb tubes
- joint spheres
- foot pads
- grippers / claws
- traction spikes
- payload packs
- sensor pods

This is still procedural, but no longer toy geometry.

### Step 3: Add richer PBR material families

Emit backend material families for:
- painted composite shell
- machined metal
- anodized actuator housing
- emissive sensor indicator
- rubber traction surfaces

Use glTF metallic-roughness core plus selective extensions where justified.

### Step 4: Expand scene metadata

`ui_scene` should include:
- `task_geometry_profile`
- `material_count`
- `primitive_keys`
- `accessory_node_count`
- `engineering_ready`

This gives the UI and tests a concrete rendering contract.

### Step 5: Frontend presentation

The viewer should:
- load the richer GLB artifact directly
- keep concept mode separate
- render engineering/joints/components from the compiled artifact
- explicitly degrade if the compiled artifact is missing

## TDD gates

Before implementation, add failing tests for:
1. task-conditioned geometry cues for climbing payload tasks
2. richer GLB parse result:
   - normals present
   - higher mesh count
   - task accessories present
3. render payload stats:
   - material count
   - accessory count
   - geometry profile
4. frontend contract still using engineering mode and no fake fallback behavior

## Non-goals for this phase

- full CAD-derived mesh generation
- texture baking
- skeletal animation
- production-grade asset optimization / Draco / KTX2

Those are later improvements.

## Success criteria

A rock-climbing / payload design should now visibly show:
- a leaner profile
- explicit grasping end-effectors
- payload carriage geometry
- non-trivial foot / traction geometry
- materially different engineering appearance from a default mobility robot
