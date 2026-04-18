import json
from pathlib import Path

def test_seed_manifest_exists():
    manifest = Path("data/seed_manifest.json")
    assert manifest.exists(), "Run: python scripts/seed_clips.py first"
    clips = json.loads(manifest.read_text())
    assert len(clips) >= 3

def test_seed_manifest_has_smpl_paths():
    clips = json.loads(Path("data/seed_manifest.json").read_text())
    for clip in clips:
        assert "smpl_url" in clip, f"Missing smpl_url in clip {clip.get('id')}"
        assert clip["smpl_url"].startswith("https://"), f"Invalid URL: {clip['smpl_url']}"
