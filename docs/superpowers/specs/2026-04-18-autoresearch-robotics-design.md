# autoResearch for Robotics — Design Spec

**Author:** Atharva Gupta  
**Date:** 2026-04-18  
**Status:** Approved  
**Deadline:** 16 hours (14h build + 2h devpost / blog)  
**Demo format:** 2-minute recorded video + live dashboard  
**Write-up format:** Blog post / Notion (not peer-reviewed)

---

## 1. One-liner

Type a task → system fetches a reference video → evolves a robot morphology and neural controller to perform that task → you watch the evolution happen live → approve the best result → export to LeRobot format.

---

## 2. Research novelty (3 defensible claims)

1. **Karpathy's `autoresearch` pattern ported from LLM training to robot co-design.** The original pattern (agent edits `train.py`, 5-min budget, keep-best) is applied verbatim to a (morphology, controller) co-design loop over MuJoCo.
2. **Gemini Robotics-ER 1.6 as an automatic success-detection oracle inside the evolution loop.** ER 1.6 judges simulated rollout videos for task completion; its output is a weighted term in the fitness function.
3. **Single HITL checkpoint at the research-agenda level.** One `program.md` approval gate — not per-iteration approval — keeps a human in the loop without bottlenecking a 20-trial autonomous loop.

---

## 3. System architecture

### 3.1 Components

| # | Name | Technology | Where it runs |
|---|---|---|---|
| 1 | Frontend | Next.js 14 App Router, shadcn/ui, Tailwind, TanStack Query, Supabase JS SDK, Monaco Editor, React Three Fiber | User's browser |
| 2 | API | FastAPI (Python), extends existing `demo/` backend | Local machine |
| 3 | Video ingest | YouTube Data API v3 + yt-dlp + Gemini Robotics-ER 1.6 (Gemini API) | Local machine |
| 4 | GVHMR endpoint | Existing Modal app (`scripts/gvhmr_modal_probe.py`) — reused as-is | Modal (A10G) |
| 5 | VAE morphology sampler | PyTorch, Modal app (`scripts/modal_vae_train.py`) | Modal (A10G) — one-time training |
| 6 | Trial runner | PyTorch Geometric (GNN), MuJoCo, Modal app (`scripts/modal_trial_runner.py`) | Modal (A10G) — per iteration |
| 7 | Autoresearch orchestrator | Local Python process, Codex CLI (primary) / Claude CLI (fallback) | Local machine |
| 8 | Database + Storage + Realtime | Supabase (Postgres + S3-compatible Storage + Postgres Realtime) | Supabase cloud (free tier) |

### 3.2 Process boundaries

```
[Browser] ←── HTTP + Supabase Realtime ──→ [FastAPI, local]
                                                    │
                         ┌──────────────────────────┼──────────────────────────┐
                         ▼                          ▼                          ▼
              [YouTube + yt-dlp]       [Autoresearch Orchestrator]      [Gemini API]
                    │ yt-dlp download       │ Codex/Claude CLI edits           │ ER 1.6
                    ▼                       │ train.py / morph_factory.py      │
              [Supabase Storage]            │ per iteration                    │
                    ▲                       ▼                                  │
                    │              [Modal: trial runner]                       │
                    │              (GNN train + MuJoCo rollout)                │
                    │                       │                                  │
                    └───────────────────────┴──────────────────────────────────┘
                                artifacts + metrics → Supabase Postgres + Storage
```

---

## 4. Data model

### 4.1 Supabase Postgres tables

