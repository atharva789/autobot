from __future__ import annotations

import json

from packages.pipeline.droid_fallback import (
    DroidDatasetFormat,
    DroidEpisodeRecord,
    DroidFallbackIndex,
    DroidFallbackQuery,
    DroidFallbackResult,
)


def test_droid_fallback_ranks_language_match_first():
    index = DroidFallbackIndex(
        episodes=[
            DroidEpisodeRecord(
                episode_id="ep-1",
                dataset_format=DroidDatasetFormat.RLDS,
                task_text="carry a box down stairs",
                language_annotations=["carry box down stairs", "stair carry"],
                action_path="gs://droid/ep-1/trajectory.h5",
                state_path="gs://droid/ep-1/trajectory.h5",
                camera_refs={"front": "gs://droid/ep-1/front.mp4"},
                confidence_hint=0.9,
            ),
            DroidEpisodeRecord(
                episode_id="ep-2",
                dataset_format=DroidDatasetFormat.RAW,
                task_text="open a drawer",
                language_annotations=["drawer opening"],
                action_path="gs://droid/ep-2/trajectory.h5",
                state_path="gs://droid/ep-2/trajectory.h5",
                camera_refs={"front": "gs://droid/ep-2/front.mp4"},
                confidence_hint=0.5,
            ),
        ]
    )

    result = index.retrieve(
        DroidFallbackQuery(
            query_text="carry heavy objects down a slippery slope",
            required_task_terms=["carry", "slope"],
        )
    )

    assert isinstance(result, DroidFallbackResult)
    assert result.episode_id == "ep-1"
    assert result.source_format in {DroidDatasetFormat.RLDS, DroidDatasetFormat.RAW}
    assert result.match_score > 0.7
    assert result.action_path.endswith("trajectory.h5")
    assert "carry" in result.reason.lower()


def test_droid_fallback_loads_real_jsonl_index_and_preserves_windows(tmp_path):
    index_path = tmp_path / "droid-index.jsonl"
    rows = [
        {
            "episode_id": "ep-windowed",
            "dataset_format": "lerobot_v3",
            "task_text": "climb a rocky incline while carrying a pack",
            "language_annotations": [
                "rock climbing with load",
                "carry backpack up slope",
            ],
            "action_path": "hf://droid/ep-windowed/actions.parquet",
            "state_path": "hf://droid/ep-windowed/states.parquet",
            "camera_refs": {"wrist": "hf://droid/ep-windowed/wrist.mp4"},
            "confidence_hint": 0.82,
            "trajectory_window": [24, 96],
        },
        {
            "episode_id": "ep-unrelated",
            "dataset_format": "raw",
            "task_text": "open a cabinet door",
            "language_annotations": ["cabinet open"],
            "action_path": "hf://droid/ep-unrelated/actions.parquet",
            "state_path": "hf://droid/ep-unrelated/states.parquet",
            "camera_refs": {"front": "hf://droid/ep-unrelated/front.mp4"},
            "confidence_hint": 0.25,
        },
    ]
    index_path.write_text("\n".join(json.dumps(row) for row in rows))

    index = DroidFallbackIndex.load_jsonl(index_path)
    result = index.retrieve(
        DroidFallbackQuery(
            query_text="carry equipment while climbing a slippery incline",
            required_task_terms=["carry", "climbing"],
            preferred_camera_terms=["wrist"],
        )
    )

    assert result.episode_id == "ep-windowed"
    assert result.source_format == DroidDatasetFormat.LEROBOT_V3
    assert result.trajectory_window == (24, 96)
    assert result.camera_refs["wrist"].endswith("wrist.mp4")
    assert result.match_score > 0.5
    assert "trajectory pointers available" in result.reason
