import pytest
import uuid
from unittest.mock import MagicMock
from demo.services.evolution_service import EvolutionService


@pytest.fixture
def svc():
    mock_supa = MagicMock()
    mock_supa.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "evo-1", "status": "pending"}]
    )
    mock_supa.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "evo-1", "status": "pending", "best_iteration_id": None, "total_cost_usd": 0}
    )
    return EvolutionService(supa=mock_supa)


def test_create_evolution_returns_id(svc):
    evo_id = svc.create(run_id="run-1")
    assert evo_id == "evo-1"


def test_get_evolution(svc):
    evo = svc.get("evo-1")
    assert evo["status"] == "pending"


def test_update_best_iteration(svc):
    svc.supa.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    svc.set_best("evo-1", "iter-7")