```sql
-- Existing, kept
clips (id TEXT PK, label TEXT, video_path TEXT, smpl_path TEXT)
runs  (id TEXT PK, clip_id TEXT, prompt TEXT, status TEXT,
       replay_path TEXT, approved BOOL, created_at TIMESTAMPTZ)
exports (id TEXT PK, run_id TEXT, parquet_path TEXT, created_at TIMESTAMPTZ)

-- New
evolutions (
  id TEXT PK,
  run_id TEXT REFERENCES runs,
  program_md TEXT,                -- approved program.md content
  status TEXT,                    -- pending|running|stopped|done
  best_iteration_id TEXT,
  total_cost_usd NUMERIC(8,4),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)

iterations (
  id TEXT PK,
  evolution_id TEXT REFERENCES evolutions,
  iter_num INT,
  morphology_id TEXT REFERENCES morphologies,
  controller_ckpt_url TEXT,       -- Supabase Storage signed URL
  trajectory_npz_url TEXT,
  replay_mp4_url TEXT,
  fitness_score NUMERIC(6,4),
  tracking_error NUMERIC(6,4),
  er16_success_prob NUMERIC(6,4),
  reasoning_log TEXT,             -- agent's markdown notes for this iter
  train_py_diff TEXT,             -- diff vs previous iteration
  morph_factory_diff TEXT,
  created_at TIMESTAMPTZ
)

morphologies (
  id TEXT PK,
  urdf_url TEXT,                  -- Supabase Storage
  latent_z_json TEXT,             -- JSON array, 8 floats
  params_json TEXT,               -- JSON of MorphologyParams
  num_dof INT,
  created_at TIMESTAMPTZ
)

ingest_jobs (
  id TEXT PK,
  source_url TEXT,
  er16_plan_json TEXT,            -- task_goal, affordances, success_criteria, search_queries
  gvhmr_job_id TEXT,
  smpl_path TEXT,
  status TEXT,                    -- pending|processing|done|failed
  created_at TIMESTAMPTZ
)

program_md_drafts (
  id TEXT PK,
  evolution_id TEXT REFERENCES evolutions,
  generator TEXT,                 -- 'codex' | 'claude-code'
  draft_content TEXT,
  approved BOOL,
  approved_at TIMESTAMPTZ,
  user_edited_content TEXT        -- null if user approved without edits
)
```

### 4.2 Supabase Storage buckets

| Bucket | Contents | Retention |
|---|---|---|
| `videos` | raw downloaded .mp4 clips | until demo |
| `smpl` | GVHMR output .pkl files | until demo |
| `artifacts` | URDFs, controller .pt files, trajectory .npz files | until demo |
| `replays` | MuJoCo rollout .mp4 per iteration | until demo |
| `exports` | final LeRobot .parquet, URDF, controller ckpt, evolution_log.md | permanent |

### 4.3 Filesystem (local only)

```
data/artifacts/evolutions/{evo_id}/
  ├── prepare.py              # FIXED: loads SMPL, MuJoCo env, fitness fn
  ├── train.py                # AGENT-EDITABLE: GNN arch + training loop
  ├── morphology_factory.py   # AGENT-EDITABLE: parametric URDF constructor
  ├── program.md              # HUMAN-APPROVED research agenda
  └── iterations/
      ├── 001/train.py        # snapshot per iter
      ├── 001/morphology_factory.py
      └── 001/reasoning.md    # agent's notes
```

### 4.4 Supabase Realtime

Frontend subscribes to INSERT events on the `iterations` table. Each new row auto-pushes to the dashboard history pane. No polling, no SSE endpoint needed.

---

## 5. Video ingest pipeline

```
User prompt
  │
  ▼
Gemini Robotics-ER 1.6  (Gemini API, one call, ~$0.02)
  Input:  prompt text
  Output: {
    task_goal: str,
    affordances: [str],
    success_criteria: str,
    search_queries: [str]   # top 3 YouTube queries
  }
  │
  ▼
YouTube Data API v3  (search_queries[0])
  Returns: list of video IDs + titles
  Pick: top result by view count with duration < 3 min
  │
  ▼
yt-dlp  (download to tmp/, upload to Supabase Storage bucket 'videos')
  │
  ▼
GVHMR Modal endpoint  (existing, reused)
  Input:  Supabase Storage signed URL for .mp4
  Output: SMPL-X trajectory .pkl, uploaded to bucket 'smpl'
  Time:   ~4 min (cached if same URL)
```

No user video upload UI. System-initiated, user sees a loading state in the dashboard.

---

## 6. Autoresearch loop

### 6.1 The three files (Karpathy pattern)

| File | Mutable by | Purpose |
|---|---|---|
| `prepare.py` | Nobody | Fixed runtime: loads SMPL trajectory, builds MuJoCo env, computes fitness. Never edited. |
| `train.py` | Agent (Codex/Claude CLI) | GNN architecture, imitation training loop, epoch count (≤40). Agent mutates this each iteration. |
| `morphology_factory.py` | Agent (Codex/Claude CLI) | Parametric URDF constructor. Agent adjusts ranges, adds/removes features. |
| `program.md` | Human (approved once) + Agent reads | Research agenda. Written by agent, approved by human before loop starts. |

### 6.2 HITL gate (program.md)

