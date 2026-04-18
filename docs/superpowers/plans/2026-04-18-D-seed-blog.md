# Seed Data + Blog (Workstream D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Curate 4 reference video clips, pre-cache their GVHMR trajectories, write the blog post outline + 4 core paragraphs, and produce the 2-minute demo script.

**Architecture:** Seed clips are stored in Supabase Storage and referenced in the `clips` table. GVHMR outputs are cached to avoid rerunning at demo time. Blog and demo artifacts are plain markdown files committed to the repo.

**Tech Stack:** yt-dlp, Modal (GVHMR endpoint), Supabase Storage, Python script, markdown

**Prerequisites:** Plan 00 complete (Supabase project, `.env` with all keys, GVHMR Modal endpoint live).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/seed_clips.py` | Create | Download 4 clips, run GVHMR, upload to Supabase, insert `clips` rows |
| `data/seed_manifest.json` | Create | Records of seeded clips (id, YouTube URL, SMPL path) |
| `blog/outline.md` | Create | Blog post section headings + key points |
| `blog/draft.md` | Create | 4 core paragraphs (intro, method, results, future) |
| `demo/demo_script.md` | Create | Exact 2-minute spoken + screen script |
| `data/artifacts/evolutions/template/program.md.example` | Create | Example program.md shown in blog/demo |
| `tests/test_seed.py` | Create | Smoke test: seed manifest exists + clips table has rows |

---

## Task D1: Seed clips + GVHMR cache

- [ ] **Step 1: Write seed test first**

Create `tests/test_seed.py`:

```python
import json
from pathlib import Path

def test_seed_manifest_exists():
    manifest = Path("data/seed_manifest.json")
    assert manifest.exists(), "Run: python scripts/seed_clips.py first"
    clips = json.loads(manifest.read_text())
    assert len(clips) >= 3

def test_seed_manifest_has_smpl_paths():
    clips = json.loads(Path("data/seed_manifest.json").read_text())
    for clip in clips:
        assert "smpl_url" in clip, f"Missing smpl_url in clip {clip.get('id')}"
        assert clip["smpl_url"].startswith("https://"), f"Invalid URL: {clip['smpl_url']}"
```

- [ ] **Step 2: Run — expect failure (manifest doesn't exist yet)**

```bash
python -m pytest tests/test_seed.py -v
# Expected: AssertionError: Run: python scripts/seed_clips.py first
```

- [ ] **Step 3: Create `scripts/seed_clips.py`**

```python
"""
Download 4 reference clips, run GVHMR, upload artifacts to Supabase.
Run once: python scripts/seed_clips.py
"""
from __future__ import annotations
import json, os, subprocess, tempfile, uuid
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supa = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

CLIPS = [
    {
        "id":    "waving_person",
        "label": "Person waving",
        "url":   "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # replace with real clip URL
        "start": 10,   # seconds into video to trim
        "end":   16,
    },
    {
        "id":    "box_lift",
        "label": "Person lifting a box",
        "url":   "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # replace
        "start": 0,
        "end":   6,
    },
    {
        "id":    "arm_raise",
        "label": "Person raising arms",
        "url":   "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # replace
        "start": 0,
        "end":   6,
    },
    {
        "id":    "sidestep",
        "label": "Person sidestepping",
        "url":   "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # replace
        "start": 0,
        "end":   6,
    },
]

MANIFEST_PATH = Path("data/seed_manifest.json")


def download_clip(url: str, start: int, end: int, dest: Path) -> None:
    subprocess.run(
        ["yt-dlp", "-f", "mp4[height<=720]",
         "--external-downloader", "ffmpeg",
         "--external-downloader-args", f"-ss {start} -to {end}",
         "-o", str(dest), url],
        check=True,
    )


def upload_to_supabase(local_path: Path, remote_path: str, bucket: str) -> str:
    with open(local_path, "rb") as f:
        supa.storage.from_(bucket).upload(remote_path, f, {"upsert": "true"})
    return supa.storage.from_(bucket).get_public_url(remote_path)


def run_gvhmr(video_url: str) -> str:
    """Dispatch to Modal GVHMR endpoint. Returns SMPL pkl URL."""
    from scripts.gvhmr_modal_probe import process_video  # type: ignore
    result = process_video.remote(video_url=video_url)
    return result.get("smpl_url", "")


