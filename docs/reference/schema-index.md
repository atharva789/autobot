---
description: Major data shapes and where their definitions live.
---

# Schema Index

## Product and frontend shapes

| Shape | File | Purpose |
| --- | --- | --- |
| `TaskIntent` | `packages/pipeline/schemas.py` and frontend types | Normalized user task |
| `RobotDesignCandidate` | `packages/pipeline/schemas.py`, `apps/web/lib/types.ts` | Product-facing candidate |
| `GenerateDesignsResponse` | `apps/web/lib/types.ts` | Design generation response |
| `GrammarHitl` | `apps/web/lib/types.ts` | Grammar-loop review payload |
| `WorkspaceProject` | `apps/web/lib/types.ts` | Workspace project |
| `WorkspaceThread` | `apps/web/lib/types.ts` | Workspace thread |
| `ThreadArtifact` | `apps/web/lib/types.ts` | Generated artifact attached to a thread |
| `SimulationSpec` | `apps/web/lib/types.ts` | Simulation check request/result |
| `PolicySpec` | `apps/web/lib/types.ts` | Policy spec request/result |

## Research shapes

| Shape | File | Purpose |
| --- | --- | --- |
| `AgentLoopConfig` | `packages/research/agent_loops/protocol.py` | Loop configuration |
| `AgentLoopResult` | `packages/research/agent_loops/protocol.py` | Loop return value |
| `GenerationStrategy` | `packages/research/strategy/protocol.py` | Experiment strategy protocol |
| `StrategyConfig` | `packages/research/strategy/protocol.py` | Strategy configuration |
| `Experiment` | `packages/research/experiment/types.py` | Experiment metadata |
| `ExperimentRun` | `packages/research/experiment/types.py` | One run record |
| `ReproEnvelope` | `packages/research/experiment/types.py` | Reproducibility metadata |
| `DesignMetrics` | `packages/research/benchmark/metrics.py` | Per-design metrics |
| `MetricsReport` | `packages/research/benchmark/metrics.py` | Aggregated metrics |

## Pipeline shapes

| Shape | File | Purpose |
| --- | --- | --- |
| `RobotDesignProgram` | `packages/pipeline/robot_program.py` | Derivation-first body program |
| `DerivationStep` | `packages/pipeline/robot_program.py` | One rule application |
| `GrammarCatalog` | `packages/pipeline/robot_program.py` | Available symbols and rules |
| `ExpandedRobotGraph` | `packages/pipeline/robot_program.py` | Expanded generated body graph |
| `ComponentProgram` | `packages/pipeline/robot_program.py` | Lowered component-level body |
| `RobotDesignHitlV2` | `packages/pipeline/robot_program.py` | Reviewable generated-body payload |
| `ProgramCompilation` | `packages/pipeline/robot_program.py` | Full compilation result |
| `RobotDesignIR` | `packages/pipeline/ir/design_ir.py` | Canonical robot design |
| `LinkIR` | `packages/pipeline/ir/design_ir.py` | Robot link |
| `JointIR` | `packages/pipeline/ir/design_ir.py` | Robot joint |
| `SensorSlot` | `packages/pipeline/ir/design_ir.py` | Sensor slot |
| `ActuatorSlot` | `packages/pipeline/ir/design_ir.py` | Actuator slot |