```
1. POST /evolutions/start  →  API creates evolution row (status=pending)
2. API shells out: codex exec "draft program.md for this task [ER16 plan JSON]"
   Fallback: claude -p "draft program.md..."  (if codex exits non-zero)
3. Draft saved to program_md_drafts row
4. Frontend screen 3 (HITL): Monaco editor shows draft
5. User clicks one of:
   [Approve]           → program.md finalized, evolution status=running
   [Edit + Approve]    → user edits in Monaco, saves, status=running
   [Regenerate]        → repeat step 2 with temperature+0.2
   [Claude fallback]   → repeat step 2 using claude CLI explicitly
6. Loop starts
```

### 6.3 Inner loop (per iteration, Modal A10G)

```python
# pseudocode — local orchestrator
for iter_num in range(MAX_ITERS):  # MAX_ITERS = 20

    # Step A: agent edits train.py + morphology_factory.py
    codex_exec(
        prompt=f"Read program.md and last 3 iterations (scores + reasoning). "
               f"Edit train.py and/or morphology_factory.py to try a better approach.",
        editable=["train.py", "morphology_factory.py"],
        timeout_s=120,
    )

    # Step B: dispatch to Modal (A10G, 15-min timeout)
    result = modal_trial_runner.remote(
        evolution_id=evo_id,
        iter_num=iter_num,
        train_py_source=read("train.py"),
        morph_factory_source=read("morphology_factory.py"),
        smpl_trajectory_url=smpl_url,
    )
    # result = { tracking_err, er16_success_prob, fitness_score,
    #            replay_mp4_url, ckpt_url, traj_npz_url, reasoning_md }

    # Step C: persist to Supabase
    supabase.table("iterations").insert({
        "evolution_id": evo_id,
        "iter_num": iter_num,
        **result,
        "train_py_diff": diff(prev_train_py, train_py),
        "morph_factory_diff": diff(prev_morph, morph_factory),
    })
    # Supabase Realtime pushes row to frontend automatically

    # Step D: keep-best
    if result["fitness_score"] > best_score * 1.01:
        best_score = result["fitness_score"]
        supabase.table("evolutions").update({"best_iteration_id": iter_id})
        no_improvement_count = 0
    else:
        no_improvement_count += 1

    # Step E: stop conditions
    if (no_improvement_count >= 5
            or elapsed_hours >= 2
            or modal_spend_usd() >= 50
            or stop_requested()):
        break
```

### 6.4 Fitness function

```
score = 0.6 × (1 − normalized_tracking_error) + 0.4 × er16_success_probability
```

- **tracking_error**: mean L2 distance (radians) between GNN-predicted joint angles and retargeted SMPL trajectory, averaged over 240 frames. Normalized by max possible error (π radians per joint × num_joints).
- **er16_success_prob**: Gemini Robotics-ER 1.6 called with replay_mp4 + success_criteria string → returns P(success) ∈ [0,1]. One API call per iteration (~$0.02).
- **Keep-best threshold**: new score must exceed current best by >1% to replace.

### 6.5 Stop controls (dashboard)

- **Stop button**: sets `stop_requested=True` in SQLite; orchestrator checks at top of each iteration. Graceful exit after current iter completes.
- **Mark as best button**: POST /evolutions/{id}/mark-best/{iter_id} → overrides keep-best pointer in Supabase. No impact on running loop.

### 6.6 Cost alarm

Before each iteration: `if modal_spend_usd() >= 50: break`. Checked via Modal Python SDK `App.stats()`. Logs warning + sends Supabase notification event.

---

## 7. Morphology design (VAE)

### 7.1 Parametric space

```python
@dataclass(frozen=True)
class MorphologyParams:
    num_arms:        int    # 0..2
    num_legs:        int    # 2..4
    has_torso:       bool
    torso_length:    float  # 0.2..0.6 m
    arm_length:      float  # 0.3..0.8 m
    leg_length:      float  # 0.4..1.0 m
    arm_dof:         int    # 3..7
    leg_dof:         int    # 3..6
    spine_dof:       int    # 0..3
    joint_damping:   float  # 0.01..1.0
    joint_stiffness: float  # 1..100
    friction:        float  # 0.3..1.2
```

12 parameters (4 discrete + 8 continuous).

### 7.2 VAE architecture

```
Encoder: 12-dim → MLP(64, 64) → (μ ∈ R^8, σ ∈ R^8)
Decoder: z ∈ R^8 → MLP(64, 64) → 12-dim (softmax heads for discrete, linear for continuous)
Prior:   N(0, I)
Loss:    ELBO = reconstruction_MSE + β × KL_divergence  (β=0.5)
```

