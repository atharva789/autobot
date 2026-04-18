# Morphology + VAE (Workstream B1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the parametric URDF factory, train a VAE over the 12-parameter morphology space on Modal, and produce the agent-editable `morphology_factory.py` template.

**Architecture:** `MorphologyParams` dataclass (from Plan 00 types.py) drives a string-template URDF builder. A small VAE (encoder/decoder over 12 params, 8-dim latent) is trained once on 2k filtered synthetic URDFs. The trained checkpoint lives in the Modal volume `autoresearch-artifacts` and is loaded by `morphology_factory.py` at sample time.

**Tech Stack:** PyTorch, mujoco (Python bindings), mujoco.mjx (JAX-vectorized for batch filtering), modal

**Prerequisites:** Plan 00 complete. `packages/pipeline/types.py` must exist with `MorphologyParams`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `packages/pipeline/urdf_factory.py` | Create | Build URDF XML string from MorphologyParams |
| `packages/pipeline/urdf_generator.py` | Create | Generate 10k synthetic MorphologyParams + filter to ~2k valid |
| `packages/pipeline/vae.py` | Create | VAE model (encoder, decoder, sample, ELBO loss) |
| `scripts/modal_vae_train.py` | Create | Modal app: train VAE on A10G, save to volume |
| `data/artifacts/evolutions/template/morphology_factory.py` | Create | Agent-editable template: exposes sample_from_vae() and build() |
| `tests/test_morphology.py` | Create | Unit tests for factory + VAE |

---

## Task B1-1: URDF factory

- [ ] **Step 1: Write the test**

Create `tests/test_morphology.py`:

```python
import pytest
import mujoco
from packages.pipeline.types import MorphologyParams
from packages.pipeline.urdf_factory import build_urdf, validate_urdf

BIPED = MorphologyParams(
    num_arms=2, num_legs=2, has_torso=True,
    torso_length=0.4, arm_length=0.5, leg_length=0.7,
    arm_dof=5, leg_dof=4, spine_dof=1,
    joint_damping=0.1, joint_stiffness=10.0, friction=0.8,
)

def test_build_returns_xml_string():
    xml = build_urdf(BIPED)
    assert isinstance(xml, str)
    assert "<mujoco" in xml
    assert "<body" in xml

def test_urdf_loads_in_mujoco():
    xml = build_urdf(BIPED)
    model = mujoco.MjModel.from_xml_string(xml)
    assert model.nq > 0   # has degrees of freedom

def test_validate_rejects_bad_params():
    bad = MorphologyParams(
        num_arms=0, num_legs=2, has_torso=False,
        torso_length=0.0,  # invalid: too small
        arm_length=0.5, leg_length=0.7,
        arm_dof=5, leg_dof=4, spine_dof=0,
        joint_damping=0.1, joint_stiffness=10.0, friction=0.8,
    )
    assert not validate_urdf(bad)

def test_validate_accepts_good_params():
    assert validate_urdf(BIPED)
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_morphology.py::test_build_returns_xml_string -v
```

- [ ] **Step 3: Create `packages/pipeline/urdf_factory.py`**

