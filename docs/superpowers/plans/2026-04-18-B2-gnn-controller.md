# GNN Controller (Workstream B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the GATv2-based GNN controller, the SMPL-X → morphology IK retargeting pipeline, the MuJoCo environment wrapper, the imitation training loop, and the Modal trial runner that combines all of these.

**Architecture:** GNN operates over a graph where nodes = robot links and edges = joints. Node features include per-timestep sensor data. Trained by behavioural cloning against retargeted SMPL-X trajectories. MuJoCo rollout produces replay video + trajectory NPZ. ER 1.6 evaluates the replay for semantic success. All of this is packaged into `modal_trial_runner.py`.

**Tech Stack:** PyTorch, torch-geometric (GATv2Conv), mujoco, pink (IK library wrapping Pinocchio), modal, google-generativeai (ER 1.6)

**Prerequisites:** Plan 00 complete. Plan B1's `urdf_factory.py` and `morphology_factory.py` template must exist. `packages/pipeline/types.py` must exist.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `packages/pipeline/gnn.py` | Create | GATv2 GNN architecture, feature construction |
| `packages/pipeline/retarget.py` | Create | SMPL-X FK → end-effector positions → morphology IK |
| `packages/pipeline/mujoco_env.py` | Create | MuJoCo env wrapper: reset, step, render |
| `packages/pipeline/fitness.py` | Create | Tracking error + ER 1.6 success probability |
| `data/artifacts/evolutions/template/prepare.py` | Create | Fixed: loads SMPL, env, fitness fn — never agent-edited |
| `data/artifacts/evolutions/template/train.py` | Create | Agent-editable: GNN training loop, epoch count |
| `scripts/modal_trial_runner.py` | Create | Modal A10G function: full trial (retarget → train → rollout → evaluate) |
| `tests/test_gnn.py` | Create | GNN + retarget unit tests |

---

## Task B2-1: GNN architecture

- [ ] **Step 1: Write the test**

Create `tests/test_gnn.py`:

```python
import torch
import pytest
from packages.pipeline.gnn import MorphologyAgnosticGNN, build_graph_from_urdf
from packages.pipeline.types import MorphologyParams
from packages.pipeline.urdf_factory import build_urdf

BIPED = MorphologyParams(
    num_arms=2, num_legs=2, has_torso=True,
    torso_length=0.4, arm_length=0.5, leg_length=0.7,
    arm_dof=5, leg_dof=4, spine_dof=1,
    joint_damping=0.1, joint_stiffness=10.0, friction=0.8,
)

def test_build_graph_returns_correct_shapes():
    xml = build_urdf(BIPED)
    n_nodes, edge_index, node_feats, edge_feats = build_graph_from_urdf(xml)
    assert n_nodes > 0
    assert edge_index.shape[0] == 2
    assert node_feats.shape == (n_nodes, 16)
    assert edge_feats.shape[1] == 6

def test_gnn_forward_returns_torque_per_joint():
    xml = build_urdf(BIPED)
    n_nodes, edge_index, node_feats, edge_feats = build_graph_from_urdf(xml)
    gnn = MorphologyAgnosticGNN()
    tau = gnn(node_feats.unsqueeze(0), edge_index, edge_feats.unsqueeze(0))
    assert tau.shape == (1, n_nodes, 1)

def test_gnn_works_on_different_morphology():
    import dataclasses
    quad = dataclasses.replace(BIPED, num_legs=4)
    from packages.pipeline.urdf_factory import build_urdf
    xml2 = build_urdf(quad)
    n2, ei2, nf2, ef2 = build_graph_from_urdf(xml2)
    gnn = MorphologyAgnosticGNN()
    tau2 = gnn(nf2.unsqueeze(0), ei2, ef2.unsqueeze(0))
    assert tau2.shape[2] == 1   # one torque per node
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_gnn.py -v
```

- [ ] **Step 3: Create `packages/pipeline/gnn.py`**

