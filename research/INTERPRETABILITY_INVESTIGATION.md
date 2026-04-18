# Interpretability Investigation Protocol

This document defines how we will investigate interpretability for the current research track.

## 1. Build comparable policies

Train two policies on the same environment and reward:
- `Policy A`: scratch initialization.
- `Policy B`: behavior-cloning warm start from video-derived reference, then PPO.

Hold constant:
- network architecture
- optimizer and PPO hyperparameters
- reward function
- rollout horizon and seed policy

This isolates initialization as the main treatment variable.

## 2. Log activations and targets

For both policies, collect rollouts and store:
- penultimate-layer activations per timestep
- observed joint states
- end-effector distance to goal
- COM/root-displacement proxy
- action outputs
- episodic success

Persist activations and labels in a single run artifact for reproducible probing.

## 3. Run linear probes

Fit probes on held-out activations for each target:
- joint angles
- end-effector distance-to-goal
- COM/root displacement proxy

Compare probe `R^2` between A and B:
- Higher `R^2` suggests the feature is linearly represented in that layer.
- If B is consistently higher on balance-related targets, this supports the video-prior representation hypothesis.

## 4. Compare representational geometry (CKA)

Compute layer-wise CKA between policy activations on matched trajectory segments:
- High CKA + similar probe scores implies similar features and geometry.
- Low CKA + similar probe scores implies functionally similar but geometrically rotated/reparameterized representations.
- Low CKA + different probe scores implies genuinely different internal feature content.

## 5. Test feature causal load-bearing via ablation

For each policy:
1. Rank penultimate units by absolute probe weight for COM proxy.
2. Zero top-k units during evaluation.
3. Measure success-rate drop and reward degradation.

Interpretation:
- Larger performance drop indicates those decoded features are causally load-bearing.
- If B degrades more under balance-feature ablation, its prior-induced balance representation is functionally important.

## 6. Decision rules

Call the hypothesis supported when:
- B reaches success threshold earlier than A, and
- B shows stronger probe performance on balance/trajectory features, and
- B shows larger ablation sensitivity on those same features.

Call the hypothesis not supported if:
- probe and ablation signals do not differentiate A vs B, or
- differences collapse under seed replication.

## 7. Reliability checks

- Repeat with at least one additional seed.
- Ensure probe train/test split is trajectory-disjoint.
- Confirm probes are not leaking targets through preprocessing shortcuts.
- Verify BC initialization quality independently (B should kinematically reach target before PPO).

## 8. Deliverables

- Learning curves for A and B.
- Probe metrics table.
- CKA heatmap figure.
- Ablation impact table/plot.
- One concise interpretation section stating what changed in internal representations and what did not.