def main() -> None:
    manifest = []
    for clip in CLIPS:
        print(f"Processing: {clip['id']}")
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / f"{clip['id']}.mp4"
            download_clip(clip["url"], clip["start"], clip["end"], mp4)

            # Upload raw video
            video_url = upload_to_supabase(mp4, f"seed/{clip['id']}.mp4", "videos")

            # Run GVHMR (returns smpl pkl URL)
            smpl_url = run_gvhmr(video_url)

            # Insert clips row
            supa.table("clips").upsert({
                "id":         clip["id"],
                "label":      clip["label"],
                "video_path": video_url,
                "smpl_path":  smpl_url,
            }).execute()

            manifest.append({
                "id":        clip["id"],
                "label":     clip["label"],
                "video_url": video_url,
                "smpl_url":  smpl_url,
            })
            print(f"  ✓ {clip['id']}: video={video_url[:60]}...")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"\n✓ Manifest written to {MANIFEST_PATH}")
    print(f"✓ {len(manifest)} clips seeded in Supabase")


if __name__ == "__main__":
    main()
```

> **NOTE:** Replace the placeholder YouTube URLs in `CLIPS` with real short clips showing the motions you want to demonstrate. Good sources: Mixamo demo videos, fitness tutorial clips, motion capture demos. Clips must show a single person moving clearly, front-facing, well-lit.

- [ ] **Step 4: Replace YouTube URLs with real clips**

Edit `scripts/seed_clips.py` and update the `url` fields in `CLIPS` with 4 real YouTube videos showing clear human motion (waving, lifting, arm raise, sidestep).

- [ ] **Step 5: Run seeding**

```bash
python scripts/seed_clips.py
# Expected: ~15-20 min (GVHMR takes ~4 min per clip on Modal warm)
# Expected output: "✓ 4 clips seeded in Supabase"
```

- [ ] **Step 6: Run seed test**

```bash
python -m pytest tests/test_seed.py -v
# Expected: 2 passed
```

- [ ] **Step 7: Commit**

```bash
git add scripts/seed_clips.py tests/test_seed.py data/seed_manifest.json
git commit -m "feat: seed 4 reference clips with GVHMR cache"
```

---

## Task D2: program.md example (for demo + blog)

- [ ] **Step 1: Create `data/artifacts/evolutions/template/program.md.example`**

```markdown
# Research Agenda — Box Lifting Robot

## Task
Design a robot morphology and controller that can reliably pick up a box
from the ground and lift it to waist height, matching the motion demonstrated
in the reference video.

## What to optimize
- Minimize trajectory tracking error against the GVHMR-extracted human motion
- Maximize Gemini Robotics-ER 1.6 task completion probability

## Morphology exploration strategy
Start with a biped (2 legs, 2 arms). If tracking error is high after 3 iterations,
try increasing arm_dof to 7 (more wrist articulation). If the robot keeps falling,
reduce leg_length to improve stability. Explore arm_length in 0.4–0.7m range.

## Controller exploration strategy
Default 40 epochs of behavioral cloning. If loss plateau is reached before epoch 30,
try reducing learning_rate to 1e-4. Try increasing grad_clip_norm to 2.0 if gradients
are unstable.

## Known failure modes to avoid
- torso_length < 0.2m causes MuJoCo loading errors
- num_legs=4 with high arm_dof (>5) makes training slow — skip quadruped+7dof combos
- epochs > 40 is not permitted (prepare.py enforces this)

## Success threshold
Score >= 0.75 (tracking weight 0.6, ER16 weight 0.4).
Stop early if 5 consecutive iterations show no improvement.
```

- [ ] **Step 2: Commit**

```bash
git add data/artifacts/evolutions/template/program.md.example
git commit -m "docs: add example program.md for demo and blog"
```

---

## Task D3: Blog post outline + 4 core paragraphs

- [ ] **Step 1: Create `blog/outline.md`**

```markdown
# Blog Post Outline: autoResearch for Robotics

## Title options
- "We ported Karpathy's autoresearch to robot co-design"
- "Text → evolved robot: 14 hours, 20 GPU iterations, one approved morphology"
- "Robot design by autoresearch: what happens when an AI agent designs its own body"

## Sections

1. **Hook / what we built** (200 words)
   - One paragraph, present tense, read like a live demo
   - Show the pipeline in one sentence

2. **Background: Karpathy's autoresearch** (150 words)
   - What the original repo does (NanoChat + 5-min training budget)
   - The key insight: agent edits code, measures, keeps best, iterates

3. **Our port to robotics: the three changes** (300 words)
   - Change 1: train.py + morphology_factory.py instead of just train.py
   - Change 2: fitness = tracking error + ER 1.6 success probability
   - Change 3: human approval gate at program.md (one HITL checkpoint)

