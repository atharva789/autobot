# Integration (Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire all 5 workstreams together, run an end-to-end smoke test (prompt → ingest → 3-iter evolution → export), fix integration mismatches, and run the demo rehearsal 3×.

**Architecture:** No new code beyond glue fixes. This phase is validation-only. All substantive code lives in workstreams A–D.

**Prerequisites:** ALL of Plans A, B1, B2, C, D complete. All `make smoke-*` passing. Supabase Realtime enabled. VAE checkpoint in Modal volume.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tests/e2e_smoke.py` | Create | End-to-end smoke test script |
| `Makefile` | Modify | Add `e2e-smoke` target |
| `scripts/run_demo_evolution.py` | Create | Pre-bake overnight evolution for demo |

---

## Task INT-1: Type consistency check

- [ ] **Step 1: Verify Python types match**

```bash
python -c "
from packages.pipeline.types import MorphologyParams, TrialResult, EvolutionConfig
from demo.services.modal_dispatch import ModalDispatch
from demo.services.evolution_service import EvolutionService
print('All Python types import cleanly')
"
# Expected: All Python types import cleanly
```

- [ ] **Step 2: Verify TypeScript types compile**

```bash
cd apps/web && npx tsc --noEmit
# Expected: no errors
```

- [ ] **Step 3: Verify Supabase types match schema**

```bash
supabase gen types typescript --project-id <YOUR_PROJECT_REF> > /tmp/new_types.ts
diff apps/web/src/lib/supabase-types.ts /tmp/new_types.ts
# Expected: no diff (or re-run gen if schema was updated since Plan 00)
```

- [ ] **Step 4: Fix any type mismatches**

If diff shows differences: `cp /tmp/new_types.ts apps/web/src/lib/supabase-types.ts` and update any broken imports in frontend components.

---

## Task INT-2: End-to-end smoke test

- [ ] **Step 1: Create `tests/e2e_smoke.py`**

```python
"""
End-to-end smoke test. Uses real Modal + real Supabase. Mocks Gemini + YouTube.
Runs 3 iterations. Expected wall-clock: ~12 min.
Run: python tests/e2e_smoke.py
"""
from __future__ import annotations
import json, os, time, uuid
from unittest.mock import patch
from dotenv import load_dotenv

load_dotenv()

MOCK_ER16_PLAN = {
    "task_goal": "lift box to waist height",
    "affordances": ["grip", "lift"],
    "success_criteria": "box raised above knee level",
    "search_queries": ["person lifting box demo"],
}


