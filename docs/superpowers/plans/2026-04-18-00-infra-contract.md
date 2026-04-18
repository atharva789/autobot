# Infra + Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap Supabase project, freeze Python + TypeScript interface types, apply DB schema, and create shared Makefile targets — all other workstreams are blocked until this plan is complete.

**Architecture:** Supabase cloud Postgres replaces SQLite. Frozen dataclasses in `packages/pipeline/types.py` are the single source of truth for all cross-workstream types. Supabase CLI generates matching TypeScript types for the frontend.

**Tech Stack:** Supabase CLI, supabase-py, Python 3.11 dataclasses, Next.js 14 (type-gen only), Make

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `packages/pipeline/__init__.py` | Create | Package marker |
| `packages/pipeline/types.py` | Create | Frozen interface types (single source of truth) |
| `supabase/migrations/0001_autoresearch.sql` | Create | All new tables + Realtime publication |
| `.env.example` | Create | All required env vars documented |
| `.env` | Create (gitignored) | Real secrets — operator fills in |
| `Makefile` | Create | `make dev`, `make test`, `make smoke-*`, `make e2e-smoke` |
| `pyproject.toml` | Create | Python deps for the whole repo |
| `apps/web/package.json` | Create | Node deps |

---

## Task 1: Supabase project + credentials

- [ ] **Step 1: Create Supabase project**

Go to https://supabase.com → New project → name: `autoresearch-robotics` → region: us-east-1 → generate strong password. Wait for provisioning (~60s).

- [ ] **Step 2: Install Supabase CLI**

```bash
brew install supabase/tap/supabase-cli
supabase --version   # expect 1.x
```

- [ ] **Step 3: Link project**

```bash
cd /Users/thorbthorb/Downloads/IL_ideation
supabase login       # opens browser
supabase link --project-ref <YOUR_PROJECT_REF>
```

Find `<YOUR_PROJECT_REF>` in Supabase dashboard → Settings → General → Reference ID.

- [ ] **Step 4: Collect credentials into `.env`**

From Supabase dashboard → Settings → API:

```bash
cat > .env << 'EOF'
# Supabase
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=<anon key>
SUPABASE_SERVICE_KEY=<service_role key>

# Modal
MODAL_TOKEN_ID=<from modal token new>
MODAL_TOKEN_SECRET=<from modal token new>

# Gemini
GEMINI_API_KEY=<from aistudio.google.com>

# YouTube
YOUTUBE_API_KEY=<from console.cloud.google.com>

# Anthropic (for Claude CLI fallback)
ANTHROPIC_API_KEY=<from console.anthropic.com>
EOF
```

- [ ] **Step 5: Create `.env.example`**

```bash
cat > .env.example << 'EOF'
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=
MODAL_TOKEN_ID=
MODAL_TOKEN_SECRET=
GEMINI_API_KEY=
YOUTUBE_API_KEY=
ANTHROPIC_API_KEY=
EOF
```

- [ ] **Step 6: Add `.env` to `.gitignore`**

```bash
echo '.env' >> .gitignore
git add .env.example .gitignore
git commit -m "chore: add env template and gitignore"
```

---

## Task 2: Python package + frozen types

- [ ] **Step 1: Write the test first**

Create `tests/test_types.py`:

```python
from packages.pipeline.types import MorphologyParams, TrialResult, EvolutionConfig
import dataclasses, pytest

def test_morphology_params_is_frozen():
    p = MorphologyParams(num_arms=2, num_legs=2, has_torso=True,
                         torso_length=0.4, arm_length=0.5, leg_length=0.7,
                         arm_dof=5, leg_dof=4, spine_dof=1,
                         joint_damping=0.1, joint_stiffness=10.0, friction=0.8)
    with pytest.raises(dataclasses.FrozenInstanceError):
        object.__setattr__(p, "num_arms", 99)

def test_trial_result_fields():
    r = TrialResult(tracking_error=0.1, er16_success_prob=0.8,
                    fitness_score=0.78, replay_mp4_url="https://x",
                    controller_ckpt_url="https://y", trajectory_npz_url="https://z",
                    reasoning_md="tried longer arms")
    assert r.fitness_score == 0.78

def test_evolution_config_defaults():
    c = EvolutionConfig()
    assert c.max_iters == 20
    assert c.cost_alarm_usd == 50.0
    assert c.fitness_weights == (0.6, 0.4)
```

