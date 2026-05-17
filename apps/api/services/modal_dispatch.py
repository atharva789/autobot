from __future__ import annotations
import os

from packages.pipeline.types import TrialResult


class ModalDispatch:
    def __init__(self) -> None:
        try:
            import modal

            app_name = os.environ.get("MODAL_TRIAL_APP_NAME", "autoresearch-trial")
            function_name = os.environ.get("MODAL_TRIAL_FUNCTION_NAME", "run_trial")
            self._remote_fn = modal.Function.from_name(app_name, function_name)
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
        raw = self._remote_fn.remote(
            evolution_id=evolution_id,
            iter_num=iter_num,
            train_py_source=train_py_source,
            morph_factory_source=morph_factory_source,
            smpl_trajectory_url=smpl_trajectory_url,
            epochs=epochs,
        )
        return TrialResult(**raw)
