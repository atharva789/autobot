from pathlib import Path

from demo.services.evolution_service import EvolutionService
from demo.workspace_store import WorkspaceStore


def test_create_evolution_returns_id_and_persists(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "evolutions.sqlite3")
    svc = EvolutionService(store=store)

    evo_id = svc.create(run_id="run-1")

    persisted = store.get_evolution(evo_id)
    assert persisted is not None
    assert persisted["id"] == evo_id
    assert persisted["run_id"] == "run-1"
    assert persisted["status"] == "pending"


def test_update_status_set_best_and_add_cost_are_persisted(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "evolutions.sqlite3")
    svc = EvolutionService(store=store)
    evo_id = svc.create(run_id="run-1")

    svc.update_status(evo_id, "running")
    svc.set_best(evo_id, "iter-7")
    svc.add_cost(evo_id, 1.25)
    svc.add_cost(evo_id, 0.75)

    evo = svc.get(evo_id)
    assert evo["status"] == "running"
    assert evo["best_iteration_id"] == "iter-7"
    assert evo["total_cost_usd"] == 2.0


def test_record_iteration_creates_retrievable_iteration(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "evolutions.sqlite3")
    svc = EvolutionService(store=store)
    evo_id = svc.create(run_id="run-1")

    iteration_id = svc.record_iteration(
        evo_id,
        3,
        {
            "fitness_score": 0.81,
            "tracking_error": 0.14,
            "replay_mp4_url": "https://example.com/replay.mp4",
            "reasoning_log": "Improved torso balance and stair clearance.",
        },
    )

    stored = store.get_iteration(iteration_id)
    assert stored is not None
    assert stored["evolution_id"] == evo_id
    assert stored["iter_num"] == 3
    assert stored["fitness_score"] == 0.81
    assert stored["tracking_error"] == 0.14
    assert stored["replay_mp4_url"] == "https://example.com/replay.mp4"
