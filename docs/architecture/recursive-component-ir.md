# Recursive Component IR Architecture

**Date**: 2026-04-19
**Status**: Design Document

## 1. Current Limitations

### Where Recursion Stops Today

| Layer | Current State | Problem |
|-------|---------------|---------|
| `RobotDesignCandidate` | Flat counts: `num_legs=4`, `leg_dof=3` | No component graph |
| `ComponentizedMorphology` | Flat lists: `actuators[]`, `structural[]` | No parent/child |
| `EngineeringScene.nodes[]` | Flat array with `component_kind` | No hierarchy |
| `BOMOutput` | Category buckets: `actuator_items[]` | No assembly ownership |
| `_MESH_LIBRARY` | Primitive-material pairs | No assembly templates |

### Shallow Abstractions

1. **"leg"** = `leg_0_link` + `leg_0_joint_0` (1 link, N joints)
   - Missing: hip assembly, knee assembly, ankle assembly, foot pad, encoder, cable harness

2. **"arm"** = `arm_0_link` + `arm_0_joint_0` (1 link, N joints)  
   - Missing: shoulder bracket, elbow assembly, wrist interface, end effector

3. **"gripper"** = visual-only claw meshes
   - Missing: palm chassis, finger assemblies, actuators, sensors, cable routing

4. **"torso"** = single `torso_frame`
   - Missing: shell panels, battery bay, controller bay, mounting bosses

## 2. Proposed Recursive Architecture

### Component IR Hierarchy

```
Robot
├── Subsystem (locomotion, manipulation, sensing, power, compute)
│   ├── Assembly (leg_0, arm_1, gripper_left)
│   │   ├── Component (hip_motor, knee_encoder, finger_proximal)
│   │   │   ├── Feature (mounting_holes, cable_port, sensor_face)
│   │   │   └── Interface (shaft_coupling, electrical_connector)
│   │   └── Subassembly (optional nesting)
│   └── Assembly...
└── Subsystem...
```

### ID Scheme

Stable, hierarchical IDs for deterministic expansion:

```
robot:quadruped_climber
├── subsystem:locomotion
│   ├── assembly:leg_fl
│   │   ├── component:hip_fl
│   │   │   ├── part:hip_fl_motor
│   │   │   ├── part:hip_fl_gearbox
│   │   │   └── part:hip_fl_encoder
│   │   ├── component:thigh_fl
│   │   │   ├── part:thigh_fl_link
│   │   │   └── part:thigh_fl_guard
│   │   ├── component:knee_fl
│   │   └── component:foot_fl
│   │       ├── part:foot_fl_pad
│   │       ├── part:foot_fl_spike_0
│   │       └── part:foot_fl_force_sensor
```

### Schema Levels

**Level 0: Robot** (from Gemini)
```python
class RobotDesignCandidate:
    embodiment_class: str
    subsystem_hints: list[str]  # ["locomotion:quadruped", "manipulation:dual_gripper"]
```

**Level 1: Subsystem** (deterministic expansion)
```python
class SubsystemSpec:
    id: str  # "subsystem:locomotion"
    kind: Literal["locomotion", "manipulation", "sensing", "power", "compute", "payload"]
    assembly_ids: list[str]
```

**Level 2: Assembly** (deterministic expansion)
```python
class AssemblySpec:
    id: str  # "assembly:leg_fl"
    parent_id: str  # "subsystem:locomotion"
    kind: str  # "leg", "arm", "gripper", "torso_bay"
    component_ids: list[str]
    joints: list[JointSpec]
```

**Level 3: Component** (deterministic expansion)
```python
class ComponentSpec:
    id: str  # "component:hip_fl"
    parent_id: str  # "assembly:leg_fl"
    kind: str  # "joint_module", "link", "end_effector"
    part_ids: list[str]
    interfaces: list[InterfaceSpec]
```

**Level 4: Part** (terminal, maps to BOM)
```python
class PartSpec:
    id: str  # "part:hip_fl_motor"
    parent_id: str  # "component:hip_fl"
    kind: str  # "actuator", "structural", "sensor", "fastener"
    vendor_sku: str | None
    geometry: PartGeometry
```

## 3. Staged Expansion Pipeline

### Stage 1: Task → Embodiment (Gemini)
```
Input: "climb a rock wall while carrying rope"
Output: RobotDesignCandidate with subsystem_hints
```

### Stage 2: Embodiment → Subsystem Graph (Deterministic)
```python
SUBSYSTEM_TEMPLATES = {
    "quadruped": ["locomotion:quadruped", "sensing:terrain", "payload:dorsal"],
    "dual_arm": ["manipulation:dual_arm", "sensing:workspace"],
    "climbing_hybrid": ["locomotion:quadruped", "manipulation:climbing_gripper", "traction:microspine"],
}
```

### Stage 3: Subsystem → Assembly Graph (Deterministic)
```python
ASSEMBLY_TEMPLATES = {
    "locomotion:quadruped": {
        "leg_fl": "leg_3dof",
        "leg_fr": "leg_3dof",
        "leg_rl": "leg_3dof",
        "leg_rr": "leg_3dof",
    },
    "manipulation:climbing_gripper": {
        "gripper_fl": "gripper_2finger",
        "gripper_fr": "gripper_2finger",
    },
}
```