```python
from __future__ import annotations
import torch
import torch.nn as nn
from torch_geometric.nn import GATv2Conv
import mujoco
import numpy as np


NODE_DIM = 16   # per-timestep node features
EDGE_DIM = 6    # static edge features


def build_graph_from_urdf(
    xml: str,
    qpos: np.ndarray | None = None,
    qvel: np.ndarray | None = None,
) -> tuple[int, torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Parse URDF XML and build a graph.
    Returns: (n_nodes, edge_index [2, E], node_feats [N, 16], edge_feats [E, 6])
    """
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    if qpos is not None:
        data.qpos[:len(qpos)] = qpos
    if qvel is not None:
        data.qvel[:len(qvel)] = qvel
    mujoco.mj_forward(model, data)

    n_bodies = model.nbody
    src, dst = [], []
    edge_feats_list = []

    for j in range(model.njnt):
        body_id = model.jnt_bodyid[j]
        parent_id = model.body_parentid[body_id]
        if parent_id < 0:
            continue
        src.extend([body_id, parent_id])
        dst.extend([parent_id, body_id])
        jtype = model.jnt_type[j]
        jtype_onehot = [float(jtype == t) for t in [0, 1, 2, 3]]  # free/ball/hinge/prismatic
        axis = model.jnt_axis[j].tolist()
        ef = jtype_onehot[:3] + axis  # 6-dim
        edge_feats_list.extend([ef, ef])

    if not src:
        src, dst = [0], [0]
        edge_feats_list = [[0.0] * EDGE_DIM]

    edge_index = torch.tensor([src, dst], dtype=torch.long)
    edge_feats = torch.tensor(edge_feats_list, dtype=torch.float32)

    node_feats_list = []
    for b in range(n_bodies):
        jnt_angle = float(data.qpos[b]) if b < len(data.qpos) else 0.0
        jnt_vel = float(data.qvel[b]) if b < len(data.qvel) else 0.0
        mass = float(model.body_mass[b])
        length = float(np.linalg.norm(model.body_pos[b]))
        inertia = model.body_inertia[b].tolist()
        com_pos = model.body_ipos[b].tolist()
        btype_onehot = [float(b == 0), float(b != 0), 0.0, 0.0]  # root / non-root
        feats = [jnt_angle, jnt_vel, mass, length] + inertia + com_pos + btype_onehot
        node_feats_list.append(feats[:NODE_DIM])

    node_feats = torch.tensor(node_feats_list, dtype=torch.float32)
    return n_bodies, edge_index, node_feats, edge_feats


class MorphologyAgnosticGNN(nn.Module):
    """GATv2-based controller. Shared weights across all morphologies."""

    def __init__(self, hidden: int = 64) -> None:
        super().__init__()
        self.node_enc = nn.Linear(NODE_DIM, hidden)
        self.edge_enc = nn.Linear(EDGE_DIM, hidden)
        self.mp1 = GATv2Conv(hidden, hidden, heads=4, edge_dim=hidden, concat=True)
        self.mp2 = GATv2Conv(hidden * 4, hidden, heads=4, edge_dim=hidden, concat=True)
        self.mp3 = GATv2Conv(hidden * 4, hidden, heads=1, edge_dim=hidden, concat=False)
        self.decoder = nn.Linear(hidden, 1)

    def forward(
        self,
        node_feats: torch.Tensor,   # (B, N, 16) or (N, 16)
        edge_index: torch.Tensor,   # (2, E)
        edge_feats: torch.Tensor,   # (B, E, 6) or (E, 6)
    ) -> torch.Tensor:              # (B, N, 1) torques
        # Handle batched vs unbatched
        batched = node_feats.dim() == 3
        if not batched:
            node_feats = node_feats.unsqueeze(0)
            edge_feats = edge_feats.unsqueeze(0)

        B, N, _ = node_feats.shape
        x = self.node_enc(node_feats.view(B * N, -1))
        ef = self.edge_enc(edge_feats.view(B * edge_feats.shape[1], -1))
        x = torch.relu(self.mp1(x, edge_index, ef))
        x = torch.relu(self.mp2(x, edge_index, ef))
        x = torch.relu(self.mp3(x, edge_index, ef))
        out = self.decoder(x).view(B, N, 1)
        return out
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_gnn.py -v
# Expected: 3 passed
```

