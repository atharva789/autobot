import pytest
import numpy as np

# These imports at module level so tests can use the fixtures
def _require_mujoco():
    return pytest.importorskip("mujoco")

def _require_torch():
    return pytest.importorskip("torch")

def _require_torch_geometric():
    return pytest.importorskip("torch_geometric")


BIPED_PARAMS = dict(
    num_arms=2, num_legs=2, has_torso=True,
    torso_length=0.4, arm_length=0.5, leg_length=0.7,
    arm_dof=5, leg_dof=4, spine_dof=1,
    joint_damping=0.1, joint_stiffness=10.0, friction=0.8,
)


def test_build_graph_returns_correct_shapes():
    mujoco = _require_mujoco()
    torch = _require_torch()
    _require_torch_geometric()
    from packages.pipeline.types import MorphologyParams
    from packages.pipeline.urdf_factory import build_urdf
    from packages.pipeline.gnn import build_graph_from_urdf
    biped = MorphologyParams(**BIPED_PARAMS)
    xml = build_urdf(biped)
    n_nodes, edge_index, node_feats, edge_feats = build_graph_from_urdf(xml)
    assert n_nodes > 0
    assert edge_index.shape[0] == 2
    assert node_feats.shape == (n_nodes, 16)
    assert edge_feats.shape[1] == 6


def test_gnn_forward_returns_torque_per_joint():
    _require_mujoco()
    _require_torch()
    _require_torch_geometric()
    import torch
    from packages.pipeline.types import MorphologyParams
    from packages.pipeline.urdf_factory import build_urdf
    from packages.pipeline.gnn import build_graph_from_urdf, MorphologyAgnosticGNN
    biped = MorphologyParams(**BIPED_PARAMS)
    xml = build_urdf(biped)
    n_nodes, edge_index, node_feats, edge_feats = build_graph_from_urdf(xml)
    gnn = MorphologyAgnosticGNN()
    tau = gnn(node_feats.unsqueeze(0), edge_index, edge_feats.unsqueeze(0))
    assert tau.shape == (1, n_nodes, 1)


def test_retarget_returns_correct_shape():
    mujoco = _require_mujoco()
    _require_torch()
    from packages.pipeline.types import MorphologyParams
    from packages.pipeline.urdf_factory import build_urdf
    from packages.pipeline.retarget import retarget_smpl_to_morphology
    biped = MorphologyParams(**BIPED_PARAMS)
    xml = build_urdf(biped)
    fake_ee = np.random.randn(10, 6, 3).astype(np.float32)
    q_target = retarget_smpl_to_morphology(end_effectors=fake_ee, urdf_xml=xml)
    model = mujoco.MjModel.from_xml_string(xml)
    assert q_target.shape == (10, model.nq)


def test_env_step_returns_observation():
    _require_mujoco()
    from packages.pipeline.types import MorphologyParams
    from packages.pipeline.urdf_factory import build_urdf
    from packages.pipeline.mujoco_env import MuJoCoEnv
    biped = MorphologyParams(**BIPED_PARAMS)
    xml = build_urdf(biped)
    env = MuJoCoEnv(xml)
    obs = env.reset()
    assert obs.shape[0] > 0
    tau = np.zeros(env.model.nv)
    obs2, done = env.step(tau)
    assert obs2.shape == obs.shape


def test_tracking_error_perfect():
    from packages.pipeline.fitness import tracking_error
    traj = np.ones((10, 5)) * 0.5
    assert tracking_error(traj, traj) == pytest.approx(0.0)


def test_tracking_error_bounded():
    from packages.pipeline.fitness import tracking_error
    a = np.zeros((10, 5))
    b = np.ones((10, 5)) * np.pi
    err = tracking_error(a, b)
    assert 0.0 <= err <= 1.0


def test_fitness_weights():
    from packages.pipeline.fitness import compute_fitness
    f = compute_fitness(tracking_err=0.2, er16_prob=0.8, weights=(0.6, 0.4))
    # 0.6 * (1 - 0.2) + 0.4 * 0.8 = 0.48 + 0.32 = 0.80
    assert f == pytest.approx(0.80)
