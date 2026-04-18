# Current Research Plan Outline

Source of truth: [RESEARCH_PLAN.md](/Users/thorbthorb/Downloads/IL_ideation/research/RESEARCH_PLAN.md)

## Objective
Determine what internal representations are installed by a video-prior initialization in humanoid RL policies, relative to training from scratch.

## Core hypothesis
Video-prior initialized policies learn stronger and earlier balance/trajectory-relevant features than scratch policies, measured through probe quality and ablation sensitivity.

## Experimental design
1. Fixed-base Unitree G1 arm-raise task in MuJoCo.
2. Two policies with identical architecture/hyperparameters:
   - Policy A: random init + PPO.
   - Policy B: BC warm-start from retargeted AMASS reference + PPO.
3. Same reward for both during RL (`-||ee-goal||`), no reference-tracking term post-init.

## Measurements
- Linear probes on penultimate activations:
  - joint-angle decoding
  - end-effector distance-to-goal
  - COM/root displacement proxy
- Layerwise CKA similarity between A and B.
- Top-k unit ablation guided by probe weights, then task success delta.

## Success criteria
- Policy A reaches at least 70 percent success.
- Policy B reaches threshold in fewer steps.
- At least one probe achieves R^2 > 0.5.
- Figures and analysis rerun seed-stably within tolerance.

## Compute and data
- Data: AMASS clip -> retargeted reference via `research/scripts/prepare_reference.py`.
- Compute: laptop for smoke runs, Colab A100 for full 500k-step runs.

## Non-goals
- No locomotion tasks.
- No Isaac stack requirement.
- No online WHAM/GVHMR dependency in this track.
- No VLM-as-reward or LLM-designed reward methods in this study.