```python
from __future__ import annotations
from packages.pipeline.types import MorphologyParams


def validate_urdf(p: MorphologyParams) -> bool:
    """Return False if params are geometrically infeasible."""
    if p.torso_length < 0.15 or p.torso_length > 0.65:
        return False
    if p.arm_length < 0.25 or p.arm_length > 0.85:
        return False
    if p.leg_length < 0.35 or p.leg_length > 1.05:
        return False
    if p.num_legs not in (2, 4) or p.num_arms not in (0, 1, 2):
        return False
    return True


def build_urdf(p: MorphologyParams) -> str:
    """Return a MuJoCo MJCF XML string for the given morphology params."""
    parts = [_header(p), _worldbody(p), _actuators(p), _footer()]
    return "\n".join(parts)


def _header(p: MorphologyParams) -> str:
    return f"""<mujoco model="automorph">
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <default>
    <joint damping="{p.joint_damping}" stiffness="{p.joint_stiffness}"/>
    <geom friction="{p.friction} 0.005 0.0001"/>
  </default>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1=".3 .5 .7" rgb2="0 0 0" width="32" height="512"/>
    <texture name="texplane" type="2d" builtin="checker" rgb1=".2 .3 .4" rgb2=".1 .2 .3" width="512" height="512" mark="cross"/>
    <material name="matplane" reflectance="0.3" texture="texplane" texrepeat="1 1" texuniform="true"/>
  </asset>"""


def _worldbody(p: MorphologyParams) -> str:
    lines = ["  <worldbody>",
             '    <geom name="floor" size="0 0 .05" type="plane" material="matplane"/>',
             '    <light pos="0 0 3" dir="0 0 -1" diffuse=".8 .8 .8"/>']
    lines.append(f'    <body name="torso" pos="0 0 {p.leg_length + 0.1}">')
    lines.append(f'      <geom type="capsule" size="0.06" fromto="0 0 0 0 0 {p.torso_length}"/>')
    if p.spine_dof > 0:
        lines.append(f'      <joint name="spine" type="ball" range="-30 30"/>')
    for side, sign in [("left", -1), ("right", 1)]:
        lines.extend(_arm_links(p, side, sign))
    for side, sign in [("left", -1), ("right", 1)]:
        lines.extend(_leg_links(p, side, sign))
    lines.append("    </body>")
    lines.append("  </worldbody>")
    return "\n".join(lines)


def _arm_links(p: MorphologyParams, side: str, sign: int) -> list[str]:
    if p.num_arms == 0:
        return []
    half = p.arm_length / max(p.arm_dof - 1, 1)
    y_off = sign * 0.12
    lines = [f'      <body name="{side}_shoulder" pos="0 {y_off} {p.torso_length * 0.9}">',
             f'        <geom type="capsule" size="0.04" fromto="0 0 0 0 {sign * half} 0"/>',
             f'        <joint name="{side}_shoulder_x" type="hinge" axis="1 0 0" range="-90 90"/>',
             f'        <joint name="{side}_shoulder_y" type="hinge" axis="0 1 0" range="-90 90"/>',
             f'        <joint name="{side}_shoulder_z" type="hinge" axis="0 0 1" range="-90 90"/>']
    if p.arm_dof >= 5:
        lines += [f'        <body name="{side}_elbow" pos="0 {sign * half} 0">',
                  f'          <geom type="capsule" size="0.035" fromto="0 0 0 0 {sign * half} 0"/>',
                  f'          <joint name="{side}_elbow" type="hinge" axis="1 0 0" range="-140 0"/>',
                  f'        </body>']
    lines.append("      </body>")
    return lines


def _leg_links(p: MorphologyParams, side: str, sign: int) -> list[str]:
    half = p.leg_length / 2
    y_off = sign * 0.1
    lines = [f'      <body name="{side}_hip" pos="0 {y_off} 0">',
             f'        <geom type="capsule" size="0.05" fromto="0 0 0 0 0 -{half}"/>',
             f'        <joint name="{side}_hip_x" type="hinge" axis="1 0 0" range="-60 60"/>',
             f'        <joint name="{side}_hip_y" type="hinge" axis="0 1 0" range="-120 20"/>',
             f'        <joint name="{side}_hip_z" type="hinge" axis="0 0 1" range="-40 40"/>',
             f'        <body name="{side}_knee" pos="0 0 -{half}">',
             f'          <geom type="capsule" size="0.04" fromto="0 0 0 0 0 -{half}"/>',
             f'          <joint name="{side}_knee" type="hinge" axis="1 0 0" range="-150 0"/>',
             f'          <body name="{side}_foot" pos="0 0 -{half}">',
             f'            <geom type="sphere" size="0.06"/>',
             f'          </body>',
             f'        </body>',
             f'      </body>']
    return lines


def _actuators(p: MorphologyParams) -> str:
    # Mirror joints into actuators (one motor per hinge/ball dof)
    lines = ["  <actuator>"]
    for side in ["left", "right"]:
        if p.num_arms > 0:
            for ax in ["x", "y", "z"]:
                lines.append(f'    <motor name="{side}_shoulder_{ax}" joint="{side}_shoulder_{ax}" gear="100" ctrllimited="true" ctrlrange="-1 1"/>')
            if p.arm_dof >= 5:
                lines.append(f'    <motor name="{side}_elbow" joint="{side}_elbow" gear="80" ctrllimited="true" ctrlrange="-1 1"/>')
        for jt in ["hip_x", "hip_y", "hip_z", "knee"]:
            lines.append(f'    <motor name="{side}_{jt}" joint="{side}_{jt}" gear="120" ctrllimited="true" ctrlrange="-1 1"/>')
    lines.append("  </actuator>")
    return "\n".join(lines)


def _footer() -> str:
    return "</mujoco>"
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m pytest tests/test_morphology.py -v
# Expected: 4 passed
```

- [ ] **Step 5: Commit**

