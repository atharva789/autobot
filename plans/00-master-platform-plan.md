# Language-to-Imitation Learning — 36h Hackathon Plan

## Framing
The original plan (preserved in git history) was an 8-week, 5-phase production platform: multi-tenant cloud workers, vector index, compliance ledger, Deep Agents orchestration, Isaac Lab, LangGraph, human-review queues. That is not shippable in 36 hours. This document collapses it to a judge-facing demo and deletes everything that does not put a humanoid robot on screen mimicking a reference video.

## Demo One-Liner
Type a task → pick a reference clip → watch Unitree G1 perform the motion in MuJoCo → click approve → download a LeRobot-compatible `.parquet` → load it in a Colab notebook.

## Locked Demo Scope
- **Robot:** Unitree G1 only. URDF + meshes committed to the repo. No upload UI.
- **Task input:** free-text prompt (displayed but not parsed) + dropdown of 3 pre-staged clips.
- **Video source:** 3 hand-curated clips with pre-extracted SMPL-X motion cached on disk. No discovery, no mirroring, no YouTube at runtime.
- **Pose extraction:** run offline before the hackathon using WHAM or GVHMR; commit the `.pkl` outputs. Fallback: use clips from AMASS / Motion-X that already ship with SMPL parameters.
- **Retargeting:** existing OSS SMPL-X→G1 retargeter (OmniH2O, PHC, or ProtoMotions — pick whichever installs fastest). No custom retarget code.
- **Simulation:** MuJoCo 3.x + `unitree_mujoco` model. Kinematic playback is acceptable; PD control is a stretch goal.
- **Export:** HuggingFace `lerobot` library, one `.parquet` per approved run.
- **UI:** single-page Next.js App Router. Side-by-side source video | MuJoCo replay | prompt field | approve + export buttons.
- **Storage:** local filesystem + SQLite.
- **Review:** one human click.

## Explicitly Deleted From Original Plan
Deferred post-hackathon (do not implement, do not scaffold):
- Open-web discovery, full-source mirroring, DMCA / copyright / retention / takedown / audit.
- Vector index, multimodal retrieval, dedup, quality filters, confidence scoring.
- Deep Agents orchestration, LangGraph workflows, agent-coordinator.
- Multi-tenant orgs / projects / users / auth / RBAC.
- Control-plane / worker-plane split, async job queue, retry state machines.
- URDF upload, URDF validation, humanoid-readiness checks.
- LLM task normalization, search-plan generation, ambiguity resolution.
- Isaac Lab / Isaac Sim.
- Validation metric suite (foot slip, fall detection, contact mismatch, timing drift).
- Manifests, re-export, provenance ledger, operator tooling, access control.
- Multi-humanoid support.

## Stack
- **Frontend:** Next.js 15 App Router, one page, `shadcn/ui` for speed.
- **Backend:** FastAPI, synchronous endpoints + `BackgroundTasks` for sim runs.
- **Pipeline:** Python 3.11, MuJoCo 3.x, retarget lib (OmniH2O / PHC / ProtoMotions), `huggingface-lerobot`.
- **DB:** SQLite via SQLAlchemy.
- **Media:** local `./data/` directory.

## 36-Hour Timeline
| Hour | Milestone |
|------|-----------|
| 0–4   | Repo scaffold, lockfiles, MuJoCo + G1 URDF loads, retarget lib installs, WHAM installs (or skipped for AMASS fallback). |
| 4–10  | Pre-extract SMPL-X from 3 clips (or adopt AMASS). Commit `.pkl`. Sanity-render to GIF. |
| 10–18 | Retarget one SMPL sequence to G1; render headless MuJoCo `.mp4`; wrap as `run_retarget_and_sim(clip_id)`. |
| 18–24 | FastAPI endpoints; Next.js skeleton wired to `/clips`, `/runs`, `/runs/{id}`. |
| 24–30 | Next.js UI polish: side-by-side player, prompt field, approve + export buttons, status polling. |
| 30–34 | LeRobot `.parquet` export; round-trip load in a notebook to prove schema. |
| 34–36 | Demo rehearsal, README, pitch slide, buffer for one blocker. |

## Hard Success Criteria (v1 = hackathon demo)
- Judge clicks "generate" on at least one staged clip and sees a rendered robot replay in under 30 seconds.
- Judge clicks "approve" and "export" and downloads a `.parquet` that `lerobot.LeRobotDataset.from_parquet(...)` loads without error, reporting `num_episodes == 1`.
- Happy path runs three times in a row without restart.

## Risks + Mitigations
- **Retarget lib install eats a day.** Mitigation: time-box install to 2h; if it fails, switch to the next candidate in the ladder (OmniH2O → PHC → ProtoMotions → hand-written SMPL-joint → G1-joint name map).
- **MuJoCo setup fragile on macOS / CUDA mismatch.** Mitigation: verify `unitree_mujoco` hello-world before hour 4; have a Linux fallback box ready.
- **Retarget output looks weird.** Mitigation: pre-polish one hero clip for the demo; keep ugly clips out of the live run.
- **LeRobot schema drift between versions.** Mitigation: pin `lerobot` version; copy schema from a known-working example dataset.
- **Pose extraction fails on staged videos.** Mitigation (primary): use AMASS / Motion-X clips from day 1 and frame the YouTube path as future work.

## Source-of-Truth Decisions (originally "open decisions", now pinned)
| Area | Hackathon decision |
|------|---------------------|
| Topology | Single FastAPI + single Next.js app. No services. |
| Queue | `FastAPI.BackgroundTasks`. No Celery, no Redis, no Temporal. |
| Orchestration | Plain Python functions. No LangGraph, no Deep Agents. |
| IDs | UUIDv4 strings per row. |
| Storage | Local filesystem + SQLite. No S3, MinIO, or object store. |
| Provenance | `clip_id` + `run_id` columns. No ledger. |
| Auth | None. Local single-user. |
| Vector index | None. Clips are a hardcoded YAML list. |
| Observability | `print()` + uvicorn access logs. |
| Review | `runs.approved BOOLEAN`. |

## What Judges See (script)
1. Paste "wave both arms" into the prompt field. Pick clip `waving_person`.
2. Click **Generate**. ~20s later, side-by-side: reference video ↔ G1 MuJoCo replay.
3. Click **Approve**, then **Export**. Browser downloads `dataset.parquet`.
4. Open Colab → `from lerobot.common.datasets.lerobot_dataset import LeRobotDataset; ds = LeRobotDataset.from_parquet("dataset.parquet"); print(len(ds))` → prints `1`.

End of v1.