- [ ] **Step 2: Run test — expect import failure**

```bash
python -m pytest tests/test_types.py -v
# Expected: ModuleNotFoundError: No module named 'packages'
```

- [ ] **Step 3: Create package files**

```bash
touch packages/__init__.py packages/pipeline/__init__.py
```

Create `packages/pipeline/types.py`:

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class MorphologyParams:
    num_arms:        int
    num_legs:        int
    has_torso:       bool
    torso_length:    float   # meters, 0.2..0.6
    arm_length:      float   # meters, 0.3..0.8
    leg_length:      float   # meters, 0.4..1.0
    arm_dof:         int     # 3..7
    leg_dof:         int     # 3..6
    spine_dof:       int     # 0..3
    joint_damping:   float   # 0.01..1.0
    joint_stiffness: float   # 1..100
    friction:        float   # 0.3..1.2


@dataclass(frozen=True)
class TrialResult:
    tracking_error:      float
    er16_success_prob:   float
    fitness_score:       float
    replay_mp4_url:      str
    controller_ckpt_url: str
    trajectory_npz_url:  str
    reasoning_md:        str


@dataclass(frozen=True)
class EvolutionConfig:
    max_iters:            int                 = 20
    max_hours:            float               = 2.0
    cost_alarm_usd:       float               = 50.0
    fitness_weights:      tuple[float, float] = (0.6, 0.4)
    keep_best_threshold:  float               = 0.01
```

- [ ] **Step 4: Run test — expect pass**

```bash
python -m pytest tests/test_types.py -v
# Expected: 3 passed
```

- [ ] **Step 5: Commit**

```bash
git add packages/ tests/test_types.py
git commit -m "feat: add frozen interface types (MorphologyParams, TrialResult, EvolutionConfig)"
```

---

## Task 3: Supabase migration

- [ ] **Step 1: Write migration file**

Create `supabase/migrations/0001_autoresearch.sql`:

```sql
-- Existing tables kept as-is (clips, runs, exports).
-- Add new tables for autoresearch loop.

