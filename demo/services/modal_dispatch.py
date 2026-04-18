from __future__ import annotations
from packages.pipeline.types import TrialResult


class ModalDispatch:
    def __init__(self) -> None:
        try:
            from scripts.modal_trial_runner import run_trial
            self._remote_fn = run_trial.remote
        except Exception:
            self._remote_fn = None

    def run_trial(
        self,
        evolution_id: str,
        iter_num: int,
        train_py_source: str,
        morph_factory_source: str,
        smpl_trajectory_url: str,
        epochs: int = 40,
    ) -> TrialResult:
        if self._remote_fn is None:
            raise RuntimeError(
                "Modal trial runner not available — deploy scripts/modal_trial_runner.py first"
            )
        raw = self._remote_fn(
            evolution_id=evolution_id,
            iter_num=iter_num,
            train_py_source=train_py_source,
            morph_factory_source=morph_factory_source,
            smpl_trajectory_url=smpl_trajectory_url,
            epochs=epochs,
        )
        return TrialResult(**raw)