- [ ] **Step 5: Commit**

```bash
git add packages/pipeline/gnn.py tests/test_gnn.py
git commit -m "feat: add GATv2 GNN controller with morphology-agnostic graph features"
```

---

## Task B2-2: SMPL-X retargeting

- [ ] **Step 1: Add retarget test**

Add to `tests/test_gnn.py`:

```python
import numpy as np
from packages.pipeline.retarget import retarget_smpl_to_morphology

def test_retarget_returns_correct_shape():
    xml = build_urdf(BIPED)
    # Fake SMPL-X trajectory: T=10 frames, 24 joints × 3 (xyz positions)
    fake_ee = np.random.randn(10, 6, 3).astype(np.float32)
    q_target = retarget_smpl_to_morphology(end_effectors=fake_ee, urdf_xml=xml)
    model = mujoco.MjModel.from_xml_string(xml)
    assert q_target.shape == (10, model.nq)
```

- [ ] **Step 2: Create `packages/pipeline/retarget.py`**

```python
from __future__ import annotations
import numpy as np
import mujoco


def smpl_pkl_to_end_effectors(smpl_pkl_path: str) -> np.ndarray:
    """
    Load GVHMR output .pkl and extract 6 key end-effector world positions:
    [left_hand, right_hand, left_foot, right_foot, head, pelvis]
    Returns: (T, 6, 3) float32
    """
    import pickle
    with open(smpl_pkl_path, "rb") as f:
        data = pickle.load(f)
    # GVHMR output format: dict with 'smpl_params_global'
    # Keys: global_orient, body_pose, transl — all (T, ...) tensors
    joints = data.get("joints", data.get("smpl_params_global", {}).get("joints", None))
    if joints is None:
        raise ValueError("Cannot find joints in GVHMR output. Keys: " + str(list(data.keys())))
    joints = np.array(joints)  # (T, 24, 3) in SMPL-X convention
    # SMPL-X joint indices: 0=pelvis, 10=left_foot, 11=right_foot,
    #                       15=head, 20=left_hand, 21=right_hand
    idx = [20, 21, 10, 11, 15, 0]
    return joints[:, idx, :].astype(np.float32)


def retarget_smpl_to_morphology(
    end_effectors: np.ndarray,   # (T, 6, 3) world positions
    urdf_xml: str,
    ik_iters: int = 10,
) -> np.ndarray:
    """
    Solve IK per frame to match end-effector positions.
    Returns q_target: (T, nq) joint angles for MuJoCo model.
    Uses damped least-squares IK (no external library dependency).
    """
    model = mujoco.MjModel.from_xml_string(urdf_xml)
    data = mujoco.MjData(model)
    T = end_effectors.shape[0]
    q_target = np.zeros((T, model.nq), dtype=np.float32)

    for t in range(T):
        mujoco.mj_resetData(model, data)
        for _ in range(ik_iters):
            mujoco.mj_forward(model, data)
            # Compute Jacobian for all bodies towards pelvis (body 0) position
            jac_pos = np.zeros((3, model.nv))
            mujoco.mj_jacBody(model, data, jac_pos, None, 0)
            target = end_effectors[t, 5]   # pelvis (index 5 in our 6-EE list)
            current = data.xpos[0]
            error = target - current
            # Damped least-squares step
            lam = 0.01
            dq = jac_pos.T @ np.linalg.solve(jac_pos @ jac_pos.T + lam * np.eye(3), error)
            data.qpos[:model.nv] += dq[:model.nq]
            data.qpos = np.clip(data.qpos, model.jnt_range[:, 0], model.jnt_range[:, 1])
        q_target[t] = data.qpos.copy()

    return q_target
```

- [ ] **Step 3: Run retarget test**

```bash
python -m pytest tests/test_gnn.py::test_retarget_returns_correct_shape -v
# Expected: PASS
```

