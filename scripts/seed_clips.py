"""
Download 4 reference clips, run GVHMR, upload artifacts to Supabase.
Run once: python scripts/seed_clips.py
"""
from __future__ import annotations
import json, os, subprocess, tempfile
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supa = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

CLIPS = [
    {
        "id":    "waving_person",
        "label": "Person waving",
        "url":   "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "start": 10,
        "end":   16,
    },
    {
        "id":    "box_lift",
        "label": "Person lifting a box",
        "url":   "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "start": 0,
        "end":   6,
    },
    {
        "id":    "arm_raise",
        "label": "Person raising arms",
        "url":   "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "start": 0,
        "end":   6,
    },
    {
        "id":    "sidestep",
        "label": "Person sidestepping",
        "url":   "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "start": 0,
        "end":   6,
    },
]

MANIFEST_PATH = Path("data/seed_manifest.json")


def download_clip(url: str, start: int, end: int, dest: Path) -> None:
    subprocess.run(
        ["yt-dlp", "-f", "mp4[height<=720]",
         "--external-downloader", "ffmpeg",
         "--external-downloader-args", f"-ss {start} -to {end}",
         "-o", str(dest), url],
        check=True,
    )


def upload_to_supabase(local_path: Path, remote_path: str, bucket: str) -> str:
    with open(local_path, "rb") as f:
        supa.storage.from_(bucket).upload(remote_path, f, {"upsert": "true"})
    return supa.storage.from_(bucket).get_public_url(remote_path)


def run_gvhmr(video_url: str) -> str:
    """Dispatch to Modal GVHMR endpoint. Returns SMPL pkl URL."""
    from scripts import gvhmr_modal_probe

    remote_fn = getattr(gvhmr_modal_probe, "run_probe", None) or getattr(
        gvhmr_modal_probe, "process_video", None
    )
    if remote_fn is None:
        raise RuntimeError(
            "GVHMR Modal module does not expose `run_probe` or `process_video`."
        )
    result = remote_fn.remote(video_url=video_url)
    return result.get("smpl_url", "")


def main() -> None:
    manifest = []
    for clip in CLIPS:
        print(f"Processing: {clip['id']}")
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / f"{clip['id']}.mp4"
            download_clip(clip["url"], clip["start"], clip["end"], mp4)

            video_url = upload_to_supabase(mp4, f"seed/{clip['id']}.mp4", "videos")
            smpl_url = run_gvhmr(video_url)

            supa.table("clips").upsert({
                "id":         clip["id"],
                "label":      clip["label"],
                "video_path": video_url,
                "smpl_path":  smpl_url,
            }).execute()

            manifest.append({
                "id":        clip["id"],
                "label":     clip["label"],
                "video_url": video_url,
                "smpl_url":  smpl_url,
            })
            print(f"  ✓ {clip['id']}: video={video_url[:60]}...")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"\n✓ Manifest written to {MANIFEST_PATH}")
    print(f"✓ {len(manifest)} clips seeded in Supabase")


if __name__ == "__main__":
    main()