```bash
git add packages/pipeline/urdf_factory.py tests/test_morphology.py
git commit -m "feat: add parametric URDF factory with MuJoCo validation"
```

---

## Task B1-2: Synthetic URDF generator + filter

- [ ] **Step 1: Add test**

Add to `tests/test_morphology.py`:

```python
from packages.pipeline.urdf_generator import generate_filtered_dataset

def test_generator_produces_valid_params(tmp_path):
    dataset = generate_filtered_dataset(n_total=50, seed=42)
    assert len(dataset) > 0
    assert len(dataset) <= 50
    for p in dataset:
        assert validate_urdf(p)
```

- [ ] **Step 2: Create `packages/pipeline/urdf_generator.py`**

```python
from __future__ import annotations
import random
import mujoco
import numpy as np
from packages.pipeline.types import MorphologyParams
from packages.pipeline.urdf_factory import build_urdf, validate_urdf


def _random_params(rng: random.Random) -> MorphologyParams:
    return MorphologyParams(
        num_arms=rng.choice([0, 1, 2]),
        num_legs=rng.choice([2, 4]),
        has_torso=rng.choice([True, False]),
        torso_length=rng.uniform(0.2, 0.6),
        arm_length=rng.uniform(0.3, 0.8),
        leg_length=rng.uniform(0.4, 1.0),
        arm_dof=rng.randint(3, 7),
        leg_dof=rng.randint(3, 6),
        spine_dof=rng.randint(0, 3),
        joint_damping=rng.uniform(0.01, 1.0),
        joint_stiffness=rng.uniform(1.0, 100.0),
        friction=rng.uniform(0.3, 1.2),
    )


def _passes_gravity_test(xml: str, duration_s: float = 1.0) -> bool:
    """Return True if the model doesn't collapse (z > 0.05) under gravity for 1s."""
    try:
        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        mujoco.mj_resetData(model, data)
        n_steps = int(duration_s / model.opt.timestep)
        for _ in range(n_steps):
            mujoco.mj_step(model, data)
        root_z = data.qpos[2] if model.nq >= 3 else 1.0
        return float(root_z) > 0.05
    except Exception:
        return False


def generate_filtered_dataset(
    n_total: int = 10_000,
    seed: int = 0,
) -> list[MorphologyParams]:
    """Generate n_total candidates; return those that pass geometry + gravity filter."""
    rng = random.Random(seed)
    valid: list[MorphologyParams] = []
    for _ in range(n_total):
        p = _random_params(rng)
        if not validate_urdf(p):
            continue
        xml = build_urdf(p)
        if _passes_gravity_test(xml):
            valid.append(p)
    return valid
```

- [ ] **Step 3: Run new test**

```bash
python -m pytest tests/test_morphology.py::test_generator_produces_valid_params -v
# Expected: PASS (may take ~10s for 50 samples on CPU)
```

- [ ] **Step 4: Commit**

```bash
git add packages/pipeline/urdf_generator.py
git commit -m "feat: add synthetic URDF generator with gravity-test filter"
```

---

## Task B1-3: VAE model

- [ ] **Step 1: Add VAE tests**

Add to `tests/test_morphology.py`:

```python
import torch
from packages.pipeline.vae import MorphologyVAE, params_to_tensor, tensor_to_params

def test_vae_encode_decode_roundtrip():
    vae = MorphologyVAE(latent_dim=8)
    tensor = params_to_tensor(BIPED)
    mu, logvar = vae.encode(tensor.unsqueeze(0))
    z = vae.reparameterize(mu, logvar)
    recon = vae.decode(z)
    assert recon.shape == (1, 12)

def test_params_to_tensor_roundtrip():
    t = params_to_tensor(BIPED)
    p2 = tensor_to_params(t)
    assert p2.num_arms == BIPED.num_arms
    assert abs(p2.torso_length - BIPED.torso_length) < 0.01

def test_vae_sample_returns_valid_params():
    vae = MorphologyVAE(latent_dim=8)
    p = vae.sample(seed=42)
    # sampled params should at least be type-correct
    assert isinstance(p, MorphologyParams)
    assert p.num_arms in (0, 1, 2)
```

- [ ] **Step 2: Create `packages/pipeline/vae.py`**

