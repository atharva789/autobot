"""
End-to-end smoke test. Uses real Modal + real Supabase. Mocks Gemini + YouTube.
Runs 3 iterations. Expected wall-clock: ~12 min.
Run: python tests/e2e_smoke.py
"""
from __future__ import annotations
import os, time
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
    timeout = 800
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
    print("✓ Mark-best override: OK")

    # 8. Stop
    r = httpx.post(f"http://localhost:8000/evolutions/{evo_id}/stop", timeout=5)
    assert r.status_code == 200
    print("✓ Stop: OK")

    print("\n=== E2E SMOKE PASSED ===")


if __name__ == "__main__":
    main()
