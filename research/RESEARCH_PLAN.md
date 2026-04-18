# Research Plan: Mechanistic Interpretability of Video-Informed Humanoid Policies

**Author:** Atharva Gupta  
**Date:** April 2026  
**Track:** Parallel research, independent of the 36h hackathon demo  

---

## 1. Motivation

Imitation learning from video is becoming a practical data source for humanoid robot control. Pipelines like WHAM, GVHMR, and OmniRetarget can extract whole-body SMPL-X motion from monocular video and retarget it to robot morphologies. The standard downstream use is behavior cloning: clone the retargeted motion as a policy initialization, then fine-tune with RL.

**What we don't know:** _What does that video prior actually teach the policy?_

The performance benefit of prior-initialized RL over from-scratch RL is well-documented — MoDem, DAPG, DDPGfD, Latent Action Priors, and DGN all show sample-efficiency gains. But none of those papers ask what internal representations the prior installs. They treat the policy as a black box and report reward curves.

Mechanistic interpretability of non-LLM control policies is flagged as an open problem in "Open Problems in Mechanistic Interpretability" (2025). Existing interpretability work in robotics focuses on VLMs, LLM-as-reward systems (Eureka), and action chain-of-thought (ACoT-VLA). There is essentially no work probing the internal geometry of dense-action RL policies trained with vs without demonstration priors.

This creates a genuine gap: using linear probes and layer-wise representation similarity to characterize what video priors install in humanoid RL policies.

---

## 2. Corrected Background Assumptions

These assumptions are common starting points for people new to the field. Each is corrected below with the relevant literature.

### 2.1 "LLMs generate RL policies from imitation data"

**Correction.** LLMs generate _reward functions_ (code), not policies. The canonical reference is **Eureka (Ma et al., NVIDIA, 2023)**: GPT-4 writes Python reward-shaping functions; a standard RL algorithm (PPO) trains the policy against that reward. Follow-ups include **DrEureka** (LLM-designed domain randomization for sim-to-real) and **Eureka-ML-Agents**. No published system outputs a neural control policy from an LLM directly.

### 2.2 "Inverse RL extracts a policy"

**Correction.** Inverse RL extracts a _reward function_ from expert trajectories. A separate forward RL pass trains the policy on that reward. Adversarial variants — **GAIL (Ho & Ermon, 2016)** and **AIRL (Fu et al., 2018)** — train a discriminator alongside the policy, but still use an inner RL loop; they are not "demonstrations → policy" converters. **GraphIRL (Kumar et al.)** is the current state-of-art for video-based IRL on manipulation; it is research code, not an API.

### 2.3 "There is a hosted IRL API / Gemini provides a reward function"

**Correction.** No IRL-as-a-service exists. What _does_ exist is **VLM-as-reward**: query Gemini/GPT-4V per rollout ("does this video match the goal?") and use the score as a sparse reward. References: **RoboCLIP (Sontakke et al., 2023)**, **VLM-RMs (Rocamonde et al., 2023)**, **RL-VLM-F (Wang et al., 2024)**, **VIPER (Escontrela et al., 2023)**. Practical constraint: per-step VLM queries take seconds and are expensive; this approach is only feasible as a sparse episode-end reward, not dense per-frame feedback.

### 2.4 "Traditional RL wastes time exploring; demonstrating is obviously better"

**Correction.** True empirically, but not a research-novel contribution. The demonstration-bootstrapped RL literature is mature: **DDPGfD (Vecerik, 2017)**, **DAPG (Rajeswaran, 2017)**, **MoDem (Hansen et al., 2022)**, **Latent Action Priors (Bogdanovic et al., 2024)**, **DGN / Data-Guided Noise (2025)**. A paper that only shows "priors help sample efficiency" will be rejected as a known result.

### 2.5 "You can export a MuJoCo-trained policy to Isaac Sim/Omniverse"

**Correction — mostly true, but terminology matters.** Isaac Sim = the simulator. Isaac Lab = the RL training framework (successor to deprecated Isaac Gym). Omniverse = the rendering/collaboration platform that hosts Isaac Sim. A MuJoCo-trained policy can transfer to Isaac Lab if observation and action spaces match, but there is a physics solver domain gap. This research track does not need Isaac Lab; MuJoCo is sufficient.

---

## 3. Research Question

> **What internal representations does a video-prior initialization install in a humanoid RL policy, relative to a policy trained from scratch on the same task?**