```python
from __future__ import annotations
import dataclasses
import numpy as np
import torch
import torch.nn as nn
from packages.pipeline.types import MorphologyParams

# Continuous param indices and their (min, max) ranges for normalization
_CONTINUOUS = [
    ("torso_length",   0.2, 0.6),
    ("arm_length",     0.3, 0.8),
    ("leg_length",     0.4, 1.0),
    ("joint_damping",  0.01, 1.0),
    ("joint_stiffness", 1.0, 100.0),
    ("friction",       0.3, 1.2),
]
# Discrete params encoded as normalized floats
_DISCRETE = [
    ("num_arms",  0, 2),
    ("num_legs",  2, 4),
    ("arm_dof",   3, 7),
    ("leg_dof",   3, 6),
    ("spine_dof", 0, 3),
    ("has_torso", 0, 1),
]
INPUT_DIM = 12


def params_to_tensor(p: MorphologyParams) -> torch.Tensor:
    vals = []
    for name, lo, hi in _CONTINUOUS:
        vals.append((getattr(p, name) - lo) / (hi - lo))
    for name, lo, hi in _DISCRETE:
        v = float(getattr(p, name)) if name != "has_torso" else float(p.has_torso)
        vals.append((v - lo) / max(hi - lo, 1))
    return torch.tensor(vals, dtype=torch.float32)


def tensor_to_params(t: torch.Tensor) -> MorphologyParams:
    t = t.detach().cpu()
    vals: dict = {}
    for i, (name, lo, hi) in enumerate(_CONTINUOUS):
        vals[name] = float(t[i]) * (hi - lo) + lo
    offset = len(_CONTINUOUS)
    for i, (name, lo, hi) in enumerate(_DISCRETE):
        raw = float(t[offset + i]) * max(hi - lo, 1) + lo
        if name == "has_torso":
            vals[name] = raw > 0.5
        elif name in ("num_arms", "num_legs"):
            vals[name] = int(round(raw))
        else:
            vals[name] = max(lo, min(hi, int(round(raw))))
    return MorphologyParams(**vals)


class MorphologyVAE(nn.Module):
    def __init__(self, latent_dim: int = 8, hidden: int = 64) -> None:
        super().__init__()
        self.latent_dim = latent_dim
        self.encoder = nn.Sequential(nn.Linear(INPUT_DIM, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU())
        self.fc_mu = nn.Linear(hidden, latent_dim)
        self.fc_logvar = nn.Linear(hidden, latent_dim)
        self.decoder = nn.Sequential(nn.Linear(latent_dim, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, INPUT_DIM))

    def encode(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.encoder(x)
        return self.fc_mu(h), self.fc_logvar(h)

    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        std = torch.exp(0.5 * logvar)
        return mu + std * torch.randn_like(std)

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        return self.decoder(z)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return self.decode(z), mu, logvar

    def elbo_loss(self, x: torch.Tensor, beta: float = 0.5) -> torch.Tensor:
        recon, mu, logvar = self(x)
        recon_loss = nn.functional.mse_loss(recon, x, reduction="mean")
        kl = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
        return recon_loss + beta * kl

    def sample(self, seed: int | None = None) -> MorphologyParams:
        if seed is not None:
            torch.manual_seed(seed)
        with torch.no_grad():
            z = torch.randn(1, self.latent_dim)
            t = self.decode(z).squeeze(0).clamp(0, 1)
        return tensor_to_params(t)
```

- [ ] **Step 3: Run VAE tests**

```bash
python -m pytest tests/test_morphology.py -k "vae" -v
# Expected: 3 passed
```

- [ ] **Step 4: Commit**

```bash
git add packages/pipeline/vae.py
git commit -m "feat: add MorphologyVAE (8-dim latent, 12-param decode)"
```

---

## Task B1-4: Modal VAE training script

- [ ] **Step 1: Create `scripts/modal_vae_train.py`**

