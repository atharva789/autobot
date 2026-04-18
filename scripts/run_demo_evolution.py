"""
Run a full 20-iteration evolution overnight on the box-lift clip.
Results will be displayed from Supabase history in the live demo.
Run the night before the demo: python scripts/run_demo_evolution.py
"""
from __future__ import annotations
import httpx, time

BASE = "http://localhost:8000"


def main() -> None:
    print("Using pre-seeded 'box_lift' clip for demo evolution")

    r = httpx.post(f"{BASE}/evolutions", json={
        "run_id": "demo-run-1",
        "ingest_job_id": "box_lift",
    }, timeout=30)
    evo = r.json()
    evo_id = evo["evolution_id"]
    print(f"Evolution: {evo_id}")
    print(f"\nDraft program.md:\n{evo['draft_content']}\n")

    curated = open("data/artifacts/evolutions/template/program.md.example").read()
    httpx.post(f"{BASE}/evolutions/{evo_id}/approve-program",
               json={"content": curated}, timeout=10)
    print("Approved. Evolution running (20 iters, ~2h)…")

    while True:
        r = httpx.get(f"{BASE}/evolutions/{evo_id}", timeout=5)
        evo_data = r.json()
        status = evo_data.get("status")
        cost = evo_data.get("total_cost_usd", 0)
        print(f"  status={status} cost=${cost:.2f}", end="\r", flush=True)
        if status in ("done", "stopped"):
            break
        time.sleep(30)

    print(f"\n✓ Demo evolution complete. Best: {evo_data.get('best_iteration_id')}")
    print(f"  Total cost: ${evo_data.get('total_cost_usd', 0):.2f}")
    print(f"\nSet this evolution ID in demo script: {evo_id}")


if __name__ == "__main__":
    main()
