import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock


def _load_seed_module(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-service-key")
    import scripts.seed_clips as seed_clips

    return importlib.reload(seed_clips)


def test_seed_main_writes_manifest_with_uploaded_and_smpl_urls(tmp_path, monkeypatch):
    seed_clips = _load_seed_module(monkeypatch)
    manifest_path = tmp_path / "seed_manifest.json"
    clips = [
        {"id": "clip-a", "label": "Carry box", "url": "https://youtube.com/a", "start": 0, "end": 5},
        {"id": "clip-b", "label": "Climb stairs", "url": "https://youtube.com/b", "start": 2, "end": 8},
    ]
    uploaded_paths: list[str] = []
    gvhmr_inputs: list[str] = []
    mock_table = MagicMock()
    mock_table.upsert.return_value.execute.return_value = MagicMock()
    mock_supa = MagicMock()
    mock_supa.table.return_value = mock_table

    def fake_download(url: str, start: int, end: int, dest: Path) -> None:
        dest.write_bytes(f"{url}|{start}|{end}".encode("utf-8"))

    def fake_upload(local_path: Path, remote_path: str, bucket: str) -> str:
        uploaded_paths.append(remote_path)
        assert bucket == "videos"
        assert local_path.exists()
        return f"https://cdn.example/{remote_path}"

    def fake_run_gvhmr(video_url: str) -> str:
        gvhmr_inputs.append(video_url)
        return f"https://cdn.example/smpl/{Path(video_url).name}.pkl"

    monkeypatch.setattr(seed_clips, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(seed_clips, "CLIPS", clips)
    monkeypatch.setattr(seed_clips, "download_clip", fake_download)
    monkeypatch.setattr(seed_clips, "upload_to_supabase", fake_upload)
    monkeypatch.setattr(seed_clips, "run_gvhmr", fake_run_gvhmr)
    monkeypatch.setattr(seed_clips, "supa", mock_supa)

    seed_clips.main()

    manifest = json.loads(manifest_path.read_text())
    assert [clip["id"] for clip in manifest] == ["clip-a", "clip-b"]
    assert uploaded_paths == ["seed/clip-a.mp4", "seed/clip-b.mp4"]
    assert gvhmr_inputs == [
        "https://cdn.example/seed/clip-a.mp4",
        "https://cdn.example/seed/clip-b.mp4",
    ]
    assert all(item["video_url"].startswith("https://cdn.example/seed/") for item in manifest)
    assert all(item["smpl_url"].startswith("https://cdn.example/smpl/") for item in manifest)

    upsert_payloads = [call.args[0] for call in mock_table.upsert.call_args_list]
    assert upsert_payloads == [
        {
            "id": "clip-a",
            "label": "Carry box",
            "video_path": "https://cdn.example/seed/clip-a.mp4",
            "smpl_path": "https://cdn.example/smpl/clip-a.mp4.pkl",
        },
        {
            "id": "clip-b",
            "label": "Climb stairs",
            "video_path": "https://cdn.example/seed/clip-b.mp4",
            "smpl_path": "https://cdn.example/smpl/clip-b.mp4.pkl",
        },
    ]


def test_run_gvhmr_prefers_run_probe_remote(monkeypatch):
    seed_clips = _load_seed_module(monkeypatch)
    fake_response = {"smpl_url": "https://cdn.example/smpl/test.pkl"}
    fake_remote = MagicMock()
    fake_remote.remote.return_value = fake_response
    fake_module = MagicMock(run_probe=fake_remote, process_video=None)

    import sys

    monkeypatch.setitem(sys.modules, "scripts.gvhmr_modal_probe", fake_module)
    smpl_url = seed_clips.run_gvhmr("https://cdn.example/seed/test.mp4")

    assert smpl_url == "https://cdn.example/smpl/test.pkl"
    fake_remote.remote.assert_called_once_with(
        video_url="https://cdn.example/seed/test.mp4"
    )
