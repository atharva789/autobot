# autoResearch for Robotics: Text → Evolved Robot

> *This post describes a 14-hour build. All code is open-source. The demo video is at the bottom.*

---

## 1. What we built

You type "a robot that picks up a box." Thirty seconds later, you're watching
a robot — one the system just designed from scratch — attempting that exact task
in a physics simulator. Over the next two hours, twenty versions of the robot try
and fail and improve. The best one gets exported as a Hugging Face LeRobot dataset,
ready to fine-tune a real policy. We built this in 14 hours, using Karpathy's
`autoresearch` repo as the core loop, Gemini Robotics-ER 1.6 as the success oracle,
and GVHMR as the motion reference.

---

## 2. The original autoresearch, in 40 words

Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) gives an AI agent
a small LLM training script (`train.py`), a 5-minute wall-clock budget, and a single
metric (validation bits-per-byte). The agent edits `train.py`, trains, measures, keeps
what works, and repeats — overnight. You wake up to a log of experiments and a better model.

---

## 3. Three changes we made to port it to robotics

**First: two editable files instead of one.** In the original, the agent edits only
`train.py`. We gave it two: `train.py` (the GNN controller architecture and training
hyperparameters) and `morphology_factory.py` (the parametric robot body generator). The
agent can independently evolve what the robot looks like and how it moves.

**Second: a two-term fitness function.** `val_bpb` in the original is unambiguous —
lower is better, always. For robotics, "better" is harder to define. We use:
`0.6 × (1 − tracking_error) + 0.4 × er16_success_probability`. The first term rewards
reproducing the reference human motion exactly; the second term rewards actually completing
the task as judged by Gemini Robotics-ER 1.6, which watches the rollout video and returns
a probability of task success. This two-term design lets the agent trade off "looks right"
against "works right."

**Third: one human-in-the-loop gate.** Before the loop starts, the system drafts
a `program.md` — a plain-English research agenda (what to optimize, what to avoid, what
counts as success). The human reads it, optionally edits it, and clicks Approve. After
that, the loop runs unattended. The agent refers to `program.md` before each iteration and
appends its reasoning. The full reasoning trace becomes the evolution history visible in
the dashboard — and, later, the raw material for this blog post.

---

## 4. Results

*(Fill in after demo run. Paste: best morphology params, final score,
agent reasoning excerpts, simulation video embed.)*

---

## 5. Limitations

This system operates over a 12-parameter morphology space: arm count, leg count, limb
lengths, joint counts, actuator properties. The VAE we trained gives us a smooth
manifold over this space, but it cannot invent morphological primitives that aren't
in the parametric family — no wheels, no continuous tracks, no soft actuators. The
controller is trained by imitation learning (behavioral cloning), which means it can
reproduce demonstrated motions well but cannot discover behaviors that go beyond the
reference video. A PPO-based controller could, in principle, improve on the demonstration;
we traded that capability for the 4-minute-per-iteration training budget that makes the
live demo feasible.

---

*GitHub · Demo video · LeRobot dataset*
