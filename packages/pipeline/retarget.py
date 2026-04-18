from __future__ import annotations
import numpy as np


def smpl_pkl_to_end_effectors(smpl_pkl_path: str) -> np.ndarray:
    """Load GVHMR output .pkl and extract 6 key end-effector world positions.
    Returns: (T, 6, 3) float32. EE order: [left_hand, right_hand, left_foot, right_foot, head, pelvis]
    """
    import pickle
    with open(smpl_pkl_path, "rb") as f:
        data = pickle.load(f)
    joints = data.get("joints", None)
    if joints is None:
        smpl_global = data.get("smpl_params_global", {})
        joints = smpl_global.get("joints", None)
    if joints is None:
        raise ValueError("Cannot find joints in GVHMR output. Keys: " + str(list(data.keys())))
    joints = np.array(joints)  # (T, 24, 3)
    # SMPL-X: 0=pelvis, 10=left_foot, 11=right_foot, 15=head, 20=left_hand, 21=right_hand
    idx = [20, 21, 10, 11, 15, 0]
    return joints[:, idx, :].astype(np.float32)


def retarget_smpl_to_morphology(
    end_effectors: np.ndarray,   # (T, 6, 3)
    urdf_xml: str,
    ik_iters: int = 10,
) -> np.ndarray:
    """IK retargeting: map end-effector targets to joint angles. Returns (T, nq)."""
    import mujoco
    model = mujoco.MjModel.from_xml_string(urdf_xml)
    data = mujoco.MjData(model)
    T = end_effectors.shape[0]
    q_target = np.zeros((T, model.nq), dtype=np.float32)

    for t in range(T):
        mujoco.mj_resetData(model, data)
        for _ in range(ik_iters):
            mujoco.mj_forward(model, data)
            jac_pos = np.zeros((3, model.nv))
            mujoco.mj_jacBody(model, data, jac_pos, None, 0)
            target = end_effectors[t, 5]  # pelvis
            current = data.xpos[0].copy()
            error = target - current
            lam = 0.01
            dq = jac_pos.T @ np.linalg.solve(
                jac_pos @ jac_pos.T + lam * np.eye(3), error
            )
            n = min(len(dq), model.nq)
            data.qpos[:n] += dq[:n].astype(np.float32)
            if model.nq > 0 and hasattr(model, 'jnt_range'):
                data.qpos[:] = np.clip(
                    data.qpos,
                    model.jnt_range[:model.nq, 0] if model.jnt_range.shape[0] >= model.nq else data.qpos,
                    model.jnt_range[:model.nq, 1] if model.jnt_range.shape[0] >= model.nq else data.qpos,
                )
        q_target[t] = data.qpos[:model.nq].copy()

    return q_target
