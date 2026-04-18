from __future__ import annotations
import numpy as np

NODE_DIM = 16
EDGE_DIM = 6


def build_graph_from_urdf(xml: str, qpos=None, qvel=None):
    """Parse MJCF XML and build a graph. Returns (n_nodes, edge_index, node_feats, edge_feats)."""
    import mujoco
    import torch
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    if qpos is not None:
        data.qpos[:len(qpos)] = qpos
    if qvel is not None:
        data.qvel[:len(qvel)] = qvel
    mujoco.mj_forward(model, data)

    n_bodies = model.nbody
    src, dst, edge_feats_list = [], [], []

    for j in range(model.njnt):
        body_id = int(model.jnt_bodyid[j])
        parent_id = int(model.body_parentid[body_id])
        if parent_id < 0:
            continue
        src.extend([body_id, parent_id])
        dst.extend([parent_id, body_id])
        jtype = int(model.jnt_type[j])
        jtype_onehot = [float(jtype == t) for t in [0, 1, 2, 3]]
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
        btype_onehot = [float(b == 0), float(b != 0), 0.0, 0.0]
        feats = [jnt_angle, jnt_vel, mass, length] + inertia + com_pos + btype_onehot
        node_feats_list.append(feats[:NODE_DIM])

    node_feats = torch.tensor(node_feats_list, dtype=torch.float32)
    return n_bodies, edge_index, node_feats, edge_feats


class MorphologyAgnosticGNN:
    """GATv2-based controller. Shared weights across all morphologies."""

    def __init__(self, hidden: int = 64) -> None:
        import torch.nn as nn
        from torch_geometric.nn import GATv2Conv
        import torch
        self._hidden = hidden
        self.node_enc = nn.Linear(NODE_DIM, hidden)
        self.edge_enc = nn.Linear(EDGE_DIM, hidden)
        self.mp1 = GATv2Conv(hidden, hidden, heads=4, edge_dim=hidden, concat=True)
        self.mp2 = GATv2Conv(hidden * 4, hidden, heads=4, edge_dim=hidden, concat=True)
        self.mp3 = GATv2Conv(hidden * 4, hidden, heads=1, edge_dim=hidden, concat=False)
        self.decoder = nn.Linear(hidden, 1)
        # collect parameters for optimizer
        self._modules_list = [self.node_enc, self.edge_enc, self.mp1, self.mp2, self.mp3, self.decoder]

    def parameters(self):
        import itertools
        return itertools.chain(*[m.parameters() for m in self._modules_list])

    def to(self, device):
        for m in self._modules_list:
            m.to(device)
        return self

    def state_dict(self):
        import torch
        sd = {}
        for i, m in enumerate(self._modules_list):
            for k, v in m.state_dict().items():
                sd[f"{i}.{k}"] = v
        return sd

    def __call__(self, node_feats, edge_index, edge_feats):
        import torch
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
        return self.decoder(x).view(B, N, 1)