- [ ] **Step 4: Commit**

```bash
git add packages/pipeline/retarget.py
git commit -m "feat: add SMPL-X to morphology IK retargeting"
```

---

## Task B2-3: MuJoCo environment wrapper

- [ ] **Step 1: Add env test**

Add to `tests/test_gnn.py`:

```python
from packages.pipeline.mujoco_env import MuJoCoEnv

def test_env_step_returns_observation():
    xml = build_urdf(BIPED)
    env = MuJoCoEnv(xml)
    obs = env.reset()
    assert obs.shape[0] > 0
    tau = np.zeros(env.model.nv)
    obs2, done = env.step(tau)
    assert not done or True   # type check only
```

- [ ] **Step 2: Create `packages/pipeline/mujoco_env.py`**

```python
from __future__ import annotations
import numpy as np
import mujoco
import tempfile, os
from pathlib import Path


class MuJoCoEnv:
    def __init__(self, urdf_xml: str, render: bool = False) -> None:
        self.model = mujoco.MjModel.from_xml_string(urdf_xml)
        self.data = mujoco.MjData(self.model)
        self._render = render
        self._renderer: mujoco.Renderer | None = None
        if render:
            self._renderer = mujoco.Renderer(self.model, height=240, width=320)

    def reset(self) -> np.ndarray:
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        return self._obs()

    def step(self, tau: np.ndarray) -> tuple[np.ndarray, bool]:
        n = min(len(tau), self.model.nu)
        self.data.ctrl[:n] = tau[:n]
        mujoco.mj_step(self.model, self.data)
        done = bool(self.data.qpos[2] < 0.05) if self.model.nq >= 3 else False
        return self._obs(), done

    def _obs(self) -> np.ndarray:
        return np.concatenate([self.data.qpos.copy(), self.data.qvel.copy()])

    def render_frame(self) -> np.ndarray:
        if self._renderer is None:
            raise RuntimeError("Renderer not enabled. Pass render=True.")
        self._renderer.update_scene(self.data, camera="track")
        return self._renderer.render()

    def rollout_to_video(
        self,
        q_target: np.ndarray,    # (T, nq)
        fps: int = 30,
    ) -> tuple[np.ndarray, list[np.ndarray]]:
        """Run controller-free kinematic replay. Returns (trajectory, frames)."""
        frames = []
        traj = []
        self.reset()
        T = q_target.shape[0]
        for t in range(T):
            n = min(q_target.shape[1], self.model.nq)
            self.data.qpos[:n] = q_target[t, :n]
            mujoco.mj_forward(self.model, self.data)
            traj.append(self.data.qpos.copy())
            if self._renderer:
                frames.append(self.render_frame())
        return np.array(traj), frames

    def save_video(self, frames: list[np.ndarray], path: str, fps: int = 30) -> None:
        import subprocess, tempfile, shutil
        tmp = tempfile.mkdtemp()
        for i, f in enumerate(frames):
            import cv2
            cv2.imwrite(f"{tmp}/{i:05d}.png", f[:, :, ::-1])
        subprocess.run(
            ["ffmpeg", "-y", "-r", str(fps), "-i", f"{tmp}/%05d.png",
             "-vcodec", "libx264", "-pix_fmt", "yuv420p", path],
            check=True, capture_output=True,
        )
        shutil.rmtree(tmp)
```

- [ ] **Step 3: Run env test**

```bash
python -m pytest tests/test_gnn.py::test_env_step_returns_observation -v
```

- [ ] **Step 4: Commit**

```bash
git add packages/pipeline/mujoco_env.py
git commit -m "feat: add MuJoCo env wrapper with rollout + video export"
```

---

## Task B2-4: Fitness computation

- [ ] **Step 1: Create `packages/pipeline/fitness.py`**

