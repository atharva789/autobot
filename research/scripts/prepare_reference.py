"""Prepare a retargeted reference trajectory for the interpretability experiment.

Reads one AMASS .npz clip, extracts SMPL-X joint angles, retargets to the
Unitree G1 URDF (via the team's Phase-04 retargeter, or a minimal joint-name-
mapping fallback), and writes:

  research/data/reference/<clip>.npz
    qpos_ref       (T, n_dof)  per-frame G1 joint positions
    target_ee_pos  (3,)        final right-hand end-effector world position
    target_qpos    (n_dof,)    final G1 joint configuration
    meta           dict        clip_name, fps, n_frames, source

  research/data/reference/<clip>_debug.mp4
    headless MuJoCo render of the reference.

Design note (see plan Section 4a): AMASS already ships SMPL-X params, so this
script deliberately has NO dependency on WHAM / GVHMR. If the Phase-04
retargeter is not yet installed, pass --fallback to use the bundled
joint-name mapping, which is weaker but unblocks research.

Usage:
    python research/scripts/prepare_reference.py \\
        --amass research/data/amass_raw/arm_raise.npz \\
        --out   research/data/reference/arm_raise.npz \\
        [--fallback] [--fps 30] [--render]
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import pathlib
import sys
from typing import Optional

import numpy as np

logger = logging.getLogger("prepare_reference")

# --- Constants ---------------------------------------------------------------

# G1 joint order (Unitree G1 23-DoF locomotion-ready URDF).
# Kept as a module-level constant so it is easy to diff against whatever
# the Phase-04 retargeter emits. If mismatched, fix here rather than silently
# re-ordering downstream.
G1_JOINT_ORDER: tuple[str, ...] = (
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
    "torso_joint",
    "left_shoulder_pitch_joint", "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint", "left_elbow_joint",
    "right_shoulder_pitch_joint", "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint", "right_elbow_joint",
)

# SMPL-X → G1 joint-name mapping used by the --fallback path. Coarse but
# sufficient for the arm-raise toy task. Do NOT rely on this for locomotion.
SMPLX_TO_G1_FALLBACK: dict[str, str] = {
    "left_hip":      "left_hip_pitch_joint",
    "right_hip":     "right_hip_pitch_joint",
    "left_knee":     "left_knee_joint",
    "right_knee":    "right_knee_joint",
    "left_ankle":    "left_ankle_pitch_joint",
    "right_ankle":   "right_ankle_pitch_joint",
    "spine1":        "torso_joint",
    "left_shoulder": "left_shoulder_pitch_joint",
    "right_shoulder":"right_shoulder_pitch_joint",
    "left_elbow":    "left_elbow_joint",
    "right_elbow":   "right_elbow_joint",
}

RIGHT_HAND_SITE = "right_hand"  # site name in G1 MuJoCo model

# --- Types -------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ReferenceArtifact:
    qpos_ref: np.ndarray       # (T, n_dof)
    target_ee_pos: np.ndarray  # (3,)
    target_qpos: np.ndarray    # (n_dof,)
    meta: dict

    def save(self, path: pathlib.Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path,
            qpos_ref=self.qpos_ref,
            target_ee_pos=self.target_ee_pos,
            target_qpos=self.target_qpos,
            meta=np.array(self.meta, dtype=object),
        )
        logger.info("Saved reference artifact to %s", path)


# --- AMASS loading -----------------------------------------------------------


def load_amass_clip(path: pathlib.Path) -> dict:
    """Load a single AMASS .npz file and return the subset we need.

    AMASS canonical keys: 'poses' (T, 156 or 165), 'trans' (T, 3),
    'mocap_framerate' or 'mocap_frame_rate'.
    """
    if not path.exists():
        raise FileNotFoundError(f"AMASS clip not found: {path}")
    data = np.load(path, allow_pickle=True)
    keys = set(data.files)
    if "poses" not in keys:
        raise ValueError(
            f"{path} is missing 'poses' key; not a valid AMASS clip "
            f"(keys found: {sorted(keys)})"
        )
    fps_key = next(
        (k for k in ("mocap_framerate", "mocap_frame_rate", "fps") if k in keys),
        None,
    )
    fps = float(data[fps_key]) if fps_key else 30.0
    return {
        "poses": np.asarray(data["poses"], dtype=np.float32),
        "trans": np.asarray(data["trans"], dtype=np.float32) if "trans" in keys else None,
        "fps": fps,
    }


# --- Retargeting -------------------------------------------------------------


def retarget_with_phase04(smplx_poses: np.ndarray) -> np.ndarray:
    """Placeholder for the Phase-04 retargeter handoff.

    The Phase-04 work (OmniH2O / PHC / ProtoMotions ladder) must expose a
    callable that maps (T, n_smplx_joints * 3) axis-angle poses to
    (T, len(G1_JOINT_ORDER)) G1 joint positions. Import it here once the
    team has locked the choice.

    This function intentionally raises so that the caller can fall back to
    the --fallback path instead of silently producing garbage.
    """
    try:
        # Expected module, provided by Phase-04 work. Import is intentionally
        # lazy so that --fallback does not require it.
        from retarget.g1 import smplx_to_g1  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Phase-04 retargeter (retarget.g1.smplx_to_g1) not available. "
            "Re-run with --fallback, or install the retargeter per "
            "plans/phase-04-retargeting-and-simulation/."
        ) from exc
    return np.asarray(smplx_to_g1(smplx_poses), dtype=np.float32)


def retarget_fallback(smplx_poses: np.ndarray, smplx_joint_names: list[str]) -> np.ndarray:
    """Minimal joint-name-mapping retargeter used when Phase-04 is unavailable.

    SMPL-X axis-angle rotations are projected onto G1 hinge axes by taking
    the pitch component. This is geometrically lossy but preserves the
    arm-raise signal, which is all we need for the toy task.
    """
    T = smplx_poses.shape[0]
    # AMASS 'poses' layout: (T, n_joints*3) axis-angle per joint.
    n_joints = smplx_poses.shape[1] // 3
    if len(smplx_joint_names) != n_joints:
        logger.warning(
            "SMPL-X joint-name list (%d) does not match pose dim (%d); "
            "taking the first %d names.",
            len(smplx_joint_names), n_joints, n_joints,
        )
    qpos = np.zeros((T, len(G1_JOINT_ORDER)), dtype=np.float32)
    g1_index = {name: i for i, name in enumerate(G1_JOINT_ORDER)}
    for smplx_idx, smplx_name in enumerate(smplx_joint_names[:n_joints]):
        g1_name = SMPLX_TO_G1_FALLBACK.get(smplx_name)
        if g1_name is None or g1_name not in g1_index:
            continue
        # Pitch component = axis-angle y-component (MuJoCo G1 hinges are
        # mostly pitch-axis for sagittal-plane motion).
        qpos[:, g1_index[g1_name]] = smplx_poses[:, smplx_idx * 3 + 1]
    return qpos


SMPLX_JOINT_NAMES_DEFAULT: list[str] = [
    "pelvis", "left_hip", "right_hip", "spine1", "left_knee", "right_knee",
    "spine2", "left_ankle", "right_ankle", "spine3", "left_foot", "right_foot",
    "neck", "left_collar", "right_collar", "head", "left_shoulder",
    "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
]


# --- Rendering ---------------------------------------------------------------


def render_debug_video(
    qpos_ref: np.ndarray,
    out_path: pathlib.Path,
    fps: float,
    model_xml: Optional[pathlib.Path] = None,
) -> None:
    """Render the retargeted trajectory to MP4 using MuJoCo offscreen.

    Deliberately light: uses mujoco.Renderer, no viewer, no custom camera
    setup beyond the model's default free camera.
    """
    try:
        import mujoco
        import imageio.v3 as iio
    except ImportError as exc:
        logger.warning("Skipping debug render (%s).", exc)
        return
    if model_xml is None:
        logger.warning("No MuJoCo G1 model provided; skipping debug render.")
        return

    model = mujoco.MjModel.from_xml_path(str(model_xml))
    data = mujoco.MjData(model)
    frames: list[np.ndarray] = []
    with mujoco.Renderer(model, height=360, width=640) as renderer:
        for t in range(qpos_ref.shape[0]):
            # Map our reduced qpos into the model's full qpos; we assume the
            # model has a floating base (7) + our n_dof hinges. If the model
            # is fixed-base, this slice is still correct.
            n_dof = qpos_ref.shape[1]
            if model.nq >= 7 + n_dof:
                data.qpos[7:7 + n_dof] = qpos_ref[t]
            else:
                data.qpos[: n_dof] = qpos_ref[t][: model.nq]
            mujoco.mj_forward(model, data)
            renderer.update_scene(data)
            frames.append(renderer.render())
    iio.imwrite(out_path, np.stack(frames), fps=int(round(fps)))
    logger.info("Wrote debug video to %s (%d frames)", out_path, len(frames))


# --- Main --------------------------------------------------------------------


def build_reference(
    amass_path: pathlib.Path,
    fallback: bool,
    target_fps: float,
) -> ReferenceArtifact:
    clip = load_amass_clip(amass_path)
    poses = clip["poses"]
    src_fps = clip["fps"]

    # Optional frame downsample to target_fps. Keep immutable: slice a new array.
    if src_fps > target_fps:
        stride = max(1, int(round(src_fps / target_fps)))
        poses = poses[::stride]
        effective_fps = src_fps / stride
    else:
        effective_fps = src_fps

    if fallback:
        qpos_ref = retarget_fallback(poses, SMPLX_JOINT_NAMES_DEFAULT)
    else:
        qpos_ref = retarget_with_phase04(poses)

    target_qpos = qpos_ref[-1].copy()

    # Target EE position: filled in by MuJoCo FK below if a model is available.
    # Otherwise we write NaNs and let the caller catch it at verification time.
    target_ee_pos = np.full((3,), np.nan, dtype=np.float32)
    try:
        import mujoco  # local import; FK is optional
        model_path = _default_g1_model_path()
        if model_path is not None:
            model = mujoco.MjModel.from_xml_path(str(model_path))
            data = mujoco.MjData(model)
            n_dof = qpos_ref.shape[1]
            if model.nq >= 7 + n_dof:
                data.qpos[7:7 + n_dof] = target_qpos
            else:
                data.qpos[: n_dof] = target_qpos[: model.nq]
            mujoco.mj_forward(model, data)
            site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, RIGHT_HAND_SITE)
            if site_id >= 0:
                target_ee_pos = np.asarray(data.site_xpos[site_id], dtype=np.float32).copy()
    except Exception as exc:  # narrow exception types unknown across envs
        logger.warning("Could not compute target_ee_pos via MuJoCo FK: %s", exc)

    meta = {
        "clip_name": amass_path.stem,
        "source": "AMASS",
        "fps": float(effective_fps),
        "n_frames": int(qpos_ref.shape[0]),
        "retargeter": "phase04" if not fallback else "fallback-name-map",
        "g1_joint_order": list(G1_JOINT_ORDER),
    }
    return ReferenceArtifact(qpos_ref, target_ee_pos, target_qpos, meta)


def _default_g1_model_path() -> Optional[pathlib.Path]:
    """Try a few known locations for the G1 MuJoCo XML; return None if none work."""
    candidates = [
        pathlib.Path("external/unitree_mujoco/unitree_robots/g1/g1.xml"),
        pathlib.Path("external/unitree_mujoco/unitree_robots/g1/scene.xml"),
        pathlib.Path("external/unitree_rl_gym/resources/robots/g1/g1.xml"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--amass", type=pathlib.Path, required=True,
                   help="Path to a single AMASS .npz clip.")
    p.add_argument("--out", type=pathlib.Path, required=True,
                   help="Output .npz path (directory will be created).")
    p.add_argument("--fallback", action="store_true",
                   help="Skip Phase-04 retargeter; use joint-name mapping.")
    p.add_argument("--fps", type=float, default=30.0,
                   help="Target fps after downsampling (default: 30).")
    p.add_argument("--render", action="store_true",
                   help="Also write a debug MP4 next to the .npz.")
    p.add_argument("--model-xml", type=pathlib.Path, default=None,
                   help="Override path to G1 MuJoCo XML for rendering.")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    artifact = build_reference(args.amass, args.fallback, args.fps)
    artifact.save(args.out)
    if args.render:
        mp4_path = args.out.with_suffix("").with_name(args.out.stem + "_debug.mp4")
        render_debug_video(
            artifact.qpos_ref,
            mp4_path,
            fps=artifact.meta["fps"],
            model_xml=args.model_xml or _default_g1_model_path(),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