4. **The pipeline in detail** (400 words)
   - Step by step with screenshots of dashboard
   - Include evolution history timeline image
   - Show program.md from demo run

5. **Results: what the agent discovered** (200 words)
   - Best morphology params (paste from demo run)
   - Agent's reasoning trace excerpts
   - Final score + simulation video embed

6. **Limitations and future work** (150 words)
   - Parametric morphology space (12 params) — not fully freeform
   - Imitation only — no novel behavior discovery
   - v2: Dedalus for always-on orchestration

7. **Conclusion + links** (100 words)
   - GitHub, demo video, LeRobot dataset export
```

- [ ] **Step 2: Create `blog/draft.md`**

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add blog/
git commit -m "docs: add blog post outline and 4-section draft"
```

---

## Task D4: 2-minute demo script

- [ ] **Step 1: Create `demo/demo_script.md`**

```markdown
# 2-Minute Demo Script

**Format:** Screen recording + voiceover. No live coding. Browser tab pre-loaded at `localhost:3000`.

---

## T+0:00 — Open dashboard, type prompt

**Screen:** http://localhost:3000 (Screen 1 — prompt entry)
**Say:** "We start by telling the system what we want a robot to do."
**Action:** Type: "a robot that picks up a box and carries it upstairs"
**Action:** Click "Analyze task"

---

## T+0:10 — Show task analysis (Screen 2)

**Screen:** `/ingest/[jobId]` — ER 1.6 output + YouTube clip preview
**Say:** "Gemini Robotics-ER 1.6 analyzed the prompt and fetched a reference video from YouTube.
It extracted the task goal, affordances, and success criteria."
**Point to:** affordance badges, success criteria text, YouTube embed playing

---

## T+0:25 — Click "Draft research plan"

**Action:** Click "Draft research plan"
**Say:** "The system now uses Codex to draft a research agenda in plain English.
This is the only point where a human is in the loop."

---

## T+0:35 — Show program.md in Monaco editor (Screen 3)

**Screen:** `/evolutions/[evoId]/program`
**Say:** "Here's the proposed research plan. I can edit it — or just approve it."
**Action:** Make one small edit (add a sentence), then click "✓ Approve + Start"

---

## T+0:50 — Evolution dashboard opens, iteration 1 lands (Screen 4)

**Screen:** `/evolutions/[evoId]`
**Say:** "The autoresearch loop is now running. Each iteration: the agent proposes
a new robot design, trains a controller by imitation, runs it in simulation, and
scores the result."
**Wait for:** First iteration card to appear in history pane (~30s for a pre-warmed run)

---

## T+1:10 — Show iteration 1 result

**Point to:** fitness score, replay video playing in right pane, 3D morphology in center
**Say:** "This is iteration 1. Score 0.42. The agent noted the arms were too short to reach
the box — let's see what it tries next."

---

## T+1:25 — Click a later iteration from history (pre-computed)

**Action:** Click iteration 7 thumbnail (pre-baked from overnight run, score ~0.78)
**Say:** "Here's iteration 7. The agent widened the arm range and increased arm DOF to 7.
Score jumped to 0.78."
**Show:** Iteration drawer — reasoning log, train.py diff, replay video

---

## T+1:45 — Click "✓ Approve best + Export"

**Say:** "We approve the best result and export."
**Action:** Click "✓ Approve best + Export"
**Show:** Download link appears — `.parquet`, `morphology.urdf`, `controller.pt`

---

## T+2:00 — End

**Say:** "The exported dataset is LeRobot-compatible — ready to fine-tune a real policy
on a physical robot. All in 14 hours of build time."
**Screen:** GitHub repo URL + demo video link

---

## Pre-demo checklist

- [ ] Backend running: `uvicorn demo.app:app --reload`
- [ ] Frontend running: `cd apps/web && npm run dev`
- [ ] Supabase Realtime enabled on `iterations` table
- [ ] At least 7 pre-baked iterations loaded for the overnight evo (from `scripts/run_demo_evolution.py`)
- [ ] Container pre-warmed: make one dummy Modal call 10 min before demo
- [ ] Microphone tested
- [ ] OBS or Quicktime recording set up, tested, 1440p
```

- [ ] **Step 2: Commit**

```bash
git add demo/demo_script.md
git commit -m "docs: add 2-minute demo script with pre-demo checklist"
```

---

## Task D5: Run all seed smoke tests

```bash
make smoke-seed
# Expected: 2 passed
```
