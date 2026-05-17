from __future__ import annotations
import uuid


class EvolutionService:
    def __init__(self, store: object) -> None:
        self.store = store

    def create(self, run_id: str) -> str:
        evo_id = str(uuid.uuid4())
        self.store.create_evolution(run_id, evo_id=evo_id)
        return evo_id

    def get(self, evo_id: str) -> dict:
        return self.store.get_evolution(evo_id)

    def update_status(self, evo_id: str, status: str) -> None:
        self.store.update_evolution(evo_id, {"status": status})

    def set_best(self, evo_id: str, iter_id: str) -> None:
        self.store.update_evolution(evo_id, {"best_iteration_id": iter_id})

    def add_cost(self, evo_id: str, delta_usd: float) -> None:
        evo = self.get(evo_id)
        new_cost = float(evo.get("total_cost_usd") or 0) + delta_usd
        self.store.update_evolution(evo_id, {"total_cost_usd": new_cost})

    def record_iteration(self, evo_id: str, iter_num: int, result: dict) -> str:
        iter_id = str(uuid.uuid4())
        self.store.record_iteration(
            {"id": iter_id, "evolution_id": evo_id, "iter_num": iter_num, **result}
        )
        return iter_id
