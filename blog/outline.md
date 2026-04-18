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
