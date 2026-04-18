"""Per-iteration trial: retarget → train → rollout → evaluate. Run on Modal A10G.

Deploy once: modal deploy scripts/modal_trial_runner.py
Cost per trial: ~$0.35 (15-min A10G)
"""
from __future__ import annotations
import modal
import os

app = modal.App("autoresearch-trial")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "torch>=2.2", "torch-geometric>=2.5", "mujoco>=3.1",
        "numpy>=1.26", "supabase>=2.4",
        "google-generativeai>=0.5", "httpx>=0.27", "opencv-python-headless>=4.9",
    )
    .add_local_python_source("packages")
)

volume = modal.Volume.from_name("autoresearch-artifacts", create_if_missing=True)


@app.function(
    image=image,
    gpu="A10G",
    volumes={"/vol": volume},
    timeout=900,                 # 15-min hard cap per trial
    container_idle_timeout=180,  # keep warm 3 min between iterations
    secrets=[
        modal.Secret.from_name("supabase-secrets"),
        modal.Secret.from_name("gemini-secrets"),
    ],
)
def run_trial(
    evolution_id: str,
    iter_num: int,
    train_py_source: str,
    morph_factory_source: str,
    smpl_trajectory_url: str,
    epochs: int = 40,
) -> dict:
    import tempfile, sys, importlib
    from pathlib import Path
    import httpx
    from supabase import create_client
    import numpy as np

    supa = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    scratch = Path(tempfile.mkdtemp())

    # Write agent-edited sources to scratch dir
    (scratch / "train.py").write_text(train_py_source)
    (scratch / "morphology_factory.py").write_text(morph_factory_source)

    # Download SMPL trajectory
    resp = httpx.get(smpl_trajectory_url, timeout=60)
    resp.raise_for_status()
    smpl_path = scratch / "motion.pkl"
    smpl_path.write_bytes(resp.content)

    # Import morphology factory from scratch
    sys.path.insert(0, str(scratch))
    import morphology_factory as mf  # type: ignore
    importlib.reload(mf)
    params, urdf_xml = mf.build(seed=iter_num)

    # Retarget SMPL to morphology
    from packages.pipeline.retarget import smpl_pkl_to_end_effectors, retarget_smpl_to_morphology
    ee = smpl_pkl_to_end_effectors(str(smpl_path))
    q_target = retarget_smpl_to_morphology(ee, urdf_xml)

    # Train GNN
    sys.path.insert(0, str(scratch))
    import train as train_module  # type: ignore
    importlib.reload(train_module)
    ckpt_path = str(scratch / "controller.pt")
    meta = train_module.train(urdf_xml=urdf_xml, q_target=q_target, ckpt_path=ckpt_path)

    # Rollout + video
    from packages.pipeline.mujoco_env import MuJoCoEnv
    env = MuJoCoEnv(urdf_xml, render=True)
    pred_traj, frames = env.rollout_to_video(q_target)
    replay_path = str(scratch / "replay.mp4")
    env.save_video(frames, replay_path)

    # Fitness
    from packages.pipeline.fitness import tracking_error, er16_success_prob, compute_fitness
    track_err = tracking_error(pred_traj, q_target)
    er16_prob = er16_success_prob(
        replay_mp4_path=replay_path,
        success_criteria="robot completes the demonstrated task",
        gemini_api_key=os.environ["GEMINI_API_KEY"],
    )
    score = compute_fitness(track_err, er16_prob)

    # Upload artifacts to Supabase Storage
    evo_iter = f"{evolution_id}/{iter_num:03d}"

    def upload(local: str, remote_key: str) -> str:
        with open(local, "rb") as f:
            supa.storage.from_("artifacts").upload(remote_key, f, {"upsert": "true"})
        return supa.storage.from_("artifacts").get_public_url(remote_key)

    replay_url = upload(replay_path, f"{evo_iter}/replay.mp4")
    ckpt_url = upload(ckpt_path, f"{evo_iter}/controller.pt")

    traj_path = str(scratch / "trajectory.npy")
    np.save(traj_path, pred_traj)
    traj_url = upload(traj_path, f"{evo_iter}/trajectory.npy")

    return {
        "tracking_error":      track_err,
        "er16_success_prob":   er16_prob,
        "fitness_score":       score,
        "replay_mp4_url":      replay_url,
        "controller_ckpt_url": ckpt_url,
        "trajectory_npz_url":  traj_url,
        "reasoning_md": (
            f"Iter {iter_num}: tracking_err={track_err:.3f}, "
            f"er16={er16_prob:.2f}, score={score:.3f}. "
            f"Train loss={meta['final_loss']:.4f}."
        ),
    }


@app.local_entrypoint()
def main():
    print("Deploy with: modal deploy scripts/modal_trial_runner.py")
    print("Then call run_trial.remote(...) from the backend.")