### 7.3 Training (one-time, pre-evolution)

1. Generate 10,000 synthetic `MorphologyParams` by uniform sampling.
2. Filter to ~2,000 that pass: (a) URDF XML validation, (b) MuJoCo model load, (c) stable under gravity for 1 second. **Note:** gravity filter runs batched via MuJoCo's `mjx` (JAX-backed vectorized sim) — 10k URDFs in ~8 min on A10G, not 2.8h on CPU.
3. Train VAE for 200 epochs on A10G (~40 min, ~$0.73).
4. Save checkpoint to Modal volume `autoresearch-artifacts`.

### 7.4 URDF factory (`morphology_factory.py`)

- Builds URDF XML string from `MorphologyParams` via string-template composition.
- `sample_from_vae(ckpt, seed)`: samples z ~ N(0,I), decodes to params, post-processes discrete values, calls `build(params)`.
- Agent edits this file to change parameter ranges, add new limb types, etc.

---

## 8. GNN controller

### 8.1 Graph construction

- **Nodes** = rigid body links (10–20 nodes per morphology)
- **Edges** = joints, bidirectional
- **Node features** (16-dim per timestep): joint angle, joint velocity, mass, link length, inertia diagonal (3), CoM position relative to root (3), link-type one-hot (4)
- **Edge features** (6-dim): joint type one-hot (revolute/prismatic/fixed), joint axis (3), damping, stiffness

### 8.2 Architecture (fixed — not agent-editable)

```python
class MorphologyAgnosticGNN(nn.Module):
    encoder  = nn.Linear(16, 64)
    edge_enc = nn.Linear(6, 64)
    mp1 = GATv2Conv(64,    64, heads=4, edge_dim=64)
    mp2 = GATv2Conv(64*4,  64, heads=4, edge_dim=64)
    mp3 = GATv2Conv(64*4,  64, heads=1, edge_dim=64)
    decoder  = nn.Linear(64, 1)   # → scalar torque per joint
```

~180K parameters. GATv2 (graph attention v2): message weights depend on both sender and receiver state. Shared weights across morphologies — morphology encoded in node/edge features, not layer shapes.

### 8.3 Training (imitation learning, per iteration)

```python
# train.py — agent can edit epoch count (hard cap: 40)
for epoch in range(epochs):          # default 40, agent-tunable ≤ 40
    for t in range(T - 1):
        features = build_node_features(morphology, env.qpos, env.qvel)
        tau      = gnn(features, edge_index)   # predicted torques
        env.step(tau)
        loss += MSE(env.qpos, q_target[t+1])   # behavioral cloning
    loss.backward(); optimizer.step()
```

Target trajectory `q_target` = retargeted SMPL-X trajectory (joint angles in morphology frame). **No RL, no reward shaping. Imitation only.** Converges in ~4 min on A10G.

### 8.4 SMPL-X → morphology retargeting (per iteration)

GVHMR outputs SMPL-X joint angles for a fixed 24-joint human skeleton. Each VAE-sampled morphology has a different joint count and layout. Retargeting maps the human motion into the morphology's joint space every iteration.

**Method (endpoint-matching IK, ~10s per clip on CPU):**

```python
def retarget(smpl_trajectory, morphology_urdf) -> np.ndarray:
    # 1. Forward kinematics on SMPL-X: compute world-space positions of
    #    key end-effectors (hands, feet, head, pelvis) per frame.
    ee_positions = smpl_fk(smpl_trajectory)  # shape: (T, 6, 3)

    # 2. For each frame, solve IK for the morphology to match those
    #    end-effector positions (damped least-squares IK, 10 iterations).
    q_target = np.zeros((T, morphology.num_joints))
    for t in range(T):
        q_target[t] = morphology_ik(ee_positions[t], morphology_urdf)

    return q_target  # shape: (T, num_joints) — input to GNN training
```