### Stage 4: Assembly → Component Graph (Deterministic)
```python
COMPONENT_TEMPLATES = {
    "leg_3dof": {
        "hip": {"kind": "joint_module", "actuator": True, "dof": 1},
        "thigh": {"kind": "link", "length_factor": 0.4},
        "knee": {"kind": "joint_module", "actuator": True, "dof": 1},
        "shin": {"kind": "link", "length_factor": 0.4},
        "ankle": {"kind": "joint_module", "actuator": True, "dof": 1},
        "foot": {"kind": "end_effector", "contact": True},
    },
    "gripper_2finger": {
        "palm": {"kind": "chassis", "mounts": ["finger_0", "finger_1", "wrist"]},
        "finger_0": {"kind": "finger_assembly", "phalanges": 2},
        "finger_1": {"kind": "finger_assembly", "phalanges": 2},
        "wrist_interface": {"kind": "interface", "dof": 1},
    },
}
```

### Stage 5: Component → Parts (Deterministic)
```python
PART_TEMPLATES = {
    "joint_module": [
        {"role": "motor", "kind": "actuator"},
        {"role": "gearbox", "kind": "transmission"},
        {"role": "encoder", "kind": "sensor"},
        {"role": "housing", "kind": "structural"},
        {"role": "shaft_coupling", "kind": "interface"},
    ],
    "finger_assembly": [
        {"role": "proximal_link", "kind": "structural"},
        {"role": "distal_link", "kind": "structural"},
        {"role": "flexure_joint", "kind": "joint"},
        {"role": "tip_sensor", "kind": "sensor"},
        {"role": "cable_path", "kind": "routing"},
    ],
}
```

## 4. Model Work vs Deterministic Work

| Stage | Who | Output |
|-------|-----|--------|
| Task interpretation | Gemini | `TaskSpec` |
| Embodiment selection | Gemini | `RobotDesignCandidate` with `subsystem_hints` |
| Subsystem expansion | **Compiler** | `SubsystemSpec[]` |
| Assembly expansion | **Compiler** | `AssemblySpec[]` |
| Component expansion | **Compiler** | `ComponentSpec[]` |
| Part resolution | **Compiler** | `PartSpec[]` with SKUs |
| Geometry generation | **Compiler** | `PartGeometry[]` |
| BOM roll-up | **Compiler** | Hierarchical `BOMOutput` |

## 5. Updated Data Structures

### Hierarchical BOM
```python
class HierarchicalBOMNode:
    id: str
    parent_id: str | None
    level: Literal["robot", "subsystem", "assembly", "component", "part"]
    display_name: str
    parts: list[PartBOMEntry]  # only at leaf level
    subtotal_usd: float | None
    children: list[str]  # child node IDs
```

### Hierarchical Render Scene
```python
class HierarchicalSceneNode:
    id: str
    parent_id: str | None
    level: str
    display_name: str
    component_kind: str
    geometry: NodeGeometry | None  # only for renderable nodes
    children: list[str]
    collapsed: bool  # UI hint for tree expansion
```

## 6. Implementation Plan

### Phase 1: Schema Foundation (2h)
- [ ] Add `packages/pipeline/component_ir.py` with recursive schemas
- [ ] Add `SubsystemSpec`, `AssemblySpec`, `ComponentSpec`, `PartSpec`
- [ ] Add hierarchical ID generation utilities

### Phase 2: Deterministic Expander (3h)
- [ ] Add `packages/pipeline/component_expander.py`
- [ ] Implement subsystem → assembly expansion
- [ ] Implement assembly → component expansion
- [ ] Implement component → parts expansion
- [ ] Add expansion templates for common assemblies

### Phase 3: BOM Integration (2h)
- [ ] Update `bom_generator.py` to use hierarchical structure
- [ ] Implement roll-up cost calculation
- [ ] Preserve assembly ownership in BOM output

### Phase 4: Render Integration (2h)
- [ ] Update `engineering_render.py` to emit hierarchical nodes
- [ ] Add parent/child relationships to `ui_scene`
- [ ] Update mesh generation for deeper components

### Phase 5: Frontend Consumption (2h)
- [ ] Update `types.ts` with hierarchical types
- [ ] Update `MorphologyViewer.tsx` to render tree
- [ ] Add collapsible component tree in inspector

### Phase 6: Tests (2h)
- [ ] Add `tests/test_component_ir.py`
- [ ] Add `tests/test_component_expander.py`
- [ ] Update existing render/BOM tests

## 7. Files to Change

**New Files:**
- `packages/pipeline/component_ir.py` - Recursive schemas
- `packages/pipeline/component_expander.py` - Deterministic expansion
- `packages/pipeline/expansion_templates.py` - Assembly templates
- `tests/test_component_ir.py`
- `tests/test_component_expander.py`

**Modified Files:**
- `packages/pipeline/schemas.py` - Add `subsystem_hints` to candidate
- `packages/pipeline/bom_generator.py` - Use hierarchical BOM
- `packages/pipeline/engineering_render.py` - Hierarchical scene nodes
- `apps/web/lib/types.ts` - Add hierarchical types
- `apps/web/components/MorphologyViewer.tsx` - Render tree structure

## 8. Residual Risks

1. **Template completeness** - Need templates for all embodiment classes
2. **Geometry complexity** - Deeper parts need appropriate primitives
3. **Performance** - Deep trees may slow render/BOM generation
4. **Backward compatibility** - Existing designs need migration path

## 9. Key Insight

The blocker is not mesh quality. The blocker is that the system models **visual parts** instead of **recursive engineering assemblies**. Visual parts have no internal structure. Engineering assemblies decompose into real manufacturable components.
