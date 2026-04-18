from __future__ import annotations
import uuid


class EvolutionService:
    def __init__(self, supa: object) -> None:
        self.supa = supa

    def create(self, run_id: str) -> str:
        evo_id = str(uuid.uuid4())
        resp = (
            self.supa.table("evolutions")
            .insert({"id": evo_id, "run_id": run_id, "status": "pending"})
            .execute()
        )
        return resp.data[0]["id"]

    def get(self, evo_id: str) -> dict:
        resp = (
            self.supa.table("evolutions")
            .select("*")
            .eq("id", evo_id)
            .single()
            .execute()
        )
        return resp.data

    def update_status(self, evo_id: str, status: str) -> None:
        self.supa.table("evolutions").update({"status": status}).eq("id", evo_id).execute()

    def set_best(self, evo_id: str, iter_id: str) -> None:
        self.supa.table("evolutions").update({"best_iteration_id": iter_id}).eq("id", evo_id).execute()

    def add_cost(self, evo_id: str, delta_usd: float) -> None:
        evo = self.get(evo_id)
        new_cost = float(evo.get("total_cost_usd") or 0) + delta_usd
        self.supa.table("evolutions").update({"total_cost_usd": new_cost}).eq("id", evo_id).execute()

    def record_iteration(self, evo_id: str, iter_num: int, result: dict) -> str:
        iter_id = str(uuid.uuid4())
        self.supa.table("iterations").insert(
            {"id": iter_id, "evolution_id": evo_id, "iter_num": iter_num, **result}
        ).execute()
        return iter_id