**Hypothesis.** A policy initialized from a behavior-cloned reference motion will develop stronger and earlier representations of balance-relevant and trajectory-relevant features (as measured by linear probe R² on penultimate-layer activations), and these features will be more load-bearing (larger task-success drop under ablation), compared to an identically-architected policy trained from random initialization.

**Why this is interesting whether or not the hypothesis is confirmed.**
- If confirmed: video priors install specific balance/motion features into early-mid layers, not just a better output head. This argues for targeted regularization (e.g., distillation of those features) rather than whole-network pretraining.
- If disconfirmed: the prior affects only the output layer / action head. Implies simpler initialization strategies (just warm-start the action head) would be equally effective — a practically useful negative result.
- If probes fail on both policies: the task is too simple for the probes to discriminate. Extend task difficulty.

---

## 4. Related Work Summary

| Paper | What it shows | Relevance |
|-------|--------------|-----------|
| Eureka (Ma et al., 2023) | LLM writes reward code; PPO trains policy | Establishes LLM-as-reward (not LLM-as-policy) paradigm |
| GAIL (Ho & Ermon, 2016) | Adversarial imitation learning | IRL baseline; still uses RL inner loop |
| AIRL (Fu et al., 2018) | Disentangled IRL reward | IRL baseline |
| RoboCLIP (Sontakke et al., 2023) | CLIP similarity as manipulation reward | VLM-as-reward, manipulation scope |
| VLM-RMs (Rocamonde et al., 2023) | VLMs as zero-shot reward models | VLM-as-reward, broader scope |
| MoDem (Hansen et al., 2022) | Demo-guided model-based RL | Prior-bootstrapped RL; shows sample efficiency gain |
| DAPG (Rajeswaran, 2017) | Demo-augmented policy gradient | Prior-bootstrapped RL; canonical reference |
| Latent Action Priors (Bogdanovic et al., 2024) | Learn latent prior over actions from demos | Most relevant prior-bootstrapped RL to our setup |
| DGN / Data-Guided Noise (2025) | Demo-guided exploration noise | Recent prior-bootstrapped RL |
| GraphIRL (Kumar et al.) | Graph-based IRL from video | State-of-art video-IRL; research code only |
| OmniRetarget | Universal SMPL→robot retargeter | Upstream pipeline; useful for data prep |
| PhysHMR | Physics-constrained human motion recovery | Better upstream than naive GVHMR |
| "From Generated Human Videos to Physically Plausible Robot Trajectories" | Full pipeline video→trajectory | Closest prior to our upstream |
| Open Problems in Mech Interp (2025) | Survey of open interp questions | Explicitly flags non-LLM policy interp as underexplored |
| ACoT-VLA | Action chain-of-thought for VLAs | Interp work on VLMs, not dense-action RL — our gap |

---

## 5. Experiment Design

### 5.1 Task

**Right arm raise to a target pose** on the Unitree G1 in MuJoCo, fixed base (no locomotion). Target pose derived from one AMASS clip.

Rationale: simple enough to train to competence on a laptop in <12h; complex enough that balance features matter (the arm raise shifts COM). No locomotion avoids the compute burden of gait learning while keeping the whole-body balance problem present.

### 5.2 Two Policies

| | Policy A | Policy B |
|---|----------|----------|
| Architecture | MLP (128, 128), Tanh | identical |
| Init | random | BC pretrain on retargeted AMASS ref, 5k gradient steps |
| Training | PPO, 500k steps | PPO, 500k steps (same reward, same hyperparams) |
| Reward | −‖ee − goal‖₂ | identical (no reference-tracking term post-pretrain) |

Both use the same random seed. BC pretrain dataset: `(qpos_ref[t], qpos_ref[t+1] − qpos_ref[t])` pairs from `prepare_reference.py`.

### 5.3 Interpretability Measurements

**Linear probes (penultimate layer):**

| Probe target | Expected outcome |
|---|---|
| Joint-angle values | Both A and B score well (sanity check) |
| EE-to-goal distance | Both score well; B slightly higher (task-oriented) |
| Root-COM displacement | B scores higher (prior installs balance features) |

**Activation similarity — CKA (Centered Kernel Alignment):**  
Layer-wise CKA matrix between A and B on a shared held-out trajectory. If CKA is low but probe R² is similar, the policies learned equivalent features in different geometric orientations.

**Top-k unit ablation:**  
Zero the 10 penultimate units with largest absolute weight in the COM-proxy probe. Re-evaluate task success. If ablation drops B more than A, B's com-proxy features are more load-bearing.

### 5.4 Secondary Output (free by-product)

