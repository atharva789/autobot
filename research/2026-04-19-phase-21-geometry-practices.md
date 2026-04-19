# 2026-04-19 Phase 21 Geometry Practices

## What improved

Phase 21 raises the backend-generated engineering artifact from a low-information primitive assembly to a metadata-rich, materially varied articulated GLB.

The important architectural point is that the frontend still does not invent engineering geometry.
It consumes:
- `render_glb`
- `ui_scene`

both compiled by the backend.

## Practice 1: improve geometry by adding substructure, not by inflating prose

A better robot render did not come from prompting the model harder.
It came from adding more deterministic component families in the backend renderer:
- chest and back plates
- side fairings
- shoulder guards
- joint cowls
- forearm guards
- shin guards
- hip skirts
- payload straps
- cable guides
- sensor emitters

This is the correct pattern because the model proposes morphology intent while the renderer owns visual realization.

## Practice 2: material richness should be explicit and testable

The renderer now uses a broader material palette:
- composite shell
- sensor glass
- anodized metal
- joint core
- traction rubber
- payload textile
- ceramic armor plate
- optic emitter
- harness webbing
- brushed alloy

The important part is not just visual variety. The backend exposes measurable render stats:
- `material_count`
- `panel_node_count`
- `pbr_extension_count`
- `visual_complexity_score`

That keeps geometry improvements auditable instead of subjective.

## Practice 3: use glTF extensions deliberately

The upgraded renderer uses:
- `KHR_materials_clearcoat`
- `KHR_materials_emissive_strength`
- `KHR_materials_specular`
- `KHR_materials_transmission`

These are a practical middle ground:
- much richer than flat colors
- still well-supported by `GLTFLoader`
- cheaper and simpler than a full authored texture pipeline

## Practice 4: keep node names stable

Every added mesh node is named deterministically.
This matters because downstream systems depend on node identity:
- hover inspection
- component tab focus
- revision-to-revision comparison
- future replay overlays

A visually richer mesh pipeline that breaks naming stability is a regression.

## Practice 5: the right first milestone is not CAD-grade geometry

This phase is still not true CAD-derived or game-studio-authored geometry.
It is a stronger intermediate step:
- backend-generated
- backend-tested
- task-conditioned
- materially richer
- structurally inspectable

That is the correct stepping stone toward a later CAD/STEP/mesh-authoring pipeline.

## What remains after Phase 21

Still not solved:
- CAD-derived shell geometry
- true custom printable exoskeleton generation
- normal/roughness texture baking
- decimation / LOD pipeline
- mesh authoring from a real `RobotDesignIR` part library

Those should be a later phase, not faked by more prompt text.
