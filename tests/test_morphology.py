from __future__ import annotations

import pytest
from packages.pipeline.types import MorphologyParams
from packages.pipeline.urdf_factory import build_urdf, validate_urdf

BIPED = MorphologyParams(
    num_arms=2, num_legs=2, has_torso=True,
    torso_length=0.4, arm_length=0.5, leg_length=0.7,
    arm_dof=5, leg_dof=4, spine_dof=1,
    joint_damping=0.1, joint_stiffness=10.0, friction=0.8,
)


def test_build_returns_xml_string() -> None:
    xml = build_urdf(BIPED)
    assert isinstance(xml, str)
    assert "<mujoco" in xml
    assert "<body" in xml


def test_urdf_loads_in_mujoco() -> None:
    mujoco = pytest.importorskip("mujoco")
    xml = build_urdf(BIPED)
    model = mujoco.MjModel.from_xml_string(xml)
    assert model.nq > 0


def test_validate_rejects_bad_params() -> None:
    bad = MorphologyParams(
        num_arms=0, num_legs=2, has_torso=False,
        torso_length=0.0,
        arm_length=0.5, leg_length=0.7,
        arm_dof=5, leg_dof=4, spine_dof=0,
        joint_damping=0.1, joint_stiffness=10.0, friction=0.8,
    )
    assert not validate_urdf(bad)


def test_validate_accepts_good_params() -> None:
    assert validate_urdf(BIPED)


# --- B1-2: Generator ---

from packages.pipeline.urdf_generator import generate_filtered_dataset  # noqa: E402


def test_generator_produces_valid_params() -> None:
    dataset = generate_filtered_dataset(n_total=20, seed=42)
    assert len(dataset) > 0
    assert len(dataset) <= 20
    for p in dataset:
        assert validate_urdf(p)


# --- B1-3: VAE ---

def test_vae_encode_decode_roundtrip() -> None:
    torch = pytest.importorskip("torch")
    from packages.pipeline.vae import MorphologyVAE, params_to_tensor
    vae = MorphologyVAE(latent_dim=8)
    tensor = params_to_tensor(BIPED)
    mu, logvar = vae.encode(tensor.unsqueeze(0))
    z = vae.reparameterize(mu, logvar)
    recon = vae.decode(z)
    assert recon.shape == (1, 12)


def test_params_to_tensor_roundtrip() -> None:
    pytest.importorskip("torch")
    from packages.pipeline.vae import params_to_tensor, tensor_to_params
    t = params_to_tensor(BIPED)
    p2 = tensor_to_params(t)
    assert p2.num_arms == BIPED.num_arms
    assert abs(p2.torso_length - BIPED.torso_length) < 0.01


def test_vae_sample_returns_valid_params() -> None:
    pytest.importorskip("torch")
    from packages.pipeline.vae import MorphologyVAE
    vae = MorphologyVAE(latent_dim=8)
    p = vae.sample(seed=42)
    assert isinstance(p, MorphologyParams)
    assert p.num_arms in (0, 1, 2)