**Why endpoint IK, not direct joint mapping?** Joint names differ across morphologies (e.g., a 4-DOF arm has no direct equivalent to a 7-DOF arm's wrist_roll). Matching end-effectors is morphology-agnostic and always well-defined.

**Where it runs:** inside `modal_trial_runner.py`, before GNN training. `~10s` per clip; negligible vs 4-min training.

**IK library:** `pink` (Python, wraps Pinocchio) — installable in the Modal image without compilation.

### 8.5 MuJoCo rollout

- After training: reset env, run controller for 240 frames, record `trajectory.npz` + `replay.mp4`.
- Replay video uploaded to Supabase Storage bucket `replays`.
- Tracking error computed over full rollout.
- ER 1.6 called with replay_mp4 URL + `success_criteria` string.

---

## 9. Modal orchestration

### 9.1 Modal apps

```
scripts/gvhmr_modal_probe.py      # existing, reused
scripts/modal_vae_train.py        # new: one-time VAE training
scripts/modal_trial_runner.py     # new: per-iteration GNN train + rollout
```

### 9.2 Trial runner config

```python
@stub.function(
    image=image,           # torch + torch-geometric + mujoco + supabase + yt-dlp
    gpu="A10G",
    volumes={"/vol": modal.Volume.from_name("autoresearch-artifacts")},
    timeout=900,           # 15 min hard cap
    container_idle_timeout=180,   # 3 min warm-keep between iters
)
def run_trial(evolution_id, iter_num, train_py_source,
              morph_factory_source, smpl_trajectory_url, epochs=40) -> dict:
    ...
```

Cold-start penalty: ~60-120s on first iteration per evolution. Subsequent iters reuse warm container (3-min warm window covers ~2-min agent-edit gap).

### 9.3 Cost budget

| Workload | GPU | Duration | Cost |
|---|---|---|---|
| GVHMR (4 clips, one-time) | A10G | 12 min | $0.22 |
| VAE training (one-time) | A10G | 40 min | $0.73 |
| Full evolution, 20 iters | A10G | 100 min | $1.83 |
| 3 dev evolutions | A10G | 5h | $5.50 |
| Overnight demo evolution | A10G | 100 min | $1.83 |
| Dev buffer (debug, restarts) | A10G | 8h | $8.80 |
| Gemini API (~60 calls) | — | — | $1.20 |
| **Total estimated** | | | **~$20** |
| **Hard stop alarm** | | | **$50** |
| **Budget** | | | **$40** |

---

## 10. Frontend (4 screens)

**Stack:** Next.js 14 App Router · shadcn/ui · Tailwind · TanStack Query · Supabase JS SDK (Realtime) · Monaco Editor · React Three Fiber + @react-three/drei

### Screen 1 — Prompt entry

Single text input. "Analyze task" button → triggers ER 1.6 + YouTube search. Loading state while ingest pipeline runs.

### Screen 2 — Task plan review

Left: ER 1.6 structured output (task_goal, affordances as badges, success_criteria). Right: fetched YouTube clip preview (HTML5 video). "Draft research plan" button → invokes Codex/Claude CLI.

### Screen 3 — program.md HITL (Monaco editor, full-screen modal)

Buttons: **Approve** · **Edit + Approve** · **Regenerate** · **Use Claude Code fallback**. Commit to database, start evolution.

### Screen 4 — Evolution dashboard

3-pane layout + history timeline:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Run #042 · Iter 7/20 · $0.73 spent · [ Stop ]                       │
├─────────────┬────────────────────────────┬──────────────────────────┤
│ Prompt      │ Current morphology         │ Current replay           │
│ [text]      │ React Three Fiber URDF 3D  │ <video> tag, loops       │
│             │ render (isometric, PBR)    │                          │
│ Reference   │ score: 0.81                │ tracking err: 0.11       │
│ [video]     │ reasoning: "..."           │ ER16: 0.82               │
│             │ [ Mark as best ]           │                          │
├─────────────┴────────────────────────────┴──────────────────────────┤
│ EVOLUTION HISTORY (Supabase Realtime, pushes live)                  │
│ [iter1] [iter2] [iter3] [★iter4] [iter5] [iter6] [iter7⟳]           │
│  .42     .55     .61     .78★     .71     .74     ...               │
│  Click → drawer: full diff, reasoning, replay, download buttons     │
├─────────────────────────────────────────────────────────────────────┤
│ [ Approve best + Export ]                                           │
└─────────────────────────────────────────────────────────────────────┘
```

**Morphology 3D render:** parse URDF box/cylinder/sphere primitives → `@react-three/fiber` scene, isometric camera, 3 directional lights. ~150 LOC.

**Evolution history drawer:** diff view of `train.py` + `morphology_factory.py` vs previous iter (collapsed by default), full `reasoning.md`, fitness breakdown, download URDF / controller / replay.

---

## 11. Export

POST `/runs/{id}/export` produces a zip containing:

- `dataset.parquet` — LeRobot-compatible (HuggingFace lerobot format)
- `morphology.urdf` — the best morphology
- `controller.pt` — GNN checkpoint
- `evolution_log.md` — full iteration history with reasoning traces (blog post artifact)

Uploaded to Supabase Storage bucket `exports`. Download link in dashboard.

---

## 12. Testing strategy

### 12.1 Unit tests (per workstream, <60s total)

```
tests/test_morphology.py   — VAE samples → valid params; URDF factory → MuJoCo loads OK
tests/test_gnn.py          — GNN forward on synthetic 12-node graph; imitation trains on toy traj
tests/test_orchestrator.py — codex CLI wrapper invokes; Modal dispatch (mocked) round-trips
tests/test_api.py          — new endpoints return correct schema (extends test_phase3_api.py)
```

### 12.2 Integration smoke test (gates Phase 4)

```bash
make e2e-smoke
```

- Seeded clip (cached SMPL), fixed prompt
- 3 real iterations (real Modal, real Supabase, mocked Gemini + YouTube)
- Asserts: 3 rows in `iterations`, `best_iteration_id` set, export downloads `.parquet`
- Runtime: ~12 min

### 12.3 Demo rehearsal (gates submission)

Full happy path × 3 runs. If any run hiccups, fix + repeat. Demo script pinned to 10 min (3-iter evolution).

### 12.4 Explicitly out of scope

Cross-browser, mobile, auth, load testing, fuzz, failure injection, Gemini rate-limit exhaustion.

---

## 13. Parallel build plan

### 13.1 Timeline

| Phase | Wall-clock | What happens |
|---|---|---|
| E: infra | 0–1h | Supabase project + schema, Modal keys, monorepo scaffold, API keys |
| Contract | 1–2h | `packages/pipeline/types.py` + `apps/web/src/lib/types.ts` frozen |
| **Parallel (5 agents)** | **2–7h** | All 5 workstreams run concurrently |
| Integration | 7–9h | Wire 5 streams; e2e-smoke |
| Polish + devpost + blog | 9–16h | Demo recording, submission, write-up |

Total wall-clock: **16h**. 3h implicit buffer across cycles.

### 13.2 Workstreams

| Agent | Scope | Smoke target |
|---|---|---|
| **A: Backend** | FastAPI endpoints, Supabase client, ER 1.6 + YouTube + yt-dlp, local orchestrator, Codex/Claude CLI wrappers, Modal dispatch | `make smoke-api` |
| **B1: Morphology** | `MorphologyParams`, URDF factory, 2k synthetic URDF generator, VAE trainer, Modal VAE script | `make smoke-morph` |
| **B2: Controller** | GNN (`gnn.py`), imitation training loop, MuJoCo env wrapper, fitness eval (tracking + ER 1.6) | `make smoke-gnn` |
| **C: Frontend** | Next.js scaffold, 4 screens, Monaco editor, React Three Fiber, Supabase Realtime, history drawer | `make smoke-fe` (manual) |
| **D: Seed + blog** | 4 cached SMPL clips, blog post outline + 4 core paragraphs, `evolution_log.md` template, 2-min demo script | `make smoke-seed` |

### 13.3 Interface contracts (frozen before dispatch)

```python
# packages/pipeline/types.py
@dataclass(frozen=True)
class MorphologyParams: ...

@dataclass(frozen=True)
class TrialResult:
    tracking_error: float
    er16_success_prob: float
    fitness_score: float
    replay_mp4_url: str
    controller_ckpt_url: str
    trajectory_npz_url: str
    reasoning_md: str

@dataclass(frozen=True)
class EvolutionConfig:
    max_iters: int = 20
    max_hours: float = 2.0
    cost_alarm_usd: float = 50.0
    fitness_weights: tuple = (0.6, 0.4)
    keep_best_threshold: float = 0.01
```

---

## 14. What is NOT in scope

- Dedalus Labs hosting (future work; local orchestrator sufficient for v1 demo)
- User video upload
- Authentication / multi-user
- Cross-browser / mobile
- Isaac Sim / Isaac Lab
- RL-based controller (imitation learning only)
- Per-iteration HITL approval (one gate at program.md)
- Vector search / semantic video retrieval
- Custom retargeting code (SMPL → morphology via existing OmniH2O/PHC ladder)
- Multi-robot / multi-morphology parallel evolution
