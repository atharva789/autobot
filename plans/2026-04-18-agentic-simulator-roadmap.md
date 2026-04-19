# Agentic Simulator Roadmap

Date: 2026-04-18
Repo: `/Users/thorbthorb/Downloads/IL_ideation`

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

Minimum models:
- `TaskIntent`
- `EmbodimentSpec`
- `RobotDesignIR`
- `AssemblyIR`
- `ExportManifest`

Refactor:
- Split or thin down [schemas.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/schemas.py).
- Make [design_generator.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/design_generator.py) output `EmbodimentSpec` or a lightweight draft, then deterministically compile to `RobotDesignIR`.

Acceptance:
- Every candidate serializes to `RobotDesignIR`.
- UI, BOM, URDF, and MJCF all derive from the same IR.

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
- `artifacts/<id>/manifest.json`

Acceptance:
- URDF parses.
- MJCF parses.
- Link/joint names are stable across all exports.
- Isaac importer naming constraints are satisfied.

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

Rule:
- `RobotGlyph` remains only for generation-state concept rendering.
- Detail mode must render from compiled artifact data.

Acceptance:
- The inspection studio matches the exported topology.
- Joint and link counts match MJCF/URDF.

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

Do not start with full RL on all 3 candidates.
Start with compile/load and short-horizon screening.

Acceptance:
- All 3 candidates compile.
- Top candidate passes MuJoCo and Isaac import/load.
- Ranking is backed by deterministic artifacts and reproducible metrics.

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
4. Procurement gate
   - Critical items resolve to real SKUs or explicit manufacturing placeholders.
5. CAD gate
   - Custom parts export to STEP and 3MF/STL.
6. Simulation gate
   - Top candidate survives staged screening.
7. Export gate
   - One-click MuJoCo, Isaac, and print bundles are produced.

## Recommended Implementation Order
1. Canonical IR
2. URDF/Xacro + ros2_control compiler
3. MJCF compiler
4. Validation suite
5. UI scene compiler and artifact-driven renderer
6. Procurement enrichment
7. CAD and print export
8. MuJoCo screening
9. Isaac promotion
10. HITL and export polish

## What Not To Do First
1. Do not make USD the canonical source of truth.
2. Do not let the LLM emit URDF/MJCF directly.
3. Do not start with full RL training on all 3 candidates.
4. Do not treat the current curated BOM catalogs as sufficient procurement grounding.
5. Do not keep the mislabeled URDF path alive indefinitely.

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