Learning curves: reward vs env steps for A vs B. This is the standard prior-vs-no-prior comparison and can be included as a baseline/ablation section.

### 5.5 Success Criteria

- Policy A reaches ≥70% task success.
- Policy B reaches the same threshold in fewer env steps.
- At least one probe scores R² > 0.5 on at least one policy (sanity — probes can read something).
- Figures render without error; reproduced within R²±0.05 across seed runs.

---

## 6. Data Sources

- **AMASS (CMU or KIT subset):** pre-extracted SMPL-X params; no WHAM/GVHMR needed.
- **Unitree G1 MuJoCo model:** from `unitree_mujoco` (already in the hackathon repo).
- **Retargeter:** Phase-04 retargeting library (OmniH2O/PHC/ProtoMotions ladder); `--fallback` joint-name map if unavailable.

No YouTube / live web access needed. All data is commit-ready.

---

## 7. Compute Estimate

| Stage | Laptop (CPU/MPS) | Colab A100 |
|-------|-----------------|------------|
| BC pretrain (5k steps) | ~2 min | <1 min |
| PPO Policy A (500k steps) | ~6–10h | ~45 min |
| PPO Policy B (500k steps) | ~6–10h | ~45 min |
| Rollout collection (200 eps) | ~5 min | ~2 min |
| Probes + CKA + ablation | <1 min | <1 min |

**If laptop training is too slow:** reduce `TOTAL_TIMESTEPS_A` to 200k for a first sanity run. If Policy A fails to reach 70% success in 12h wall-clock, switch to Colab A100.

---

## 8. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Compute: two PPO runs don't finish on laptop | Colab A100; reduce task horizon |
| BC init doesn't help (Policy B ≈ Policy A in sample efficiency) | Verify BC policy kinematically reaches goal before RL; if not, fix the retargeting step |
| Probes trivially saturate (R²≈1 everywhere) | Task too simple — add perturbation or change target every episode |
| Probes fail on both (R²≈0) | Need more training, or probe on earlier layers |
| Phase-04 retargeter not stable | `--fallback` joint-name map; documents weaker but unblocking |
| Scope creep into demo | Strict separation: `research/` dir, no shared imports with demo |

---

## 9. Potential Contributions

1. **Empirical:** first characterization of how video-prior initialization shifts the internal geometry of humanoid RL policies.
2. **Methodological:** application of linear probing + CKA to dense-action whole-body control policies (novel context for mech-interp tools).
3. **Practical:** if ablation shows prior features are more load-bearing, argues for explicitly preserving those features during fine-tuning rather than unconstrained PPO.

---

## 10. References

- Eureka: Ma et al., 2023. "Eureka: Human-Level Reward Design via Coding Large Language Models."
- GAIL: Ho & Ermon, 2016. "Generative Adversarial Imitation Learning."
- AIRL: Fu et al., 2018. "Learning Robust Rewards with Adversarial Inverse Reinforcement Learning."
- RoboCLIP: Sontakke et al., 2023. "RoboCLIP: One Demonstration is Enough to Learn Robot Policies."
- VLM-RMs: Rocamonde et al., 2023. "Vision-Language Models are Zero-Shot Reward Models for Reinforcement Learning."
- RL-VLM-F: Wang et al., 2024. "RL-VLM-F: Reinforcement Learning from Vision Language Foundation Model Feedback."
- VIPER: Escontrela et al., 2023. "Video PreTraining (VPT) / VIPER."
- DAPG: Rajeswaran et al., 2017. "Learning Complex Dexterous Manipulation with Deep Reinforcement Learning and Demonstrations."
- MoDem: Hansen et al., 2022. "MoDem: Accelerating Visual Model-Based Reinforcement Learning with Demonstrations."
- DDPGfD: Vecerik et al., 2017. "Leveraging Demonstrations for Deep Reinforcement Learning on Robotics Problems."
- Latent Action Priors: Bogdanovic et al., 2024. "Model-Free Reinforcement Learning with Latent Action Priors."
- GraphIRL: Kumar et al. (year TBD). "GraphIRL: Graph-Based Inverse Reinforcement Learning from Diverse Videos."
- Open Problems in Mech Interp: 2025 survey (multiple authors). "Open Problems in Mechanistic Interpretability."
- ACoT-VLA: Action Chain-of-Thought for Vision-Language-Action models (2024–25).
- OmniRetarget: Universal motion retargeting from SMPL to arbitrary robot morphologies.
- PhysHMR: Physics-constrained human mesh recovery from monocular video.