CREATE TABLE IF NOT EXISTS evolutions (
  id              TEXT PRIMARY KEY,
  run_id          TEXT REFERENCES runs(id),
  program_md      TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending|running|stopped|done
  best_iteration_id TEXT,
  total_cost_usd  NUMERIC(8,4) DEFAULT 0,
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS morphologies (
  id              TEXT PRIMARY KEY,
  urdf_url        TEXT,
  latent_z_json   TEXT,   -- JSON array of 8 floats
  params_json     TEXT,   -- JSON of MorphologyParams fields
  num_dof         INT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS iterations (
  id                  TEXT PRIMARY KEY,
  evolution_id        TEXT REFERENCES evolutions(id),
  iter_num            INT NOT NULL,
  morphology_id       TEXT REFERENCES morphologies(id),
  controller_ckpt_url TEXT,
  trajectory_npz_url  TEXT,
  replay_mp4_url      TEXT,
  fitness_score       NUMERIC(6,4),
  tracking_error      NUMERIC(6,4),
  er16_success_prob   NUMERIC(6,4),
  reasoning_log       TEXT,
  train_py_diff       TEXT,
  morph_factory_diff  TEXT,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ingest_jobs (
  id              TEXT PRIMARY KEY,
  source_url      TEXT,
  er16_plan_json  TEXT,   -- JSON: task_goal, affordances, success_criteria, search_queries
  gvhmr_job_id    TEXT,
  smpl_path       TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending|processing|done|failed
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS program_md_drafts (
  id                  TEXT PRIMARY KEY,
  evolution_id        TEXT REFERENCES evolutions(id),
  generator           TEXT,   -- 'codex' | 'claude-code'
  draft_content       TEXT,
  approved            BOOLEAN DEFAULT FALSE,
  approved_at         TIMESTAMPTZ,
  user_edited_content TEXT
);

-- Enable Supabase Realtime on iterations so dashboard updates live
ALTER PUBLICATION supabase_realtime ADD TABLE iterations;
```

- [ ] **Step 2: Apply migration**

```bash
supabase db push
# Expected: Migration applied successfully
```

Verify in Supabase dashboard → Table Editor: all 5 new tables visible.

- [ ] **Step 3: Generate TypeScript types**

```bash
supabase gen types typescript --project-id <YOUR_PROJECT_REF> \
  > apps/web/src/lib/supabase-types.ts
```

- [ ] **Step 4: Commit**

```bash
git add supabase/ apps/web/src/lib/supabase-types.ts
git commit -m "feat: apply autoresearch schema migration + generate TS types"
```

---

## Task 4: Python dependencies

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "autoresearch-robotics"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "pydantic>=2.0",
  "supabase>=2.4",
  "google-generativeai>=0.5",
  "google-api-python-client>=2.120",
  "yt-dlp>=2024.4",
  "modal>=0.62",
  "torch>=2.2",
  "torch-geometric>=2.5",
  "mujoco>=3.1",
  "numpy>=1.26",
  "pink>=3.1",
  "pinocchio>=3.1",
  "python-dotenv>=1.0",
  "httpx>=0.27",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]
```

- [ ] **Step 2: Install**

```bash
pip install -e ".[dev]"
# MuJoCo and torch-geometric may take 2-3 min
```

- [ ] **Step 3: Verify key imports**

```bash
python -c "import mujoco; print('mujoco ok')"
python -c "import torch_geometric; print('pyg ok')"
python -c "import supabase; print('supabase ok')"
python -c "import modal; print('modal ok')"
```

---

## Task 5: Makefile

- [ ] **Step 1: Create Makefile**

```makefile
.PHONY: dev test smoke-api smoke-morph smoke-gnn smoke-seed e2e-smoke

dev:
	uvicorn demo.app:app --reload &
	cd apps/web && npm run dev

test:
	python -m pytest tests/ -q --timeout=60

smoke-api:
	python -m pytest tests/test_api.py tests/test_evolutions.py tests/test_ingest.py -q

smoke-morph:
	python -m pytest tests/test_morphology.py -q

smoke-gnn:
	python -m pytest tests/test_gnn.py -q

smoke-seed:
	python -m pytest tests/test_seed.py -q

e2e-smoke:
	python tests/e2e_smoke.py
```

- [ ] **Step 2: Commit**

```bash
git add Makefile pyproject.toml
git commit -m "chore: add Makefile and pyproject.toml"
```

---

## Task 6: Node dependencies

- [ ] **Step 1: Scaffold Next.js app**

```bash
cd apps/web
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --import-alias "@/*"
# answer: yes to all defaults
```

- [ ] **Step 2: Install additional deps**

```bash
npm install @supabase/supabase-js @monaco-editor/react \
  @react-three/fiber @react-three/drei three \
  @tanstack/react-query lucide-react
npx shadcn@latest init   # choose: New York style, zinc base color, yes CSS vars
npx shadcn@latest add button input card badge textarea dialog drawer tabs
```

- [ ] **Step 3: Create `apps/web/src/lib/supabase.ts`**

```typescript
import { createClient } from "@supabase/supabase-js";
import type { Database } from "./supabase-types";

export const supabase = createClient<Database>(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);
```

- [ ] **Step 4: Create `apps/web/.env.local`**

```bash
cat > apps/web/.env.local << 'EOF'
NEXT_PUBLIC_SUPABASE_URL=<your SUPABASE_URL>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your SUPABASE_ANON_KEY>
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF
```

- [ ] **Step 5: Verify Next.js boots**

```bash
npm run dev
# Open http://localhost:3000 — expect default Next.js page
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/
git commit -m "chore: scaffold Next.js app with Supabase + shadcn + R3F deps"
```
