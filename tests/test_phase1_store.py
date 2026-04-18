from __future__ import annotations

from pathlib import Path

from demo.store import DemoStore


def test_store_creates_schema_and_seeds_clips(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.sqlite3"
    store = DemoStore(db_path)
    store.seed_clips(
        [
            {"id": "waving_person", "label": "Waving Person", "video_path": "tmp_clips/waving.mp4"},
            {"id": "sidestep_person", "label": "Sidestep Person", "video_path": "tmp_clips/sidestep.mp4"},
        ]
    )

    clips = store.list_clips()
    assert len(clips) == 2
    assert clips[0].id == "sidestep_person" or clips[0].id == "waving_person"


def test_store_can_create_and_read_run(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.sqlite3"
    store = DemoStore(db_path)
    store.seed_clips(
        [
            {"id": "waving_person", "label": "Waving Person", "video_path": "tmp_clips/waving.mp4"},
        ]
    )

    run = store.create_run(prompt="wave both arms", clip_id="waving_person")
    fetched = store.get_run(run.id)

    assert fetched is not None
    assert fetched.prompt == "wave both arms"
    assert fetched.clip_id == "waving_person"
    assert fetched.status == "queued"
    assert fetched.approved is False


def test_store_updates_run_status_and_paths(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.sqlite3"
    store = DemoStore(db_path)
    store.seed_clips(
        [
            {"id": "waving_person", "label": "Waving Person", "video_path": "tmp_clips/waving.mp4"},
        ]
    )
    run = store.create_run(prompt="wave", clip_id="waving_person")

    store.update_run(
        run_id=run.id,
        status="completed",
        replay_path="data/replays/run-1.mp4",
        retarget_npz_path="data/replays/run-1.npz",
    )
    fetched = store.get_run(run.id)
    assert fetched is not None
    assert fetched.status == "completed"
    assert fetched.replay_path == "data/replays/run-1.mp4"
    assert fetched.retarget_npz_path == "data/replays/run-1.npz"

