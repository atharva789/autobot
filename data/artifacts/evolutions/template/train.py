"""
train.py — AGENT-EDITABLE.

You may change:
  - epochs (hard cap: 40)
  - learning_rate
  - optimizer type
  - GNN layer count / hidden dim
  - Any training trick (grad clipping, LR schedule, dropout)

Do NOT change the function signatures.
Do NOT remove the save_checkpoint() call at the end.
Do NOT exceed MAX_EPOCHS = 40.
"""
from __future__ import annotations
import time
import numpy as np
import torch
import torch.nn as nn
from packages.pipeline.gnn import MorphologyAgnosticGNN, build_graph_from_urdf

MAX_EPOCHS = 40  # hard cap — do not increase

# --- AGENT: tune these ---
epochs = 40
learning_rate = 3e-4
grad_clip_norm = 1.0


def train(urdf_xml: str, q_target: np.ndarray, ckpt_path: str) -> dict:
    """Train GNN by imitation learning. Returns training metadata."""
    import mujoco
    model_mj = mujoco.MjModel.from_xml_string(urdf_xml)
    data_mj = mujoco.MjData(model_mj)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    gnn = MorphologyAgnosticGNN()
    gnn.to(device)
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
            tau = gnn(node_feats.to(device), edge_index, edge_feats.to(device))
            tau_np = tau.squeeze().detach().cpu().numpy()
            n = min(len(tau_np), model_mj.nu)
            data_mj.ctrl[:n] = tau_np[:n]
            mujoco.mj_step(model_mj, data_mj)
            n_q = min(model_mj.nq, q_target.shape[1])
            target_t = torch.tensor(q_target[t + 1, :n_q], dtype=torch.float32).to(device)
            pred_t = torch.tensor(data_mj.qpos[:n_q], dtype=torch.float32).to(device)
            loss = nn.functional.mse_loss(pred_t, target_t)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(list(gnn.parameters()), grad_clip_norm)
            opt.step()
            ep_loss += loss.item()
        losses.append(ep_loss / max(T, 1))
        if ep % 10 == 0:
            print(f"Epoch {ep:3d} | loss {losses[-1]:.4f} | elapsed {time.time()-t0:.0f}s")

    torch.save(gnn.state_dict(), ckpt_path)
    return {"final_loss": losses[-1] if losses else 0.0, "epochs_run": _epochs}
