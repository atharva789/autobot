# Phase 02: Robot + Task Ingest (Hackathon)

## Scope
Skip robot upload entirely. G1 URDF + meshes are committed. Task input is a free-text prompt plus a dropdown selecting one of 3 pre-staged clips. The prompt is stored but not parsed — there is no LLM normalization in v1.

## Pinned Decisions
- Robot = Unitree G1. Assets at `assets/g1/` (URDF, MuJoCo XML, meshes). Source: `unitreerobotics/unitree_ros` or `unitree_mujoco`.
- Clip catalog = `config/clips.yaml`, 3 entries. Loaded into SQLite at API boot.
- Task prompt = free text, stored on the `runs` row, displayed in the UI, not parsed.

## Hours 4–6 Checklist
- [ ] Commit G1 URDF, MuJoCo XML, and meshes. Verify MuJoCo viewer loads the model and the default pose looks right.
- [ ] Write `config/clips.yaml`:
  ```yaml
  - id: waving
    title: Person waves both arms
    video_path: data/videos/waving.mp4
    smpl_path: data/smpl/waving.pkl
  - id: walking
    title: Person walks forward
    video_path: data/videos/walking.mp4
    smpl_path: data/smpl/walking.pkl
  - id: reaching
    title: Person reaches overhead
    video_path: data/videos/reaching.mp4
    smpl_path: data/smpl/reaching.pkl
  ```
- [ ] Implement `GET /clips` → reads YAML or the SQLite mirror of it.
- [ ] Implement `POST /runs` → creates a `runs` row with `(clip_id, prompt, status='queued')`, returns `run_id`.
- [ ] Frontend: prompt textarea + clip dropdown + generate button. On submit, POST `/runs`, then poll `GET /runs/{id}` every 2s until `status == 'done'`.

## Explicitly Out of Scope
- URDF upload UI, parsing, validation, mesh resolution, joint-limit diagnostics.
- Humanoid readiness checks, embodiment tagging.
- Task normalization LLM, search plan generation, ambiguity handling, uncertainty markers.
- Task edit / review state machine.
- Multi-robot, multi-embodiment.

## Exit Criteria
- UI dropdown lists the 3 clips.
- Submitting a prompt + clip creates a row in `runs` and returns a `run_id`.
- Polling `GET /runs/{id}` transitions `queued → running → done` as the pipeline progresses.

## Handoff to Phase 03
- `runs` row is ready for the retarget-and-sim pipeline to consume: `clip_id` points at a valid `smpl_path`.
