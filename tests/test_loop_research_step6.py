"""Build-order step 6 tests (plan.md §7): "Actions workflow + Compose stack, running steps 1-5 in
CI. Gate: green run, logs committed."

`orchestrator.py`'s job today is to re-run steps 1-5's own committed-evidence generators
(`step2_run`, `step4_run`, `step5_run`) and aggregate pass/fail — these tests cover that
aggregation logic against fake steps (so they run instantly and don't spend real wall-clock on
physics rollouts already covered by `tests/test_loop_research_step{2,4,5}.py`), plus one real,
disk-touching smoke of the full pipeline to prove the wiring against the actual step modules.

`gates.py`'s job is to backfill G1 for scaffolds a crashed run left ungated — tested against a
real scaffold and a real temp run directory, since that IO path (reading/writing `gates.json`) is
exactly what would be wrong if it were faked.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace

from packages.research.loop_research import orchestrator
from packages.research.loop_research.baselines import build_dev_a_baseline
from packages.research.loop_research.gates import backfill_g1, load_scaffold


def test_run_pipeline_aggregates_all_pass(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "_STEPS",
        (("a", lambda: 0), ("b", lambda: 0)),
    )
    results = orchestrator.run_pipeline()
    assert [r["step"] for r in results] == ["a", "b"]
    assert all(r["passed"] for r in results)
    assert all(r["error"] is None for r in results)


def test_run_pipeline_records_failure_without_aborting(monkeypatch):
    calls = []

    def _failing():
        calls.append("b")
        return 1

    def _ok():
        calls.append("c")
        return 0

    monkeypatch.setattr(orchestrator, "_STEPS", (("b", _failing), ("c", _ok)))
    results = orchestrator.run_pipeline()

    assert calls == ["b", "c"], "a later step must still run after an earlier one fails"
    assert results[0]["passed"] is False
    assert results[1]["passed"] is True


def test_run_pipeline_records_exception_as_failure_not_a_crash(monkeypatch):
    def _raises():
        raise RuntimeError("boom")

    monkeypatch.setattr(orchestrator, "_STEPS", (("broken", _raises),))
    results = orchestrator.run_pipeline()

    assert results[0]["passed"] is False
    assert "boom" in results[0]["error"]


def test_orchestrator_main_writes_a_run_id_directory_verbatim(tmp_path, monkeypatch):
    """The workflow's 'Commit the run log' step looks for `.runs/loop_research/$LOOP_RUN_ID`
    exactly -- a caller-supplied run id must not be suffixed."""

    monkeypatch.setattr(orchestrator, "_RUNS_ROOT", tmp_path)
    monkeypatch.setattr(orchestrator, "_STEPS", (("noop", lambda: 0),))
    monkeypatch.setattr(orchestrator, "_git_sha", lambda: "test-sha")

    monkeypatch.setattr(sys, "argv", ["orchestrator", "--run-id", "2026-01-01T00-00-00Z_abc123"])
    exit_code = orchestrator.main()

    assert exit_code == 0
    run_dir = tmp_path / "2026-01-01T00-00-00Z_abc123"
    assert run_dir.is_dir()
    run = json.loads((run_dir / "run.json").read_text())
    assert run["run_id"] == "2026-01-01T00-00-00Z_abc123"
    assert run["control"]["orchestrator"]["all_passed"] is True


def test_orchestrator_full_pipeline_real_run(tmp_path, monkeypatch):
    """One real, disk-touching run of the actual step 2/4/5 generators, redirected to a temp
    runs root so it doesn't add a permanent .runs/loop_research/ entry every test run."""

    monkeypatch.setattr(orchestrator, "_RUNS_ROOT", tmp_path)
    import packages.research.loop_research.step2_run as step2_run
    import packages.research.loop_research.step4_run as step4_run
    import packages.research.loop_research.step5_run as step5_run

    monkeypatch.setattr(step2_run, "_RUNS_ROOT", tmp_path)
    monkeypatch.setattr(step4_run, "_RUNS_ROOT", tmp_path)
    monkeypatch.setattr(step5_run, "_RUNS_ROOT", tmp_path)

    results = orchestrator.run_pipeline()

    assert [r["step"] for r in results] == ["step2", "step4", "step5"]
    assert all(r["passed"] for r in results), results
    for r in results:
        assert (tmp_path / r["run_dir"]).is_dir()


def test_backfill_g1_computes_missing_gate(tmp_path):
    scaffold = build_dev_a_baseline()
    run_dir = tmp_path / "run"
    (run_dir / "scaffolds").mkdir(parents=True)
    (run_dir / "scaffolds" / f"{scaffold.scaffold_id}.json").write_text(
        json.dumps(asdict(scaffold), indent=2)
    )

    new_gates = backfill_g1(run_dir)

    assert len(new_gates) == 1
    assert new_gates[0].gate == "G1"
    assert new_gates[0].passed
    gates_on_disk = json.loads((run_dir / "gates.json").read_text())
    assert len(gates_on_disk) == 1


def test_backfill_g1_is_idempotent(tmp_path):
    scaffold = build_dev_a_baseline()
    run_dir = tmp_path / "run"
    (run_dir / "scaffolds").mkdir(parents=True)
    (run_dir / "scaffolds" / f"{scaffold.scaffold_id}.json").write_text(
        json.dumps(asdict(scaffold), indent=2)
    )

    first = backfill_g1(run_dir)
    second = backfill_g1(run_dir)

    assert len(first) == 1
    assert second == [], "an already-gated scaffold must not be re-scored or duplicated"
    gates_on_disk = json.loads((run_dir / "gates.json").read_text())
    assert len(gates_on_disk) == 1


def test_backfill_g1_skips_unknown_schema_id(tmp_path):
    scaffold = build_dev_a_baseline()
    unknown = replace(scaffold, schema_id="not-a-locked-schema")
    run_dir = tmp_path / "run"
    (run_dir / "scaffolds").mkdir(parents=True)
    (run_dir / "scaffolds" / f"{unknown.scaffold_id}.json").write_text(json.dumps(asdict(unknown), indent=2))

    new_gates = backfill_g1(run_dir)
    assert new_gates == []
    assert not (run_dir / "gates.json").exists()


def test_load_scaffold_round_trips(tmp_path):
    scaffold = build_dev_a_baseline()
    path = tmp_path / "s.json"
    path.write_text(json.dumps(asdict(scaffold), indent=2))

    loaded = load_scaffold(path)
    assert loaded == scaffold
