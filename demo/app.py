from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from demo.service import DemoService
from demo.store import DemoStore


DEFAULT_CLIPS: list[dict[str, str]] = [
    {"id": "waving_person", "label": "Waving Person", "video_path": "tmp_clips/tennis.mp4"},
    {"id": "sidestep_person", "label": "Sidestep Person", "video_path": "tmp_clips/tennis.mp4"},
    {"id": "arm_raise_person", "label": "Arm Raise Person", "video_path": "tmp_clips/tennis.mp4"},
]


class CreateRunRequest(BaseModel):
    prompt: str
    clip_id: str


def create_app(
    db_path: Path = Path("data/demo.sqlite3"),
    replays_dir: Path = Path("data/replays"),
    exports_dir: Path = Path("data/exports"),
) -> FastAPI:
    store = DemoStore(db_path)
    store.seed_clips(DEFAULT_CLIPS)
    service = DemoService(store=store, replays_dir=replays_dir, exports_dir=exports_dir)

    app = FastAPI(title="Prompt2Policy Data Demo API")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/clips")
    def list_clips() -> dict[str, list[dict[str, Any]]]:
        items = [clip.__dict__ for clip in store.list_clips()]
        return {"items": items}

    @app.post("/runs", status_code=201)
    def create_run(req: CreateRunRequest) -> dict[str, Any]:
        try:
            run = service.start_run(prompt=req.prompt, clip_id=req.clip_id)
            run = service.execute_run(run.id)
            return run.__dict__
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Unknown run id: {run_id}")
        return run.__dict__

    @app.post("/runs/{run_id}/approve")
    def approve_run(run_id: str) -> dict[str, Any]:
        try:
            run = service.approve_run(run_id)
            return run.__dict__
        except ValueError as exc:
            message = str(exc)
            status = 404 if "Unknown run id" in message else 400
            raise HTTPException(status_code=status, detail=message) from exc

    @app.post("/runs/{run_id}/export", status_code=201)
    def export_run(run_id: str) -> dict[str, Any]:
        try:
            record = service.export_run(run_id)
            return record.__dict__
        except ValueError as exc:
            message = str(exc)
            status = 404 if "Unknown run id" in message else 400
            raise HTTPException(status_code=status, detail=message) from exc

    return app


app = create_app()

