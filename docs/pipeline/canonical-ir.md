---
description: The canonical robot design IR used for compilation, validation, and research benchmarking.
---

# Canonical IR

The canonical robot representation lives in:

```text
packages/pipeline/ir/design_ir.py
```

It defines frozen dataclasses for robot bodies.

## Main types

| Type | Purpose |
| --- | --- |
| `RobotDesignIR` | Complete robot design |
| `LinkIR` | Link/body segment |
| `JointIR` | Connection and motion relationship between links |
| `Geometry` | Link geometry description |
| `SensorSlot` | Sensor mount point and metadata |
| `ActuatorSlot` | Actuator assignment and metadata |

## Why IR exists

The product candidate is optimized for display. The grammar HITL payload is optimized for review. The canonical IR is optimized for deterministic downstream robotics work.

The IR is the shape that compilers and benchmark harnesses should prefer.

## Validation

The IR validates important structural references, including:

- joint parent links,
- joint child links,
- sensor mount links,
- actuator targets.

Invalid references should be caught close to the IR rather than surfacing later as confusing MJCF or simulation failures.

## Relationship to generated body programs

`RobotDesignProgram` and `ComponentProgram` are upstream body-generation representations. They can be materialized into `RobotDesignIR` by research strategies and materializers.

The product route currently also adapts generated HITL data into flat candidates. That product candidate path is separate from full IR materialization.

## When to change IR

Change IR only when downstream robotics behavior needs it:

- a new joint type,
- a new geometry type,
- new actuator or sensor semantics,
- additional physical properties needed by compilers or simulation,
- stronger validation requirements.

IR changes are architecture-sensitive and should update the handoff document and tests.

