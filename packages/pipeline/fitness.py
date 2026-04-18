from __future__ import annotations
import json
import numpy as np


def tracking_error(pred_traj: np.ndarray, target_traj: np.ndarray) -> float:
    """Mean L2 distance between predicted and target joint angles, normalized to [0,1]."""
    n_joints = min(pred_traj.shape[1], target_traj.shape[1])
    diff = pred_traj[:, :n_joints] - target_traj[:, :n_joints]
    raw = float(np.mean(np.linalg.norm(diff, axis=1)))
    max_err = np.pi * n_joints
    return min(raw / max_err, 1.0)


def er16_success_prob(
    replay_mp4_path: str,
    success_criteria: str,
    gemini_api_key: str,
) -> float:
    """Call Gemini Robotics-ER 1.6 to evaluate task completion. Returns P(success) in [0, 1]."""
    import google.generativeai as genai
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-robotics-er-1.6")
    with open(replay_mp4_path, "rb") as f:
        video_bytes = f.read()
    prompt = (
        f"Watch this robot simulation video. Success criteria: '{success_criteria}'.\n"
        'Reply with ONLY a JSON object: {"success_probability": <float 0-1>, "reasoning": <str>}'
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