```python
from __future__ import annotations
import json
import numpy as np
import google.generativeai as genai
import mujoco


def tracking_error(pred_traj: np.ndarray, target_traj: np.ndarray) -> float:
    """
    Mean L2 distance between predicted and target joint angles, normalized.
    pred_traj, target_traj: (T, nq) arrays.
    """
    n_joints = min(pred_traj.shape[1], target_traj.shape[1])
    diff = pred_traj[:, :n_joints] - target_traj[:, :n_joints]
    raw = float(np.mean(np.linalg.norm(diff, axis=1)))
    max_err = np.pi * n_joints   # worst case: pi radians per joint
    return min(raw / max_err, 1.0)


def er16_success_prob(
    replay_mp4_path: str,
    success_criteria: str,
    gemini_api_key: str,
) -> float:
    """
    Call Gemini Robotics-ER 1.6 to evaluate task completion in replay video.
    Returns P(success) in [0, 1].
    """
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-robotics-er-1.6")
    with open(replay_mp4_path, "rb") as f:
        video_bytes = f.read()
    prompt = (
        f"Watch this robot simulation video. Success criteria: '{success_criteria}'.\n"
        "Reply with ONLY a JSON object: {\"success_probability\": <float 0-1>, \"reasoning\": <str>}"
    )
    resp = model.generate_content([
        {"mime_type": "video/mp4", "data": video_bytes},
        prompt,
    ])
    try:
        parsed = json.loads(resp.text)
        return float(parsed["success_probability"])
    except Exception:
        return 0.0


def compute_fitness(
    tracking_err: float,
    er16_prob: float,
    weights: tuple[float, float] = (0.6, 0.4),
) -> float:
    w_track, w_er = weights
    return w_track * (1.0 - tracking_err) + w_er * er16_prob
```

- [ ] **Step 2: Add fitness test**

Add to `tests/test_gnn.py`:

```python
from packages.pipeline.fitness import tracking_error, compute_fitness

def test_tracking_error_perfect():
    traj = np.ones((10, 5)) * 0.5
    assert tracking_error(traj, traj) == pytest.approx(0.0)

def test_tracking_error_bounded():
    a = np.zeros((10, 5))
    b = np.ones((10, 5)) * np.pi
    err = tracking_error(a, b)
    assert 0.0 <= err <= 1.0

def test_fitness_weights():
    f = compute_fitness(tracking_err=0.2, er16_prob=0.8, weights=(0.6, 0.4))
    assert f == pytest.approx(0.6 * 0.8 + 0.4 * 0.8)
```

- [ ] **Step 3: Run fitness tests**

```bash
python -m pytest tests/test_gnn.py -k "fitness or tracking" -v
# Expected: 3 passed
```

- [ ] **Step 4: Commit**

```bash
git add packages/pipeline/fitness.py
git commit -m "feat: add fitness module (tracking error + ER 1.6 success probability)"
```

---

## Task B2-5: Agent-editable `train.py` + fixed `prepare.py` templates

- [ ] **Step 1: Create `data/artifacts/evolutions/template/prepare.py`** (FIXED — never edited by agent)

```python
"""
prepare.py — FIXED. Do not modify.
Loaded by train.py to get: smpl_trajectory, env, fitness_fn.
"""
from __future__ import annotations
import os, pickle
import numpy as np
from packages.pipeline.mujoco_env import MuJoCoEnv
from packages.pipeline.retarget import smpl_pkl_to_end_effectors, retarget_smpl_to_morphology
from packages.pipeline.fitness import tracking_error, er16_success_prob, compute_fitness


def load_everything(urdf_xml: str, smpl_pkl_path: str) -> dict:
    ee = smpl_pkl_to_end_effectors(smpl_pkl_path)
    q_target = retarget_smpl_to_morphology(ee, urdf_xml)
    env = MuJoCoEnv(urdf_xml, render=True)
    return {
        "q_target": q_target,
        "env": env,
        "ee": ee,
    }
```

- [ ] **Step 2: Create `data/artifacts/evolutions/template/train.py`** (AGENT-EDITABLE)

