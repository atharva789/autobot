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
