"""prepare.py — FIXED. Do not modify. Loaded by train.py."""
from __future__ import annotations
import numpy as np
from packages.pipeline.mujoco_env import MuJoCoEnv
from packages.pipeline.retarget import smpl_pkl_to_end_effectors, retarget_smpl_to_morphology
from packages.pipeline.fitness import tracking_error, er16_success_prob, compute_fitness


def load_everything(urdf_xml: str, smpl_pkl_path: str) -> dict:
    ee = smpl_pkl_to_end_effectors(smpl_pkl_path)
    q_target = retarget_smpl_to_morphology(ee, urdf_xml)
    env = MuJoCoEnv(urdf_xml, render=True)
    return {"q_target": q_target, "env": env, "ee": ee}