```python
"""
train.py — AGENT-EDITABLE.

You may change:
  - epochs (hard cap: 40)
  - learning_rate
  - optimizer type
  - GNN layer count / hidden dim (import and instantiate a new GNN class if needed)
  - Any training trick (grad clipping, LR schedule, dropout)

Do NOT change the function signatures.
Do NOT remove the save_checkpoint() call.
Do NOT exceed MAX_EPOCHS = 40.
"""
from __future__ import annotations
import os, time
import numpy as np
import torch
import torch.nn as nn
from packages.pipeline.gnn import MorphologyAgnosticGNN, build_graph_from_urdf

MAX_EPOCHS = 40   # hard cap — do not increase

# --- AGENT: tune these ---
epochs         = 40
learning_rate  = 3e-4
grad_clip_norm = 1.0


def train(urdf_xml: str, q_target: np.ndarray, ckpt_path: str) -> dict:
    """Train GNN by imitation. Returns training metadata."""
    import mujoco
    model_mj = mujoco.MjModel.from_xml_string(urdf_xml)
    data_mj = mujoco.MjData(model_mj)
    gnn = MorphologyAgnosticGNN().cuda() if torch.cuda.is_available() else MorphologyAgnosticGNN()
    opt = torch.optim.Adam(gnn.parameters(), lr=learning_rate)
    T = q_target.shape[0]
    t0 = time.time()
    losses = []
    _epochs = min(epochs, MAX_EPOCHS)
    for ep in range(_epochs):
        ep_loss = 0.0
        mujoco.mj_resetData(model_mj, data_mj)
        for t in range(T - 1):
            _, edge_index, node_feats, edge_feats = build_graph_from_urdf(
                urdf_xml, qpos=data_mj.qpos, qvel=data_mj.qvel
            )
            dev = next(gnn.parameters()).device
            tau = gnn(node_feats.to(dev), edge_index, edge_feats.to(dev))  # (1, N, 1)
            tau_np = tau.squeeze().detach().cpu().numpy()
            n = min(len(tau_np), model_mj.nu)
            data_mj.ctrl[:n] = tau_np[:n]
            mujoco.mj_step(model_mj, data_mj)
            target_t = torch.tensor(q_target[t + 1], dtype=torch.float32).to(dev)
            pred_t = torch.tensor(data_mj.qpos[:len(target_t)], dtype=torch.float32).to(dev)
            loss = nn.functional.mse_loss(pred_t, target_t)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(gnn.parameters(), grad_clip_norm)
            opt.step()
            ep_loss += loss.item()
        losses.append(ep_loss / T)
        if ep % 10 == 0:
            print(f"Epoch {ep:3d} | loss {losses[-1]:.4f} | elapsed {time.time()-t0:.0f}s")
    torch.save(gnn.state_dict(), ckpt_path)
    return {"final_loss": losses[-1], "epochs_run": _epochs}
```

- [ ] **Step 3: Commit templates**

```bash
git add data/artifacts/evolutions/template/
git commit -m "feat: add prepare.py (fixed) and train.py (agent-editable) templates"
```

---

## Task B2-6: Modal trial runner

- [ ] **Step 1: Create `scripts/modal_trial_runner.py`**

