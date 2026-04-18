from __future__ import annotations

import json
from pathlib import Path

import pytest

from demo.service import DemoService
from demo.store import DemoStore


def _seed_store(store: DemoStore) -> None:
    store.seed_clips(
        [
            {"id": "waving_person", "label": "Waving Person", "video_path": "tmp_clips/tennis.mp4"},
        ]
    )


def test_execute_run_writes_replay_and_npz(tmp_path: Path) -> None:
    store = DemoStore(tmp_path / "demo.sqlite3")
    _seed_store(store)
    service = DemoService(
        store=store,
        replays_dir=tmp_path / "data" / "replays",
        exports_dir=tmp_path / "data" / "exports",
    )
    run = service.start_run(prompt="wave both arms", clip_id="waving_person")

    completed = service.execute_run(run.id)
    assert completed.status == "completed"
    assert completed.replay_path is not None
    assert completed.retarget_npz_path is not None
    assert Path(completed.replay_path).exists()
    assert Path(completed.retarget_npz_path).exists()


def test_export_requires_approval(tmp_path: Path) -> None:
    store = DemoStore(tmp_path / "demo.sqlite3")
    _seed_store(store)
    service = DemoService(
        store=store,
        replays_dir=tmp_path / "data" / "replays",
        exports_dir=tmp_path / "data" / "exports",
    )
    run = service.start_run(prompt="wave both arms", clip_id="waving_person")
    service.execute_run(run.id)

    with pytest.raises(ValueError, match="approved"):
        service.export_run(run.id)


def test_export_produces_parquet_named_artifact(tmp_path: Path) -> None:
    store = DemoStore(tmp_path / "demo.sqlite3")
    _seed_store(store)
    service = DemoService(
        store=store,
        replays_dir=tmp_path / "data" / "replays",
        exports_dir=tmp_path / "data" / "exports",
    )
    run = service.start_run(prompt="wave both arms", clip_id="waving_person")
    service.execute_run(run.id)
    service.approve_run(run.id)

    export = service.export_run(run.id)
    assert export.parquet_path.endswith(".parquet")
    payload = json.loads(Path(export.parquet_path).read_text())
    assert payload["run_id"] == run.id
    assert payload["task"] == "wave both arms"