def main() -> None:
    print("=== E2E Smoke Test ===\n")

    # 1. Start backend (check it's running)
    import httpx
    try:
        r = httpx.get("http://localhost:8000/health", timeout=3)
        assert r.json()["status"] == "ok"
        print("✓ Backend healthy")
    except Exception as e:
        print(f"✗ Backend not running: {e}")
        print("  Start with: uvicorn demo.app:app --reload")
        raise SystemExit(1)

    # 2. Ingest (mocked ER 1.6 + YouTube)
    from demo.services.ingest_service import IngestService
    svc = IngestService(
        gemini_api_key=os.environ.get("GEMINI_API_KEY", "fake"),
        youtube_api_key=os.environ.get("YOUTUBE_API_KEY", "fake"),
        supabase_url=os.environ["SUPABASE_URL"],
        supabase_key=os.environ["SUPABASE_SERVICE_KEY"],
    )
    with patch.object(svc, "analyze_prompt", return_value=MOCK_ER16_PLAN), \
         patch.object(svc, "search_youtube", return_value="dQw4w9WgXcQ"), \
         patch.object(svc, "download_clip", return_value=None), \
         patch.object(svc, "run_gvhmr", return_value="fake-gvhmr-job"):
        plan = svc.analyze_prompt("lift box")
        video_id = svc.search_youtube(plan["search_queries"][0])
    print(f"✓ Ingest mocked: video_id={video_id}")

    # 3. Create evolution via API
    r = httpx.post("http://localhost:8000/evolutions", json={
        "run_id": "smoke-run-1",
        "ingest_job_id": "smoke-ingest-1",
    }, timeout=30)
    if r.status_code not in (200, 201):
        print(f"✗ Create evolution failed: {r.status_code} {r.text}")
        raise SystemExit(1)
    evo = r.json()
    evo_id = evo["evolution_id"]
    print(f"✓ Evolution created: {evo_id}")
    print(f"  Draft program.md ({len(evo.get('draft_content',''))} chars)")

    # 4. Approve program.md
    r = httpx.post(
        f"http://localhost:8000/evolutions/{evo_id}/approve-program",
        json={"content": "# Smoke test agenda\nMinimize tracking error. Try biped with 5-DOF arms."},
        timeout=10,
    )
    assert r.status_code == 200, f"Approve failed: {r.text}"
    print("✓ Program approved, evolution loop starting in background")

    # 5. Wait for 3 iterations (poll Supabase)
    from supabase import create_client
    supa = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    t0 = time.time()
    timeout = 800   # ~13 min
    target_iters = 3
    print(f"  Waiting for {target_iters} iterations (up to {timeout//60} min)…", flush=True)

    while True:
        rows = supa.table("iterations").select("id,fitness_score,iter_num").eq("evolution_id", evo_id).execute()
        n = len(rows.data)
        if n >= target_iters:
            break
        elapsed = time.time() - t0
        if elapsed > timeout:
            print(f"✗ Timeout: only {n}/{target_iters} iterations after {elapsed:.0f}s")
            raise SystemExit(1)
        print(f"  {n}/{target_iters} iterations… ({elapsed:.0f}s)", end="\r", flush=True)
        time.sleep(10)

    print(f"\n✓ {n} iterations complete")
    for row in rows.data:
        print(f"  iter {row['iter_num']}: score={row.get('fitness_score')}")

    # 6. Check best_iteration_id set
    evo_row = supa.table("evolutions").select("best_iteration_id").eq("id", evo_id).single().execute()
    assert evo_row.data.get("best_iteration_id") is not None, "best_iteration_id not set"
    print(f"✓ best_iteration_id: {evo_row.data['best_iteration_id']}")

    # 7. Mark best (manual override test)
    first_iter_id = rows.data[0]["id"]
    r = httpx.post(f"http://localhost:8000/evolutions/{evo_id}/mark-best/{first_iter_id}", timeout=5)
    assert r.status_code == 200
    print(f"✓ Mark-best override: OK")

    # 8. Stop
    r = httpx.post(f"http://localhost:8000/evolutions/{evo_id}/stop", timeout=5)
    assert r.status_code == 200
    print("✓ Stop: OK")

    print("\n=== E2E SMOKE PASSED ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add to Makefile**

```makefile
e2e-smoke:
	python tests/e2e_smoke.py
```

- [ ] **Step 3: Run smoke test**

```bash
make e2e-smoke
# Expected: === E2E SMOKE PASSED === after ~12 min
# Requires: uvicorn demo.app:app --reload running in another terminal
```

- [ ] **Step 4: Fix any failures before proceeding**

Common failure modes and fixes:

| Failure | Likely cause | Fix |
|---|---|---|
| `Backend not running` | uvicorn not started | `uvicorn demo.app:app --reload` in separate terminal |
| `Create evolution failed: 500` | Missing env vars in backend | Check `.env` is loaded |
| `Timeout: 0/3 iterations` | Modal not deployed | `modal deploy scripts/modal_trial_runner.py` |
| `best_iteration_id not set` | Keep-best bug in orchestrator | Check `_run_evolution_loop` in `demo/routes/evolutions.py` |
| `Supabase insert fails` | RLS blocks service key | Disable RLS on new tables in Supabase dashboard |

- [ ] **Step 5: Commit**

```bash
git add tests/e2e_smoke.py Makefile
git commit -m "test: add E2E smoke test (prompt → 3 iterations → stop)"
```

---

## Task INT-3: Frontend integration check

- [ ] **Step 1: Start both services**

```bash
# Terminal 1
uvicorn demo.app:app --reload

# Terminal 2
cd apps/web && npm run dev
```

- [ ] **Step 2: Manual walkthrough — all 4 screens**

- [ ] Open http://localhost:3000 — Screen 1 loads, text area visible
- [ ] Type "a robot that picks up a box" → click "Analyze task"
- [ ] Screen 2 loads — ER 1.6 plan visible, YouTube embed plays
- [ ] Click "Draft research plan" → Screen 3 loads with Monaco editor, program.md visible
- [ ] Edit one line → click "✓ Approve + Start" → redirected to Screen 4
- [ ] Screen 4: evolution dashboard opens, status shows "running"
- [ ] Wait ~5 min → first iteration card appears in history pane (Realtime working)
- [ ] Click iteration card → drawer slides in, shows reasoning + replay video
- [ ] Click "★" (mark as best) → card gets yellow border
- [ ] Click "■ Stop" → status changes to "stopped"

- [ ] **Step 3: Fix any UI issues**

Common issues:
- CORS: add `allow_origins=["http://localhost:3000"]` to FastAPI app
- Realtime not firing: check `ALTER PUBLICATION supabase_realtime ADD TABLE iterations;` was applied
- Monaco not loading: ensure `dynamic()` import with `{ ssr: false }` is in `ProgramMdEditor.tsx`

- [ ] **Step 4: Build check**

```bash
cd apps/web && npm run build
# Expected: build succeeds, no TypeScript errors
```

---

## Task INT-4: Pre-bake demo evolution

- [ ] **Step 1: Create `scripts/run_demo_evolution.py`**

```python
"""
Run a full 20-iteration evolution overnight on the box-lift clip.
Results will be displayed from Supabase history in the live demo.
Run the night before the demo: python scripts/run_demo_evolution.py
"""
from __future__ import annotations
import httpx, time, json

BASE = "http://localhost:8000"

def main() -> None:
    # 1. Use pre-seeded clip
    print("Using pre-seeded 'box_lift' clip for demo evolution")

    # 2. Create evolution
    r = httpx.post(f"{BASE}/evolutions", json={
        "run_id": "demo-run-1",
        "ingest_job_id": "box_lift",   # seeded clip ID
    }, timeout=30)
    evo = r.json()
    evo_id = evo["evolution_id"]
    print(f"Evolution: {evo_id}")
    print(f"\nDraft program.md:\n{evo['draft_content']}\n")

    # 3. Approve with curated program.md
    curated = open("data/artifacts/evolutions/template/program.md.example").read()
    httpx.post(f"{BASE}/evolutions/{evo_id}/approve-program",
               json={"content": curated}, timeout=10)
    print("Approved. Evolution running (20 iters, ~2h)…")

    # 4. Poll until done
    while True:
        r = httpx.get(f"{BASE}/evolutions/{evo_id}", timeout=5)
        evo = r.json()
        status = evo.get("status")
        cost = evo.get("total_cost_usd", 0)
        print(f"  status={status} cost=${cost:.2f}", end="\r", flush=True)
        if status in ("done", "stopped"):
            break
        time.sleep(30)

    print(f"\n✓ Demo evolution complete. Best: {evo.get('best_iteration_id')}")
    print(f"  Total cost: ${evo.get('total_cost_usd', 0):.2f}")
    print(f"\nSet this evolution ID in demo script: {evo_id}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the night before demo**

```bash
python scripts/run_demo_evolution.py
# Expected: runs ~2h, prints evolution ID when done
# Note the evolution ID — update demo_script.md with it
```

- [ ] **Step 3: Commit**

```bash
git add scripts/run_demo_evolution.py
git commit -m "chore: add demo evolution pre-bake script"
```

---

## Task INT-5: Demo rehearsal (3×)

- [ ] **Step 1: Run through demo_script.md exactly**

Open `demo/demo_script.md`. Follow every action verbatim. Time with a stopwatch.

Expected time: 1:45–2:10.

- [ ] **Rehearsal 1:** note any jank (loading spinners, missing data, broken URLs)
- [ ] Fix issues, commit
- [ ] **Rehearsal 2:** smoother; note remaining rough edges
- [ ] Fix issues, commit
- [ ] **Rehearsal 3:** must be clean. If a step fails, fix before submitting.

- [ ] **Step 2: Record demo video**

```bash
# macOS: use QuickTime → File → New Screen Recording
# Target: 1920×1200, 30fps, microphone on
```

- [ ] **Step 3: Final check — all smoke targets pass**

```bash
make test
make smoke-api
make smoke-morph
make smoke-gnn
make smoke-seed
# Expected: all green
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: integration complete — all smoke tests pass, demo rehearsed 3×"
```

---

## Task INT-6: Devpost submission

- [ ] **Step 1: Write devpost description** (use `blog/draft.md` sections 1-3)
- [ ] **Step 2: Upload demo video**
- [ ] **Step 3: Add GitHub repo link**
- [ ] **Step 4: List tech stack:** Next.js 14, FastAPI, Supabase, Modal, PyTorch Geometric, MuJoCo, Gemini Robotics-ER 1.6, GVHMR, Karpathy autoresearch pattern
- [ ] **Step 5: Submit**