```python
"""One-time VAE training job. Run: modal run scripts/modal_vae_train.py"""
from __future__ import annotations
import modal

stub = modal.App("autoresearch-vae-train")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch>=2.2", "mujoco>=3.1", "numpy>=1.26")
    .add_local_python_source("packages")
)
volume = modal.Volume.from_name("autoresearch-artifacts", create_if_missing=True)


@stub.function(
    image=image,
    gpu="A10G",
    volumes={"/vol": volume},
    timeout=3600,
)
def train_vae(n_total: int = 10_000, epochs: int = 200) -> str:
    import torch
    from torch.utils.data import DataLoader, TensorDataset
    from packages.pipeline.urdf_generator import generate_filtered_dataset
    from packages.pipeline.vae import MorphologyVAE, params_to_tensor

    print(f"Generating {n_total} synthetic morphologies...")
    dataset = generate_filtered_dataset(n_total=n_total, seed=0)
    print(f"Filtered to {len(dataset)} valid morphologies.")

    tensors = torch.stack([params_to_tensor(p) for p in dataset])
    loader = DataLoader(TensorDataset(tensors), batch_size=64, shuffle=True)

    vae = MorphologyVAE(latent_dim=8).cuda()
    opt = torch.optim.Adam(vae.parameters(), lr=1e-3)

    for epoch in range(epochs):
        total = 0.0
        for (batch,) in loader:
            batch = batch.cuda()
            loss = vae.elbo_loss(batch)
            opt.zero_grad(); loss.backward(); opt.step()
            total += loss.item()
        if epoch % 20 == 0:
            print(f"Epoch {epoch:3d} | loss {total / len(loader):.4f}")

    ckpt_path = "/vol/vae_checkpoint.pt"
    torch.save(vae.state_dict(), ckpt_path)
    volume.commit()
    print(f"Saved to {ckpt_path}")
    return ckpt_path


if __name__ == "__main__":
    with stub.run():
        train_vae.remote(n_total=10_000, epochs=200)
```

- [ ] **Step 2: Run VAE training**

```bash
modal run scripts/modal_vae_train.py
# Expected: ~40 min on A10G, prints epoch losses, saves /vol/vae_checkpoint.pt
# Estimated cost: ~$0.73
```

- [ ] **Step 3: Verify checkpoint**

```bash
modal run -c "
from scripts.modal_vae_train import volume
import torch
from packages.pipeline.vae import MorphologyVAE
vae = MorphologyVAE()
vae.load_state_dict(torch.load('/vol/vae_checkpoint.pt', map_location='cpu'))
p = vae.sample(seed=0)
print('sampled:', p)
"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/modal_vae_train.py
git commit -m "feat: add Modal VAE training script (one-time, A10G)"
```

---

## Task B1-5: Agent-editable `morphology_factory.py` template

- [ ] **Step 1: Create template directory**

```bash
mkdir -p data/artifacts/evolutions/template
```

- [ ] **Step 2: Create `data/artifacts/evolutions/template/morphology_factory.py`**

```python
"""
morphology_factory.py — AGENT-EDITABLE

This file is read and modified by the autoresearch agent each iteration.
You may change:
  - Parameter ranges passed to MorphologyParams
  - Which VAE latent dimensions to emphasize
  - Post-processing of sampled params

Do NOT change the function signatures (build, sample_from_vae).
Do NOT import from outside packages/pipeline/.
"""
from __future__ import annotations
import torch
from packages.pipeline.types import MorphologyParams
from packages.pipeline.urdf_factory import build_urdf, validate_urdf
from packages.pipeline.vae import MorphologyVAE, tensor_to_params

# --- AGENT: adjust these ranges to explore different morphologies ---
PARAM_OVERRIDES: dict = {
    # Example: force biped by fixing num_legs=2
    # "num_legs": 2,
}

VAE_CKPT_PATH = "/vol/vae_checkpoint.pt"
_vae: MorphologyVAE | None = None


def _load_vae() -> MorphologyVAE:
    global _vae
    if _vae is None:
        _vae = MorphologyVAE(latent_dim=8)
        _vae.load_state_dict(torch.load(VAE_CKPT_PATH, map_location="cpu"))
        _vae.eval()
    return _vae


def sample_from_vae(seed: int | None = None) -> MorphologyParams:
    """Sample a morphology from the VAE latent space."""
    vae = _load_vae()
    if seed is not None:
        torch.manual_seed(seed)
    # --- AGENT: you can modify z before decoding, e.g. to bias towards longer legs ---
    with torch.no_grad():
        z = torch.randn(1, vae.latent_dim)
        t = vae.decode(z).squeeze(0).clamp(0, 1)
    params = tensor_to_params(t)
    # Apply any overrides
    if PARAM_OVERRIDES:
        params = MorphologyParams(**{**vars(params), **PARAM_OVERRIDES})
    return params


def build(params: MorphologyParams | None = None, seed: int | None = None) -> tuple[MorphologyParams, str]:
    """Return (params, urdf_xml). Samples from VAE if params is None."""
    if params is None:
        params = sample_from_vae(seed=seed)
    xml = build_urdf(params)
    return params, xml
```

- [ ] **Step 3: Run full smoke test**

```bash
make smoke-morph
# Expected: all tests pass
```

- [ ] **Step 4: Commit**

```bash
git add data/artifacts/evolutions/template/morphology_factory.py
git commit -m "feat: add agent-editable morphology_factory.py template"
```
