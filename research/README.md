# Research Track — Interpretability of Video-Informed Humanoid Policies

**Scope.** This directory is a parallel research track to the 36h hackathon demo in [../plans/00-master-platform-plan.md](../plans/00-master-platform-plan.md). It does NOT ship with the demo, does NOT share runtime code with the demo, and runs on a laptop or Colab.

**Research question.** When a humanoid control policy is initialized from a behavior-cloned reference motion (a "video prior"), what internal representation does that prior install that exploration-only RL does not?

See the full plan at [../../.claude/plans/read-existing-papers-to-valiant-goose.md](~/.claude/plans/read-existing-papers-to-valiant-goose.md) (Section 3 for experiment design, Section 1 for literature motivation).

## Layout

```
research/
  scripts/
    prepare_reference.py    # AMASS -> retargeted G1 reference .npz
  notebooks/
    interp_priors.ipynb     # trains 2 policies + probes + CKA + ablation
  data/
    amass_raw/              # put raw AMASS .npz clips here (gitignored)
    reference/              # prepare_reference.py writes here
  runs/                     # policy checkpoints, TB logs, activations.h5
```

## One-off setup

```bash
pip install numpy torch gymnasium "stable-baselines3>=2.3" mujoco imageio imageio-ffmpeg \
            scikit-learn seaborn matplotlib h5py
```

Place one AMASS clip at `research/data/amass_raw/arm_raise.npz`. Any clip that contains an arm-raise motion will do; the "CMU" AMASS subset is a common source.

Confirm the Unitree G1 MuJoCo XML is reachable. The pipeline looks first at `../external/unitree_mujoco/unitree_robots/g1/g1.xml`; override with `--model-xml` if your path differs.

## Run

```bash
# 1. Build the retargeted reference (uses fallback joint-name map if the
#    Phase-04 retargeter is not installed).
python research/scripts/prepare_reference.py \
  --amass research/data/amass_raw/arm_raise.npz \
  --out   research/data/reference/arm_raise.npz \
  --fallback --render

# 2. Open and run the notebook top-to-bottom.
jupyter lab research/notebooks/interp_priors.ipynb
```

On a laptop, set `TOTAL_TIMESTEPS_A` in the notebook to ~200k for a first sanity run; bump to 500k+ on Colab A100. If Policy A can't reach ~70% success, the task is compute-bound — see plan Section 7 risks.

## Verification checklist

- [ ] `prepare_reference.py` produces `arm_raise.npz` and (with `--render`) a debug MP4 that visually matches the source.
- [ ] Notebook Section 3: Policy A learning curve reaches ≥70% task success.
- [ ] Notebook Section 4: Policy B reaches the threshold in fewer env steps than A.
- [ ] Notebook Section 6: at least one probe scores R² > 0.5 for at least one policy.
- [ ] Notebook Sections 7–9 render without error; `interp_figures.png` is written to `runs/`.
- [ ] Seed-stable: rerun with `SEED=0` reproduces probe R² within ±0.05.

## Non-goals

- No locomotion (fixed-base task only).
- No Isaac Sim / Isaac Lab / Omniverse (MuJoCo is enough for this question).
- No WHAM / GVHMR dependency (AMASS is upstream of the live pose-extraction path).
- No VLM-as-reward / LLM-designed-reward (rejected on feasibility grounds; see plan Section 2).
