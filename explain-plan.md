# explain-plan.md

**Project: autoResearch for Robotics — text → evolved robot**

A plain-language explanation of what we are building and exactly how it works. No ambiguity. Terms defined the first time they are used.

---

## Part 1 — Features (what the user sees)

### Feature 1: a single-page dashboard

The user opens one web page. There are three panes side by side:

- **Left pane — the prompt.** A text box ("build me a robot that can pick up a box and walk upstairs") and, below it, a list of reference video clips the system has fetched. One button: "Run pipeline."
- **Middle pane — the generated robot.** A rendering of the robot the system just designed: how many arms and legs it has, how long each limb is, how many joints it has. Small readouts next to it show its "fitness score" and "stability score."
- **Right pane — the simulation.** A short video of that robot actually attempting the task inside a physics simulator (MuJoCo). Next to it: tracking error, task success probability.

Below all three panes is a **history timeline**: thumbnails of every robot the system has tried so far, the score each one got, and a short written explanation from the agent ("I shortened the right arm by 8 cm because the last version couldn't reach the box").

### Feature 2: the research agenda, with human approval

Before any robot is designed, the system drafts a short research plan in plain English — what it will optimize, how it will measure success, what constraints it will respect. This plan is called `program.md`.

The user sees this plan in an editor, reads it, and either:
- clicks **Approve** (runs as-is), or
- edits the text and then clicks **Approve**, or
- clicks **Regenerate** (ask the system to draft a new version).

The evolution loop does not start until the user approves.

### Feature 3: the evolution loop with stop + pick controls

After approval, the system starts trying out robot designs, one at a time. Each attempt takes about 5 minutes. The user can:
- watch each new attempt land on the dashboard in real time,
- click **Stop** at any point to abort,
- click **Mark as best** on any attempt to override the system's automatic choice.

### Feature 4: export

When the user is happy, they click **Approve + Export**. The system produces:
- a `.parquet` file compatible with Hugging Face's LeRobot format (standard imitation-learning dataset),
- the robot's description file (`.urdf`),
- the trained controller (`.pt`).

### Feature 5: the evolution history (for the research paper / blog post)

A timeline of every design the system tried, in order, with:
- thumbnail of the morphology,
- the fitness score,
- the agent's written reasoning for why it chose those changes,
- a link to the 5-second simulation video.

This timeline is the artifact that gets embedded in the blog post / write-up.

---

## Part 2 — Mechanics (how it works, step by step)

### Step 1 — The user types a prompt

Example: *"A robot that can carry a box up a flight of stairs."*

### Step 2 — Gemini Robotics-ER 1.6 analyzes the prompt

Gemini Robotics-ER 1.6 is a Google model (released April 2026) that specializes in understanding physical tasks. It takes the prompt and produces a structured output:

```
{
  "task_goal": "lift object and traverse stairs",
  "affordances": ["grip", "biped-walk", "stair-climb"],
  "success_criteria": "object remains grasped, agent reaches top step",
  "search_queries": ["person carrying box upstairs", "stair climbing demo"]
}
```

We access it through the Gemini API — a single HTTP call costs about $0.02.

### Step 3 — The system fetches a reference video

The system takes `search_queries[0]` and sends it to YouTube's Data API. YouTube returns a list of matching videos. The system picks the top result and downloads it with `yt-dlp`. The clip is stored in Supabase Storage (a cloud file store).

### Step 4 — GVHMR extracts human motion from the video

GVHMR is a pre-trained computer-vision model that watches a video of a person moving and outputs the exact 3D position of every joint in that person's body, at every frame. This output is called an **SMPL-X trajectory**.

We already have a GVHMR endpoint running on Modal (a cloud GPU service). We send it the video URL; it returns the trajectory file.

### Step 5 — The agent drafts `program.md`

The system opens a local terminal command (`codex` CLI — fallback: `claude` CLI) inside the project folder. It feeds in the task analysis from step 2 and asks the agent: *"Write a short research plan for evolving a robot that achieves this task."*

The agent writes `program.md`. The file is shown to the user in the dashboard's Monaco editor.

### Step 6 — Human-in-the-loop approval

The user reads `program.md`, optionally edits it, and clicks **Approve**. The `program_md_drafts` table in Supabase records both the agent's version and the user's final version (for the paper).

### Step 7 — The evolution loop begins

The loop runs on the user's local machine. It repeats the same five sub-steps up to 20 times:

**Sub-step 7a — Agent proposes changes.**
The loop invokes `codex` CLI again: *"Here is `program.md`. Here are the last three attempts and their scores. Edit `train.py` and `morphology_factory.py` to try a better idea next."*

The agent rewrites these two files.

**Sub-step 7b — Generate the morphology.**
`morphology_factory.py` builds a `.urdf` file (a standard XML description of a robot: limb lengths, joints, masses). The shape is sampled from a trained VAE — a small neural network we trained once, up front, over ~2000 robot designs, that lets us sample *new* designs that are statistically similar to valid ones.

**Sub-step 7c — Train a controller.**
The controller is a small neural network called a **GNN** (graph neural network). Each joint of the robot is a "node"; each physical link between joints is an "edge." The GNN looks at sensor data at each joint and outputs a torque command. It is trained by imitation learning: we show it the retargeted human trajectory and teach it to reproduce those joint angles. Training takes about 4 minutes on a Modal A10G GPU.

**Sub-step 7d — Roll out in simulation.**
We drop the robot into a MuJoCo physics simulator and let the controller drive it. We record:
- **tracking error**: how closely the robot's joint angles matched the target trajectory (smaller is better),
- **success probability**: we send the 5-second replay video to Gemini Robotics-ER 1.6 and ask "did this robot complete the task?"

**Sub-step 7e — Score and record.**

```
score = 0.6 × (1 − normalized_tracking_error)  +  0.4 × ER16_success_probability
```

We insert a new row into the `iterations` table in Supabase. Supabase Realtime (a push-notification feature) instantly pushes that row to the dashboard — the new attempt appears on the history timeline.

### Step 8 — Keep-best policy

After each iteration, the system compares the new score to the current best. If it's more than 1% better, it becomes the new best. The "best" attempt is flagged in the database. The user can override this with the **Mark as best** button.

### Step 9 — Stopping

The loop stops when any of these is true:
- 20 iterations reached,
- 2 wall-clock hours elapsed,
- no improvement in 5 consecutive iterations,
- user clicks **Stop**.

### Step 10 — Export

The user clicks **Approve + Export**. The system packages:
- `dataset.parquet` (LeRobot format),
- `morphology.urdf`,
- `controller.pt`,
- `evolution_log.md` (the full reasoning trace, for the blog post).

All four are written to Supabase Storage and a download link appears.

---

## Part 3 — Where each piece runs

| Piece | Where it runs | Why |
|---|---|---|
| Frontend (Next.js dashboard) | User's browser | standard web app |
| API (FastAPI, Python) | Local machine | thin layer over Supabase + orchestrator |
| Supabase (Postgres + Storage + Realtime) | Supabase cloud (free tier) | remote DB + file store + push notifications |
| Gemini Robotics-ER 1.6 | Google cloud (API call) | model not available locally |
| YouTube Data API + yt-dlp | Local machine | search + download |
| GVHMR (pose extraction) | Modal (A10G, existing endpoint) | needs GPU, already deployed |
| VAE training (one-time) | Modal (A10G, ~40 min) | needs GPU |
| Evolution orchestrator | Local machine | drives Codex / Claude CLI, which need local auth |
| GNN controller training | Modal (A10G, ~4 min per iter) | needs GPU |
| MuJoCo physics + fitness eval | Modal (same container as GNN) | keeps data co-located |

---

## Part 4 — What is new about this

Three claims, all modest and defensible:

1. **Porting Karpathy's `autoresearch` pattern from LLM training to robot co-design.** Karpathy's original shows an agent editing `train.py` on a nanochat. We show the same loop editing `train.py` and `morphology_factory.py` on a MuJoCo robot, optimizing a multi-term fitness (trajectory tracking + semantic success).
2. **Using Gemini Robotics-ER 1.6 as an automatic success-detection oracle inside the evolution loop.** ER 1.6 is designed to judge real-world task completion; we repurpose that for simulated rollouts.
3. **Human-in-the-loop at the research-agenda level, not at every iteration.** One approval gate (on `program.md`) + coarse overrides (Stop, Mark as best) is enough to stay in control without bottlenecking a 20-trial loop.

---

## Part 5 — What this is NOT

- Not a general-purpose robot-design tool. We operate on a 12-parameter parametric morphology space.
- Not a new RL algorithm. The controller is trained by imitation, not from scratch with reward.
- Not a new vision model. GVHMR and ER 1.6 are used as-is, off-the-shelf.
- Not deployed. The demo runs on the user's local machine + Supabase free tier + Modal pay-per-use.