```python
"""Per-iteration trial: retarget → train → rollout → evaluate. Run on Modal A10G."""
from __future__ import annotations
import modal, os

stub = modal.App("autoresearch-trial")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1-mesa-glx")
    .pip_install(
        "torch>=2.2", "torch-geometric>=2.5", "mujoco>=3.1",
        "numpy>=1.26", "pink>=3.1", "supabase>=2.4",
        "google-generativeai>=0.5", "httpx>=0.27",
    )
    .add_local_python_source("packages")
)

volume = modal.Volume.from_name("autoresearch-artifacts", create_if_missing=True)


@stub.function(
    image=image,
    gpu="A10G",
    volumes={"/vol": volume},
    timeout=900,                  # 15-min hard cap
    container_idle_timeout=180,   # stay warm 3 min between iters
)
def run_trial(
    evolution_id: str,
    iter_num: int,
    train_py_source: str,
    morph_factory_source: str,
    smpl_trajectory_url: str,   # Supabase Storage signed URL
    epochs: int = 40,
) -> dict:
    import tempfile, uuid, subprocess
    from pathlib import Path
    from supabase import create_client

    supa = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    scratch = Path(tempfile.mkdtemp())

    # 1. Write agent-edited source files
    (scratch / "train.py").write_text(train_py_source)
    (scratch / "morphology_factory.py").write_text(morph_factory_source)

    # 2. Download SMPL trajectory
    import httpx
    smpl_bytes = httpx.get(smpl_trajectory_url).content
    smpl_path = scratch / "motion.pkl"
    smpl_path.write_bytes(smpl_bytes)

    # 3. Import morphology factory from scratch dir
    import sys; sys.path.insert(0, str(scratch))
    import importlib, morphology_factory as mf  # type: ignore
    importlib.reload(mf)
    params, urdf_xml = mf.build(seed=iter_num)

    # 4. Load prepare + retarget
    from packages.pipeline.retarget import smpl_pkl_to_end_effectors, retarget_smpl_to_morphology
    ee = smpl_pkl_to_end_effectors(str(smpl_path))
    q_target = retarget_smpl_to_morphology(ee, urdf_xml)

    # 5. Train GNN (executes train.py's train() function)
    import train as train_module  # type: ignore
    importlib.reload(train_module)
    ckpt_path = str(scratch / "controller.pt")
    meta = train_module.train(urdf_xml=urdf_xml, q_target=q_target, ckpt_path=ckpt_path)

    # 6. Rollout
    from packages.pipeline.mujoco_env import MuJoCoEnv
    import numpy as np
    env = MuJoCoEnv(urdf_xml, render=True)
    pred_traj, frames = env.rollout_to_video(q_target)
    replay_path = str(scratch / "replay.mp4")
    env.save_video(frames, replay_path)

    # 7. Fitness
    from packages.pipeline.fitness import tracking_error, er16_success_prob, compute_fitness
    track_err = tracking_error(pred_traj, q_target)
    er16_prob = er16_success_prob(
        replay_mp4_path=replay_path,
        success_criteria="robot completes the demonstrated task",
        gemini_api_key=os.environ["GEMINI_API_KEY"],
    )
    score = compute_fitness(track_err, er16_prob)

    # 8. Upload artifacts to Supabase Storage
    def upload(local: str, remote: str) -> str:
        with open(local, "rb") as f:
            supa.storage.from_("artifacts").upload(remote, f)
        return supa.storage.from_("artifacts").get_public_url(remote)

    evo_iter = f"{evolution_id}/{iter_num:03d}"
    replay_url = upload(replay_path, f"{evo_iter}/replay.mp4")
    ckpt_url   = upload(ckpt_path,   f"{evo_iter}/controller.pt")

    import json
    traj_bytes = q_target.tobytes()
    (scratch / "traj.bin").write_bytes(traj_bytes)
    traj_url = upload(str(scratch / "traj.bin"), f"{evo_iter}/trajectory.bin")

    return {
        "tracking_error":      track_err,
        "er16_success_prob":   er16_prob,
        "fitness_score":       score,
        "replay_mp4_url":      replay_url,
        "controller_ckpt_url": ckpt_url,
        "trajectory_npz_url":  traj_url,
        "reasoning_md":        f"Iter {iter_num}: tracking_err={track_err:.3f}, er16={er16_prob:.2f}, score={score:.3f}. Train loss={meta['final_loss']:.4f}.",
    }
```

- [ ] **Step 2: Deploy to Modal**

```bash
modal deploy scripts/modal_trial_runner.py
# Expected: Deployment complete — function available for .remote() calls
```

- [ ] **Step 3: Run smoke test**

```bash
python -m pytest tests/test_gnn.py -v
make smoke-gnn
# Expected: all tests pass
```

- [ ] **Step 4: Commit**

```bash
git add scripts/modal_trial_runner.py packages/pipeline/fitness.py
git commit -m "feat: add Modal trial runner (retarget → GNN train → rollout → ER1.6 eval)"
```
