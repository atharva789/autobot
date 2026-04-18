# Phase 04: Retargeting + Simulation (Hackathon)

## Scope
Adopt an existing SMPL-X → G1 retargeter off the shelf. Play the resulting joint trajectory back in MuJoCo headless. Render an `.mp4`. This is the single most technically risky block in the 36 hours — time-box aggressively and use the fallback ladder.

## Pinned Decisions
- Simulator = MuJoCo 3.x + `unitree_mujoco` G1 model. Isaac Lab is deleted from scope.
- Retarget lib candidates (pick by install speed):
  1. OmniH2O (NVIDIA, has SMPL→humanoid scripts)
  2. PHC (CMU, SMPL-to-humanoid retarget)
  3. ProtoMotions (NVIDIA, broader)
  4. `unitree_rl_gym` retarget example
  5. **Nuclear fallback:** hand-written joint-name map from SMPL joints to G1 joints + IK via `mink` or `pink`.
- Playback mode = kinematic (set qpos, step, render). PD control with gravity is a stretch goal only if hours 10–14 finish early.
- Rendering = MuJoCo offscreen → ffmpeg → `.mp4` at 30fps, 480p.

## Hours 10–18 Checklist
- [ ] Time-box the first retarget-lib install to 2 hours. If it blocks, drop to the next in the ladder.
- [ ] Run the retargeter on one staged SMPL sequence → G1 joint trajectory `.npz` (shape: `[T, num_joints]`).
- [ ] Load the `.npz` into MuJoCo; step frame-by-frame setting `qpos` directly.
- [ ] Render to `data/replays/<run_id>.mp4` headless. Verify it plays in a browser `<video>` tag.
- [ ] Wrap the pipeline as `run_retarget_and_sim(run_id: str) -> str` returning the replay path.
- [ ] Wire `POST /runs` to trigger it via `BackgroundTasks` and update `runs.status` and `runs.replay_path` when done.
- [ ] Stretch: catch joint-limit violations and clamp. Do not ship a metrics suite.

## Demo Safety Net
Pre-render `.mp4` replays for all 3 staged clips offline. If the live pipeline misbehaves during the demo, the API serves the cached `.mp4` and the judge never knows.

## Explicitly Out of Scope
- Isaac Lab / Isaac Sim.
- Dynamic control with balance, PD gains tuning, contact-rich manipulation.
- Validation metric suite: foot slip, self-collision, fall events, contact mismatch, timing drift, instability.
- Pass/fail/borderline thresholds.
- Corrected-vs-original trajectory versioning. Ship whichever the retargeter produced.
- Reviewer payload contracts beyond "play the mp4."

## Exit Criteria
- For one staged clip, `run_retarget_and_sim` produces an `.mp4` that visibly resembles the source motion.
- `POST /runs` completes end-to-end in <30 seconds with the pipeline warmed.
- Replay mp4 plays in the Next.js UI next to the source video.

## Handoff to Phase 05
- `runs.replay_path` is set. `runs.approved` is false until the human clicks approve. Joint trajectory `.npz` is saved for export.
