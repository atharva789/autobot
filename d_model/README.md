# d_model

This folder contains a repo-grounded write-up and a small LaTeX paper for the current `IL_ideation` codebase.

The core claim is straightforward: this project is not just "prompt the model again for a better robot." It is a hybrid co-design stack that combines structured generation, deterministic task conditioning, artifact grounding, a single human approval checkpoint, and a search loop over morphology plus controller code.

## What The System Actually Is

At the highest level, the repository implements a task-conditioned robot design workspace with an attached autoresearch-style training loop:

1. A task prompt is normalized into a `TaskSpec`.
2. The system generates multiple robot candidates with a model-facing structured schema.
3. Those candidates are reranked by deterministic task-fit logic and hardrails.
4. The selected design is grounded into render, BOM, telemetry, and validation artifacts.
5. A `program.md` checkpoint turns the chosen design into a human-reviewed research agenda.
6. An agentic loop edits morphology and training code, runs remote trials, scores results, and keeps the best iteration.

That structure is the important parallel with autoresearch: the model is a proposal mechanism inside a measured loop, not the loop itself.

## Architectural Thesis

The repo uses three layers that should be kept distinct:

- Proposal layer: Gemini-driven structured generation of robot candidates and research edits.
- Deterministic control layer: task capability extraction, hardrails, ranking, telemetry, and validation.
- Execution layer: MuJoCo/MJCF artifacts, remote Modal trials, replay generation, and artifact upload.

This separation matters because it prevents the system from collapsing into a pure prompt-chain. The proposal layer can be stochastic and exploratory while the control layer remains explicit, inspectable, and overridable.

## End-To-End Stack

### 1. Task grounding and capability extraction

The repository converts a natural-language robotics task into explicit capability requirements. `build_task_capability_graph(...)` expands prompt-level language into structured requirements such as `payload_stability`, `surface_attachment_strategy`, `dual_arm_grasping`, `traction_contact_strategy`, and task-family tags like `climbing`, `crawling`, or `slippery_terrain`.

This is one of the main anti-handwave mechanisms in the repo. Instead of asking a model to "reason better" each time, the system turns task semantics into a machine-readable target against which candidates are scored.

### 2. Structured candidate generation

`packages/pipeline/design_generator.py` uses Gemini with a deliberately compact schema. The file is explicit about why: richer provider-facing schemas can fail with "too many states for serving," so the repo shrinks the model-facing output and reconstructs richer internal objects afterward.

That design choice is technically important. It means the system is not relying on the model to emit the final internal data structure directly. The generation contract is:

- emit exactly three candidates
- force contrast across embodiment classes
- use a compact response schema
- post-process and normalize the result deterministically

The generation prompt also encodes a contrastive triad:

- Candidate A: conventional
- Candidate B: unconventional
- Candidate C: minimal

That is not cosmetic prompt writing. It is a diversity prior over the search frontier.

### 3. Deterministic task conditioning and reranking

The generated candidates are then passed through `apply_task_conditioning(...)`, which does four things:

- scores task-fit coverage
- adds risk flags
- applies hardrail results
- may override the model's preferred candidate

The implemented scoring rule is intentionally hybrid. Capability coverage dominates, design quality contributes a smaller term, and model confidence contributes the smallest term. Preferred embodiments add a small bonus and risk flags subtract score. Hardrail failures can cap the score sharply.

This means the LLM can suggest a candidate, but it cannot unilaterally choose it if the deterministic evaluator rejects that choice.

### 4. Artifact grounding: render, BOM, telemetry, validation

A candidate is not considered useful merely because it looks plausible in text. The repo grounds it into inspection artifacts:

- engineering render / scene payload
- MJCF output
- GLB render payload
- BOM and procurement confidence
- candidate telemetry
- validation report JSON

`build_design_validation_report(...)` checks structural completeness, task validity, compiler outputs, render quality, simulation viability, and procurement grounding. This is one of the strongest pieces of evidence that the repository is meant to be an engineering workspace rather than a concept generator.

Telemetry is also explicit. The repo computes estimated reach, backlash, bandwidth, payload margin, and design-quality summaries. Some of these are heuristics, but they are still much stronger than narrative-only model output because they convert design properties into stable review features.

### 5. Human-in-the-loop checkpoint via `program.md`

The single central approval point is `program.md`.

`demo/services/orchestrator.py` drafts that file from the ER-style task plan, either through Gemini or a deterministic fallback builder. The purpose of the file is to freeze:

- what morphology features to explore
- what controller changes to try
- how progress will be measured
- what failure modes to avoid

This is a practical architecture decision. Instead of forcing the human to micromanage every iteration, the repo makes the user approve the research agenda once and then lets the loop search within that envelope.

### 6. Agentic editing loop

The repo's orchestrator then acts like a bounded coding agent:

- it reads editable files
- sends them plus a task prompt to Gemini
- expects file-by-file rewritten outputs
- applies those edits back into the working tree
- optionally runs a second pass to catch PyTorch device mismatches

That last step is worth calling out. `review_code_for_device_issues(...)` is not a generic agent flourish; it is a narrow reliability guard aimed at a real failure class in research code.

### 7. Remote trial execution

The intended closed loop is implemented across `ModalDispatch`, `EvolutionService`, and `scripts/modal_trial_runner.py`.

Per trial, the remote worker:

1. writes the agent-edited `train.py` and `morphology_factory.py`
2. loads or downloads a motion trajectory
3. builds morphology and MJCF
4. retargets motion to the generated body
5. trains a controller
6. rolls out a replay video
7. scores the result with tracking error plus an ER16-style success oracle
8. uploads replay, checkpoint, and trajectory artifacts

That is the point at which the project becomes genuinely autoresearch-like. A proposal is only good if it survives execution and improves the measured objective.

## DL Framework

The repository's deep learning stack is compact but coherent.

### Morphology latent model

`packages/pipeline/vae.py` defines a morphology VAE over a 12-parameter robot design space:

- continuous parameters: torso length, arm length, leg length, damping, stiffness, friction
- discrete parameters: arm count, leg count, arm DoF, leg DoF, spine DoF, torso presence
- latent dimension: 8
- hidden dimension: 64

The model uses a standard encoder -> `(mu, logvar)` -> reparameterization -> decoder path with MSE reconstruction plus KL regularization. In methodological terms, this gives the system a compact latent prior over buildable morphologies, which is useful for guided sampling and controlled variation.

### Morphology-agnostic controller

`packages/pipeline/gnn.py` defines a shared-weights graph controller:

- nodes are MuJoCo bodies
- edges are bidirectional joint relations
- node feature size: 16
- edge feature size: 6
- encoder MLPs map node and edge features into a hidden space
- message passing uses three `GATv2Conv` layers
- a linear decoder emits one scalar per node

This is the most important DL design decision in the repo. Instead of training a separate controller architecture for each body plan, the controller is meant to generalize across morphologies by operating on the robot graph directly.

### Execution-time objective

The remote trial loop combines:

- kinematic retargeting from motion data to the sampled morphology
- controller training in MuJoCo
- rollout video generation
- fitness computed from tracking error and a Gemini ER16-like success probability

So the optimization target is neither purely differentiable nor purely learned. It is a hybrid objective that mixes simulator metrics with a vision-language success oracle.

## Agentic Architecture

The repo uses the term "agentic" in a concrete sense, not a branding sense.

The agentic architecture here means:

- planning around a persistent research agenda (`program.md`)
- code-edit proposals scoped to editable files
- automatic application of the proposal output
- looped execution on a remote worker
- artifact-backed scoring
- keep-best iteration state through the evolution service

This is closer to a local research operator plus remote experiment runner than to a general conversational agent.

## Why This Is More Than Auto-Prompting

The clean distinction is:

- auto-prompting: ask for a better answer
- autoresearch: propose a change, run it, score it, keep it or discard it

This repo is aiming for the second pattern. The generated proposal is only one component. Deterministic reranking, validation, telemetry, remote execution, and best-iteration tracking are the rest of the loop.

## Methodological Summary

The methodology used in the repo can be described as hybrid agentic co-design:

- Structured generation narrows the proposal language.
- Task conditioning turns language goals into explicit capability requirements.
- Hardrails reject designs that are semantically or physically misaligned.
- Artifact grounding forces every candidate to leave behind inspectable outputs.
- A graph controller provides morphology-agnostic control.
- A morphology VAE provides a compact latent prior over body plans.
- A remote trial loop tests edits in simulation and scores them with mixed metrics.
- Human approval is centralized rather than injected at every step.

That combination is the real contribution of the codebase. None of the individual pieces are exotic alone, but the repo composes them into a coherent robotics search workflow.

## Current Limits

The write-up should stay honest about the repository's maturity.

- The strongest implemented surface today is task-conditioned candidate generation, inspection artifacts, and workflow scaffolding.
- The evolution loop is architecturally present end-to-end, but its operational quality still depends on deployed Modal services, external model access, and surrounding infra.
- Several telemetry values are engineering heuristics rather than hardware-calibrated measurements.
- The repo is best understood as a local-first robotics co-design and experiment workspace, not as a finished robot compiler.

## Paper

The LaTeX paper is in `d_model/paper.tex`.

It is written to compile as a small four-page note with embedded TikZ diagrams. Build outputs should be written outside the repo, for example:

```bash
mkdir -p /tmp/d_model-paper
pdflatex -output-directory=/tmp/d_model-paper d_model/paper.tex
pdflatex -output-directory=/tmp/d_model-paper d_model/paper.tex
```

This environment does not currently have `pdflatex` or `latexmk`, so the file has been authored but not locally compiled here.
