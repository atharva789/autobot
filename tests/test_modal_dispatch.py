import pytest
from unittest.mock import patch, MagicMock
from demo.services.modal_dispatch import ModalDispatch
from packages.pipeline.types import TrialResult


def test_dispatch_returns_trial_result():
    dispatch = ModalDispatch.__new__(ModalDispatch)
    mock_result = {
        "tracking_error": 0.12, "er16_success_prob": 0.75,
        "fitness_score": 0.672, "replay_mp4_url": "https://x",
        "controller_ckpt_url": "https://y", "trajectory_npz_url": "https://z",
        "reasoning_md": "tried longer arms",
    }
    dispatch._remote_fn = MagicMock()
    dispatch._remote_fn.remote.return_value = mock_result
    result = dispatch.run_trial(
        evolution_id="evo-1", iter_num=3,
        train_py_source="x=1", morph_factory_source="y=2",
        smpl_trajectory_url="https://smpl", epochs=40,
    )
    assert isinstance(result, TrialResult)
    assert result.fitness_score == pytest.approx(0.672)


def test_dispatch_looks_up_deployed_modal_function(monkeypatch):
    mock_function = object()
    mock_modal = MagicMock()
    mock_modal.Function.from_name.return_value = mock_function

    with patch.dict("sys.modules", {"modal": mock_modal}):
        dispatch = ModalDispatch()

    assert dispatch._remote_fn is mock_function
    mock_modal.Function.from_name.assert_called_once_with("autoresearch-trial", "run_trial")
